"""
Pure unit tests for cc command helpers — no Neo4j needed.
"""
from __future__ import annotations

from pathlib import Path

from seldon.commands.cc import _name_from_filepath, _extract_description
from seldon.mcp_server import _WRITE_PATTERN


class TestNameFromFilepath:
    def test_strips_date_prefix_and_underscores(self):
        assert _name_from_filepath("cc_tasks/2026-04-03_some_task.md") == "some task"

    def test_no_date_prefix(self):
        assert _name_from_filepath("cc_tasks/fix_bug.md") == "fix bug"

    def test_bare_filename(self):
        assert _name_from_filepath("just_a_name.md") == "just a name"

    def test_deep_path(self):
        assert _name_from_filepath("/abs/path/2026-01-15_register_result.md") == "register result"


class TestExtractDescription:
    def test_extracts_first_non_header_line(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("# Title\n\nSome description text here.\n\nMore content.")
        assert _extract_description(f) == "Some description text here."

    def test_skips_blank_lines_before_header(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("\n\n# Header\n\nFirst real line.\n")
        assert _extract_description(f) == "First real line."

    def test_falls_back_to_filename_if_only_headers(self, tmp_path):
        f = tmp_path / "mytask.md"
        f.write_text("# Title\n## Subtitle\n")
        assert _extract_description(f) == "mytask.md"

    def test_truncates_at_200_chars(self, tmp_path):
        f = tmp_path / "long.md"
        f.write_text("# H\n\n" + "x" * 300 + "\n")
        result = _extract_description(f)
        assert len(result) == 200

    def test_skips_date_metadata_line(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("# Title\n\n**Date:** 2026-04-05\n**Project:** seldon\n\nActual goal.")
        assert _extract_description(f) == "Actual goal."

    def test_skips_all_metadata_before_content(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text(
            "# CC Task\n\n"
            "**Date:** 2026-04-05\n"
            "**Project:** seldon\n"
            "**Priority:** HIGH\n"
            "\n---\n\n"
            "## Goal\n\n"
            "Fix the thing.\n"
        )
        assert _extract_description(f) == "Fix the thing."

    def test_skips_horizontal_rule(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("# Title\n\n---\n\nFirst real content.\n")
        assert _extract_description(f) == "First real content."


class TestQueryWritePattern:
    def test_rejects_create(self):
        assert _WRITE_PATTERN.search("CREATE (n:Foo)")

    def test_rejects_merge(self):
        assert _WRITE_PATTERN.search("MERGE (n:Foo {id: '1'})")

    def test_rejects_set(self):
        assert _WRITE_PATTERN.search("MATCH (n) SET n.x = 1")

    def test_rejects_delete(self):
        assert _WRITE_PATTERN.search("MATCH (n) DELETE n")

    def test_rejects_remove(self):
        assert _WRITE_PATTERN.search("MATCH (n) REMOVE n.prop")

    def test_rejects_detach(self):
        assert _WRITE_PATTERN.search("MATCH (n) DETACH DELETE n")

    def test_allows_match(self):
        assert not _WRITE_PATTERN.search("MATCH (n) RETURN n")

    def test_allows_return_with_where(self):
        assert not _WRITE_PATTERN.search("MATCH (n) WHERE n.x > 0 RETURN n.x")
