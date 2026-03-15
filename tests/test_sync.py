"""
Sync layer tests. Requires Neo4j (skipped if unavailable).
"""
import uuid
import pytest
from seldon.core.events import append_event, make_event
from seldon.core.sync import (
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
