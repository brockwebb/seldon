"""Description extraction for `seldon cc register` / `seldon cc complete`.

Covers the contract fixed in the 2026-09-03 defect sweep (lane D3): the first
H1 that names a subject IS the description, with `CC Task` / `Task` boilerplate
and its separator stripped. Prose is a fallback, and the fallback now skips
all-bold banner paragraphs.

Every fixture in `TestObservedFailureShapes` reproduces a description that was
actually written into a project graph by an earlier parser. No Neo4j needed.
"""
from __future__ import annotations

import pytest

from seldon.commands.cc import (
    _description_looks_like_metadata,
    _extract_description,
    _extract_description_with_source,
    _subject_from_h1,
    _warn_if_description_suspicious,
)


class TestSubjectFromH1:
    """Boilerplate stripping is separator-driven, not prefix-driven."""

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("CC Task: Reply-Ingest Crash Resilience", "Reply-Ingest Crash Resilience"),
            ("CC Task T4: Retire segment vestige columns", "Retire segment vestige columns"),
            ("CC Task — Seldon defect sweep", "Seldon defect sweep"),
            ("CC Task – en dash variant", "en dash variant"),
            ("CC Task - hyphen variant", "hyphen variant"),
            ("Task — no CC prefix", "no CC prefix"),
            ("Task: no CC prefix, colon", "no CC prefix, colon"),
            ("cc task: lowercase is still boilerplate", "lowercase is still boilerplate"),
        ],
    )
    def test_boilerplate_prefix_is_stripped(self, title, expected):
        assert _subject_from_h1(title) == expected

    @pytest.mark.parametrize(
        "title",
        ["Fix the widget", "Task list overhaul", "Tasks and their lifecycle"],
    )
    def test_plain_title_is_its_own_subject(self, title):
        """No separator means no boilerplate — the whole title is the subject."""
        assert _subject_from_h1(title) == title

    @pytest.mark.parametrize("title", ["CC Task", "Task", "CC Task T4:", "CC Task —"])
    def test_boilerplate_only_title_names_no_subject(self, title):
        assert _subject_from_h1(title) == ""


