"""
Integration tests for AgentRole and Workflow artifact types (AD-014).

Requires Neo4j — tests are skipped if Neo4j is unreachable and NEO4J_PASSWORD
is not set, or failed if NEO4J_PASSWORD is set but Neo4j is not reachable.
"""
import pytest
from pathlib import Path

from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def test_create_agent_role_succeeds(neo4j_driver, project_dir, domain_config, clean_test_db):
    """AgentRole with required properties creates successfully."""
    artifact_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="AgentRole",
        properties={
            "name": "test_role",
            "display_name": "Test Role",
            "system_prompt": "You are a test role.",
        },
        actor="human", authority="accepted",
    )
    assert artifact_id is not None


def test_create_agent_role_missing_system_prompt_fails(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """AgentRole without system_prompt raises ValueError."""
    with pytest.raises(ValueError, match="Missing required properties"):
        create_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="AgentRole",
            properties={"name": "bad_role", "display_name": "Bad Role"},
            actor="human", authority="accepted",
        )


def test_agent_role_state_transitions(neo4j_driver, project_dir, domain_config, clean_test_db):
    """AgentRole proposed -> active -> stale -> active state transitions work."""
    from seldon.core.state import validate_transition
    from seldon.core.graph import change_state

    artifact_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="AgentRole",
        properties={
            "name": "transition_role",
            "display_name": "Transition Role",
            "system_prompt": "You transition.",
        },
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        validate_transition(domain_config, "AgentRole", "proposed", "active")
        change_state(session, artifact_id, "active")
        validate_transition(domain_config, "AgentRole", "active", "stale")
        change_state(session, artifact_id, "stale")
        validate_transition(domain_config, "AgentRole", "stale", "active")
        change_state(session, artifact_id, "active")


def test_create_workflow_succeeds(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Workflow with required properties creates successfully."""
    artifact_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Workflow",
        properties={
            "name": "test_workflow",
            "display_name": "Test Workflow",
            "description": "A test workflow.",
        },
        actor="human", authority="accepted",
    )
    assert artifact_id is not None


def test_includes_role_and_leads_links(neo4j_driver, project_dir, domain_config, clean_test_db):
    """includes_role and leads relationship links validate correctly."""
    role_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="AgentRole",
        properties={"name": "link_role", "display_name": "Link Role", "system_prompt": "Links."},
        actor="human", authority="accepted",
    )
    workflow_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Workflow",
        properties={"name": "link_workflow", "display_name": "Link Workflow", "description": "Links."},
        actor="human", authority="accepted",
    )

    # includes_role: Workflow -> AgentRole
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=workflow_id, to_id=role_id,
        from_type="Workflow", to_type="AgentRole",
        rel_type="includes_role", actor="human", authority="accepted",
    )

    # leads: AgentRole -> Workflow
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=role_id, to_id=workflow_id,
        from_type="AgentRole", to_type="Workflow",
        rel_type="leads", actor="human", authority="accepted",
    )
