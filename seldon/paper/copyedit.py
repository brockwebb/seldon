"""
Paper Copy Edit module — Tier 0 (mechanical defects).

Catches deterministic copy-edit issues that slip through fast edit cycles:
duplicate sentences/paragraphs, orphaned references, formatting artifacts,
heading hierarchy gaps, leftover markers.

All checks are purely mechanical — no LLM needed.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

from seldon.paper.qc import (
    Violation,
    _line_number_of,
    _split_paragraphs,
    _split_sentences,
    _strip_skipped_regions,
    _truncate,
    format_violations,
)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "paper"


def load_copyedit_config(config_path: Optional[Path] = None) -> dict:
    """Load paper_copyedit_config.yaml. Falls back to templates default."""
    path = config_path if config_path is not None else _TEMPLATES_DIR / "paper_copyedit_config.yaml"
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

_CITE_RE = re.compile(r"\{cite:[pt]\}`[^`]*`")


def _normalize_sentence(s: str) -> str:
    """Normalize a sentence for duplicate comparison."""
    s = _CITE_RE.sub("", s)
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    s = s.strip().strip(".,;:!?\"'()[]")
    return s


def _word_count(s: str) -> int:
    return len(s.split())


# ---------------------------------------------------------------------------
# CE-01: Duplicate sentences
# ---------------------------------------------------------------------------

def check_CE_01(
    text: str, config: dict, filename: str, *, global_sentences: Optional[Dict[str, List[str]]] = None
) -> List[Violation]:
    """Flag exact-duplicate sentences (normalized) within a file or across files."""
    rules = config.get("copyedit_rules", {}).get("duplicate_sentence", {})
    if not rules.get("enabled", True):
        return []

    min_words = rules.get("min_words", 6)
    processed = _strip_skipped_regions(text)
    violations = []

    sentences_with_loc: list[tuple[str, int]] = []
    for para in _split_paragraphs(processed):
        for sent in _split_sentences(para):
            norm = _normalize_sentence(sent)
            if _word_count(norm) < min_words:
                continue
            line = _line_number_of(text, text.find(sent[:30])) if sent[:30] in text else 1
            sentences_with_loc.append((norm, line))

    # Within-file duplicates
    seen: dict[str, int] = {}
    for norm, line in sentences_with_loc:
        if norm in seen:
            violations.append(Violation(
                check_id="CE-01",
                file=filename,
                line=line,
                message=f"Duplicate sentence (first at line {seen[norm]})",
                text=_truncate(norm),
            ))
        else:
            seen[norm] = line

    # Cross-file duplicates
    if global_sentences is not None:
        for norm, line in sentences_with_loc:
            if norm in global_sentences:
                for other_file in global_sentences[norm]:
                    if other_file != filename:
                        violations.append(Violation(
                            check_id="CE-01",
                            file=filename,
                            line=line,
                            message=f"Duplicate sentence also in {other_file}",
                            text=_truncate(norm),
                        ))
                        break
                global_sentences[norm].append(filename)
            else:
                global_sentences[norm] = [filename]

    return violations


# ---------------------------------------------------------------------------
# CE-02: Duplicate paragraphs
# ---------------------------------------------------------------------------

def check_CE_02(text: str, config: dict, filename: str) -> List[Violation]:
    """Flag duplicate paragraphs within a file."""
    rules = config.get("copyedit_rules", {}).get("duplicate_paragraph", {})
    if not rules.get("enabled", True):
        return []

    min_words = rules.get("min_words", 15)
    processed = _strip_skipped_regions(text)
    violations = []

    paras = _split_paragraphs(processed)
    seen: dict[str, int] = {}

    for para in paras:
        norm = _normalize_sentence(para)
        if _word_count(norm) < min_words:
            continue
        line = _line_number_of(text, text.find(para[:40])) if para[:40] in text else 1
        if norm in seen:
            violations.append(Violation(
                check_id="CE-02",
                file=filename,
                line=line,
                message=f"Duplicate paragraph (first at line {seen[norm]})",
                text=_truncate(norm),
            ))
        else:
            seen[norm] = line

    return violations


# ---------------------------------------------------------------------------
# CE-03: Near-duplicate phrases (n-gram overlap)
# ---------------------------------------------------------------------------

def check_CE_03(text: str, config: dict, filename: str) -> List[Violation]:
    """Flag repeated n-grams within a file."""
    rules = config.get("copyedit_rules", {}).get("near_duplicate_phrases", {})
    if not rules.get("enabled", True):
        return []

    ngram_size = rules.get("ngram_size", 8)
    min_occ = rules.get("min_occurrences", 2)
    excludes = set(rules.get("exclude_patterns", []))

    processed = _strip_skipped_regions(text)
    words = processed.lower().split()
    violations = []

    ngram_positions: dict[str, list[int]] = {}
    for i in range(len(words) - ngram_size + 1):
        ngram = " ".join(words[i:i + ngram_size])
        if ngram in excludes:
            continue
        ngram_positions.setdefault(ngram, []).append(i)

    reported: set[str] = set()
    for ngram, positions in ngram_positions.items():
        if len(positions) >= min_occ and ngram not in reported:
            # Find approximate line number from char offset
            char_offset = len(" ".join(words[:positions[1]]))
            line = _line_number_of(processed, min(char_offset, len(processed) - 1))
            violations.append(Violation(
                check_id="CE-03",
                file=filename,
                line=line,
                message=f"Near-duplicate phrase appears {len(positions)} times",
                text=_truncate(ngram),
            ))
            reported.add(ngram)

    return violations


# ---------------------------------------------------------------------------
# CE-04: Orphaned section references
# ---------------------------------------------------------------------------

def check_CE_04(
    text: str, config: dict, filename: str, *, heading_sections: Optional[Set[str]] = None
) -> List[Violation]:
    """Flag 'Section N' references where N doesn't match any heading."""
    rules = config.get("copyedit_rules", {}).get("orphaned_refs", {})
    if not rules.get("enabled", True):
        return []

    violations = []

    # Build heading section numbers from this file if not provided externally
    if heading_sections is None:
        heading_sections = set()
        for m in re.finditer(r"^#+\s+", text, re.MULTILINE):
            # Extract section number from filename pattern or heading
            pass
        # Try to extract from headings that contain numbers
        for m in re.finditer(r"^#+\s+(?:Section\s+)?(\d+)", text, re.MULTILINE):
            heading_sections.add(m.group(1))
        # Also add numbers derived from filename (e.g., 03_classical_validity → "3")
        fname_match = re.match(r"(\d+)_", Path(filename).stem)
        if fname_match:
            heading_sections.add(str(int(fname_match.group(1))))

    ref_patterns = rules.get("ref_patterns", [r'Section\s+(\d+)'])
    processed = _strip_skipped_regions(text)

    for pat_str in ref_patterns:
        for m in re.finditer(pat_str, processed):
            ref_num = m.group(1)
            if ref_num not in heading_sections:
                line = _line_number_of(text, m.start())
                violations.append(Violation(
                    check_id="CE-04",
                    file=filename,
                    line=line,
                    message=f"Reference to Section {ref_num} — no matching heading found",
                    text=_truncate(m.group(0)),
                ))

    return violations


