"""
Integration tests for seldon docs check.
Requires Neo4j.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact
from seldon.commands.docs import run_docs_check

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def test_docs_check_empty_graph(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Empty graph returns zero artifacts."""
    data = run_docs_check(neo4j_driver, NEO4J_DB, domain_config)
    assert data["total_artifacts"] == 0
    assert data["fully_documented"] == 0


def test_docs_check_detects_missing_doc_properties(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Script with no doc properties is flagged as incomplete."""
    # Create a Script with only required props (no documentation props)
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties={"name": "my_script", "path": "scripts/my_script.py"},
        actor="human", authority="accepted",
    )

    data = run_docs_check(neo4j_driver, NEO4J_DB, domain_config)
    assert data["total_artifacts"] == 1
    assert data["fully_documented"] == 0
    assert "Script" in data["by_type"]
    incomplete = data["by_type"]["Script"]["incomplete"]
    assert len(incomplete) == 1
    assert "description" in incomplete[0]["missing"]
    assert "inputs" in incomplete[0]["missing"]


def test_docs_check_fully_documented_artifact(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Script with all doc properties present is marked complete."""
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties={
            "name": "full_script",
            "path": "scripts/full.py",
            "description": "Does everything",
            "inputs": "data.csv",
            "outputs": "results.json",
            "parameters": "--n 100",
            "usage": "python full.py",
            "dependencies": "numpy",
        },
        actor="human", authority="accepted",
    )

    data = run_docs_check(neo4j_driver, NEO4J_DB, domain_config)
    assert data["total_artifacts"] == 1
    assert data["fully_documented"] == 1
    assert "Script" in data["by_type"]
    assert len(data["by_type"]["Script"]["complete"]) == 1
    assert len(data["by_type"]["Script"]["incomplete"]) == 0


def test_docs_check_type_filter(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """--type filter only checks specified artifact type."""
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties={"name": "s", "path": "s.py"},
        actor="human", authority="accepted",
    )
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 1.0, "units": "score", "description": "r"},
        actor="human", authority="accepted",
    )

    data = run_docs_check(neo4j_driver, NEO4J_DB, domain_config, artifact_type_filter="Script")
    assert data["total_artifacts"] == 1
    assert "Script" in data["by_type"]
    assert "Result" not in data["by_type"]


def test_docs_check_required_vs_doc_stats(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Required properties are counted separately from documentation properties."""
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 42.0, "units": "ms", "description": "latency"},
        actor="human", authority="accepted",
    )

    data = run_docs_check(neo4j_driver, NEO4J_DB, domain_config, artifact_type_filter="Result")
    # 3 required props for Result (value, units, description) all present
    assert data["required_total"] == 3
    assert data["required_present"] == 3
    # 2 doc props for Result (interpretation, methodology_note) both missing
    assert data["doc_total"] == 2
    assert data["doc_present"] == 0


def test_docs_check_mixed_completeness(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Mixed complete/incomplete artifacts are reported correctly."""
    # Complete result
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={
            "value": 1.0, "units": "score", "description": "complete",
            "interpretation": "good", "methodology_note": "computed",
        },
        actor="human", authority="accepted",
    )
    # Incomplete result
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 2.0, "units": "score", "description": "incomplete"},
        actor="human", authority="accepted",
    )

    data = run_docs_check(neo4j_driver, NEO4J_DB, domain_config, artifact_type_filter="Result")
    assert data["total_artifacts"] == 2
    assert data["fully_documented"] == 1
    assert len(data["by_type"]["Result"]["complete"]) == 1
    assert len(data["by_type"]["Result"]["incomplete"]) == 1
