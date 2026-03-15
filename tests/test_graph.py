"""
Neo4j graph layer tests.
Requires a running Neo4j instance. Tests are SKIPPED (not failed) if Neo4j is unreachable.
Uses dedicated `seldon-test` database.
"""
import uuid
import pytest
from seldon.core.graph import (
    create_artifact,
    update_artifact,
    change_state,
    create_link,
    remove_link,
    get_artifact,
    get_artifacts_by_type,
    get_artifacts_by_state,
    get_neighbors,
    get_provenance_chain,
    get_dependents,
    get_stale_artifacts,
    graph_stats,
)

pytestmark = pytest.mark.usefixtures("neo4j_available")


def make_id():
    return str(uuid.uuid4())


# ── create_artifact ───────────────────────────────────────────────────────────

def test_create_artifact_double_label(neo4j_driver, clean_test_db):
    artifact_id = make_id()
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Result", {
            "artifact_id": artifact_id,
            "state": "proposed",
            "value": 0.912,
        })
        result = session.run(
            "MATCH (a:Artifact:Result {artifact_id: $id}) RETURN a",
            id=artifact_id
        ).single()
    assert result is not None
    assert result["a"]["artifact_id"] == artifact_id


def test_create_artifact_generic_match(neo4j_driver, clean_test_db):
    artifact_id = make_id()
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Script", {
            "artifact_id": artifact_id,
            "state": "proposed",
        })
        result = session.run(
            "MATCH (a:Artifact {artifact_id: $id}) RETURN a",
            id=artifact_id
        ).single()
    assert result is not None


# ── update_artifact ───────────────────────────────────────────────────────────

def test_update_artifact(neo4j_driver, clean_test_db):
    artifact_id = make_id()
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Result", {"artifact_id": artifact_id, "state": "proposed"})
        update_artifact(session, artifact_id, {"value": 0.99, "description": "updated"})
        result = session.run(
            "MATCH (a:Artifact {artifact_id: $id}) RETURN a",
            id=artifact_id
        ).single()
    assert result["a"]["value"] == 0.99
    assert result["a"]["description"] == "updated"


# ── change_state ──────────────────────────────────────────────────────────────

def test_change_state(neo4j_driver, clean_test_db):
    artifact_id = make_id()
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Result", {"artifact_id": artifact_id, "state": "proposed"})
        change_state(session, artifact_id, "verified")
        result = session.run(
            "MATCH (a:Artifact {artifact_id: $id}) RETURN a.state AS state",
            id=artifact_id
        ).single()
    assert result["state"] == "verified"


# ── create_link / remove_link ─────────────────────────────────────────────────

def test_create_link(neo4j_driver, clean_test_db):
    result_id = make_id()
    script_id = make_id()
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Result", {"artifact_id": result_id, "state": "proposed"})
        create_artifact(session, "Script", {"artifact_id": script_id, "state": "proposed"})
        create_link(session, result_id, script_id, "GENERATED_BY", {})
        rel = session.run(
            "MATCH (a:Artifact {artifact_id: $from_id})-[r:GENERATED_BY]->(b:Artifact {artifact_id: $to_id}) RETURN r",
            from_id=result_id, to_id=script_id
        ).single()
    assert rel is not None


def test_remove_link(neo4j_driver, clean_test_db):
    result_id = make_id()
    script_id = make_id()
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Result", {"artifact_id": result_id, "state": "proposed"})
        create_artifact(session, "Script", {"artifact_id": script_id, "state": "proposed"})
        create_link(session, result_id, script_id, "GENERATED_BY", {})
        remove_link(session, result_id, script_id, "GENERATED_BY")
        rel = session.run(
            "MATCH (a:Artifact {artifact_id: $from_id})-[r:GENERATED_BY]->(b:Artifact {artifact_id: $to_id}) RETURN r",
            from_id=result_id, to_id=script_id
        ).single()
    assert rel is None


# ── get_artifact ──────────────────────────────────────────────────────────────

def test_get_artifact_exists(neo4j_driver, clean_test_db):
    artifact_id = make_id()
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Result", {"artifact_id": artifact_id, "state": "proposed"})
        artifact = get_artifact(session, artifact_id)
    assert artifact is not None
    assert artifact["artifact_id"] == artifact_id


