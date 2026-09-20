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

from seldon.core import cadence as C

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

#: The Network header's grammar (ai-readiness-kg/cc_tasks/2026-09-18_network_allowlist.md
#: decision 1, amending DN-006 decision 2). Network is a declared budget, like Spend, and not a
#: binary: a task either contacts no host, or names the exact hosts it may contact, or carries
#: the cadence provenance decision 8 writes. `beyond git push` is implied by all three.
#:
#: The shape is an egress allowlist, the way CI runners and build sandboxes declare network
#: (Nix and Bazel deny by default and allow named fetches). It is DECLARATIVE: macOS offers no
#: cheap per-process egress filter, so the dispatcher enforces nothing at the socket. The
#: session-side fetch helper refuses off-list hosts and logs every request, and the RESULT
#: quotes that log — the same standing as the Spend header, a declared budget audited after.
NETWORK_GRAMMAR = ("`**Network:** none` (optionally followed by prose, e.g. `none beyond "
                   "git push`), or `**Network:** allowlist: host1, host2, ...` with exact "
                   "hostnames (no wildcards, no schemes, no paths, no ports), or "
                   "`**Network:** <hosts>, under cadence <name>`")

#: `none` must LEAD the value. It used to match anywhere, so `the hosts in §2, none else`
#: passed as if it declared no network; every surveyed task file that meant none says so
#: first (`none.`, `none beyond git push`, `NONE — ...`, a backticked `none`).
_NETWORK_NONE_RE = re.compile(r"^[\s`*_]*none\b", re.IGNORECASE)
#: The child's copy of a launched task's allowlist, comma-separated. The session-side fetch
#: helper refuses any host not on it and refuses to run at all when it is unset; the dispatcher
#: strips any inherited value, so a `none` task never runs with a stale list.
NETWORK_ALLOWLIST_ENV = "SELDON_NETWORK_ALLOWLIST"
_NETWORK_CADENCE_RE = re.compile(r"under\s+cadence\s+\S+", re.IGNORECASE)
_NETWORK_ALLOWLIST_RE = re.compile(r"^[\s`*_]*allowlist\s*:(?P<hosts>.*)$", re.IGNORECASE)
#: RFC 1123 host names: dot-separated labels of letters, digits and inner hyphens, each at most
#: 63 characters, the whole at most 253. Compared case-insensitively (RFC 4343) and stored
#: lower-case, so the child's list and the helper's comparison speak one spelling.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")

#: The OPTIONAL fourth header, read by `seldon cc register` and not by candidacy
#: (ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence_after.md decision 3).
#:
#: **What it closes.** DN-007 records that SEQUENCING lines are "read into `precedes` edges
#: inconsistently". They are not read at all: a repo-wide `grep -rn -i sequencing seldon/` on
#: 2026-09-19 returned zero hits. `cc register` wrote no edge, dispatcher readiness reads
#: `precedes` edges only, and every such edge in ai-readiness-kg's graph was written by a
#: Desktop session calling `seldon_task_chain` by hand, when it remembered to. The sentence at
#: the end of a SEQUENCING line — "Not launched before `X.md` is `completed` on the graph" — is
#: prose the dispatcher cannot see, the same class as a supersession stated only in prose
#: (DN-006 ADDENDUM_01).
#:
#: Prior art, and the reason this is a separate header rather than a parser for the prose:
#: systemd's `After=` is an ORDERING-only declaration, deliberately separate from `Requires=`
#: (systemd.unit(5)) — which is exactly what `precedes` is, order and not requirement; Make
#: declares prerequisites where the scheduler reads them; Airflow's `set_upstream` is a call,
#: not a docstring. Every one of them puts the ordering in the machine-read place and leaves
#: the comment as a comment. The name is taken from systemd for that reason.
HEADER_AFTER = "After"
AFTER_GRAMMAR = ("`**After:** none`, or `**After:** <ref>[, <ref> ...]` where each ref is a "
                 "cc_tasks file stem (with or without `.md`) or an artifact id prefix of 8 or "
                 "more hex characters")
