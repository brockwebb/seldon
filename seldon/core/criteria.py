"""Acceptance criteria are marked (AD-037-R1): each is `check: <command>` or `judgment: <why no program decides it>`.

A criterion a program can decide is decided by running the program, never by a judge reading output (S1, Pombal, Rei
and Martins 2026: self-preference persists on objective, programmatically verifiable rubrics). So registration
refuses a task with an unmarked criterion, as `criterion_unmarked`, naming each one and its line.

What counts as an acceptance criterion, in the forms this portfolio's task files use:
- **inline:** `- Acceptance: <criterion>` (or `**Acceptance:**`, `Acceptance criteria:`, `Success criteria:`) holds one
  criterion on its own line;
- **block:** the same label with nothing after it, or numbered (`4. Acceptance:`), followed by list items indented
  deeper than the label; each item is one criterion, and deeper non-list lines continue it;
- **section:** a heading `## Acceptance`, `## Acceptance criteria` or `## Success criteria`, whose list items up to the
  next heading are the criteria.

Tasks registered before QC-001's merge are baseline: the list is the file `qc.criteria_baseline` in `seldon.yaml`
names (one task path per line), and a listed task is not re-checked.
"""
from __future__ import annotations

import re
from pathlib import Path

REFUSAL = "criterion_unmarked"
_LABEL = r"(?:acceptance(?:\s+criteria)?|success\s+criteria)"
_HEADING_RE = re.compile(rf"^#{{1,6}}\s+{_LABEL}\b", re.IGNORECASE)
_ANY_HEADING_RE = re.compile(r"^#{1,6}\s")
_LIST_LABEL_RE = re.compile(
    rf"^(?P<indent>\s*)(?:(?:[-*]|\d+[.)])\s+)?\**\s*{_LABEL}\s*\**\s*:\s*\**\s*(?P<rest>.*)$", re.IGNORECASE)
_ITEM_RE = re.compile(r"^(?P<indent>\s*)(?:[-*]|\d+[.)])\s+(?P<text>.*)$")
_MARKED_RE = re.compile(r"^`?(?P<kind>check|judgment):`?(?P<rest>.*)$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def acceptance_criteria(text: str) -> list[tuple[int, str]]:
    """Every acceptance criterion in a task file, as `(line number, text)`."""
    lines = text.splitlines()
    out: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _HEADING_RE.match(line):
            i += 1
            while i < len(lines) and not _ANY_HEADING_RE.match(lines[i]):
                m = _ITEM_RE.match(lines[i])
                if m and _indent(lines[i]) == 0:
                    out.append((i + 1, m.group("text").strip()))
                i += 1
            continue
        m = _LIST_LABEL_RE.match(line)
        if m:
            rest = m.group("rest").strip()
            if rest:
                out.append((i + 1, rest))
                i += 1
                continue
            base = _indent(line)
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    i += 1
                    continue
                if _indent(nxt) <= base or _ANY_HEADING_RE.match(nxt):
                    break
                im = _ITEM_RE.match(nxt)
                if im:
                    out.append((i + 1, im.group("text").strip()))
                i += 1
            continue
        i += 1
    return out


def unmarked(text: str) -> list[tuple[int, str]]:
    """The criteria not marked `check:` or `judgment:` with text after the mark."""
    def marked(c: str) -> bool:
        m = _MARKED_RE.match(c)
        return bool(m and re.search(r"[^\s`]", m.group("rest")))    # a mark with nothing after it is not one
    return [(n, c) for n, c in acceptance_criteria(text) if not marked(c)]


def baseline(project_dir: Path, config: dict) -> set[str]:
    """Task paths registered before QC-001's merge, from the file `qc.criteria_baseline` names (none when unset)."""
    rel = ((config or {}).get("qc") or {}).get("criteria_baseline")
    if not rel:
        return set()
    path = Path(project_dir) / rel
    if not path.is_file():
        raise FileNotFoundError(f"seldon.yaml qc.criteria_baseline names {path}, which does not exist")
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")}


def registration_refusal(task_path: Path, project_dir: Path, config: dict) -> str | None:
    """The refusal for a task with an unmarked criterion, or None. A baseline task is not re-checked."""
    try:
        rel = str(Path(task_path).resolve().relative_to(Path(project_dir).resolve()))
    except ValueError:
        rel = str(task_path)
    if rel in baseline(project_dir, config):
        return None
    bad = unmarked(Path(task_path).read_text(encoding="utf-8", errors="replace"))
    if not bad:
        return None
    shown = "; ".join(f"line {n}: {c[:120]!r}" for n, c in bad[:8])
    return (f"{REFUSAL}: {len(bad)} acceptance criterion(s) not marked `check: <command>` or `judgment: <why no "
            f"program decides it>` (AD-037-R1): {shown}")
