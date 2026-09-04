"""Legacy event-log records: derived ids, shape repair, migration. No Neo4j.

Covers the defect recorded in the 2026-09-04 sweep: nine pre-envelope records in
`seldon-seldon-self`'s log carried no ``event_id``, `read_events` read two
``None`` values as a duplicate, and full replay — hence Recoverability — was
impossible.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.cli import main
from seldon.core.events import (
    DuplicateEventError,
    append_event,
    make_event,
    read_events,
    read_events_since,
)
from seldon.core.legacy_events import (
    ENVELOPE_KEYS,
    LEGACY_ASSIGNMENT_EVENT_TYPE,
    LEGACY_EVENT_ID_PREFIX,
    assignment_records,
    canonical_json,
    content_digest,
    is_legacy_event_id,
    is_legacy_record,
    legacy_event_id,
    make_assignment_payload,
    normalise_legacy_record,
    raw_records,
    scan_legacy_records,
    unassigned_ordinals,
    verify_assignments,
)

# The exact shape of the nine lines that head seldon-seldon-self's log:
# flat, no envelope, no event_id, no timestamp, no session_id.
LEGACY_SHAPE = {
    "event_type": "artifact_state_changed",
    "artifact_id": "6813530a-6593-4201-b494-3cd588858f19",
    "artifact_type": "AgentRole",
    "from_state": "proposed",
    "to_state": "active",
    "actor": "human",
    "authority": "accepted",
}


def legacy_line(**overrides) -> dict:
    record = dict(LEGACY_SHAPE)
    record.update(overrides)
    return record


def write_log(project_dir: Path, records) -> Path:
    path = project_dir / "seldon_events.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    return path


# ── id recipe ─────────────────────────────────────────────────────────────────

def test_derived_id_is_deterministic():
    """The same (ordinal, content) always yields the same id."""
    assert legacy_event_id(1, legacy_line()) == legacy_event_id(1, legacy_line())


def test_derived_id_ignores_key_order():
    """The parsed object is hashed, not the raw line — so key order is irrelevant.

    This is what makes the id survive any reformatting of the log file.
    """
    a = legacy_line()
    b = {k: a[k] for k in reversed(list(a))}
    assert a == b  # same mapping, different insertion order
    assert legacy_event_id(1, a) == legacy_event_id(1, b)


def test_derived_id_changes_when_content_changes():
    """Editing a legacy line changes its derived id — the tamper signal."""
    assert legacy_event_id(1, legacy_line()) != legacy_event_id(
        1, legacy_line(to_state="withdrawn")
    )


def test_derived_id_changes_when_ordinal_changes():
    """Position is carried in the id, so two identical lines never collide."""
    assert legacy_event_id(1, legacy_line()) != legacy_event_id(2, legacy_line())


def test_two_identical_lines_get_distinct_ids():
    """Uniqueness is by construction, not by hash luck."""
    ids = {legacy_event_id(n, legacy_line()) for n in (1, 2, 3)}
    assert len(ids) == 3


def test_derived_id_cannot_be_parsed_as_a_uuid():
    """A derived id is structurally un-confusable with a real uuid4."""
    derived = legacy_event_id(1, legacy_line())
    with pytest.raises(ValueError):
        uuid.UUID(derived)


def test_derived_id_shape():
    """Prefix and length are both independently sufficient to rule out uuid4."""
    derived = legacy_event_id(42, legacy_line())
    assert derived.startswith(LEGACY_EVENT_ID_PREFIX)
    assert len(derived) == 46 != len(str(uuid.uuid4()))
    assert derived.split("-")[1] == "000042"


@pytest.mark.parametrize("bad", [0, -1, True, 1.0, "1", None])
def test_derived_id_rejects_a_bad_ordinal(bad):
    """A lost ordinal must fail loudly, not be frozen into an audit record."""
    with pytest.raises(ValueError):
        legacy_event_id(bad, legacy_line())


def test_canonical_json_is_sorted_and_compact():
    text = canonical_json({"b": 1, "a": {"d": 2, "c": 3}})
    assert text == '{"a":{"c":3,"d":2},"b":1}'


def test_content_digest_is_full_sha256():
    digest = content_digest(legacy_line())
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_is_legacy_event_id_discriminates():
    assert is_legacy_event_id(legacy_event_id(1, legacy_line()))
    assert not is_legacy_event_id(str(uuid.uuid4()))
    assert not is_legacy_event_id(None)
    assert not is_legacy_event_id(7)


@pytest.mark.parametrize("record,expected", [
    (LEGACY_SHAPE, True),
    ({**LEGACY_SHAPE, "event_id": None}, True),
    ({**LEGACY_SHAPE, "event_id": ""}, True),
    ({**LEGACY_SHAPE, "event_id": str(uuid.uuid4())}, False),
])
def test_is_legacy_record(record, expected):
    assert is_legacy_record(record) is expected


# ── shape repair ──────────────────────────────────────────────────────────────

def test_normalise_moves_flat_fields_into_payload():
    """An id alone does not restore recoverability — the shape must be repaired.

    `sync._apply_event` reads ``payload["artifact_id"]`` and
    ``payload["to_state"]``. A legacy record keeps both at the top level, so a
    replay of an id-only repair raises KeyError.
    """
    out = normalise_legacy_record(1, legacy_line())
    assert out["payload"]["artifact_id"] == LEGACY_SHAPE["artifact_id"]
    assert out["payload"]["to_state"] == "active"
    assert out["payload"]["from_state"] == "proposed"
    assert out["payload"]["artifact_type"] == "AgentRole"


def test_normalise_keeps_envelope_fields_out_of_payload():
    out = normalise_legacy_record(1, legacy_line())
    assert out["actor"] == "human"
    assert out["authority"] == "accepted"
    assert out["event_type"] == "artifact_state_changed"
    assert not (set(out["payload"]) & ENVELOPE_KEYS)


def test_normalise_does_not_invent_a_timestamp():
    """The legacy writer recorded none. Synthesising one would fabricate provenance."""
    out = normalise_legacy_record(1, legacy_line())
    assert out["timestamp"] is None
    assert out["session_id"] is None


def test_normalise_flags_the_record_as_repaired():
    assert normalise_legacy_record(1, legacy_line())["legacy"] is True


def test_normalise_does_not_mutate_its_input():
    record = legacy_line()
    before = json.dumps(record, sort_keys=True)
    normalise_legacy_record(1, record)
    assert json.dumps(record, sort_keys=True) == before


def test_explicit_payload_beats_a_top_level_twin():
    """A deliberate payload wins; a stray top-level duplicate does not overwrite it."""
    record = legacy_line(payload={"artifact_id": "explicit"})
    out = normalise_legacy_record(1, record)
    assert out["payload"]["artifact_id"] == "explicit"


# ── read_events tolerance ─────────────────────────────────────────────────────

def test_read_events_no_longer_raises_on_legacy_lines(tmp_path):
    """The exact reproduction of the reported defect.

    Before the repair this raised: DuplicateEventError: Duplicate event_id
    'None' found at line 2.
    """
    write_log(tmp_path, [legacy_line(artifact_id="a1"), legacy_line(artifact_id="a2")])
    events = read_events(tmp_path)
    assert len(events) == 2
    assert events[0]["event_id"] != events[1]["event_id"]


def test_read_events_assigns_ids_matching_the_recipe(tmp_path):
    records = [legacy_line(artifact_id=f"a{i}") for i in range(1, 4)]
    write_log(tmp_path, records)
    events = read_events(tmp_path)
    for ordinal, (event, record) in enumerate(zip(events, records), start=1):
        assert event["event_id"] == legacy_event_id(ordinal, record)


def test_read_events_still_raises_on_genuinely_duplicated_uuid4(tmp_path):
    """The duplicate check must not be weakened by the legacy tolerance."""
    event = make_event("artifact_created", "human", "accepted", {"artifact_id": "x"})
    write_log(tmp_path, [event, dict(event)])
    with pytest.raises(DuplicateEventError) as exc:
        read_events(tmp_path)
    assert event["event_id"] in str(exc.value)


def test_duplicate_uuid4_still_raises_in_a_log_that_also_has_legacy_lines(tmp_path):
    """Both behaviours coexist: legacy lines tolerated, real duplicates rejected."""
    event = make_event("artifact_created", "human", "accepted", {"artifact_id": "x"})
    write_log(tmp_path, [
        legacy_line(artifact_id="a1"),
        legacy_line(artifact_id="a2"),
        event,
        dict(event),
    ])
    with pytest.raises(DuplicateEventError):
        read_events(tmp_path)


def test_a_native_event_is_untouched(tmp_path):
    """Non-legacy records pass through byte-identical — no `legacy` flag, no reshape."""
    event = make_event("artifact_created", "human", "accepted", {"artifact_id": "x"})
    write_log(tmp_path, [event])
    (read_back,) = read_events(tmp_path)
    assert read_back == event
    assert "legacy" not in read_back


def test_blank_lines_do_not_advance_the_ordinal(tmp_path):
    """read_events and raw_records must agree on which lines count."""
    path = tmp_path / "seldon_events.jsonl"
    path.write_text(
        "\n"
        + json.dumps(legacy_line(artifact_id="a1")) + "\n"
        + "\n\n"
        + json.dumps(legacy_line(artifact_id="a2")) + "\n"
    )
    events = read_events(tmp_path)
    records = raw_records(path)
    assert len(events) == len(records) == 2
    for ordinal, (event, record) in enumerate(zip(events, records), start=1):
        assert event["event_id"] == legacy_event_id(ordinal, record)


def test_malformed_lines_do_not_advance_the_ordinal(tmp_path):
    """A malformed line is skipped by both readers, so ids stay in lockstep."""
    path = tmp_path / "seldon_events.jsonl"
    path.write_text(
        json.dumps(legacy_line(artifact_id="a1")) + "\n"
        + "{not json at all\n"
        + json.dumps(legacy_line(artifact_id="a2")) + "\n"
    )
    events = read_events(tmp_path)
    records = raw_records(path)
    assert len(events) == len(records) == 2
    assert events[1]["event_id"] == legacy_event_id(2, records[1])


def test_read_events_since_accepts_a_derived_id_as_the_sync_point(tmp_path):
    """Incremental sync must be able to resume from a repaired record."""
    later = make_event("artifact_created", "human", "accepted", {"artifact_id": "x"})
    write_log(tmp_path, [legacy_line(artifact_id="a1"), later])
    events = read_events(tmp_path)
    rest = read_events_since(tmp_path, events[0]["event_id"])
    assert [e["event_id"] for e in rest] == [later["event_id"]]


def test_appending_does_not_change_earlier_derived_ids(tmp_path):
    """Ordinals of existing records are stable because the log is append-only."""
    write_log(tmp_path, [legacy_line(artifact_id="a1")])
    before = read_events(tmp_path)[0]["event_id"]
    append_event(
        tmp_path,
        make_event("artifact_created", "human", "accepted", {"artifact_id": "x"}),
    )
    assert read_events(tmp_path)[0]["event_id"] == before


def test_read_events_on_a_missing_log_is_empty(tmp_path):
    assert read_events(tmp_path) == []


def test_raw_records_on_a_missing_log_is_empty(tmp_path):
    assert raw_records(tmp_path / "seldon_events.jsonl") == []


# ── assignment records ────────────────────────────────────────────────────────

def test_scan_and_unassigned_before_migration(tmp_path):
    write_log(tmp_path, [legacy_line(artifact_id=f"a{i}") for i in range(3)])
    events = read_events(tmp_path)
    assert [r["ordinal"] for r in scan_legacy_records(events)] == [1, 2, 3]
    assert unassigned_ordinals(events) == [1, 2, 3]
    assert assignment_records(events) == {}
    assert verify_assignments(events) == []


def test_assignment_payload_carries_the_full_digest():
    payload = make_assignment_payload(3, legacy_line())
    assert payload["ordinal"] == 3
    assert payload["assigned_event_id"] == legacy_event_id(3, legacy_line())
    assert payload["content_sha256"] == content_digest(legacy_line())
    assert payload["legacy_event_type"] == "artifact_state_changed"
    assert payload["recipe_version"] == 1


def test_verify_assignments_detects_an_edited_legacy_line(tmp_path):
    """The tamper detector. The log is append-only; an edit must be visible."""
    original = legacy_line(artifact_id="a1")
    write_log(tmp_path, [original])
    append_event(
        tmp_path,
        make_event(
            LEGACY_ASSIGNMENT_EVENT_TYPE, "human", "accepted",
            make_assignment_payload(1, original),
        ),
    )
    assert verify_assignments(read_events(tmp_path)) == []

    # Now edit line 1 in place — the thing that must never happen.
    lines = (tmp_path / "seldon_events.jsonl").read_text().splitlines()
    lines[0] = json.dumps(legacy_line(artifact_id="a1", to_state="withdrawn"))
    (tmp_path / "seldon_events.jsonl").write_text("\n".join(lines) + "\n")

    problems = verify_assignments(read_events(tmp_path))
    assert len(problems) == 1
    assert "edited after its id was assigned" in problems[0]


def test_verify_assignments_detects_a_reordered_log(tmp_path):
    """An assignment pointing at a position that is no longer legacy is a rewrite."""
    native = make_event("artifact_created", "human", "accepted", {"artifact_id": "x"})
    write_log(tmp_path, [native])
    append_event(
        tmp_path,
        make_event(
            LEGACY_ASSIGNMENT_EVENT_TYPE, "human", "accepted",
            make_assignment_payload(1, legacy_line()),
        ),
    )
    problems = verify_assignments(read_events(tmp_path))
    assert len(problems) == 1
    assert "reordered or rewritten" in problems[0]


def test_a_later_assignment_supersedes_an_earlier_one_for_the_same_ordinal(tmp_path):
    record = legacy_line(artifact_id="a1")
    write_log(tmp_path, [record])
    for payload in ({"ordinal": 1, "assigned_event_id": "stale"},
                    make_assignment_payload(1, record)):
        append_event(
            tmp_path,
            make_event(LEGACY_ASSIGNMENT_EVENT_TYPE, "human", "accepted", payload),
        )
    assert verify_assignments(read_events(tmp_path)) == []


# ── migration CLI ─────────────────────────────────────────────────────────────

def test_migration_dry_run_writes_nothing(tmp_path):
    path = write_log(tmp_path, [legacy_line(artifact_id=f"a{i}") for i in range(3)])
    before = path.read_bytes()
    result = CliRunner().invoke(
        main, ["events", "migrate-legacy-ids", "--dry-run", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "3 record(s) would be appended" in result.output
    assert path.read_bytes() == before


def test_migration_appends_one_record_per_legacy_line(tmp_path):
    records = [legacy_line(artifact_id=f"a{i}") for i in range(3)]
    path = write_log(tmp_path, records)
    result = CliRunner().invoke(
        main, ["events", "migrate-legacy-ids", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output

    lines = path.read_text().splitlines()
    assert len(lines) == 6
    # The original three lines are byte-identical — nothing was rewritten.
    assert lines[:3] == [json.dumps(r) for r in records]

    events = read_events(tmp_path)
    assert unassigned_ordinals(events) == []
    assert verify_assignments(events) == []
    assert set(assignment_records(events)) == {1, 2, 3}


def test_migration_is_idempotent(tmp_path):
    path = write_log(tmp_path, [legacy_line(artifact_id="a1")])
    CliRunner().invoke(main, ["events", "migrate-legacy-ids", "--project-dir", str(tmp_path)])
    after_first = path.read_bytes()
    result = CliRunner().invoke(
        main, ["events", "migrate-legacy-ids", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "No-op" in result.output
    assert path.read_bytes() == after_first


def test_migration_on_a_clean_log_is_a_no_op(tmp_path):
    path = write_log(
        tmp_path,
        [make_event("artifact_created", "human", "accepted", {"artifact_id": "x"})],
    )
    before = path.read_bytes()
    result = CliRunner().invoke(
        main, ["events", "migrate-legacy-ids", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "No legacy records" in result.output
    assert path.read_bytes() == before


def test_migration_on_a_missing_log_is_a_no_op(tmp_path):
    result = CliRunner().invoke(
        main, ["events", "migrate-legacy-ids", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "Nothing to migrate" in result.output


def test_audit_reports_unassigned_records(tmp_path):
    write_log(tmp_path, [legacy_line(artifact_id="a1")])
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: fixture\nneo4j:\n  database: seldon-fixture\n"
    )
    result = CliRunner().invoke(
        main, ["events", "audit", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "seldon-fixture" in result.output
    assert "hold legacy records with no assignment record" in result.output
