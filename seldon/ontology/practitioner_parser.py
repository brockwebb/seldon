"""Parser for PRACTITIONER_VOCABULARY.md — converts practitioner/domain terms to structured data.

Format expected:
    ## Section Name   ← maps to category
    **term name**
    : Definition sentence one. Sentence two.
    : *Citations:* [Key-2026a]
    : *Projects:* project-slug

Section headings map to categories:
    ## Practitioner Terms   → practitioner_term
    ## Design Patterns      → design_pattern
    ## Domain Terms         → domain_term
    ## Governance Terms     → governance_term

Term IDs use the namespace `ontology:practitioner:<slug>`.

Per AD-017: Central Validity Ontology.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from seldon.ontology.parser import (
    ParsedTerm,
    ParsedRelationship,
    ParsedVocabulary,
    _extract_citations,
    _strip_markdown,
    _slugify,
)

__all__ = ["parse_practitioner_vocabulary"]

_NAMESPACE = "ontology:practitioner"

# Map section heading text → category value
_SECTION_CATEGORY_MAP = {
    "practitioner terms": "practitioner_term",
    "design patterns": "design_pattern",
    "domain terms": "domain_term",
    "governance terms": "governance_term",
}

_TERM_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
_DEFINITION_LINE_RE = re.compile(r"^:\s*(.*)")
_CITATIONS_RE = re.compile(r"^\*Citations:\*\s*(.*)", re.IGNORECASE)
_PROJECTS_RE = re.compile(r"^\*Projects:\*\s*(.*)", re.IGNORECASE)


def parse_practitioner_vocabulary(path: Path | str) -> ParsedVocabulary:
    """Parse PRACTITIONER_VOCABULARY.md and return structured vocabulary.

    Args:
        path: Path to the PRACTITIONER_VOCABULARY.md file.

    Returns:
        ParsedVocabulary with all extracted terms, empty relationships list,
        and a SHA-256 content hash of the source file.

    Raises:
        FileNotFoundError: If the file does not exist at path.
        ValueError: If no terms could be parsed from the file.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Practitioner vocabulary file not found: {path}")

    raw_content = path.read_text(encoding="utf-8")
    content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
    lines = raw_content.splitlines()

    terms: list[ParsedTerm] = []
    current_category = "practitioner_term"

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Section heading → category
        if stripped.startswith("## "):
            heading = stripped[3:].strip().lower()
            current_category = _SECTION_CATEGORY_MAP.get(heading, current_category)
            i += 1
            continue

        # Skip top-level headings (#) and separators
        if stripped.startswith("# ") or stripped == "---" or not stripped:
            i += 1
            continue

        # Term line: **term name**
        m = _TERM_RE.match(stripped)
        if m:
            term_name = _strip_markdown(m.group(1))
            definition_parts: list[str] = []
            citations: list[str] = []

            # Collect definition lines (: ...) immediately following
            j = i + 1
            while j < len(lines):
                next_stripped = lines[j].strip()
                dm = _DEFINITION_LINE_RE.match(next_stripped)
                if dm:
                    content = dm.group(1).strip()
                    # Check if this is a metadata line
                    if _CITATIONS_RE.match(content):
                        cm = _CITATIONS_RE.match(content)
                        raw_cit = cm.group(1).strip()
                        citations = _extract_citations(raw_cit)
                    elif _PROJECTS_RE.match(content):
                        pass  # Skip — projects metadata, not part of definition
                    else:
                        definition_parts.append(content)
                    j += 1
                else:
                    break

            i = j  # advance past this term block

            if not definition_parts:
                # No definition — skip silently
                continue

            raw_definition = " ".join(definition_parts)
            definition = _strip_markdown(raw_definition)
            # Also extract inline citations from definition text itself
            inline_citations = _extract_citations(raw_definition)
            # Merge, deduplicating
            all_citations = list(dict.fromkeys(citations + inline_citations))

            slug = _slugify(term_name)
            term_id = f"{_NAMESPACE}:{slug}"

            terms.append(
                ParsedTerm(
                    term_id=term_id,
                    name=term_name,
                    definition=definition,
                    category=current_category,
                    citations=all_citations,
                    namespace=_NAMESPACE,
                    extra={},
                )
            )
            continue

        i += 1

    if not terms:
        raise ValueError(
            f"No terms parsed from practitioner vocabulary file: {path}. "
            "Check that terms follow the '**term name**' / ': definition' format."
        )

    return ParsedVocabulary(
        source_path=str(path),
        terms=terms,
        relationships=[],
        content_hash=content_hash,
    )
