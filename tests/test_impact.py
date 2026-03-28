"""
Integration tests for seldon paper impact command (AD-018 B3).

Tests require Neo4j (skipped if unavailable, failed if NEO4J_PASSWORD is set
but Neo4j is unreachable — see conftest.py).

Impact traversal direction: ``dependent -[REL]-> target``.
"Impact of target" = all nodes that point TO it (directly or transitively).
So for a Result, impact includes any PaperSection that cites it,
any Figure that contains it, and any Section that references that Figure.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.core.artifacts import create_artifact, create_link
from seldon.domain.loader import load_domain_config
from seldon.cli import main

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def cli_project(tmp_path):
    """Temporary project dir with seldon.yaml pointing at the test Neo4j database."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    seldon_yaml = tmp_path / "seldon.yaml"
    seldon_yaml.write_text(
        f"project:\n  name: impact-test\n  domain: research\n"
        f"neo4j:\n  uri: {uri}\n  username: {username}\n"
        f"  password: {password}\n  database: {NEO4J_DB}\n"
    )
    return tmp_path


def _make_result(project_dir, driver, domain_config, name):
    return create_artifact(
        project_dir=project_dir,
        driver=driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={
            "name": name,
            "value": 0.95,
            "units": "accuracy",
            "description": f"test result {name}",
        },
        actor="human",
        authority="accepted",
    )


def _make_section(project_dir, driver, domain_config, name):
    return create_artifact(
        project_dir=project_dir,
        driver=driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={"name": name, "title": name.replace("_", " ").title()},
        actor="human",
        authority="accepted",
    )


def _make_figure(project_dir, driver, domain_config, name):
    return create_artifact(
        project_dir=project_dir,
        driver=driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Figure",
        properties={
            "name": name,
            "caption": f"Caption for {name}",
            "description": f"Description for {name}",
        },
        actor="human",
        authority="accepted",
    )


def _link(project_dir, driver, domain_config, from_id, to_id, from_type, to_type, rel_type):
    create_link(
        project_dir=project_dir,
        driver=driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=from_id,
        to_id=to_id,
        from_type=from_type,
        to_type=to_type,
        rel_type=rel_type,
        actor="human",
        authority="accepted",
    )


# ── tests ─────────────────────────────────────────────────────────────────────

def test_impact_shows_direct_dependents(
    neo4j_driver, project_dir, domain_config, clean_test_db, cli_project, monkeypatch
):
    """PaperSection that cites a Result appears in impact output for that Result.

    Edge: PaperSection -[CITES]-> Result
    Impact of Result = PaperSection (it cites the result, so it's a dependent).
    """
    result_id = _make_result(project_dir, neo4j_driver, domain_config, "result_accuracy_score")
    section_id = _make_section(project_dir, neo4j_driver, domain_config, "chapter_02")

    # PaperSection -[CITES]-> Result  (section depends on result)
    _link(
        project_dir, neo4j_driver, domain_config,
        from_id=section_id,
        to_id=result_id,
        from_type="PaperSection",
        to_type="Result",
        rel_type="cites",
    )

    monkeypatch.chdir(cli_project)
    runner = CliRunner()
    result = runner.invoke(main, ["paper", "impact", "result_accuracy_score"])

    assert result.exit_code == 0, result.output
    assert "chapter_02" in result.output
    assert "PaperSection" in result.output


def test_impact_shows_transitive(
    neo4j_driver, project_dir, domain_config, clean_test_db, cli_project, monkeypatch
):
    """Transitive dependents appear in the tree.

    Graph edges:
      Figure -[CONTAINS]-> Result
      PaperSection -[REFERENCES_FIGURE]-> Figure

    Impact of Result:
      - Figure (depth 1: contains the result)
      - PaperSection (depth 2: references Figure which contains the result)
    """
    result_id = _make_result(project_dir, neo4j_driver, domain_config, "transitive_result")
    figure_id = _make_figure(project_dir, neo4j_driver, domain_config, "fig_containing_result")
    section_id = _make_section(project_dir, neo4j_driver, domain_config, "section_with_figure")

    # Figure -[CONTAINS]-> Result
    _link(
        project_dir, neo4j_driver, domain_config,
        from_id=figure_id,
        to_id=result_id,
        from_type="Figure",
        to_type="Result",
        rel_type="contains",
    )

    # PaperSection -[REFERENCES_FIGURE]-> Figure
    _link(
        project_dir, neo4j_driver, domain_config,
        from_id=section_id,
        to_id=figure_id,
        from_type="PaperSection",
        to_type="Figure",
        rel_type="references_figure",
    )

    monkeypatch.chdir(cli_project)
    runner = CliRunner()
    result = runner.invoke(main, ["paper", "impact", "transitive_result"])

    assert result.exit_code == 0, result.output
    assert "fig_containing_result" in result.output
    assert "Figure" in result.output
    assert "section_with_figure" in result.output
    assert "PaperSection" in result.output


def test_impact_empty_for_leaf(
    neo4j_driver, project_dir, domain_config, clean_test_db, cli_project, monkeypatch
):
    """A Result with no dependents produces a '0 dependents' blast radius summary."""
    _make_result(project_dir, neo4j_driver, domain_config, "isolated_result")

    monkeypatch.chdir(cli_project)
    runner = CliRunner()
    result = runner.invoke(main, ["paper", "impact", "isolated_result"])

    assert result.exit_code == 0, result.output
    assert "isolated_result" in result.output
    assert "0 dependents" in result.output
