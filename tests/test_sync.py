"""
Sync layer tests. Requires Neo4j (skipped if unavailable).
"""
import uuid
import pytest
from seldon.core.events import append_event, make_event
from seldon.core.sync import (
    _apply_event,
    full_replay,
    incremental_sync,
    get_sync_point,
    set_sync_point,
)

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"


def sample_create_event(artifact_type="Result"):
    artifact_id = str(uuid.uuid4())
    return make_event(
        event_type="artifact_created",
        actor="human",
        authority="accepted",
        payload={
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "properties": {"value": 0.5},
            "from_state": None,
            "to_state": "proposed",
        },
    )


def test_full_replay_creates_nodes(neo4j_driver, project_dir, clean_test_db):
    events = [sample_create_event() for _ in range(3)]
    for e in events:
        append_event(project_dir, e)

    full_replay(project_dir, neo4j_driver, NEO4J_DB)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        count = session.run("MATCH (a:Artifact) RETURN count(a) AS c").single()["c"]
    assert count == 3


def test_full_replay_clears_existing_nodes(neo4j_driver, project_dir, clean_test_db):
    """full_replay replays from zero — existing nodes are replaced."""
    e1 = sample_create_event()
    append_event(project_dir, e1)
    full_replay(project_dir, neo4j_driver, NEO4J_DB)

    e2 = sample_create_event()
    append_event(project_dir, e2)
    full_replay(project_dir, neo4j_driver, NEO4J_DB)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        count = session.run("MATCH (a:Artifact) RETURN count(a) AS c").single()["c"]
    # Should be 2, not 3 (no duplicates from double replay)
    assert count == 2


def test_incremental_sync_only_new_events(neo4j_driver, project_dir, clean_test_db):
    events = [sample_create_event() for _ in range(2)]
    for e in events:
        append_event(project_dir, e)
    full_replay(project_dir, neo4j_driver, NEO4J_DB)

    new_events = [sample_create_event() for _ in range(2)]
    for e in new_events:
        append_event(project_dir, e)

    incremental_sync(project_dir, neo4j_driver, NEO4J_DB)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        count = session.run("MATCH (a:Artifact) RETURN count(a) AS c").single()["c"]
    assert count == 4


def test_sync_point_stored_and_retrieved(neo4j_driver, clean_test_db):
    with neo4j_driver.session(database=NEO4J_DB) as session:
        test_id = str(uuid.uuid4())
        set_sync_point(session, test_id)
        retrieved = get_sync_point(session)
    assert retrieved == test_id


def test_sync_point_none_when_no_meta(neo4j_driver, clean_test_db):
    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = get_sync_point(session)
    assert result is None


def test_full_replay_sets_sync_point(neo4j_driver, project_dir, clean_test_db):
    events = [sample_create_event() for _ in range(2)]
    for e in events:
        append_event(project_dir, e)
    full_replay(project_dir, neo4j_driver, NEO4J_DB)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        sync_point = get_sync_point(session)
    assert sync_point == events[-1]["event_id"]


def test_incremental_sync_no_new_events_is_noop(neo4j_driver, project_dir, clean_test_db):
    """incremental_sync with nothing new must not raise or corrupt state."""
    e = sample_create_event()
    append_event(project_dir, e)
    full_replay(project_dir, neo4j_driver, NEO4J_DB)
    incremental_sync(project_dir, neo4j_driver, NEO4J_DB)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        count = session.run("MATCH (a:Artifact) RETURN count(a) AS c").single()["c"]
    assert count == 1


# ---------------------------------------------------------------------------
# Replay round-trip: events that carry ontology state
#
# Regression guard for the defect where `seldon init` emitted `ontology_synced`
# but replay had no handler for it, so `seldon rebuild` silently dropped the
# ontology to epoch 0 and `seldon verify` then failed its Ontology check.
# Artifacts survived, which is what made it quiet.
# ---------------------------------------------------------------------------

def ontology_event(event_type="ontology_synced", epoch=3):
    return make_event(
        event_type=event_type,
        actor="seldon",
        authority="accepted",
        payload={
            "master_epoch": epoch,
            "new_terms": 105,
            "updated_terms": 0,
            "deprecated_terms": 0,
            "relationships_synced": 0,
        },
    )


