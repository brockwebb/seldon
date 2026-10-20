"""The toil measure `seldon qc chart` reports per ISO week (AD-038-R6, FRICTION-001 Part E).

**Why this exists.** AD-038-R6: "no new control enters the dispatcher without its own negative control and a toil
measure". Between 10 and 17 October 2026 the operator broke every dispatcher stall by hand: a paste, a Desktop
restart, a re-issued task. Google SRE, "Eliminating Toil" (Beyer et al. 2016, ch. 5): toil is manual, repetitive,
automatable, tactical, without enduring value, and scales with the service; its cure starts with measuring it. The
target for every count here is zero; the chart is the evidence that it stays there.

Four counts per week, each read from a record that already exists or that this task added:

* **passes refused on machine dirt**: dispatcher passes (one `=== <ts> | seldon-dispatch fire` block of the launchd
  wrapper's log) that refused a candidate as `dirty_tree` while every dirty path it named was machine-written
  governed state (`seldon.core.reconcile`'s classes, by path). Passes refused on other dirt are counted beside it.
* **redrives by an operator**: `dispatch_redrive` events whose actor is not `dispatcher` (AD-038-R2).
* **Desktop restarts**: inferred from the stale refusals seldon-mcp's read-only tools appended to its stale log
  between AD-038-R3 and MCP-001: each server process (its `loaded_at` and HEAD) that refused at least once was
  replaced by a restart. Since MCP-001 (AD-038 ADDENDUM 01) every tool runs the checkout's current code in a fresh
  process and none refuses, so nothing appends and the count is zero by construction; the old rows still count.
* **re-issues**: ResearchTasks walked to `superseded` that were never launched (`dispatch_launched`), DESK-002 to
  DESK-002R's shape.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

_FIRE_RE = re.compile(r"^=== (?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) \| \S+ fire\s*$")
_DIRTY_REFUSAL_RE = re.compile(r"^\s+[0-9a-f?]{1,8} dirty_tree: ")
_DIRTY_PATHS_RE = re.compile(r"^\s+dirty: (?P<paths>.*)$")
_UNRECONCILED_RE = re.compile(r"^\s+unreconciled: (?P<path>[^:]+): ")


def week_of(ts: str) -> str:
    """The ISO week of a timestamp, `YYYY-Www`."""
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def machine_path(path: str, gp: dict) -> bool:
    """Is `path` machine-written governed state? The reconciler's classes, by path alone (a historical log names
    paths, not their diffs): the event store, the prior-art logs, the decision register, seldon.yaml (the
    cadence's write-back) and task files under cc_tasks/."""
    if path in {gp.get("event_store"), gp.get("query_log"), gp.get("verdict_ledger"), gp.get("rendered"),
                "seldon.yaml"}:
        return True
    reg = (gp.get("register_dir") or "").rstrip("/") + "/"
    return path.startswith(reg) or (path.startswith("cc_tasks/") and path.endswith(".md"))


def dirt_passes(log_paths: list, gp: dict) -> dict:
    """`{week: {"machine": n, "other": n}}` over every pass block in the given dispatcher logs.

    A pass counts once, by its refusal lines: `machine` when every path named on its `dirty:` line is machine
    dirt (the `(+N more)` tail is not a path); `other` when any named path is not, or when the reconciler named an
    unreconciled path (after AD-038-R1 that is all the dirt a refusal can show).
    """
    out: dict = {}
    for log in log_paths:
        week, refused, paths, unreconciled = None, False, [], False

        def close():
            if week and refused:
                row = out.setdefault(week, {"machine": 0, "other": 0})
                named = [p for p in paths if not p.startswith("(+")]
                if named and not unreconciled and all(machine_path(p, gp) for p in named):
                    row["machine"] += 1
                else:
                    row["other"] += 1

        with Path(log).open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = _FIRE_RE.match(line)
                if m:
                    close()
                    week, refused, paths, unreconciled = week_of(m.group("ts")), False, [], False
                    continue
                if _DIRTY_REFUSAL_RE.match(line):
                    refused = True
                    continue
                d = _DIRTY_PATHS_RE.match(line)
                if d and refused and not paths:
                    paths = [p.strip() for p in d.group("paths").split(",") if p.strip()]
                    continue
                if _UNRECONCILED_RE.match(line):
                    unreconciled = True
        close()
    return out


def stale_restarts(stale_log: Path | None) -> dict:
    """`{week: n}`: server processes that refused as stale at least once, by the week of their first refusal."""
    if stale_log is None or not Path(stale_log).is_file():
        return {}
    first: dict = {}
    for raw in Path(stale_log).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        key = (row.get("loaded_head"), row.get("loaded_at"), row.get("pid"))
        if row.get("at") and key not in first:
            first[key] = row["at"]
    out: dict = {}
    for at in first.values():
        out[week_of(at)] = out.get(week_of(at), 0) + 1
    return out


def event_counts(events: list) -> tuple:
    """`({week: operator redrives}, {week: superseded-never-launched tasks})` from the event store."""
    launched = {(e.get("payload") or {}).get("task_id") for e in events if e.get("event_type") == "dispatch_launched"}
    redrives, reissues = {}, {}
    for e in events:
        p = e.get("payload") or {}
        if e.get("event_type") == "dispatch_redrive" and e.get("actor") != "dispatcher":
            w = week_of(e["timestamp"])
            redrives[w] = redrives.get(w, 0) + 1
        elif (e.get("event_type") == "artifact_state_changed" and p.get("artifact_type") == "ResearchTask"
              and p.get("to_state") == "superseded" and p.get("artifact_id") not in launched):
            w = week_of(e["timestamp"])
            reissues[w] = reissues.get(w, 0) + 1
    return redrives, reissues


def toil(events: list, log_paths: list, gp: dict, stale_log: Path | None) -> dict:
    """The per-week toil reading: `{"weeks": [{week, refused_machine_dirt, refused_other_dirt, redrives_by_operator,
    desktop_restarts, reissued_tasks, interventions}], "sources": {...}}`, weeks in order."""
    dirt = dirt_passes(log_paths, gp)
    restarts = stale_restarts(stale_log)
    redrives, reissues = event_counts(events)
    weeks = sorted(set(dirt) | set(restarts) | set(redrives) | set(reissues))
    rows = []
    for w in weeks:
        row = {"week": w, "refused_machine_dirt": dirt.get(w, {}).get("machine", 0),
               "refused_other_dirt": dirt.get(w, {}).get("other", 0),
               "redrives_by_operator": redrives.get(w, 0), "desktop_restarts": restarts.get(w, 0),
               "reissued_tasks": reissues.get(w, 0)}
        row["interventions"] = row["redrives_by_operator"] + row["desktop_restarts"] + row["reissued_tasks"]
        rows.append(row)
    return {"weeks": rows, "sources": {"dispatch_logs": [str(p) for p in log_paths],
                                       "stale_log": str(stale_log) if stale_log else None}}


def dispatch_logs(project_dir: Path, rel: str | None) -> list:
    """The dispatcher log named by `qc.toil.dispatch_log` and its rotations (`<log>.<timestamp>`), oldest first."""
    if not rel:
        return []
    log = Path(project_dir) / rel
    rotated = sorted(log.parent.glob(log.name + ".*")) if log.parent.is_dir() else []
    return rotated + ([log] if log.is_file() else [])
