"""
Tests for seldon verify command (AD-018 B4).

Requires Neo4j. Uses seldon-test database (cleaned before each test).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from seldon.commands.verify import (
    check_blocking_tasks,
    check_file_hashes,
    check_references,
    check_stale_artifacts,
    check_unregistered_files,
    _fix_unregistered_files,
    _sha256,
)
from seldon.core.artifacts import create_artifact, transition_state, create_link
from seldon.domain.loader import load_domain_config

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_section(neo4j_driver, project_dir, domain_config, name, file_path, content):
    """Helper: write file and create PaperSection artifact with content_hash."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    try:
        rel_path = str(path.relative_to(project_dir))
    except ValueError:
        rel_path = str(path)

    aid = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={
            "name": name,
            "title": name.replace("_", " ").title(),
            "file_path": rel_path,
            "content_hash": content_hash,
        },
        actor="test",
        authority="accepted",
    )
    return aid


# ---------------------------------------------------------------------------
# Test 1: Clean project — everything passes
# ---------------------------------------------------------------------------

def test_verify_clean_project(neo4j_driver, project_dir, domain_config, clean_test_db):
    """No stale artifacts, all files synced, no unregistered files -> all pass."""
    # Create a section file and register it
    sections_dir = project_dir / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    _make_section(
        neo4j_driver, project_dir, domain_config,
        "chapter_01",
        str(sections_dir / "chapter-01.md"),
        "# Introduction\nSome content.\n",
    )

    r_hashes = check_file_hashes(neo4j_driver, NEO4J_DB, project_dir)
    assert r_hashes.symbol == "pass"

    r_stale = check_stale_artifacts(neo4j_driver, NEO4J_DB)
    assert r_stale.symbol == "pass"

    r_unreg = check_unregistered_files(neo4j_driver, NEO4J_DB, project_dir)
    assert r_unreg.symbol == "pass"

    r_blocking = check_blocking_tasks(neo4j_driver, NEO4J_DB)
    assert r_blocking.symbol == "pass"


# ---------------------------------------------------------------------------
# Test 2: Detects modified file
# ---------------------------------------------------------------------------

def test_verify_detects_modified_file(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Create artifact with content_hash, change file on disk -> hash mismatch."""
    sections_dir = project_dir / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    file_path = sections_dir / "chapter-02.md"

    _make_section(
        neo4j_driver, project_dir, domain_config,
        "chapter_02",
        str(file_path),
        "# Methods\nOriginal content.\n",
    )

    # Modify the file after registration
    file_path.write_text("# Methods\nModified content — now different.\n", encoding="utf-8")

    result = check_file_hashes(neo4j_driver, NEO4J_DB, project_dir)
    assert result.symbol == "fail"
    assert "chapter-02.md" in result.summary


# ---------------------------------------------------------------------------
# Test 3: Detects stale artifacts
# ---------------------------------------------------------------------------

def test_verify_detects_stale_artifacts(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Artifact in stale state -> reported with warning."""
    result_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={
            "name": "metric_stale",
            "value": 0.5,
            "units": "fraction",
            "description": "A stale metric",
        },
        actor="test",
        authority="accepted",
    )
    transition_state(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=result_id,
        artifact_type="Result",
        current_state="proposed",
        new_state="verified",
        actor="test",
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
        actor="test",
        authority="accepted",
    )

    result = check_stale_artifacts(neo4j_driver, NEO4J_DB)
    assert result.symbol == "warn"
    assert "metric_stale" in result.summary


# ---------------------------------------------------------------------------
# Test 4: Detects unregistered file
# ---------------------------------------------------------------------------

def test_verify_detects_unregistered_file(neo4j_driver, project_dir, domain_config, clean_test_db):
    """File in paper/sections/ without a PaperSection artifact -> reported."""
    sections_dir = project_dir / "paper" / "sections"
    sections_dir.mkdir(parents=True)

    # Register one section
    _make_section(
        neo4j_driver, project_dir, domain_config,
        "chapter_01",
        str(sections_dir / "chapter-01.md"),
        "# Intro\n",
    )

    # Add an unregistered file
    (sections_dir / "chapter-99.md").write_text("# Unregistered\n", encoding="utf-8")

    result = check_unregistered_files(neo4j_driver, NEO4J_DB, project_dir)
    assert result.symbol == "fail"
    assert "chapter-99.md" in result.summary