def test_apply_event_signals_restore_for_ontology_events(test_db_session):
    """Ontology events cannot be projected from their payload — they must
    signal a post-loop restore rather than being silently skipped."""
    for event_type in ("ontology_synced", "ontology_ingested"):
        assert _apply_event(test_db_session, ontology_event(event_type)) is True


def test_apply_event_does_not_signal_restore_for_artifact_events(test_db_session):
    assert _apply_event(test_db_session, sample_create_event()) is False


def test_audit_only_event_is_recognised_not_warned(test_db_session, caplog):
    """paper_fix records that an edit happened but projects no graph state.
    It must not be reported as unknown — that warning is reserved for emitters
    added without a replay decision."""
    event = make_event(
        event_type="paper_fix",
        actor="human",
        authority="accepted",
        payload={"file": "sections/a.md", "find": "x", "replace": "y", "diff_chars": 0},
    )
    with caplog.at_level("WARNING"):
        assert _apply_event(test_db_session, event) is False
    assert "Unknown event_type" not in caplog.text


def test_genuinely_unknown_event_still_warns(test_db_session, caplog):
    """The unknown-type warning must survive — it is how a new emitter without
    a replay decision gets noticed."""
    event = make_event(
        event_type="totally_new_thing",
        actor="human",
        authority="accepted",
        payload={},
    )
    with caplog.at_level("WARNING"):
        assert _apply_event(test_db_session, event) is False
    assert "Unknown event_type" in caplog.text


def test_full_replay_restores_ontology_once(
    neo4j_driver, project_dir, clean_test_db, monkeypatch
):
    """Restore runs exactly once per replay no matter how many ontology events
    are in the log — the sync is idempotent and converges on master epoch."""
    calls = []
    monkeypatch.setattr(
        "seldon.core.sync._restore_ontology",
        lambda project_path, driver, database: calls.append(database),
    )

    append_event(project_dir, sample_create_event())
    for _ in range(3):
        append_event(project_dir, ontology_event())
    append_event(project_dir, sample_create_event())

    full_replay(project_dir, neo4j_driver, NEO4J_DB)

    assert calls == [NEO4J_DB], "ontology restore should run exactly once"

    with neo4j_driver.session(database=NEO4J_DB) as session:
        count = session.run("MATCH (a:Artifact) RETURN count(a) AS c").single()["c"]
    assert count == 2, "artifact replay must be unaffected by ontology events"


def test_full_replay_skips_restore_when_no_ontology_events(
    neo4j_driver, project_dir, clean_test_db, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        "seldon.core.sync._restore_ontology",
        lambda project_path, driver, database: calls.append(database),
    )
    append_event(project_dir, sample_create_event())

    full_replay(project_dir, neo4j_driver, NEO4J_DB)

    assert calls == []


def test_replay_does_not_append_to_the_event_log(
    neo4j_driver, project_dir, clean_test_db
):
    """The infinite-growth guard: restoring ontology state re-runs the sync,
    and the sync normally emits an ontology_synced event. During replay that
    emission must be suppressed, or every rebuild would add an event that
    triggers another restore on the next rebuild.

    Runs the real _restore_ontology. project_dir has no seldon.yaml, so the
    restore fails and logs — which also asserts a rebuild does not crash when
    the ontology master is unreachable.
    """
    log = project_dir / "seldon_events.jsonl"
    append_event(project_dir, sample_create_event())
    append_event(project_dir, ontology_event())
    before = log.read_text().count("\n")

    full_replay(project_dir, neo4j_driver, NEO4J_DB)

    assert log.read_text().count("\n") == before, "replay must not grow the event log"


def test_incremental_sync_also_restores_ontology(
    neo4j_driver, project_dir, clean_test_db, monkeypatch
):
    """Both replay paths need the handler, not just full_replay."""
    calls = []
    monkeypatch.setattr(
        "seldon.core.sync._restore_ontology",
        lambda project_path, driver, database: calls.append(database),
    )
    e1 = sample_create_event()
    append_event(project_dir, e1)
    full_replay(project_dir, neo4j_driver, NEO4J_DB)
    calls.clear()

    append_event(project_dir, ontology_event())
    incremental_sync(project_dir, neo4j_driver, NEO4J_DB)

    assert calls == [NEO4J_DB]
