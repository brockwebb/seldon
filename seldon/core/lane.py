"""The coordination lane and the project's own premises (SEL-054 Part A; AD-038-R40 to R42).

**The lane (R40, R41).** `dispatch.coordination_lane: {name_pattern, slots, writes, merge_wait_s}` names one class of
work once, in configuration: a task whose graph name matches `name_pattern` (factory's `^OODA-\\d+`) is a lane task.
It goes first among eligible candidates, runs in its own worktree under its own supervisor, and holds one of `slots`
reserved slots that are not `max_parallel`'s. An exclusive task does not hold it back and it does not hold an
exclusive task back, because what a lane task may change in this repository is declared (`writes`) and the merge
refuses the rest (`outside_writes`). Prior art: Slurm's QOS, which reserves capacity for a named class of jobs;
Kubernetes' `system-cluster-critical` PriorityClass, a class named once by the operator rather than a priority set per
job; and the readers-writer lock (Courtois, Heymans and Parnas, CACM 1971), whose writer need not exclude a party that
touches nothing it writes. DN-006 decision 9 (no per-task priority field) stands: no task file can put itself in the
lane; only the configured pattern does.

**Project premises (R42).** `dispatch.premises: [{statement, check}]`: opaque `check:` commands station (a) runs before
every launch, beside `environment_in_flight`. A false one refuses the launch and names itself and its check's output.
It is a STANDING condition of the project, not a defect of a task, so it is treated as `environment_in_flight` and
`api_key_present` are: one record per episode, the stuck streak, no Issue, and it clears itself when the check
passes. Prior art: admission control evaluated for every request at the queue's head (Kubernetes validating admission
and ResourceQuota, which refuse new pods and never touch running ones).
"""
from __future__ import annotations

import fnmatch
import re

#: The `seldon.yaml` keys.
LANE_KEY = "coordination_lane"
PREMISES_KEY = "premises"

#: How long a lane task's supervisor waits for the pass lease at its finish. An exclusive task's holder keeps the pass
#: lease for its whole session (`dispatch._launch_inplace`), so a lane task that finishes beside a build waits for the
#: build; `merge_lock_timeout_s` (600 s, sized for a pass) would give up first and leave the task `released_unfinished`.
#: **No measured basis**: four hours, above factory FAC-31's ninety-minute build (the filing's own observation).
LANE_MERGE_WAIT_S_DEFAULT = 14400

#: The refusal reasons this module adds to `dispatch.REFUSAL_REASONS`.
REFUSED_PROJECT_PREMISE = "project_premise_false"
#: A lane candidate waiting for a lane slot (c6 for a lane task, and `plan_launches`' deferral reason).
DEFERRED_LANE_SLOTS = "lane_slots"
#: The merge round's reason for a lane branch that changed a path its lane does not declare.
MERGE_LANE_WROTE_OUTSIDE = "lane_wrote_outside"


class LaneConfigError(ValueError):
    """`dispatch.coordination_lane` or `dispatch.premises` is malformed."""


