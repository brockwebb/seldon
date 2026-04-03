"""
Tests for check_glossary() path resolution in seldon verify.

No Neo4j needed — pure filesystem tests.
"""
from __future__ import annotations

from pathlib import Path

from seldon.commands.verify import _find_glossary, check_glossary


def test_glossary_no_file_warns(tmp_path):
    """No glossary anywhere — warn (not silent skip)."""
    result = check_glossary(tmp_path)
    assert result.symbol == "warn"
    assert "No glossary file found" in result.summary


def test_glossary_finds_paper_glossary(tmp_path):
    """Falls back to paper/glossary.md when no config and no check script."""
    glossary = tmp_path / "paper" / "glossary.md"
    glossary.parent.mkdir(parents=True)
    glossary.write_text("# Glossary\n")
    # No check script — skips gracefully, still a pass
    result = check_glossary(tmp_path)
    assert result.symbol == "pass"
    assert "No check_glossary.py found" in result.summary


def test_glossary_finds_book_glossary(tmp_path):
    """Finds book/glossary.md when paper/glossary.md doesn't exist."""
    glossary = tmp_path / "book" / "glossary.md"
    glossary.parent.mkdir(parents=True)
    glossary.write_text("# Glossary\n")
    result = check_glossary(tmp_path)
    assert result.symbol == "pass"
    assert "No check_glossary.py found" in result.summary


def test_glossary_config_book_path_takes_priority(tmp_path):
    """Config 'book' key is checked before conventional fallbacks."""
    custom_dir = tmp_path / "chapters"
    custom_dir.mkdir()
    glossary = custom_dir / "glossary.md"
    glossary.write_text("# Glossary\n")

    config = {"paths": {"book": "chapters"}}
    found = _find_glossary(tmp_path, config)
    assert found == glossary


def test_glossary_config_paper_key(tmp_path):
    """Config 'paper' key resolves correctly."""
    paper_dir = tmp_path / "content"
    paper_dir.mkdir()
    glossary = paper_dir / "glossary.md"
    glossary.write_text("# Glossary\n")

    config = {"paths": {"paper": "content"}}
    found = _find_glossary(tmp_path, config)
    assert found == glossary


def test_find_glossary_returns_none_when_no_file(tmp_path):
    """_find_glossary returns None when no glossary exists anywhere."""
    assert _find_glossary(tmp_path) is None


def test_find_glossary_config_path_not_found_falls_back(tmp_path):
    """Config path pointing to non-existent dir falls through to conventional location."""
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    glossary = paper_dir / "glossary.md"
    glossary.write_text("# Glossary\n")

    # Config specifies a path that doesn't have a glossary
    config = {"paths": {"book": "nonexistent"}}
    found = _find_glossary(tmp_path, config)
    # Falls back to paper/glossary.md
    assert found == glossary