# ---------------------------------------------------------------------------
# CE-05: Orphaned citations
# ---------------------------------------------------------------------------

def check_CE_05(
    text: str, config: dict, filename: str, *, bib_keys: Optional[Set[str]] = None
) -> List[Violation]:
    """Flag citation keys not found in references.bib."""
    rules = config.get("copyedit_rules", {}).get("orphaned_citations", {})
    if not rules.get("enabled", True):
        return []
    if bib_keys is None:
        return []  # No bib file provided — skip

    violations = []
    cite_patterns = rules.get("cite_patterns", [r'\{cite:[pt]\}`([^`]+)`'])

    for pat_str in cite_patterns:
        for m in re.finditer(pat_str, text):
            raw_keys = m.group(1)
            # Handle comma-separated keys: {cite:p}`key1,key2,key3`
            keys = [k.strip() for k in raw_keys.split(",")]
            for key in keys:
                if key and key not in bib_keys:
                    line = _line_number_of(text, m.start())
                    violations.append(Violation(
                        check_id="CE-05",
                        file=filename,
                        line=line,
                        message=f"Citation key '{key}' not found in references.bib",
                        text=_truncate(m.group(0)),
                    ))

    return violations


# ---------------------------------------------------------------------------
# CE-06: Formatting artifacts
# ---------------------------------------------------------------------------

_REF_TOKEN_RE = re.compile(r"\{\{[^}]*\}\}")


def _mask_reference_tokens(line: str) -> str:
    """Replace every {{...}} token with a same-length run of a non-space sentinel.

    Preserves column positions (unlike deleting the token) without turning the
    token into whitespace (unlike _strip_skipped_regions), so whitespace checks
    see the token as opaque text rather than as a gap.
    """
    return _REF_TOKEN_RE.sub(lambda m: "\x00" * len(m.group(0)), line)


