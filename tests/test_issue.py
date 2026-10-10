"""Issue artifact tests — state machine, enum validation, Eisenhower labels, relationships."""

import pytest
from pathlib import Path

from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact
from seldon.core.state import InvalidStateTransition
from seldon.core.issue_utils import (
    ISSUE_ENUMS, eisenhower_quadrant, validate_issue_enum,
)

from tests.testdb import TEST_DATABASE

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


ISSUE_PROPS = {
    "description": "Test issue",
    "issue_type": "citation_gap",
    "importance": "high",
    "urgency": "medium",
    "detection_method": "audit",
    "target": "citation",
}


def _make_issue(project_dir, driver, domain_config, **overrides):
    props = {**ISSUE_PROPS, **overrides}
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Issue",
        properties=props, actor="human", authority="accepted",
    )


def _make_paper_section(project_dir, driver, domain_config, name="test_section"):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": name, "title": "Test Section"},
        actor="human", authority="accepted",
    )


# ── State machine ────────────────────────────────────────────────────────────


def test_issue_initial_state_is_open(neo4j_driver, project_dir, domain_config, clean_test_db):
    issue_id = _make_issue(project_dir, neo4j_driver, domain_config)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, issue_id)
    assert node["state"] == "open"


def test_issue_valid_transitions(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Walk open → in_progress → resolved → verified."""
    issue_id = _make_issue(project_dir, neo4j_driver, domain_config)
    for from_s, to_s in [("open", "in_progress"), ("in_progress", "resolved"), ("resolved", "verified")]:
        transition_state(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=issue_id,
            artifact_type="Issue", current_state=from_s, new_state=to_s,
            actor="human", authority="accepted",
        )
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, issue_id)
    assert node["state"] == "verified"


def test_issue_wont_fix_path(neo4j_driver, project_dir, domain_config, clean_test_db):
    """open → wont_fix → open (escape hatch)."""
    issue_id = _make_issue(project_dir, neo4j_driver, domain_config)
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=issue_id,
        artifact_type="Issue", current_state="open", new_state="wont_fix",
        actor="human", authority="accepted",
    )
    # Escape hatch back to open
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=issue_id,
        artifact_type="Issue", current_state="wont_fix", new_state="open",
        actor="human", authority="accepted",
    )
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, issue_id)
    assert node["state"] == "open"


def test_issue_invalid_transition_raises(neo4j_driver, project_dir, domain_config, clean_test_db):
    issue_id = _make_issue(project_dir, neo4j_driver, domain_config)
    with pytest.raises(InvalidStateTransition):
        transition_state(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=issue_id,
            artifact_type="Issue", current_state="open", new_state="verified",
            actor="human", authority="accepted",
        )


def test_issue_blocked_path(neo4j_driver, project_dir, domain_config, clean_test_db):
    """in_progress → blocked → in_progress."""
    issue_id = _make_issue(project_dir, neo4j_driver, domain_config)
    for from_s, to_s in [("open", "in_progress"), ("in_progress", "blocked"), ("blocked", "in_progress")]:
        transition_state(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=issue_id,
            artifact_type="Issue", current_state=from_s, new_state=to_s,
            actor="human", authority="accepted",
        )
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, issue_id)
    assert node["state"] == "in_progress"


# ── Enum validation ──────────────────────────────────────────────────────────


def test_issue_enum_validation_accepts_valid():
    for field, values in ISSUE_ENUMS.items():
        for v in values:
            validate_issue_enum(field, v)  # Should not raise


def test_issue_enum_validation_rejects_invalid():
    with pytest.raises(ValueError, match="Invalid issue_type"):
        validate_issue_enum("issue_type", "nonexistent_type")

    with pytest.raises(ValueError, match="Invalid importance"):
        validate_issue_enum("importance", "critical")

    with pytest.raises(ValueError, match="Invalid urgency"):
        validate_issue_enum("urgency", "extreme")


# ── Eisenhower labels ────────────────────────────────────────────────────────


def test_eisenhower_all_nine_combinations():
    expected = {
        ("high", "high"): "DO NOW",
        ("high", "medium"): "DO SOON",
        ("high", "low"): "SCHEDULE",
        ("medium", "high"): "ACT SOON",
        ("medium", "medium"): "PLAN",
        ("medium", "low"): "BACKLOG",
        ("low", "high"): "BATCH",
        ("low", "medium"): "DEFER",
        ("low", "low"): "ELIMINATE",
    }
    for (imp, urg), label in expected.items():
        assert eisenhower_quadrant(imp, urg) == label


def test_eisenhower_unknown_returns_unknown():
    assert eisenhower_quadrant("extreme", "high") == "UNKNOWN"


# ── Relationships ────────────────────────────────────────────────────────────


def test_issue_affects_paper_section(neo4j_driver, project_dir, domain_config, clean_test_db):
    issue_id = _make_issue(project_dir, neo4j_driver, domain_config)
    section_id = _make_paper_section(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=issue_id, to_id=section_id,
        from_type="Issue", to_type="PaperSection",
        rel_type="affects", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (i:Issue {artifact_id: $iid})-[:AFFECTS]->(s:PaperSection {artifact_id: $sid}) RETURN s",
            iid=issue_id, sid=section_id,
        ).single()
    assert rel is not None


def test_issue_blocked_by_issue(neo4j_driver, project_dir, domain_config, clean_test_db):
    issue1 = _make_issue(project_dir, neo4j_driver, domain_config, description="Issue 1")
    issue2 = _make_issue(project_dir, neo4j_driver, domain_config, description="Issue 2")

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=issue1, to_id=issue2,
        from_type="Issue", to_type="Issue",
        rel_type="blocked_by", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (a:Issue {artifact_id: $aid})-[:BLOCKED_BY]->(b:Issue {artifact_id: $bid}) RETURN b",
            aid=issue1, bid=issue2,
        ).single()
    assert rel is not None


# ── The CLI a job drives (ai-readiness-kg daily suite, 2026-10-09 task decision 6) ──────────


@pytest.fixture
def issue_cli_project(tmp_path, monkeypatch):
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: t\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


_CREATE = ["create", "--description", "d1", "--type", "merge_blocked", "--importance", "high",
           "--urgency", "high", "--detection", "build_failure", "--target", "structure"]


@pytest.mark.usefixtures("clean_test_db")
def test_a_named_issue_lists_as_json_and_takes_a_new_description(issue_cli_project):
    import json
    from click.testing import CliRunner
    from seldon.commands.issue import issue_group

    r = CliRunner().invoke(issue_group, _CREATE + ["--name", "daily suite red: t.py::x"])
    assert r.exit_code == 0, r.output
    assert "name: daily suite red: t.py::x" in r.output
    r = CliRunner().invoke(issue_group, ["list", "--open", "--type", "merge_blocked", "--json"])
    assert r.exit_code == 0, r.output
    rows = json.loads(r.output)
    assert [i["name"] for i in rows] == ["daily suite red: t.py::x"]
    iid = rows[0]["artifact_id"]
    r = CliRunner().invoke(issue_group, ["update", iid, "--description", "d1; red again"])
    assert r.exit_code == 0, r.output
    rows = json.loads(CliRunner().invoke(
        issue_group, ["list", "--open", "--type", "merge_blocked", "--json"]).output)
    assert rows[0]["description"] == "d1; red again" and rows[0]["state"] == "open"


@pytest.mark.usefixtures("clean_test_db")
def test_an_issue_created_without_a_name_has_none(issue_cli_project):
    import json
    from click.testing import CliRunner
    from seldon.commands.issue import issue_group

    assert CliRunner().invoke(issue_group, _CREATE).exit_code == 0
    rows = json.loads(CliRunner().invoke(issue_group, ["list", "--json"]).output)
    assert len(rows) == 1 and "name" not in rows[0]
