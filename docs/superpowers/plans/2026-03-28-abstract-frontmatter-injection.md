# Abstract Frontmatter Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `seldon paper build` skip `00_abstract.md` from the section body and inject its content as the `abstract:` YAML field in the assembled document frontmatter; create `paper/frontmatter.yml` for the Leibniz project with correct font standards.

**Architecture:** `build_paper()` in `seldon/paper/build.py` filters `00_abstract.md` from assembled sections, extracts the abstract text (stripping the `# Abstract` heading), then injects it into the frontmatter YAML via string manipulation. New private helpers keep the logic isolated and testable without Neo4j. The Leibniz `frontmatter.yml` is a standalone file creation requiring no code changes.

**Tech Stack:** Python stdlib (pathlib, re), PyYAML (already a dependency), Quarto YAML frontmatter format

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `seldon/paper/build.py` | Modify | 3 new private helpers + `build_paper()` step 3 and step 9 |
| `tests/test_paper_build.py` | Modify | 5 new unit tests for the helpers and pipeline |
| `ai-demos/leibniz-pi/paper/frontmatter.yml` | Create | Document frontmatter with Source Sans Pro, Leibniz metadata |

**No new files in the Seldon package.** Helpers live in `build.py` alongside the code they support. The Leibniz frontmatter.yml is outside the Seldon repo.

---

## Task 1: Add abstract extraction helpers to build.py

**Files:**
- Modify: `seldon/paper/build.py`

Context: `build_paper()` currently discovers all `sections/*.md` files and concatenates them after any `frontmatter.yml`. The fix: filter out `00_abstract.md` from the body, extract its text, and inject it into the frontmatter YAML block.

Three private helpers are added. They contain no I/O beyond reading a single file — pure string/path logic, fully unit-testable.

