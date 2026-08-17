from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from neo4j import Driver, Session

from seldon.core.events import read_events, read_events_since
from seldon.core.graph import (
    change_state,
    create_artifact,
    create_link,
    remove_link,
    update_artifact,
)

logger = logging.getLogger(__name__)

_META_KEY = "sync_point"

# Event types that carry ontology state. Their payloads hold only counts and the
# master epoch, not the terms themselves, so they cannot be projected from the
# payload alone — replay restores them by re-running the ontology sync against
# the master database once, after the event loop. See _restore_ontology.
_ONTOLOGY_EVENT_TYPES = frozenset({"ontology_synced", "ontology_ingested"})

# Event types that are deliberately audit-only: they record that something
# happened, but project no graph state. Recognised here so replay does not warn
# about them. An unrecognised type is still a real warning — that is the signal
# an emitter was added without a replay decision being made.
_AUDIT_ONLY_EVENT_TYPES = frozenset({"paper_fix"})


def get_sync_point(session: Session) -> Optional[str]:
    """
    Return the last synced event_id from the _SeldonMeta node.
    Returns None if no sync point has been set (fresh database).
    """
    result = session.run(
        "MATCH (m:_SeldonMeta {key: $key}) RETURN m.last_event_id AS id",
        key=_META_KEY,
    ).single()
    if result is None:
        return None
    return result["id"]


def set_sync_point(session: Session, event_id: str) -> None:
    """
    Upsert the sync point in the _SeldonMeta node.
    Uses MERGE to ensure only one sync_point node exists.
    """
    session.run(
        "MERGE (m:_SeldonMeta {key: $key}) "
        "SET m.last_event_id = $event_id, m.synced_at = $now",
        key=_META_KEY,
        event_id=event_id,
        now=datetime.now(timezone.utc).isoformat(),
    )


def _apply_event(session: Session, event: Dict[str, Any]) -> bool:
    """
    Apply a single event to the Neo4j projection.
    Each event_type maps to one or more Cypher operations.

    Returns True if this event requires an ontology restore after the replay
    loop completes (see _restore_ontology); False otherwise.
    """
    event_type = event["event_type"]
    payload = event.get("payload", {})

    if event_type == "artifact_created":
        props = {
            "artifact_id": payload["artifact_id"],
            "state": payload.get("to_state", "proposed"),
            "authority": event.get("authority", "accepted"),
            "created_by": event.get("actor", "human"),
        }
        props.update(payload.get("properties", {}))
        create_artifact(session, payload["artifact_type"], props)

    elif event_type == "artifact_updated":
        update_artifact(session, payload["artifact_id"], payload.get("properties", {}))

    elif event_type == "artifact_state_changed":
        change_state(session, payload["artifact_id"], payload["to_state"])

    elif event_type == "link_created":
        create_link(
            session,
            payload["from_id"],
            payload["to_id"],
            payload["rel_type"].upper(),
            payload.get("properties", {}),
        )

    elif event_type == "link_removed":
        remove_link(
            session,
            payload["from_id"],
            payload["to_id"],
            payload["rel_type"].upper(),
        )

    elif event_type in _ONTOLOGY_EVENT_TYPES:
        # Cannot be projected from the payload — signal a post-loop restore.
        return True

    elif event_type in _AUDIT_ONLY_EVENT_TYPES:
        logger.debug("Audit-only event_type '%s' — no graph projection", event_type)

    else:
        logger.warning("Unknown event_type '%s' — skipped during sync", event_type)

    return False


def _restore_ontology(project_path: Path, driver: Driver, database: str) -> None:
    """
    Restore ontology state after a replay that saw ontology events.

    Ontology events record only counts and the master epoch, so the terms cannot
    be rebuilt from the event log. The ontology's source of truth is the master
    database, and `seldon ontology sync` is the code path that pulls from it —
    so replay reuses that path rather than duplicating its logic.

    Runs once per replay regardless of how many ontology events were seen: the
    sync is idempotent and converges on the current master epoch, so replaying
    each event separately would repeat identical work.

    Failure here is logged, not raised. A rebuild that restored every artifact
    but could not reach the master ontology is degraded, not lost, and
    `seldon verify` reports the epoch mismatch. Raising would discard a
    successful artifact replay over a recoverable condition.
    """
    # Imported lazily: seldon.commands.ontology imports from seldon.core, so a
    # module-level import here would be circular.
    from seldon.commands.ontology import _do_sync
    from seldon.config import load_project_config

    try:
        config = load_project_config(project_path)
    except Exception as exc:
        logger.warning("Ontology restore skipped — could not load config: %s", exc)
        return

    try:
        result = _do_sync(driver, database, project_path, config, emit_event=False)
    except Exception as exc:
        logger.warning(
            "Ontology restore failed: %s. Artifacts were replayed successfully; "
            "run `seldon ontology sync` to finish restoring the ontology.",
            exc,
        )
        return

    logger.info(
        "Ontology restored to epoch %s (%s terms)",
        result.get("epoch"),
        result.get("terms"),
    )


def full_replay(
    project_path: Path,
    driver: Driver,
    database: str,
) -> int:
    """
    Replay ALL events from the JSONL log into a clean Neo4j database.

    DESTRUCTIVE on the target database: all nodes and relationships are
    deleted before replay begins. Use only on project databases
    (seldon_<slug>), never on shared databases.

    Returns the number of events replayed.
    """
    events = read_events(project_path)
    if not events:
        logger.info("full_replay: no events to replay")
        return 0

    with driver.session(database=database) as session:
        # Clear the database — destructive, project DB only
        session.run("MATCH (n) DETACH DELETE n")
        logger.info("full_replay: cleared database '%s'", database)

        needs_ontology_restore = False
        for event in events:
            if _apply_event(session, event):
                needs_ontology_restore = True

        set_sync_point(session, events[-1]["event_id"])

    # After the session closes — _do_sync opens its own session.
    if needs_ontology_restore:
        _restore_ontology(project_path, driver, database)

    logger.info("full_replay: replayed %d events into '%s'", len(events), database)
    return len(events)


def incremental_sync(
    project_path: Path,
    driver: Driver,
    database: str,
) -> int:
    """
    Replay only events that have not yet been synced to Neo4j.

    Reads the current sync point from _SeldonMeta, then replays all events
    appended after that point. If no sync point exists, falls back to full_replay.

    Returns the number of new events applied.
    """
    with driver.session(database=database) as session:
        sync_point = get_sync_point(session)

    if sync_point is None:
        logger.info("incremental_sync: no sync point found, falling back to full_replay")
        return full_replay(project_path, driver, database)

    new_events = read_events_since(project_path, sync_point)
    if not new_events:
        logger.info("incremental_sync: no new events since '%s'", sync_point)
        return 0

    with driver.session(database=database) as session:
        needs_ontology_restore = False
        for event in new_events:
            if _apply_event(session, event):
                needs_ontology_restore = True
        set_sync_point(session, new_events[-1]["event_id"])

    if needs_ontology_restore:
        _restore_ontology(project_path, driver, database)

    logger.info(
        "incremental_sync: applied %d new events into '%s'", len(new_events), database
    )
    return len(new_events)
