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


# ── D2: no default path may name a developer's machine ───────────────────────
#
# `seldon init` used to emit `/Users/brock/Documents/GitHub/seldon/ontology`,
# which resolved only because a compatibility symlink happened to exist. These
# tests assert the property (defaults are DERIVED) rather than one literal.

import re

import yaml as _yaml

from seldon import paths as seldon_paths
from seldon.commands.init import init_command

REPO_ROOT = Path(__file__).parent.parent

#: Files that produce, or ship as, a default path. If one of these names a
#: user's home directory, some install of Seldon is broken.
DEFAULT_PRODUCING_SOURCES = [
    REPO_ROOT / "seldon" / "paths.py",
    REPO_ROOT / "seldon" / "commands" / "init.py",
    REPO_ROOT / "seldon" / "commands" / "go.py",
    REPO_ROOT / "scripts" / "observability_collect.py",
    REPO_ROOT / "docs" / "templates" / "seldon_yaml_template.yaml",
]

#: The retired source root. Kept as an explicit check so the specific
#: regression is named, on top of the general home-directory rule below.
RETIRED_SOURCE_ROOT = "Documents/GitHub"

_HOME_PATH_RE = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")


class TestNoHardcodedPathsInDefaults:
    @pytest.mark.parametrize(
        "source", DEFAULT_PRODUCING_SOURCES, ids=lambda p: p.name
    )
    def test_source_does_not_name_the_retired_root(self, source):
        assert source.exists(), f"scanned file is missing: {source}"
        assert RETIRED_SOURCE_ROOT not in source.read_text()

    @pytest.mark.parametrize(
        "source", DEFAULT_PRODUCING_SOURCES, ids=lambda p: p.name
    )
    def test_source_does_not_name_any_home_directory(self, source):
        found = _HOME_PATH_RE.findall(source.read_text())
        assert not found, f"{source} hardcodes a home directory: {found}"

    def test_this_projects_own_config_does_not_name_the_retired_root(self):
        """seldon.yaml is machine-specific, but must not carry the dead path."""
        assert RETIRED_SOURCE_ROOT not in (REPO_ROOT / "seldon.yaml").read_text()

    def test_shipped_template_ontology_source_is_a_placeholder(self):
        """The template must not ship one machine's real path as a default."""
        template = _yaml.safe_load(
            (REPO_ROOT / "docs" / "templates" / "seldon_yaml_template.yaml").read_text()
        )
        source = template["shared_ontology"]["source"]
        assert "/Users/" not in source
        assert "PATH" in source.upper()


