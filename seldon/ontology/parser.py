"""Parser for VALIDITY_VOCABULARY.md — converts canonical vocabulary file to structured data.

Parses the markdown vocabulary file using regex and line-by-line logic (no LLM).
Same input always produces the same output (deterministic).

Per AD-017: Central Validity Ontology.

Section scanning is *bounded*
-----------------------------
Every section parser resolves its heading to an explicit ``(start, end)`` line
range via :func:`_find_section` and scans only inside it.  This is not
stylistic.  The original parsers located their heading and then scanned forward
to "the next thing that looks like my shape" with no stop condition, e.g.::

    while j < len(lines) and not lines[j].strip().startswith("|"):
        j += 1

When commit ``b6714f3`` (2026-03-28) rewrote ``## Related Terms (Defined
Elsewhere)`` from a pipe table into a definition list, that scan walked straight
past the section and parsed the *next* table in the file — ``## Terms That May
Be Promoted from Projects`` — as if it were Related Terms.  For roughly five
months the shared ``seldon-ontology`` master carried two junk terms whose
``definition`` was the literal string ``leibniz-pi`` (an "Origin Project" column
value) while five genuine terms were silently absent.  Nothing failed; the
parse simply produced the wrong terms.

Two mechanisms keep that failure mode from recurring:

1. Bounded scanning makes cross-section leakage structurally impossible.
2. :data:`SECTION_COVERAGE` declares, for every ``##``/``###`` heading in the
   vocabulary file, which parser claims it and how many terms it must yield.
   :func:`parse_vocabulary` enforces the per-section minimums at runtime, and
   ``tests/test_parser_sections.py`` enforces that the declaration and the real
   file agree — so an added, renamed, or reformatted section fails loudly
   instead of silently yielding nothing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ParsedTerm:
    """A single vocabulary term extracted from the vocabulary file."""

    term_id: str
    """Namespaced identifier, e.g. 'ontology:validity:SFV'."""

    name: str
    """Human-readable term name."""

    definition: str
    """Canonical definition text (markdown stripped)."""

    category: str
    """
    One of: framework, sub_dimension, threat, severity, tax, argument,
    countermeasure, metric, classical_validity, terminology_decision,
    framework_term, boilerplate, core_instrument_term, cross_cutting_term,
    related_term.
    """

    citations: list[str]
    """Citation keys found in definition, e.g. ['[Webb-2026a]', '[SCC-2002]']."""

    namespace: str
    """Always 'ontology:validity'."""

    extra: dict
    """Category-specific fields: shorthand, threat_number, tax_rate, etc."""


@dataclass
class ParsedRelationship:
    """A directed relationship between two vocabulary terms."""

    from_term_id: str
    to_term_id: str
    rel_type: str
    """
    One of: defines_sub_dimension, defines_threat, addresses_threat,
    measures_threat, precondition_for.
    """


@dataclass
class ParsedVocabulary:
    """Full structured output of parsing VALIDITY_VOCABULARY.md."""

    source_path: str
    terms: list[ParsedTerm]
    relationships: list[ParsedRelationship]
    content_hash: str
    """SHA-256 of the entire source file."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

__all__ = [
    "parse_vocabulary",
    "ParsedTerm",
    "ParsedRelationship",
    "ParsedVocabulary",
    "VocabularyParseError",
    "SECTION_COVERAGE",
]

_NAMESPACE = "ontology:validity"

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"\*(.+?)\*")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# Multi-citation bracket: [Key1; Key2] — captures the bracket's inner content.
# Also matches single-citation brackets [Webb-2026a].
_MULTI_CITATION_RE = re.compile(
    r"\[([A-Z][\w\-]*-\d{4}[a-z]?(?:\s*;\s*[A-Z][\w\-]*-\d{4}[a-z]?)*)\]"
)
# Individual citation key within a matched bracket group.
_CITATION_KEY_RE = re.compile(r"[A-Z][\w\-]*-\d{4}[a-z]?")

# Markdown definition list: a bold-only line is the term, following ": " lines
# are its definition body.
_DEFN_TERM_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
_DEFN_BODY_RE = re.compile(r"^:\s*(.*)")


def _extract_citations(text: str) -> list[str]:
    """Return all citation keys found in *text* as bracketed tokens.

    Handles both single-key brackets ([Webb-2026a]) and multi-key brackets
    ([SCC-2002; CM-1955]) by splitting on semicolons and wrapping each key
    in its own brackets.  Preserves insertion order; no duplicates.
    """
    citations: list[str] = []
    seen: set[str] = set()
    for m in _MULTI_CITATION_RE.finditer(text):
        inner = m.group(1)
        for key in _CITATION_KEY_RE.findall(inner):
            token = f"[{key}]"
            if token not in seen:
                seen.add(token)
                citations.append(token)
    return citations


