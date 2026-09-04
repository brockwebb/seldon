"""`seldon verify` checks 10 and 11: event-log readability and replay fidelity."""
from __future__ import annotations

import json
import uuid

import pytest

from seldon.commands.verify import (
    TIER_A_CHECKS,
    check_event_log,
    check_replay,
)
from seldon.core.events import append_event, make_event
from seldon.core.legacy_events import (
    LEGACY_ASSIGNMENT_EVENT_TYPE,
    make_assignment_payload,
)
from seldon.core.sync import full_replay

from tests.testdb import TEST_DATABASE

LEGACY_LINE = {
    "event_type": "artifact_state_changed",
    "artifact_id": "6813530a-6593-4201-b494-3cd588858f19",
    "artifact_type": "AgentRole",
    "from_state": "proposed",
    "to_state": "active",
    "actor": "human",
    "authority": "accepted",
}


def write_lines(project_dir, records):
    path = project_dir / "seldon_events.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    return path


def native(artifact_id=None, artifact_type="Result", state="proposed"):
    return make_event(
        event_type="artifact_created",
        actor="human",
        authority="accepted",
        payload={
            "artifact_id": artifact_id or str(uuid.uuid4()),
            "artifact_type": artifact_type,
            "properties": {"name": "n"},
            "from_state": None,
            "to_state": state,
        },
    )


# ── check 10: Event log ───────────────────────────────────────────────────────

def test_no_log_passes(tmp_path):
    result = check_event_log(tmp_path)
    assert result.symbol == "pass"
    assert "No event log" in result.summary


def test_clean_log_passes(tmp_path):
    write_lines(tmp_path, [native(), native()])
    result = check_event_log(tmp_path)
    assert result.symbol == "pass"
    assert "2 events readable" in result.summary


def test_unassigned_legacy_records_warn(tmp_path):
    """Readability is restored, so this is advisory — but it is still reported."""
    write_lines(tmp_path, [dict(LEGACY_LINE, artifact_id=f"a{i}") for i in range(3)])
    result = check_event_log(tmp_path)
    assert result.symbol == "warn"
    assert "3 legacy records have no frozen id assignment" in result.summary
    assert any("seldon events migrate-legacy-ids" in d for d in result.details)


def test_migrated_legacy_records_pass(tmp_path):
    record = dict(LEGACY_LINE)
    write_lines(tmp_path, [record])
    append_event(
        tmp_path,
        make_event(
            LEGACY_ASSIGNMENT_EVENT_TYPE, "human", "accepted",
            make_assignment_payload(1, record),
        ),
    )
    result = check_event_log(tmp_path)
    assert result.symbol == "pass"
    assert "1 legacy record(s) with frozen ids" in result.summary


def test_tampered_legacy_line_fails(tmp_path):
    """Editing an append-only line is the one thing this check exists to catch."""
    record = dict(LEGACY_LINE)
    path = write_lines(tmp_path, [record])
    append_event(
        tmp_path,
        make_event(
            LEGACY_ASSIGNMENT_EVENT_TYPE, "human", "accepted",
            make_assignment_payload(1, record),
        ),
    )
    lines = path.read_text().splitlines()
    lines[0] = json.dumps(dict(LEGACY_LINE, to_state="withdrawn"))
    path.write_text("\n".join(lines) + "\n")

    result = check_event_log(tmp_path)
    assert result.symbol == "fail"
    assert "the append-only log was edited" in result.summary


def test_unreadable_log_fails(tmp_path):
    """A genuinely duplicated uuid4 still makes the log unreadable, and is reported."""
    event = native()
    write_lines(tmp_path, [event, dict(event)])
    result = check_event_log(tmp_path)
    assert result.symbol == "fail"
    assert "full replay is impossible" in result.summary
    assert "DuplicateEventError" in result.summary


def test_event_log_check_is_not_tier_a():
    """Every finding is a property of accumulated log history, which an
    executing agent cannot clear by doing its own task correctly."""
    assert "Event log" not in TIER_A_CHECKS


# ── check 11: Replay ──────────────────────────────────────────────────────────

def test_replay_is_skipped_by_default(tmp_path):
    """`seldon verify` is a pre-commit gate; a tens-of-seconds check gets bypassed."""
    result = check_replay(None, "seldon-nonexistent", tmp_path, enabled=False)
    assert result.symbol == "pass"
    assert "seldon verify --replay" in result.summary


def test_replay_check_is_not_tier_a():
    assert "Replay" not in TIER_A_CHECKS


def test_replay_with_no_log_passes(tmp_path):
    result = check_replay(None, "seldon-nonexistent", tmp_path, enabled=True)
    assert result.symbol == "pass"
    assert "nothing to replay" in result.summary


@pytest.mark.usefixtures("neo4j_available")
def test_replay_passes_on_a_faithfully_projected_graph(
    neo4j_driver, project_dir, clean_test_db
):
    for _ in range(3):
        append_event(project_dir, native())
    full_replay(project_dir, neo4j_driver, TEST_DATABASE)

    result = check_replay(neo4j_driver, TEST_DATABASE, project_dir, enabled=True)
    assert result.symbol == "pass", result.details
    assert "reproduce the live graph exactly" in result.summary


@pytest.mark.usefixtures("neo4j_available")
def test_replay_fails_and_diagnoses_an_un_evented_write(
    neo4j_driver, project_dir, clean_test_db
):
    append_event(project_dir, native())
    full_replay(project_dir, neo4j_driver, TEST_DATABASE)
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        s.run(
            "CREATE (a:Artifact:Result {artifact_id: $id, state: 'proposed', "
            "artifact_type: 'Result'})",
            id=str(uuid.uuid4()),
        )

    result = check_replay(neo4j_driver, TEST_DATABASE, project_dir, enabled=True)
    assert result.symbol == "fail"
    assert any("unrecoverable graph state" in d for d in result.details)
    assert any("do not reconcile by hand" in d for d in result.details)


@pytest.mark.usefixtures("neo4j_available")
def test_replay_reports_an_unreachable_database_rather_than_raising(
    neo4j_driver, project_dir, clean_test_db
):
    append_event(project_dir, native())
    result = check_replay(
        neo4j_driver, "seldon-database-that-does-not-exist", project_dir, enabled=True
    )
    assert result.symbol == "fail"
    assert "could not run" in result.summary


@pytest.mark.usefixtures("neo4j_available")
def test_all_checks_include_the_two_new_ones(neo4j_driver, project_dir, clean_test_db):
    """Wiring test: the checks must actually be in the report, not just importable."""
    from seldon.commands.verify import _run_all_checks

    config = {"project": {"name": "fixture"}, "neo4j": {"database": TEST_DATABASE}}
    results = _run_all_checks(neo4j_driver, TEST_DATABASE, config, project_dir)
    names = [r.name for r in results]
    assert names[-2:] == ["Event log", "Replay"]
    assert len(results) == 11