- [ ] **Step 1: Write failing tests first** (see Task 2 — do Task 2's Step 1 before implementing)

- [ ] **Step 2: Add `_extract_abstract_text` helper**

In `seldon/paper/build.py`, add after the `REFTYPE_TO_TYPE` constant block (around line 36), before `# ---------------------------------------------------------------------------`:

```python
# ---------------------------------------------------------------------------
# Abstract extraction
# ---------------------------------------------------------------------------

def _extract_abstract_text(abstract_path: Path) -> str:
    """
    Read 00_abstract.md and return plain text with the heading stripped.

    Strips any leading line that is a markdown heading (starts with '#').
    Strips leading and trailing whitespace from the result.
    Returns empty string if file is empty after stripping.
    """
    raw = abstract_path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    # Drop lines that are purely a markdown heading at the start of the file
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()


def _inject_abstract_into_frontmatter(frontmatter_content: str, abstract_text: str) -> str:
    """
    Inject an abstract: block scalar into an existing YAML frontmatter string.

    frontmatter_content must be a string starting with '---' and ending with '---'.
    The abstract is inserted before the closing '---' delimiter.
    Lines of abstract_text are indented by 2 spaces for the YAML block scalar.
    """
    # Build YAML block scalar: "abstract: |\n  line1\n  line2"
    indented_lines = []
    for line in abstract_text.split("\n"):
        indented_lines.append(f"  {line}" if line.strip() else "")
    abstract_block = "abstract: |\n" + "\n".join(indented_lines).rstrip()

    content = frontmatter_content.rstrip()
    if content.endswith("---"):
        # Insert before closing ---
        body = content[:-3].rstrip()
        return f"{body}\n{abstract_block}\n---"
    else:
        # No closing --- found — append and close
        return f"{content}\n{abstract_block}\n---"


def _build_minimal_frontmatter(abstract_text: str) -> str:
    """
    Build a minimal YAML frontmatter block containing only the abstract.

    Used when no frontmatter.yml exists but 00_abstract.md does.
    Returns a complete '---...---' block.
    """
    return _inject_abstract_into_frontmatter("---", abstract_text)
```

- [ ] **Step 3: Modify `build_paper()` steps 3 and 9**

In `build_paper()`:

**Replace step 3** (line ~262 currently):
```python
# OLD:
section_files = sorted(sections_dir.glob("*.md")) if sections_dir.exists() else []

# NEW (same line, replace with):
if sections_dir.exists():
    all_section_files = sorted(sections_dir.glob("*.md"))
    section_files = [f for f in all_section_files if f.name != "00_abstract.md"]
    abstract_path = sections_dir / "00_abstract.md"
    abstract_text = _extract_abstract_text(abstract_path) if abstract_path.exists() else None
else:
    section_files = []
    abstract_text = None
```

**Replace step 9** (lines ~313-324 currently):
```python
# OLD:
parts: list[str] = []
frontmatter_path = paper_dir / "frontmatter.yml"
if frontmatter_path.exists():
    frontmatter_content = frontmatter_path.read_text(encoding="utf-8").rstrip()
    parts.append(frontmatter_content)

# NEW:
parts: list[str] = []
frontmatter_path = paper_dir / "frontmatter.yml"
if abstract_text:
    if frontmatter_path.exists():
        raw_frontmatter = frontmatter_path.read_text(encoding="utf-8").rstrip()
        parts.append(_inject_abstract_into_frontmatter(raw_frontmatter, abstract_text))
    else:
        parts.append(_build_minimal_frontmatter(abstract_text))
elif frontmatter_path.exists():
    parts.append(frontmatter_path.read_text(encoding="utf-8").rstrip())
```

- [ ] **Step 4: Run tests to verify helpers work** (after Task 2 is written)

```bash
cd /Users/brock/Documents/GitHub/seldon
python -m pytest tests/test_paper_build.py -k "abstract" -v
```

Expected: all new abstract tests pass.

- [ ] **Step 5: Run full test suite**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: same pass count as before + new tests, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add seldon/paper/build.py
git commit -m "feat: inject 00_abstract.md as YAML abstract: field in paper build (not body section)"
```

---

## Task 2: Tests for abstract extraction and frontmatter injection

**Files:**
- Modify: `tests/test_paper_build.py`

These tests exercise only the new private helper functions — no Neo4j required. They go in a new section at the bottom of the existing test file, clearly separated from the integration tests above.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_paper_build.py`:

```python
# ---------------------------------------------------------------------------
# Unit tests: abstract extraction and frontmatter injection (no Neo4j)
# ---------------------------------------------------------------------------

from seldon.paper.build import (
    _extract_abstract_text,
    _inject_abstract_into_frontmatter,
    _build_minimal_frontmatter,
)


def test_extract_abstract_text_strips_heading(tmp_path):
    """# Abstract heading is removed; body text is returned stripped."""
    f = tmp_path / "00_abstract.md"
    f.write_text("# Abstract\n\nThis is the abstract body.\n")
    result = _extract_abstract_text(f)
    assert result == "This is the abstract body."
    assert "# Abstract" not in result


def test_extract_abstract_text_strips_multiple_heading_lines(tmp_path):
    """Multiple leading heading lines (e.g., ## Abstract) are all stripped."""
    f = tmp_path / "00_abstract.md"
    f.write_text("# Abstract\n## Subtitle\n\nBody text.\n")
    result = _extract_abstract_text(f)
    assert result == "Body text."


def test_extract_abstract_text_no_heading(tmp_path):
    """File without a heading returns body text unchanged."""
    f = tmp_path / "00_abstract.md"
    f.write_text("Body text without heading.\n")
    result = _extract_abstract_text(f)
    assert result == "Body text without heading."


def test_inject_abstract_into_frontmatter_inserts_before_closing():
    """Abstract block is inserted before the closing --- of frontmatter."""
    frontmatter = "---\ntitle: Test\n---"
    result = _inject_abstract_into_frontmatter(frontmatter, "My abstract.")
    assert "abstract: |" in result
    assert "  My abstract." in result
    # Must still end with ---
    assert result.strip().endswith("---")
    # Title must still be present
    assert "title: Test" in result


def test_inject_abstract_multiline_indented():
    """Multiline abstract lines are each indented by 2 spaces."""
    frontmatter = "---\ntitle: Test\n---"
    abstract = "Line one.\nLine two."
    result = _inject_abstract_into_frontmatter(frontmatter, abstract)
    assert "  Line one." in result
    assert "  Line two." in result


def test_build_minimal_frontmatter_wraps_in_delimiters():
    """Minimal frontmatter starts and ends with --- even with no existing frontmatter."""
    result = _build_minimal_frontmatter("Abstract text.")
    assert result.startswith("---")
    assert result.strip().endswith("---")
    assert "abstract: |" in result
    assert "  Abstract text." in result


def test_build_paper_skips_abstract_from_body(tmp_path, monkeypatch):
    """00_abstract.md content does not appear in the assembled section body."""
    # Minimal project setup
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n  database: seldon-test\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    paper_dir = tmp_path / "paper"
    sections_dir = paper_dir / "sections"
    sections_dir.mkdir(parents=True)

    (sections_dir / "00_abstract.md").write_text("# Abstract\n\nMy abstract text.\n")
    (sections_dir / "01_intro.md").write_text("## Introduction\n\nSection body.\n")

    # Mock the Neo4j driver (no actual DB needed)
    from unittest.mock import MagicMock
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value.run.return_value.data.return_value = []
    monkeypatch.setattr("seldon.paper.build.get_neo4j_driver", lambda config: mock_driver)
    monkeypatch.setattr("seldon.paper.build.load_project_config", lambda path: {
        "project": {"name": "test", "domain": "research"},
        "neo4j": {"uri": "bolt://localhost:7687", "database": "seldon-test"},
    })

    output_path = paper_dir / "paper.qmd"
    from seldon.paper.build import build_paper
    build_paper(
        project_dir=tmp_path,
        paper_dir=paper_dir,
        output_path=output_path,
        skip_qc=True,
        no_render=True,
    )

    assembled = output_path.read_text()
    # Abstract heading must NOT appear as a section
    assert "# Abstract" not in assembled
    # Abstract text must appear in frontmatter abstract field
    assert "abstract: |" in assembled
    assert "My abstract text." in assembled
    # Regular section must still be present
    assert "## Introduction" in assembled


def test_build_paper_no_abstract_file_unchanged(tmp_path, monkeypatch):
    """If 00_abstract.md does not exist, build behaves as before (no abstract: in output)."""
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n  database: seldon-test\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    paper_dir = tmp_path / "paper"
    sections_dir = paper_dir / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "01_intro.md").write_text("## Introduction\n\nBody.\n")

    from unittest.mock import MagicMock
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value.run.return_value.data.return_value = []
    monkeypatch.setattr("seldon.paper.build.get_neo4j_driver", lambda config: mock_driver)
    monkeypatch.setattr("seldon.paper.build.load_project_config", lambda path: {
        "project": {"name": "test", "domain": "research"},
        "neo4j": {"uri": "bolt://localhost:7687", "database": "seldon-test"},
    })

    output_path = paper_dir / "paper.qmd"
    from seldon.paper.build import build_paper
    build_paper(
        project_dir=tmp_path,
        paper_dir=paper_dir,
        output_path=output_path,
        skip_qc=True,
        no_render=True,
    )

    assembled = output_path.read_text()
    assert "abstract:" not in assembled
    assert "## Introduction" in assembled
```

- [ ] **Step 2: Run tests to confirm they FAIL before implementation**

```bash
cd /Users/brock/Documents/GitHub/seldon
python -m pytest tests/test_paper_build.py -k "abstract" -v 2>&1 | tail -20
```

Expected: ImportError (functions not yet defined) or assertion failures. Confirms tests are real.

- [ ] **Step 3: Implement Task 1 (the helpers and build_paper changes)**

(Go do Task 1 Steps 2-3 now, then come back here)

- [ ] **Step 4: Run tests to confirm they PASS**

```bash
python -m pytest tests/test_paper_build.py -k "abstract" -v 2>&1 | tail -25
```

Expected: 9 new tests pass.

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 341 + 9 = 350 passed (or close), 0 failures.

- [ ] **Step 6: Commit tests**

```bash
git add tests/test_paper_build.py
git commit -m "test: abstract extraction and frontmatter injection unit tests"
```

---

## Task 3: Create Leibniz paper/frontmatter.yml

**Files:**
- Create: `/Users/brock/Documents/GitHub/ai-demos/leibniz-pi/paper/frontmatter.yml`

Context: The Leibniz project has `paper/_quarto.yml` (native Quarto config) with `mainfont: "Palatino"` and complex LaTeX includes. The Seldon build pipeline uses `paper/frontmatter.yml` as the assembled document's YAML header. The QUARTO_SPEC says `mainfont: "Source Sans Pro"` (not Palatino). The abstract field is injected at build time from `00_abstract.md` — do NOT include `abstract:` in this file.

Note: `paper/_quarto.yml` stays as-is for native Quarto builds. `paper/frontmatter.yml` is used by `seldon paper build` only. Both can coexist.

- [ ] **Step 1: Create the file**

Create `/Users/brock/Documents/GitHub/ai-demos/leibniz-pi/paper/frontmatter.yml` with this exact content:

```yaml
---
title: "Wrong-Limit Attractors: Why Constraining the Search Space Dominates Fitness Engineering for Discovery of Convergent Processes"
author: "Brock Webb"
date: "March 2026"
thanks: "The views expressed are the author's own and do not necessarily represent the views of the U.S. Census Bureau or the U.S. Department of Commerce."
keywords:
  - genetic programming
  - symbolic regression
  - wrong-limit attractors
  - convergent series
  - search space
format:
  pdf:
    documentclass: article
    papersize: letter
    fontsize: 11pt
    pdf-engine: xelatex
    geometry:
      - margin=1in
    number-sections: true
    toc: false
    colorlinks: true
    linkcolor: "blue"
    linestretch: 1.25
    mainfont: "Source Sans Pro"
    sansfont: "Source Sans Pro"
    monofont: "Source Code Pro"
    include-in-header:
      text: |
        \usepackage{booktabs}
        \usepackage{longtable}
  html:
    toc: false
    number-sections: false
bibliography: references.bib
csl: apa.csl
link-citations: true
---
```

- [ ] **Step 2: Verify the file parses as valid YAML**

```bash
python3 -c "
import yaml
with open('/Users/brock/Documents/GitHub/ai-demos/leibniz-pi/paper/frontmatter.yml') as f:
    content = f.read()
# Strip --- delimiters to parse the YAML body
body = content.strip()
if body.startswith('---'):
    body = body[3:]
if body.endswith('---'):
    body = body[:-3]
data = yaml.safe_load(body)
print('title:', data['title'][:50])
print('mainfont:', data['format']['pdf']['mainfont'])
print('YAML valid: OK')
"
```

Expected output:
```
title: Wrong-Limit Attractors: Why Constraining t...
mainfont: Source Sans Pro
YAML valid: OK
```

- [ ] **Step 3: Verify build pipeline sees the abstract correctly**

Run a dry build from the Leibniz project directory to confirm the abstract gets injected:

```bash
cd /Users/brock/Documents/GitHub/ai-demos/leibniz-pi
NEO4J_PASSWORD="i'llbeback" seldon paper build --no-render --skip-qc 2>&1 | head -20
```

Then inspect the assembled output:
```bash
python3 -c "
from pathlib import Path
paper = Path('paper/paper.qmd').read_text()
# Check abstract is in frontmatter
lines = paper.split('\n')
in_frontmatter = False
for i, line in enumerate(lines):
    if line.strip() == '---' and i == 0:
        in_frontmatter = True
    elif line.strip() == '---' and in_frontmatter:
        in_frontmatter = False
        break
    elif in_frontmatter and 'abstract' in line.lower():
        print('Found abstract in frontmatter at line', i, ':', line)
        break
# Check 00_abstract.md heading not in body
if '# Abstract' in paper:
    print('WARNING: # Abstract heading still in document body')
else:
    print('OK: # Abstract heading not in body')
print('mainfont present:', 'Source Sans Pro' in paper)
"
```

Expected: abstract in frontmatter, no `# Abstract` heading in body, `Source Sans Pro` in output.

- [ ] **Step 4: Commit the Leibniz file**

```bash
cd /Users/brock/Documents/GitHub/ai-demos/leibniz-pi
git add paper/frontmatter.yml
git commit -m "feat: add frontmatter.yml with Source Sans Pro font stack per QUARTO_SPEC (AD-017)"
```

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|-------------|------|
| Skip `00_abstract.md` from section body | Task 1 Step 3 (section_files filter) |
| Extract text, strip `# Abstract` heading | Task 1 Step 2 (`_extract_abstract_text`) |
| Inject as `abstract:` YAML field | Task 1 Step 2 (`_inject_abstract_into_frontmatter`) |
| If `frontmatter.yml` exists: merge | Task 1 Step 2 + Step 3 (`_inject_abstract_into_frontmatter`) |
| If `frontmatter.yml` absent: minimal | Task 1 Step 2 + Step 3 (`_build_minimal_frontmatter`) |
| Support title/author/date/thanks in frontmatter.yml | Task 3 (file creation) |
| Leibniz `paper/frontmatter.yml` | Task 3 |
| Source Sans Pro (not Palatino) | Task 3 Step 1 |

All requirements covered. No gaps.

### Placeholder scan

No TBD, TODO, or "similar to above" entries. All code blocks are complete.

### Type consistency

- `_extract_abstract_text(path: Path) -> str` — used in `build_paper()` as `_extract_abstract_text(abstract_path)` ✓
- `_inject_abstract_into_frontmatter(frontmatter_content: str, abstract_text: str) -> str` — called with `(raw_frontmatter, abstract_text)` ✓
- `_build_minimal_frontmatter(abstract_text: str) -> str` — called with `(abstract_text)` ✓
- `abstract_text` variable: `Optional[str]`, set to `None` when no abstract file exists ✓
