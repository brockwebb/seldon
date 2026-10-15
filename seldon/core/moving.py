"""The status line: what is moving in a project's task queue (TRIAGE-001 Part B).

`seldon go` (text and `--json`, and the MCP `seldon_go`, which renders the text form) and
`seldon status` print this line first:

    Moving: <n> in progress, <n> proposed with a source file; <n> future ideas; <n> closed this week.

**Why a line and not the open-task list.** Before TRIAGE-001 the open list held twenty tasks of
which one had a source file, so "20 open" said nothing about what would actually run. The four
numbers separate the work that can move (in progress; proposed with a task file the dispatcher
can read) from the ideas parked under the `FUTURE` prefix (TRIAGE-001 decision rule 4) and from
what was closed recently.

**FUTURE is a description prefix, not a state.** Rule 4 rewrites a still-valid, unscheduled
task's description to begin `FUTURE (not scheduled; trigger: <condition>):`. The dispatcher
leaves such tasks out of its candidates and its log (`seldon.core.dispatch.evaluate`,
`seldon.commands.dispatch._tasks`), and this line counts them apart from the moving work.

**Counting rules**, each from the task's own properties:

- *in progress*: `state = in_progress`, not FUTURE.
- *proposed with a source file*: `state` in `seldon.core.dispatch.DISPATCHABLE_STATES` (proposed,
  and accepted, the dispatcher's transient claim step), a `source_file`, not FUTURE.
- *future ideas*: an open state (derived from the domain state machine, AD-028) and FUTURE.
- *closed this week*: a state outside the open set (completed, verified, superseded, withdrawn,
  rejected) whose closing time, `completed_at` else `updated_at`, falls inside the window.
  The window is `status.closed_window_days` in `seldon.yaml`, default
  `CLOSED_WINDOW_DAYS_DEFAULT`.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

#: TRIAGE-001 rule 4's marker: a description that begins with the word FUTURE.
FUTURE_RE = re.compile(r"^\s*FUTURE\b")

#: "This week" as a rolling window of days, overridable in seldon.yaml (`status.closed_window_days`).
CLOSED_WINDOW_DAYS_DEFAULT = 7

#: Every ResearchTask's properties this line reads. One query, so the line costs one round trip.
TASK_ROWS_QUERY = (
    "MATCH (t:ResearchTask) "
    "RETURN t.artifact_id AS artifact_id, t.state AS state, t.source_file AS source_file, "
    "       t.description AS description, t.completed_at AS completed_at, "
    "       t.updated_at AS updated_at"
)


def is_future(description: Optional[str]) -> bool:
    """True when a task's description carries TRIAGE-001 rule 4's `FUTURE` prefix.

    Args:
        description: The task's description; None reads as not FUTURE.

    Returns:
        Whether the task is a parked idea rather than moving work.
    """
    return bool(description) and FUTURE_RE.match(description) is not None


def closed_window_days(config: dict) -> int:
    """The closed-this-week window, from `status.closed_window_days` in seldon.yaml.

    Args:
        config: Parsed seldon.yaml.

    Returns:
        A positive number of days.

    Raises:
        ValueError: If the configured value is not a positive integer.
    """
    value = ((config or {}).get("status") or {}).get("closed_window_days", CLOSED_WINDOW_DAYS_DEFAULT)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"status.closed_window_days must be a positive integer, got {value!r}")
    return value


def _parse_ts(value, artifact_id) -> datetime:
    """An ISO-8601 timestamp as an aware UTC datetime; a naive one is read as UTC."""
    if not value:
        raise ValueError(f"closed ResearchTask {artifact_id} has neither completed_at nor updated_at")
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"ResearchTask {artifact_id}: unreadable timestamp {value!r}") from exc
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def moving_counts(rows: Iterable[dict], open_set: Iterable[str], now: datetime,
                  window_days: int) -> dict:
    """The four numbers of the status line, from task rows.

    Args:
        rows: One dict per ResearchTask with `state`, `source_file`, `description`,
            `completed_at`, `updated_at` (`artifact_id` for error messages).
        open_set: The open ResearchTask states (`seldon.core.artifacts.open_states`).
        now: The current time, timezone-aware.
        window_days: The closed-this-week window in days.

    Returns:
        `{in_progress, proposed_with_source, future, closed_this_week}`.

    Raises:
        ValueError: If a closed task carries no readable closing timestamp.
    """
    # Imported here, not at module top: `seldon.core.dispatch` imports `is_future` from this module.
    from seldon.core.dispatch import DISPATCHABLE_STATES

    open_set = set(open_set)
    since = now - timedelta(days=window_days)
    counts = {"in_progress": 0, "proposed_with_source": 0, "future": 0, "closed_this_week": 0}
    for r in rows:
        state = r.get("state")
        if state in open_set:
            if is_future(r.get("description")):
                counts["future"] += 1
            elif state == "in_progress":
                counts["in_progress"] += 1
            elif state in DISPATCHABLE_STATES and r.get("source_file"):
                counts["proposed_with_source"] += 1
        else:
            closed = _parse_ts(r.get("completed_at") or r.get("updated_at"), r.get("artifact_id"))
            if closed >= since:
                counts["closed_this_week"] += 1
    return counts


def moving_line(counts: dict) -> str:
    """Render the counts as the line `seldon go` and `seldon status` print first."""
    return (f"Moving: {counts['in_progress']} in progress, {counts['proposed_with_source']} "
            f"proposed with a source file; {counts['future']} future ideas; "
            f"{counts['closed_this_week']} closed this week.")


def project_moving(project_dir: str, now: Optional[datetime] = None) -> dict:
    """The counts for the project at `project_dir`, read from its graph.

    Args:
        project_dir: Project root holding seldon.yaml.
        now: Override for the current time (tests).

    Returns:
        The counts of `moving_counts`.

    Raises:
        FileNotFoundError: No seldon.yaml. Neo4j errors propagate; callers that must render
            regardless (`seldon go`) catch and say so.
    """
    from pathlib import Path

    from seldon.config import get_neo4j_driver, load_project_config
    from seldon.domain.loader import load_domain_config
    from seldon.core.artifacts import open_states

    config = load_project_config(Path(project_dir))
    domain_name = config["project"].get("domain", "research")
    domain_config = load_domain_config(
        Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml")
    driver = get_neo4j_driver(config)
    try:
        with driver.session(database=config["neo4j"]["database"]) as s:
            rows = [dict(r) for r in s.run(TASK_ROWS_QUERY)]
    finally:
        driver.close()
    return moving_counts(rows, open_states(domain_config, "ResearchTask"),
                         now or datetime.now(timezone.utc), closed_window_days(config))