# ---------------------------------------------------------------------------
# Test 5: --fix syncs files (mocked subprocess)
# ---------------------------------------------------------------------------

def test_verify_fix_syncs_files(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Modified file + --fix -> paper sync is invoked via subprocess."""
    sections_dir = project_dir / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    file_path = sections_dir / "chapter-03.md"

    _make_section(
        neo4j_driver, project_dir, domain_config,
        "chapter_03",
        str(file_path),
        "# Results\nOriginal.\n",
    )
    file_path.write_text("# Results\nChanged.\n", encoding="utf-8")

    # Confirm issue is detected
    r = check_file_hashes(neo4j_driver, NEO4J_DB, project_dir)
    assert r.symbol == "fail"
    assert r.fixable is True

    # Mock subprocess to verify the fix call
    with patch("seldon.commands.verify.subprocess.run") as mock_run:
        from seldon.commands.verify import _fix_file_hashes
        _fix_file_hashes(project_dir)
        mock_run.assert_called_once()
        args = mock_run.call_args
        cmd = args[0][0] if args[0] else args[1].get("args", [])
        assert "paper" in cmd
        assert "sync" in cmd


# ---------------------------------------------------------------------------
# Test 6: --fix registers unregistered files
# ---------------------------------------------------------------------------

def test_verify_fix_registers_files(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Unregistered file + fix -> artifact is created in the graph."""
    sections_dir = project_dir / "paper" / "sections"
    sections_dir.mkdir(parents=True)

    new_file = sections_dir / "chapter-new.md"
    new_file.write_text("# New Chapter\nContent.\n", encoding="utf-8")

    # Detect the unregistered file
    r = check_unregistered_files(neo4j_driver, NEO4J_DB, project_dir)
    assert r.symbol == "fail"

    # Fix: register it
    count = _fix_unregistered_files(
        neo4j_driver, NEO4J_DB, project_dir, domain_config, r.details
    )
    assert count == 1

    # Verify artifact was created
    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (a:Artifact:PaperSection {name: 'chapter-new'}) RETURN a"
        ).single()
    assert result is not None
    node = dict(result["a"])
    assert node["title"] == "Chapter New"


# ---------------------------------------------------------------------------
# Test 7: --quiet exit codes (no output) — three separate cases
# ---------------------------------------------------------------------------

def _mock_config_and_driver(neo4j_driver):
    """Return (mock_config_value, mock_driver_value) for patching verify_command."""
    return (
        {
            "project": {"name": "test-project", "domain": "research"},
            "neo4j": {"uri": "bolt://localhost:7687", "database": NEO4J_DB},
        },
        neo4j_driver,
    )


def _invoke_quiet(runner, neo4j_driver, project_dir):
    """Invoke verify_command --quiet with mocked config/driver/cwd. Returns CliRunner result."""
    from seldon.commands.verify import verify_command

    cfg, drv = _mock_config_and_driver(neo4j_driver)
    with patch("seldon.commands.verify.load_project_config") as mock_config, \
         patch("seldon.commands.verify.get_neo4j_driver") as mock_driver, \
         patch("seldon.commands.verify.Path") as mock_path_cls:
        # Make Path.cwd() return the fixture project_dir; all other Path calls
        # must still behave normally, so we forward __call__ to the real Path.
        from pathlib import Path as RealPath
        mock_path_cls.cwd.return_value = project_dir
        mock_path_cls.side_effect = RealPath
        mock_config.return_value = cfg
        mock_driver.return_value = drv
        with patch.object(neo4j_driver, "close"):
            return runner.invoke(verify_command, ["--quiet"])