def load_lane(value) -> dict | None:
    """`dispatch.coordination_lane`, validated; None when absent (nothing changes)."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise LaneConfigError(f"dispatch.{LANE_KEY} must be a mapping, got {value!r}")
    unknown = sorted(set(value) - {"name_pattern", "slots", "writes", "merge_wait_s"})
    if unknown:
        raise LaneConfigError(f"dispatch.{LANE_KEY} has unknown key(s) {unknown}: expected name_pattern, slots, "
                              f"writes, merge_wait_s")
    pattern = value.get("name_pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        raise LaneConfigError(f"dispatch.{LANE_KEY}.name_pattern must be a non-empty regular expression, got "
                              f"{pattern!r}")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise LaneConfigError(f"dispatch.{LANE_KEY}.name_pattern {pattern!r} does not compile: {exc}") from exc
    slots = value.get("slots", 1)
    if isinstance(slots, bool) or not isinstance(slots, int) or slots < 1:
        raise LaneConfigError(f"dispatch.{LANE_KEY}.slots must be a positive whole number, got {slots!r}")
    writes = value.get("writes")
    # Required, not defaulted: the lane is safe beside an exclusive build only because what it may change is declared,
    # so a lane with no declaration would be a second exclusive task that nothing holds back.
    if not isinstance(writes, list) or not writes or not all(isinstance(w, str) and w.strip() for w in writes):
        raise LaneConfigError(f"dispatch.{LANE_KEY}.writes must be a non-empty list of repository-relative globs (what "
                              f"a lane task may change; the merge refuses the rest), got {writes!r}")
    for w in writes:
        if w.startswith("/") or ".." in w.split("/"):
            raise LaneConfigError(f"dispatch.{LANE_KEY}.writes entry {w!r} is not repository-relative")
    wait = value.get("merge_wait_s", LANE_MERGE_WAIT_S_DEFAULT)
    if isinstance(wait, bool) or not isinstance(wait, int) or wait < 1:
        raise LaneConfigError(f"dispatch.{LANE_KEY}.merge_wait_s must be a positive whole number of seconds, got "
                              f"{wait!r}")
    return {"name_pattern": pattern, "slots": slots, "writes": list(writes), "merge_wait_s": wait,
            "_re": compiled}


def is_lane(name: str | None, lane: dict | None) -> bool:
    """Whether a task with this graph name is a lane task. `re.search`, so the pattern anchors itself (`^OODA-`)."""
    return bool(lane and name and lane["_re"].search(str(name)))


def order(rows: list, lane: dict | None) -> list:
    """Lane tasks first, each class in the order it came (the caller's FIFO by `created_at`)."""
    if not lane:
        return rows
    return [r for r in rows if is_lane(r.get("name"), lane)] + [r for r in rows if not is_lane(r.get("name"), lane)]


def lane_c6(running_lane: list, slots: int) -> dict:
    """c6 for a lane task: a free lane slot. The in-place claim (an exclusive task in flight) is not its gate."""
    return {"lane": True, "lane_running": list(running_lane), "slots": slots, "ok": len(running_lane) < slots,
            **({} if len(running_lane) < slots else {"reason": DEFERRED_LANE_SLOTS})}


def apply_lane_c6(row: dict, running_lane: list, lane: dict) -> dict:
    """Replace a lane row's c6 with `lane_c6` and recompute its eligibility. Rows that are not candidates are left."""
    crit = row.get("criteria") or {}
    if not row.get("candidate") or "c6" not in crit:
        return row
    crit["c6"] = lane_c6(running_lane, lane["slots"])
    row["eligible"] = all(v["ok"] for v in crit.values())
    row["failed"] = [k for k, v in crit.items() if not v["ok"]]
    row["lane"] = True
    return row


def path_matches(path: str, glob: str) -> bool:
    """A path against one `writes` glob. `fnmatch`'s `*` crosses `/`, so `notes/*` and `notes/**` both take a nested
    file; a trailing `/` names the whole directory."""
    if glob.endswith("/"):
        return path.startswith(glob)
    return fnmatch.fnmatchcase(path, glob)


def outside_writes(writes: list, lane: dict, exempt: set) -> list:
    """The paths a lane branch changed that its lane does not declare (R41). `exempt`: the task's own RESULT, the
    `merge=union` files (append-only, merged by design) and the gate record ledger."""
    return sorted(w for w in writes if w not in exempt and not any(path_matches(w, g) for g in lane["writes"]))


def load_premises(value) -> list:
    """`dispatch.premises`, validated: `[{statement, check}]`. Absent is none."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise LaneConfigError(f"dispatch.{PREMISES_KEY} must be a list of {{statement, check}}, got {value!r}")
    out = []
    for i, p in enumerate(value):
        if not isinstance(p, dict) or set(p) - {"statement", "check"}:
            raise LaneConfigError(f"dispatch.{PREMISES_KEY}[{i}] must be a mapping of statement and check, got {p!r}")
        statement, check = p.get("statement"), p.get("check")
        if not isinstance(statement, str) or not statement.strip():
            raise LaneConfigError(f"dispatch.{PREMISES_KEY}[{i}].statement must be a non-empty string")
        if not isinstance(check, str) or not check.strip():
            raise LaneConfigError(f"dispatch.{PREMISES_KEY}[{i}].check must be a non-empty shell command")
        out.append({"statement": statement.strip(), "check": check.strip()})
    return out


def review_project_premises(premises: list, run, cwd, timeout_s: float, **run_kw) -> dict:
    """Run every project premise's check. `run` is `stations.run_check`. `outcome` is `true` when all pass (or none
    is declared), else `false`; each false row carries its check's exit, stdout and stderr tails."""
    rows = []
    for p in premises:
        r = run(p["check"], cwd, timeout_s, **run_kw)
        outcome = "true" if r.get("outcome") == "pass" else ("false" if r.get("outcome") == "fail" else "unrunnable")
        rows.append({"statement": p["statement"], "command": p["check"], "outcome": outcome,
                     "exit_code": r.get("exit"), "output": (r.get("tail") or "").strip()[-500:]})
    false = [r for r in rows if r["outcome"] != "true"]
    return {"source": "project", "premises": rows, "false": false, "outcome": "false" if false else "true"}


def episode_identity(review: dict) -> str:
    """What makes two refusals one episode: the same premises false. Output is not part of it (a counter in it would
    make every pass a new episode)."""
    return " | ".join(sorted(f["statement"] for f in review["false"]))
