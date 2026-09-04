"""Regression tests for section-bounded parsing of VALIDITY_VOCABULARY.md.

These tests exist because of a specific silent failure. Commit ``b6714f3``
(2026-03-28) rewrote ``## Related Terms (Defined Elsewhere)`` from a pipe table
into a markdown definition list. ``_parse_related_terms`` located its heading and
then scanned forward for "the next line starting with ``|``" with no stop
condition, so it walked out of its own section and parsed the following table —
``## Terms That May Be Promoted from Projects`` — instead. The shared
``seldon-ontology`` master consequently carried two junk terms whose definition
was the literal string ``leibniz-pi`` (an "Origin Project" *column value*) while
five genuine terms were absent. Nothing raised; nothing failed.

The regression was invisible to synthetic fixtures because a hand-written
fixture reproduces the shape the parser already expects. So these tests read the
real vocabulary file, and the boundary tests build their fixtures by *mutating*
the real file rather than by inventing one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from seldon.ontology.parser import (
    SECTION_COVERAGE,
    VocabularyParseError,
    _PARSER_CATEGORY,
    _find_section,
    _heading_level,
    _parse_related_terms,
    parse_vocabulary,
)

VOCAB_PATH = Path(__file__).parent.parent / "ontology" / "validity" / "VALIDITY_VOCABULARY.md"

#: The five terms that ``## Related Terms (Defined Elsewhere)`` actually defines,
#: with a distinctive fragment of each real definition. Checking the definition
#: text — not just the count — is the point: the broken parser also produced
#: "some related terms", they were simply the wrong ones.
EXPECTED_RELATED_TERMS = {
    "ontology:validity:related:context_window": (
        "Context window",
        "mutable content that accumulates during pipeline operation",
    ),
    "ontology:validity:related:compaction": (
        "Compaction",
        "Automated summarization/truncation of context to fit window limits",
    ),
    "ontology:validity:related:handoff_document": (
        "Handoff document",
        "Explicit serialization of accumulated state for session continuity",
    ),
    "ontology:validity:related:state": (
        "State",
        "accumulated working context",
    ),
    "ontology:validity:related:fidelity": (
        "Fidelity",
        "Faithfulness of the operative state to the actual history of decisions",
    ),
}

#: Term IDs produced by the b6714f3 regression. These came from the "Terms That
#: May Be Promoted from Projects" table, one section further down the file.
JUNK_TERM_IDS = {
    "ontology:validity:related:log_precision_fitness",
    "ontology:validity:related:precision_gain_rate",
}


@pytest.fixture(scope="module")
def vocab():
    """Parse the real vocabulary file once for the whole module."""
    return parse_vocabulary(VOCAB_PATH)


@pytest.fixture(scope="module")
def vocab_lines():
    """The real vocabulary file split into lines."""
    return VOCAB_PATH.read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------
# The specific regression
# ---------------------------------------------------------------------------


class TestRelatedTermsRegression:
    """The b6714f3 mis-parse of ## Related Terms (Defined Elsewhere)."""

    def test_all_five_related_terms_parse(self, vocab):
        """The five real Related Terms are present with their real definitions."""
        related = {
            t.term_id: t for t in vocab.terms if t.category == "related_term"
        }
        assert set(related) == set(EXPECTED_RELATED_TERMS), (
            "Related Terms parse does not match the definition list in the file"
        )

        for term_id, (name, fragment) in EXPECTED_RELATED_TERMS.items():
            term = related[term_id]
            assert term.name == name
            assert fragment in term.definition, (
                f"{term_id} definition does not contain {fragment!r}; got "
                f"{term.definition!r}"
            )
            assert term.namespace == "ontology:validity"

    def test_junk_terms_are_not_produced(self, vocab):
        """The leibniz-pi promotion-candidate rows never become related terms."""
        produced = {t.term_id for t in vocab.terms}
        assert not (produced & JUNK_TERM_IDS), (
            "parser is still reaching into '## Terms That May Be Promoted from "
            "Projects'"
        )

    def test_no_term_definition_is_an_origin_project_value(self, vocab):
        """No term's definition is a bare column value from the promotion table.

        'leibniz-pi' as a definition is the signature of a parser that captured a
        table cell from the wrong table. Assert on the signature, not just on the
        two known IDs, so a different column leaking the same way is also caught.
        """
        offenders = [
            (t.term_id, t.definition)
            for t in vocab.terms
            if t.definition.strip().lower() == "leibniz-pi"
        ]
        assert offenders == []

    def test_usage_notes_kept_out_of_definitions(self, vocab):
        """A second ':' line is guidance, stored in extra, not in the definition."""
        state = next(
            t for t in vocab.terms if t.term_id == "ontology:validity:related:state"
        )
        assert "do not conflate with database state" in state.extra["usage_note"]
        assert "do not conflate with database state" not in state.definition

    def test_promotion_candidates_section_yields_nothing(self, vocab_lines):
        """Nothing in the file parses the promotion-candidate table into terms."""
        bounds = _find_section(
            vocab_lines, "## Terms That May Be Promoted from Projects"
        )
        assert bounds is not None, "fixture assumption: the section still exists"
        start, end = bounds
        body = "\n".join(vocab_lines[start:end])
        assert "leibniz-pi" in body, (
            "fixture assumption: the promotion table still names leibniz-pi"
        )


