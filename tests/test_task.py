"""
Task tracking tests. Requires Neo4j.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact
from seldon.core.state import InvalidStateTransition

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_task(project_dir, driver, domain_config, description="Test task"):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": description}, actor="human", authority="accepted",
    )


def _make_result(project_dir, driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={}, actor="human", authority="accepted",
    )


# ── create ────────────────────────────────────────────────────────────────────

def test_create_task_has_proposed_state(neo4j_driver, project_dir, domain_config, clean_test_db):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, task_id)
    assert node["state"] == "proposed"
    assert node["description"] == "Test task"


def test_create_task_with_blocks_creates_relationship(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    result_id = _make_result(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=task_id, to_id=result_id,
        from_type="ResearchTask", to_type="Result",
        rel_type="blocks", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (t:ResearchTask {artifact_id: $tid})-[:BLOCKS]->(r:Result {artifact_id: $rid}) RETURN r",
            tid=task_id, rid=result_id,
        ).single()
    assert rel is not None


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_open_tasks_excludes_completed(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    open_id = _make_task(project_dir, neo4j_driver, domain_config, "open task")
    done_id = _make_task(project_dir, neo4j_driver, domain_config, "done task")

    # advance done_id: proposed → accepted → in_progress → completed
    for from_s, to_s in [("proposed", "accepted"), ("accepted", "in_progress"), ("in_progress", "completed")]:
        transition_state(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=done_id,
            artifact_type="ResearchTask", current_state=from_s, new_state=to_s,
            actor="human", authority="accepted",
        )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        open_tasks = session.run(
            "MATCH (t:ResearchTask) WHERE t.state IN ['proposed','accepted','in_progress','blocked'] RETURN t"
        ).data()

    open_ids = {dict(r["t"])["artifact_id"] for r in open_tasks}
    assert open_id in open_ids
    assert done_id not in open_ids


# ── update ────────────────────────────────────────────────────────────────────

def test_update_task_state_valid_transition(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)

    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=task_id,
        artifact_type="ResearchTask", current_state="proposed", new_state="accepted",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, task_id)
    assert node["state"] == "accepted"


def test_update_task_state_invalid_raises(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)

    with pytest.raises(InvalidStateTransition):
        transition_state(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            artifact_type="ResearchTask", current_state="proposed", new_state="completed",
            actor="human", authority="accepted",
        )


# ── show ──────────────────────────────────────────────────────────────────────

def test_show_task_with_blocks(neo4j_driver, project_dir, domain_config, clean_test_db):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    result_id = _make_result(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=task_id, to_id=result_id,
        from_type="ResearchTask", to_type="Result",
        rel_type="blocks", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        task_node = get_artifact(session, task_id)
        blocked_targets = session.run(
            "MATCH (t:ResearchTask {artifact_id: $id})-[:BLOCKS]->(target) RETURN target",
            id=task_id,
        ).data()

    assert task_node is not None
    assert len(blocked_targets) == 1
    assert dict(blocked_targets[0]["target"])["artifact_id"] == result_id
