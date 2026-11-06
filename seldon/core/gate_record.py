"""A project's declared pass record gates the merge (SEL-024, AD-034 ADDENDUM 08, AD-034-R16 and R17).

**Why this exists.** On squiddy main, four tasks merged between the 2026-10-27 kit pass (`bc345c09`) and SQ-099's
(`d31501c7`) with no pass record, and SQ-101 merged at `67cde2da` with none, its RESULT calling 17 failures
"worktree-environmental" and reporting that ruff was not installed, so no lint ran. squiddy's DN-043 R-188 requires a
pass per kit commit and DN-052 R-237 makes the ledger main's; the merge round accepted whatever the session's RESULT
said, so the rule held only when a session chose to honour it.

**The rule lives in the project; seldon only reads it.** A project declares, in seldon.yaml:

    dispatch:
      gate_record:
        command: python -m squiddy kit record-pass   # run in the worktree, under the declared interpreter
        ledger: kit/ledger/passes.jsonl              # the tracked JSONL the command appends one line to
        commit_field: payload.commit                 # where a line names the commit it judged
        pass_field: payload.passed                   # true on a pass, anything else is not one
        timeout_s: 9000                              # the command's wall clock
        requires: [ruff]                             # tools that must resolve on the command's PATH
        unrunnable_exits: [4, 5]                     # the command's own "I could not judge" exits
        tree_paths: [squiddy/]                       # what a pass covers; absent, the whole tree

or `gate_record: none` where the project keeps no ledger. Absent, the merge round is today's.

**What "a record for the exact tip" means.** A line covers the tip when the commit it names has the tip's tree, apart
from the ledger itself and the housekeeping the merge round already rebases over without a round (the `merge=union`
files and `dispatch.shared_paths`). This is reproducible-build identity (the Reproducible Builds project's definition:
the same source produces the same artifact) applied at git's own unit, the tree: a commit is recorded, then the line
naming it is committed on top, so the merged tip is never the recorded commit itself but is byte-identical to it
where it matters. By default the whole tree is compared. A project whose own rule scopes a pass to part of the tree
declares that part in `tree_paths`: squiddy's `kitpass.pass_for` accepts a later commit whose `squiddy/` tree is
unchanged (check_pin.kit_matches), and seldon reads squiddy's ledger by squiddy's rule, not a stricter one of its own.
Without the scope, every commit main took during a long gate (a filed task file, a handoff) would be a new tree, and
a 108-minute kit pass could be outrun indefinitely. The newest line that covers the tip decides: a pass covers, a
later failure for the same tree does not.

**"Environmental" is a refusal, not a pass.** A gate that could not run (a declared tool absent from its PATH, the
shell's 126/127, a usage error, python's `No module named` for its `-m` module, or one of the project's
`unrunnable_exits`) is `gate_unrunnable`: in MSA's terms an inspection-equipment failure, which yields no reading. It
blocks the merge and opens a huddle naming the tool; nothing is recorded as a pass. The classification reuses the
stations' (`seldon.core.stations.run_check`), so a gate and a `check:` line mean the same thing by "unrunnable".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

#: The `dispatch:` key.
CONFIG_KEY = "gate_record"
#: The explicit "this project keeps no pass ledger" value.
NONE = "none"
#: Merge-round refusal reasons (AD-034-R16, R17).
PASS_UNRECORDED = "pass_unrecorded"
GATE_UNRUNNABLE = "gate_unrunnable"
#: The events the record path writes: a pending record a locked path left (`PENDING`), and one run of the command
#: (`RECORDED`), whatever its outcome.
EVENT_PENDING = "gate_record_pending"
EVENT_RECORDED = "gate_recorded"

_KEYS = {"command", "ledger", "commit_field", "pass_field", "timeout_s", "requires", "unrunnable_exits", "tree_paths"}
_REQUIRED = ("command", "ledger", "commit_field", "pass_field", "timeout_s")
#: python's own message when `-m <module>` names a module it cannot import: the interpreter has no such install.
_NO_MODULE_RE = re.compile(r"^\S*python[\d.]*: No module named (\S+)", re.MULTILINE)


class GateRecordError(Exception):
    """The declaration is malformed."""


def parse(value) -> Optional[dict]:
    """The validated `dispatch.gate_record` value: None when absent or `none`, else the full mapping. Idempotent, so
    a block parsed once may be parsed again."""
    if value is None or value == NONE:
        return None
    if not isinstance(value, dict):
        raise GateRecordError(f"dispatch.{CONFIG_KEY} must be a mapping or {NONE!r}, got {value!r}")
    extra = sorted(set(value) - _KEYS)
    if extra:
        raise GateRecordError(f"dispatch.{CONFIG_KEY} has unknown key(s) {extra}; known: {sorted(_KEYS)}")
    missing = [k for k in _REQUIRED if k not in value]
    if missing:
        raise GateRecordError(f"dispatch.{CONFIG_KEY} is missing {missing}; every one is the project's to declare "
                              f"(seldon guesses neither its ledger's shape nor its gate's wall clock)")
    for k in ("command", "ledger", "commit_field", "pass_field"):
        if not isinstance(value[k], str) or not value[k].strip():
            raise GateRecordError(f"dispatch.{CONFIG_KEY}.{k} must be a non-empty string, got {value[k]!r}")
    ledger = value["ledger"]
    if ledger.startswith("/") or ".." in ledger.split("/"):
        raise GateRecordError(f"dispatch.{CONFIG_KEY}.ledger {ledger!r} is not repository-relative")
    t = value["timeout_s"]
    if isinstance(t, bool) or not isinstance(t, (int, float)) or t <= 0:
        raise GateRecordError(f"dispatch.{CONFIG_KEY}.timeout_s must be a positive number of seconds, got {t!r}")
    requires = value.get("requires", [])
    if not isinstance(requires, list) or not all(isinstance(r, str) and r.strip() for r in requires):
        raise GateRecordError(f"dispatch.{CONFIG_KEY}.requires must be a list of tool names, got {requires!r}")
    exits = value.get("unrunnable_exits", [])
    if not isinstance(exits, list) or not all(isinstance(e, int) and not isinstance(e, bool) and e != 0
                                              for e in exits):
        raise GateRecordError(f"dispatch.{CONFIG_KEY}.unrunnable_exits must be a list of non-zero exit codes, got "
                              f"{exits!r}")
    paths = value.get("tree_paths", [])
    if not isinstance(paths, list) or not all(isinstance(x, str) and x.strip() and not x.startswith("/")
                                              and ".." not in x.split("/") for x in paths):
        raise GateRecordError(f"dispatch.{CONFIG_KEY}.tree_paths must be a list of repository-relative paths, got "
                              f"{paths!r}")
    return {"command": value["command"], "ledger": ledger, "commit_field": value["commit_field"],
            "pass_field": value["pass_field"], "timeout_s": t, "requires": list(requires),
            "unrunnable_exits": list(exits), "tree_paths": list(paths)}


# ------------------------------------------------------------------------------------------------- the ledger read

def _git(repo: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _field(obj, dotted: str):
    for part in dotted.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def ledger_lines(repo: Path, rev: str, decl: dict) -> list:
    """The ledger as `rev` carries it: `[(commit, passed)]` per parseable line, oldest first. A file read; no lock."""
    r = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{decl['ledger']}"], capture_output=True)
    if r.returncode != 0:
        return []
    out = []
    for raw in r.stdout.decode("utf-8", "replace").splitlines():
        if not raw.strip():
            continue
        try:
            line = json.loads(raw)
        except json.JSONDecodeError:
            continue
        commit = _field(line, decl["commit_field"])
        if isinstance(commit, str) and commit:
            out.append((commit, _field(line, decl["pass_field"]) is True))
    return out


def tree_differences(repo: Path, recorded: str, tip: str, paths: Optional[list] = None) -> Optional[list]:
    """The paths (under `paths`, or anywhere) whose content differs between two commits' trees, or None when
    `recorded` is not a commit here."""
    if _git(repo, "cat-file", "-e", f"{recorded}^{{commit}}").returncode != 0:
        return None
    r = _git(repo, "diff", "--name-only", "--no-renames", recorded, tip, "--", *(paths or []))
    if r.returncode != 0:
        return None
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def coverage(repo: Path, tip: str, decl: dict, housekeeping) -> dict:
    """Does the ledger at `tip` carry a pass for `tip`'s tree? `housekeeping(paths) -> set` names the paths among
    `paths` the merge round treats as housekeeping (`merge=union` files and `shared_paths`).

    `{covered, tip, recorded, reason}`: `recorded` is the commit of the line that decided, `reason` is None when
    covered, `no_line` when no line covers the tip's tree, `recorded_fail` when the newest such line is not a pass.
    """
    lines = ledger_lines(repo, tip, decl)
    for commit, passed in reversed(lines):
        diff = tree_differences(repo, commit, tip, decl.get("tree_paths"))
        if diff is None:
            continue
        rest = set(diff) - {decl["ledger"]}
        if rest and not rest <= set(housekeeping(sorted(rest))):
            continue
        return {"covered": passed, "tip": tip, "recorded": commit, "lines": len(lines),
                "reason": None if passed else "recorded_fail"}
    return {"covered": False, "tip": tip, "recorded": None, "lines": len(lines), "reason": "no_line"}


# ------------------------------------------------------------------------------------------------- the gate run

def run(wt: Path, decl: dict, interpreter: Optional[str] = None, env: Optional[dict] = None) -> dict:
    """Run the declared command in `wt` through the stations' runner (AD-037-R14's path, AD-037-R15's interpreter).

    The row is `run_check`'s, with `outcome` one of `pass`, `fail` or `unrunnable`, and `missing` naming the tools or
    modules an unrunnable gate lacked. Never raises for a gate that cannot start: that is a reading of its own.
    """
    from seldon.core import stations as Q
    base = dict(os.environ if env is None else env)
    path_env = Q.interpreter_env(interpreter, base) if interpreter else base
    missing = [t for t in decl["requires"] if shutil.which(t, path=path_env.get("PATH")) is None]
    if missing:
        return {"command": decl["command"], "interpreter": interpreter, "outcome": "unrunnable", "exit": None,
                "seconds": 0.0, "missing": missing,
                "tail": f"required tool(s) not on the gate's PATH: {', '.join(missing)}"}
    row = Q.run_check(decl["command"], wt, decl["timeout_s"], env=base, interpreter=interpreter)
    tail = row.get("tail") or ""
    if row["outcome"] == "fail" and row.get("exit") in decl["unrunnable_exits"]:
        row = {**row, "outcome": "unrunnable", "missing": [f"exit {row['exit']} (declared unrunnable)"]}
    elif row["outcome"] == "fail" and row.get("exit") == 1 and _NO_MODULE_RE.search(tail):
        row = {**row, "outcome": "unrunnable", "missing": [_NO_MODULE_RE.search(tail).group(1)]}
    elif row["outcome"] == "unrunnable" and "missing" not in row:
        argv0 = decl["command"].split()[0] if decl["command"].split() else decl["command"]
        row = {**row, "missing": [argv0] if row.get("exit") in Q.UNRUNNABLE_EXITS else ["usage"]}
    return row


def commit_ledger(wt: Path, decl: dict, tip: str, outcome: str) -> dict:
    """Commit the line the command appended to the ledger, alone, on the worktree's branch. `{committed, commit,
    stderr}`; nothing to commit is `committed: False` with no error (a command that recorded nothing)."""
    status = _git(wt, "status", "--porcelain", "--", decl["ledger"]).stdout.strip()
    if not status:
        return {"committed": False, "commit": None, "stderr": ""}
    add = _git(wt, "add", "--", decl["ledger"])
    if add.returncode != 0:
        return {"committed": False, "commit": None, "stderr": (add.stderr or add.stdout).strip()[-500:]}
    msg = (f"gate_record: {outcome} recorded for {tip[:12]} in {decl['ledger']} (AD-034-R16)\n\n"
           f"Written by the dispatcher's merge round from `{decl['command']}`.")
    c = _git(wt, "commit", "-q", "-m", msg, "--", decl["ledger"])
    if c.returncode != 0:
        return {"committed": False, "commit": None, "stderr": (c.stderr or c.stdout).strip()[-1000:]}
    return {"committed": True, "commit": _git(wt, "rev-parse", "HEAD").stdout.strip(), "stderr": ""}


def summary(row: dict) -> dict:
    """What an event or a merge record keeps of a gate run."""
    return {k: row.get(k) for k in ("command", "interpreter", "outcome", "exit", "seconds", "missing")
            if row.get(k) is not None} | {"tail": (row.get("tail") or "")[-600:]}
