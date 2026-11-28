from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import uuid
from contextlib import contextmanager
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
    """Construct a new event dict with generated event_id and timestamp.

    A caller that passes no ``session_id`` gets the id this process inherited or bound
    (`seldon.config.process_session_id`), so an MCP tool call carries its server's id and a
    dispatched session's call carries the id the dispatcher gave it. Only a process with
    neither falls back to a per-event uuid, the pre-2026-09-16 behaviour.
    """
    from seldon.config import process_session_id

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "session_id": session_id or process_session_id() or str(uuid.uuid4()),
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
    append_events(project_path, [event])


def append_events(project_path: Path, events: List[Dict[str, Any]]) -> None:
    """Append several events to the JSONL event log in one write.

    The all-or-nothing half of a command that writes more than one line
    (SEL-007): every line is serialised first, so an event that cannot be
    encoded raises before the file is touched, and the lines then go down in a
    single ``write`` followed by one fsync. A command validates everything,
    builds its events, then calls this once; a refusal at any step before it
    leaves the log exactly as it was. An empty list writes nothing.
    """
    if not events:
        return
    payload = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)
    path = _events_path(project_path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())


def read_events(project_path: Path) -> List[Dict[str, Any]]:
    """
    Read all events from the JSONL event log.

    - Skips malformed lines with a WARNING log (does not crash).
    - Repairs legacy pre-envelope records: a record with no ``event_id`` gets a
      deterministic derived one and its flat top-level fields are folded into
      ``payload``. See `seldon.core.legacy_events` for the recipe and the
      argument that a derived id can never collide with a real uuid4. The log
      file itself is never modified — the repair happens in memory on every
      read, which is what makes it safe to apply to an append-only substrate.
    - Raises DuplicateEventError if any event_id appears more than once.
    - Returns events in append order (oldest first).

    On the duplicate check and legacy records
    -----------------------------------------
    The check is *strengthened*, not weakened. Before the repair, two records
    that both lacked an id collided on ``None`` and the whole log became
    unreadable — a false positive that made full replay impossible and broke
    Recoverability. Now every record carries a distinct id and the check does
    what it was written to do: two genuinely duplicated uuid4 values still
    raise, because they are equal strings in ``seen_ids`` exactly as before.
    Nothing in this path special-cases legacy ids out of the comparison.
    """
    scope = _SCOPE.get()
    if scope is None:
        return read_events_uncached(project_path)
    return _scoped_read(scope, project_path)


def read_events_uncached(project_path: Path) -> List[Dict[str, Any]]:
    """`read_events` with no pass scope: the whole file parsed now."""
    path = _events_path(project_path)
    if not path.exists():
        return []
    with open(path, "rb") as f:
        data = f.read()
    return _parse(data, path, set(), 0, 0)[0]


def _parse(data: bytes, path: Path, seen_ids: set, ordinal: int, lineno: int) -> tuple:
    """Parse JSONL bytes as `read_events` does, continuing from `ordinal` and `lineno` with `seen_ids`.

    Returns `(events, ordinal, lineno)`. Shared by the full read and the pass scope's tail read, so a tail is parsed
    exactly as it would be in a full read (the legacy ordinal and the duplicate check included)."""
    # Imported here rather than at module scope: legacy_events documents the
    # repair in terms of this reader, and a module-level import in both
    # directions would be circular.
    from seldon.core.legacy_events import is_legacy_record, normalise_legacy_record

    events: List[Dict[str, Any]] = []
    for raw_line in data.decode("utf-8").split("\n"):
        lineno += 1
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

        # Ordinal counts parsed records only, and must stay in lockstep
        # with legacy_events.raw_records — the derived id embeds it.
        ordinal += 1

        if is_legacy_record(event):
            event = normalise_legacy_record(ordinal, event)
            logger.debug(
                "Repaired legacy event log record at line %d as %s",
                lineno,
                event["event_id"],
            )

        event_id = event.get("event_id")
        if event_id in seen_ids:
            raise DuplicateEventError(
                f"Duplicate event_id '{event_id}' found at line {lineno} "
                f"of {path}"
            )
        seen_ids.add(event_id)
        events.append(event)
    # `split("\n")` yields one empty piece after a final newline; it is not a line of the file.
    if data.endswith(b"\n") or not data:
        lineno -= 1
    return events, ordinal, lineno


# ------------------------------------------------------------------------------------------------ the pass scope
#
# SEL-062 (REVIEW-001 F-17; AD-038 ADDENDUM 17 §4). The primary store is about 20 MB and 15,000 events, and one
# dispatcher pass read it in full more than ten times. Inside `pass_scope()` the store is parsed once while it is
# unchanged. When it has only grown, and its first N bytes still hash to what was parsed, only the tail is parsed:
# the append-only property, checked the way RFC 9162's consistency check takes a log's prefix as its evidence. Any
# other change (a rebase, a union merge, a rewrite) is parsed again in full. Each caller gets its own copy of the list,
# of each event and of each payload, so a caller that mutates what it read changes nothing for the next.

_SCOPE: "contextvars.ContextVar[Optional[dict]]" = contextvars.ContextVar("seldon_events_pass_scope", default=None)


@contextmanager
def pass_scope():
    """Parse each event store at most once per unchanged state while the block runs; yields the counters
    `{full, tail, hits}`. Nested scopes share the outermost one."""
    current = _SCOPE.get()
    if current is not None:
        yield current["stats"]
        return
    state = {"stats": {"full": 0, "tail": 0, "hits": 0}, "cache": {}}
    token = _SCOPE.set(state)
    try:
        yield state["stats"]
    finally:
        _SCOPE.reset(token)


def _copy(events: list) -> list:
    return [{**e, "payload": dict(e["payload"])} if isinstance(e.get("payload"), dict) else dict(e) for e in events]


def _scoped_read(scope: dict, project_path: Path) -> List[Dict[str, Any]]:
    path = _events_path(project_path)
    key = str(path.resolve()) if path.exists() else str(path)
    cache, stats = scope["cache"], scope["stats"]
    try:
        st = path.stat()
    except FileNotFoundError:
        cache.pop(key, None)
        return []
    entry = cache.get(key)
    if entry and (st.st_size, st.st_mtime_ns, st.st_ino) == (entry["size"], entry["mtime_ns"], entry["ino"]):
        stats["hits"] += 1
        return _copy(entry["events"])
    with open(path, "rb") as f:
        data = f.read()
    if entry and len(data) > entry["size"] and _digest(data[:entry["size"]]) == entry["digest"]:
        tail = data[entry["size"]:]
        try:
            events, ordinal, lineno = _parse(tail, path, entry["seen"], entry["ordinal"], entry["lineno"])
        except DuplicateEventError:
            cache.pop(key, None)     # its `seen` set took the tail's ids; the next read parses the file afresh
            raise
        entry["events"].extend(events)
        stats["tail"] += 1
    else:
        seen: set = set()
        events, ordinal, lineno = _parse(data, path, seen, 0, 0)
        entry = {"events": events, "seen": seen}
        stats["full"] += 1
    entry.update(size=len(data), mtime_ns=st.st_mtime_ns, ino=st.st_ino, digest=_digest(data), ordinal=ordinal,
                 lineno=lineno)
    if data and not data.endswith(b"\n"):
        # A line still being written: parsed as it stands (as an uncached read would) but never extended as a tail.
        cache.pop(key, None)
    else:
        cache[key] = entry
    return _copy(entry["events"])


def _digest(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=16).hexdigest()


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
