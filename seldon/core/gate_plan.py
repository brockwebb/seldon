"""SEL-041 (AD-034 ADDENDUM 12, AD-034-R29 to R37): the gate runs what a change touched, and the whole suite only at
declared points.

A project's gate has two tiers (R29). The **full** tier is `dispatch.gate_command`, as before. The **scoped** tier is
planned here from what the branch changed against main: the slices a project declares in `dispatch.gate.slices`
(R30) name, for each set of paths, the tests and commands those paths require, or `tests: none`; the test files the
branch added or changed and the files that failed in the last recorded gate always run (R31); and anything selection
cannot vouch for makes the gate full, with the reason on the record (R32): a path no slice names, a change to the
gate's own configuration, a lock or project file, a `conftest.py`, a slice whose tests match nothing, a request
(`--full`, `**Gate:** full`) or the project's cadence.

Every run is one `gate_run` record (R33): tier, reason, call site, commit and tree, test files selected of the total,
tests run, wall seconds, outcome, the files that failed, and the escapes a full gate found against the last scoped
gate on the same change set. A passing record for a clean tree is merge evidence under AD-034-R26 (R34). `seldon
verify`, `seldon go` and `seldon qc chart` read the same records (R36).

SEL-055 (AD-034 ADDENDUM 13, R38 to R40). The cadence no longer promotes a task's gate: the full suite runs on main on
a schedule (`scheduled_due`, run by `seldon.commands.dispatch_gate`, call site `scheduled`). While the newest scheduled
run is red (`main_red`), the merge round's plans are closed (`plan(..., closure=...)`): a plan that selects anything
also runs the red run's failed files, or goes full when it named none; a plan whose every path is declared
`tests: none` is inert and is not closed. A lane branch is planned like any other (R40); its record says `lane`.

Prior art (the addendum's section 2): test impact analysis as Fowler's page reports it (new and previously failing
tests always run; resources listed by hand; periodic full runs against a reference build), the build systems' declared
dependencies (Bazel, Buck, Pants), and fail-safe defaults (Saltzer and Schroeder): a test is skipped only where a
declaration permits it.

This module imports no dispatcher module at load, so `seldon.core.dispatch` can validate the block through it.
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shlex
import signal
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from seldon.core import worktree as WT

CONFIG_KEY = "gate"
EVENT_GATE_RUN = "gate_run"
TIER_SCOPED, TIER_FULL = "scoped", "full"
OUTCOME_PASS, OUTCOME_FAIL, OUTCOME_TIMEOUT = "pass", "fail", "timeout"
#: The call sites a record names (R35). `cli` is `seldon gate run` by hand or from a session.
#: SEL-055 (AD-034-R38): `scheduled` is the full suite on main's head, run by the dispatcher's pass or `seldon gate main`.
CALL_SITES = ("cli", "stop_gate", "regate", "merge_gate", "scheduled")
CALL_SITE_SCHEDULED = "scheduled"
#: The coverage-map values a project may declare (R30). SEL-041 Part C measured testmon on seldon's suite and did not
#: ship the arm (the RESULT, Part C), so `none` is the only value; a later task that ships an arm adds its name here.
COVERAGE_MAPS = ("none",)
#: The task-file header that asks for the full tier (R29).
HEADER_GATE = "Gate"
#: The project file that holds the gate's configuration; a change to its `dispatch.gate_command` or `dispatch.gate`
#: makes the gate full (R32).
CONFIG_FILE = "seldon.yaml"

#: Every key of `dispatch.gate` and its default. Each default is the conservative one: no slices (the gate is full, as
#: before this addendum), no time warning until a project states its threshold.
DEFAULTS = {
    "slices": [],
    # How the scoped tier runs selected tests: `{tests}` is replaced by the selected paths, shell-quoted. Required when
    # a slice requires tests or a branch can change a test file (always, so required whenever slices are declared).
    "test_command": None,
    # Where a `marker:` selection is run: `{tests}` becomes `<test_root> -m '<expr>'`.
    "test_root": "tests",
    # What a test file is, for R31's "tests added or changed on the branch" and for the total a record counts.
    "test_globs": ["**/test_*.py", "**/*_test.py"],
    # Paths whose change makes the gate full (R32): the dependency locks and project files that change every test's
    # environment. A project adds its own here; `conftest.py` anywhere is always full and not listed.
    "full_paths": ["pyproject.toml", "uv.lock", "poetry.lock", "Pipfile", "Pipfile.lock", "requirements*.txt",
                   "setup.py", "setup.cfg", "pytest.ini", "tox.ini", "package.json", "package-lock.json"],
    # R29's cadence, R38's schedule. Fowler's page: the map (here, the slices) is checked against a periodic full run.
    # Nightly is SEL-041's own default ("nightly by default where a dispatcher runs"). Since SEL-055 (R38) it is how long
    # after the newest full gate the dispatcher's idle pass runs the full suite on main; it never promotes a task's gate.
    "full_every_s": 86400,
    # R38's starvation bound: past this age the scheduled run goes before a launch, not only on an idle pass. NO
    # MEASURED BASIS: two cadences, so a queue that is never empty still gets one full run on main every two days.
    "full_overdue_s": 172800,
    # R38: where the scheduled run checks out main's head (repository-relative, under the ignored `.seldon/`), made fresh
    # for each run and removed after it.
    "scheduled_worktree": ".seldon/gate_main",
    # R36: warn when the median of the last ten scoped gates exceeds this. None: no time warning.
    "warn_seconds": None,
    "coverage_map": "none",
}
#: R36's window: "the median scoped gate over its last ten runs".
WARN_WINDOW = 10
#: How many unmatched paths and reasons a record lists (the counts are recorded whole): hazbrief HB-186 changed
#: 2,978 files, and a record is one line of the event store.
RECORD_LIST_CAP = 50
#: How many bytes of a failing gate's output a record and a Stop-gate refusal carry.
TAIL_BYTES = 2000

_SLICE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_FAILED_RE = re.compile(r"^(?:FAILED|ERROR) ([^\s:]+?\.py)(?:::|\s|$)", re.M)
_COUNT_RE = re.compile(r"(\d+) (passed|failed|errors?|xfailed|xpassed)\b")
_SUMMARY_RE = re.compile(r"^=*\s*(?:\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)"
                         r"(?:, )?)+.* in [0-9.]+s", re.M)


class GateConfigError(ValueError):
    """`dispatch.gate` does not load: the message names the key and what it holds."""


# ================================================================================================ configuration

def _str_list(value, where: str, allow_empty: bool = True) -> list:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value) \
            or (not allow_empty and not value):
        raise GateConfigError(f"{where} must be a list of non-empty strings, got {value!r}")
    return list(value)


def _relative(globs: list, where: str) -> list:
    for g in globs:
        if g.startswith("/") or ".." in g.split("/"):
            raise GateConfigError(f"{where} entry {g!r} is not repository-relative")
    return globs


def load_gate_config(block, gate_command: str | None) -> dict:
    """`dispatch.gate`, validated, with every default filled in. Absent is the defaults: no slices.

    Refuses (GateConfigError) a slice without a name, paths or a `tests` value; a duplicate name; slices with no
    `test_command` (a branch's changed test files always run, R31, and need a command); slices with no
    `gate_command` (the full tier has nothing to run, and R32 sends every unvouched change there); an unknown key;
    and a coverage map SEL-041 did not ship."""
    if block is None:
        block = {}
    if not isinstance(block, dict):
        raise GateConfigError(f"dispatch.gate must be a mapping, got {block!r}")
    unknown = sorted(set(block) - set(DEFAULTS))
    if unknown:
        raise GateConfigError(f"dispatch.gate has unknown key(s) {unknown}; the keys are {sorted(DEFAULTS)}")
    out = {**DEFAULTS, **block}
    slices = out["slices"] if out["slices"] is not None else []
    if not isinstance(slices, list):
        raise GateConfigError(f"dispatch.gate.slices must be a list, got {slices!r}")
    seen, parsed = set(), []
    for i, s in enumerate(slices):
        where = f"dispatch.gate.slices[{i}]"
        if not isinstance(s, dict):
            raise GateConfigError(f"{where} must be a mapping with name, paths and tests, got {s!r}")
        extra = sorted(set(s) - {"name", "paths", "tests", "commands", "basis"})
        if extra:
            raise GateConfigError(f"{where} has unknown key(s) {extra}; a slice has name, paths, tests, commands, basis")
        name = s.get("name")
        if not isinstance(name, str) or not _SLICE_NAME_RE.match(name):
            raise GateConfigError(f"{where}.name must be a bare word ({_SLICE_NAME_RE.pattern}), got {name!r}")
        if name in seen:
            raise GateConfigError(f"dispatch.gate.slices: the name {name!r} is declared twice")
        seen.add(name)
        paths = _relative(_str_list(s.get("paths"), f"{where}.paths", allow_empty=False), f"{where}.paths")
        tests = s.get("tests")
        if tests == "none":
            tests = []
        elif isinstance(tests, list) and tests:
            tests = _str_list(tests, f"{where}.tests")
            _relative([t for t in tests if not t.startswith("marker:")], f"{where}.tests")
            for t in tests:
                if t.startswith("marker:") and not t[len("marker:"):].strip():
                    raise GateConfigError(f"{where}.tests entry {t!r} names no marker expression")
        else:
            raise GateConfigError(f"{where}.tests must be `none` or a non-empty list of test paths and "
                                  f"`marker:<expression>` entries, got {tests!r}: a slice states what its paths "
                                  f"require, and `none` is a statement too (R30)")
        commands = _str_list(s.get("commands") or [], f"{where}.commands")
        parsed.append({"name": name, "paths": paths, "tests": tests, "commands": commands})
    out["slices"] = parsed
    for key in ("test_globs", "full_paths"):
        out[key] = _relative(_str_list(out[key], f"dispatch.gate.{key}", allow_empty=False), f"dispatch.gate.{key}")
    if not isinstance(out["test_root"], str) or not out["test_root"].strip():
        raise GateConfigError(f"dispatch.gate.test_root must be a non-empty path, got {out['test_root']!r}")
    tc = out["test_command"]
    if tc is not None and (not isinstance(tc, str) or "{tests}" not in tc):
        raise GateConfigError(f"dispatch.gate.test_command must be a shell command containing `{{tests}}`, got {tc!r}")
    for key in ("full_every_s", "full_overdue_s"):
        v = out[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise GateConfigError(f"dispatch.gate.{key} must be a positive number of seconds, got {v!r}")
    sw = out["scheduled_worktree"]
    if not isinstance(sw, str) or not sw.strip():
        raise GateConfigError(f"dispatch.gate.scheduled_worktree must be a non-empty repository-relative path, got {sw!r}")
    _relative([sw], "dispatch.gate.scheduled_worktree")
    if posixpath.normpath(sw.strip()) == ".":
        # REVIEW-001 F-01: the scheduled run removes its checkout before and after each run, so a value naming the
        # checkout itself would name the primary for removal. `dispatch_gate._clear` also refuses any path the run's
        # own marker does not claim; this refuses the one value no project can mean.
        raise GateConfigError(f"dispatch.gate.scheduled_worktree {sw!r} names the checkout itself; it must name a "
                              f"scratch path inside it, such as the default {DEFAULTS['scheduled_worktree']!r}")
    w = out["warn_seconds"]
    if w is not None and (isinstance(w, bool) or not isinstance(w, (int, float)) or w <= 0):
        raise GateConfigError(f"dispatch.gate.warn_seconds must be a positive number of seconds or absent, got {w!r}")
    if out["coverage_map"] not in COVERAGE_MAPS:
        raise GateConfigError(f"dispatch.gate.coverage_map must be one of {list(COVERAGE_MAPS)}, got "
                              f"{out['coverage_map']!r}: SEL-041 measured testmon on seldon's suite and did not ship "
                              f"the arm (its RESULT, Part C)")
    if parsed:
        if not gate_command:
            raise GateConfigError("dispatch.gate.slices needs dispatch.gate_command: it is the full tier, which every "
                                  "change selection cannot vouch for runs (AD-034-R29, R32)")
        if tc is None:
            raise GateConfigError("dispatch.gate.slices needs dispatch.gate.test_command (with `{tests}`): a "
                                  "branch's added or changed test files always run (AD-034-R31)")
    return out


def declared(gcfg: dict | None) -> bool:
    """Whether the project declares slices, the condition for the scoped tier and the planner's call sites (R35)."""
    return bool((gcfg or {}).get("slices"))


# ================================================================================================ the planner

def _glob_re(pattern: str) -> re.Pattern:
    """A path glob as a regex over a repository-relative POSIX path: `*` and `?` stay inside one directory, `**`
    crosses directories (`a/**/b` matches `a/b`), and a pattern ending in `/` is the directory's whole subtree."""
    if pattern.endswith("/"):
        pattern += "**"
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            j = pattern.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
                i += 1
            else:
                out.append(pattern[i:j + 1])
                i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


_GLOB_CACHE: dict = {}


def glob_match(path: str, pattern: str) -> bool:
    rx = _GLOB_CACHE.get(pattern)
    if rx is None:
        rx = _GLOB_CACHE[pattern] = _glob_re(pattern)
    return bool(rx.match(path))


def _any(path: str, globs) -> bool:
    return any(glob_match(path, g) for g in globs)


def _files(tree: Path) -> list:
    """The tree's files as git sees them: tracked, plus untracked and not ignored (a session's new test file counts
    before it is committed)."""
    r = WT.git(tree, "ls-files", "-co", "--exclude-standard")
    if r.returncode != 0:
        raise GateConfigError(f"git ls-files failed in {tree}: {r.stderr.strip()}")
    return sorted(set(p for p in r.stdout.splitlines() if p))


def _gate_conf(text: str | None) -> tuple:
    """`(gate_command, gate)` as one `seldon.yaml` text declares them; `(None, None)` for no text or no block."""
    if not text:
        return None, None
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return ("<unparseable>", "<unparseable>")
    d = (doc.get("dispatch") or {}) if isinstance(doc, dict) else {}
    return d.get("gate_command"), d.get(CONFIG_KEY)


def _change_set(branch: str | None, paths: list) -> str:
    return hashlib.sha256(("\n".join([branch or ""] + sorted(paths))).encode("utf-8")).hexdigest()[:16]


def _ts(e: dict) -> datetime | None:
    raw = str(e.get("timestamp") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def runs(events: list) -> list:
    """Every `gate_run` event, oldest first."""
    return [e for e in events if e.get("event_type") == EVENT_GATE_RUN]


def last_full_pass(events: list) -> dict | None:
    """The newest passing full gate's event, or None."""
    for e in reversed(runs(events)):
        p = e.get("payload") or {}
        if p.get("tier") == TIER_FULL and p.get("outcome") == OUTCOME_PASS:
            return e
    return None


def last_failed_files(events: list) -> list:
    """R31: the files that failed in the project's last recorded gate of a change (empty when it passed). SEL-055
    (AD-034-R39): a scheduled run on main is not a change's gate; its failures are the closure's, which the merge round
    applies and the Stop gate does not."""
    rr = [e for e in runs(events) if (e.get("payload") or {}).get("call_site") != CALL_SITE_SCHEDULED]
    if not rr:
        return []
    p = rr[-1].get("payload") or {}
    return list(p.get("failed_files") or []) if p.get("outcome") != OUTCOME_PASS else []


# ================================================================================ SEL-055: the schedule and the closure

#: The dispatcher's merged finish (`dispatch.EVENT_FINISHED`), named here so this module imports no dispatcher module.
_EVENT_FINISHED = "dispatch_finished"


def _scheduled(e: dict) -> bool:
    return e.get("event_type") == EVENT_GATE_RUN and (e.get("payload") or {}).get("call_site") == CALL_SITE_SCHEDULED


def last_scheduled(events: list) -> dict | None:
    """The newest scheduled run's event (R38), whatever its outcome, or None."""
    for e in reversed(events):
        if _scheduled(e):
            return e
    return None


def _merged_on_full_pass(e: dict) -> bool:
    """A merged finish whose gate evidence is a passing full gate of the tip that became main (R39's second exit): the
    round's own full re-gate or evidence gate, a full `gate_run` record, or a declared pass record (a kit's full run)."""
    p = e.get("payload") or {}
    if e.get("event_type") != _EVENT_FINISHED or p.get("outcome") != "merged":
        return False
    ev = (p.get("merge") or {}).get("gate_evidence") or {}
    src = ev.get("source")
    if src in ("merge_gate", "regate"):
        g = ev.get("gate") or {}
        return g.get("tier") == TIER_FULL and bool(g.get("ok"))
    if src == "gate_run":
        return ev.get("tier") == TIER_FULL
    return src == "gate_record"


def main_red(events: list) -> dict | None:
    """R39: the red scheduled run whose closure holds, or None. It holds from a scheduled run that did not pass until a
    later scheduled run passes or a branch merges on a passing full gate of its tip."""
    red = None
    for e in events:
        if _scheduled(e):
            red = None if (e.get("payload") or {}).get("outcome") == OUTCOME_PASS else e
        elif red is not None and _merged_on_full_pass(e):
            red = None
    return red


def merged_after(events: list, event: dict) -> bool:
    """Whether any task merged after `event` (R39: after a merge under closure the schedule is due at once)."""
    seen = False
    for e in events:
        if e is event or (event.get("event_id") and e.get("event_id") == event.get("event_id")):
            seen = True
            continue
        if seen and e.get("event_type") == _EVENT_FINISHED and (e.get("payload") or {}).get("outcome") == "merged":
            return True
    return False


def scheduled_due(events: list, gcfg: dict | None, *, idle: bool, now: datetime | None = None) -> str | None:
    """R38: why the scheduled run on main is due on this pass, or None.

    Only where slices are declared (without them every gate is already full, R37). The anchor is the newest full gate
    on record: the newest scheduled run, whatever its outcome, or the newest passing full gate at any call site (a
    task's full gate tested main with the task's change on top). Due on an idle pass (nothing eligible to launch) once
    `full_every_s` has passed since the anchor, or when no full gate is recorded at all; due on any pass once
    `full_overdue_s` has passed, or when main is red and a task merged after the red run (R39)."""
    if not declared(gcfg):
        return None
    now = now or datetime.now(timezone.utc)
    red = main_red(events)
    if red is not None and merged_after(events, red):
        return (f"main_red_merged: a task merged after the red scheduled run {str(red.get('event_id'))[:8]} "
                f"({red.get('timestamp')})")
    stamps = [x for x in (_ts(last_scheduled(events) or {}), _ts(last_full_pass(events) or {})) if x is not None]
    if not stamps:
        return "never: no full gate is recorded" if idle else None
    anchor = max(stamps)
    age = (now - anchor).total_seconds()
    if age > gcfg["full_overdue_s"]:
        return (f"overdue: the newest full gate was at {anchor.isoformat()}, {age:.0f} s ago, past "
                f"full_overdue_s {gcfg['full_overdue_s']:g}")
    if idle and age > gcfg["full_every_s"]:
        return (f"due: the newest full gate was at {anchor.isoformat()}, {age:.0f} s ago, past "
                f"full_every_s {gcfg['full_every_s']:g}")
    return None


def scheduled_plan(tree: Path, gcfg: dict, why: str, branch: str | None) -> dict:
    """The full plan of a scheduled run (R38): main's head in `tree`, every test file, the reason `scheduled: <why>`."""
    tree = Path(tree)
    head = WT.rev(tree, "HEAD")
    tree_hash = WT.git(tree, "rev-parse", "HEAD^{tree}").stdout.strip() or None
    total = len([f for f in _files(tree) if _any(f, gcfg["test_globs"])])
    reason = f"scheduled: {why}"
    return {"base": branch, "fork": head, "commit": head, "tree": tree_hash, "dirty": False, "changed": [],
            "change_set": _change_set(branch, []), "slices": {}, "unmatched": [], "tests": [], "markers": [],
            "commands": [], "always": {"changed_tests": [], "last_failed": []}, "files_total": total,
            "files_selected": total, "reasons": [reason], "tier": TIER_FULL, "reason": reason}


def closure_admits(evidence: dict | None, red: dict | None) -> bool:
    """R39: whether merge evidence found by `gate_evidence` stands while `red` (a `main_red` event) holds. A declared
    pass record and the round's own re-gate stand (the round's gates apply the closure); a `gate_run` record stands when
    it was full, declared inert, or planned under this same closure; a kept regate's and a Stop gate's checks do not."""
    if red is None or evidence is None:
        return True
    src = evidence.get("source")
    if src in ("gate_record", "regate", "merge_gate"):
        return True
    if src == "gate_run":
        if evidence.get("tier") == TIER_FULL or str(evidence.get("reason") or "").startswith("declared_none"):
            return True
        return evidence.get("main_red") == red.get("event_id")
    return False


def task_requests_full(task_text: str | None) -> bool:
    """`**Gate:** full` in the task file's header block (R29)."""
    if not task_text:
        return False
    from seldon.core import dispatch as D
    v = D._header_value(task_text, HEADER_GATE)
    return bool(v) and v.strip().strip("`").split()[0].lower() == "full"


def plan(tree: Path, gcfg: dict, *, base: str, gate_command: str | None, events: list, full: bool = False,
         task_text: str | None = None, branch: str | None = None, exclude=(), now: datetime | None = None,
         closure: dict | None = None) -> dict:
    """What the gate runs for `tree` (a checkout of the branch) against `base` (main), and why.

    `closure` (SEL-055, AD-034-R39) is `main_red(events)` where the caller applies it (the merge round and `seldon gate
    run`; never the Stop gate): the red scheduled run whose failed files the plan must also run. `now` is kept for
    callers that pass it; since R38 the plan reads no clock.

    The changed paths are the branch's commits since its fork from `base` plus the tree's uncommitted paths (`dirty`
    is recorded, and a dirty run is never merge evidence, R34). Returns the plan the runner and the record read:
    `tier`, `reason` (the first cause) and `reasons` (all), the slices matched with their paths, the paths no slice
    matched, the selected test files, marker expressions and commands, R31's always-run files, and the counts."""
    tree = Path(tree)
    now = now or datetime.now(timezone.utc)
    fork = WT.git(tree, "merge-base", "HEAD", base).stdout.strip()
    if not fork:
        raise GateConfigError(f"no merge base between HEAD and {base!r} in {tree}")
    head = WT.rev(tree, "HEAD")
    tree_hash = WT.git(tree, "rev-parse", "HEAD^{tree}").stdout.strip()
    committed = WT.changed_files(tree, fork, "HEAD")
    dirt = [p.rstrip("/") for p in WT.dirty_paths(tree, exclude=exclude)]
    changed = sorted(set(committed) | set(dirt))
    out = {"base": base, "fork": fork, "commit": head, "tree": tree_hash, "dirty": bool(dirt), "changed": changed,
           # The change set is what the branch committed (R33): a gate run's own records, written to a primary
           # checkout's store, must not make two gates of the same commits two change sets.
           "change_set": _change_set(branch, committed), "slices": {}, "unmatched": [], "tests": [], "markers": [],
           "commands": [], "always": {"changed_tests": [], "last_failed": []}, "files_total": 0,
           "files_selected": 0, "reasons": []}
    files = _files(tree)
    test_files = [f for f in files if _any(f, gcfg["test_globs"])]
    out["files_total"] = len(test_files)
    reasons = out["reasons"]
    if not declared(gcfg):
        # No slices: the gate is full, as every gate was before the addendum (R37). Nothing is matched, so a record
        # does not list every changed path as unmatched.
        out.update({"tier": TIER_FULL, "reason": "no_slices", "files_selected": out["files_total"]})
        reasons.append("no_slices")
        return out
    if full:
        reasons.append("requested: --full")
    if task_requests_full(task_text):
        reasons.append(f"requested: **{HEADER_GATE}:** full")
    if CONFIG_FILE in changed:
        before = WT.show(tree, fork, CONFIG_FILE)
        after_path = tree / CONFIG_FILE
        after = after_path.read_text(encoding="utf-8") if after_path.is_file() else None
        if _gate_conf(before.decode("utf-8", "replace") if before else None) != _gate_conf(after):
            reasons.append(f"gate_config_changed: {CONFIG_FILE}")
    selected, markers, commands = set(), [], []
    for p in changed:
        if Path(p).name == "conftest.py":
            reasons.append(f"conftest: {p}")
            continue
        if _any(p, gcfg["full_paths"]):
            reasons.append(f"full_path: {p}")
            continue
        hit = False
        for s in gcfg["slices"]:
            if _any(p, s["paths"]):
                hit = True
                out["slices"].setdefault(s["name"], []).append(p)
        if _any(p, gcfg["test_globs"]):
            # A test file the branch added or changed always runs (R31); one it deleted needs nothing run.
            hit = True
            if (tree / p).is_file():
                selected.add(p)
                out["always"]["changed_tests"].append(p)
        if not hit:
            out["unmatched"].append(p)
    for p in out["unmatched"]:
        reasons.append(f"unmatched: {p}")
    for s in gcfg["slices"]:
        if s["name"] not in out["slices"]:
            continue
        for t in s["tests"]:
            if t.startswith("marker:"):
                expr = t[len("marker:"):].strip()
                if expr not in markers:
                    markers.append(expr)
                continue
            got = [f for f in test_files if glob_match(f, t)]
            if not got:
                reasons.append(f"slice_tests_missing: {s['name']}: {t}")
            selected |= set(got)
        for c in s["commands"]:
            if c not in commands:
                commands.append(c)
    # R39: whether the branch's own paths select anything, before R31's last-failed files are added: a branch whose
    # every path is declared `tests: none` is inert, whatever another branch's gate left failing.
    own = bool(selected or markers or commands)
    for f in last_failed_files(events):
        if (tree / f).is_file():
            selected.add(f)
            out["always"]["last_failed"].append(f)
    # SEL-055 (AD-034-R38): no cadence here. The full suite's schedule runs on main (`scheduled_due`), so a task's gate
    # is never promoted to full by the day it happens to merge on (SEL-051 paid two full gates for one RESULT file).
    if closure is not None and not reasons:
        # R39: main's newest scheduled run is red. A plan that selects anything also runs the files that run failed,
        # so only a change that leaves them passing merges; a red run that named none closes such a plan in full. A
        # plan that selects nothing (every path declared `tests: none`) is inert by the project's declarations and is
        # not closed.
        rp = closure.get("payload") or {}
        red = {"event_id": closure.get("event_id"), "timestamp": closure.get("timestamp"),
               "commit": rp.get("commit"), "outcome": rp.get("outcome")}
        if not own:
            red["applied"] = "inert"
        elif not rp.get("failed_files"):
            red["applied"] = "full"
            reasons.append(f"main_red: the scheduled run {str(closure.get('event_id'))[:8]} on main is "
                           f"{rp.get('outcome')} and named no failed file")
        else:
            red["applied"] = "failed_files"
            out["always"]["main_red"] = []
            for f in rp["failed_files"]:
                if (tree / f).is_file():
                    selected.add(f)
                    out["always"]["main_red"].append(f)
        out["main_red"] = red
    out["tests"], out["markers"], out["commands"] = sorted(selected), markers, commands
    out["files_selected"] = len(out["tests"])
    if reasons:
        out["tier"], out["reason"] = TIER_FULL, reasons[0]
        out["files_selected"] = out["files_total"]
    else:
        out["tier"] = TIER_SCOPED
        out["reason"] = ("declared_none: every changed path matched a slice declared `tests: none`"
                         if not (out["tests"] or out["markers"] or out["commands"]) else
                         "scoped: " + ", ".join(sorted(out["slices"])) if out["slices"] else "scoped: changed tests")
    return out


def unplanned(tree: Path, base: str, why: str, branch: str | None = None) -> dict:
    """A full plan for a tree the planner could not read (no merge base, git refused): the fail-safe answer to a
    selection that cannot be made is the whole suite (R32), with the cause as the reason."""
    tree = Path(tree)
    tree_hash = WT.git(tree, "rev-parse", "HEAD^{tree}").stdout.strip() or None
    return {"base": base, "fork": None, "commit": WT.rev(tree, "HEAD"), "tree": tree_hash, "dirty": True,
            "changed": [], "change_set": _change_set(branch, []), "slices": {}, "unmatched": [], "tests": [],
            "markers": [], "commands": [], "always": {"changed_tests": [], "last_failed": []}, "files_total": 0,
            "files_selected": 0, "reasons": [f"plan_failed: {why}"], "tier": TIER_FULL,
            "reason": f"plan_failed: {why}"}


# ================================================================================================ the runner

def _steps(p: dict, gcfg: dict, gate_command: str | None) -> list:
    """The shell commands a plan runs, in order: `[(kind, command)]`."""
    if p["tier"] == TIER_FULL:
        if not gate_command:
            raise GateConfigError("the plan is full and the project declares no dispatch.gate_command to run")
        return [("full", gate_command)]
    steps = []
    tc = gcfg["test_command"]
    if p["tests"]:
        steps.append(("tests", tc.replace("{tests}", " ".join(shlex.quote(t) for t in p["tests"]))))
    if p["markers"]:
        expr = " or ".join(f"({m})" for m in p["markers"])
        steps.append(("markers", tc.replace("{tests}", f"{shlex.quote(gcfg['test_root'])} -m {shlex.quote(expr)}")))
    steps += [("command", c) for c in p["commands"]]
    return steps


def _read_from(path: Path, offset: int) -> str:
    with path.open("rb") as fh:
        fh.seek(offset)
        return fh.read().decode("utf-8", "replace")


def parse_output(text: str) -> dict:
    """The test files pytest named as failed or errored (`FAILED`/`ERROR` lines of its short summary, on by default
    since pytest 6), and the tests run, summed over the summary lines (`N passed, M failed ... in S s`)."""
    failed = sorted(set(_FAILED_RE.findall(text)))
    ran = 0
    for line in _SUMMARY_RE.findall(text):
        ran += sum(int(n) for n, _ in _COUNT_RE.findall(line))
    return {"failed_files": failed, "tests_run": ran if _SUMMARY_RE.search(text) else None}


def run(tree: Path, p: dict, gcfg: dict, *, gate_command: str | None, timeout_s: float, log_path: Path,
        primary: Path) -> dict:
    """Run a plan's steps in `tree`, appending their output to `log_path`. Every step runs, in order, until one fails
    or the shared deadline passes: `{ok, outcome, exit_code, timed_out, seconds, steps, tests_run, failed_files,
    tail, log_path}`. A scoped plan with nothing to run passes at once (R34's `declared_none`). pytest's exit 5 (no
    test collected) passes a marker step: the marker selected nothing, which is what the slice said."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, WT.PRIMARY_CHECKOUT_ENV: str(primary)}
    steps = _steps(p, gcfg, gate_command)
    start = time.monotonic()
    deadline = start + timeout_s
    offset = log_path.stat().st_size if log_path.is_file() else 0
    done, code, timed_out = [], 0, False
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with log_path.open("a", encoding="utf-8") as fh:
        if p["tier"] == TIER_FULL:
            # The full tier's log is the gate log as it was before the addendum: one header line naming the command.
            fh.write(f"=== {stamp} | gate | {gate_command}\n")
        else:
            fh.write(f"=== {stamp} | gate scoped | {p['reason']}\n")
        for kind, cmd in steps:
            if kind != "full":
                fh.write(f"--- {kind}: {cmd}\n")
            fh.flush()
            t0 = time.monotonic()
            proc = subprocess.Popen(["/bin/sh", "-c", cmd], cwd=tree, env=env, stdin=subprocess.DEVNULL, stdout=fh,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = proc.wait(timeout=max(1.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                code, timed_out = proc.wait(), True
            if kind == "markers" and code == 5:
                code = 0
            done.append({"kind": kind, "command": cmd, "exit": code, "seconds": round(time.monotonic() - t0, 3)})
            if code != 0 or timed_out:
                break
        fh.write(f"\nEXIT={code}\n")
    seconds = round(time.monotonic() - start, 3)
    text = _read_from(log_path, offset)
    parsed = parse_output(text)
    ok = code == 0 and not timed_out
    # SEL-043 (AD-037-R21): `seconds` is monotonic and leaves out sleep; the wall clock and the power log's sleep are
    # recorded beside it, and wall time is what a person is shown.
    from seldon.core import stations as Q
    wall = Q.wall_fields(stamp, Q._iso_now(), seconds)
    return {"ok": ok, "outcome": OUTCOME_PASS if ok else (OUTCOME_TIMEOUT if timed_out else OUTCOME_FAIL),
            "exit_code": code, "timed_out": timed_out, "seconds": seconds, **wall, "steps": done,
            "tests_run": parsed["tests_run"], "failed_files": parsed["failed_files"],
            "tail": "" if ok else text[-TAIL_BYTES:], "log_path": str(log_path)}


# ================================================================================================ the record

def escapes(events: list, p: dict, result: dict) -> list:
    """R33: of the files a full gate failed, those the last scoped gate on the same change set did not select."""
    if p["tier"] != TIER_FULL or not result.get("failed_files"):
        return []
    for e in reversed(runs(events)):
        q = e.get("payload") or {}
        if q.get("tier") == TIER_SCOPED and q.get("change_set") == p["change_set"]:
            chosen = set(q.get("tests") or [])
            return [f for f in result["failed_files"] if f not in chosen]
    return []


def record_payload(p: dict, result: dict, *, call_site: str, events: list, task_id: str | None = None,
                   branch: str | None = None, log_rel: str | None = None, lane: bool = False) -> dict:
    """The `gate_run` payload (R33). SEL-055: `main_red` (R39, the closure the plan applied) and `lane` (R40) are
    written only when they hold, so a record of a project that uses neither is unchanged."""
    if call_site not in CALL_SITES:
        raise ValueError(f"call_site must be one of {CALL_SITES}, got {call_site!r}")
    extra = {}
    if p.get("main_red"):
        extra["main_red"] = p["main_red"]
    if lane:
        extra["lane"] = True
    return {**extra, "task_id": task_id, "branch": branch, "call_site": call_site, "tier": p["tier"], "reason": p["reason"],
            "reasons": p["reasons"][:RECORD_LIST_CAP], "commit": p["commit"], "tree": p["tree"], "dirty": p["dirty"],
            "base": p["base"], "fork": p["fork"], "change_set": p["change_set"], "changed": len(p["changed"]),
            "slices": sorted(p["slices"]), "unmatched": p["unmatched"][:RECORD_LIST_CAP],
            "unmatched_count": len(p["unmatched"]),
            "tests": p["tests"] if p["tier"] == TIER_SCOPED else [], "markers": p["markers"],
            "commands": p["commands"], "always": p["always"], "files_selected": p["files_selected"],
            "files_total": p["files_total"], "tests_run": result.get("tests_run"), "seconds": result["seconds"],
            "started_at": result.get("started_at"), "ended_at": result.get("ended_at"),
            "wall_seconds": result.get("wall_seconds"), "asleep_s": result.get("asleep_s"),
            "steps": result.get("steps") or [], "outcome": result["outcome"], "exit_code": result["exit_code"],
            "failed_files": result.get("failed_files") or [], "log_path": log_rel or result.get("log_path"),
            "escapes": escapes(events, p, result)}


def emit(primary: Path, payload: dict, actor: str, session_id: str | None = None) -> dict:
    """Append the `gate_run` record to the primary checkout's store (AD-038-R4: a worktree's records go where the
    dispatcher reads them)."""
    from seldon.core.events import append_event, make_event
    ev = make_event(event_type=EVENT_GATE_RUN, actor=actor, authority="accepted", payload=payload,
                    session_id=session_id)
    append_event(Path(primary), ev)
    return ev


def passing_record(events: list, tree_hash: str) -> dict | None:
    """R34: the newest passing `gate_run` event for `tree_hash`, run on a clean tree, or None."""
    for e in reversed(runs(events)):
        q = e.get("payload") or {}
        if q.get("tree") == tree_hash and q.get("outcome") == OUTCOME_PASS and not q.get("dirty"):
            return e
    return None


def completion_evidence(primary: Path, branch: str, events: list) -> dict | None:
    """SEL-058 (AD-034-R41): the passing, clean `gate_run` of `branch`'s tip tree in `primary`, or None.

    What `seldon cc complete` needs before it completes a task the dispatcher blocked: whatever reached main by hand,
    the tree main holds now has passed a gate (a scheduled run, `seldon gate main`, or a full `seldon gate run`).
    None when the branch cannot be read: no evidence is not evidence.

    REVIEW-001 F-03: only a FULL gate counts, as R41 names (the scheduled run is full). A scoped `seldon gate run` of
    main's clean tree selects nothing (its change set is empty, `declared_none`) and passes at once, and R26 says a gate
    that ran nothing is not evidence."""
    out = subprocess.run(["git", "-C", str(primary), "rev-parse", f"{branch}^{{tree}}"], capture_output=True,
                         text=True)
    if out.returncode != 0:
        return None
    full = [e for e in events if (e.get("payload") or {}).get("tier") == TIER_FULL]
    return passing_record(full, out.stdout.strip())


def evidence(e: dict) -> dict:
    """What a merge record's `gate_evidence` says of the `gate_run` it merged on."""
    q = e.get("payload") or {}
    out = {"source": "gate_run", "event_id": e.get("event_id"), "tier": q.get("tier"), "reason": q.get("reason"),
           "call_site": q.get("call_site"), "seconds": q.get("seconds")}
    if (q.get("main_red") or {}).get("event_id"):
        # SEL-055 (R39): the closure the record was planned under, which `closure_admits` compares.
        out["main_red"] = q["main_red"]["event_id"]
    return out


# ================================================================================================ R36: telling

def scoped_seconds(events: list, n: int = WARN_WINDOW) -> list:
    """Monotonic seconds of the last `n` scoped gates. Deliberately not wall time (SEL-043): the warning is about how
    much the slices select, and a host that slept through a gate did not make the gate slow."""
    return [float((e.get("payload") or {}).get("seconds") or 0) for e in runs(events)
            if (e.get("payload") or {}).get("tier") == TIER_SCOPED][-n:]


def _sample_path(glob: str) -> str:
    """A path a glob matches, to ask whether another set of globs covers it (R40's warning): `**` as one directory,
    `*` and `?` as one letter, a trailing `/` as a file in the directory."""
    if glob.endswith("/"):
        glob += "x"
    return re.sub(r"\*\*/?", "x/", glob).replace("*", "x").replace("?", "x").rstrip("/") or "x"


def lane_uncovered(gcfg: dict | None, lane: dict | None) -> list:
    """R40: the lane's `writes` globs no declared slice covers (a merge of a lane branch that writes there is full)."""
    if not lane:
        return []
    slices = (gcfg or {}).get("slices") or []
    return [w for w in lane.get("writes") or []
            if not any(_any(_sample_path(w), s["paths"]) for s in slices)]


def warnings(gcfg: dict | None, gate_command: str | None, events: list, lane: dict | None = None) -> list:
    """R36's warnings, never failures: a gate command with no slices, and a median scoped gate over the threshold.
    SEL-055 (R40): a coordination lane whose `writes` no slice covers, where the project has a gate command."""
    out = []
    gcfg = gcfg or DEFAULTS
    uncovered = lane_uncovered(gcfg, lane) if gate_command else []
    if uncovered:
        out.append(f"dispatch.coordination_lane.writes {uncovered} match no dispatch.gate.slices entry: a lane branch "
                   f"that writes there is gated in full at merge. Declare a slice for them (`tests: none`, or the "
                   f"tests that read them) (AD-034-R40).")
    if gate_command and not declared(gcfg):
        out.append("dispatch.gate_command is declared and dispatch.gate.slices is not: every task runs the whole "
                   "suite. Declare `dispatch.gate.slices` and `dispatch.gate.test_command` (AD-034-R30, AD-034 "
                   "ADDENDUM 12; `seldon gate plan` shows what a branch would run).")
    w = gcfg.get("warn_seconds")
    secs = scoped_seconds(events)
    if w and secs:
        med = statistics.median(secs)
        if med > w:
            out.append(f"the median of the last {len(secs)} scoped gate(s) is {med:.0f} s, over "
                       f"dispatch.gate.warn_seconds ({w:g} s): the slices select too much, or the suite's selected "
                       f"tests are slow (AD-034-R36)")
    return out


def by_week(events: list) -> list:
    """`seldon qc chart`'s gate line (R36): per ISO week, runs, median and total seconds per tier, and escapes."""
    weeks: dict = {}
    for e in runs(events):
        at = _ts(e)
        if at is None:
            continue
        y, w, _ = at.isocalendar()
        key = f"{y}-W{w:02d}"
        q = e.get("payload") or {}
        row = weeks.setdefault(key, {"week": key, TIER_SCOPED: [], TIER_FULL: [], "escapes": 0, "failed": 0})
        # SEL-043 (AD-037-R21): a person is shown wall time; a record from before R21 has only monotonic seconds.
        row.setdefault(q.get("tier") or TIER_FULL, []).append(float(q.get("wall_seconds") or q.get("seconds") or 0))
        row["escapes"] += len(q.get("escapes") or [])
        row["failed"] += q.get("outcome") != OUTCOME_PASS
    out = []
    for key in sorted(weeks):
        row = weeks[key]
        item = {"week": key, "escapes": row["escapes"], "failed": row["failed"]}
        for tier in (TIER_SCOPED, TIER_FULL):
            xs = row[tier]
            item[tier] = {"n": len(xs), "median_s": round(statistics.median(xs), 1) if xs else None,
                          "total_s": round(sum(xs), 1)}
        out.append(item)
    return out


def summary(p: dict) -> str:
    """One line for a plan: what `seldon gate plan` prints first and a refusal names."""
    if p["tier"] == TIER_FULL:
        more = f" (+{len(p['reasons']) - 1} more)" if len(p["reasons"]) > 1 else ""
        return f"full: {p['reason']}{more}"
    return (f"scoped: {p['files_selected']} of {p['files_total']} test files"
            + (f", markers {p['markers']}" if p["markers"] else "")
            + (f", {len(p['commands'])} command(s)" if p["commands"] else "")
            + f"; {p['reason']}")


def as_json(p: dict) -> str:
    return json.dumps(p, indent=1, sort_keys=True)