def test_verify_quiet_exit_code_0(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Clean project with --quiet: exit code 0 and no output."""
    from click.testing import CliRunner

    # Register one section so there are no unregistered files
    sections_dir = project_dir / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    _make_section(
        neo4j_driver, project_dir, domain_config,
        "chapter_01",
        str(sections_dir / "chapter-01.md"),
        "# Introduction\nSome content.\n",
    )

    # Create a glossary file so the glossary check passes (no check script = skip gracefully)
    glossary_dir = project_dir / "paper"
    glossary_dir.mkdir(parents=True, exist_ok=True)
    (glossary_dir / "glossary.md").write_text("```{glossary}\n```\n")

    runner = CliRunner()
    result = _invoke_quiet(runner, neo4j_driver, project_dir)

    assert result.exit_code == 0
    assert result.output == ""


def test_verify_quiet_exit_code_1(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Stale artifact with --quiet: exit code 1 and no output."""
    from click.testing import CliRunner

    # Create a stale artifact (warning condition)
    result_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={
            "name": "metric_quiet_warn",
            "value": 0.42,
            "units": "fraction",
            "description": "Metric for quiet-mode warning test",
        },
        actor="test",
        authority="accepted",
    )
    transition_state(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=result_id,
        artifact_type="Result",
        current_state="proposed",
        new_state="verified",
        actor="test",
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
        actor="test",
        authority="accepted",
    )

    runner = CliRunner()
    result = _invoke_quiet(runner, neo4j_driver, project_dir)

    assert result.exit_code == 1
    assert result.output == ""


