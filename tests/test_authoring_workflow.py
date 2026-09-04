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
#
# Every `paper fix` test chdirs into tmp_path first. `paper_fix` resolves its
# event store as `Path.cwd()`, so a test that invokes it from the repo root
# appends a real `paper_fix` event — naming a pytest temp file that no longer
# exists — to Seldon's own append-only `seldon_events.jsonl`. Three such events
# were being written on every single suite run. The log is immutable, so those
# lines are permanent; chdir stops the bleeding.


def test_paper_fix_unique_match(tmp_path, monkeypatch):
    """Fix applied when find text appears exactly once."""
    monkeypatch.chdir(tmp_path)
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


def test_paper_fix_zero_matches(tmp_path, monkeypatch):
    """Error when find text not found."""
    monkeypatch.chdir(tmp_path)
    section = tmp_path / "section.md"
    section.write_text("Nothing matches here.\n")

    runner = CliRunner()
    result = runner.invoke(paper_fix, [
        str(section), "--find", "nonexistent_text_xyz",
        "--replace", "whatever", "--confirm", "--no-build",
    ])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "not found" in (result.output + str(result.exception or "")).lower()


def test_paper_fix_multiple_matches(tmp_path, monkeypatch):
    """Error when find text appears more than once."""
    monkeypatch.chdir(tmp_path)
    section = tmp_path / "section.md"
    section.write_text("the word appears and the word appears again.\n")

    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(paper_fix, [
        str(section), "--find", "the word appears",
        "--replace", "it works", "--confirm", "--no-build",
    ])
    assert result.exit_code != 0


def test_paper_fix_deletion(tmp_path, monkeypatch):
    """Empty replace string deletes the found text."""
    monkeypatch.chdir(tmp_path)
    section = tmp_path / "section.md"
    section.write_text("Remove THIS_MARKER from the text.\n")

    runner = CliRunner()
    result = runner.invoke(paper_fix, [
        str(section), "--find", "THIS_MARKER ", "--replace", "",
        "--confirm", "--no-build",
    ])
    assert result.exit_code == 0
    assert "THIS_MARKER" not in section.read_text()


def test_paper_fix_no_build_skips_build_cycle(tmp_path, monkeypatch):
    """--no-build prevents running the build cycle."""
    monkeypatch.chdir(tmp_path)
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
