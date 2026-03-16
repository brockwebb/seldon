"""
Result registry tests. Requires Neo4j.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact
from seldon.core.events import read_events

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_result(project_dir, driver, domain_config, **props):
    defaults = {"value": 1.0, "units": "score", "description": "test result"}
    defaults.update(props)
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties=defaults, actor="human", authority="accepted",
    )


def _make_script(project_dir, driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties={"name": "test_script", "path": "scripts/test.py"},
        actor="human", authority="accepted",
    )


def _make_datafile(project_dir, driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="DataFile",
        properties={"name": "test_data", "path": "data/test.csv"},
        actor="human", authority="accepted",
    )


# ── register ──────────────────────────────────────────────────────────────────

def test_register_result_creates_node(neo4j_driver, project_dir, domain_config, clean_test_db):
    result_id = _make_result(project_dir, neo4j_driver, domain_config,
                             value=0.912, units="accuracy", description="test result")
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, result_id)
    assert node is not None
    assert node["value"] == 0.912
    assert node["units"] == "accuracy"
    assert node["state"] == "proposed"


def test_register_result_writes_event(neo4j_driver, project_dir, domain_config, clean_test_db):
    _make_result(project_dir, neo4j_driver, domain_config, value=0.5)
    events = read_events(project_dir)
    assert len(events) == 1
    assert events[0]["event_type"] == "artifact_created"


def test_register_with_script_id_creates_generated_by_link(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.8)
    script_id = _make_script(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_id, to_id=script_id,
        from_type="Result", to_type="Script",
        rel_type="generated_by", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (r:Result {artifact_id: $rid})-[:GENERATED_BY]->(s:Script {artifact_id: $sid}) RETURN r",
            rid=result_id, sid=script_id,
        ).single()
    assert rel is not None


def test_register_with_data_ids_creates_computed_from_links(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.7)
    data1 = _make_datafile(project_dir, neo4j_driver, domain_config)
    data2 = _make_datafile(project_dir, neo4j_driver, domain_config)

    for data_id in [data1, data2]:
        create_link(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config,
            from_id=result_id, to_id=data_id,
            from_type="Result", to_type="DataFile",
            rel_type="computed_from", actor="human", authority="accepted",
        )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rels = session.run(
            "MATCH (r:Result {artifact_id: $id})-[:COMPUTED_FROM]->(d:DataFile) RETURN d",
            id=result_id,
        ).data()
    assert len(rels) == 2


# ── verify ────────────────────────────────────────────────────────────────────

def test_verify_result_transitions_to_verified(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.9)

    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, result_id)
    assert node["state"] == "verified"


def test_verify_result_writes_state_changed_event(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.9)
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )
    events = read_events(project_dir)
    state_events = [e for e in events if e["event_type"] == "artifact_state_changed"]
    assert len(state_events) == 1
    assert state_events[0]["payload"]["to_state"] == "verified"


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_results_by_state(neo4j_driver, project_dir, domain_config, clean_test_db):
    result1 = _make_result(project_dir, neo4j_driver, domain_config, value=0.1)
    result2 = _make_result(project_dir, neo4j_driver, domain_config, value=0.2)

    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result1,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        from seldon.core.graph import get_artifacts_by_state
        proposed = get_artifacts_by_state(session, "proposed")
        verified = get_artifacts_by_state(session, "verified")

    assert len(proposed) == 1
    assert len(verified) == 1


# ── trace ─────────────────────────────────────────────────────────────────────

def test_trace_result_returns_provenance_chain(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.9)
    script_id = _make_script(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_id, to_id=script_id,
        from_type="Result", to_type="Script",
        rel_type="generated_by", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        from seldon.core.graph import get_provenance_chain
        chain = get_provenance_chain(session, result_id)

    chain_ids = {a["artifact_id"] for a in chain}
    assert script_id in chain_ids


# ── check-stale ───────────────────────────────────────────────────────────────

def test_check_stale_identifies_stale_results(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.9)
    # proposed → verified → stale
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
