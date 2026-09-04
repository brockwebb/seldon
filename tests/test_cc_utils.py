"""
Pure unit tests for cc command helpers — no Neo4j needed.
"""
from __future__ import annotations

from pathlib import Path

from seldon.commands.cc import (
    _name_from_filepath,
    _extract_description,
    _description_looks_like_metadata,
    cc_register,
)
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
    """Prose-fallback behaviour of the description extractor.

    The first H1 wins whenever it names a subject, so every fixture below whose
    point is the FALLBACK path uses a subject-free boilerplate title
    (`# CC Task`). H1 precedence itself is covered in test_cc_description.py.
    """

    def test_extracts_first_non_header_line(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("# CC Task\n\nSome description text here.\n\nMore content.")
        assert _extract_description(f) == "Some description text here."

    def test_skips_blank_lines_before_header(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("\n\n# CC Task\n\nFirst real line.\n")
        assert _extract_description(f) == "First real line."

    def test_falls_back_to_filename_if_only_headers(self, tmp_path):
        f = tmp_path / "mytask.md"
        f.write_text("# CC Task\n## Subtitle\n")
        assert _extract_description(f) == "mytask.md"

    def test_truncates_at_200_chars(self, tmp_path):
        f = tmp_path / "long.md"
        f.write_text("# CC Task\n\n" + "x" * 300 + "\n")
        result = _extract_description(f)
        assert len(result) == 200

    def test_skips_date_metadata_line(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("# CC Task\n\n**Date:** 2026-04-05\n**Project:** seldon\n\nActual goal.")
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
        f.write_text("# CC Task\n\n---\n\nFirst real content.\n")
        assert _extract_description(f) == "First real content."

    def test_skips_location_bold_metadata(self, tmp_path):
        """Regression: **Location:** is not in the narrow allowlist but is metadata."""
        f = tmp_path / "task.md"
        f.write_text(
            "# CC Task\n\n"
            "**Location:** cc_tasks/foo.md\n"
            "**Date:** 2026-04-21\n\n"
            "Fix the metadata extractor.\n"
        )
        assert _extract_description(f) == "Fix the metadata extractor."

    def test_skips_bare_location_metadata(self, tmp_path):
        """Regression (the bug): `Location: foo.md` (no bold) was being taken as description."""
        f = tmp_path / "task.md"
        f.write_text(
            "# CC Task\n\n"
            "Location: cc_tasks/foo.md\n"
            "Date: 2026-04-21\n\n"
            "Fix the metadata extractor.\n"
        )
        assert _extract_description(f) == "Fix the metadata extractor."

    def test_skips_unusual_metadata_keys(self, tmp_path):
        """Keys outside the old allowlist (Severity, Target, Owner, Depends on, Estimate) are skipped."""
        f = tmp_path / "task.md"
        f.write_text(
            "# CC Task\n\n"
            "**Severity:** high\n"
            "**Target:** 2026-05-01\n"
            "**Owner:** brock\n"
            "**Depends on:** AD-022\n"
            "**Estimate:** 2h\n\n"
            "Actual task description goes here.\n"
        )
        assert _extract_description(f) == "Actual task description goes here."

    def test_metadata_only_file_falls_back_to_filename(self, tmp_path):
        """File with only metadata → fallback to filename (caller emits warning)."""
        f = tmp_path / "metadata_only.md"
        f.write_text(
            "# CC Task\n\n"
            "**Date:** 2026-04-21\n"
            "**Location:** cc_tasks/x.md\n"
            "**Severity:** high\n"
        )
        assert _extract_description(f) == "metadata_only.md"

    def test_multiword_key_with_underscore(self, tmp_path):
        """Keys with word chars like 'Due_date' or 'X-Ref' still recognized."""
        f = tmp_path / "task.md"
        f.write_text(
            "# CC Task\n\n"
            "**Due date:** tomorrow\n"
            "**X-Ref:** issue-42\n\n"
            "Real description.\n"
        )
        assert _extract_description(f) == "Real description."

    # --- H1-title extraction (kills the hard-wrap fragment class) ---
    # Real cc_task files carry the subject in a "# CC Task: <subject>" H1,
    # a single physical line immune to the wrapping that made prose
    # extraction capture mid-sentence metadata continuations.

    def test_cc_task_h1_is_the_description(self, tmp_path):
        f = tmp_path / "2026-07-06_reply-ingest-crash-resilience.md"
        f.write_text(
            "# CC Task: Reply-Ingest Crash Resilience — IMAP EOF Must Not Lose a Reply\n"
            "\n"
            "**Created:** 2026-07-06\n"
            "**Priority:** HIGH — reply-to-log is the PRIMARY logging interface; a crash class that\n"
            "can silently drop a reply is data loss on the main write path.\n"
        )
        assert _extract_description(f) == (
            "Reply-Ingest Crash Resilience — IMAP EOF Must Not Lose a Reply"
        )

    def test_cc_task_h1_with_TN_prefix(self, tmp_path):
        f = tmp_path / "2026-06-27_vocab-T4-segment-vestige-retire.md"
        f.write_text(
            "# CC Task T4: Retire segment vestige columns (destructive — backup + verify)\n"
            "\n"
            "**Priority:** LOW\n"
        )
        assert _extract_description(f) == (
            "Retire segment vestige columns (destructive — backup + verify)"
        )

    def test_wrapped_priority_value_never_captured(self, tmp_path):
        """The exact bug: a **Priority:** value that hard-wraps to a second
        physical line must not become the description — even on the fallback
        path (non-CC-Task H1)."""
        f = tmp_path / "task.md"
        f.write_text(
            "# CC Task\n"
            "\n"
            "**Priority:** HIGH — kills the whining email and ~$59/mo burn;\n"
            "removes the iCloud-symlink fragility from all scheduled jobs.\n"
            "\n"
            "First real prose line.\n"
        )
        assert _extract_description(f) == "First real prose line."


class TestDescriptionLooksLikeMetadata:
    def test_bold_metadata_line_detected(self):
        assert _description_looks_like_metadata("**Date:** 2026-04-21")

    def test_bare_metadata_line_detected(self):
        assert _description_looks_like_metadata("Location: cc_tasks/foo.md")

    def test_prose_sentence_not_flagged(self):
        assert not _description_looks_like_metadata("Fix the metadata extractor.")

    def test_sentence_with_midline_colon_not_flagged(self):
        assert not _description_looks_like_metadata(
            "The bug is that descriptions starting with metadata are truncated."
        )

    def test_empty_string_not_flagged(self):
        assert not _description_looks_like_metadata("")


class TestCCRegisterFlags:
    def test_register_has_description_option(self):
        """--description flag must exist on cc register, mirroring --note on cc complete."""
        option_names = {param.name for param in cc_register.params}
        assert "description" in option_names


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