# ---------------------------------------------------------------------------
# The class of bug: a section parser that leaves its own section
# ---------------------------------------------------------------------------


class TestSectionBounds:
    """Section scans must not cross into a neighbouring section."""

    def test_heading_level(self):
        assert _heading_level("## Foo") == 2
        assert _heading_level("### Foo") == 3
        assert _heading_level("   ### Foo") == 3
        assert _heading_level("Foo") == 0
        assert _heading_level("#hashtag") == 0
        assert _heading_level("| ## not a heading |") == 0

    def test_section_ends_at_next_same_or_shallower_heading(self, vocab_lines):
        """A ## section ends at the next ##, and contains its own ### children."""
        start, end = _find_section(vocab_lines, "## Key Terminology Decisions")
        assert vocab_lines[start].strip() == "## Key Terminology Decisions"
        # Its ### children are inside.
        body = vocab_lines[start:end]
        assert any(b.strip().startswith("### Confabulation") for b in body)
        assert any(b.strip().startswith("### Terms Considered") for b in body)
        # The next ## section is not.
        assert not any(b.strip() == "## Framework Terms" for b in body)

    def test_exact_heading_match_does_not_collide_with_longer_heading(
        self, vocab_lines
    ):
        """'## Framework Terms' must not resolve to '## Framework Terms (Cross-Cutting)'."""
        start, _ = _find_section(vocab_lines, "## Framework Terms")
        assert vocab_lines[start].strip() == "## Framework Terms"

    def test_missing_section_returns_none(self, vocab_lines):
        assert _find_section(vocab_lines, "## No Such Section Exists Here") is None

    def test_reformatted_section_does_not_steal_the_next_table(self, tmp_path):
        """Reproduce the exact b6714f3 shape: gut a section, keep the next table.

        With the section's own content removed, the parser must yield nothing for
        it — not the following section's table rows.
        """
        text = VOCAB_PATH.read_text(encoding="utf-8")
        marker = "## Related Terms (Defined Elsewhere)"
        next_marker = "## Terms That May Be Promoted from Projects"
        head, _, tail = text.partition(marker)
        _, _, rest = tail.partition(next_marker)
        gutted = (
            head
            + marker
            + "\n\n*Section temporarily emptied.*\n\n---\n\n"
            + next_marker
            + rest
        )
        lines = gutted.splitlines()

        assert _parse_related_terms(lines) == [], (
            "parser reached past an empty section into the next one"
        )

    def test_emptied_section_fails_the_parse_loudly(self, tmp_path):
        """An emptied claimed section raises instead of yielding zero terms.

        This is the assertion that would have failed in March 2026.
        """
        text = VOCAB_PATH.read_text(encoding="utf-8")
        marker = "## Related Terms (Defined Elsewhere)"
        next_marker = "## Terms That May Be Promoted from Projects"
        head, _, tail = text.partition(marker)
        _, _, rest = tail.partition(next_marker)
        gutted = (
            head + marker + "\n\n*Section temporarily emptied.*\n\n---\n\n"
            + next_marker + rest
        )
        broken = tmp_path / "VALIDITY_VOCABULARY.md"
        broken.write_text(gutted, encoding="utf-8")

        with pytest.raises(VocabularyParseError) as exc:
            parse_vocabulary(broken)
        assert "Related Terms (Defined Elsewhere)" in str(exc.value)
        assert "_parse_related_terms" in str(exc.value)

    def test_renamed_section_fails_the_parse_loudly(self, tmp_path):
        """Renaming a claimed section raises rather than silently dropping it."""
        text = VOCAB_PATH.read_text(encoding="utf-8")
        renamed = text.replace(
            "### Engineering Countermeasures", "### Mitigations", 1
        )
        broken = tmp_path / "VALIDITY_VOCABULARY.md"
        broken.write_text(renamed, encoding="utf-8")

        with pytest.raises(VocabularyParseError) as exc:
            parse_vocabulary(broken)
        assert "Engineering Countermeasures" in str(exc.value)

    def test_partial_row_removal_does_not_break_ingest(self, tmp_path):
        """Editing one row out of a table is a legitimate change, not a failure.

        The runtime floor is one term per claimed section, not the declared
        count. Exact counts are the repo test's job (see TestSectionCoverage),
        so that a downstream project's ingest is not broken by a vocabulary edit
        that is merely newer than its checkout.
        """
        lines = VOCAB_PATH.read_text(encoding="utf-8").splitlines()
        start, end = _find_section(lines, "### Sub-dimensions")
        kept, seen_pipe = [], 0
        for idx, line in enumerate(lines):
            if start < idx < end and line.strip().startswith("|"):
                seen_pipe += 1
                if seen_pipe > 3:  # header + separator + one data row
                    continue
            kept.append(line)
        edited = tmp_path / "VALIDITY_VOCABULARY.md"
        edited.write_text("\n".join(kept), encoding="utf-8")

        parsed = parse_vocabulary(edited)
        assert len([t for t in parsed.terms if t.category == "sub_dimension"]) == 1


