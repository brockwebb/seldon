from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EVENTS_FILENAME = "seldon_events.jsonl"


class DuplicateEventError(Exception):
    """Raised when the event log contains duplicate event_id values."""
    pass


def make_event(
    event_type: str,
    actor: str,
    authority: str,
    payload: Dict[str, Any],
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Construct a new event dict with generated event_id and timestamp."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "session_id": session_id or str(uuid.uuid4()),
        "actor": actor,
        "authority": authority,
        "payload": payload,
    }


def _events_path(project_path: Path) -> Path:
    return Path(project_path) / EVENTS_FILENAME


def append_event(project_path: Path, event: Dict[str, Any]) -> None:
    """
    Append a single event to the JSONL event log.

    Writes the JSON line atomically as a single write call followed by fsync.
    The event log is created if it does not exist.
    """
    path = _events_path(project_path)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def read_events(project_path: Path) -> List[Dict[str, Any]]:
    """
    Read all events from the JSONL event log.

    - Skips malformed lines with a WARNING log (does not crash).
    - Raises DuplicateEventError if any event_id appears more than once.
    - Returns events in append order (oldest first).
    """
    path = _events_path(project_path)
    if not path.exists():
        return []

    events: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(
                    "Malformed line in event log (line %d, skipped): %r",
                    lineno,
                    line[:120],
                )
                continue

            event_id = event.get("event_id")
            if event_id in seen_ids:
                raise DuplicateEventError(
                    f"Duplicate event_id '{event_id}' found at line {lineno} "
                    f"of {path}"
                )
            seen_ids.add(event_id)
            events.append(event)

    return events


def read_events_since(
    project_path: Path, last_event_id: str
) -> List[Dict[str, Any]]:
    """
    Return all events that were appended AFTER the event with last_event_id.

    Raises ValueError if last_event_id is not found in the log.
    """
    all_events = read_events(project_path)
    for i, event in enumerate(all_events):
        if event["event_id"] == last_event_id:
            return all_events[i + 1:]
    raise ValueError(
        f"Sync point event_id '{last_event_id}' not found in event log at {project_path}"
    )


def event_count(project_path: Path) -> int:
    """
    Return the number of events in the log using fast line counting.

    Does NOT parse JSON. Empty lines are excluded from the count.
    """
    path = _events_path(project_path)
    if not path.exists():
        return 0
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count