def test_get_artifact_missing_returns_none(neo4j_driver, clean_test_db):
    with neo4j_driver.session(database="seldon-test") as session:
        result = get_artifact(session, "nonexistent-id")
    assert result is None


# ── get_artifacts_by_type / state ─────────────────────────────────────────────

def test_get_artifacts_by_type(neo4j_driver, clean_test_db):
    with neo4j_driver.session(database="seldon-test") as session:
        for _ in range(3):
            create_artifact(session, "Result", {"artifact_id": make_id(), "state": "proposed"})
        create_artifact(session, "Script", {"artifact_id": make_id(), "state": "proposed"})
        results = get_artifacts_by_type(session, "Result")
    assert len(results) == 3


def test_get_artifacts_by_state(neo4j_driver, clean_test_db):
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Result", {"artifact_id": make_id(), "state": "proposed"})
        create_artifact(session, "Result", {"artifact_id": make_id(), "state": "stale"})
        create_artifact(session, "Script", {"artifact_id": make_id(), "state": "proposed"})
        stale = get_artifacts_by_state(session, "stale")
    assert len(stale) == 1


# ── get_neighbors ─────────────────────────────────────────────────────────────

def test_get_neighbors(neo4j_driver, clean_test_db):
    result_id = make_id()
    script_id = make_id()
    data_id = make_id()
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Result", {"artifact_id": result_id, "state": "proposed"})
        create_artifact(session, "Script", {"artifact_id": script_id, "state": "proposed"})
        create_artifact(session, "DataFile", {"artifact_id": data_id, "state": "proposed"})
        create_link(session, result_id, script_id, "GENERATED_BY", {})
        create_link(session, result_id, data_id, "COMPUTED_FROM", {})
        neighbors = get_neighbors(session, result_id)
    assert len(neighbors) == 2


# ── get_provenance_chain ──────────────────────────────────────────────────────

def test_get_provenance_chain(neo4j_driver, clean_test_db):
    """Chain: section -[cites]-> result -[generated_by]-> script"""
    section_id = make_id()
    result_id = make_id()
    script_id = make_id()
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "PaperSection", {"artifact_id": section_id, "state": "proposed"})
        create_artifact(session, "Result", {"artifact_id": result_id, "state": "proposed"})
        create_artifact(session, "Script", {"artifact_id": script_id, "state": "proposed"})
        create_link(session, section_id, result_id, "CITES", {})
        create_link(session, result_id, script_id, "GENERATED_BY", {})
        chain = get_provenance_chain(session, section_id)
    chain_ids = {a["artifact_id"] for a in chain}
    assert result_id in chain_ids
    assert script_id in chain_ids


# ── get_dependents ────────────────────────────────────────────────────────────

def test_get_dependents(neo4j_driver, clean_test_db):
    """Script has dependents: result1, result2."""
    script_id = make_id()
    result1_id = make_id()
    result2_id = make_id()
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Script", {"artifact_id": script_id, "state": "proposed"})
        create_artifact(session, "Result", {"artifact_id": result1_id, "state": "proposed"})
        create_artifact(session, "Result", {"artifact_id": result2_id, "state": "proposed"})
        create_link(session, result1_id, script_id, "GENERATED_BY", {})
        create_link(session, result2_id, script_id, "GENERATED_BY", {})
        dependents = get_dependents(session, script_id)
    dep_ids = {a["artifact_id"] for a in dependents}
    assert result1_id in dep_ids
    assert result2_id in dep_ids


# ── graph_stats ───────────────────────────────────────────────────────────────

def test_graph_stats(neo4j_driver, clean_test_db):
    with neo4j_driver.session(database="seldon-test") as session:
        create_artifact(session, "Result", {"artifact_id": make_id(), "state": "proposed"})
        create_artifact(session, "Result", {"artifact_id": make_id(), "state": "verified"})
        create_artifact(session, "Script", {"artifact_id": make_id(), "state": "proposed"})
        stats = graph_stats(session)
    assert stats["total_nodes"] == 3
    assert stats["by_type"]["Result"] == 2
    assert stats["by_type"]["Script"] == 1
    assert stats["by_state"]["proposed"] == 2
    assert stats["by_state"]["verified"] == 1