# ---------------------------------------------------------------------------
# Coverage: every heading in the file is accounted for
# ---------------------------------------------------------------------------


class TestSectionCoverage:
    """Every ## / ### heading is claimed by exactly one parser or declared prose."""

    def _headings(self, lines: list[str]) -> list[str]:
        return [
            re.sub(r"\s+", " ", ln.strip())
            for ln in lines
            if _heading_level(ln) in (2, 3)
        ]

    def test_every_heading_is_declared(self, vocab_lines):
        """A new or renamed section forces an explicit decision.

        If this fails, add the heading to SECTION_COVERAGE — either naming the
        parser that claims it and the minimum term count, or ``(None, 0)`` with a
        comment saying why it produces no ontology terms.
        """
        actual = self._headings(vocab_lines)
        declared = set(SECTION_COVERAGE)
        undeclared = [h for h in actual if h not in declared]
        assert undeclared == [], (
            f"headings present in {VOCAB_PATH.name} but absent from "
            f"SECTION_COVERAGE: {undeclared}"
        )

    def test_no_stale_declarations(self, vocab_lines):
        """SECTION_COVERAGE must not describe sections that no longer exist."""
        actual = set(self._headings(vocab_lines))
        stale = sorted(set(SECTION_COVERAGE) - actual)
        assert stale == [], (
            f"SECTION_COVERAGE declares headings that are gone from "
            f"{VOCAB_PATH.name}: {stale}"
        )

    def test_headings_are_unique(self, vocab_lines):
        """Duplicate headings would make bounded lookup ambiguous."""
        actual = self._headings(vocab_lines)
        dupes = sorted({h for h in actual if actual.count(h) > 1})
        assert dupes == [], f"duplicate headings in {VOCAB_PATH.name}: {dupes}"

    def test_each_claimed_section_resolves(self, vocab_lines):
        """Every claimed heading resolves to a non-empty section body."""
        for heading, (parser_name, expected) in SECTION_COVERAGE.items():
            if parser_name is None:
                continue
            prefix = heading.startswith("### Limitations Boilerplate")
            bounds = _find_section(vocab_lines, heading, prefix=prefix)
            assert bounds is not None, f"{heading!r} claimed by {parser_name} is missing"
            start, end = bounds
            body = [ln for ln in vocab_lines[start + 1:end] if ln.strip()]
            assert body, f"{heading!r} is claimed by {parser_name} but has no content"
            assert expected > 0, f"{heading!r} names a parser but declares 0 terms"

    def test_declared_counts_match_actual_counts(self, vocab):
        """Each claimed section produces exactly the number of terms declared.

        This is the strict half of the two-strength check described in
        SECTION_COVERAGE's docstring: the runtime parser only refuses a zero
        yield, so a partial mis-parse or a boundary leak surfaces here. If a
        vocabulary edit changed a count on purpose, update SECTION_COVERAGE in
        the same commit.
        """
        counts: dict[str, int] = {}
        for term in vocab.terms:
            counts[term.category] = counts.get(term.category, 0) + 1

        for heading, (parser_name, expected) in SECTION_COVERAGE.items():
            if parser_name is None:
                continue
            category = _PARSER_CATEGORY[parser_name]
            assert counts.get(category, 0) == expected, (
                f"{heading!r} produced {counts.get(category, 0)} term(s) of "
                f"category {category!r}, SECTION_COVERAGE declares {expected}"
            )

    def test_total_term_count(self, vocab):
        """Total parsed terms equal the sum of declared per-section counts.

        Catches terms arriving from a section that declares none — the direct
        signature of a parser reaching outside its own bounds.
        """
        expected = sum(n for _, n in SECTION_COVERAGE.values())
        assert len(vocab.terms) == expected