def _strip_markdown(text: str) -> str:
    """Remove bold, italic, inline links, and inline code markers from *text*.

    Content is preserved; only the surrounding markers are removed.
    """
    text = _LINK_RE.sub(r"\1", text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    return text.strip()


def _slugify(name: str) -> str:
    """Convert a human-readable name to a lowercase underscore slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug


def _parse_table_rows(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    """Parse a markdown pipe table starting at *start*.

    Returns (rows, next_line_index).  Skips the header row and the separator
    row (the |---|...| line).  Returns only data rows.
    """
    rows: list[list[str]] = []
    i = start
    header_seen = False
    separator_seen = False

    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.split("|")[1:-1]]

        if not header_seen:
            header_seen = True
            i += 1
            continue

        if not separator_seen:
            # separator row: cells contain only dashes/colons
            if all(re.match(r"^[-:]+$", c) for c in cells if c):
                separator_seen = True
                i += 1
                continue

        rows.append(cells)
        i += 1

    return rows, i


# ---------------------------------------------------------------------------
# Section bounds — see the module docstring for why these exist
# ---------------------------------------------------------------------------


class VocabularyParseError(ValueError):
    """Raised when the vocabulary file cannot be parsed as declared.

    Subclasses :class:`ValueError` so existing callers that catch ``ValueError``
    keep working.
    """


def _heading_level(line: str) -> int:
    """Return the ATX heading depth of *line*, or ``0`` if it is not a heading.

    ``"## Foo"`` is level 2, ``"### Foo"`` is level 3.  A run of ``#`` not
    followed by a space (``"#nothashtag"``) is not a heading.
    """
    stripped = line.strip()
    if not stripped.startswith("#"):
        return 0
    level = len(stripped) - len(stripped.lstrip("#"))
    if level > 6:
        return 0
    rest = stripped[level:]
    if rest and not rest.startswith(" "):
        return 0
    return level


def _normalize_heading(line: str) -> str:
    """Collapse a heading line to a comparable form (lowercased, single-spaced)."""
    return re.sub(r"\s+", " ", line.strip()).lower()


def _find_section(
    lines: list[str], heading: str, *, prefix: bool = False
) -> tuple[int, int] | None:
    """Locate the section introduced by *heading* and return its line bounds.

    Args:
        lines: The full vocabulary file split into lines.
        heading: The heading line to match, hashes included
            (e.g. ``"### Sub-dimensions"``).  Matched case-insensitively with
            whitespace collapsed.
        prefix: When True, match any heading that *starts with* *heading*, so a
            trailing parenthetical in the document does not break the parser.

    Returns:
        ``(start, end)`` where *start* is the index of the heading line and
        *end* is one past the last line of the section — i.e. the index of the
        next heading at the same or a shallower level, or ``len(lines)``.
        Returns None if the heading is not present.
    """
    target = _normalize_heading(heading)
    target_level = _heading_level(heading)

    for i, line in enumerate(lines):
        level = _heading_level(line)
        if not level:
            continue
        norm = _normalize_heading(line)
        if norm == target or (prefix and norm.startswith(target)):
            for j in range(i + 1, len(lines)):
                nxt = _heading_level(lines[j])
                if nxt and nxt <= (target_level or level):
                    return i, j
            return i, len(lines)

    return None


def _section_table_rows(
    lines: list[str], heading: str, *, prefix: bool = False
) -> list[list[str]]:
    """Return the data rows of the first pipe table inside section *heading*.

    The search for the table start is bounded by the section, so a section that
    no longer contains a table yields an empty list instead of silently
    capturing the next section's table.

    Returns an empty list if the section is absent or contains no table; the
    caller's declared minimum in :data:`SECTION_COVERAGE` turns that into a
    loud failure.
    """
    bounds = _find_section(lines, heading, prefix=prefix)
    if bounds is None:
        return []
    start, end = bounds

    j = start + 1
    while j < end and not lines[j].strip().startswith("|"):
        j += 1
    if j >= end:
        return []

    rows, _ = _parse_table_rows(lines[:end], j)
    return rows


def _parse_definition_list(
    lines: list[str], start: int, end: int
) -> list[tuple[str, list[str]]]:
    """Parse a markdown definition list from ``lines[start:end]``.

    Recognizes the form used throughout the vocabulary files::

        **Term name**
        : First definition line.
        : Second line — usage note, "do not write" guidance, etc.

    Returns:
        A list of ``(term_name, definition_lines)`` pairs in document order.
        Entries with no ``:`` continuation lines are skipped, since a bold line
        with no definition is a heading-like emphasis, not a term.
    """
    entries: list[tuple[str, list[str]]] = []
    i = start
    while i < end:
        stripped = lines[i].strip()
        m = _DEFN_TERM_RE.match(stripped)
        if not m:
            i += 1
            continue

        term_name = _strip_markdown(m.group(1))
        defn_lines: list[str] = []
        j = i + 1
        while j < end:
            dm = _DEFN_BODY_RE.match(lines[j].strip())
            if not dm:
                # Blank lines inside an entry are tolerated; anything else ends it.
                if not lines[j].strip():
                    j += 1
                    continue
                break
            defn_lines.append(dm.group(1).strip())
            j += 1

        i = j
        if defn_lines:
            entries.append((term_name, defn_lines))

    return entries


#: Declared coverage of every ``##``/``###`` heading in VALIDITY_VOCABULARY.md.
#:
#: Maps the exact heading line to ``(claiming parser, expected term count)``.
#: ``None`` as the parser means the section is intentionally not turned into
#: ontology terms (prose, reference tables, placeholders).
#:
#: The count is enforced at two different strengths, deliberately:
#:
#: * :func:`parse_vocabulary` — runtime, ships to every project — fails if a
#:   claimed section is missing or yields *zero* terms.  That is the shape of the
#:   b6714f3 mis-parse and of any reformatting the parser cannot read.  Editing
#:   one row out of a table is a legitimate vocabulary change and must not break
#:   ingest for every downstream project, so the runtime floor is one, not N.
#: * ``tests/test_parser_sections.py`` — repo CI, against the real file —
#:   enforces the exact count and the exact heading set.  Drift there forces this
#:   table to be updated, which is a deliberate, reviewable one-line act.
#:
#: A new or renamed section therefore forces an explicit decision instead of
#: being silently ignored — or silently swallowed by a neighbouring parser.
#: See the module docstring.
SECTION_COVERAGE: dict[str, tuple[str | None, int]] = {
    "## Purpose": (None, 0),
    "## Sources": (None, 0),  # citation key table, not terms
    "## State Fidelity Validity (SFV)": ("_parse_sfv_term", 1),
    # Deliberately unparsed, and the reason is enforced by
    # tests/test_parser_sections.py::test_context_window_is_not_minted_twice.
    # This section defines "Context window", which ALREADY reaches the graph as
    # ontology:validity:related:context_window via _parse_related_terms. Minting
    # a second node would give two active OntologyTerms with the same `name`,
    # and `seldon glossary generate` renders one MyST {glossary} entry per term
    # by name — a duplicate term description. The Related Terms entry carries the
    # shorter of the two definitions and points here for the full one; promoting
    # the fuller text is a vocabulary-content edit for the vocabulary's author,
    # not something a parser may decide.
    "### Core Construct: Context Window": (None, 0),
    "### Sub-dimensions": ("_parse_sub_dimensions", 5),
    "### Threat Taxonomy": ("_parse_threats", 5),
    "### Severity Scale": ("_parse_severity", 4),
    "### Operationalization: The State Fidelity Tax": ("_parse_tax_tiers", 3),
    "### Key Arguments": ("_parse_key_arguments", 5),
    "### Engineering Countermeasures": ("_parse_countermeasures", 7),
    "### Operationalization Metrics": ("_parse_metrics", 6),
    "### Limitations Boilerplate (for papers using LLM pipelines)": (
        "_parse_boilerplate",
        1,
    ),
    "## Classical Validity Types": ("_parse_classical_validity", 4),
    "### Positioning of SFV Relative to Classical Types": (None, 0),
    "## Key Terminology Decisions": ("_parse_terminology_decisions", 2),
    "### Confabulation (not fabrication, not hallucination)": (None, 0),
    "### Reliability vs. Validity Distinction": (None, 0),
    "### Terms Considered and Rejected": (None, 0),  # feeds terminology extra{}
    "## Framework Terms": ("_parse_framework_terms", 3),
    "### TEVV (Test, Evaluation, Verification, and Validation)": (None, 0),
    "### Total Survey Error (TSE)": (None, 0),
    "### FCSM Data Quality Dimensions": (None, 0),
    "### Construct Validity Audit Methodology (Crosswalk Application)": (None, 0),
    "## Core Instrument Terms": ("_parse_core_instrument_terms", 5),
    "## Framework Terms (Cross-Cutting)": ("_parse_cross_cutting_terms", 1),
    "## Related Terms (Defined Elsewhere)": ("_parse_related_terms", 5),
    "## Terms That May Be Promoted from Projects": (None, 0),  # placeholder
}

#: Maps a parser name in :data:`SECTION_COVERAGE` to the ``ParsedTerm.category``
#: it produces, so ``parse_vocabulary`` can check the declared minimums against
#: what was actually parsed.
_PARSER_CATEGORY: dict[str, str] = {
    "_parse_sfv_term": "framework",
    "_parse_sub_dimensions": "sub_dimension",
    "_parse_threats": "threat",
    "_parse_severity": "severity",
    "_parse_tax_tiers": "tax",
    "_parse_key_arguments": "argument",
    "_parse_countermeasures": "countermeasure",
    "_parse_metrics": "metric",
    "_parse_boilerplate": "boilerplate",
    "_parse_classical_validity": "classical_validity",
    "_parse_terminology_decisions": "terminology_decision",
    "_parse_framework_terms": "framework_term",
    "_parse_core_instrument_terms": "core_instrument_term",
    "_parse_cross_cutting_terms": "cross_cutting_term",
    "_parse_related_terms": "related_term",
}


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------


def _parse_sfv_term(lines: list[str]) -> ParsedTerm | None:
    """Parse the primary SFV framework term definition."""
    for line in lines:
        if line.startswith("**State Fidelity Validity (SFV):**"):
            raw = line[len("**State Fidelity Validity (SFV):**"):].strip()
            definition = _strip_markdown(raw)
            citations = _extract_citations(raw)
            return ParsedTerm(
                term_id=f"{_NAMESPACE}:SFV",
                name="State Fidelity Validity",
                definition=definition,
                category="framework",
                citations=citations,
                namespace=_NAMESPACE,
                extra={"shorthand": "SFV"},
            )
    return None


def _parse_sub_dimensions(lines: list[str]) -> list[ParsedTerm]:
    """Parse sub-dimension table rows from ``### Sub-dimensions``."""
    terms: list[ParsedTerm] = []

    for row in _section_table_rows(lines, "### Sub-dimensions"):
        if len(row) < 3:
            continue
        canonical_name, shorthand, definition_raw = row[0], row[1], row[2]
        terms.append(
            ParsedTerm(
                term_id=f"{_NAMESPACE}:SFV:{shorthand}",
                name=canonical_name,
                definition=_strip_markdown(definition_raw),
                category="sub_dimension",
                citations=_extract_citations(definition_raw),
                namespace=_NAMESPACE,
                extra={"shorthand": shorthand},
            )
        )

    return terms


def _parse_threats(lines: list[str]) -> list[ParsedTerm]:
    """Parse threat taxonomy table rows from ``### Threat Taxonomy``."""
    terms: list[ParsedTerm] = []

    for row in _section_table_rows(lines, "### Threat Taxonomy"):
        if len(row) < 3:
            continue
        number, name, desc_raw = row[0], row[1], row[2]
        terms.append(
            ParsedTerm(
                term_id=f"{_NAMESPACE}:SFV:{number}",
                name=name,
                definition=_strip_markdown(desc_raw),
                category="threat",
                citations=_extract_citations(desc_raw),
                namespace=_NAMESPACE,
                extra={"threat_number": number},
            )
        )

    return terms


def _parse_severity(lines: list[str]) -> list[ParsedTerm]:
    """Parse severity scale table rows from ``### Severity Scale``."""
    terms: list[ParsedTerm] = []

    for row in _section_table_rows(lines, "### Severity Scale"):
        if len(row) < 2:
            continue
        level, desc_raw = row[0], row[1]
        terms.append(
            ParsedTerm(
                term_id=f"{_NAMESPACE}:severity:{_slugify(level)}",
                name=level,
                definition=_strip_markdown(desc_raw),
                category="severity",
                citations=_extract_citations(desc_raw),
                namespace=_NAMESPACE,
                extra={},
            )
        )

    return terms


def _parse_tax_tiers(lines: list[str]) -> list[ParsedTerm]:
    """Parse the tolerable variance tier table from the State Fidelity Tax section.

    Keyed on the ``**Tolerable Variance Tiers:**`` lead-in, but the search for
    that lead-in — and for the table under it — is confined to
    ``### Operationalization: The State Fidelity Tax``.
    """
    terms: list[ParsedTerm] = []

    bounds = _find_section(lines, "### Operationalization: The State Fidelity Tax")
    if bounds is None:
        return terms
    start, end = bounds

    for i in range(start, end):
        if "**Tolerable Variance Tiers:**" in lines[i]:
            j = i + 1
            while j < end and not lines[j].strip().startswith("|"):
                j += 1
            if j >= end:
                break
            rows, _ = _parse_table_rows(lines[:end], j)
            for row in rows:
                if len(row) < 4:
                    continue
                level, tax_rate, desc_raw, tolerability = (
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                )
                slug = level.lower()
                definition = _strip_markdown(desc_raw)
                citations = _extract_citations(desc_raw)
                terms.append(
                    ParsedTerm(
                        term_id=f"{_NAMESPACE}:tax:{slug}",
                        name=level,
                        definition=definition,
                        category="tax",
                        citations=citations,
                        namespace=_NAMESPACE,
                        extra={
                            "tax_rate": tax_rate,
                            "tolerability": _strip_markdown(tolerability),
                        },
                    )
                )
            break

    return terms


def _parse_key_arguments(lines: list[str]) -> list[ParsedTerm]:
    """Parse numbered key arguments under ``### Key Arguments``."""
    terms: list[ParsedTerm] = []

    bounds = _find_section(lines, "### Key Arguments")
    if bounds is None:
        return terms
    start, section_end = bounds
    start += 1
    lines = lines[:section_end]

    # Collect numbered list items; each spans until the next numbered item or
    # blank-line-then-heading.
    arg_re = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*(.*)")
    i = start
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("###") or line.strip().startswith("##"):
            break

        m = arg_re.match(line.strip())
        if m:
            number_str, bold_lead, rest = m.group(1), m.group(2), m.group(3)
            # Accumulate continuation lines (indented or same paragraph)
            full_text_parts = [rest] if rest else []
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    # blank line — peek ahead
                    k = j + 1
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    # If next non-blank starts a numbered item or heading, stop
                    if k < len(lines) and (
                        arg_re.match(lines[k].strip())
                        or lines[k].strip().startswith("#")
                    ):
                        j = k
                        break
                    # Otherwise it's a continuation paragraph
                    j = k
                    continue
                if arg_re.match(next_line) or next_line.startswith("#"):
                    break
                full_text_parts.append(next_line)
                j += 1

            i = j
            raw_definition = " ".join(full_text_parts).strip()
            full_raw = f"**{bold_lead}** {raw_definition}".strip()
            definition = _strip_markdown(full_raw)
            citations = _extract_citations(full_raw)
            terms.append(
                ParsedTerm(
                    term_id=f"{_NAMESPACE}:argument:{number_str}",
                    name=bold_lead,
                    definition=definition,
                    category="argument",
                    citations=citations,
                    namespace=_NAMESPACE,
                    extra={"argument_number": int(number_str)},
                )
            )
            continue

        i += 1

    return terms


def _parse_countermeasures(lines: list[str]) -> list[ParsedTerm]:
    """Parse the ``### Engineering Countermeasures`` table."""
    terms: list[ParsedTerm] = []

    for row in _section_table_rows(lines, "### Engineering Countermeasures"):
        if len(row) < 3:
            continue
        name_raw, threat_field, impl_raw = row[0], row[1], row[2]
        name = _strip_markdown(name_raw)
        impl = _strip_markdown(impl_raw)
        # Extract T-codes from threat_field: T1, T2, etc.
        threat_refs = re.findall(r"\bT\d+\b", threat_field)
        terms.append(
            ParsedTerm(
                term_id=f"{_NAMESPACE}:countermeasure:{_slugify(name)}",
                name=name,
                definition=impl,  # implementation text serves as definition
                category="countermeasure",
                citations=_extract_citations(name_raw + " " + impl_raw),
                namespace=_NAMESPACE,
                extra={"implementation": impl, "threat_refs": threat_refs},
            )
        )

    return terms


def _parse_metrics(lines: list[str]) -> list[ParsedTerm]:
    """Parse the ``### Operationalization Metrics`` table."""
    terms: list[ParsedTerm] = []

    for row in _section_table_rows(lines, "### Operationalization Metrics"):
        if len(row) < 3:
            continue
        metric_raw, what_measures_raw, threat_field = row[0], row[1], row[2]
        name = _strip_markdown(metric_raw)
        what_measures = _strip_markdown(what_measures_raw)
        threat_refs = re.findall(r"\bT\d+\b", threat_field)
        terms.append(
            ParsedTerm(
                term_id=f"{_NAMESPACE}:metric:{_slugify(name)}",
                name=name,
                definition=what_measures,
                category="metric",
                citations=_extract_citations(metric_raw + " " + what_measures_raw),
                namespace=_NAMESPACE,
                extra={
                    "what_it_measures": what_measures,
                    "threat_refs": threat_refs,
                },
            )
        )

    return terms


def _parse_classical_validity(lines: list[str]) -> list[ParsedTerm]:
    """Parse classical validity types from ## Classical Validity Types section."""
    terms: list[ParsedTerm] = []

    bounds = _find_section(lines, "## Classical Validity Types")
    if bounds is None:
        return terms
    start, section_end = bounds
    start += 1

    # Definitions use pattern: **Name:** text  (bold name followed by colon)
    # Matches "**Name:**" (colon inside bold) or "**Name**:" (colon outside bold)
    defn_re = re.compile(r"^\*\*(.+?):\*\*\s*(.*)|^\*\*(.+?)\*\*:\s*(.*)")
    slug_map = {
        "Construct Validity": "construct",
        "Internal Validity": "internal",
        "External Validity": "external",
        "Statistical Conclusion Validity": "statistical_conclusion",
    }

    for i in range(start, section_end):
        line = lines[i].strip()
        m = defn_re.match(line)
        if m:
            # Alternation: first alt uses groups 1,2; second uses groups 3,4
            name = m.group(1) if m.group(1) is not None else m.group(3)
            raw_def = m.group(2) if m.group(2) is not None else m.group(4)
            if name not in slug_map:
                continue
            slug = slug_map[name]
            definition = _strip_markdown(raw_def)
            citations = _extract_citations(raw_def)
            terms.append(
                ParsedTerm(
                    term_id=f"{_NAMESPACE}:classical:{slug}",
                    name=name,
                    definition=definition,
                    category="classical_validity",
                    citations=citations,
                    namespace=_NAMESPACE,
                    extra={},
                )
            )

    return terms


def _parse_terminology_decisions(lines: list[str]) -> list[ParsedTerm]:
    """Parse key terminology decisions section."""
    terms: list[ParsedTerm] = []

    bounds = _find_section(lines, "## Key Terminology Decisions")
    if bounds is None:
        return terms
    start, section_end = bounds
    start += 1

    # --- Confabulation ---
    for i in range(start, section_end):
        line = lines[i].strip()
        if line.startswith("**Confabulation:**"):
            raw_def = line[len("**Confabulation:**"):].strip()
            # Collect continuation lines up to blank line
            j = i + 1
            while j < section_end and lines[j].strip():
                raw_def += " " + lines[j].strip()
                j += 1
            definition = _strip_markdown(raw_def)
            citations = _extract_citations(raw_def)

            # Extract rejected terms from the "Terms Considered and Rejected"
            # table — a subsection of this one, so bounded to it.
            rejected_terms = [
                r[0]
                for r in _section_table_rows(
                    lines[:section_end], "### Terms Considered and Rejected"
                )
                if r
            ]

            terms.append(
                ParsedTerm(
                    term_id=f"{_NAMESPACE}:terminology:confabulation",
                    name="Confabulation",
                    definition=definition,
                    category="terminology_decision",
                    citations=citations,
                    namespace=_NAMESPACE,
                    extra={"terms_considered_rejected": rejected_terms},
                )
            )
            break

    # --- Reliability vs. Validity ---
    # The "Reliability vs. Validity Distinction" entry is the combined definition
    # of Reliability + Validity + Application to SFV paragraph.
    rv_bounds = _find_section(
        lines[:section_end], "### Reliability vs. Validity Distinction"
    )
    if rv_bounds is not None:
        rv_start, rv_end = rv_bounds
        parts = [lines[j].strip() for j in range(rv_start + 1, rv_end) if lines[j].strip()]
        raw_def = " ".join(parts)
        terms.append(
            ParsedTerm(
                term_id=f"{_NAMESPACE}:terminology:reliability_vs_validity",
                name="Reliability vs. Validity Distinction",
                definition=_strip_markdown(raw_def),
                category="terminology_decision",
                citations=_extract_citations(raw_def),
                namespace=_NAMESPACE,
                extra={},
            )
        )

    return terms


def _parse_framework_terms(lines: list[str]) -> list[ParsedTerm]:
    """Parse TEVV, TSE, and FCSM framework term definitions.

    Confined to ``## Framework Terms``.  Note that ``## Framework Terms
    (Cross-Cutting)`` is a *different* section further down the file; the
    heading match here is exact, not prefix, so the two do not collide.
    """
    terms: list[ParsedTerm] = []

    bounds = _find_section(lines, "## Framework Terms")
    if bounds is None:
        return terms
    lines = lines[bounds[0]:bounds[1]]

    # TEVV
    for line in lines:
        if line.strip().startswith("**TEVV:**"):
            raw = line.strip()[len("**TEVV:**"):].strip()
            definition = _strip_markdown(raw)
            citations = _extract_citations(raw)
            terms.append(
                ParsedTerm(
                    term_id=f"{_NAMESPACE}:framework:tevv",
                    name="TEVV",
                    definition=definition,
                    category="framework_term",
                    citations=citations,
                    namespace=_NAMESPACE,
                    extra={},
                )
            )
            break

    # Total Survey Error
    for line in lines:
        if line.strip().startswith("**Total Survey Error:**"):
            raw = line.strip()[len("**Total Survey Error:**"):].strip()
            definition = _strip_markdown(raw)
            citations = _extract_citations(raw)
            terms.append(
                ParsedTerm(
                    term_id=f"{_NAMESPACE}:framework:tse",
                    name="Total Survey Error",
                    definition=definition,
                    category="framework_term",
                    citations=citations,
                    namespace=_NAMESPACE,
                    extra={},
                )
            )
            break

    # FCSM — definition is the introductory line before the dimension table
    for i, line in enumerate(lines):
        if "### FCSM Data Quality Dimensions" in line:
            # The definition follows on the next non-blank line
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                raw = lines[j].strip()
                # If it looks like a table row, skip — look for prose line
                if not raw.startswith("|"):
                    definition = _strip_markdown(raw)
                    citations = _extract_citations(raw)
                    terms.append(
                        ParsedTerm(
                            term_id=f"{_NAMESPACE}:framework:fcsm",
                            name="FCSM Data Quality Dimensions",
                            definition=definition,
                            category="framework_term",
                            citations=citations,
                            namespace=_NAMESPACE,
                            extra={},
                        )
                    )
            break

    return terms


def _parse_boilerplate(lines: list[str]) -> list[ParsedTerm]:
    """Parse the limitations boilerplate blockquote.

    Matched by heading prefix so the trailing parenthetical
    ("(for papers using LLM pipelines)") can be reworded without breaking the
    parser; the scan for the blockquote is still bounded by the section.
    """
    terms: list[ParsedTerm] = []

    bounds = _find_section(lines, "### Limitations Boilerplate", prefix=True)
    if bounds is None:
        return terms
    start, end = bounds

    parts = [
        lines[j].strip()[1:].strip()
        for j in range(start + 1, end)
        if lines[j].strip().startswith(">")
    ]
    if parts:
        raw = " ".join(parts)
        terms.append(
            ParsedTerm(
                term_id=f"{_NAMESPACE}:boilerplate:limitations",
                name="Limitations Boilerplate",
                definition=_strip_markdown(raw),
                category="boilerplate",
                citations=_extract_citations(raw),
                namespace=_NAMESPACE,
                extra={},
            )
        )

    return terms


def _parse_related_terms(lines: list[str]) -> list[ParsedTerm]:
    """Parse the definition list under ``## Related Terms (Defined Elsewhere)``.

    The section is a markdown definition list::

        **Handoff document**
        : Explicit serialization of accumulated state for session continuity.
        : Use precisely; do not conflate with ...

    The first ``:`` line is the definition.  Any further ``:`` lines are usage
    guidance and are kept in ``extra["usage_note"]`` rather than folded into the
    definition, because the definition is what downstream consumers cite.

    Only the definition-list form is supported.  This section was a pipe table
    until commit ``b6714f3`` (2026-03-28); nothing in the repo has used that form
    since, ``ontology/practitioner/PRACTITIONER_VOCABULARY.md`` contains no
    tables at all, and a permissive "parse whichever shape turns up next" scan is
    precisely what caused the regression this function exists to fix.  A revert
    to the table form is caught by the section minimum in
    :data:`SECTION_COVERAGE`, not silently absorbed.
    """
    return _parse_definition_list_section(
        lines,
        heading="## Related Terms (Defined Elsewhere)",
        id_segment="related",
        category="related_term",
    )


def _parse_definition_list_section(
    lines: list[str], *, heading: str, id_segment: str, category: str
) -> list[ParsedTerm]:
    """Parse one bounded definition-list section into terms.

    Three sections of the vocabulary share exactly this shape::

        **Term name**
        : The definition.
        : Do not write: "some synonym" (why not).

    The first ``:`` line is the definition. Any further ``:`` lines are usage
    guidance and are kept in ``extra["usage_note"]`` rather than folded into the
    definition, because the definition is what downstream consumers cite.

    Only the definition-list form is supported. A section that is reformatted
    into a table yields nothing here and is caught by the section minimum in
    :data:`SECTION_COVERAGE` — a permissive "parse whichever shape turns up
    next" scan is precisely the b6714f3 failure this module exists to prevent.

    Args:
        lines: The full vocabulary file split into lines.
        heading: Exact heading line introducing the section.
        id_segment: Segment placed after the namespace in each ``term_id``.
        category: :attr:`ParsedTerm.category` stamped on every term produced.

    Returns:
        Terms in document order; empty when the section is absent.
    """
    terms: list[ParsedTerm] = []

    bounds = _find_section(lines, heading)
    if bounds is None:
        return terms
    start, end = bounds

    for name, defn_lines in _parse_definition_list(lines, start + 1, end):
        raw_definition = defn_lines[0]
        usage_note = " ".join(defn_lines[1:]).strip()
        extra: dict = {}
        if usage_note:
            extra["usage_note"] = _strip_markdown(usage_note)
        terms.append(
            ParsedTerm(
                term_id=f"{_NAMESPACE}:{id_segment}:{_slugify(name)}",
                name=name,
                definition=_strip_markdown(raw_definition),
                category=category,
                citations=_extract_citations(" ".join(defn_lines)),
                namespace=_NAMESPACE,
                extra=extra,
            )
        )

    return terms


def _parse_core_instrument_terms(lines: list[str]) -> list[ParsedTerm]:
    """Parse the definition list under ``## Core Instrument Terms``.

    Added to the vocabulary by commit ``62d6bdf`` (2026-04-17) and claimed by no
    parser until 2026-09-04, so its five terms — accumulated state, operative
    state, composite instrument, token limit, instrument stability assumption —
    had never reached the shared master despite being enforced for glossary
    checking by ``ontology/validity/vocabulary_rules.yaml``.
    """
    return _parse_definition_list_section(
        lines,
        heading="## Core Instrument Terms",
        id_segment="instrument",
        category="core_instrument_term",
    )


def _parse_cross_cutting_terms(lines: list[str]) -> list[ParsedTerm]:
    """Parse the definition list under ``## Framework Terms (Cross-Cutting)``.

    A *different* section from ``## Framework Terms`` further up the file, which
    :func:`_parse_framework_terms` claims. Both heading matches are exact, not
    prefix, so the two cannot collide — the shorter heading is a strict prefix
    of the longer one and a prefix match here would silently merge them.
    """
    return _parse_definition_list_section(
        lines,
        heading="## Framework Terms (Cross-Cutting)",
        id_segment="crosscutting",
        category="cross_cutting_term",
    )


# ---------------------------------------------------------------------------
# Relationship builders
# ---------------------------------------------------------------------------


def _build_relationships(
    sfv_term: ParsedTerm | None,
    sub_dims: list[ParsedTerm],
    threats: list[ParsedTerm],
    countermeasures: list[ParsedTerm],
    metrics: list[ParsedTerm],
    classical: list[ParsedTerm],
) -> list[ParsedRelationship]:
    """Build all directed relationships between parsed terms."""
    rels: list[ParsedRelationship] = []

    if sfv_term is None:
        return rels

    sfv_id = sfv_term.term_id

    # SFV → sub_dimensions
    for t in sub_dims:
        rels.append(
            ParsedRelationship(
                from_term_id=sfv_id,
                to_term_id=t.term_id,
                rel_type="defines_sub_dimension",
            )
        )

    # SFV → threats
    threat_by_number: dict[str, str] = {}
    for t in threats:
        rels.append(
            ParsedRelationship(
                from_term_id=sfv_id,
                to_term_id=t.term_id,
                rel_type="defines_threat",
            )
        )
        threat_by_number[t.extra["threat_number"]] = t.term_id

    # countermeasure → addresses_threat
    for cm in countermeasures:
        for tcode in cm.extra.get("threat_refs", []):
            target_id = threat_by_number.get(tcode)
            if target_id:
                rels.append(
                    ParsedRelationship(
                        from_term_id=cm.term_id,
                        to_term_id=target_id,
                        rel_type="addresses_threat",
                    )
                )

    # metric → measures_threat
    for m in metrics:
        for tcode in m.extra.get("threat_refs", []):
            target_id = threat_by_number.get(tcode)
            if target_id:
                rels.append(
                    ParsedRelationship(
                        from_term_id=m.term_id,
                        to_term_id=target_id,
                        rel_type="measures_threat",
                    )
                )

    # SFV → precondition_for each classical validity type
    for ct in classical:
        rels.append(
            ParsedRelationship(
                from_term_id=sfv_id,
                to_term_id=ct.term_id,
                rel_type="precondition_for",
            )
        )

    return rels


# ---------------------------------------------------------------------------
# Parse-completeness guard
# ---------------------------------------------------------------------------


def _check_section_yields(
    all_terms: list[ParsedTerm], lines: list[str], path: Path
) -> None:
    """Fail loudly when a claimed section is missing or produced nothing.

    For every entry in :data:`SECTION_COVERAGE` that names a parser, this
    verifies (a) that the heading is still present in the document and (b) that
    the parser produced at least one term in that section's category.

    A section that was reformatted, renamed, or emptied therefore raises here
    rather than quietly contributing nothing to the shared ontology — the
    failure mode that let the ``## Related Terms (Defined Elsewhere)`` mis-parse
    survive from 2026-03-28 to 2026-09-04.

    The floor is deliberately one term, not the declared count: dropping a single
    row from a table is a legitimate vocabulary edit, and breaking ingest for
    every downstream project over it would be a worse failure than the one being
    prevented. Exact counts are asserted in ``tests/test_parser_sections.py``
    against the real file, where a change is reviewable.

    Raises:
        VocabularyParseError: If a claimed section is missing or yields nothing.
    """
    by_category: dict[str, int] = {}
    for term in all_terms:
        by_category[term.category] = by_category.get(term.category, 0) + 1

    problems: list[str] = []
    for heading, (parser_name, expected) in SECTION_COVERAGE.items():
        if parser_name is None or expected == 0:
            continue
        prefix = heading.startswith("### Limitations Boilerplate")
        if _find_section(lines, heading, prefix=prefix) is None:
            problems.append(
                f"section {heading!r} is claimed by {parser_name}() but is not "
                f"present in the file"
            )
            continue
        category = _PARSER_CATEGORY[parser_name]
        if by_category.get(category, 0) == 0:
            problems.append(
                f"section {heading!r} yielded no terms of category {category!r} "
                f"via {parser_name}(), but the section is present. Its content no "
                f"longer matches the shape {parser_name}() parses"
            )

    if problems:
        raise VocabularyParseError(
            f"Vocabulary parse incomplete for {path}:\n  - "
            + "\n  - ".join(problems)
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_vocabulary(path: Path | str) -> ParsedVocabulary:
    """Parse VALIDITY_VOCABULARY.md and return structured vocabulary.

    Args:
        path: Path to the VALIDITY_VOCABULARY.md file.

    Returns:
        ParsedVocabulary with all extracted terms, relationships, and a
        SHA-256 content hash of the source file.

    Raises:
        FileNotFoundError: If the file does not exist at *path*.
        ValueError: If the file cannot be parsed (missing required sections).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Vocabulary file not found: {path}")

    raw_content = path.read_text(encoding="utf-8")
    content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
    lines = raw_content.splitlines()

    # Parse all term groups
    sfv_term = _parse_sfv_term(lines)
    if sfv_term is None:
        raise ValueError(
            "Could not parse primary SFV term. Check that the vocabulary file "
            "contains '**State Fidelity Validity (SFV):**' on a single line."
        )

    sub_dims = _parse_sub_dimensions(lines)
    threats = _parse_threats(lines)
    severity = _parse_severity(lines)
    tax = _parse_tax_tiers(lines)
    arguments = _parse_key_arguments(lines)
    countermeasures = _parse_countermeasures(lines)
    metrics = _parse_metrics(lines)
    classical = _parse_classical_validity(lines)
    terminology = _parse_terminology_decisions(lines)
    framework_terms = _parse_framework_terms(lines)
    boilerplate = _parse_boilerplate(lines)
    core_instrument = _parse_core_instrument_terms(lines)
    cross_cutting = _parse_cross_cutting_terms(lines)
    related = _parse_related_terms(lines)

    all_terms: list[ParsedTerm] = (
        [sfv_term]
        + sub_dims
        + threats
        + severity
        + tax
        + arguments
        + countermeasures
        + metrics
        + classical
        + terminology
        + framework_terms
        + boilerplate
        + core_instrument
        + cross_cutting
        + related
    )

    _check_section_yields(all_terms, lines, path)

    relationships = _build_relationships(
        sfv_term=sfv_term,
        sub_dims=sub_dims,
        threats=threats,
        countermeasures=countermeasures,
        metrics=metrics,
        classical=classical,
    )

    return ParsedVocabulary(
        source_path=str(path),
        terms=all_terms,
        relationships=relationships,
        content_hash=content_hash,
    )
