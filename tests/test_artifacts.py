"""
Full integration tests for artifact CRUD.
Requires Neo4j (skipped if unavailable).
Validates: domain config → state machine → JSONL write → Neo4j write.
"""
import os
import uuid
import pytest
from pathlib import Path
from click.testing import CliRunner
from seldon.core.artifacts import create_artifact, update_artifact, transition_state, create_link
from seldon.core.events import read_events, event_count
from seldon.core.graph import get_artifact
from seldon.domain.loader import load_domain_config
from seldon.core.state import InvalidStateTransition
from seldon.cli import main

pytestmark = pytest.mark.usefixtures("neo4j_available")

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
NEO4J_DB = "seldon-test"

RESULT_PROPS = {"value": 0.912, "units": "accuracy", "description": "test result"}
SCRIPT_PROPS = {"name": "test_script", "path": "scripts/test.py"}


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


# ── create_artifact ───────────────────────────────────────────────────────────

def test_create_artifact_writes_jsonl_and_neo4j(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    artifact_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties=RESULT_PROPS,
        actor="human",
        authority="accepted",
    )
    # JSONL event written
    events = read_events(project_dir)
    assert len(events) == 1
    assert events[0]["event_type"] == "artifact_created"
    assert events[0]["payload"]["artifact_id"] == artifact_id

    # Neo4j node created
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, artifact_id)
    assert node is not None
    assert node["artifact_id"] == artifact_id
    assert node["value"] == 0.912


def test_create_artifact_invalid_type_raises_before_write(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    with pytest.raises(ValueError, match="Unknown artifact type"):
        create_artifact(
            project_dir=project_dir,
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
            artifact_type="Unicorn",
            properties={},
            actor="human",
            authority="accepted",
        )
    # No events written
    assert event_count(project_dir) == 0


def test_create_artifact_returns_artifact_id(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    artifact_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Script",
        properties=SCRIPT_PROPS,
        actor="ai",
        authority="proposed",
    )
    assert artifact_id is not None
    uuid.UUID(artifact_id)  # must be valid UUID


def test_create_artifact_missing_required_raises(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    with pytest.raises(ValueError, match="Missing required properties"):
        create_artifact(
            project_dir=project_dir,
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
            artifact_type="Result",
            properties={"value": 1.0},  # missing units and description
            actor="human",
            authority="accepted",
        )
    assert event_count(project_dir) == 0


# ── update_artifact ───────────────────────────────────────────────────────────

def test_update_artifact_writes_jsonl_and_neo4j(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    artifact_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={"value": 0.5, "units": "score", "description": "test result"},
        actor="human",
        authority="accepted",
    )
    update_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        artifact_id=artifact_id,
        properties={"value": 0.99, "description": "improved"},
        actor="human",
        authority="accepted",
    )
    events = read_events(project_dir)
    assert len(events) == 2
    assert events[1]["event_type"] == "artifact_updated"

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, artifact_id)
    assert node["value"] == 0.99


# ── transition_state ──────────────────────────────────────────────────────────

def test_transition_state_valid(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    artifact_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties=RESULT_PROPS,
        actor="human",
        authority="accepted",
    )
    transition_state(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=artifact_id,
        artifact_type="Result",
        current_state="proposed",
        new_state="verified",
        actor="human",
        authority="accepted",
    )
    events = read_events(project_dir)
    assert events[-1]["event_type"] == "artifact_state_changed"
    assert events[-1]["payload"]["to_state"] == "verified"

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, artifact_id)
    assert node["state"] == "verified"


def test_transition_state_invalid_raises_before_write(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    artifact_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties=RESULT_PROPS,
        actor="human",
        authority="accepted",
    )
    initial_count = event_count(project_dir)

    with pytest.raises(InvalidStateTransition):
        transition_state(
            project_dir=project_dir,
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
            artifact_id=artifact_id,
            artifact_type="Result",
            current_state="proposed",
            new_state="published",  # invalid: proposed → published not allowed
            actor="human",
            authority="accepted",
        )
    # No additional events written after failed validation
    assert event_count(project_dir) == initial_count


# ── create_link ───────────────────────────────────────────────────────────────

def test_create_link_valid(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties=RESULT_PROPS, actor="human", authority="accepted",
    )
    script_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties=SCRIPT_PROPS, actor="human", authority="accepted",
    )
    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_id,
        to_id=script_id,
        from_type="Result",
        to_type="Script",
        rel_type="generated_by",
        actor="human",
        authority="accepted",
    )
    events = read_events(project_dir)
    link_event = [e for e in events if e["event_type"] == "link_created"]
    assert len(link_event) == 1

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (a:Artifact {artifact_id: $from_id})-[r:GENERATED_BY]->(b:Artifact {artifact_id: $to_id}) RETURN r",
            from_id=result_id, to_id=script_id,
        ).single()
    assert rel is not None