# ---------------------------------------------------------------------------
# Practitioner vocabulary — the other file the definition-list logic serves
# ---------------------------------------------------------------------------


def test_practitioner_vocabulary_has_no_tables():
    """Documents the basis for supporting only the definition-list form.

    ``_parse_related_terms`` deliberately does not retain the pre-b6714f3 table
    branch. That is only defensible while no live vocabulary uses tables for term
    definitions. If this fails, revisit that decision rather than deleting the
    test.
    """
    practitioner = (
        Path(__file__).parent.parent
        / "ontology"
        / "practitioner"
        / "PRACTITIONER_VOCABULARY.md"
    )
    if not practitioner.exists():
        pytest.skip("practitioner vocabulary not present")
    table_lines = [
        ln for ln in practitioner.read_text(encoding="utf-8").splitlines()
        if ln.strip().startswith("|")
    ]
    assert table_lines == []


# ---------------------------------------------------------------------------
# The three sections that no parser claimed until 2026-09-04
# ---------------------------------------------------------------------------

#: The five terms defined by ``## Core Instrument Terms``, with a distinctive
#: fragment of each real definition. Added to the vocabulary by commit 62d6bdf
#: (2026-04-17), enforced for glossary checking by
#: ``ontology/validity/vocabulary_rules.yaml``, and claimed by no parser — so
#: they had never once reached the shared ``seldon-ontology`` master.
EXPECTED_CORE_INSTRUMENT_TERMS = {
    "ontology:validity:instrument:accumulated_state": (
        "Accumulated state",
        "content that has built up inside the context window over sequential",
    ),
    "ontology:validity:instrument:operative_state": (
        "Operative state",
        "accumulated state at a specific point in time",
    ),
    "ontology:validity:instrument:composite_instrument": (
        "Composite instrument",
        "fixed model weights plus mutable context window",
    ),
    "ontology:validity:instrument:token_limit": (
        "Token limit",
        "fixed architectural constraint on context window size",
    ),
    "ontology:validity:instrument:instrument_stability_assumption": (
        "Instrument stability assumption",
        "measurement instrument is defined, stable, and consistent",
    ),
}

#: The single term defined by ``## Framework Terms (Cross-Cutting)``.
EXPECTED_CROSS_CUTTING_TERMS = {
    "ontology:validity:crosscutting:bounded_agency": (
        "Bounded agency",
        "constrained autonomy and persistent human oversight",
    ),
}


