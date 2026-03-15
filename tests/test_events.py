"""
Event store tests. NO Neo4j required — pure JSONL.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from seldon.core.events import (
    append_event,
    read_events,
    read_events_since,
    event_count,
    make_event,
    DuplicateEventError,
)


@pytest.fixture
def project_dir(tmp_path):
    """Temp directory simulating a Seldon project."""
    return tmp_path


def sample_event(**overrides):
    base = make_event(
        event_type="artifact_created",
        actor="human",
        authority="accepted",
        payload={
            "artifact_id": str(uuid.uuid4()),
            "artifact_type": "Result",
            "properties": {"value": 0.912},
            "from_state": None,
            "to_state": "proposed",
        },
    )
    base.update(overrides)
    return base


# ── append_event ──────────────────────────────────────────────────────────────

def test_append_event_creates_file(project_dir):
    event = sample_event()
    append_event(project_dir, event)
    jsonl_path = project_dir / "seldon_events.jsonl"
    assert jsonl_path.exists()


def test_append_event_is_valid_json(project_dir):
    event = sample_event()
    append_event(project_dir, event)
    jsonl_path = project_dir / "seldon_events.jsonl"
    line = jsonl_path.read_text().strip()
    parsed = json.loads(line)
    assert parsed["event_id"] == event["event_id"]


def test_append_multiple_events(project_dir):
    for _ in range(5):
        append_event(project_dir, sample_event())
    events = read_events(project_dir)
    assert len(events) == 5


def test_each_line_is_independent_json(project_dir):
    for _ in range(3):
        append_event(project_dir, sample_event())
    jsonl_path = project_dir / "seldon_events.jsonl"
    lines = jsonl_path.read_text().strip().split("\n")
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        assert "event_id" in obj


# ── read_events ───────────────────────────────────────────────────────────────

def test_read_events_empty(project_dir):
    events = read_events(project_dir)
    assert events == []


def test_read_events_preserves_order(project_dir):
    ids = []
    for _ in range(5):
        e = sample_event()
        ids.append(e["event_id"])
        append_event(project_dir, e)
    events = read_events(project_dir)
    assert [e["event_id"] for e in events] == ids


def test_read_events_skips_malformed_lines(project_dir, caplog):
    """A truncated/corrupted line is skipped with a warning, not a crash."""
    import logging
    jsonl_path = project_dir / "seldon_events.jsonl"
    good_event = sample_event()
    append_event(project_dir, good_event)
    # Inject a malformed line
    with open(jsonl_path, "a") as f:
        f.write("this is not json\n")
    another_event = sample_event()
    append_event(project_dir, another_event)

    with caplog.at_level(logging.WARNING):
        events = read_events(project_dir)

    assert len(events) == 2
    assert any("malformed" in r.message.lower() for r in caplog.records)


def test_read_events_detects_duplicate_event_ids(project_dir):
    """Duplicate event_id in the log raises DuplicateEventError."""
    event = sample_event()
    append_event(project_dir, event)
    # Manually append duplicate
    jsonl_path = project_dir / "seldon_events.jsonl"
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(event) + "\n")

    with pytest.raises(DuplicateEventError, match=event["event_id"]):
        read_events(project_dir)


# ── read_events_since ─────────────────────────────────────────────────────────

def test_read_events_since_returns_events_after_id(project_dir):
    events = [sample_event() for _ in range(5)]
    for e in events:
        append_event(project_dir, e)

    # Events after index 2 (exclusive)
    since_id = events[2]["event_id"]
    result = read_events_since(project_dir, since_id)
    assert len(result) == 2
    assert result[0]["event_id"] == events[3]["event_id"]
    assert result[1]["event_id"] == events[4]["event_id"]


def test_read_events_since_unknown_id_raises(project_dir):
    append_event(project_dir, sample_event())
    with pytest.raises(ValueError, match="not found"):
        read_events_since(project_dir, "nonexistent-id")


def test_read_events_since_last_event_returns_empty(project_dir):
    events = [sample_event() for _ in range(3)]
    for e in events:
        append_event(project_dir, e)
    result = read_events_since(project_dir, events[-1]["event_id"])
    assert result == []


# ── event_count ───────────────────────────────────────────────────────────────

def test_event_count_empty(project_dir):
    assert event_count(project_dir) == 0


def test_event_count_accurate(project_dir):
    for _ in range(7):
        append_event(project_dir, sample_event())
    assert event_count(project_dir) == 7


def test_event_count_does_not_load_events(project_dir, monkeypatch):
    """event_count should use line counting, not full JSON parsing."""
    for _ in range(3):
        append_event(project_dir, sample_event())
    # Patch json.loads to detect if it gets called
    called = []
    original = json.loads
    def patched(s):
        called.append(True)
        return original(s)
    monkeypatch.setattr(json, "loads", patched)
    count = event_count(project_dir)
    assert count == 3
    assert not called, "event_count must not call json.loads"


# ── make_event ────────────────────────────────────────────────────────────────

def test_make_event_generates_uuid(project_dir):
    e1 = make_event("artifact_created", "human", "accepted", {})
    e2 = make_event("artifact_created", "human", "accepted", {})
    assert e1["event_id"] != e2["event_id"]


def test_make_event_has_timestamp(project_dir):
    e = make_event("artifact_created", "human", "accepted", {})
    # Must be parseable ISO8601
    dt = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
    assert dt.tzinfo is not None
