"""A halted task is redriven, not re-issued (AD-038-R2, FRICTION-001 Part B).

**Why this exists.** `blocked` used to lead only to `in_progress`, `superseded` and `withdrawn`, and only `proposed`
and `accepted` are dispatchable, so a false stop could only be answered by a new task file, a supersede and a
re-registration: DESK-002's halt became DESK-002R at the cost of one task file, one supersede and 44 minutes
(`docs/design/AD-038_the_machine_reconciles_its_own_state.md` §1, mechanism 2).

**Prior art.** Amazon SQS dead-letter-queue redrive: "By default, dead-letter queue redrive moves messages from a
dead-letter queue to a source queue." A blocked task is a dead-lettered message; the queue needs a redrive, not a new
message. The task keeps its file, its id and its history; `blocked -> accepted` is the one new edge.

`redrive` clears `claimed_by`, records `dispatch_redrive` naming the stop it answers, and walks the task to `accepted`.
The dispatcher redrives on its own only when the stop's cause is one of its own recorded defects
(`AUTO_REDRIVE_REASONS`): a station that ran its check in the wrong tree (AD-038-R4) or a database outage (R6's
59b2db84). Any other cause waits for a redrive from a Desktop or CC session.
"""
from __future__ import annotations

from pathlib import Path

EVENT_REDRIVE = "dispatch_redrive"

#: Stops that are the dispatcher's own defects, so it answers them itself (AD-038-R2). Not a tunable: adding a reason
#: here decides that a class of stop is never the session's fault, which is a ruling, not a setting.
AUTO_REDRIVE_REASONS = ("check_unrunnable_wrong_tree", "database_unavailable")


class RedriveRefused(ValueError):
    """The task cannot be redriven: it is not blocked, or it does not exist."""


def _ts(event: dict) -> str:
    return str(event.get("timestamp") or "")


def answered_stop(events: list, task_id: str) -> dict | None:
    """The stop a redrive of this task answers: `{event_id, event_type, reason}`, or None when nothing is recorded.

    Read from the task's records since its last `dispatch_launched`, most specific first: the last `session_stop`
    (a station, the operator or the dispatcher stopped the line); else the last `huddle` that carries a `reason`
    (AD-038-R4's wrong-tree check); else a `dispatch_finished` that was not ok (its `failure`, or `finished_not_ok`).
    """
    since, records = "", []
    for e in events:
        p = e.get("payload") or {}
        if p.get("task_id") != task_id:
            continue
        if e.get("event_type") == "dispatch_launched":
            since, records = _ts(e), []
            continue
        if _ts(e) >= since:
            records.append(e)
    for kind, pick in (("session_stop", lambda p: p.get("reason")),
                       ("huddle", lambda p: p.get("reason")),
                       ("dispatch_finished", lambda p: None if p.get("ok") else (p.get("failure") or "finished_not_ok"))):
        for e in reversed(records):
            if e.get("event_type") != kind:
                continue
            reason = pick(e.get("payload") or {})
            if reason:
                return {"event_id": e.get("event_id"), "event_type": kind, "reason": reason}
    return None


def already_redriven(events: list, stop: dict | None) -> bool:
    """Has a `dispatch_redrive` already answered this stop? Keeps the automatic redrive to one per stop."""
    if stop is None:
        return False
    return any(e.get("event_type") == EVENT_REDRIVE and (e.get("payload") or {}).get("answers") == stop["event_id"]
               for e in events)


def redrive(project_dir: Path, driver, database: str, domain_config, task_id: str, actor: str,
            session_id: str | None = None, events: list | None = None) -> dict:
    """Walk a blocked task back to `accepted`, recording the stop it answers.

    Args:
        project_dir: The project root (the event store).
        driver: Neo4j driver.
        database: The project database.
        domain_config: The loaded domain configuration (the state machine).
        task_id: The full artifact id.
        actor: Who redrives: `dispatcher` for the automatic redrive, `desktop`, `cc` or `human` otherwise. `seldon
            qc chart` counts a non-dispatcher redrive as an operator intervention (AD-038-R6).
        session_id: Recorded on the events.
        events: The event store, when the caller has read it already.

    Returns:
        The `dispatch_redrive` payload.

    Raises:
        RedriveRefused: When the task does not exist or is not `blocked`.
    """
    from seldon.core.artifacts import transition_task, update_artifact
    from seldon.core.events import append_event, make_event, read_events

    with driver.session(database=database) as s:
        row = s.run("MATCH (t:ResearchTask {artifact_id: $id}) RETURN t.state AS state, t.claimed_by AS claimed_by, "
                    "t.source_file AS source_file", id=task_id).single()
    if row is None:
        raise RedriveRefused(f"no ResearchTask {task_id}")
    if row["state"] != "blocked":
        raise RedriveRefused(f"task {task_id[:8]} is {row['state']}, not blocked: only a halted task is redriven "
                             f"(AD-038-R2)")
    events = read_events(Path(project_dir)) if events is None else events
    stop = answered_stop(events, task_id)
    payload = {"task_id": task_id, "source_file": row["source_file"], "answers": stop and stop["event_id"],
               "stop_event_type": stop and stop["event_type"], "stop_reason": stop and stop["reason"],
               "cleared_claim": row["claimed_by"], "by": actor,
               "automatic": actor == "dispatcher"}
    # The claim first: an `accepted` task still carrying `claimed_by` would read as in flight to anything that keys
    # on the marker rather than the state.
    update_artifact(project_dir=project_dir, driver=driver, database=database, artifact_id=task_id,
                    properties={"claimed_by": None, "claimed_at": None}, actor=actor, authority="accepted",
                    session_id=session_id)
    append_event(project_dir, make_event(event_type=EVENT_REDRIVE, actor=actor, authority="accepted",
                                         payload=payload, session_id=session_id))
    transition_task(project_dir=project_dir, driver=driver, database=database, domain_config=domain_config,
                    artifact_id=task_id, current_state="blocked", new_state="accepted", actor=actor,
                    authority="accepted", session_id=session_id)
    return payload


def auto_redrive(project_dir: Path, driver, database: str, domain_config, session_id: str | None = None) -> list:
    """Redrive every dispatcher-claimed blocked task whose stop is one of `AUTO_REDRIVE_REASONS`, once per stop.

    Returns the `dispatch_redrive` payloads written. The caller holds the lease with no claim in flight.
    """
    from seldon.core.events import read_events

    with driver.session(database=database) as s:
        blocked = [dict(r) for r in s.run(
            "MATCH (t:ResearchTask {state: 'blocked'}) WHERE t.claimed_by STARTS WITH 'dispatcher:' "
            "RETURN t.artifact_id AS id ORDER BY t.created_at")]
    if not blocked:
        return []
    events = read_events(Path(project_dir))
    done = []
    for b in blocked:
        stop = answered_stop(events, b["id"])
        if stop is None or stop["reason"] not in AUTO_REDRIVE_REASONS or already_redriven(events, stop):
            continue
        done.append(redrive(project_dir, driver, database, domain_config, b["id"], "dispatcher", session_id,
                            events=events))
    return done
