"""
Tests for MCP tools in mcp_server.py.

Requires Neo4j.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.core.artifacts import create_artifact
from seldon.domain.loader import load_domain_config
from seldon.mcp_server import (
    seldon_task_create,
    seldon_task_update,
    seldon_task_list,
    seldon_issue_create,
    seldon_issue_update,
    seldon_cc_complete,
    seldon_cc_register,
    seldon_query,
)

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _write_seldon_yaml(project_dir: Path):
    (project_dir / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        f"event_store:\n  path: seldon_events.jsonl\n"
    )

def test_task_create_via_mcp(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """seldon_task_create creates a ResearchTask in proposed state."""
    _write_seldon_yaml(project_dir)
    result = seldon_task_create(
        description="Test task via MCP",
        project_dir=str(project_dir),
    )
    assert "Created ResearchTask" in result
    assert "proposed" in result

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rec = session.run(
            "MATCH (t:Artifact:ResearchTask {description: 'Test task via MCP'}) RETURN t"
        ).single()
    assert rec is not None
    assert dict(rec["t"])["state"] == "proposed"


def test_task_update_state(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """seldon_task_update transitions a task from proposed to accepted."""
    _write_seldon_yaml(project_dir)

    artifact_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": "Task to update"},
        actor="test", authority="accepted",
    )

    result = seldon_task_update(
        task_id=artifact_id,
        state="accepted",
        project_dir=str(project_dir),
    )
    assert "accepted" in result

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rec = session.run(
            "MATCH (t:Artifact:ResearchTask {artifact_id: $id}) RETURN t.state AS s",
            id=artifact_id,
        ).single()
    assert rec["s"] == "accepted"


def test_task_list_filters(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """seldon_task_list with 'open' filter includes proposed, excludes completed."""
    from seldon.core.artifacts import walk_to_completed

    _write_seldon_yaml(project_dir)

    # Create one open task
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": "Open task"},
        actor="test", authority="accepted",
    )

    # Create one completed task
    completed_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": "Done task", "source_file": "cc_tasks/done.md"},
        actor="test", authority="accepted",
    )
    walk_to_completed(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=completed_id,
        current_state="proposed", session_id=None,
    )

    result = seldon_task_list(project_dir=str(project_dir), state_filter="open")
    assert "Open task" in result
    assert "Done task" not in result


def test_issue_create_via_mcp(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """seldon_issue_create creates an Issue with correct Eisenhower quadrant."""
    _write_seldon_yaml(project_dir)

    result = seldon_issue_create(
        name="test issue",
        description="Something is broken",
        importance="high",
        urgency="high",
        project_dir=str(project_dir),
    )
    assert "Created Issue" in result
    assert "DO NOW" in result

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rec = session.run(
            "MATCH (i:Artifact:Issue {name: 'test issue'}) RETURN i"
        ).single()
    assert rec is not None
    node = dict(rec["i"])
    assert node["importance"] == "high"
    assert node["urgency"] == "high"


def test_cc_complete_via_mcp(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """seldon_cc_complete marks a CC task file as completed in the graph."""
    _write_seldon_yaml(project_dir)

    cc_file = project_dir / "cc_tasks" / "2026-04-03_mcp_test.md"
    cc_file.parent.mkdir(parents=True, exist_ok=True)
    cc_file.write_text("# CC Task: MCP Test\n\nTest task for MCP.\n")

    result = seldon_cc_complete(
        filepath="cc_tasks/2026-04-03_mcp_test.md",
        project_dir=str(project_dir),
    )
    assert "completed" in result
    assert "mcp test" in result

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rec = session.run(
            "MATCH (t:Artifact:ResearchTask {source_file: 'cc_tasks/2026-04-03_mcp_test.md'}) "
            "RETURN t.state AS s"
        ).single()
    assert rec["s"] == "completed"


def test_cc_register_via_mcp(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """seldon_cc_register creates a proposed ResearchTask for a CC task file."""
    _write_seldon_yaml(project_dir)

    cc_file = project_dir / "cc_tasks" / "2026-04-03_register_test.md"
    cc_file.parent.mkdir(parents=True, exist_ok=True)
    cc_file.write_text("# CC Task: Register Test\n\nA task to register.\n")

    result = seldon_cc_register(
        filepath="cc_tasks/2026-04-03_register_test.md",
        project_dir=str(project_dir),
    )
    assert "proposed" in result
    assert "register test" in result

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rec = session.run(
            "MATCH (t:Artifact:ResearchTask {source_file: 'cc_tasks/2026-04-03_register_test.md'}) "
            "RETURN t.state AS s"
        ).single()
    assert rec["s"] == "proposed"


def test_query_read_only(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """seldon_query executes a read query and returns formatted results."""
    _write_seldon_yaml(project_dir)

    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": "Queryable task"},
        actor="test", authority="accepted",
    )

    result = seldon_query(
        cypher="MATCH (t:Artifact:ResearchTask) RETURN t.description AS d",
        project_dir=str(project_dir),
    )
    assert "Queryable task" in result
    assert "result" in result.lower()


def test_query_rejects_writes(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """seldon_query returns an error for write operations without executing them."""
    _write_seldon_yaml(project_dir)

    for query in [
        "CREATE (n:Foo)",
        "MERGE (n:Foo {id: '1'})",
        "MATCH (n) SET n.x = 1",
        "MATCH (n) DELETE n",
    ]:
        result = seldon_query(cypher=query, project_dir=str(project_dir))
        assert "Error" in result, f"Expected error for: {query}"
        assert "write" in result.lower()


def test_query_uses_project_database(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """seldon_query hits the configured project database (NEO4J_DB), not a hardcoded one."""
    _write_seldon_yaml(project_dir)

    # Write a unique artifact to NEO4J_DB
    unique_desc = "unique-db-marker-artifact-xyz"
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": unique_desc},
        actor="test", authority="accepted",
    )

    result = seldon_query(
        cypher=f"MATCH (t:Artifact:ResearchTask {{description: '{unique_desc}'}}) RETURN t.description AS d",
        project_dir=str(project_dir),
    )
    assert unique_desc in result
