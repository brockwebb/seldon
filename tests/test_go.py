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