#: `none` must LEAD the value, for the reason `_NETWORK_NONE_RE` gives: a `none` matched
#: anywhere would read "after the scan, none of the report tasks" as declaring no predecessor.
_AFTER_NONE_RE = re.compile(r"^[\s`*_]*none\b", re.IGNORECASE)
#: A ref: a path-free stem, optionally `.md`, optionally backticked, optionally with a
#: `cc_tasks/` prefix that is stripped. No globs and no directories, so a ref names one file.
_AFTER_REF_RE = re.compile(r"^(?:cc_tasks/)?(?P<stem>[A-Za-z0-9][A-Za-z0-9._-]*?)(?:\.md)?$")
#: An artifact id prefix. Eight hex characters is what `short()` prints and what every task
#: file and commit message in these projects quotes.
AFTER_ID_MIN_HEX = 8
_AFTER_ID_RE = re.compile(r"^[0-9a-f]{%d,}$" % AFTER_ID_MIN_HEX)


def parse_after(value: str | None) -> dict:
    """The After header against :data:`AFTER_GRAMMAR`: `{kind, refs, error}`.

    `kind` is `none` or `refs` when the value parses, and `None` when it does not — in which
    case `error` says which part failed and quotes the grammar. The header is OPTIONAL: a
    `value` of None is `{"kind": "absent"}`, which means no edges, as before this existed.
    """
    if value is None:
        return {"kind": "absent", "refs": [], "error": None}
    stripped = value.strip()
    if not stripped:
        return {"kind": None, "refs": [],
                "error": f"After header is empty; expected {AFTER_GRAMMAR}"}
    if _AFTER_NONE_RE.match(stripped):
        return {"kind": "none", "refs": [], "error": None}
    # A trailing sentence period is prose, the way it is in the Network header's allowlist.
    stripped = stripped[:-1] if stripped.endswith(".") else stripped
    items = [r.strip().strip("`").strip() for r in stripped.split(",")]
    refs, bad = [], []
    for item in items:
        m = _AFTER_REF_RE.match(item)
        if not item or not m:
            bad.append(item)
            continue
        stem = m.group("stem")
        if stem not in refs:
            refs.append(stem)
    if bad:
        return {"kind": None, "refs": [],
                "error": (f"After header entries are not refs: "
                          f"{', '.join(repr(b) for b in bad)}; expected {AFTER_GRAMMAR}")}
    return {"kind": "refs", "refs": refs, "error": None}


def after_ref_is_id(ref: str) -> bool:
    """True when a ref may also be read as an artifact id prefix."""
    return bool(_AFTER_ID_RE.match(ref))


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
#: DN-006 decision 8's. A cadence that created a task asserted that a period was due and that
#: nothing had served it yet; that is a judgement and it goes on the log. A cadence that created
#: NOTHING writes no event, for decision 7's reason — a five-minute poll that logged its own
#: silence would bury the assertions in it.
EVENT_CADENCE_CREATED = "cadence_created"
#: A candidate refused on the same criterion for `dispatch.stuck_after_passes` consecutive
#: passes (ADDENDUM_01 to ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence
#: _after.md, decision 6b). The incident: 84 consecutive passes over seven hours printed
#: `65e5da0e dirty_tree: c7`, exit 0, no event, no notification, while one untracked task file
#: sat in `cc_tasks/`. Every refusal reason reachable from the quiet branch is a STANDING
#: condition, so decision 7 rightly forbids logging each pass — but a queue that can stop needs
#: a staleness alarm SEPARATE from its failure alarm. Prior art: the dead man's switch; Nagios
#: freshness checks; Prometheus `absent()` with a `for:` duration. A healthy exit code on a
#: pass that has refused the same candidate 84 times is the case those exist for.
EVENT_STUCK = "dispatch_stuck"
#: Passes on one criterion before the alarm. `seldon.yaml dispatch.stuck_after_passes`; at the
#: standing `poll_interval_s: 300` the default is fifteen minutes. **No measured basis**, like
#: `poll_interval_s` itself, and it says so in the config file.
STUCK_AFTER_PASSES_DEFAULT = 3
#: Where the streak is kept. Under `.seldon/`, which is gitignored: a count of passes is local
#: state and not a project record. The EVENT is the record.
STUCK_STATE_FILE = "dispatch_stuck.json"