class TestH1Precedence:
    def test_plain_h1_beats_following_prose(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("# Fix the widget\n\nSome prose that is not the title.\n")
        assert _extract_description(f) == "Fix the widget"

    def test_subject_free_h1_falls_through_to_prose(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("# CC Task\n\nSome prose that IS the description.\n")
        assert _extract_description(f) == "Some prose that IS the description."

    def test_only_the_first_h1_is_consulted(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("# The real subject\n\nProse.\n\n# A later H1\n")
        assert _extract_description(f) == "The real subject"

    def test_h1_subject_is_truncated_to_200_chars(self, tmp_path):
        f = tmp_path / "task.md"
        f.write_text("# CC Task: " + "y" * 300 + "\n")
        assert len(_extract_description(f)) == 200


class TestObservedFailureShapes:
    """Each of the three descriptions observed in live graphs, as a fixture."""

    def test_em_dash_h1_no_longer_yields_the_immutability_banner(self, tmp_path):
        """seldon + 7 ai-readiness-kg tasks: `**Immutable once written...**`.

        The em-dash H1 form missed the colon-only title pattern, so extraction
        fell through to prose, where the all-bold immutability banner is not a
        metadata line (its first sentence ends in `.`, not `:`) and was taken
        as the description.
        """
        f = tmp_path / "2026-09-03_seldon_defect_sweep.md"
        f.write_text(
            "# CC Task — Seldon defect sweep: Result registry contract, task lifecycle\n"
            "\n"
            "**Date:** 2026-09-03\n"
            "**Project:** seldon\n"
            "\n"
            "**Immutable once written. Changes require a new task file "
            "or an `_ADDENDUM-NN.md` sibling.**\n"
            "\n"
            "---\n"
        )
        assert _extract_description(f) == (
            "Seldon defect sweep: Result registry contract, task lifecycle"
        )

    def test_immutability_banner_skipped_even_with_no_h1(self, tmp_path):
        """The banner must lose on the fallback path too, not only via the H1."""
        f = tmp_path / "banner_first.md"
        f.write_text(
            "**Immutable once written. Changes require a new task file.**\n"
            "\n"
            "Rebuild the registrar's description parser.\n"
        )
        assert _extract_description(f) == "Rebuild the registrar's description parser."

    def test_metadata_first_file_no_longer_yields_task_id(self, tmp_path):
        """seldon 7120e000: `**Task ID:** \\`seldon_file_issues_...\\``.

        A metadata block ahead of any prose. The H1 now supplies the subject
        outright; the metadata line is never a candidate.
        """
        f = tmp_path / "2026-04-16_file_issues_and_convention.md"
        f.write_text(
            "# CC Task: File issues and naming convention cleanup\n"
            "\n"
            "**Task ID:** `seldon_file_issues_and_convention_2026-04-16`\n"
            "**Date:** 2026-04-16\n"
            "\n"
            "## Goal\n"
            "\n"
            "Clean up file issues.\n"
        )
        assert _extract_description(f) == "File issues and naming convention cleanup"

    def test_metadata_first_file_without_h1_skips_the_metadata_block(self, tmp_path):
        """Same shape, no H1 at all: the fallback must still skip the metadata."""
        f = tmp_path / "no_h1.md"
        f.write_text(
            "**Task ID:** `seldon_file_issues_and_convention_2026-04-16`\n"
            "**Date:** 2026-04-16\n"
            "\n"
            "Clean up file issues and settle the naming convention.\n"
        )
        assert _extract_description(f) == (
            "Clean up file issues and settle the naming convention."
        )

    def test_hard_wrapped_prose_is_not_truncated_mid_sentence(self, tmp_path):
        """seldon 676c0e39: description stopped at the first physical line.

        `Add \\`tracer_bullet\\` as a named term to the master Seldon ontology
        with its` — a hard-wrapped paragraph captured one line deep.
        """
        f = tmp_path / "no_h1_wrapped.md"
        f.write_text(
            "Add `tracer_bullet` as a named term to the master Seldon ontology\n"
            "with its definition, usage rule, and banned synonyms.\n"
        )
        assert _extract_description(f) == (
            "Add `tracer_bullet` as a named term to the master Seldon ontology "
            "with its definition, usage rule, and banned synonyms."
        )

    def test_hard_wrapped_h1_case_uses_the_title(self, tmp_path):
        """The same file with its real H1 present: the title wins outright."""
        f = tmp_path / "2026-05-07_ontology_tracer_bullet.md"
        f.write_text(
            "# CC Task — Add `tracer_bullet` to the master ontology\n"
            "\n"
            "Add `tracer_bullet` as a named term to the master Seldon ontology\n"
            "with its definition, usage rule, and banned synonyms.\n"
        )
        assert _extract_description(f) == (
            "Add `tracer_bullet` to the master ontology"
        )


class TestSuspiciousDescriptionWarningStillWorks:
    def test_metadata_still_flagged(self):
        assert _description_looks_like_metadata("**Task ID:** `x`")

    def test_all_bold_banner_flagged(self):
        assert _description_looks_like_metadata(
            "**Immutable once written. Changes require a new task file.**"
        )

    def test_ordinary_description_not_flagged(self):
        assert not _description_looks_like_metadata(
            "Rebuild the registrar description parser"
        )

    def test_description_with_inline_bold_not_flagged(self):
        assert not _description_looks_like_metadata(
            "Make **verify** exempt snapshot artifacts from the drift check"
        )


class TestWarningIsSourceAware:
    """A colon in an authored title is punctuation, not a metadata key.

    Without this, every task titled "<topic>: <detail>" — the dominant title
    form in this repo — would emit a spurious warning on every registration,
    which trains the reader to ignore the warning that matters.
    """

    def test_title_with_colon_does_not_warn(self, tmp_path, capsys):
        f = tmp_path / "task.md"
        f.write_text("# CC Task — Defect sweep: registry contract\n\nBody.\n")
        description, source = _extract_description_with_source(f)
        assert source == "h1"
        _warn_if_description_suspicious(f, description, source)
        assert capsys.readouterr().err == ""

    def test_metadata_from_prose_still_warns(self, tmp_path, capsys):
        f = tmp_path / "task.md"
        _warn_if_description_suspicious(f, "**Task ID:** `x`", "prose")
        assert "WARNING" in capsys.readouterr().err

    def test_filename_fallback_still_warns(self, tmp_path, capsys):
        f = tmp_path / "only_headers.md"
        f.write_text("# CC Task\n## Subtitle\n")
        description, source = _extract_description_with_source(f)
        assert source == "filename"
        _warn_if_description_suspicious(f, description, source)
        assert "WARNING" in capsys.readouterr().err