class TestOntologySourceIsDerived:
    def test_candidates_are_all_under_the_installed_package(self):
        package_root = seldon_paths.package_root()
        for candidate in seldon_paths.ontology_source_candidates():
            assert candidate.is_relative_to(package_root.parent)

    def test_resolves_to_this_checkouts_ontology_tree(self, monkeypatch):
        monkeypatch.delenv(seldon_paths.ONTOLOGY_PATH_ENV, raising=False)
        resolved = seldon_paths.resolve_ontology_source()
        assert resolved is not None
        assert resolved.is_dir()
        assert resolved.name == "ontology"
        assert (resolved / "validity").is_dir()

    def test_the_parser_code_package_is_never_the_vocabulary_root(self, monkeypatch):
        """`seldon/ontology/` holds the vocabulary PARSERS, not the vocabulary.

        Deriving "package dir + 'ontology'" hits that code package, which exists
        on every install, so the resolver would always "succeed" with a
        directory containing no vocabulary at all.
        """
        monkeypatch.delenv(seldon_paths.ONTOLOGY_PATH_ENV, raising=False)
        parser_package = seldon_paths.package_root() / "ontology"
        assert parser_package.is_dir(), "fixture assumption: the code package exists"
        assert seldon_paths.is_ontology_root(parser_package) is False
        assert seldon_paths.resolve_ontology_source() != parser_package

    def test_a_directory_without_the_marker_is_not_an_ontology_root(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv(seldon_paths.ONTOLOGY_PATH_ENV, raising=False)
        fake_dist = tmp_path / "dist"
        (fake_dist / "seldon").mkdir(parents=True)
        (fake_dist / "ontology").mkdir()  # right name, no vocabulary inside
        monkeypatch.setattr(
            seldon_paths, "package_root", lambda: fake_dist / "seldon"
        )
        assert seldon_paths.resolve_ontology_source() is None

    def test_a_directory_with_the_marker_is_an_ontology_root(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv(seldon_paths.ONTOLOGY_PATH_ENV, raising=False)
        fake_dist = tmp_path / "dist"
        (fake_dist / "seldon").mkdir(parents=True)
        marker = fake_dist / "ontology" / seldon_paths.ONTOLOGY_MARKER
        marker.parent.mkdir(parents=True)
        marker.write_text("# vocabulary\n")
        monkeypatch.setattr(
            seldon_paths, "package_root", lambda: fake_dist / "seldon"
        )
        assert seldon_paths.resolve_ontology_source() == fake_dist / "ontology"

    def test_default_vocabularies_are_the_single_source_of_truth(self):
        """init writes exactly the vocabularies paths.py declares."""
        from seldon.commands import init as init_module

        assert init_module.DEFAULT_VOCABULARIES is seldon_paths.DEFAULT_VOCABULARIES
        assert seldon_paths.ONTOLOGY_MARKER == seldon_paths.DEFAULT_VOCABULARIES[0]

    def test_env_override_wins(self, tmp_path, monkeypatch):
        override = tmp_path / "my-ontology"
        override.mkdir()
        monkeypatch.setenv(seldon_paths.ONTOLOGY_PATH_ENV, str(override))
        assert seldon_paths.resolve_ontology_source() == override.resolve()

    def test_missing_env_override_fails_loudly(self, tmp_path, monkeypatch):
        monkeypatch.setenv(
            seldon_paths.ONTOLOGY_PATH_ENV, str(tmp_path / "nope")
        )
        with pytest.raises(FileNotFoundError):
            seldon_paths.resolve_ontology_source()

    def test_env_override_pointing_at_a_file_fails_loudly(self, tmp_path, monkeypatch):
        """The init default is a DIRECTORY; a file would yield an unusable path."""
        vocab = tmp_path / "VALIDITY_VOCABULARY.md"
        vocab.write_text("# vocab\n")
        monkeypatch.setenv(seldon_paths.ONTOLOGY_PATH_ENV, str(vocab))
        with pytest.raises(NotADirectoryError):
            seldon_paths.resolve_ontology_source()

    def test_wheel_layout_without_ontology_tree_returns_none(
        self, tmp_path, monkeypatch
    ):
        """A wheel install has no sibling `ontology/`; None beats a bogus path."""
        monkeypatch.delenv(seldon_paths.ONTOLOGY_PATH_ENV, raising=False)
        site_packages = tmp_path / "site-packages"
        (site_packages / "seldon").mkdir(parents=True)
        monkeypatch.setattr(
            seldon_paths, "package_root", lambda: site_packages / "seldon"
        )
        assert seldon_paths.resolve_ontology_source() is None


#: Unroutable bolt endpoint. `seldon init` writes seldon.yaml before it attempts
#: a connection, so these tests need the connection to FAIL — but they must not
#: fail it with bad credentials. Repeated bad-password attempts trip Neo4j's
#: AuthenticationRateLimit, which then refuses connections from *every* process
#: for the lockout window, poisoning the rest of the suite (AD-028 defect sweep,
#: integration pass). Port 1 is never listening, so the driver fails to connect
#: without ever presenting a credential.
UNREACHABLE_NEO4J_URI = "bolt://127.0.0.1:1"


class TestInitWritesADerivedOntologySource:
    """End-to-end: no Neo4j needed — an unreachable server makes setup warn, and
    seldon.yaml is written before the connection is attempted."""

    def _run_init(self, tmp_path, monkeypatch, name="derived-default-probe"):
        monkeypatch.setenv("NEO4J_URI", UNREACHABLE_NEO4J_URI)
        monkeypatch.delenv("SELDON_ONTOLOGY_PATH", raising=False)
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            result = runner.invoke(init_command, [name])
            config_text = Path(td, "seldon.yaml").read_text()
        return result, config_text

    def test_written_source_is_the_resolved_ontology_tree(self, tmp_path, monkeypatch):
        result, config_text = self._run_init(tmp_path, monkeypatch)
        assert result.exit_code == 0, result.output
        config = _yaml.safe_load(config_text)
        assert config["shared_ontology"]["source"] == str(
            seldon_paths.resolve_ontology_source()
        )

    def test_written_source_does_not_name_the_retired_root(self, tmp_path, monkeypatch):
        _, config_text = self._run_init(tmp_path, monkeypatch)
        assert RETIRED_SOURCE_ROOT not in config_text

    def test_written_source_exists_on_disk(self, tmp_path, monkeypatch):
        _, config_text = self._run_init(tmp_path, monkeypatch)
        config = _yaml.safe_load(config_text)
        assert Path(config["shared_ontology"]["source"]).is_dir()

    def test_env_override_is_honoured_by_init(self, tmp_path, monkeypatch):
        override = tmp_path / "override-ontology"
        override.mkdir()
        monkeypatch.setenv("NEO4J_URI", UNREACHABLE_NEO4J_URI)
        monkeypatch.setenv("SELDON_ONTOLOGY_PATH", str(override))
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            result = runner.invoke(init_command, ["env-override-probe"])
            config = _yaml.safe_load(Path(td, "seldon.yaml").read_text())
        assert result.exit_code == 0, result.output
        assert config["shared_ontology"]["source"] == str(override.resolve())

    def test_bad_env_override_aborts_before_writing_config(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("SELDON_ONTOLOGY_PATH", str(tmp_path / "does-not-exist"))
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            result = runner.invoke(init_command, ["bad-override-probe"])
            assert result.exit_code != 0
            assert not Path(td, "seldon.yaml").exists()

    def test_missing_ontology_tree_omits_the_block_and_warns(
        self, tmp_path, monkeypatch
    ):
        """A wheel install with no ontology tree must not write a dead path."""
        monkeypatch.setenv("NEO4J_URI", UNREACHABLE_NEO4J_URI)
        monkeypatch.delenv("SELDON_ONTOLOGY_PATH", raising=False)
        site_packages = tmp_path / "site-packages"
        (site_packages / "seldon").mkdir(parents=True)
        monkeypatch.setattr(
            seldon_paths, "package_root", lambda: site_packages / "seldon"
        )
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            result = runner.invoke(init_command, ["no-ontology-probe"])
            config = _yaml.safe_load(Path(td, "seldon.yaml").read_text())
        assert result.exit_code == 0, result.output
        assert "shared_ontology" not in config
        assert "SELDON_ONTOLOGY_PATH" in result.output


class TestSystemStandardsPathIsDerived:
    def test_candidates_sit_above_the_distribution_root(self):
        dist_root = seldon_paths.distribution_root()
        for candidate in seldon_paths.system_standards_candidates():
            assert candidate.parent == dist_root.parent

    def test_env_override_wins(self, tmp_path, monkeypatch):
        standards = tmp_path / "CLAUDE.md"
        standards.write_text("# standards\n")
        monkeypatch.setenv(seldon_paths.SYSTEM_STANDARDS_ENV, str(standards))
        assert seldon_paths.resolve_system_standards() == standards

    def test_missing_override_falls_through_to_derived_candidate(
        self, tmp_path, monkeypatch
    ):
        """A dangling override must not shadow a real derived candidate."""
        monkeypatch.setenv(
            seldon_paths.SYSTEM_STANDARDS_ENV, str(tmp_path / "absent.md")
        )
        resolved = seldon_paths.resolve_system_standards()
        assert resolved is None or resolved.is_file()

    def test_returns_none_when_nothing_exists(self, tmp_path, monkeypatch):
        monkeypatch.delenv(seldon_paths.SYSTEM_STANDARDS_ENV, raising=False)
        monkeypatch.setattr(
            seldon_paths, "package_root", lambda: tmp_path / "a" / "b" / "seldon"
        )
        assert seldon_paths.resolve_system_standards() is None