#: The finish notification's failure (ai-readiness-kg/cc_tasks/2026-09-17_dispatcher_notifies.md
#: decision 1). A notifier that ran is not an event: the finish it reports is already on the log.
#: A notifier that did not run, failed or hung is one, because it is the only trace that the
#: operator was never told.
EVENT_NOTIFY_FAILED = "dispatch_notify_failed"

#: How long the finish notifier may run before it is killed. Decision 1 of the task above: a
#: desktop or push notifier returns in well under a second, and a notifier that is still running
#: after thirty has hung — it must not hold the lease, and with it every later pass, hostage.
#: Overridable per project as `dispatch.notify_timeout_s`.
NOTIFY_TIMEOUT_S_DEFAULT = 30

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
    # DN-006 decision 8. Optional — a project with no schedule has no `cadence:` key — but an
    # entry that IS there is validated here, so an unreadable rule refuses at config load and
    # not at 00:00 on the first Monday, unattended, at the only moment it mattered.
    block["cadence"] = C.validate_cadence(block.get("cadence"))
    # The finish notifier. Optional; a value that IS there must be a non-empty command string,
    # checked here so an unusable notifier refuses at load and not after an hour-long task has
    # finished with nobody to tell.
    notify = block.get("notify")
    if notify is not None and (not isinstance(notify, str) or not notify.strip()):
        raise DispatchConfigError(
            f"dispatch.notify must be a non-empty shell command string, got {notify!r}")
    block["notify"] = notify
    timeout = block.get("notify_timeout_s", NOTIFY_TIMEOUT_S_DEFAULT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise DispatchConfigError(
            f"dispatch.notify_timeout_s must be a positive number of seconds, got {timeout!r}")
    block["notify_timeout_s"] = timeout
    # Decision 6b. Optional with a default, so installing this build changes no config file;
    # a value that IS there is validated at load for `notify_timeout_s`'s reason.
    stuck = block.get("stuck_after_passes", STUCK_AFTER_PASSES_DEFAULT)
    if isinstance(stuck, bool) or not isinstance(stuck, int) or stuck < 1:
        raise DispatchConfigError(
            f"dispatch.stuck_after_passes must be a positive whole number of passes, got "
            f"{stuck!r}")
    block["stuck_after_passes"] = stuck
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


def parse_network(value: str | None) -> dict:
    """The Network header against `NETWORK_GRAMMAR`: `{kind, hosts, error}`.

    `kind` is `none`, `allowlist` or `cadence` when the value parses and `None` when it does
    not, in which case `error` says which part failed and quotes the grammar. `hosts` is the
    parsed allowlist, lower-cased and de-duplicated in order, and empty for the other kinds.
    """
    if value is None:
        return {"kind": None, "hosts": [], "error": f"no Network header; expected {NETWORK_GRAMMAR}"}
    m = _NETWORK_ALLOWLIST_RE.match(value)
    if m:
        raw = m.group("hosts").strip()
        # A sentence-ending period after the last host is prose, not a trailing-dot FQDN.
        raw = raw[:-1] if raw.endswith(".") else raw
        items = [h.strip().strip("`").strip() for h in raw.split(",")]
        if not raw or not any(items):
            return {"kind": None, "hosts": [],
                    "error": f"allowlist names no host; expected {NETWORK_GRAMMAR}"}
        bad = [h for h in items if not _HOSTNAME_RE.match(h.lower())]
        if bad:
            return {"kind": None, "hosts": [],
                    "error": (f"allowlist entries are not exact hostnames: "
                              f"{', '.join(repr(b) for b in bad)}; expected {NETWORK_GRAMMAR}")}
        hosts = list(dict.fromkeys(h.lower() for h in items))
        return {"kind": "allowlist", "hosts": hosts, "error": None}
    if _NETWORK_NONE_RE.search(value):
        return {"kind": "none", "hosts": [], "error": None}
    if _NETWORK_CADENCE_RE.search(value):
        return {"kind": "cadence", "hosts": [], "error": None}
    return {"kind": None, "hosts": [],
            "error": f"Network header {value!r} does not parse; expected {NETWORK_GRAMMAR}"}


def network_declared_none(value: str | None) -> bool:
    """True for the two forms that name no host of their own: `none` and the cadence
    provenance. An allowlist is declared, and passes c5, but is not `none`."""
    return parse_network(value)["kind"] in ("none", "cadence")


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
    # NOT `.strip()` on the porcelain output. Every line is `XY PATH` with X and Y each
    # possibly a space, so an unstaged modification is `" M path"` — and stripping the whole
    # blob removes the leading space of the FIRST line only, after which `ln[3:]` eats the
    # first character of that one path and no other. Found by running the dry pass and reading
    # `LAUDE.md` in the criteria vector; a defect that corrupts exactly one entry of a
    # diagnostic list is one no amount of staring at the code finds.
    porcelain = git(project_dir, "status", "--porcelain").stdout
    paths = [ln[3:] for ln in porcelain.split("\n") if ln.strip()]
    return {"branch": branch, "dirty": bool(paths), "dirty_paths": paths[:20],
            "dirty_count": len(paths)}


def stage(project_dir: Path, paths: list) -> subprocess.CompletedProcess:
    """`git add` exactly these paths. Never `-A`.

    A dispatcher that staged the whole tree would commit whatever else happened to be lying in
    the checkout, under a message saying it created a task file.
    """
    return git(project_dir, "add", "--", *[str(p) for p in paths])


def commit_paths(project_dir: Path, paths: list, message: str) -> dict:
    """Commit exactly these paths, and report what happened as values.

    **Why the dispatcher commits at all.** DN-006 decision 8 says the rendered task "flows
    through decisions 2 to 5 like any other task" — and decision 2's c1 requires the task file
    to be git-tracked while c7 requires the working tree to be clean. A rendered file that is
    never committed fails both, forever, for every task in the queue: the cadence would create
    January's cycle and then wedge the dispatcher until a person came and committed it, which
    is the exact latency this whole mechanism exists to remove. The commit is entailed by
    decision 8, not added to it; DN-006 ADDENDUM_02 records that the note does not say so.

    Pathspec-limited (`git commit -- <paths>`), so a tree that is dirty for some other reason
    keeps its other changes and this commit contains only what the cadence wrote. This function
    does not push; the pass pushes separately (`push_if_ahead`), after every commit it makes
    and on every pass that finds the branch still ahead
    (`ai-readiness-kg/cc_tasks/2026-09-16_dispatcher_commits_its_record.md` decision 2).
    """
    # A path the project ignores is dropped rather than staged: `git add` on an ignored path
    # is an error, and it would abort a commit for a file the project has deliberately said it
    # does not track (a test project ignores its event store; the real one tracks it). What is
    # skipped is reported, so the difference is visible rather than assumed.
    wanted = [str(p) for p in paths]
    keep = [p for p in wanted
            if (Path(project_dir) / p).exists()
            and git(project_dir, "check-ignore", "-q", "--", p).returncode != 0]
    skipped = [p for p in wanted if p not in keep]
    if not keep:
        return {"committed": False, "reason": "nothing_to_commit", "skipped": skipped}
    added = stage(project_dir, keep)
    if added.returncode != 0:
        return {"committed": False, "reason": "git_add_failed", "stderr": added.stderr.strip(),
                "skipped": skipped}
    done = git(project_dir, "commit", "-m", message, "--", *keep)
    if done.returncode != 0:
        return {"committed": False, "reason": "git_commit_failed",
                "stderr": (done.stderr or done.stdout).strip(), "skipped": skipped}
    head = git(project_dir, "rev-parse", "--short", "HEAD").stdout.strip()
    return {"committed": True, "reason": None, "commit": head, "message": message,
            "committed_paths": keep, "skipped": skipped}


def appended_events(project_dir: Path, store_rel: str) -> dict:
    """The events appended to the tracked store since HEAD, whoever wrote them.

    The append-only half of :func:`own_appended_lines`, shared with the registration-record
    sweep (`ai-readiness-kg/cc_tasks/2026-09-18_registration_commits.md`). Checked against
    HEAD's blob: the working copy must begin with HEAD's bytes, and every appended line must
    parse. Returns `{ok, reason, events}` with `reason` one of `None`, `clean`, `untracked`,
    `not_append_only`, `unparseable`; never raises on a state.
    """
    path = Path(project_dir) / store_rel
    if not path.is_file() or not is_tracked(Path(project_dir), path):
        return {"ok": False, "reason": "untracked", "events": []}
    head = subprocess.run(["git", "show", f"HEAD:{store_rel}"], cwd=project_dir,
                          capture_output=True)
    if head.returncode != 0:
        return {"ok": False, "reason": "untracked", "events": []}
    work = path.read_bytes()
    if work == head.stdout:
        return {"ok": False, "reason": "clean", "events": []}
    if not work.startswith(head.stdout):
        return {"ok": False, "reason": "not_append_only", "events": []}
    events = []
    for raw in work[len(head.stdout):].decode("utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            return {"ok": False, "reason": "unparseable", "events": events}
    return {"ok": True, "reason": None, "events": events}


#: Who may have written an uncommitted line the dispatcher is willing to commit
#: (ADDENDUM_01 decision 6a). `dispatcher` is its own record. `desktop` is the MCP tools':
#: `seldon_task_create` and `seldon_task_chain` append to a TRACKED store, and a Desktop
#: session that used one and then went away left the tree dirty — which is c7 false for the
#: WHOLE queue, not just for the task it touched. A `cc` line is deliberately NOT here: a
#: dispatched session's uncommitted event is the DD-019 class and the refusal is the guard.
COMMITTABLE_ACTORS = ("dispatcher", "desktop")


def own_appended_lines(project_dir: Path, store_rel: str, actor) -> dict:
    """Is the store's uncommitted change made ONLY of lines these actors appended?

    `actor` is one actor string or an iterable of them.

    The precondition for the dispatcher committing its own record
    (`ai-readiness-kg/cc_tasks/2026-09-16_dispatcher_commits_its_record.md` decision 1). The
    pathspec on the commit limits WHICH FILE is committed; this limits WHOSE LINES. Two checks,
    both against HEAD's blob rather than a textual diff, because the store is append-only and
    that contract is exactly what they test:

    * the working copy **begins with HEAD's bytes** — anything else is an in-place edit, and
      the dispatcher does not put its name on one;
    * every appended line **parses and carries `actor == <actor>`** — a line a session or an
      operator wrote and did not commit is their finding to surface (c7 surfaces it), not a
      line to launder under a dispatcher message.

    Returns values, never raises on a state: `{ok, reason, events}` with `reason` one of
    `None`, `clean`, `untracked`, `not_append_only`, `unparseable`, `not_own_lines`.
    """
    allowed = {actor} if isinstance(actor, str) else set(actor)
    appended = appended_events(project_dir, store_rel)
    if not appended["ok"]:
        return appended
    events, foreign = [], []
    for ev in appended["events"]:
        (events if ev.get("actor") in allowed else foreign).append(ev)
    if foreign:
        return {"ok": False, "reason": "not_own_lines", "events": events,
                "foreign_actors": sorted({str(e.get("actor")) for e in foreign})}
    return {"ok": True, "reason": None, "events": events}


def push_if_ahead(project_dir: Path) -> dict:
    """Push the current branch when it is ahead of its upstream; otherwise do nothing.

    Decision 2 of the same task: the dispatcher pushes what it commits, and a failed push is
    retried by the next pass whenever the branch is still ahead. "Ahead" is read from git
    (`rev-list --count @{u}..HEAD`), never remembered, so the retry needs no state of its own.
    Returns `{pushed, reason, ahead, stderr?}`; `reason` is `None`, `up_to_date`,
    `no_upstream` or `push_failed`. Never raises: an offline machine is an ordinary state.
    """
    count = git(project_dir, "rev-list", "--count", "@{u}..HEAD")
    if count.returncode != 0:
        return {"pushed": False, "reason": "no_upstream", "ahead": None,
                "stderr": count.stderr.strip()}
    ahead = int(count.stdout.strip() or 0)
    if ahead == 0:
        return {"pushed": False, "reason": "up_to_date", "ahead": 0}
    # `GIT_TERMINAL_PROMPT=0`: a launchd pass has no terminal, and a credential prompt would
    # hang the pass until the next one collided with its lease.
    done = subprocess.run(["git", "push", "--quiet"], cwd=project_dir, capture_output=True,
                          text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if done.returncode != 0:
        return {"pushed": False, "reason": "push_failed", "ahead": ahead,
                "stderr": (done.stderr or done.stdout).strip()}
    return {"pushed": True, "reason": None, "ahead": ahead}


def lease_is_held(project_dir: Path, cfg: dict) -> bool:
    """Is a dispatcher pass — and therefore possibly a dispatched session — working here?

    Read from the lease's RECORD plus PID liveness, never from age: the DD-022 orphan rule,
    which `reap_lease` already follows. A stale body naming a dead PID is not a held lease.
    """
    body = read_lease(Path(project_dir) / cfg["lease_file"])
    if not body or body.get("holder") is None:
        return False
    pid = body.get("pid")
    return not isinstance(pid, int) or pid_alive(pid)


def commit_journal_append(project_dir: Path, config: dict, by: str, actor: str = "desktop",
                          actors=COMMITTABLE_ACTORS) -> dict:
    """Commit the lines `by` just appended to the tracked event store, path-scoped.

    ADDENDUM_01 decision 6a to
    `ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence_after.md`.

    **What it closes.** `seldon cc register` has committed its own footprint since
    `2026-09-18_registration_commits`, for a reason that is not special to registration: the
    event store is a TRACKED file in this project, and a write to it that nobody commits keeps
    c7 false for the WHOLE queue — not for the task that was touched, for every task behind it.
    Every other MCP write tool appends to the same file and committed nothing. `_record_own_lines`
    then refuses the file, by name, as "not dispatcher-only (also written by desktop)".

    **Deferred, never forced.** Nothing is committed while a lease is held: a `git commit`
    beside a working dispatched session is DD-019's class and an `index.lock` collision
    besides. The next pass that holds the lease commits what it finds, which is why
    `COMMITTABLE_ACTORS` now includes `desktop`. Nothing is committed either when the project
    has no `dispatch:` block (the dispatcher is opt-in per project and this is its hygiene),
    when the store is untracked, or when a `cc` line is in the append — that last one is the
    DD-019 guard and it stays.

    Returns:
        `{committed, reason, ...}` — `reason` one of `None`, `no_dispatch_block`,
        `lease_held`, `wrong_branch`, or whatever `own_appended_lines` / `commit_paths`
        reported. **Never raises**: a tool that did its work must not fail on its bookkeeping.
    """
    try:
        cfg = load_dispatch_config(Path(project_dir), config)
    except (DispatchConfigError, OSError):
        return {"committed": False, "reason": "no_dispatch_block"}
    store = (config or {}).get("event_store", {}).get("path", "seldon_events.jsonl")
    if lease_is_held(project_dir, cfg):
        return {"committed": False, "reason": "lease_held"}
    if tree_state(project_dir)["branch"] != cfg["branch"]:
        return {"committed": False, "reason": "wrong_branch"}
    own = own_appended_lines(Path(project_dir), store, actors)
    if not own["ok"]:
        return {"committed": False, "reason": own["reason"],
                "foreign_actors": own.get("foreign_actors", [])}
    types = list(dict.fromkeys(e.get("event_type") for e in own["events"]))
    ids = list(dict.fromkeys(
        str(pl.get("task_id") or pl.get("artifact_id") or pl.get("id"))[:8]
        for pl in ((e.get("payload") or {}) for e in own["events"])
        if pl.get("task_id") or pl.get("artifact_id") or pl.get("id")))
    message = (f"{actor}: {', '.join(types)} {', '.join(ids) or '-'} — "
               f"{len(own['events'])} line(s) written by {by}")
    return commit_paths(Path(project_dir), [store], message)


# ------------------------------------------------------------------- the stuck-queue alarm

def read_stuck_state(project_dir: Path, cfg: dict) -> dict:
    path = Path(project_dir) / Path(cfg["lease_file"]).parent / STUCK_STATE_FILE
    if not path.is_file():
        return {}
    try:
        body = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        # A corrupt streak file re-arms the alarm rather than silencing it: the failure
        # direction of a staleness alarm must be "tell them again", never "stay quiet".
        return {}
    return body if isinstance(body, dict) else {}


def write_stuck_state(project_dir: Path, cfg: dict, state: dict) -> None:
    path = Path(project_dir) / Path(cfg["lease_file"]).parent / STUCK_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def advance_stuck(previous: dict, refusals: dict, threshold: int, now: str) -> tuple:
    """One pass's refusals against the previous streaks: `(state, alarms)`.

    Pure, so the whole re-arm rule is testable without a clock, a graph or a notifier.

    Args:
        previous: The state file's contents.
        refusals: `{task_id: {"criterion": str, "detail": ...}}` for this pass.
        threshold: `dispatch.stuck_after_passes`.
        now: Timestamp stamped on a new streak and on the alarm.

    Returns:
        The state to persist, and the task ids to raise the alarm for in this pass.

    A streak re-arms when the criterion CHANGES or CLEARS — a task that stops being refused
    drops out of the state entirely, so the same criterion recurring later alarms again. The
    alarm fires exactly once per streak: that is the difference between a staleness alarm and
    the per-pass refusal logging DN-006 decision 7 forbids.
    """
    state, alarms = {}, []
    for task_id, row in refusals.items():
        prior = previous.get(task_id) or {}
        same = prior.get("criterion") == row["criterion"]
        passes = (prior.get("passes", 0) + 1) if same else 1
        notified = bool(prior.get("notified")) if same else False
        entry = {"criterion": row["criterion"], "passes": passes, "notified": notified,
                 "first_seen": prior.get("first_seen", now) if same else now}
        if passes >= threshold and not notified:
            entry["notified"] = True
            entry["notified_at"] = now
            alarms.append(task_id)
        elif same and prior.get("notified_at"):
            entry["notified_at"] = prior["notified_at"]
        state[task_id] = entry
    return state, alarms


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
            # RECORD THE RELEASE, do not just drop the flock. The file is the lease's *record*
            # and the flock is its *guard*; leaving the body naming a holder whose process has
            # since exited makes every reader — `status`, `seldon go` — report a lease held by
            # a dead PID and tell the operator to run `lease reap`. That is a false alarm after
            # every ordinary pass, and an operator who is told to reap a healthy lease twelve
            # times an hour will reap a real one without looking.
            #
            # The file is kept rather than unlinked so the flock has a stable inode: two passes
            # racing on a path that is deleted between them can each open a different file and
            # each take "the" lock.
            body = read_lease(self.path)
            self.write({"holder": None, "pid": None, "task": None,
                        "last_holder": body.get("holder"),
                        "acquired_at": body.get("acquired_at"),
                        "released_at": datetime.now(timezone.utc).isoformat()
                        .replace("+00:00", "Z")})
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
    if body.get("holder") is None and not body.get("unparseable"):
        # Released cleanly by its holder on exit. There is nothing to reap, and saying so is
        # not the same as saying there is no lease file — an operator who asked to reap wants
        # to know which of the two they are looking at.
        return {"reaped": False, "reason": "not_held", "holder": None,
                "last_holder": body.get("last_holder"),
                "released_at": body.get("released_at")}
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
    net = parse_network(headers[HEADER_NETWORK])
    c["c5"] = {"network_header": headers[HEADER_NETWORK], "network_kind": net["kind"],
               "network_allowlist": net["hosts"], "ok": net["kind"] is not None}
    if net["error"]:
        c["c5"]["message"] = net["error"]
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
