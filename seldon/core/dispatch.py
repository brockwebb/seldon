"""The standing dispatcher's pure logic: candidacy, eligibility, the lease, the config.

`docs/design/2026-09-15_standing_dispatcher.md` in this repo describes the command group;
`ai-readiness-kg/docs/design/2026-09-15_DN-006_standing_dispatcher.md` is the design note this
implements, and its §3 decisions are the spec.

**The condition this closes.** A registered ResearchTask whose gate is clean waited in
`proposed` until a person relayed a dispatch line into Claude Code. Nothing about *which* task
to run was missing — only the act of starting it. That is a latency defect, and it is the only
one this module addresses (DN-006 §4 is explicit that post-completion decision latency is not
touched).

**Everything here is pure or filesystem-local.** No Neo4j, no subprocess, no launch. The command
module composes these against the graph; keeping the evaluation separable is what lets each
criterion be tested against a fixture task file that fails exactly that one.

Prior art the shape is taken from, read before designing (DN-006 §2): Airflow's scheduler claim
as a database row transition rather than a message; the Kubernetes `Lease` object's separation
of holder identity from the thing acted on; Chubby (Burrows, OSDI 2006) for advisory locks whose
holder is identified and whose release is never inferred from age alone.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

#: DN-006 decision 3, as corrected by this build's ADDENDUM_01 to that note. The marker survey
#: over 34 addenda in `ai-readiness-kg/cc_tasks/` found a `**Status:**` field in the first ten
#: lines to be an existing habit (5 files) with an upper-case verb vocabulary — `AMENDS` in
#: four, `SUPERSEDED` in one — but only ONE file has ever expressed base-task supersession, and
#: it spells it `**Status of base task: SUPERSEDED — DO NOT EXECUTE.**`
#: (`2026-09-01_harness_reconciliation_ADDENDUM-01.md`). One instance in 34 is not a convention,
#: so decision 3's `**Status:** SUPERSEDED` is what gets written from here on; the matcher also
#: accepts the one historical spelling, because the alternative is a dispatcher that reads the
#: single genuinely superseded task in the repository as executable.
#:
#: Case-sensitive on `SUPERSEDED` deliberately: `**Status:** AMENDS the base task. Does not
#: supersede it.` is four of the five Status lines, and lower-case `supersede` inside a sentence
#: saying the opposite is exactly what a case-insensitive match would read as a supersession.
SUPERSEDED_MARKER = "**Status:** SUPERSEDED"
SUPERSEDED_RE = re.compile(r"\*\*Status(?:\s+of\s+base\s+task)?\s*:?\*?\*?:?\s*[^*\n]*"
                           r"\bSUPERSEDED\b")
#: How far into an addendum the marker must appear. DN-006 decision 3.
MARKER_WINDOW_LINES = 10

#: The three headers a dispatchable task file must carry. The first two are DN-006 decision 2;
#: the third is ADDENDUM_01 to the implementing task, which binds DN-005 §5 rule 1 — every task
#: names the framework layer it advances, or says it is hygiene — to something other than a
#: reader's attention.
#:
#: The dispatcher does not judge whether the named layer is the RIGHT one. It asserts that a
#: layer was named, which is what the rule requires.
HEADER_SPEND = "Spend"
HEADER_NETWORK = "Network"
HEADER_LAYER = "Framework layer served"
REQUIRED_HEADERS = (HEADER_SPEND, HEADER_NETWORK, HEADER_LAYER)

#: `**Spend:** zero model calls.` / `**Network:** none.` / `**Framework layer served (DN-005 §5
#: rule 1):** §2.2 Tier M.` — the same bolded-header shape `seldon cc register` already parses.
#: The header name may carry a parenthetical, which the third one does.
_HEADER_RE_CACHE: dict[str, re.Pattern] = {}


def _header_re(name: str) -> re.Pattern:
    if name not in _HEADER_RE_CACHE:
        _HEADER_RE_CACHE[name] = re.compile(
            r"\*\*" + re.escape(name) + r"(?:\s*\([^)]*\))?\s*:?\*\*\s*(?P<value>[^\n]*)"
            r"|\*\*" + re.escape(name) + r"(?:\s*\([^)]*\))?\s*:(?P<v2>[^*\n]*)\*\*"
            r"(?P<rest>[^\n]*)")
    return _HEADER_RE_CACHE[name]

#: A framework-layer value that satisfies ADDENDUM_01: a DN-005 §2 layer reference, a capability
#: tier, or the word `none` for a hygiene task.
_LAYER_VALUE_RE = re.compile(r"§\s?2\.[1-5]\b|\bTier\s+[MOD]\b|\bnone\b", re.IGNORECASE)

#: `zero` in a Spend header means zero model calls. Anything else must name a token count that
#: the standing band can be compared against; `M`/`K` suffixes are the spelling the task files
#: and `--ceiling-tokens` already use.
_ZERO_RE = re.compile(r"\bzero\b", re.IGNORECASE)
_TOKENS_RE = re.compile(r"(?P<n>\d[\d,_]*(?:\.\d+)?)\s*(?P<suffix>[MmKk])?\s*(?:tokens?|$|[ .,;)])")

#: `**Network:** none` is the only value that passes without a cadence provenance. DN-006
#: decision 5's second limb (a task created by the cadence rule) is decision 8's work and is not
#: implemented here; a task carrying that provenance is recognised so the criterion does not
#: have to change when it arrives.
_NETWORK_NONE_RE = re.compile(r"\bnone\b", re.IGNORECASE)
_NETWORK_CADENCE_RE = re.compile(r"under\s+cadence\s+\S+", re.IGNORECASE)

#: Predecessor states that let a successor run (DN-006 decision 2, c2). `blocked` and `rejected`
#: are deliberately absent: a successor whose predecessor is blocked is a successor whose
#: premise nobody has checked.
PREDECESSOR_SATISFIED = ("completed", "verified", "superseded", "withdrawn")

#: The states a task may be dispatched from (c1).
DISPATCHABLE_STATES = ("proposed", "accepted")

#: DN-006 decision 7's event names.
EVENT_LAUNCHED = "dispatch_launched"
EVENT_FINISHED = "dispatch_finished"
EVENT_REFUSED = "dispatch_refused"
EVENT_OBSERVED_STOP = "dispatch_observed_stop"

#: Refusal reasons. A closed set, so `status` and the log speak one vocabulary.
REFUSAL_REASONS = ("lease_held", "stop_file", "disabled", "dirty_tree", "above_band",
                   "network_undeclared", "api_key_present", "claim_failed")

#: DD-007. The subscription-OAuth gate, the same one `kg/extraction/model_stub.py` enforces at
#: its own choke point: an inherited API key means a dispatched session would spend against a
#: credential nobody declared. Checked BEFORE any claim, so a refusal leaves no state change.
API_KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


class DispatchConfigError(ValueError):
    """The `dispatch:` block is missing, malformed, or names a reference that does not resolve."""


# --------------------------------------------------------------------------- configuration

def load_dispatch_config(project_dir: Path, config: dict | None = None) -> dict:
    """The project's `dispatch:` block, validated. Read at call time, never cached.

    DN-006 decision 2's c8 requires `enabled` and the STOP file to be read on *every* pass; a
    cached config would make the kill switch advisory, which is the one thing a kill switch may
    not be (DD-004).
    """
    if config is None:
        config = yaml.safe_load((project_dir / "seldon.yaml").read_text(encoding="utf-8"))
    block = (config or {}).get("dispatch")
    if block is None:
        raise DispatchConfigError(
            f"{project_dir}/seldon.yaml has no `dispatch:` block; the dispatcher is opt-in per "
            f"project and refuses to guess one")
    for key in ("enabled", "branch", "standing_band_ref", "poll_interval_s", "permission_mode",
                "stop_file", "log_dir", "lease_file"):
        if key not in block:
            raise DispatchConfigError(f"seldon.yaml dispatch block missing {key!r}")
    if not isinstance(block["enabled"], bool):
        raise DispatchConfigError(
            f"dispatch.enabled must be a bool, got {block['enabled']!r}: a kill switch that "
            f"can be a truthy string is a kill switch nobody can read")
    return block


def resolve_standing_band(project_dir: Path, ref: str) -> int:
    """`controls.yaml#spend.daily_tokens` -> the int that file holds, today.

    A REFERENCE and never a copied number (DN-006 §5): the standing band is the same value the
    spend guard enforces, and a second copy of it in `seldon.yaml` would be a number that drifts
    silently the first time the operator moves the cap.
    """
    if "#" not in ref:
        raise DispatchConfigError(
            f"standing_band_ref {ref!r} is not a reference: expected `<file>#<dotted.path>`")
    rel, dotted = ref.split("#", 1)
    path = project_dir / rel
    if not path.is_file():
        raise DispatchConfigError(f"standing_band_ref {ref!r} names {rel}, which does not exist")
    node: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise DispatchConfigError(f"standing_band_ref {ref!r}: {rel} has no {dotted!r}")
        node = node[part]
    if not isinstance(node, int):
        raise DispatchConfigError(
            f"standing_band_ref {ref!r} resolves to {node!r}, which is not an integer token count")
    return node


# ------------------------------------------------------------------ the task file's headers

def _header_value(text: str, name: str) -> str | None:
    m = _header_re(name).search(text)
    if not m:
        return None
    if m.group("value") is not None:
        return m.group("value").strip()
    return ((m.group("v2") or "") + (m.group("rest") or "")).strip()


def parse_headers(text: str) -> dict:
    """The three headers, as raw values. `None` where the header is absent.

    Reads the same bolded-header lines `seldon cc register` already reads and adds nothing to
    the task file format — the opt-in is that a task file carries them, not that it adopts a
    new syntax (DN-006 decision 2).
    """
    return {name: _header_value(text, name) for name in REQUIRED_HEADERS}


def spend_tokens(value: str | None) -> int | None:
    """The Spend header as a token count: 0 for `zero`, the declared ceiling otherwise.

    `None` means the header says something this cannot read, which is a refusal and never a
    zero — a Spend line nobody can parse is the one case where guessing costs money.
    """
    if value is None:
        return None
    if _ZERO_RE.search(value):
        return 0
    m = _TOKENS_RE.search(value)
    if not m:
        return None
    n = float(m.group("n").replace(",", "").replace("_", ""))
    mult = {"m": 1_000_000, "k": 1_000}.get((m.group("suffix") or "").lower(), 1)
    return int(n * mult)


def network_declared_none(value: str | None) -> bool:
    if value is None:
        return False
    return bool(_NETWORK_NONE_RE.search(value) or _NETWORK_CADENCE_RE.search(value))


def layer_named(value: str | None) -> bool:
    """ADDENDUM_01: the header is present AND names a layer, a tier, or `none`."""
    return value is not None and bool(_LAYER_VALUE_RE.search(value))


def candidacy(task_file: Path) -> dict:
    """Is this task file dispatchable at all, and if not, which header failed.

    A task whose file lacks the headers is **not a candidate** — not "ineligible". The
    distinction is the whole opt-in (DN-006 decision 2): nothing already queued changes
    behaviour when the job is installed, and `status` can say so in one word.
    """
    if not task_file.is_file():
        return {"candidate": False, "reason": "source_file_missing", "headers": {}}
    text = task_file.read_text(encoding="utf-8", errors="surrogateescape")
    headers = parse_headers(text)
    missing = [n for n in REQUIRED_HEADERS if headers[n] is None]
    if missing:
        return {"candidate": False, "reason": f"no_header:{','.join(missing)}",
                "headers": headers}
    if not layer_named(headers[HEADER_LAYER]):
        return {"candidate": False, "reason": "framework_layer_names_no_layer",
                "headers": headers}
    return {"candidate": True, "reason": None, "headers": headers}


# ------------------------------------------------------------------------- the addendum scan

def addenda_for(task_file: Path) -> list[Path]:
    return sorted(task_file.parent.glob(f"{task_file.stem}_ADDENDUM*.md"))


def superseding_addendum(task_file: Path) -> Path | None:
    """The first sibling addendum carrying the supersession marker in its first ten lines."""
    for path in addenda_for(task_file):
        head = path.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
        for line in head[:MARKER_WINDOW_LINES]:
            # SEARCH, not match: every Status line in the surveyed repository sits after a
            # `**Date:** ...` on the same line, so an anchored pattern reads none of them.
            if SUPERSEDED_RE.search(line):
                return path
    return None


# --------------------------------------------------------------------------------- git state

def git(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=project_dir, capture_output=True, text=True)


def tree_state(project_dir: Path) -> dict:
    """`{branch, dirty, dirty_paths}` — c7's raw material, recorded as values.

    DN-006 decision 2 asks every criterion to be recorded as a value rather than a boolean
    summary, and this is the criterion where the value matters most: "the tree was dirty" is
    not actionable and "the tree was dirty on these three paths" is.
    """
    branch = git(project_dir, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    porcelain = git(project_dir, "status", "--porcelain").stdout.strip()
    paths = [ln[3:] for ln in porcelain.splitlines() if ln]
    return {"branch": branch, "dirty": bool(paths), "dirty_paths": paths[:20],
            "dirty_count": len(paths)}


def is_tracked(project_dir: Path, path: Path) -> bool:
    try:
        rel = path.relative_to(project_dir)
    except ValueError:
        return False
    r = git(project_dir, "ls-files", "--error-unmatch", str(rel))
    return r.returncode == 0


# ------------------------------------------------------------------------------- the lease

def holder_id(pid: int | None = None) -> str:
    return f"dispatcher:{socket.gethostname()}:{pid or os.getpid()}"


def pid_alive(pid: int) -> bool:
    """PID liveness, the DD-022 orphan-reap rule adopted unchanged (DN-006 §5).

    Never age. A reservation — or here a lease — is orphaned when its holder is gone, and a
    long-running holder is not an orphan however long it runs.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class LeaseHeld(RuntimeError):
    """Another dispatcher holds the flock. Not an error condition: a second pass exits 0."""

    def __init__(self, body: dict):
        self.body = body
        super().__init__(f"lease held by {body.get('holder')!r}")


