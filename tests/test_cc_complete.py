"""
Tests for seldon cc complete and go handoff reconciliation.

Pure unit tests run without Neo4j.
Integration tests require Neo4j (marked with neo4j_available).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.commands.cc import _find_existing, _walk_to_completed, _name_from_filepath
from seldon.commands.go import _get_handoff_reconciliation
from seldon.core.artifacts import create_artifact
from seldon.domain.loader import load_domain_config

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"

pytestmark = pytest.mark.usefixtures("neo4j_available")


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_completed_task(project_dir, driver, domain_config, rel_path, name=None, desc="Test task"):
    """Helper: create a ResearchTask in completed state."""
    artifact_id = create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={
            "description": desc,
            "name": name or _name_from_filepath(rel_path),
            "source_file": rel_path,
            "completed_at": "2026-04-03T12:00:00Z",
        },
        actor="cc", authority="accepted",
    )
    _walk_to_completed(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=artifact_id, session_id=None,
    )
    return artifact_id


def _write_seldon_yaml(project_dir: Path):
    (project_dir / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        f"event_store:\n  path: seldon_events.jsonl\n"
    )


def test_cc_complete_creates_research_task(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """_walk_to_completed leaves the task in completed state with source_file set."""
    rel_path = "cc_tasks/2026-04-03_test_task.md"
    artifact_id = _make_completed_task(project_dir, neo4j_driver, domain_config, rel_path,
                                       name="test task", desc="Do some work.")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rec = session.run(
            "MATCH (t:Artifact:ResearchTask {artifact_id: $id}) RETURN t",
            id=artifact_id,
        ).single()

    node = dict(rec["t"])
    assert node["state"] == "completed"
    assert node["source_file"] == rel_path
    assert node["name"] == "test task"


def test_cc_complete_nonexistent_file(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """No artifact created for a missing source file."""
    # Verify that _find_existing returns None when nothing exists
    result = _find_existing(neo4j_driver, NEO4J_DB, "cc_tasks/does_not_exist.md")
    assert result is None


def test_cc_complete_with_note(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """--note overrides auto-extracted description."""
    rel_path = "cc_tasks/2026-04-03_noted_task.md"
    custom_note = "Custom description from --note flag."
    artifact_id = _make_completed_task(project_dir, neo4j_driver, domain_config, rel_path,
                                       desc=custom_note)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rec = session.run(
            "MATCH (t:Artifact:ResearchTask {artifact_id: $id}) RETURN t.description AS d",
            id=artifact_id,
        ).single()

    assert rec["d"] == custom_note


def test_cc_complete_idempotent(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """_find_existing detects duplicates; only one task per source_file."""
    rel_path = "cc_tasks/2026-04-03_dup_test.md"
    artifact_id = _make_completed_task(project_dir, neo4j_driver, domain_config, rel_path)

    found = _find_existing(neo4j_driver, NEO4J_DB, rel_path)
    assert found == artifact_id

    with neo4j_driver.session(database=NEO4J_DB) as session:
        count = session.run(
            "MATCH (t:Artifact:ResearchTask {source_file: $sf}) RETURN count(t) AS n",
            sf=rel_path,
        ).single()["n"]
    assert count == 1


def test_go_reconciliation_marks_completed(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Handoff text mentioning a completed CC task gets a reconciliation annotation."""
    _write_seldon_yaml(project_dir)
    rel_path = "cc_tasks/2026-04-03_reconcile_me.md"
    _make_completed_task(project_dir, neo4j_driver, domain_config, rel_path)

    handoff_text = (
        "## Open Items\n"
        f"- Still need to run {rel_path}\n"
    )

    result = _get_handoff_reconciliation(str(project_dir), handoff_text)

    assert result is not None
    assert "COMPLETED" in result
    assert "2026-04-03_reconcile_me.md" in result
    assert "✓" in result


def test_go_reconciliation_no_noise_when_clean(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Handoff with no CC task references → no reconciliation section appended."""
    _write_seldon_yaml(project_dir)

    handoff_text = "## Summary\nDid some work today. No CC tasks mentioned here.\n"
    result = _get_handoff_reconciliation(str(project_dir), handoff_text)
    assert result is None
