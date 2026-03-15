"""
Paper QC module — Tier 2 (prose quality) and Tier 3 (style preferences).

All checks operate on a pre-processed version of the text where fenced code
blocks, YAML frontmatter, and {{...}} reference tokens are replaced with
whitespace so that line numbers are preserved and false positives are avoided.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    check_id: str      # e.g., "PQ-01"
    file: str          # filename or "<string>"
    line: int          # 1-based line number
    message: str       # human-readable description
    text: str          # offending text snippet (truncated to ~80 chars)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "paper"


def load_qc_config(config_path: Optional[Path] = None) -> dict:
    """Load paper_qc_config.yaml. Falls back to templates default."""
    path = config_path if config_path is not None else _TEMPLATES_DIR / "paper_qc_config.yaml"
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_style_config(config_path: Optional[Path] = None) -> dict:
    """Load paper_style_config.yaml. Falls back to templates default."""
    path = config_path if config_path is not None else _TEMPLATES_DIR / "paper_style_config.yaml"
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Pre-processing helpers
# ---------------------------------------------------------------------------

def _strip_skipped_regions(text: str) -> str:
    """
    Return a version of *text* where fenced code blocks (```...```),
    YAML frontmatter (---...--- at file start), and {{...}} reference tokens
    are replaced with blank spaces of the same length (preserving line numbers).
    Does NOT strip — replaces with whitespace.
    """
    result = list(text)

    # 1. YAML frontmatter: --- at very beginning of file
    fm_match = re.match(r"^---\r?\n(.*?\r?\n)---\r?\n", text, re.DOTALL)
    if fm_match:
        start, end = fm_match.span()
        for i in range(start, end):
            if result[i] not in ("\n", "\r"):
                result[i] = " "

    # 2. Fenced code blocks: ``` ... ```
    for m in re.finditer(r"```.*?```", text, re.DOTALL):
        start, end = m.span()
        for i in range(start, end):
            if result[i] not in ("\n", "\r"):
                result[i] = " "

    # 3. {{...}} reference tokens
    for m in re.finditer(r"\{\{[^}]*\}\}", text):
        start, end = m.span()
        for i in range(start, end):
            if result[i] not in ("\n", "\r"):
                result[i] = " "

    return "".join(result)


# ---------------------------------------------------------------------------
# Sentence and paragraph splitting
# ---------------------------------------------------------------------------

# Abbreviations whose trailing period should NOT trigger a sentence split.
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr",
    "e.g", "i.e", "etc", "vs", "fig", "eq", "ref", "no", "vol",
}

_ABBREV_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(a) for a in _ABBREVIATIONS) + r")\.",
    re.IGNORECASE,
)


def _split_sentences(text: str) -> List[str]:
    """
    Split *text* into sentences.  Handles common abbreviations so they don't
    trigger false splits.  Splits on '. ', '! ', '? '.
    """
    # Replace abbreviation periods with a placeholder to prevent splitting.
    placeholder = "\x00"
    protected = _ABBREV_RE.sub(lambda m: m.group().replace(".", placeholder), text)

    # Split on sentence-ending punctuation followed by whitespace.
    parts = re.split(r"(?<=[.!?])\s+", protected)

    # Restore placeholders.
    sentences = [p.replace(placeholder, ".").strip() for p in parts if p.strip()]
    return sentences


def _split_paragraphs(text: str) -> List[str]:
    """
    Split on double newlines.  Skip headings (lines starting with #),
    YAML frontmatter lines, code blocks (including their interior), and
    table rows (lines starting with |).
    Returns paragraphs that contain at least one non-skipped line.
    """
    raw_paragraphs = re.split(r"\n\s*\n", text)
    result = []
    for para in raw_paragraphs:
        lines = para.splitlines()
        kept = []
        in_code_fence = False
        for line in lines:
            stripped = line.strip()
            # Toggle fence state
            if stripped.startswith("```"):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence:
                continue
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            if stripped.startswith("|"):
                continue
            if stripped.startswith("---"):
                continue
            kept.append(line)
        if kept:
            result.append("\n".join(kept))
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _line_number_of(text: str, char_offset: int) -> int:
    """Return 1-based line number for *char_offset* in *text*."""
    return text.count("\n", 0, char_offset) + 1


def _truncate(s: str, n: int = 80) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def _para_start_line(full_text: str, para_text: str) -> int:
    """Return 1-based line number where *para_text* begins inside *full_text*."""
    idx = full_text.find(para_text)
    if idx == -1:
        return 1
    return _line_number_of(full_text, idx)


# ---------------------------------------------------------------------------
# Tier 2 checks
# ---------------------------------------------------------------------------

def check_PQ_01(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """PQ-01: Flag sentences exceeding max_sentence_words."""
    max_words = config["prose_rules"]["max_sentence_words"]
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    violations: List[Violation] = []

    for para in _split_paragraphs(stripped):
        for sentence in _split_sentences(para):
            word_count = len(sentence.split())
            if word_count > max_words:
                # Find the line number of this sentence in the original text.
                idx = stripped.find(sentence)
                lineno = _line_number_of(stripped, idx) if idx != -1 else 1
                violations.append(Violation(
                    check_id="PQ-01",
                    file=filename,
                    line=lineno,
                    message=f"Sentence too long ({word_count} words, max {max_words})",
                    text=_truncate(sentence),
                ))
    return violations


def check_PQ_02(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """PQ-02: Flag paragraphs with too few or too many sentences."""
    min_s = config["prose_rules"]["min_paragraph_sentences"]
    max_s = config["prose_rules"]["max_paragraph_sentences"]
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    violations: List[Violation] = []

    for para in _split_paragraphs(stripped):
        sentences = _split_sentences(para)
        count = len(sentences)
        if count < min_s:
            lineno = _para_start_line(stripped, para)
            violations.append(Violation(
                check_id="PQ-02",
                file=filename,
                line=lineno,
                message=f"Paragraph has {count} sentence(s) (min {min_s})",
                text=_truncate(para),
            ))
        elif count > max_s:
            lineno = _para_start_line(stripped, para)
            violations.append(Violation(
                check_id="PQ-02",
                file=filename,
                line=lineno,
                message=f"Paragraph has {count} sentences (max {max_s})",
                text=_truncate(para),
            ))
    return violations


def check_PQ_03(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """PQ-03: Flag inline bold (**text**) outside headings and tables."""
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    stripped_lines = stripped.splitlines()
    violations: List[Violation] = []
    bold_re = re.compile(r"\*\*[^*]+\*\*")

    for lineno_0, line in enumerate(stripped_lines):
        stripped_line = line.strip()
        if stripped_line.startswith("#"):
            continue
        if stripped_line.startswith("|"):
            continue
        for m in bold_re.finditer(line):
            violations.append(Violation(
                check_id="PQ-03",
                file=filename,
                line=lineno_0 + 1,
                message="Inline bold in prose (use bold only in headings/labels)",
                text=_truncate(m.group()),
            ))
    return violations


def check_PQ_04(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """PQ-04: Flag em dashes (U+2014) and spaced double hyphens ( -- )."""
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    stripped_lines = stripped.splitlines()
    violations: List[Violation] = []
    em_dash_re = re.compile(r"—| -- ")

    for lineno_0, line in enumerate(stripped_lines):
        for m in em_dash_re.finditer(line):
            violations.append(Violation(
                check_id="PQ-04",
                file=filename,
                line=lineno_0 + 1,
                message="Em dash or spaced double hyphen found (use comma, colon, or restructure)",
                text=_truncate(line),
            ))
    return violations


def check_PQ_05(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """PQ-05: Flag semicolons in sentences exceeding no_semicolons_over_words."""
    threshold = config["prose_rules"]["no_semicolons_over_words"]
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    violations: List[Violation] = []

    for para in _split_paragraphs(stripped):
        for sentence in _split_sentences(para):
            if ";" in sentence and len(sentence.split()) > threshold:
                idx = stripped.find(sentence)
                lineno = _line_number_of(stripped, idx) if idx != -1 else 1
                violations.append(Violation(
                    check_id="PQ-05",
                    file=filename,
                    line=lineno,
                    message=(
                        f"Semicolon in long sentence "
                        f"({len(sentence.split())} words, threshold {threshold})"
                    ),
                    text=_truncate(sentence),
                ))
    return violations


_HEDGE_WORDS = [
    "may", "might", "could", "possibly", "potentially", "perhaps",
    "appears", "seems", "suggests",
]


def check_PQ_06(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """PQ-06: Flag sentences with 2+ hedge words (hedge stacking)."""
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    violations: List[Violation] = []

    hedge_patterns = [re.compile(r"\b" + w + r"\b", re.IGNORECASE) for w in _HEDGE_WORDS]

    for para in _split_paragraphs(stripped):
        for sentence in _split_sentences(para):
            count = sum(1 for p in hedge_patterns if p.search(sentence))
            if count >= 2:
                idx = stripped.find(sentence)
                lineno = _line_number_of(stripped, idx) if idx != -1 else 1
                violations.append(Violation(
                    check_id="PQ-06",
                    file=filename,
                    line=lineno,
                    message=f"Hedge stacking: {count} hedge words in one sentence",
                    text=_truncate(sentence),
                ))
    return violations


_AMBIGUOUS_VERBS = {
    "is", "was", "were", "has", "have", "had",
    "shows", "suggests", "indicates", "demonstrates", "implies",
    "means", "represents", "provides", "offers", "gives",
    "allows", "enables", "ensures", "requires",
}

_AMBIGUOUS_PRONOUN_RE = re.compile(
    r"^(This|It)\s+(" + "|".join(sorted(_AMBIGUOUS_VERBS)) + r")\b",
    re.IGNORECASE,
)


def check_PQ_07(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """PQ-07: Flag sentences starting with 'This' or 'It' followed by a verb."""
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    violations: List[Violation] = []

    for para in _split_paragraphs(stripped):
        for sentence in _split_sentences(para):
            if _AMBIGUOUS_PRONOUN_RE.match(sentence):
                idx = stripped.find(sentence)
                lineno = _line_number_of(stripped, idx) if idx != -1 else 1
                violations.append(Violation(
                    check_id="PQ-07",
                    file=filename,
                    line=lineno,
                    message="Ambiguous pronoun opener ('This'/'It' + verb) — clarify antecedent",
                    text=_truncate(sentence),
                ))
    return violations


# ---------------------------------------------------------------------------
# Tier 3 checks
# ---------------------------------------------------------------------------

def check_SP_01(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """SP-01: Flag banned words."""
    banned = list(config["banned_words"].get("always", [])) + \
             list(config["banned_words"].get("paper_specific", []))
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    stripped_lines = stripped.splitlines()
    violations: List[Violation] = []

    for lineno_0, line in enumerate(stripped_lines):
        for word in banned:
            matches = list(re.finditer(r"\b" + re.escape(word) + r"\b", line, re.IGNORECASE))
            for _ in matches:
                violations.append(Violation(
                    check_id="SP-01",
                    file=filename,
                    line=lineno_0 + 1,
                    message=f"Banned word: '{word}'",
                    text=_truncate(line),
                ))
                break  # one violation per word per line is enough
    return violations


def check_SP_02(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """SP-02: Flag banned phrases."""
    phrases = list(config["banned_phrases"].get("always", [])) + \
              list(config["banned_phrases"].get("paper_specific", []))
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    stripped_lines = stripped.splitlines()
    violations: List[Violation] = []

    for lineno_0, line in enumerate(stripped_lines):
        lower_line = line.lower()
        for phrase in phrases:
            if phrase.lower() in lower_line:
                violations.append(Violation(
                    check_id="SP-02",
                    file=filename,
                    line=lineno_0 + 1,
                    message=f"Banned phrase: '{phrase}'",
                    text=_truncate(line),
                ))
    return violations


def check_SP_03(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """SP-03: Flag repeated non-trivial words within a sliding window of paragraphs."""
    cfg = config["repetition_detection"]
    window = cfg["window_paragraphs"]
    min_len = cfg["min_word_length"]
    min_occ = cfg.get("min_occurrences", 3)
    exclude = {w.lower() for w in cfg.get("exclude", [])}

    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)

    # Collect paragraphs with their start-line numbers.
    raw_paragraphs = re.split(r"\n\s*\n", stripped)
    paragraphs: List[tuple] = []  # (start_line, text)
    current_line = 1
    for para in raw_paragraphs:
        start = current_line
        current_line += para.count("\n") + 2  # +2 for the blank line separator
        lines_in = para.splitlines()
        kept = []
        for line in lines_in:
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("|") or \
               s.startswith("---") or s.startswith("```"):
                continue
            kept.append(line)
        if kept:
            paragraphs.append((start, "\n".join(kept)))

    violations: List[Violation] = []
    seen_windows: set = set()  # avoid duplicate violations for same word+window

    for i in range(len(paragraphs) - window + 1):
        window_paras = paragraphs[i: i + window]
        window_text = " ".join(p for _, p in window_paras)
        window_start_line = window_paras[0][0]

        # Count words.
        word_counts: Dict[str, int] = {}
        for word in re.findall(r"\b[a-zA-Z]+\b", window_text):
            w = word.lower()
            if len(w) >= min_len and w not in exclude:
                word_counts[w] = word_counts.get(w, 0) + 1

        for word, count in word_counts.items():
            if count >= min_occ:
                key = (word, i)
                if key not in seen_windows:
                    seen_windows.add(key)
                    violations.append(Violation(
                        check_id="SP-03",
                        file=filename,
                        line=window_start_line,
                        message=(
                            f"Repeated word '{word}' appears {count}× "
                            f"in {window}-paragraph window"
                        ),
                        text=_truncate(word),
                    ))
    return violations


def check_SP_04(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """SP-04: Flag cliché patterns."""
    patterns = config.get("cliche_patterns", [])
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    stripped_lines = stripped.splitlines()
    violations: List[Violation] = []

    compiled = [(p, re.compile(p, re.IGNORECASE)) for p in patterns]

    for lineno_0, line in enumerate(stripped_lines):
        for raw_pat, pat in compiled:
            if pat.search(line):
                violations.append(Violation(
                    check_id="SP-04",
                    file=filename,
                    line=lineno_0 + 1,
                    message=f"Cliché pattern matched: {raw_pat}",
                    text=_truncate(line),
                ))
    return violations


def check_SP_05(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """SP-05: Flag self-congratulatory emphasis adverbs."""
    flag_words = config["self_congratulation"]["flag_words"]
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    stripped_lines = stripped.splitlines()
    violations: List[Violation] = []

    for lineno_0, line in enumerate(stripped_lines):
        for word in flag_words:
            if re.search(r"\b" + re.escape(word) + r"\b", line, re.IGNORECASE):
                violations.append(Violation(
                    check_id="SP-05",
                    file=filename,
                    line=lineno_0 + 1,
                    message=f"Self-congratulatory emphasis word: '{word}'",
                    text=_truncate(line),
                ))
                break  # one violation per line
    return violations


def check_SP_06(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """SP-06: Flag nominalizations (noun form where a verb exists)."""
    nominalizations: Dict[str, str] = config.get("nominalizations", {})
    text = "\n".join(lines)
    stripped = _strip_skipped_regions(text)
    stripped_lines = stripped.splitlines()
    violations: List[Violation] = []

    for lineno_0, line in enumerate(stripped_lines):
        lower_line = line.lower()
        for phrase, suggestion in nominalizations.items():
            if phrase.lower() in lower_line:
                violations.append(Violation(
                    check_id="SP-06",
                    file=filename,
                    line=lineno_0 + 1,
                    message=f"Nominalization: '{phrase}' → consider '{suggestion}'",
                    text=_truncate(line),
                ))
    return violations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_tier2(text: str, qc_config: dict, filename: str = "<string>") -> List[Violation]:
    """Run all PQ-01..PQ-07 checks. Returns combined violations."""
    lines = text.splitlines()
    violations: List[Violation] = []
    for check_fn in (
        check_PQ_01,
        check_PQ_02,
        check_PQ_03,
        check_PQ_04,
        check_PQ_05,
        check_PQ_06,
        check_PQ_07,
    ):
        violations.extend(check_fn(lines, qc_config, filename))
    return violations


def run_tier3(text: str, style_config: dict, filename: str = "<string>") -> List[Violation]:
    """Run all SP-01..SP-06 checks. Returns combined findings."""
    lines = text.splitlines()
    violations: List[Violation] = []
    for check_fn in (
        check_SP_01,
        check_SP_02,
        check_SP_03,
        check_SP_04,
        check_SP_05,
        check_SP_06,
    ):
        violations.extend(check_fn(lines, style_config, filename))
    return violations


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_violations(violations: List[Violation], tier_name: str) -> str:
    """Format violations for CLI output, grouped by check_id."""
    if not violations:
        return f"=== {tier_name} ===\n\nNo violations found.\n"

    # Group by check_id while preserving order of first appearance.
    groups: Dict[str, List[Violation]] = {}
    for v in violations:
        groups.setdefault(v.check_id, []).append(v)

    lines: List[str] = [f"=== {tier_name} ===", ""]

    for check_id, viols in groups.items():
        # Use the first violation's message prefix as the group header.
        # Strip the per-instance detail to get a clean label.
        header_msg = viols[0].message.split(":")[0] if ":" in viols[0].message else viols[0].message
        lines.append(f"{check_id} {header_msg}:")
        for v in viols:
            lines.append(f'  {v.file}:{v.line}: {v.message} — "{v.text}"')
        lines.append("")

    total = len(violations)
    files = len({v.file for v in violations})
    lines.append(
        f"{tier_name.split(':')[0].strip()} SUMMARY: "
        f"{total} violation{'s' if total != 1 else ''} across {files} file{'s' if files != 1 else ''}"
    )
    return "\n".join(lines) + "\n"
