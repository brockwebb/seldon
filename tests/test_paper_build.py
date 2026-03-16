"""
Tests for seldon/paper/build.py — reference resolution and Tier 1 checks.

Integration tests require Neo4j (use neo4j_available fixture).
Unit tests mock the driver and run without Neo4j.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from seldon.core.artifacts import create_artifact, transition_state
from seldon.domain.loader import load_domain_config
from seldon.paper.build import (
    RefError,
    load_named_artifacts,
    resolve_references,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


# ---------------------------------------------------------------------------
# Integration tests (require Neo4j)
# ---------------------------------------------------------------------------

def test_resolve_references_substitutes_value(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """A verified Result with name=test_result resolves {{result:test_result:value}} to its value."""
    # 1. Create Result artifact in test DB
    result_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={"name": "test_result", "value": 42.0, "units": "score", "description": "test result"},
        actor="human",
        authority="accepted",
    )

    # Transition to verified
    transition_state(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=result_id,
        artifact_type="Result",
        current_state="proposed",
        new_state="verified",
        actor="human",
        authority="accepted",
    )

    # 2. Load artifacts dict
    artifacts = load_named_artifacts(neo4j_driver, NEO4J_DB)

    # 3. Resolve references
    resolved, errors = resolve_references(
        "{{result:test_result:value}}", artifacts, "test.md"
    )

    # 4. Assert substitution
    assert resolved == "42.0"
    # 5. Assert no errors
    assert not errors


def test_resolve_references_si01_missing(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """SI-01: {{result:nonexistent:value}} produces fatal error when artifact not in DB."""
    # Empty DB — no artifacts
    artifacts = load_named_artifacts(neo4j_driver, NEO4J_DB)

    resolved, errors = resolve_references(
        "{{result:nonexistent:value}}", artifacts, "test.md"
    )

    assert len(errors) == 1
    assert errors[0].check_id == "SI-01"
    assert errors[0].fatal is True
    # Token left in place
    assert "{{result:nonexistent:value}}" in resolved


def test_resolve_references_si02_stale(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """SI-02: Stale result produces fatal error."""
    result_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={"name": "stale_result", "value": 1.0, "units": "score", "description": "stale result"},
        actor="human",
        authority="accepted",
    )

    # Transition proposed → verified → stale
    transition_state(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=result_id,
        artifact_type="Result",
        current_state="proposed",
        new_state="verified",
        actor="human",
        authority="accepted",
    )
    transition_state(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=result_id,
        artifact_type="Result",
        current_state="verified",
        new_state="stale",
        actor="human",
        authority="accepted",
    )

    artifacts = load_named_artifacts(neo4j_driver, NEO4J_DB)
    resolved, errors = resolve_references(
        "{{result:stale_result:value}}", artifacts, "test.md"
    )

    assert len(errors) == 1
    assert errors[0].check_id == "SI-02"
    assert errors[0].fatal is True


def test_resolve_references_si03_proposed(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """SI-03: Proposed result (not yet verified) produces fatal error."""
    # Create Result — default state = proposed
    create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={"name": "proposed_result", "value": 7.5, "units": "score", "description": "proposed result"},
        actor="human",
        authority="accepted",
    )

    artifacts = load_named_artifacts(neo4j_driver, NEO4J_DB)
    resolved, errors = resolve_references(
        "{{result:proposed_result:value}}", artifacts, "test.md"
    )

    assert len(errors) == 1
    assert errors[0].check_id == "SI-03"
    assert errors[0].fatal is True


# ---------------------------------------------------------------------------
# Unit tests (no Neo4j)
# ---------------------------------------------------------------------------

def test_load_named_artifacts_keys():
    """load_named_artifacts builds correct 'reftype:name' keys."""
    # Mock driver.session returning Result with name="foo", Figure with name="bar"
    result_node = MagicMock()
    result_node.__getitem__ = lambda self, key: {
        "artifact_type": "Result",
        "name": "foo",
        "state": "verified",
        "value": 1.0,
        "artifact_id": "uuid-1",
    }[key]

    figure_node = MagicMock()
    figure_node.__getitem__ = lambda self, key: {
        "artifact_type": "Figure",
        "name": "bar",
        "state": "verified",
        "path": "figures/bar.png",
        "artifact_id": "uuid-2",
    }[key]

    # Make dict() work on the mock nodes
    result_data = {
        "artifact_type": "Result",
        "name": "foo",
        "state": "verified",
        "value": 1.0,
        "artifact_id": "uuid-1",
    }
    figure_data = {
        "artifact_type": "Figure",
        "name": "bar",
        "state": "verified",
        "path": "figures/bar.png",
        "artifact_id": "uuid-2",
    }

    mock_records = [{"a": result_data}, {"a": figure_data}]

    mock_session = MagicMock()
    mock_session.run.return_value.data.return_value = mock_records
    mock_session.__enter__ = lambda self: self
    mock_session.__exit__ = MagicMock(return_value=False)

    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    artifacts = load_named_artifacts(mock_driver, "test-db")

    assert "result:foo" in artifacts
    assert "figure:bar" in artifacts


def test_resolve_references_field_substitution():
    """Field other than value (e.g., units) resolves correctly."""
    artifacts = {
        "result:myresult": {
            "artifact_type": "Result",
            "state": "verified",
            "value": 3.32,
            "units": "bits_per_decade",
        }
    }
    resolved, errors = resolve_references(
        "{{result:myresult:units}}", artifacts, "test.md"
    )
    assert resolved == "bits_per_decade"
    assert not errors


def test_resolve_references_multiple_tokens():
    """Multiple tokens in a single text are all resolved."""
    artifacts = {
        "result:r1": {"artifact_type": "Result", "state": "verified", "value": 10.0},
        "result:r2": {"artifact_type": "Result", "state": "verified", "value": 20.0},
    }
    text = "First: {{result:r1:value}}, second: {{result:r2:value}}."
    resolved, errors = resolve_references(text, artifacts, "test.md")
    assert resolved == "First: 10.0, second: 20.0."
    assert not errors


def test_resolve_references_leaves_token_on_error():
    """On SI-01, the original token is preserved in the output text."""
    artifacts = {}
    text = "Value is {{result:missing:value}} here."
    resolved, errors = resolve_references(text, artifacts, "test.md")
    assert "{{result:missing:value}}" in resolved
    assert len(errors) == 1
    assert errors[0].check_id == "SI-01"


def test_resolve_references_si07_bib_key_missing(tmp_path):
    """SI-07: cite token with bibtex_key not in bib file produces fatal error."""
    bib_path = tmp_path / "references.bib"
    bib_path.write_text("@article{smith2020, title={Something}}\n", encoding="utf-8")

    artifacts = {
        "cite:jones2021": {
            "artifact_type": "Citation",
            "state": "verified",
            "bibtex_key": "jones2021",
            "title": "Some Paper",
        }
    }
    resolved, errors = resolve_references(
        "See {{cite:jones2021:title}}.", artifacts, "test.md", bib_path=bib_path
    )
    # bibtex_key "jones2021" is not in the bib file content → SI-07
    assert len(errors) == 1
    assert errors[0].check_id == "SI-07"
    assert errors[0].fatal is True


def test_resolve_references_si07_bib_key_present(tmp_path):
    """SI-07: cite token whose bibtex_key IS in the bib file resolves without error."""
    bib_path = tmp_path / "references.bib"
    bib_path.write_text(
        "@article{jones2021, title={Some Paper}}\n", encoding="utf-8"
    )

    artifacts = {
        "cite:jones2021": {
            "artifact_type": "Citation",
            "state": "verified",
            "bibtex_key": "jones2021",
            "title": "Some Paper",
        }
    }
    resolved, errors = resolve_references(
        "See {{cite:jones2021:title}}.", artifacts, "test.md", bib_path=bib_path
    )
    assert resolved == "See Some Paper."
    assert not errors


def test_resolve_references_si08_figure_missing(tmp_path):
    """SI-08: figure path that does not exist produces fatal error."""
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()

    artifacts = {
        "figure:fig1": {
            "artifact_type": "Figure",
            "state": "verified",
            "path": "figures/nonexistent.png",
        }
    }
    resolved, errors = resolve_references(
        "![Fig]({{figure:fig1:path}})", artifacts, "test.md", paper_dir=paper_dir
    )
    assert len(errors) == 1
    assert errors[0].check_id == "SI-08"
    assert errors[0].fatal is True


def test_resolve_references_si08_figure_exists(tmp_path):
    """SI-08: figure path that exists resolves without error."""
    paper_dir = tmp_path / "paper"
    figures_dir = paper_dir / "figures"
    figures_dir.mkdir(parents=True)
    (figures_dir / "fig1.png").write_bytes(b"")

    artifacts = {
        "figure:fig1": {
            "artifact_type": "Figure",
            "state": "verified",
            "path": "figures/fig1.png",
        }
    }
    resolved, errors = resolve_references(
        "Path: {{figure:fig1:path}}", artifacts, "test.md", paper_dir=paper_dir
    )
    assert resolved == "Path: figures/fig1.png"
    assert not errors
