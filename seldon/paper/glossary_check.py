"""
Portable glossary enforcement for seldon verify and seldon paper glossary.

Reads enforcement rules from vocabulary_rules.yaml companion files (one per
vocabulary markdown file in the shared ontology). Scans paper section files
for banned synonym violations and builds a keyword concordance index.

Architecture:
  vocabulary_rules.yaml   — machine-readable enforcement rules (banned phrases, exemptions)
  VALIDITY_VOCABULARY.md  — human-readable definitions (source for seldon paper glossary)
  seldon verify           — calls run_glossary_check() to enforce banned synonyms
  seldon paper glossary   — calls get_term_definitions() + scan_* to produce reader glossary
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Vocabulary rule loading
# ---------------------------------------------------------------------------

def find_vocabulary_rule_files(vocab_paths: list[Path]) -> list[Path]:
    """Return vocabulary_rules.yaml companions that exist alongside vocabulary MDs."""
    return [
        p.parent / "vocabulary_rules.yaml"
        for p in vocab_paths
        if (p.parent / "vocabulary_rules.yaml").exists()
    ]


def load_vocabulary_rules(
    rule_paths: list[Path],
) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    """Load enforcement rules from one or more vocabulary_rules.yaml files.

    Args:
        rule_paths: Paths to vocabulary_rules.yaml files.

    Returns:
        terms:      {term_name: ""}  — term names tracked for keyword index
        banned:     {banned_phrase_lower: preferred_term}
        exemptions: {banned_phrase_lower: [exempt_context_lower]}
    """
    terms: dict[str, str] = {}
    banned: dict[str, str] = {}
    exemptions: dict[str, list[str]] = {}

    for rule_path in rule_paths:
        data = yaml.safe_load(rule_path.read_text(encoding="utf-8")) or {}
        for term_name, entry in (data.get("rules") or {}).items():
            terms[term_name] = ""
            for item in (entry.get("banned") or []):
                phrase = item["phrase"].lower()
                banned[phrase] = term_name
            for ctx in (entry.get("exemptions") or []):
                banned_phrases_for_term = [
                    item["phrase"].lower()
                    for item in (entry.get("banned") or [])
                ]
                for bp in banned_phrases_for_term:
                    exemptions.setdefault(bp, []).append(ctx.lower())

    return terms, banned, exemptions


# ---------------------------------------------------------------------------
# Vocabulary definition extraction (for seldon paper glossary)
# ---------------------------------------------------------------------------

def get_term_definitions(vocab_paths: list[Path]) -> dict[str, str]:
    """Extract short definitions for bold-header terms from vocabulary markdown files.

    Parses entries of the form:
        **Term Name**
        : First definition sentence. ...
        : Do not write: ...

    Returns {term_name: first_definition_line} for terms found in bold-header format.
    """
    definitions: dict[str, str] = {}
    bold_header = re.compile(r'^\*\*(.+?)\*\*[:\s]*$')

    for vocab_path in vocab_paths:
        if not vocab_path.exists():
            continue
        text = vocab_path.read_text(encoding="utf-8")
        current_term: Optional[str] = None
        got_def = False

        for line in text.splitlines():
            m = bold_header.match(line.strip())
            if m:
                current_term = m.group(1).strip().rstrip(":")
                got_def = False
                continue

            if current_term and not got_def and line.startswith(":"):
                body = line[1:].strip()
                # Skip enforcement/metadata lines; first real prose line is the definition
                skip_prefixes = (
                    "Do not write:", "EXEMPT:", "Abbreviation:", "Note:",
                    "Citations:", "Projects:", "*Citations:", "*Projects:",
                )
                if not any(body.startswith(p) for p in skip_prefixes) and body:
                    definitions[current_term] = body
                    got_def = True

    return definitions


# ---------------------------------------------------------------------------
# Section scanning
# ---------------------------------------------------------------------------

def scan_section(
    section_path: Path,
    terms: dict[str, str],
    banned: dict[str, str],
    exemptions: dict[str, list[str]],
) -> tuple[dict[str, list[int]], list[tuple[int, str, str]]]:
    """Scan a section file for term occurrences and banned synonym violations.

    Returns:
        found:      {term_name: [line_numbers]}
        violations: [(line_number, banned_phrase, preferred_term)]

    Violations are suppressed when an exempt context phrase appears on the same line.
    """
    text = section_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    found: dict[str, list[int]] = defaultdict(list)
    violations: list[tuple[int, str, str]] = []

    for i, line in enumerate(lines, 1):
        line_lower = line.lower()

        for term_name in terms:
            pattern = re.escape(term_name.lower())
            if re.search(r'\b' + pattern + r'\b', line_lower):
                found[term_name].append(i)

        for banned_phrase, preferred in banned.items():
            pattern = re.escape(banned_phrase)
            if re.search(r'\b' + pattern + r'\b', line_lower):
                exempt = any(
                    ctx in line_lower
                    for ctx in exemptions.get(banned_phrase, [])
                )
                if not exempt:
                    violations.append((i, banned_phrase, preferred))

    return dict(found), violations


# ---------------------------------------------------------------------------
# Full check runner
# ---------------------------------------------------------------------------

def run_glossary_check(
    rule_paths: list[Path],
    section_paths: list[Path],
    index_output_path: Optional[Path] = None,
) -> tuple[int, list[str]]:
    """Run the full glossary enforcement check across all section files.

    Args:
        rule_paths:        vocabulary_rules.yaml files to load rules from.
        section_paths:     Section markdown files to scan.
        index_output_path: If given, write keyword_index.md here.

    Returns:
        (violation_count, violation_messages)
        violation_messages are formatted as "filename:line: phrase → preferred"
    """
    terms, banned, exemptions = load_vocabulary_rules(rule_paths)

    index: dict[str, dict[str, list[int]]] = defaultdict(dict)
    all_violations: list[tuple[str, int, str, str]] = []

    for sf in section_paths:
        section_name = sf.stem
        found, violations = scan_section(sf, terms, banned, exemptions)

        for term, line_nums in found.items():
            index[term][section_name] = line_nums

        for line_num, phrase, preferred in violations:
            all_violations.append((sf.name, line_num, phrase, preferred))

    if index_output_path is not None:
        _write_keyword_index(index, terms, index_output_path)

    messages = [
        f"  {filename}:{line_num}: \"{phrase}\" → use \"{preferred}\""
        for filename, line_num, phrase, preferred in sorted(all_violations)
    ]
    return len(all_violations), messages


def _write_keyword_index(
    index: dict[str, dict[str, list[int]]],
    terms: dict[str, str],
    output_path: Path,
) -> None:
    """Write keyword_index.md showing which terms appear in which sections."""
    lines = [
        "# Keyword Index",
        "",
        "Auto-generated by `seldon verify`. Do not edit manually.",
        "",
        "Shows which controlled vocabulary terms appear in which sections.",
        "",
        "---",
        "",
    ]

    for term in sorted(index.keys(), key=str.lower):
        sections_info = [
            f"{section} ({len(line_nums)})"
            for section, line_nums in sorted(index[term].items())
        ]
        lines.append(f"**{term}**: {', '.join(sections_info)}")
        lines.append("")

    unused = [t for t in terms if t not in index]
    if unused:
        lines.extend([
            "---",
            "",
            "## Unused Terms",
            "",
            "Controlled vocabulary terms not found in any section:",
            "",
        ])
        for t in sorted(unused, key=str.lower):
            lines.append(f"- {t}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
