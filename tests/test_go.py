"""
Unit tests for `seldon go` — orientation context assembler.
These tests do NOT require Neo4j.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.go import (
    assemble_go_context,
    assemble_go_context_as_dict,
    _get_pipeline_section,
)
from seldon.cli import main


# ---------------------------------------------------------------------------
# Test 1: No seldon.yaml — degrades gracefully, Role section present
# ---------------------------------------------------------------------------

def test_go_without_graph_degrades_gracefully(tmp_path):
    """assemble_go_context() with no seldon.yaml must not raise; output must include Role section."""
    result = assemble_go_context(project_dir=str(tmp_path))
    assert "## Role" in result


# ---------------------------------------------------------------------------
# Test 2: SELDON_SYSTEM_CLAUDE_MD env var is honoured
# ---------------------------------------------------------------------------

def test_go_includes_system_standards(tmp_path, monkeypatch):
    """Content from the file pointed to by SELDON_SYSTEM_CLAUDE_MD must appear in output."""
    standards_file = tmp_path / "system_claude.md"
    standards_file.write_text("# Global Engineering Standards\n\nAlways write tests first.")
    monkeypatch.setenv("SELDON_SYSTEM_CLAUDE_MD", str(standards_file))

    result = assemble_go_context(project_dir=str(tmp_path))
    assert "Always write tests first." in result


# ---------------------------------------------------------------------------
# Test 3: brief=True skips system CLAUDE.md
# ---------------------------------------------------------------------------

def test_go_brief_skips_system_standards(tmp_path, monkeypatch):
    """With brief=True, system CLAUDE.md content must NOT appear in output."""
    standards_file = tmp_path / "system_claude.md"
    unique_token = "UNIQUE_SYSTEM_STANDARDS_TOKEN_XYZ"
    standards_file.write_text(f"# Standards\n\n{unique_token}")
    monkeypatch.setenv("SELDON_SYSTEM_CLAUDE_MD", str(standards_file))

    result = assemble_go_context(project_dir=str(tmp_path), brief=True)
    assert unique_token not in result


# ---------------------------------------------------------------------------
# Test 4: Project CLAUDE.md content is included
# ---------------------------------------------------------------------------

def test_go_includes_project_context(tmp_path):
    """CLAUDE.md in project_dir must appear under Project Context section."""
    claude_md = tmp_path / "CLAUDE.md"
    unique_token = "MY_PROJECT_CONTEXT_TOKEN_ABC123"
    claude_md.write_text(f"# My Project\n\n{unique_token}")

    result = assemble_go_context(project_dir=str(tmp_path))
    assert unique_token in result
    assert "## Project Context" in result


# ---------------------------------------------------------------------------
# Test 5: Missing project CLAUDE.md shows degraded message
# ---------------------------------------------------------------------------

def test_go_missing_project_claude_md(tmp_path):
    """When no CLAUDE.md is present in project_dir, output should note its absence."""
    result = assemble_go_context(project_dir=str(tmp_path))
    assert "No CLAUDE.md found" in result


# ---------------------------------------------------------------------------
# Test 6: Most recent handoff file is included
# ---------------------------------------------------------------------------

def test_go_includes_latest_handoff(tmp_path):
    """The most recently named handoff file (sorted descending) must be in output."""
    handoffs_dir = tmp_path / "handoffs"
    handoffs_dir.mkdir()

    older_file = handoffs_dir / "2024-01-01_session.md"
    older_file.write_text("OLDER_HANDOFF_CONTENT")

    newer_file = handoffs_dir / "2024-06-15_session.md"
    newer_file.write_text("NEWER_HANDOFF_CONTENT")

    result = assemble_go_context(project_dir=str(tmp_path))
    assert "NEWER_HANDOFF_CONTENT" in result
    assert "OLDER_HANDOFF_CONTENT" not in result


# ---------------------------------------------------------------------------
# Test 7: JSON output via assemble_go_context_as_dict has all expected keys
# ---------------------------------------------------------------------------

def test_go_json_output_has_expected_keys(tmp_path):
    """assemble_go_context_as_dict() must return dict with all required top-level keys."""
    data = assemble_go_context_as_dict(project_dir=str(tmp_path))

    expected_keys = {
        "role",
        "system_standards",
        "project_context",
        "latest_handoff",
        "project_state",
        "audit_pipeline",
        "agent_roles",
        "available_commands",
    }
    assert expected_keys == set(data.keys())

    # Also verify the CLI --json flag produces valid JSON with the same keys
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["go", "--json"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert expected_keys == set(parsed.keys())


# ---------------------------------------------------------------------------
# Test 8: assemble_go_context includes Agent Roles section when roles exist
# ---------------------------------------------------------------------------

def test_go_includes_agent_roles_when_roles_exist(monkeypatch, tmp_path):
    """assemble_go_context includes Agent Roles section when _get_agent_roles_section returns content."""
    from seldon.commands import go as go_module

    fake_roles_section = "## Agent Roles\n\n### Test Role\nYou are a test role."
    monkeypatch.setattr(go_module, "_get_agent_roles_section", lambda project_dir: fake_roles_section)

    result = go_module.assemble_go_context(project_dir=str(tmp_path))
    assert "## Agent Roles" in result
    assert "Test Role" in result


# ---------------------------------------------------------------------------
# Test 9: assemble_go_context omits Agent Roles section when function returns None
# ---------------------------------------------------------------------------

def test_go_omits_agent_roles_when_none(monkeypatch, tmp_path):
    """assemble_go_context omits Agent Roles section when _get_agent_roles_section returns None."""
    from seldon.commands import go as go_module

    monkeypatch.setattr(go_module, "_get_agent_roles_section", lambda project_dir: None)

    result = go_module.assemble_go_context(project_dir=str(tmp_path))
    assert "## Agent Roles" not in result


# ---------------------------------------------------------------------------
# Test 10: SELDON_DEFAULT_PROJECT env var used when project_dir is "."
# ---------------------------------------------------------------------------

def test_go_default_project_from_env(tmp_path, monkeypatch):
    """When project_dir is '.', SELDON_DEFAULT_PROJECT env var is used if it contains seldon.yaml."""
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / "seldon.yaml").write_text("project:\n  name: test\n")
    unique_token = "MY_DEFAULT_PROJECT_TOKEN_XYZ"
    (project_dir / "CLAUDE.md").write_text(f"# Project\n\n{unique_token}")

    monkeypatch.setenv("SELDON_DEFAULT_PROJECT", str(project_dir))
    result = assemble_go_context(project_dir=".")
    assert unique_token in result


# ---------------------------------------------------------------------------
# Test 11: Explicit project_dir overrides SELDON_DEFAULT_PROJECT
# ---------------------------------------------------------------------------

def test_go_explicit_project_dir_overrides_env(tmp_path, monkeypatch):
    """An explicit project_dir (not '.') takes precedence over SELDON_DEFAULT_PROJECT."""
    env_project = tmp_path / "env_project"
    env_project.mkdir()
    (env_project / "seldon.yaml").write_text("project:\n  name: env\n")
    (env_project / "CLAUDE.md").write_text("ENV_PROJECT_CONTENT")

    explicit_project = tmp_path / "explicit_project"
    explicit_project.mkdir()
    (explicit_project / "CLAUDE.md").write_text("EXPLICIT_PROJECT_CONTENT")

    monkeypatch.setenv("SELDON_DEFAULT_PROJECT", str(env_project))
    result = assemble_go_context(project_dir=str(explicit_project))
    assert "EXPLICIT_PROJECT_CONTENT" in result
    assert "ENV_PROJECT_CONTENT" not in result


# ---------------------------------------------------------------------------
# Test 12: Invalid SELDON_DEFAULT_PROJECT degrades gracefully
# ---------------------------------------------------------------------------

def test_go_invalid_env_path_degrades_gracefully(tmp_path, monkeypatch):
    """Invalid or missing SELDON_DEFAULT_PROJECT falls back to '.' without crashing."""
    monkeypatch.setenv("SELDON_DEFAULT_PROJECT", str(tmp_path / "nonexistent"))
    result = assemble_go_context(project_dir=".")
    assert "## Role" in result


# ---------------------------------------------------------------------------
# Tests 13-17: _get_pipeline_section
# ---------------------------------------------------------------------------

def _write_seldon_yaml(path: Path, content: str) -> None:
    (path / "seldon.yaml").write_text(content)


def test_pipeline_section_policy_brief_gates(tmp_path):
    """policy_brief profile lists correct gates and marks bloom_depth_check as skipped."""
    _write_seldon_yaml(tmp_path, "project:\n  name: test\nreview:\n  document_type: policy_brief\n")
    result = _get_pipeline_section(str(tmp_path))
    assert result is not None
    assert "policy_brief" in result
    assert "content_audit" in result
    assert "bloom_depth_check" in result  # appears in skipped line
    assert "Skipped gates" in result


def test_pipeline_section_not_configured(tmp_path):
    """No review.document_type key → 'Not configured' message."""
    _write_seldon_yaml(tmp_path, "project:\n  name: test\n")
    result = _get_pipeline_section(str(tmp_path))
    assert result is not None
    assert "Not configured" in result


def test_pipeline_section_no_seldon_yaml(tmp_path):
    """No seldon.yaml → returns None (no section emitted)."""
    result = _get_pipeline_section(str(tmp_path))
    assert result is None


def test_pipeline_section_agent_checkmarks(tmp_path):
    """Agent files present → checkmarks; missing → ✗ with doc reference."""
    _write_seldon_yaml(tmp_path, "project:\n  name: test\nreview:\n  document_type: academic_paper\n")

    # No agents dir yet — both missing
    result_missing = _get_pipeline_section(str(tmp_path))
    assert "✗" in result_missing
    assert "audit_pipeline.md" in result_missing

    # Create agent files
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "auditor.md").write_text("# Auditor")
    (agents_dir / "cascade-checker.md").write_text("# Cascade")

    result_present = _get_pipeline_section(str(tmp_path))
    assert "✓" in result_present
    assert "✗" not in result_present


def test_pipeline_section_latest_run_surfaced(tmp_path):
    """Latest run-* directory name appears in the pipeline section."""
    _write_seldon_yaml(tmp_path, "project:\n  name: test\nreview:\n  document_type: academic_paper\n")
    audits_dir = tmp_path / "audits"
    audits_dir.mkdir()
    (audits_dir / "run-001_2026-04-10").mkdir()
    latest = audits_dir / "run-002_2026-04-17"
    latest.mkdir()
    (latest / "run_manifest.yaml").write_text("run_id: run-002\ndate: '2026-04-17'\n")

    result = _get_pipeline_section(str(tmp_path))
    assert "run-002_2026-04-17" in result


def test_verdict_extraction_top_level(tmp_path):
    """Top-level verdict field is returned directly."""
    from seldon.commands.go import _extract_verdict
    assert _extract_verdict({"verdict": "ready_to_ship"}) == "ready_to_ship"


def test_verdict_extraction_paper_status(tmp_path):
    """paper_status is used when no top-level verdict key exists."""
    from seldon.commands.go import _extract_verdict
    assert _extract_verdict({"paper_status": "ready_for_submission"}) == "ready_for_submission"


def test_verdict_extraction_delta_summary(tmp_path):
    """delta_summary.verdict is used when top-level verdict is absent."""
    from seldon.commands.go import _extract_verdict
    manifest = {
        "run_id": "run-002",
        "delta_summary": {"verdict": "conditionally_ready", "net_reduction": 28},
    }
    assert _extract_verdict(manifest) == "conditionally_ready"


def test_verdict_extraction_chapters_worst_case(tmp_path):
    """Worst-case chapter verdict returned when no run-level summary exists."""
    from seldon.commands.go import _extract_verdict
    manifest = {
        "chapters_audited": [
            {"chapter": "ch01", "verdict": "conditionally_ready"},
            {"chapter": "ch02", "verdict": "needs_revision"},
            {"chapter": "ch03", "verdict": "clean"},
        ]
    }
    assert _extract_verdict(manifest) == "needs_revision"


def test_verdict_extraction_missing(tmp_path):
    """Returns 'unknown' when no verdict is found anywhere."""
    from seldon.commands.go import _extract_verdict
    assert _extract_verdict({"run_id": "run-001", "gates": []}) == "unknown"


def test_pipeline_section_shows_verdict(tmp_path):
    """Pipeline section renders the extracted verdict in the Last run line."""
    _write_seldon_yaml(tmp_path, "project:\n  name: test\nreview:\n  document_type: academic_paper\n")
    audits_dir = tmp_path / "audits"
    audits_dir.mkdir()
    latest = audits_dir / "run-003_2026-04-17"
    latest.mkdir()
    (latest / "run_manifest.yaml").write_text(
        "run_id: run-003\ndate: '2026-04-17'\nverdict: ready_to_ship\n"
    )
    result = _get_pipeline_section(str(tmp_path))
    assert "ready_to_ship" in result


def test_pipeline_behavioral_contract_rules_present():
    """_ROLE_SECTION must contain both new verify-before-asserting rules."""
    from seldon.commands.go import _ROLE_SECTION
    assert "verify by reading the relevant convention document" in _ROLE_SECTION
    assert "query the graph first" in _ROLE_SECTION