def check_CE_06(text: str, config: dict, filename: str) -> List[Violation]:
    """Flag mechanical formatting defects."""
    rules = config.get("copyedit_rules", {}).get("formatting", {})
    if not rules.get("enabled", True):
        return []

    checks = set(rules.get("checks", []))
    processed = _strip_skipped_regions(text)
    violations = []

    lines = text.splitlines()
    proc_lines = processed.splitlines()

    for i, (raw_line, proc_line) in enumerate(zip(lines, proc_lines), start=1):
        # Double spaces. `proc_line.strip()` skips lines that are entirely a
        # blanked region (fenced code, frontmatter). The search itself runs on
        # the raw line with {{...}} tokens masked to a non-space sentinel:
        # _strip_skipped_regions blanks tokens to same-length whitespace, so an
        # unresolved token such as "See {{figure:x}} for" would otherwise read
        # as a double space (root-caused 2026-09-02, xref passthrough failure).
        if (
            "double_spaces" in checks
            and proc_line.strip()
            and "  " in _mask_reference_tokens(raw_line)
        ):
            violations.append(Violation(
                check_id="CE-06", file=filename, line=i,
                message="Double space in prose",
                text=_truncate(raw_line),
            ))

        # Repeated punctuation (.., ,,) but not ellipsis (...)
        if "repeated_punctuation" in checks:
            for m in re.finditer(r'([.!?,;:])\1', proc_line):
                if m.group(0) == ".." and proc_line[max(0, m.start()-1):m.end()+1] == "...":
                    continue  # part of ellipsis
                violations.append(Violation(
                    check_id="CE-06", file=filename, line=i,
                    message=f"Repeated punctuation: '{m.group(0)}'",
                    text=_truncate(raw_line),
                ))

        # Trailing whitespace
        if "trailing_whitespace" in checks and raw_line != raw_line.rstrip():
            violations.append(Violation(
                check_id="CE-06", file=filename, line=i,
                message="Trailing whitespace",
                text=_truncate(raw_line),
            ))

        # Non-breaking spaces
        if "non_breaking_spaces" in checks and "\u00a0" in raw_line:
            violations.append(Violation(
                check_id="CE-06", file=filename, line=i,
                message="Non-breaking space (U+00A0)",
                text=_truncate(raw_line),
            ))

        # Tab characters (in processed text to skip code blocks)
        if "tab_characters" in checks and "\t" in proc_line and proc_line.strip():
            violations.append(Violation(
                check_id="CE-06", file=filename, line=i,
                message="Tab character in prose",
                text=_truncate(raw_line),
            ))

    # Mixed quotes (file-level check)
    if "mixed_quotes" in checks:
        has_straight = bool(re.search(r'["\']', processed))
        has_smart = bool(re.search(r'[\u201c\u201d\u2018\u2019]', processed))
        if has_straight and has_smart:
            violations.append(Violation(
                check_id="CE-06", file=filename, line=1,
                message="Mixed straight and smart quotes in same file",
                text="(file-level check)",
            ))

    return violations


# ---------------------------------------------------------------------------
# CE-07: Heading hierarchy gaps
# ---------------------------------------------------------------------------

def check_CE_07(text: str, config: dict, filename: str) -> List[Violation]:
    """Flag heading level jumps (e.g., ## followed by #### with no ###)."""
    rules = config.get("copyedit_rules", {}).get("heading_hierarchy", {})
    if not rules.get("enabled", True):
        return []

    violations = []
    prev_level = 0

    for i, line in enumerate(text.splitlines(), start=1):
        m = re.match(r"^(#{1,6})\s+", line)
        if m:
            level = len(m.group(1))
            if prev_level > 0 and level > prev_level + 1:
                violations.append(Violation(
                    check_id="CE-07",
                    file=filename,
                    line=i,
                    message=f"Heading jump: level {prev_level} → {level} (skipped {level - prev_level - 1} level(s))",
                    text=_truncate(line),
                ))
            prev_level = level

    return violations


# ---------------------------------------------------------------------------
# CE-08: Leftover markers
# ---------------------------------------------------------------------------

def check_CE_08(text: str, config: dict, filename: str) -> List[Violation]:
    """Flag TODO/FIXME/HACK/etc. markers left in text."""
    rules = config.get("copyedit_rules", {}).get("markers", {})
    if not rules.get("enabled", True):
        return []

    patterns = rules.get("patterns", ["TODO", "FIXME", "XXX", "HACK", "PLACEHOLDER", "TBD"])
    processed = _strip_skipped_regions(text)
    violations = []

    for pat in patterns:
        for m in re.finditer(re.escape(pat), processed):
            line = _line_number_of(text, m.start())
            violations.append(Violation(
                check_id="CE-08",
                file=filename,
                line=line,
                message=f"Leftover marker: {pat}",
                text=_truncate(text.splitlines()[line - 1] if line <= len(text.splitlines()) else ""),
            ))

    return violations


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_copyedit(
    text: str,
    config: dict,
    filename: str = "<string>",
    *,
    bib_keys: Optional[Set[str]] = None,
    heading_sections: Optional[Set[str]] = None,
    global_sentences: Optional[Dict[str, List[str]]] = None,
) -> List[Violation]:
    """Run all CE checks on a single file's text. Returns violations."""
    violations: List[Violation] = []
    violations.extend(check_CE_01(text, config, filename, global_sentences=global_sentences))
    violations.extend(check_CE_02(text, config, filename))
    violations.extend(check_CE_03(text, config, filename))
    violations.extend(check_CE_04(text, config, filename, heading_sections=heading_sections))
    violations.extend(check_CE_05(text, config, filename, bib_keys=bib_keys))
    violations.extend(check_CE_06(text, config, filename))
    violations.extend(check_CE_07(text, config, filename))
    violations.extend(check_CE_08(text, config, filename))
    return violations


# ---------------------------------------------------------------------------
# Bib parsing helper
# ---------------------------------------------------------------------------

def parse_bib_keys(bib_path: Path) -> Set[str]:
    """Extract all entry keys from a .bib file."""
    keys: Set[str] = set()
    with open(bib_path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"@\w+\{([^,]+),", line)
            if m:
                keys.add(m.group(1).strip())
    return keys
