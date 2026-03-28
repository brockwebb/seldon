"""Parser for VALIDITY_VOCABULARY.md — converts canonical vocabulary file to structured data.

Parses the markdown vocabulary file using regex and line-by-line logic (no LLM).
Same input always produces the same output (deterministic).

Per AD-017: Central Validity Ontology.
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
    framework_term, boilerplate, related_term.
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

__all__ = ["parse_vocabulary", "ParsedTerm", "ParsedRelationship", "ParsedVocabulary"]

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
    """Parse sub-dimension table rows."""
    terms: list[ParsedTerm] = []

    # Find the ### Sub-dimensions heading
    for i, line in enumerate(lines):
        if line.strip().lower() == "### sub-dimensions":
            # Advance to the table (skip blank lines)
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("|"):
                j += 1
            rows, _ = _parse_table_rows(lines, j)
            for row in rows:
                if len(row) < 3:
                    continue
                canonical_name, shorthand, definition_raw = row[0], row[1], row[2]
                definition = _strip_markdown(definition_raw)
                citations = _extract_citations(definition_raw)
                terms.append(
                    ParsedTerm(
                        term_id=f"{_NAMESPACE}:SFV:{shorthand}",
                        name=canonical_name,
                        definition=definition,
                        category="sub_dimension",
                        citations=citations,
                        namespace=_NAMESPACE,
                        extra={"shorthand": shorthand},
                    )
                )
            break

    return terms


def _parse_threats(lines: list[str]) -> list[ParsedTerm]:
    """Parse threat taxonomy table rows."""
    terms: list[ParsedTerm] = []

    for i, line in enumerate(lines):
        if line.strip().lower() == "### threat taxonomy":
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("|"):
                j += 1
            rows, _ = _parse_table_rows(lines, j)
            for row in rows:
                if len(row) < 3:
                    continue
                number, name, desc_raw = row[0], row[1], row[2]
                definition = _strip_markdown(desc_raw)
                citations = _extract_citations(desc_raw)
                terms.append(
                    ParsedTerm(
                        term_id=f"{_NAMESPACE}:SFV:{number}",
                        name=name,
                        definition=definition,
                        category="threat",
                        citations=citations,
                        namespace=_NAMESPACE,
                        extra={"threat_number": number},
                    )
                )
            break

    return terms


def _parse_severity(lines: list[str]) -> list[ParsedTerm]:
    """Parse severity scale table rows."""
    terms: list[ParsedTerm] = []

    for i, line in enumerate(lines):
        if line.strip().lower() == "### severity scale":
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("|"):
                j += 1
            rows, _ = _parse_table_rows(lines, j)
            for row in rows:
                if len(row) < 2:
                    continue
                level, desc_raw = row[0], row[1]
                slug = _slugify(level)
                definition = _strip_markdown(desc_raw)
                citations = _extract_citations(desc_raw)
                terms.append(
                    ParsedTerm(
                        term_id=f"{_NAMESPACE}:severity:{slug}",
                        name=level,
                        definition=definition,
                        category="severity",
                        citations=citations,
                        namespace=_NAMESPACE,
                        extra={},
                    )
                )
            break

    return terms


def _parse_tax_tiers(lines: list[str]) -> list[ParsedTerm]:
    """Parse tolerable variance tier table rows."""
    terms: list[ParsedTerm] = []

    for i, line in enumerate(lines):
        if "**Tolerable Variance Tiers:**" in line:
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("|"):
                j += 1
            rows, _ = _parse_table_rows(lines, j)
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
    """Parse numbered key arguments under ### Key Arguments."""
    terms: list[ParsedTerm] = []

    # Find the heading
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "### key arguments":
            start = i + 1
            break

    if start is None:
        return terms

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
    """Parse engineering countermeasures table."""
    terms: list[ParsedTerm] = []

    for i, line in enumerate(lines):
        if line.strip().lower() == "### engineering countermeasures":
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("|"):
                j += 1
            rows, _ = _parse_table_rows(lines, j)
            for row in rows:
                if len(row) < 3:
                    continue
                name_raw, threat_field, impl_raw = row[0], row[1], row[2]
                name = _strip_markdown(name_raw)
                slug = _slugify(name)
                impl = _strip_markdown(impl_raw)
                # Extract T-codes from threat_field: T1, T2, etc.
                threat_refs = re.findall(r"\bT\d+\b", threat_field)
                definition = impl  # implementation text serves as definition
                citations = _extract_citations(name_raw + " " + impl_raw)
                terms.append(
                    ParsedTerm(
                        term_id=f"{_NAMESPACE}:countermeasure:{slug}",
                        name=name,
                        definition=definition,
                        category="countermeasure",
                        citations=citations,
                        namespace=_NAMESPACE,
                        extra={"implementation": impl, "threat_refs": threat_refs},
                    )
                )
            break

    return terms