def test_create_link_invalid_relationship_raises_before_write(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties=RESULT_PROPS, actor="human", authority="accepted",
    )
    script_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties=SCRIPT_PROPS, actor="human", authority="accepted",
    )
    initial_count = event_count(project_dir)

    with pytest.raises(ValueError, match="cannot originate"):
        create_link(
            project_dir=project_dir,
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
            from_id=result_id,
            to_id=script_id,
            from_type="Result",
            to_type="Script",
            rel_type="cites",  # invalid: Result cannot cite
            actor="human",
            authority="accepted",
        )
    # No link event written
    assert event_count(project_dir) == initial_count


# ── CLI helpers ───────────────────────────────────────────────────────────────

@pytest.fixture
def cli_project(tmp_path):
    """Temporary project directory with seldon.yaml pointing at the test Neo4j database."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    seldon_yaml = tmp_path / "seldon.yaml"
    seldon_yaml.write_text(
        f"project:\n  name: cli-test\n  domain: research\n"
        f"neo4j:\n  uri: {uri}\n  username: {username}\n"
        f"  password: {password}\n  database: {NEO4J_DB}\n"
    )
    return tmp_path


# ── artifact update CLI ───────────────────────────────────────────────────────

def test_artifact_update_sets_properties(
    neo4j_driver, project_dir, domain_config, clean_test_db, cli_project, monkeypatch
):
    artifact_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties=RESULT_PROPS, actor="human", authority="accepted",
    )
    monkeypatch.chdir(cli_project)
    runner = CliRunner()
    result = runner.invoke(main, [
        "artifact", "update", artifact_id,
        "-p", "description=updated description",
    ])
    assert result.exit_code == 0, result.output
    assert "Updated" in result.output

    node = get_artifact(neo4j_driver.session(database=NEO4J_DB), artifact_id)
    assert node["description"] == "updated description"


def test_artifact_update_nonexistent_fails(
    neo4j_driver, project_dir, domain_config, clean_test_db, cli_project, monkeypatch
):
    monkeypatch.chdir(cli_project)
    runner = CliRunner()
    result = runner.invoke(main, [
        "artifact", "update", "nonexistent-id-xyz",
        "-p", "description=test",
    ])
    assert result.exit_code != 0


def test_artifact_update_partial_id_resolution(
    neo4j_driver, project_dir, domain_config, clean_test_db, cli_project, monkeypatch
):
    artifact_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties=RESULT_PROPS, actor="human", authority="accepted",
    )
    monkeypatch.chdir(cli_project)
    prefix = artifact_id[:8]
    runner = CliRunner()
    result = runner.invoke(main, [
        "artifact", "update", prefix,
        "-p", "units=precision",
    ])
    assert result.exit_code == 0, result.output
    node = get_artifact(neo4j_driver.session(database=NEO4J_DB), artifact_id)
    assert node["units"] == "precision"


def test_artifact_update_ambiguous_prefix_fails(
    neo4j_driver, project_dir, domain_config, clean_test_db, cli_project, monkeypatch
):
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties=RESULT_PROPS, actor="human", authority="accepted",
    )
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties=RESULT_PROPS, actor="human", authority="accepted",
    )
    monkeypatch.chdir(cli_project)
    runner = CliRunner()
    # Empty string prefix matches all artifacts → ambiguous
    result = runner.invoke(main, [
        "artifact", "update", "",
        "-p", "description=test",
    ])
    assert result.exit_code != 0


# ── artifact show CLI ─────────────────────────────────────────────────────────

def test_artifact_show_displays_properties(
    neo4j_driver, project_dir, domain_config, clean_test_db, cli_project, monkeypatch
):
    artifact_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={**RESULT_PROPS, "description": "show-test-result"},
        actor="human", authority="accepted",
    )
    monkeypatch.chdir(cli_project)
    runner = CliRunner()
    result = runner.invoke(main, ["artifact", "show", artifact_id])
    assert result.exit_code == 0, result.output
    assert "show-test-result" in result.output
    assert artifact_id in result.output
    assert "artifact_type" in result.output


def test_artifact_show_displays_relationships(
    neo4j_driver, project_dir, domain_config, clean_test_db, cli_project, monkeypatch
):
    result_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties=RESULT_PROPS, actor="human", authority="accepted",
    )
    script_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties=SCRIPT_PROPS, actor="human", authority="accepted",
    )
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_id, to_id=script_id,
        from_type="Result", to_type="Script",
        rel_type="generated_by", actor="human", authority="accepted",
    )
    monkeypatch.chdir(cli_project)
    runner = CliRunner()
    result = runner.invoke(main, ["artifact", "show", result_id])
    assert result.exit_code == 0, result.output
    assert "GENERATED_BY" in result.output
