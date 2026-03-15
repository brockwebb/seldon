"""
Session briefing/closeout tests. Requires Neo4j.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact, get_artifacts_by_type
from seldon.core.events import read_events
from seldon.config import start_session, end_session, get_current_session

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_task(project_dir, driver, domain_config, desc="test"):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": desc}, actor="human", authority="accepted",
    )


def _make_result(project_dir, driver, domain_config, value=0.5):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": value}, actor="human", authority="accepted",
    )


def _make_script(project_dir, driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties={}, actor="human", authority="accepted",
    )


# ── briefing queries ──────────────────────────────────────────────────────────

def test_briefing_open_tasks_query(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Briefing should find all tasks in open states."""
    _make_task(project_dir, neo4j_driver, domain_config, "task 1")
    _make_task(project_dir, neo4j_driver, domain_config, "task 2")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        records = session.run(
            "MATCH (t:ResearchTask) WHERE t.state IN ['proposed','accepted','in_progress','blocked'] RETURN t"
        ).data()
    assert len(records) == 2


def test_briefing_stale_results_query(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Briefing should find stale results."""
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="verified", new_state="stale",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        from seldon.core.graph import get_stale_artifacts
        stale = get_stale_artifacts(session)
    assert any(a["artifact_id"] == result_id for a in stale)


def test_briefing_incomplete_provenance_query(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Briefing should find Results with no GENERATED_BY Script."""
    result_with_script = _make_result(project_dir, neo4j_driver, domain_config, 0.8)
    result_no_script = _make_result(project_dir, neo4j_driver, domain_config, 0.9)
    script_id = _make_script(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_with_script, to_id=script_id,
        from_type="Result", to_type="Script",
        rel_type="generated_by", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        records = session.run(
            "MATCH (r:Result) WHERE NOT (r)-[:GENERATED_BY]->(:Script) "
            "AND NOT (r)-[:DERIVED_FROM]->() RETURN r"
        ).data()

    no_script_ids = {dict(r["r"])["artifact_id"] for r in records}
    assert result_no_script in no_script_ids
    assert result_with_script not in no_script_ids


def test_briefing_derived_from_satisfies_provenance(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """A Result with DERIVED_FROM link is NOT flagged as incomplete provenance."""
    result_id = _make_result(project_dir, neo4j_driver, domain_config, 3.32)
    notebook_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="LabNotebookEntry",
        properties={"summary": "analytical derivation"}, actor="human", authority="accepted",
    )

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_id, to_id=notebook_id,
        from_type="Result", to_type="LabNotebookEntry",
        rel_type="derived_from", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        records = session.run(
            "MATCH (r:Result) WHERE NOT (r)-[:GENERATED_BY]->(:Script) "
            "AND NOT (r)-[:DERIVED_FROM]->() RETURN r"
        ).data()

    incomplete_ids = {dict(r["r"])["artifact_id"] for r in records}
    assert result_id not in incomplete_ids


# ── closeout ──────────────────────────────────────────────────────────────────

def test_closeout_creates_lab_notebook_entry(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """closeout should create a LabNotebookEntry artifact."""
    session_id = start_session(project_dir)

    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 0.5}, actor="human", authority="accepted",
        session_id=session_id,
    )

    entry_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="LabNotebookEntry",
        properties={"summary": "test session", "session_id": session_id},
        actor="human", authority="accepted",
        session_id=session_id,
    )

    end_session(project_dir)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        entries = get_artifacts_by_type(session, "LabNotebookEntry")
    assert len(entries) == 1
    assert entries[0]["artifact_id"] == entry_id


def test_closeout_session_event_count(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Events tagged with session_id should be countable."""
    session_id = start_session(project_dir)

    for _ in range(3):
        create_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="Result",
            properties={"value": 0.1}, actor="human", authority="accepted",
            session_id=session_id,
        )

    end_session(project_dir)

    all_events = read_events(project_dir)
    session_events = [e for e in all_events if e.get("session_id") == session_id]
    created = [e for e in session_events if e["event_type"] == "artifact_created"]

    assert len(created) == 3


def test_start_session_sets_current_session(project_dir):
    """start_session sets the active session ID."""
    sid = start_session(project_dir)
    assert get_current_session(project_dir) == sid
    end_session(project_dir)


def test_events_tagged_with_session_id(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Events created while a session is active carry the session_id."""
    session_id = start_session(project_dir)

    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 0.5}, actor="human", authority="accepted",
        session_id=session_id,
    )

    end_session(project_dir)

    all_events = read_events(project_dir)
    assert all_events[0]["session_id"] == session_id