def _parse_metrics(lines: list[str]) -> list[ParsedTerm]:
    """Parse operationalization metrics table."""
    terms: list[ParsedTerm] = []

    for i, line in enumerate(lines):
        if line.strip().lower() == "### operationalization metrics":
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("|"):
                j += 1
            rows, _ = _parse_table_rows(lines, j)
            for row in rows:
                if len(row) < 3:
                    continue
                metric_raw, what_measures_raw, threat_field = (
                    row[0],
                    row[1],
                    row[2],
                )
                name = _strip_markdown(metric_raw)
                slug = _slugify(name)
                what_measures = _strip_markdown(what_measures_raw)
                threat_refs = re.findall(r"\bT\d+\b", threat_field)
                definition = what_measures
                citations = _extract_citations(metric_raw + " " + what_measures_raw)
                terms.append(
                    ParsedTerm(
                        term_id=f"{_NAMESPACE}:metric:{slug}",
                        name=name,
                        definition=definition,
                        category="metric",
                        citations=citations,
                        namespace=_NAMESPACE,
                        extra={
                            "what_it_measures": what_measures,
                            "threat_refs": threat_refs,
                        },
                    )
                )
            break

    return terms


def _parse_classical_validity(lines: list[str]) -> list[ParsedTerm]:
    """Parse classical validity types from ## Classical Validity Types section."""
    terms: list[ParsedTerm] = []

    # Find section start
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "## classical validity types":
            start = i + 1
            break

    if start is None:
        return terms

    # Definitions use pattern: **Name:** text  (bold name followed by colon)
    # Matches "**Name:**" (colon inside bold) or "**Name**:" (colon outside bold)
    defn_re = re.compile(r"^\*\*(.+?):\*\*\s*(.*)|^\*\*(.+?)\*\*:\s*(.*)")
    slug_map = {
        "Construct Validity": "construct",
        "Internal Validity": "internal",
        "External Validity": "external",
        "Statistical Conclusion Validity": "statistical_conclusion",
    }

    for i in range(start, len(lines)):
        line = lines[i].strip()
        if line.startswith("## ") and i > start:
            break
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

    # Find section start
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "## key terminology decisions":
            start = i + 1
            break

    if start is None:
        return terms

    # --- Confabulation ---
    for i in range(start, len(lines)):
        line = lines[i].strip()
        if line.startswith("## ") and i > start:
            break
        if line.startswith("**Confabulation:**"):
            raw_def = line[len("**Confabulation:**"):].strip()
            # Collect continuation lines up to blank line
            j = i + 1
            while j < len(lines) and lines[j].strip():
                raw_def += " " + lines[j].strip()
                j += 1
            definition = _strip_markdown(raw_def)
            citations = _extract_citations(raw_def)

            # Extract rejected terms from the "Terms Considered and Rejected" table
            rejected_terms: list[str] = []
            for k, tl in enumerate(lines):
                if tl.strip().lower() == "### terms considered and rejected":
                    tj = k + 1
                    while tj < len(lines) and not lines[tj].strip().startswith("|"):
                        tj += 1
                    rows, _ = _parse_table_rows(lines, tj)
                    rejected_terms = [r[0] for r in rows if r]
                    break

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
    for i in range(start, len(lines)):
        line = lines[i].strip()
        if line.startswith("## ") and i > start:
            break
        if line.strip().lower() == "### reliability vs. validity distinction":
            # Collect everything from here until next ### or ## section
            parts: list[str] = []
            j = i + 1
            while j < len(lines):
                tl = lines[j].strip()
                if tl.startswith("## ") or tl.startswith("### "):
                    break
                if tl:
                    parts.append(tl)
                j += 1
            raw_def = " ".join(parts)
            definition = _strip_markdown(raw_def)
            citations = _extract_citations(raw_def)
            terms.append(
                ParsedTerm(
                    term_id=f"{_NAMESPACE}:terminology:reliability_vs_validity",
                    name="Reliability vs. Validity Distinction",
                    definition=definition,
                    category="terminology_decision",
                    citations=citations,
                    namespace=_NAMESPACE,
                    extra={},
                )
            )
            break

    return terms


