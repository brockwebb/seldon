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


def _apply_event(session: Session, event: Dict[str, Any]) -> None:
    """
    Apply a single event to the Neo4j projection.
    Each event_type maps to one or more Cypher operations.
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

    else:
        logger.warning("Unknown event_type '%s' — skipped during sync", event_type)


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

        for event in events:
            _apply_event(session, event)

        set_sync_point(session, events[-1]["event_id"])

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
        for event in new_events:
            _apply_event(session, event)
        set_sync_point(session, new_events[-1]["event_id"])

    logger.info(
        "incremental_sync: applied %d new events into '%s'", len(new_events), database
    )
    return len(new_events)
