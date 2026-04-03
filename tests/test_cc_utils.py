"""
Pure unit tests for cc command helpers — no Neo4j needed.
"""
from __future__ import annotations

from pathlib import Path

from seldon.commands.cc import _name_from_filepath, _extract_description


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
