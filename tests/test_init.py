"""
Tests for `seldon init` template-driven bootstrap and database-emptiness guard.

Unit tests for helpers (`_apply_template`, `_database_has_artifacts`) require
Neo4j. CLI tests for `--list-templates` and unknown-template errors do not.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.domain.loader import load_domain_config

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


# ── CLI tests that need no Neo4j ─────────────────────────────────────────────

class TestListTemplatesFlag:
    def test_list_templates_exits_cleanly(self):
        from seldon.commands.init import init_command
        runner = CliRunner()
        result = runner.invoke(init_command, ["--list-templates"])
        assert result.exit_code == 0
        assert "blank" in result.output
        assert "paper" in result.output

    def test_list_templates_shows_descriptions(self):
        from seldon.commands.init import init_command
        runner = CliRunner()
        result = runner.invoke(init_command, ["--list-templates"])
        assert "Research paper manuscript" in result.output or "paper" in result.output


class TestUnknownTemplateFailsEarly:
    def test_unknown_template_exits_nonzero_without_touching_fs(self, tmp_path):
        """Unknown template must fail BEFORE any filesystem or Neo4j side effects."""
        from seldon.commands.init import init_command
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                init_command,
                ["test-project", "--template", "nonexistent-xyz"],
            )
            assert result.exit_code != 0
            assert "nonexistent-xyz" in result.output
            # Must NOT have written seldon.yaml before failing.
            assert not Path("seldon.yaml").exists()


# ── Neo4j-dependent helper tests ─────────────────────────────────────────────

pytestmark_neo4j = pytest.mark.usefixtures("neo4j_available")


@pytest.mark.usefixtures("neo4j_available")
class TestApplyTemplate:
    def test_blank_applies_zero_tasks(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        from seldon.commands.init import _apply_template
        from seldon.templates.loader import load_template

        _apply_template(
            neo4j_driver, NEO4J_DB, project_dir, load_template("blank")
        )

        with neo4j_driver.session(database=NEO4J_DB) as s:
            count = s.run(
                "MATCH (t:Artifact:ResearchTask) RETURN count(t) AS n"
            ).single()["n"]
        assert count == 0

    def test_paper_applies_five_tasks_with_setup_prefixes(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        from seldon.commands.init import _apply_template
        from seldon.templates.loader import load_template

        _apply_template(
            neo4j_driver, NEO4J_DB, project_dir, load_template("paper")
        )

        with neo4j_driver.session(database=NEO4J_DB) as s:
            descriptions = sorted(
                r["d"]
                for r in s.run(
                    "MATCH (t:Artifact:ResearchTask) RETURN t.description AS d"
                )
            )

        assert len(descriptions) == 5
        assert all(d.startswith("SETUP-") for d in descriptions)

    def test_paper_tasks_start_in_proposed_state(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        from seldon.commands.init import _apply_template
        from seldon.templates.loader import load_template

        _apply_template(
            neo4j_driver, NEO4J_DB, project_dir, load_template("paper")
        )

        with neo4j_driver.session(database=NEO4J_DB) as s:
            states = [
                r["s"]
                for r in s.run(
                    "MATCH (t:Artifact:ResearchTask) RETURN t.state AS s"
                )
            ]

        assert states and all(s == "proposed" for s in states)


@pytest.mark.usefixtures("neo4j_available")
class TestDatabaseEmptinessCheck:
    def test_empty_database_reports_empty(
        self, neo4j_driver, clean_test_db
    ):
        from seldon.commands.init import _database_has_artifacts
        assert _database_has_artifacts(neo4j_driver, NEO4J_DB) is False

    def test_database_with_artifact_reports_non_empty(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        from seldon.commands.init import _database_has_artifacts
        from seldon.core.artifacts import create_artifact

        create_artifact(
            project_dir=project_dir,
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
            artifact_type="ResearchTask",
            properties={"description": "pre-existing"},
            actor="human",
            authority="accepted",
        )
        assert _database_has_artifacts(neo4j_driver, NEO4J_DB) is True