def _parse_framework_terms(lines: list[str]) -> list[ParsedTerm]:
    """Parse TEVV, TSE, and FCSM framework term definitions."""
    terms: list[ParsedTerm] = []

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
    """Parse limitations boilerplate blockquote."""
    terms: list[ParsedTerm] = []

    for i, line in enumerate(lines):
        if "### Limitations Boilerplate" in line:
            # Find the blockquote (lines starting with ">")
            parts: list[str] = []
            j = i + 1
            while j < len(lines):
                tl = lines[j]
                stripped = tl.strip()
                if stripped.startswith(">"):
                    parts.append(stripped[1:].strip())
                elif stripped.startswith("###") or stripped.startswith("##"):
                    break
                j += 1
            if parts:
                raw = " ".join(parts)
                definition = _strip_markdown(raw)
                citations = _extract_citations(raw)
                terms.append(
                    ParsedTerm(
                        term_id=f"{_NAMESPACE}:boilerplate:limitations",
                        name="Limitations Boilerplate",
                        definition=definition,
                        category="boilerplate",
                        citations=citations,
                        namespace=_NAMESPACE,
                        extra={},
                    )
                )
            break

    return terms


def _parse_related_terms(lines: list[str]) -> list[ParsedTerm]:
    """Parse related terms table under ## Related Terms (Defined Elsewhere)."""
    terms: list[ParsedTerm] = []

    for i, line in enumerate(lines):
        if line.strip().lower() == "## related terms (defined elsewhere)":
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("|"):
                j += 1
            rows, _ = _parse_table_rows(lines, j)
            for row in rows:
                if len(row) < 3:
                    continue
                term_name, brief_meaning_raw, canonical_source = (
                    row[0],
                    row[1],
                    row[2],
                )
                name = _strip_markdown(term_name)
                slug = _slugify(name)
                definition = _strip_markdown(brief_meaning_raw)
                citations = _extract_citations(brief_meaning_raw)
                terms.append(
                    ParsedTerm(
                        term_id=f"{_NAMESPACE}:related:{slug}",
                        name=name,
                        definition=definition,
                        category="related_term",
                        citations=citations,
                        namespace=_NAMESPACE,
                        extra={"canonical_source": canonical_source},
                    )
                )
            break

    return terms


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
        + related
    )

    # Guard: fail loudly if any mandatory category is missing entirely,
    # which indicates a section heading mismatch or corrupted vocabulary file.
    _EXPECTED_MINIMUMS = {
        "sub_dimension": 1,
        "threat": 1,
        "countermeasure": 1,
        "metric": 1,
        "classical_validity": 1,
    }
    by_category = {cat: sum(1 for t in all_terms if t.category == cat) for cat in _EXPECTED_MINIMUMS}
    for cat, minimum in _EXPECTED_MINIMUMS.items():
        if by_category.get(cat, 0) < minimum:
            raise ValueError(
                f"Expected at least {minimum} term(s) in category '{cat}', got "
                f"{by_category.get(cat, 0)}. Check section headings in {path}."
            )

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
