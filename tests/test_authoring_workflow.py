"""Tests for authoring workflow phase 1: hash enforcement + paper fix."""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from seldon.commands.cc import _file_hash, cc_group
from seldon.commands.paper import paper_fix


# ---------------------------------------------------------------------------
# Item 2: file_hash on registration
# ---------------------------------------------------------------------------

def test_file_hash_computes_sha256(tmp_path):
    """_file_hash returns correct SHA-256 hex digest."""
    f = tmp_path / "test.md"
    content = b"# Test Task\n\nSome content.\n"
    f.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert _file_hash(f) == expected


# ---------------------------------------------------------------------------
# Item 4: paper fix
# ---------------------------------------------------------------------------

def test_paper_fix_unique_match(tmp_path):
    """Fix applied when find text appears exactly once."""
    section = tmp_path / "section.md"
    section.write_text("This has a typo in the sentnece somewhere.\n")

    runner = CliRunner()
    result = runner.invoke(paper_fix, [
        str(section), "--find", "sentnece", "--replace", "sentence",
        "--confirm", "--no-build",
    ])
    assert result.exit_code == 0
    assert "Fixed:" in result.output
    assert "sentence" in section.read_text()
    assert "sentnece" not in section.read_text()


def test_paper_fix_zero_matches(tmp_path):
    """Error when find text not found."""
    section = tmp_path / "section.md"
    section.write_text("Nothing matches here.\n")

    runner = CliRunner()
    result = runner.invoke(paper_fix, [
        str(section), "--find", "nonexistent_text_xyz",
        "--replace", "whatever", "--confirm", "--no-build",
    ])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "not found" in (result.output + str(result.exception or "")).lower()


def test_paper_fix_multiple_matches(tmp_path):
    """Error when find text appears more than once."""
    section = tmp_path / "section.md"
    section.write_text("the word appears and the word appears again.\n")

    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(paper_fix, [
        str(section), "--find", "the word appears",
        "--replace", "it works", "--confirm", "--no-build",
    ])
    assert result.exit_code != 0


def test_paper_fix_deletion(tmp_path):
    """Empty replace string deletes the found text."""
    section = tmp_path / "section.md"
    section.write_text("Remove THIS_MARKER from the text.\n")

    runner = CliRunner()
    result = runner.invoke(paper_fix, [
        str(section), "--find", "THIS_MARKER ", "--replace", "",
        "--confirm", "--no-build",
    ])
    assert result.exit_code == 0
    assert "THIS_MARKER" not in section.read_text()


def test_paper_fix_no_build_skips_build_cycle(tmp_path):
    """--no-build prevents running the build cycle."""
    section = tmp_path / "section.md"
    section.write_text("Fix this typo here.\n")

    runner = CliRunner()
    result = runner.invoke(paper_fix, [
        str(section), "--find", "typo", "--replace", "error",
        "--confirm", "--no-build",
    ])
    assert result.exit_code == 0
    assert "Running build cycle" not in result.output


def test_paper_fix_event_captured(tmp_path, monkeypatch):
    """Paper fix captures event via append_event."""
    section = tmp_path / "section.md"
    section.write_text("Fix the problem here.\n")

    # Mock append_event at the module it's imported from in paper_fix
    captured = []
    monkeypatch.setattr(
        "seldon.core.events.append_event",
        lambda project_dir, event: captured.append(event),
    )

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(paper_fix, [
        str(section), "--find", "problem", "--replace", "issue",
        "--confirm", "--no-build",
    ])
    assert result.exit_code == 0
    assert len(captured) == 1
    assert captured[0]["event_type"] == "paper_fix"
    assert captured[0]["payload"]["find"] == "problem"
    assert captured[0]["payload"]["replace"] == "issue"