def test_verify_quiet_exit_code_2(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Unregistered file in tracked directory with --quiet: exit code 2 and no output."""
    from click.testing import CliRunner

    # Create a tracked directory with an unregistered file (issue condition)
    sections_dir = project_dir / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "orphan-section.md").write_text("# Orphan\nNo artifact.\n", encoding="utf-8")

    runner = CliRunner()
    result = _invoke_quiet(runner, neo4j_driver, project_dir)

    assert result.exit_code == 2
    assert result.output == ""


# ---------------------------------------------------------------------------
# TODO: Ontology drift tests
# ---------------------------------------------------------------------------

# TODO: test_verify_detects_ontology_drift — requires multi-DB test setup
#   Would need to create _OntologyMeta in seldon-ontology DB and
#   _OntologyReplicaMeta in seldon-test DB with different epochs.

# TODO: test_verify_fix_syncs_ontology — requires multi-DB test setup
#   Would mock subprocess call to `seldon ontology sync`.


# ---------------------------------------------------------------------------
# Test: Reference check detects unresolvable tokens
# ---------------------------------------------------------------------------

def test_verify_detects_unresolvable_references(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """PaperSection with {{result:MISSING:value}} -> reported as unresolvable."""
    sections_dir = project_dir / "paper" / "sections"
    sections_dir.mkdir(parents=True)

    content = "# Results\nThe accuracy is {{result:nonexistent_metric:value}}.\n"
    _make_section(
        neo4j_driver, project_dir, domain_config,
        "chapter_results",
        str(sections_dir / "chapter-results.md"),
        content,
    )

    result = check_references(neo4j_driver, NEO4J_DB, project_dir)
    assert result.symbol == "fail"
    assert "nonexistent_metric" in result.summary


# ---------------------------------------------------------------------------
# Test: --strict mode exit code logic (pure unit — no Neo4j needed)
# ---------------------------------------------------------------------------

class TestStrictMode:
    """Strict-mode exit code tests — mock CheckResult lists, no database."""

    def _invoke_strict(self, runner, mock_results):
        """Invoke verify_command --strict with mocked check results."""
        from click.testing import CliRunner
        from unittest.mock import patch, MagicMock
        from seldon.commands.verify import verify_command

        fake_config = {
            "project": {"name": "test", "domain": "research"},
            "neo4j": {"uri": "bolt://localhost:7687", "database": "seldon-test"},
        }
        fake_driver = MagicMock()
        fake_driver.close = MagicMock()

        with patch("seldon.commands.verify.load_project_config", return_value=fake_config), \
             patch("seldon.commands.verify.get_neo4j_driver", return_value=fake_driver), \
             patch("seldon.commands.verify._run_all_checks", return_value=mock_results), \
             patch("seldon.commands.verify.Path") as mock_path_cls:
            from pathlib import Path as RealPath
            mock_path_cls.cwd.return_value = RealPath("/tmp")
            mock_path_cls.side_effect = RealPath
            return runner.invoke(verify_command, ["--strict"])

    def test_strict_exits_0_when_only_tier_b_warn(self):
        """--strict exits 0 when only advisory (Tier B) findings exist."""
        from click.testing import CliRunner
        from seldon.commands.verify import CheckResult

        mock_results = [
            CheckResult(name="File hashes", symbol="pass", summary="OK"),
            CheckResult(name="Ontology", symbol="pass", summary="OK"),
            CheckResult(name="Glossary", symbol="pass", summary="OK"),
            CheckResult(name="References", symbol="pass", summary="OK"),
            CheckResult(name="Stale artifacts", symbol="warn", summary="2 stale"),
            CheckResult(name="Blocking tasks", symbol="warn", summary="1 blocker"),
            CheckResult(name="Unregistered files", symbol="pass", summary="OK"),
        ]
        result = self._invoke_strict(CliRunner(), mock_results)
        assert result.exit_code == 0

    def test_strict_exits_2_on_tier_a_file_hash_fail(self):
        """--strict exits 2 when File hashes (Tier A) fails."""
        from click.testing import CliRunner
        from seldon.commands.verify import CheckResult

        mock_results = [
            CheckResult(name="File hashes", symbol="fail", summary="1 out of sync"),
            CheckResult(name="Ontology", symbol="pass", summary="OK"),
            CheckResult(name="Glossary", symbol="pass", summary="OK"),
            CheckResult(name="References", symbol="pass", summary="OK"),
            CheckResult(name="Stale artifacts", symbol="pass", summary="OK"),
            CheckResult(name="Blocking tasks", symbol="pass", summary="OK"),
            CheckResult(name="Unregistered files", symbol="pass", summary="OK"),
        ]
        result = self._invoke_strict(CliRunner(), mock_results)
        assert result.exit_code == 2

    def test_strict_exits_2_on_ontology_fail(self):
        """--strict exits 2 when Ontology (Tier A) drifts."""
        from click.testing import CliRunner
        from seldon.commands.verify import CheckResult

        mock_results = [
            CheckResult(name="File hashes", symbol="pass", summary="OK"),
            CheckResult(name="Ontology", symbol="fail", summary="epoch 1 vs master 3"),
            CheckResult(name="Glossary", symbol="pass", summary="OK"),
            CheckResult(name="References", symbol="pass", summary="OK"),
            CheckResult(name="Stale artifacts", symbol="warn", summary="1 stale"),
            CheckResult(name="Blocking tasks", symbol="pass", summary="OK"),
            CheckResult(name="Unregistered files", symbol="pass", summary="OK"),
        ]
        result = self._invoke_strict(CliRunner(), mock_results)
        assert result.exit_code == 2

    def test_default_mode_unchanged_warn_exits_1(self):
        """Default mode (no --strict): advisory warn still exits 1."""
        from click.testing import CliRunner
        from unittest.mock import patch, MagicMock
        from seldon.commands.verify import verify_command, CheckResult

        mock_results = [
            CheckResult(name="File hashes", symbol="pass", summary="OK"),
            CheckResult(name="Ontology", symbol="pass", summary="OK"),
            CheckResult(name="Glossary", symbol="pass", summary="OK"),
            CheckResult(name="References", symbol="pass", summary="OK"),
            CheckResult(name="Stale artifacts", symbol="warn", summary="1 stale"),
            CheckResult(name="Blocking tasks", symbol="pass", summary="OK"),
            CheckResult(name="Unregistered files", symbol="pass", summary="OK"),
        ]

        fake_config = {
            "project": {"name": "test", "domain": "research"},
            "neo4j": {"uri": "bolt://localhost:7687", "database": "seldon-test"},
        }
        fake_driver = MagicMock()
        fake_driver.close = MagicMock()

        with patch("seldon.commands.verify.load_project_config", return_value=fake_config), \
             patch("seldon.commands.verify.get_neo4j_driver", return_value=fake_driver), \
             patch("seldon.commands.verify._run_all_checks", return_value=mock_results), \
             patch("seldon.commands.verify.Path") as mock_path_cls:
            from pathlib import Path as RealPath
            mock_path_cls.cwd.return_value = RealPath("/tmp")
            mock_path_cls.side_effect = RealPath
            runner = CliRunner()
            result = runner.invoke(verify_command, [])
        assert result.exit_code == 1