class Lease:
    """`fcntl.flock` on `<project>/.seldon/dispatch.lock`, with an identified holder.

    The flock is the guard; the JSON body is the *record* of who holds it and what is in
    flight, so `status` and `lease reap` can answer without taking the lock. DD-019 is why the
    guard is hard rather than advisory: two runners on one queue is the batch-identity defect
    at runner grain, and that one cost 22.0M tokens against a 12M ceiling.
    """

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def __enter__(self) -> "Lease":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._fh.close()
            self._fh = None
            raise LeaseHeld(read_lease(self.path)) from exc
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.write({"holder": holder_id(), "pid": os.getpid(), "acquired_at": now,
                    "heartbeat_at": now, "task": None})
        return self

    def write(self, body: dict) -> None:
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(json.dumps(body, indent=1) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def heartbeat(self, task: str | None = None) -> None:
        body = read_lease(self.path)
        body["heartbeat_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if task is not None:
            body["task"] = task
        self.write(body)

    def __exit__(self, *exc) -> bool:
        if self._fh is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None
        return False


def read_lease(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {"unparseable": True}


def reap_lease(path: Path) -> dict:
    """The only release path other than process exit, and it refuses a live holder.

    No age-based auto-reap, for the reason DD-022 gives: an age threshold releases a lease a
    healthy long-running holder still needs, and the whole class of defect that guards against
    is two writers believing they are one.
    """
    body = read_lease(path)
    if not body:
        return {"reaped": False, "reason": "no_lease_file", "holder": None}
    pid = body.get("pid")
    if isinstance(pid, int) and pid_alive(pid):
        return {"reaped": False, "reason": "holder_alive", "holder": body.get("holder"),
                "pid": pid}
    path.unlink()
    return {"reaped": True, "reason": "holder_gone", "holder": body.get("holder"), "pid": pid}


# ------------------------------------------------------------------------------- evaluation

def evaluate(project_dir: Path, task: dict, cfg: dict, band: int, tree: dict,
             claim_in_flight: dict | None, lease_body: dict) -> dict:
    """The eight criteria of DN-006 decision 2, each evaluated to a recorded VALUE.

    Never a boolean summary: a pass that says "ineligible" and nothing else is a pass a
    stranger cannot replay, and DD-065 is that every assertion the project makes carries the
    grounds it was made on.
    """
    source = task.get("source_file")
    task_file = project_dir / source if source else None
    cand = candidacy(task_file) if task_file else {"candidate": False,
                                                   "reason": "no_source_file", "headers": {}}
    out = {"task_id": task.get("artifact_id"), "name": task.get("name"),
           "state": task.get("state"), "source_file": source,
           "candidate": cand["candidate"], "not_a_candidate_reason": cand["reason"],
           "framework_layer": cand["headers"].get(HEADER_LAYER)}
    if not cand["candidate"]:
        out["criteria"] = {}
        out["eligible"] = False
        return out

    headers = cand["headers"]
    sup = superseding_addendum(task_file)
    tokens = spend_tokens(headers[HEADER_SPEND])
    stop = project_dir / cfg["stop_file"]

    c = {}
    c["c1"] = {"state": task["state"], "source_file": source,
               "file_exists": task_file.is_file(),
               "git_tracked": is_tracked(project_dir, task_file),
               "ok": (task["state"] in DISPATCHABLE_STATES and task_file.is_file()
                      and is_tracked(project_dir, task_file))}
    preds = task.get("predecessors") or []
    unsatisfied = [p for p in preds if p.get("state") not in PREDECESSOR_SATISFIED]
    c["c2"] = {"predecessors": len(preds),
               "unsatisfied": [{"id": p.get("artifact_id"), "state": p.get("state")}
                               for p in unsatisfied],
               "ok": not unsatisfied}
    c["c3"] = {"addenda": [p.name for p in addenda_for(task_file)],
               "superseding": sup.name if sup else None, "ok": sup is None}
    c["c4"] = {"spend_header": headers[HEADER_SPEND], "declared_tokens": tokens,
               "standing_band": band, "band_ref": cfg["standing_band_ref"],
               "ok": tokens is not None and tokens <= band}
    c["c5"] = {"network_header": headers[HEADER_NETWORK],
               "ok": network_declared_none(headers[HEADER_NETWORK])}
    c["c6"] = {"in_progress_claim": claim_in_flight,
               "lease_task": lease_body.get("task"),
               "lease_holder": lease_body.get("holder"),
               "ok": claim_in_flight is None}
    c["c7"] = {"branch": tree["branch"], "configured_branch": cfg["branch"],
               "dirty": tree["dirty"], "dirty_count": tree["dirty_count"],
               "dirty_paths": tree["dirty_paths"],
               "ok": tree["branch"] == cfg["branch"] and not tree["dirty"]}
    c["c8"] = {"enabled": cfg["enabled"], "stop_file": str(cfg["stop_file"]),
               "stop_file_present": stop.exists(),
               "ok": bool(cfg["enabled"]) and not stop.exists()}
    #: ADDENDUM_01's criterion, numbered beyond DN-006's table rather than renumbering it: the
    #: note's decision 2 is cited by id elsewhere and a c-number that means two things in two
    #: documents is worse than a table with a ninth row.
    c["c9"] = {"framework_layer": headers[HEADER_LAYER], "ok": True}

    out["criteria"] = c
    out["eligible"] = all(v["ok"] for v in c.values())
    out["failed"] = [k for k, v in c.items() if not v["ok"]]
    return out


def first_refusal_reason(row: dict) -> str | None:
    """The refusal reason DN-006 decision 7 names, for a row that failed. Ordered so the
    SYSTEM-wide conditions are reported ahead of the task-specific ones: `disabled` and
    `stop_file` are facts about the pass, and reporting a per-task reason instead would put a
    task's name on a refusal that had nothing to do with it."""
    c = row.get("criteria") or {}
    if not c.get("c8", {}).get("ok", True):
        return "stop_file" if c["c8"]["stop_file_present"] else "disabled"
    if not c.get("c7", {}).get("ok", True):
        return "dirty_tree"
    if not c.get("c4", {}).get("ok", True):
        return "above_band"
    if not c.get("c5", {}).get("ok", True):
        return "network_undeclared"
    return None


def fifo(rows: list) -> list:
    """DN-006 decision 9: FIFO by `created_at` among eligible tasks, and nothing else. The
    Desktop orders work with `precedes` edges; a priority field would be a value nobody
    measured."""
    return sorted(rows, key=lambda r: (r.get("created_at") or "", r.get("task_id") or ""))


def api_key_present(env: dict | None = None) -> str | None:
    """The name of the first API-key variable set, or None. DD-007."""
    env = os.environ if env is None else env
    for var in API_KEY_VARS:
        if env.get(var):
            return var
    return None