class TestPreviouslyUnparsedSections:
    """The six terms that existed in the file but never in the graph."""

    def test_core_instrument_terms_parse(self, vocab):
        parsed = {
            t.term_id: t for t in vocab.terms if t.category == "core_instrument_term"
        }
        assert set(parsed) == set(EXPECTED_CORE_INSTRUMENT_TERMS)
        for term_id, (name, fragment) in EXPECTED_CORE_INSTRUMENT_TERMS.items():
            term = parsed[term_id]
            assert term.name == name
            assert fragment in term.definition, (
                f"{term_id} definition does not contain {fragment!r}; got "
                f"{term.definition!r}"
            )
            assert term.namespace == "ontology:validity"

    def test_cross_cutting_terms_parse(self, vocab):
        parsed = {
            t.term_id: t for t in vocab.terms if t.category == "cross_cutting_term"
        }
        assert set(parsed) == set(EXPECTED_CROSS_CUTTING_TERMS)
        for term_id, (name, fragment) in EXPECTED_CROSS_CUTTING_TERMS.items():
            term = parsed[term_id]
            assert term.name == name
            assert fragment in term.definition

    def test_do_not_write_guidance_stays_out_of_definitions(self, vocab):
        """Every ':' line after the first is usage guidance, not definition."""
        for term in vocab.terms:
            if term.category not in ("core_instrument_term", "cross_cutting_term"):
                continue
            assert "Do not write" in term.extra.get("usage_note", ""), (
                f"{term.term_id} lost its 'Do not write' guidance"
            )
            assert "Do not write" not in term.definition, (
                f"{term.term_id} folded usage guidance into its definition"
            )

    def test_cross_cutting_section_does_not_collide_with_framework_terms(self, vocab):
        """'## Framework Terms' and '## Framework Terms (Cross-Cutting)' stay apart.

        The shorter heading is a strict prefix of the longer one. A prefix match
        in either parser silently merges the two sections; both must be exact.
        """
        framework = {t.term_id for t in vocab.terms if t.category == "framework_term"}
        crosscutting = {
            t.term_id for t in vocab.terms if t.category == "cross_cutting_term"
        }
        assert framework == {
            "ontology:validity:framework:tevv",
            "ontology:validity:framework:tse",
            "ontology:validity:framework:fcsm",
        }
        assert not (framework & crosscutting)

    def test_core_instrument_section_does_not_reach_the_next_section(self):
        """Gutting ## Core Instrument Terms must not capture the next section.

        Its neighbour ``## Framework Terms (Cross-Cutting)`` is a definition list
        of exactly the shape this parser reads, so an unbounded scan would
        silently absorb it — the b6714f3 failure mode in a new location.
        """
        from seldon.ontology.parser import _parse_core_instrument_terms

        text = VOCAB_PATH.read_text(encoding="utf-8")
        marker = "## Core Instrument Terms"
        next_marker = "## Framework Terms (Cross-Cutting)"
        head, _, tail = text.partition(marker)
        _, _, rest = tail.partition(next_marker)
        gutted = (
            head + marker + "\n\n*Section temporarily emptied.*\n\n---\n\n"
            + next_marker + rest
        )
        assert _parse_core_instrument_terms(gutted.splitlines()) == []

    def test_emptied_core_instrument_section_fails_loudly(self, tmp_path):
        """A newly claimed section gets the same loud-failure guarantee."""
        text = VOCAB_PATH.read_text(encoding="utf-8")
        marker = "## Core Instrument Terms"
        next_marker = "## Framework Terms (Cross-Cutting)"
        head, _, tail = text.partition(marker)
        _, _, rest = tail.partition(next_marker)
        gutted = (
            head + marker + "\n\n*Section temporarily emptied.*\n\n---\n\n"
            + next_marker + rest
        )
        broken = tmp_path / "VALIDITY_VOCABULARY.md"
        broken.write_text(gutted, encoding="utf-8")

        with pytest.raises(VocabularyParseError) as exc:
            parse_vocabulary(broken)
        assert "Core Instrument Terms" in str(exc.value)
        assert "_parse_core_instrument_terms" in str(exc.value)

    def test_context_window_is_not_minted_twice(self, vocab):
        """'### Core Construct: Context Window' stays unclaimed, on purpose.

        That section defines "Context window", which already reaches the graph
        as ``ontology:validity:related:context_window``. Two active OntologyTerms
        with the same ``name`` make ``seldon glossary generate`` emit two MyST
        ``{glossary}`` entries for one term — a duplicate term description. This
        test enforces the reasoning recorded next to that section's ``(None, 0)``
        entry in SECTION_COVERAGE, so the decision cannot rot into an unnoticed
        omission.
        """
        assert SECTION_COVERAGE["### Core Construct: Context Window"] == (None, 0)
        names = [t.name.strip().lower() for t in vocab.terms]
        dupes = sorted({n for n in names if names.count(n) > 1})
        assert dupes == [], (
            f"duplicate term names would duplicate glossary entries: {dupes}"
        )
