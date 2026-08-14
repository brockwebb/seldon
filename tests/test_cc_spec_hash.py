"""Spec-scoped task hashing — the closure-integrity fix.

Pure unit tests, no Neo4j.

The defect: task files are hashed at registration, and every task file in this
project instructs its executor to append findings under a `## Findings` heading.
Hashing the whole file therefore guarantees that a *correctly executed* task is
hash-divergent by completion time, so `seldon cc complete` refuses it and every
closure has to route around the integrity check by raw UUID transition. The
sanctioned path could never succeed by design (reproduced 3x: 2026-07-30, and
twice in the 2026-08-13 arnold triage).

The fix hashes the SPEC — everything above the first Findings heading — so the
enforced invariant becomes the real one: **the spec is immutable, findings are
additive.**
"""
from __future__ import annotations

from seldon.commands.cc import _file_hash, _spec_hash, _split_spec


SPEC = """# CC Task: do the thing

**Date:** 2026-08-13

## Steps
1. Do it.

## Acceptance
- It is done.
"""

PLACEHOLDER = "\n## Findings\n*(CC appends here)*\n"
APPENDED = "\n## Findings\n\nDid the thing. Verified by read-back.\n"


def _write(tmp_path, text, name="task.md"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


class TestSplitSpec:
    def test_splits_at_findings_heading(self):
        spec, had = _split_spec(SPEC + PLACEHOLDER)
        assert had is True
        assert spec == SPEC.rstrip()
        assert "Findings" not in spec

    def test_no_findings_heading_returns_whole_text(self):
        spec, had = _split_spec(SPEC)
        assert had is False
        assert spec == SPEC.rstrip()

    def test_splits_at_FIRST_findings_heading_only(self):
        text = SPEC + "\n## Findings\nfirst\n\n## Findings (round 2)\nsecond\n"
        spec, had = _split_spec(text)
        assert had is True
        assert "first" not in spec and "second" not in spec

    def test_tolerates_heading_level_case_and_suffix(self):
        for heading in (
            "## Findings",
            "### findings",
            "#### FINDINGS",
            "## Findings (2026-07-16, CC)",
            "## Findings — round 2",
        ):
            spec, had = _split_spec(SPEC + f"\n{heading}\nbody\n")
            assert had is True, heading
            assert spec == SPEC.rstrip(), heading

    def test_does_not_split_on_prose_mentioning_findings(self):
        text = SPEC + "\nThe findings are important. ## not a heading\n"
        _, had = _split_spec(text)
        assert had is False

    def test_does_not_split_on_a_heading_merely_containing_findings(self):
        # "Prior findings" is a spec section, not the findings sink.
        text = "# T\n\n## Prior findings review\nread them\n"
        _, had = _split_spec(text)
        assert had is False


class TestSpecHash:
    def test_appending_findings_does_not_change_spec_hash(self, tmp_path):
        """THE regression this fix exists for."""
        p = _write(tmp_path, SPEC + PLACEHOLDER)
        before = _spec_hash(p)
        p.write_text(SPEC + APPENDED, encoding="utf-8")
        assert _spec_hash(p) == before

    def test_whole_file_hash_DOES_change_when_findings_appended(self, tmp_path):
        """Documents the old behaviour that made completion impossible."""
        p = _write(tmp_path, SPEC + PLACEHOLDER)
        before = _file_hash(p)
        p.write_text(SPEC + APPENDED, encoding="utf-8")
        assert _file_hash(p) != before

    def test_editing_the_spec_DOES_change_spec_hash(self, tmp_path):
        """Enforcement is preserved, not abandoned."""
        p = _write(tmp_path, SPEC + PLACEHOLDER)
        before = _spec_hash(p)
        p.write_text(SPEC.replace("It is done.", "It is mostly done.") + PLACEHOLDER,
                     encoding="utf-8")
        assert _spec_hash(p) != before

    def test_editing_spec_still_detected_when_findings_also_appended(self, tmp_path):
        """The realistic tamper case: spec edited AND findings appended."""
        p = _write(tmp_path, SPEC + PLACEHOLDER)
        before = _spec_hash(p)
        p.write_text(SPEC.replace("Do it.", "Do something else.") + APPENDED,
                     encoding="utf-8")
        assert _spec_hash(p) != before

    def test_trailing_whitespace_before_findings_is_not_significant(self, tmp_path):
        p = _write(tmp_path, SPEC + PLACEHOLDER)
        before = _spec_hash(p)
        p.write_text(SPEC + "\n\n\n" + APPENDED, encoding="utf-8")
        assert _spec_hash(p) == before

    def test_file_with_no_findings_section_hashes_its_whole_content(self, tmp_path):
        p = _write(tmp_path, SPEC)
        assert _spec_hash(p) == _file_hash(_write(tmp_path, SPEC.rstrip(), "stripped.md"))


class TestSpecTerminators:
    """aa5c7b73's ruling: a task file has three lifecycles — spec (immutable),
    ruling (new input after registration), findings (output). Only the spec is
    hashed, so a ruling appended mid-flight does not break closure either."""

    def test_ruling_heading_terminates_spec(self, tmp_path):
        p = _write(tmp_path, SPEC + PLACEHOLDER)
        before = _spec_hash(p)
        p.write_text(SPEC + "\n## RULING\nDo it the other way.\n" + APPENDED,
                     encoding="utf-8")
        assert _spec_hash(p) == before

    def test_addendum_heading_terminates_spec(self, tmp_path):
        p = _write(tmp_path, SPEC + PLACEHOLDER)
        before = _spec_hash(p)
        p.write_text(SPEC + "\n## Addendum\nAlso this.\n", encoding="utf-8")
        assert _spec_hash(p) == before

    def test_explicit_spec_end_marker_wins_over_headings(self, tmp_path):
        """The marker lets a task put the boundary where it wants — including
        ABOVE a section that happens to be titled Findings."""
        body = "# T\n\n## Steps\n1. go\n\n<!-- SPEC END -->\n## Notes\nfree\n"
        p = _write(tmp_path, body)
        before = _spec_hash(p)
        p.write_text(body + "\n## Findings\nmore\n", encoding="utf-8")
        assert _spec_hash(p) == before

    def test_spec_edit_above_marker_still_refused(self, tmp_path):
        body = "# T\n\n## Steps\n1. go\n\n<!-- SPEC END -->\n## Notes\nfree\n"
        p = _write(tmp_path, body)
        before = _spec_hash(p)
        p.write_text(body.replace("1. go", "1. stop"), encoding="utf-8")
        assert _spec_hash(p) != before

    def test_ruling_and_findings_together_end_to_end(self, tmp_path):
        """aa5c7b73 acceptance: register -> ruling appended -> findings appended
        -> still closes."""
        p = _write(tmp_path, SPEC + PLACEHOLDER)
        at_registration = _spec_hash(p)
        p.write_text(SPEC + "\n## RULING\nuse approach B\n", encoding="utf-8")
        assert _spec_hash(p) == at_registration
        p.write_text(SPEC + "\n## RULING\nuse approach B\n" + APPENDED, encoding="utf-8")
        assert _spec_hash(p) == at_registration
