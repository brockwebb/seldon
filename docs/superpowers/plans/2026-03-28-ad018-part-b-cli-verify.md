# AD-018 Part B: CLI Commands & seldon verify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `seldon paper numbering`, `{{figure:NAME}}`/`{{table:NAME}}`/`{{section:NAME}}` token resolution in paper build, `seldon paper impact` blast-radius display, and `seldon verify` with 7 integrity checks and `--fix` mode.

**Architecture:** Four new/modified components. `seldon/paper/numbering.py` computes figure/table display numbers from the graph (pure query, no writes). `build.py` gets a pre-pass that resolves XREF tokens using those numbers. `seldon paper impact` traverses downstream edges from any artifact. `seldon verify` runs 7 project integrity checks in order and reports with ✓/⚠/✗. All commands live in `seldon/commands/`; `numbering.py` is the only new module. Depends on Part A being merged.

**Tech Stack:** Click, Neo4j Cypher, Python stdlib (subprocess, hashlib, re), pytest

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `seldon/paper/numbering.py` | Create | `compute_figure_numbers`, `compute_table_numbers`, `resolve_xref_tokens` |
| `seldon/paper/build.py` | Modify | Add `XREF_PATTERN`, call `resolve_xref_tokens` as step 3.5 in `build_paper` |
| `seldon/commands/paper.py` | Modify | Add `paper impact` command |
| `seldon/commands/verify.py` | Create | `verify_command` with 7 checks and `--fix` mode |
| `seldon/commands/session.py` | Modify | Add verify tip to closeout output |
| `seldon/cli.py` | Modify | Register `verify_command` |
| `seldon/CLAUDE.md` | Modify | Add verify and paper impact to Skills table and Session Protocol |
| `tests/test_numbering.py` | Create | 6 numbering and XREF token tests |
| `tests/test_verify.py` | Create | 9 verify command tests |

Note: `tests/test_paper_build.py` gets 2 new XREF token tests (added at end of existing file).

---

## Task 1: Figure/table numbering module

**Files:**
- Create: `seldon/paper/numbering.py`
- Create: `tests/test_numbering.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_numbering.py`:

```python
"""
Tests for seldon/paper/numbering.py — figure/table number computation and XREF resolution.

Integration tests require Neo4j. Unit tests (resolve_xref_tokens) run without it.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from seldon.core.artifacts import create_artifact, create_link
from seldon.domain.loader import load_domain_config

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


# ---------------------------------------------------------------------------
# Integration tests: figure numbering
# ---------------------------------------------------------------------------

def test_figure_numbering_flat(neo4j_driver, project_dir, domain_config, clean_test_db):
    """No chapter structure: figures numbered 1, 2, 3 by section sequence."""
    from seldon.paper.numbering import compute_figure_numbers

    # Create two sections (no depth/sequence — flat paper)
    sec1_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "sec_intro", "title": "Introduction", "sequence": 1},
        actor="human", authority="accepted",
    )
    sec2_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "sec_methods", "title": "Methods", "sequence": 2},
        actor="human", authority="accepted",
    )

    fig1_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Figure",
        properties={"name": "fig_a", "caption": "Fig A", "description": "First figure"},
        actor="human", authority="accepted",
    )
    fig2_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Figure",
        properties={"name": "fig_b", "caption": "Fig B", "description": "Second figure"},
        actor="human", authority="accepted",
    )

    create_link(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                domain_config=domain_config, from_id=fig1_id, to_id=sec1_id,
                rel_type="appears_in", actor="human", authority="accepted")
    create_link(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                domain_config=domain_config, from_id=fig2_id, to_id=sec2_id,
                rel_type="appears_in", actor="human", authority="accepted")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        numbers = compute_figure_numbers(session, NEO4J_DB)

    # Both figures must have numbers; they should be "1" and "2"
    assert fig1_id in numbers
    assert fig2_id in numbers
    values = sorted(numbers.values())
    assert values == ["1", "2"]


def test_figure_numbering_chaptered(neo4j_driver, project_dir, domain_config, clean_test_db):
    """With chapters (depth=0): figures numbered {chapter}.{n} within chapter."""
    from seldon.paper.numbering import compute_figure_numbers

    # Chapter 2
    ch2_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "chapter_02", "title": "Methods", "depth": 0, "sequence": 2},
        actor="human", authority="accepted",
    )
    # Chapter 3
    ch3_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "chapter_03", "title": "Results", "depth": 0, "sequence": 3},
        actor="human", authority="accepted",
    )

    # Section inside chapter 2
    sec21_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "sec_2_1", "title": "Setup", "depth": 1, "sequence": 1},
        actor="human", authority="accepted",
    )
    create_link(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                domain_config=domain_config, from_id=ch2_id, to_id=sec21_id,
                rel_type="contains_section", actor="human", authority="accepted")

    fig_ch2_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Figure",
        properties={"name": "fig_setup", "caption": "Experimental setup", "description": "GP setup"},
        actor="human", authority="accepted",
    )
    fig_ch3_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Figure",
        properties={"name": "fig_results", "caption": "Results comparison", "description": "Accuracy curves"},
        actor="human", authority="accepted",
    )

    create_link(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                domain_config=domain_config, from_id=fig_ch2_id, to_id=sec21_id,
                rel_type="appears_in", actor="human", authority="accepted")
    create_link(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                domain_config=domain_config, from_id=fig_ch3_id, to_id=ch3_id,
                rel_type="appears_in", actor="human", authority="accepted")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        numbers = compute_figure_numbers(session, NEO4J_DB)

    # fig in ch2 section → "2.1"; fig in ch3 directly → "3.1"
    assert numbers[fig_ch2_id] == "2.1"
    assert numbers[fig_ch3_id] == "3.1"


def test_table_numbering_flat(neo4j_driver, project_dir, domain_config, clean_test_db):
    """No chapter structure: tables numbered 1, 2 by section sequence."""
    from seldon.paper.numbering import compute_table_numbers

    sec_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "sec_results", "title": "Results", "sequence": 3},
        actor="human", authority="accepted",
    )
    tbl_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Table",
        properties={"name": "tbl_summary", "caption": "Summary"},
        actor="human", authority="accepted",
    )
    create_link(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                domain_config=domain_config, from_id=tbl_id, to_id=sec_id,
                rel_type="appears_in", actor="human", authority="accepted")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        numbers = compute_table_numbers(session, NEO4J_DB)

    assert tbl_id in numbers
    assert numbers[tbl_id] == "1"


# ---------------------------------------------------------------------------
# Unit tests: resolve_xref_tokens (no Neo4j)
# ---------------------------------------------------------------------------

def test_resolve_xref_tokens_figure():
    """{{figure:NAME}} resolves to 'Figure 2.1' from figure_numbers dict."""
    from seldon.paper.numbering import resolve_xref_tokens

    figure_numbers = {"uuid-fig-1": "2.1"}
    table_numbers = {}
    section_map = {}
    # The function needs artifact id from name — so we also need a name→id lookup.
    # resolve_xref_tokens takes the pre-built lookups by NAME (not id).
    figure_by_name = {"fig_setup": "2.1"}
    table_by_name = {}
    section_by_name = {}

    text = "As shown in {{figure:fig_setup}}, the results are clear."
    result = resolve_xref_tokens(text, figure_by_name, table_by_name, section_by_name)
    assert result == "As shown in Figure 2.1, the results are clear."


def test_resolve_xref_tokens_table():
    """{{table:NAME}} resolves to 'Table 3.1'."""
    from seldon.paper.numbering import resolve_xref_tokens

    figure_by_name = {}
    table_by_name = {"tbl_summary": "3.1"}
    section_by_name = {}

    text = "See {{table:tbl_summary}} for details."
    result = resolve_xref_tokens(text, figure_by_name, table_by_name, section_by_name)
    assert result == "See Table 3.1 for details."


def test_resolve_xref_tokens_section():
    """{{section:NAME}} resolves to 'Chapter 3' for depth-0, 'Section 3.2' for depth-1."""
    from seldon.paper.numbering import resolve_xref_tokens

    figure_by_name = {}
    table_by_name = {}
    section_by_name = {
        "chapter_03": "Chapter 3",
        "sec_3_2": "Section 3.2",
    }

    text = "As described in {{section:chapter_03}} and {{section:sec_3_2}}."
    result = resolve_xref_tokens(text, figure_by_name, table_by_name, section_by_name)
    assert result == "As described in Chapter 3 and Section 3.2."
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/brock/Documents/GitHub/seldon
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_numbering.py -v 2>&1 | tail -15
```

Expected: `ModuleNotFoundError: No module named 'seldon.paper.numbering'` — confirms tests are real.

- [ ] **Step 3: Create `seldon/paper/numbering.py`**

```python
"""
Figure and table numbering for the paper build pipeline.

Computes display numbers (e.g., "2.3" or "5") from graph position via
appears_in and contains_section edges. Numbers are computed on the fly —
the figure_number/table_number properties on artifacts are for caching only.

Public API:
    compute_figure_numbers(session, database) -> dict[artifact_id, display_str]
    compute_table_numbers(session, database) -> dict[artifact_id, display_str]
    compute_section_display(session, database) -> dict[artifact_id, display_str]
    resolve_xref_tokens(text, figure_by_name, table_by_name, section_by_name) -> str
"""
from __future__ import annotations

import re
from typing import Optional

from neo4j import Session

# Pattern for cross-reference tokens: {{figure:NAME}}, {{table:NAME}}, {{section:NAME}}
# Distinct from REFERENCE_PATTERN (which handles {{type:name:field}})
XREF_PATTERN = re.compile(r'\{\{(figure|table|section):([^:}]+)\}\}')


def _assign_numbers(records: list[dict]) -> dict[str, str]:
    """
    Assign display numbers from ordered records.

    Each record must have: artifact_id, chapter_seq (int or None), within_chapter_order (int).

    Returns:
        dict mapping artifact_id → display string ("1", "2", "3" for flat; "2.1", "2.2" for chaptered)
    """
    has_chapters = any(r["chapter_seq"] is not None for r in records)

    result: dict[str, str] = {}
    if has_chapters:
        chapter_counters: dict[int, int] = {}
        for r in records:
            ch = r["chapter_seq"] if r["chapter_seq"] is not None else 0
            chapter_counters[ch] = chapter_counters.get(ch, 0) + 1
            result[r["artifact_id"]] = f"{ch}.{chapter_counters[ch]}"
    else:
        for i, r in enumerate(records, start=1):
            result[r["artifact_id"]] = str(i)

    return result


def compute_figure_numbers(session: Session, database: str) -> dict[str, str]:
    """
    Compute display numbers for all Figures based on graph position.

    Queries all Figures with appears_in edges to PaperSections. Finds
    depth-0 ancestor (chapter) via contains_section* edges. If no chapter
    structure exists (flat paper), numbers are sequential: 1, 2, 3.
    If chapters exist, numbers are {chapter_seq}.{n}: 2.1, 2.2, 3.1.

    Returns: {artifact_id: display_string}
    """
    records = session.run("""
        MATCH (f:Artifact:Figure)-[:APPEARS_IN]->(s:Artifact:PaperSection)
        OPTIONAL MATCH (chapter:Artifact:PaperSection {depth: 0})-[:CONTAINS_SECTION*0..]->(s)
        RETURN f.artifact_id AS artifact_id,
               chapter.sequence AS chapter_seq,
               coalesce(s.sequence, 0) AS section_seq,
               f.name AS fig_name
        ORDER BY coalesce(chapter.sequence, 0), coalesce(s.sequence, 0), f.name
    """).data()

    return _assign_numbers(records)


def compute_table_numbers(session: Session, database: str) -> dict[str, str]:
    """
    Compute display numbers for all Tables based on graph position.

    Same logic as compute_figure_numbers but queries Table nodes.

    Returns: {artifact_id: display_string}
    """
    records = session.run("""
        MATCH (t:Artifact:Table)-[:APPEARS_IN]->(s:Artifact:PaperSection)
        OPTIONAL MATCH (chapter:Artifact:PaperSection {depth: 0})-[:CONTAINS_SECTION*0..]->(s)
        RETURN t.artifact_id AS artifact_id,
               chapter.sequence AS chapter_seq,
               coalesce(s.sequence, 0) AS section_seq,
               t.name AS tbl_name
        ORDER BY coalesce(chapter.sequence, 0), coalesce(s.sequence, 0), t.name
    """).data()

    return _assign_numbers(records)


def compute_section_display(session: Session, database: str) -> dict[str, str]:
    """
    Compute display strings for PaperSections based on depth and sequence.

    depth=0 → "Chapter N" (using sequence)
    depth=1 → "Section P.N" (using parent chapter sequence and own sequence)
    depth=2 → "Section P.Q.N"
    No depth set → "Section N" (flat)

    Returns: {artifact_id: display_string}
    """
    records = session.run("""
        MATCH (s:Artifact:PaperSection)
        OPTIONAL MATCH (parent:Artifact:PaperSection)-[:CONTAINS_SECTION]->(s)
        OPTIONAL MATCH (grandparent:Artifact:PaperSection)-[:CONTAINS_SECTION]->(parent)
        RETURN s.artifact_id AS artifact_id, s.depth AS depth,
               s.sequence AS seq,
               parent.sequence AS parent_seq,
               grandparent.sequence AS gp_seq
    """).data()

    result: dict[str, str] = {}
    for r in records:
        depth = r["depth"]
        seq = r["seq"] or 0
        if depth == 0:
            result[r["artifact_id"]] = f"Chapter {seq}"
        elif depth == 1:
            p = r["parent_seq"] or 0
            result[r["artifact_id"]] = f"Section {p}.{seq}"
        elif depth == 2:
            gp = r["gp_seq"] or 0
            p = r["parent_seq"] or 0
            result[r["artifact_id"]] = f"Section {gp}.{p}.{seq}"
        else:
            result[r["artifact_id"]] = f"Section {seq}"

    return result


def build_name_lookup(
    session: Session,
    figure_numbers: dict[str, str],
    table_numbers: dict[str, str],
    section_display: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """
    Convert {artifact_id: display} dicts to {name: display} dicts for token resolution.

    Queries artifact names for the given IDs and builds name-keyed lookups.

    Returns: (figure_by_name, table_by_name, section_by_name)
    """
    all_ids = list(figure_numbers) + list(table_numbers) + list(section_display)
    if not all_ids:
        return {}, {}, {}

    records = session.run(
        "MATCH (a:Artifact) WHERE a.artifact_id IN $ids AND a.name IS NOT NULL "
        "RETURN a.artifact_id AS artifact_id, a.name AS name",
        ids=all_ids,
    ).data()
    id_to_name = {r["artifact_id"]: r["name"] for r in records}

    figure_by_name = {id_to_name[k]: v for k, v in figure_numbers.items() if k in id_to_name}
    table_by_name = {id_to_name[k]: v for k, v in table_numbers.items() if k in id_to_name}
    section_by_name = {id_to_name[k]: v for k, v in section_display.items() if k in id_to_name}

    return figure_by_name, table_by_name, section_by_name


def resolve_xref_tokens(
    text: str,
    figure_by_name: dict[str, str],
    table_by_name: dict[str, str],
    section_by_name: dict[str, str],
) -> str:
    """
    Replace {{figure:NAME}}, {{table:NAME}}, {{section:NAME}} tokens with display strings.

    Unknown names are left as-is (no error — missing xrefs are caught by seldon verify).

    Returns: text with tokens replaced.
    """
    def _replace(match: re.Match) -> str:
        token_type = match.group(1)
        name = match.group(2)
        if token_type == "figure":
            display = figure_by_name.get(name)
            return f"Figure {display}" if display else match.group(0)
        elif token_type == "table":
            display = table_by_name.get(name)
            return f"Table {display}" if display else match.group(0)
        elif token_type == "section":
            display = section_by_name.get(name)
            return display if display else match.group(0)
        return match.group(0)

    return XREF_PATTERN.sub(_replace, text)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_numbering.py -v 2>&1 | tail -20
```

Expected: all 6 tests PASSED.

- [ ] **Step 5: Run full test suite**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 368 + 6 = 374 passed, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add seldon/paper/numbering.py tests/test_numbering.py
git commit -m "feat: figure/table/section numbering and XREF token resolution (AD-018)"
```

---

## Task 2: XREF token resolution in paper build

**Files:**
- Modify: `seldon/paper/build.py` (add XREF pre-pass step)
- Modify: `tests/test_paper_build.py` (2 new unit tests)

The `build_paper()` function in `seldon/paper/build.py` gets a new step between steps 3 and 4: compute numbering and resolve `{{figure:NAME}}`, `{{table:NAME}}`, `{{section:NAME}}` tokens in section text before field-based reference resolution.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_paper_build.py`:

```python
# ---------------------------------------------------------------------------
# Unit tests: XREF token resolution in build pipeline (no Neo4j)
# ---------------------------------------------------------------------------

def test_build_paper_resolves_figure_xref_token(tmp_path, monkeypatch):
    """{{figure:NAME}} in section text is replaced with 'Figure N' in the assembled output."""
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n  database: seldon-test\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    paper_dir = tmp_path / "paper"
    sections_dir = paper_dir / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "01_results.md").write_text(
        "See {{figure:fig_convergence}} for convergence curves.\n"
    )

    mock_driver = MagicMock()
    # load_named_artifacts returns empty — no field-based refs to resolve
    mock_driver.session.return_value.__enter__.return_value.run.return_value.data.return_value = []
    monkeypatch.setattr("seldon.paper.build.get_neo4j_driver", lambda config: mock_driver)
    monkeypatch.setattr("seldon.paper.build.load_project_config", lambda path: {
        "project": {"name": "test", "domain": "research"},
        "neo4j": {"uri": "bolt://localhost:7687", "database": "seldon-test"},
    })

    # Inject numbering: mock compute_figure_numbers etc. to return known values
    monkeypatch.setattr(
        "seldon.paper.build._compute_xref_lookups",
        lambda session, database: ({"fig_convergence": "1"}, {}, {}),
    )

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
    assert "Figure 1" in assembled
    assert "{{figure:fig_convergence}}" not in assembled


def test_build_paper_leaves_unknown_xref_intact(tmp_path, monkeypatch):
    """{{figure:unknown_fig}} with no match in numbering dict is left as-is in output."""
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n  database: seldon-test\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    paper_dir = tmp_path / "paper"
    sections_dir = paper_dir / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "01_results.md").write_text(
        "See {{figure:unknown_fig}} here.\n"
    )

    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value.run.return_value.data.return_value = []
    monkeypatch.setattr("seldon.paper.build.get_neo4j_driver", lambda config: mock_driver)
    monkeypatch.setattr("seldon.paper.build.load_project_config", lambda path: {
        "project": {"name": "test", "domain": "research"},
        "neo4j": {"uri": "bolt://localhost:7687", "database": "seldon-test"},
    })
    # Empty lookups — figure not found
    monkeypatch.setattr(
        "seldon.paper.build._compute_xref_lookups",
        lambda session, database: ({}, {}, {}),
    )

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
    # Token left as-is when unknown
    assert "{{figure:unknown_fig}}" in assembled
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_paper_build.py -k "xref" -v 2>&1 | tail -15
```

Expected: `AttributeError: module 'seldon.paper.build' has no attribute '_compute_xref_lookups'` — confirms tests are real.

- [ ] **Step 3: Add `_compute_xref_lookups` helper and XREF pre-pass to `build.py`**

In `seldon/paper/build.py`, add import at the top (after existing imports):

```python
from seldon.paper.numbering import (
    compute_figure_numbers,
    compute_table_numbers,
    compute_section_display,
    build_name_lookup,
    resolve_xref_tokens,
)
```

Add helper function after the `_build_minimal_frontmatter` function (before the `# ---------------------------------------------------------------------------\n# Data structures` comment):

```python
def _compute_xref_lookups(
    session, database: str
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """
    Compute figure/table/section display lookups for XREF token resolution.

    Returns (figure_by_name, table_by_name, section_by_name) — all keyed by artifact name.
    Calls numbering module functions and converts artifact_id keys to name keys.
    """
    fig_numbers = compute_figure_numbers(session, database)
    tbl_numbers = compute_table_numbers(session, database)
    sec_display = compute_section_display(session, database)
    return build_name_lookup(session, fig_numbers, tbl_numbers, sec_display)
```

In `build_paper()`, the existing driver/session flow opens and closes the driver in step 4. We need to reuse the same session for XREF lookups. Replace steps 3–4 with the updated version:

Find this block in `build_paper()`:
```python
    # 4. Load artifacts from graph
    driver = get_neo4j_driver(config)
    try:
        artifacts = load_named_artifacts(driver, database)
    finally:
        driver.close()
```

Replace with:
```python
    # 4. Load artifacts and compute XREF lookups in single driver connection
    driver = get_neo4j_driver(config)
    try:
        artifacts = load_named_artifacts(driver, database)
        with driver.session(database=database) as _xref_session:
            figure_by_name, table_by_name, section_by_name = _compute_xref_lookups(
                _xref_session, database
            )
    finally:
        driver.close()
```

Then add the XREF pre-pass as step 6.5 — insert after step 6 (`# 6. Resolve references in each section`) and before the loop that iterates `section_files`:

Find:
```python
    # 6. Resolve references in each section
    all_ref_errors: list[RefError] = []
    resolved_sections: list[tuple[str, str]] = []  # (filename, resolved_text)

    for section_file in section_files:
        text = section_file.read_text(encoding="utf-8")
        resolved, errors = resolve_references(
```

Replace with:
```python
    # 6. Resolve references in each section
    all_ref_errors: list[RefError] = []
    resolved_sections: list[tuple[str, str]] = []  # (filename, resolved_text)

    for section_file in section_files:
        text = section_file.read_text(encoding="utf-8")
        # 6.5 Pre-pass: replace {{figure:NAME}}, {{table:NAME}}, {{section:NAME}} tokens
        text = resolve_xref_tokens(text, figure_by_name, table_by_name, section_by_name)
        resolved, errors = resolve_references(
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_paper_build.py -k "xref" -v 2>&1 | tail -15
```

Expected: both XREF tests PASSED.

- [ ] **Step 5: Run full test suite**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 374 + 2 = 376 passed, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add seldon/paper/build.py tests/test_paper_build.py
git commit -m "feat: resolve {{figure:NAME}}/{{table:NAME}}/{{section:NAME}} XREF tokens in paper build (AD-018)"
```

---

## Task 3: `seldon paper impact` command

**Files:**
- Modify: `seldon/commands/paper.py` (add impact command)
- Create: `tests/test_impact.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_impact.py`:

```python
"""
Tests for `seldon paper impact` command.

Integration tests require Neo4j.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.core.artifacts import create_artifact, create_link
from seldon.domain.loader import load_domain_config

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_result(neo4j_driver, project_dir, domain_config, name):
    return create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"name": name, "value": 1.0, "units": "score", "description": name},
        actor="human", authority="accepted",
    )


def test_impact_shows_direct_dependents(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Result with cites edge from PaperSection appears in impact output."""
    from seldon.commands.paper import _compute_impact

    result_id = _make_result(neo4j_driver, project_dir, domain_config, "metric_base")
    sec_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "sec_analysis", "title": "Analysis"},
        actor="human", authority="accepted",
    )
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, from_id=sec_id, to_id=result_id,
        rel_type="cites", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        impact_tree = _compute_impact(session, result_id)

    names = [node["artifact"]["name"] for node in impact_tree]
    assert "sec_analysis" in names


def test_impact_shows_transitive(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Result → Figure (contains) → PaperSection (references_figure) appears in impact."""
    from seldon.commands.paper import _compute_impact

    result_id = _make_result(neo4j_driver, project_dir, domain_config, "metric_deep")
    fig_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Figure",
        properties={"name": "fig_deep", "caption": "Deep fig", "description": "Depth test"},
        actor="human", authority="accepted",
    )
    sec_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "sec_deep", "title": "Deep Section"},
        actor="human", authority="accepted",
    )

    create_link(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                domain_config=domain_config, from_id=fig_id, to_id=result_id,
                rel_type="contains", actor="human", authority="accepted")
    create_link(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                domain_config=domain_config, from_id=sec_id, to_id=fig_id,
                rel_type="references_figure", actor="human", authority="accepted")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        impact_tree = _compute_impact(session, result_id)

    names = [node["artifact"]["name"] for node in impact_tree]
    assert "fig_deep" in names
    assert "sec_deep" in names


def test_impact_empty_for_leaf(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Artifact with no dependents returns empty impact list."""
    from seldon.commands.paper import _compute_impact

    result_id = _make_result(neo4j_driver, project_dir, domain_config, "metric_leaf")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        impact_tree = _compute_impact(session, result_id)

    assert impact_tree == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_impact.py -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name '_compute_impact'`.

- [ ] **Step 3: Add `_compute_impact` and `paper impact` to `seldon/commands/paper.py`**

Add to `seldon/commands/paper.py` after the existing imports:

```python
from seldon.core.graph import get_artifact
```

Add the `_compute_impact` helper function before `paper_group`:

```python
def _compute_impact(session, root_artifact_id: str) -> list[dict]:
    """
    BFS downstream traversal from root_artifact_id.

    Returns list of {artifact, rel_type, depth, parent_id} dicts
    for all artifacts that depend on (have a path to) root_artifact_id.
    """
    visited: set[str] = set()
    queue: list[tuple[str, int, Optional[str], Optional[str]]] = [
        (root_artifact_id, 0, None, None)
    ]
    results: list[dict] = []

    while queue:
        current_id, depth, parent_id, rel_type = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        # Find all artifacts that have any edge pointing to current_id
        records = session.run(
            "MATCH (dep:Artifact)-[r]->(target:Artifact {artifact_id: $id}) "
            "RETURN dep, type(r) AS rel_type",
            id=current_id,
        ).data()

        for record in records:
            dep = dict(record["dep"])
            dep_id = dep["artifact_id"]
            dep_rel = record["rel_type"].lower()
            if dep_id not in visited:
                results.append({
                    "artifact": dep,
                    "rel_type": dep_rel,
                    "depth": depth + 1,
                    "parent_id": current_id,
                })
                queue.append((dep_id, depth + 1, current_id, dep_rel))

    return results
```

Add the `paper impact` command to `paper_group`:

```python
@paper_group.command("impact")
@click.argument("artifact_name")
@click.option("--depth", "max_depth", default=0, type=int,
              help="Maximum traversal depth (0 = unlimited)")
def paper_impact(artifact_name, max_depth):
    """Show blast radius: all artifacts that depend on ARTIFACT_NAME.

    Traverses downstream edges from the named artifact and displays
    a tree of everything that would be affected by a change to it.
    """
    project_dir = Path.cwd()
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    try:
        with driver.session(database=database) as session:
            # Find artifact by name
            records = session.run(
                "MATCH (a:Artifact {name: $name}) RETURN a LIMIT 1",
                name=artifact_name,
            ).data()
            if not records:
                click.echo(f"Artifact not found: {artifact_name}", err=True)
                raise SystemExit(1)

            root = dict(records[0]["a"])
            root_id = root["artifact_id"]
            root_type = root.get("artifact_type", "?")
            root_state = root.get("state", "?")

            impact_tree = _compute_impact(session, root_id)

            # Apply depth limit if requested
            if max_depth > 0:
                impact_tree = [n for n in impact_tree if n["depth"] <= max_depth]
    finally:
        driver.close()

    click.echo(f"\nImpact analysis for: {artifact_name} ({root_type}, {root_state})")
    if not impact_tree:
        click.echo("  (no dependents found)")
        return

    # Group by type for summary
    type_counts: dict[str, int] = {}
    for node in impact_tree:
        t = node["artifact"].get("artifact_type", "?")
        type_counts[t] = type_counts.get(t, 0) + 1

    # Display tree (depth-sorted, indented)
    depth_groups: dict[int, list] = {}
    for node in impact_tree:
        d = node["depth"]
        depth_groups.setdefault(d, []).append(node)

    for d in sorted(depth_groups):
        indent = "  " + "  " * (d - 1)
        for node in depth_groups[d]:
            art = node["artifact"]
            name = art.get("name", art["artifact_id"][:8])
            atype = art.get("artifact_type", "?")
            state = art.get("state", "?")
            rel = node["rel_type"]
            state_flag = " → STALE" if state == "stale" else ""
            click.echo(f"{indent}├── {atype}: {name} ({rel}){state_flag}")

    summary = ", ".join(f"{cnt} {t.lower()}{'s' if cnt != 1 else ''}"
                        for t, cnt in sorted(type_counts.items()))
    click.echo(f"\nBlast radius: {summary}")
```

Also add `Optional` to the import at the top of `paper.py` (update the existing `from typing` line, or add if not present):

```python
from typing import Optional
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_impact.py -v 2>&1 | tail -15
```

Expected: all 3 tests PASSED.

- [ ] **Step 5: Run full test suite**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 376 + 3 = 379 passed, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add seldon/commands/paper.py tests/test_impact.py
git commit -m "feat: seldon paper impact blast-radius command (AD-018)"
```

---

## Task 4: `seldon verify` command

**Files:**
- Create: `seldon/commands/verify.py`
- Create: `tests/test_verify.py`

This is the largest task. `verify` runs 7 ordered checks, collects results, and prints a summary. Each check is a separate function for testability.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verify.py`:

```python
"""
Tests for `seldon verify` — project integrity checks.

Integration tests require Neo4j. Unit tests use mocks.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from seldon.core.artifacts import create_artifact, transition_state
from seldon.domain.loader import load_domain_config

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def minimal_project(tmp_path):
    """A minimal project directory with seldon.yaml and paper/sections/."""
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: testproject\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n  database: seldon-test\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    sections_dir = tmp_path / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Check 1: File hash integrity
# ---------------------------------------------------------------------------

def test_check_file_hashes_clean(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Artifact whose file matches stored hash passes check 1."""
    from seldon.commands.verify import check_file_hashes

    # Create a real file and record its hash
    section_file = project_dir / "paper" / "sections" / "01_intro.md"
    section_file.parent.mkdir(parents=True)
    section_file.write_text("# Introduction\n\nTest content.\n")
    file_hash = hashlib.sha256(section_file.read_bytes()).hexdigest()

    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={
            "name": "sec_intro", "title": "Introduction",
            "file_path": str(section_file), "content_hash": file_hash,
        },
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        mismatches = check_file_hashes(session, NEO4J_DB, project_dir)

    assert mismatches == []


def test_check_file_hashes_detects_modified(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Modified file (hash mismatch) appears in check 1 output."""
    from seldon.commands.verify import check_file_hashes

    section_file = project_dir / "paper" / "sections" / "01_intro.md"
    section_file.parent.mkdir(parents=True)
    section_file.write_text("Original content.\n")
    old_hash = hashlib.sha256(b"Different original content.\n").hexdigest()

    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={
            "name": "sec_intro", "title": "Introduction",
            "file_path": str(section_file), "content_hash": old_hash,
        },
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        mismatches = check_file_hashes(session, NEO4J_DB, project_dir)

    assert len(mismatches) == 1
    assert "sec_intro" in mismatches[0] or str(section_file) in mismatches[0]


# ---------------------------------------------------------------------------
# Check 5: Stale artifacts
# ---------------------------------------------------------------------------

def test_check_stale_detects_stale_artifact(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Stale result is reported in check 5."""
    from seldon.commands.verify import check_stale_artifacts

    result_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"name": "metric_old", "value": 1.0, "units": "score", "description": "old"},
        actor="human", authority="accepted",
    )
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id, artifact_type="Result",
        current_state="proposed", new_state="verified", actor="human", authority="accepted",
    )
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id, artifact_type="Result",
        current_state="verified", new_state="stale", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        stale_report = check_stale_artifacts(session, NEO4J_DB)

    names = [entry["name"] for entry in stale_report]
    assert "metric_old" in names


def test_check_stale_clean_project(neo4j_driver, project_dir, domain_config, clean_test_db):
    """No stale artifacts returns empty list."""
    from seldon.commands.verify import check_stale_artifacts

    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"name": "metric_fresh", "value": 1.0, "units": "score", "description": "fresh"},
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        stale_report = check_stale_artifacts(session, NEO4J_DB)

    assert stale_report == []


# ---------------------------------------------------------------------------
# Check 7: Unregistered files
# ---------------------------------------------------------------------------

def test_check_unregistered_detects_new_file(neo4j_driver, project_dir, domain_config, clean_test_db):
    """File in sections/ without a PaperSection artifact is reported."""
    from seldon.commands.verify import check_unregistered_files

    sections_dir = project_dir / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "01_intro.md").write_text("# Intro\n")
    (sections_dir / "02_methods.md").write_text("# Methods\n")

    # Register only the first file
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={
            "name": "sec_intro", "title": "Introduction",
            "file_path": str(sections_dir / "01_intro.md"),
        },
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        unregistered = check_unregistered_files(session, NEO4J_DB, project_dir)

    assert len(unregistered) == 1
    assert "02_methods.md" in unregistered[0]


def test_check_unregistered_clean(neo4j_driver, project_dir, domain_config, clean_test_db):
    """All section files registered returns empty list."""
    from seldon.commands.verify import check_unregistered_files

    sections_dir = project_dir / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    section_file = sections_dir / "01_intro.md"
    section_file.write_text("# Intro\n")

    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={
            "name": "sec_intro", "title": "Introduction",
            "file_path": str(section_file),
        },
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        unregistered = check_unregistered_files(session, NEO4J_DB, project_dir)

    assert unregistered == []


# ---------------------------------------------------------------------------
# Exit code tests
# ---------------------------------------------------------------------------

def test_verify_exit_codes(neo4j_driver, project_dir, domain_config, clean_test_db):
    """check functions return correct structures for building exit codes."""
    from seldon.commands.verify import check_stale_artifacts, check_file_hashes

    with neo4j_driver.session(database=NEO4J_DB) as session:
        # Clean project → both checks return empty
        stale = check_stale_artifacts(session, NEO4J_DB)
        hashes = check_file_hashes(session, NEO4J_DB, project_dir)

    assert stale == []   # no warnings
    assert hashes == []  # no issues
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_verify.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'seldon.commands.verify'`.

- [ ] **Step 3: Create `seldon/commands/verify.py`**

```python
"""
seldon verify — project integrity gate.

Runs 7 checks in order and reports with ✓/⚠/✗. Exit codes:
  0: all clean
  1: warnings only (stale artifacts, open blocking tasks)
  2: issues found (hash mismatch, ontology drift, unregistered files)

Usage:
    seldon verify
    seldon verify --fix     # auto-fix: paper sync, ontology sync, file registration
    seldon verify --quiet   # exit code only, no output
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Optional

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.domain.loader import load_domain_config
from seldon.paper.build import REFERENCE_PATTERN

ISSUE = "✗"
WARN  = "⚠"
OK    = "✓"


# ---------------------------------------------------------------------------
# Check functions (each returns a list; empty = clean)
# ---------------------------------------------------------------------------

def check_file_hashes(session, database: str, project_dir: Path) -> list[str]:
    """
    Check 1: File hash integrity.

    Queries all artifacts with file_path or path + content_hash.
    Returns list of mismatch description strings (empty = all clean).
    """
    records = session.run("""
        MATCH (a:Artifact)
        WHERE (a.file_path IS NOT NULL OR a.path IS NOT NULL)
          AND a.content_hash IS NOT NULL
        RETURN coalesce(a.file_path, a.path) AS file_path,
               a.content_hash AS stored_hash,
               coalesce(a.name, a.artifact_id) AS artifact_name
    """).data()

    mismatches = []
    for r in records:
        file_path = Path(r["file_path"])
        if not file_path.is_absolute():
            file_path = project_dir / file_path
        if not file_path.exists():
            mismatches.append(f"{r['artifact_name']}: file not found ({file_path})")
            continue
        current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if current_hash != r["stored_hash"]:
            mismatches.append(f"{r['artifact_name']}: modified since last sync ({file_path.name})")
    return mismatches


def check_ontology_freshness(
    driver, database: str
) -> tuple[bool, Optional[str]]:
    """
    Check 2: Ontology freshness.

    Returns (is_fresh, message). is_fresh=True if up to date or no ontology config.
    message is None when fresh.
    """
    try:
        from seldon.commands.ontology import ONTOLOGY_MASTER_DB
        with driver.session(database=database) as session:
            replica_result = session.run(
                "MATCH (m:_OntologyReplicaMeta {key: 'replica'}) RETURN m.epoch AS epoch"
            ).single()
        if replica_result is None:
            return True, None  # No ontology synced yet — not an issue

        local_epoch = replica_result["epoch"]

        with driver.session(database=ONTOLOGY_MASTER_DB) as master_session:
            master_result = master_session.run(
                "MATCH (m:_OntologyMeta {key: 'master'}) RETURN m.epoch AS epoch"
            ).single()
        if master_result is None:
            return True, None  # Master not populated — not an issue

        master_epoch = master_result["epoch"]
        if master_epoch > local_epoch:
            return False, f"Local epoch {local_epoch}, master epoch {master_epoch} — run `seldon ontology sync`"
        return True, None
    except Exception:
        # Master unreachable or no ontology config — skip silently
        return True, None


def check_stale_artifacts(session, database: str) -> list[dict]:
    """
    Check 5: Stale artifacts.

    Returns list of {name, artifact_type, artifact_id} dicts for stale artifacts.
    Empty = all clean.
    """
    records = session.run(
        "MATCH (a:Artifact {state: 'stale'}) "
        "RETURN coalesce(a.name, a.artifact_id) AS name, "
        "a.artifact_type AS artifact_type, a.artifact_id AS artifact_id"
    ).data()
    return [dict(r) for r in records]


def check_blocking_tasks(session, database: str) -> list[dict]:
    """
    Check 6: Open blocking tasks.

    Returns list of {task_name, task_id, blocks_name, blocks_type} for blocking tasks.
    Empty = no blockers.
    """
    records = session.run("""
        MATCH (t:ResearchTask)-[:BLOCKS]->(target:Artifact)
        WHERE t.state IN ['accepted', 'in_progress']
        RETURN coalesce(t.description, t.artifact_id) AS task_name,
               t.artifact_id AS task_id,
               coalesce(target.name, target.artifact_id) AS blocks_name,
               target.artifact_type AS blocks_type
    """).data()
    return [dict(r) for r in records]


def check_unregistered_files(session, database: str, project_dir: Path) -> list[str]:
    """
    Check 7: Unregistered section files.

    Compares files in paper/sections/ against artifacts with matching file_path.
    Returns list of unregistered file path strings. Empty = all registered.
    """
    sections_dir = project_dir / "paper" / "sections"
    if not sections_dir.exists():
        return []

    section_files = sorted(sections_dir.glob("*.md"))
    if not section_files:
        return []

    # Get all file_path values from PaperSection artifacts
    records = session.run(
        "MATCH (a:Artifact:PaperSection) WHERE a.file_path IS NOT NULL "
        "RETURN a.file_path AS file_path"
    ).data()
    registered_paths = {r["file_path"] for r in records}
    # Also match by filename stem (some registrations use relative paths)
    registered_names = {Path(p).name for p in registered_paths}

    unregistered = []
    for f in section_files:
        if str(f) not in registered_paths and f.name not in registered_names:
            unregistered.append(str(f))
    return unregistered


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@click.command("verify")
@click.option("--fix", is_flag=True, default=False,
              help="Auto-fix: run paper sync, ontology sync, register untracked files.")
@click.option("--quiet", is_flag=True, default=False,
              help="Exit code only, no output.")
@click.pass_context
def verify_command(ctx, fix, quiet):
    """Run project integrity checks.

    Exit codes: 0=clean, 1=warnings only, 2=issues found.

    Checks run in order:
      1. File hash integrity (files modified since last sync)
      2. Ontology freshness (local epoch vs master)
      3. Glossary compliance (if paper/check_glossary.py exists)
      4. Reference resolution (unresolvable {{...}} tokens)
      5. Stale artifacts (and their blast radius)
      6. Open blocking tasks
      7. Unregistered section files
    """
    project_dir = Path.cwd()
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    issues: list[str] = []    # exit code 2
    warnings: list[str] = []  # exit code 1
    results: list[tuple[str, str, str]] = []  # (check_name, symbol, detail)

    try:
        with driver.session(database=database) as session:

            # Check 1: File hash integrity
            hash_mismatches = check_file_hashes(session, database, project_dir)
            if hash_mismatches:
                detail = f"{len(hash_mismatches)} modified: {', '.join(m.split(':')[0] for m in hash_mismatches)}"
                results.append(("File hashes", ISSUE, detail))
                issues.append("file_hashes")
                if fix:
                    subprocess.run(["seldon", "paper", "sync"], cwd=project_dir)
            else:
                n_tracked = session.run(
                    "MATCH (a:Artifact) WHERE a.content_hash IS NOT NULL RETURN count(a) AS n"
                ).single()["n"]
                results.append(("File hashes", OK, f"All {n_tracked} tracked files in sync"))

            # Check 2: Ontology freshness
            is_fresh, msg = check_ontology_freshness(driver, database)
            if not is_fresh:
                results.append(("Ontology", ISSUE, msg))
                issues.append("ontology")
                if fix:
                    subprocess.run(["seldon", "ontology", "sync"], cwd=project_dir)
            else:
                results.append(("Ontology", OK, "Up to date"))

            # Check 3: Glossary compliance
            glossary_script = project_dir / "paper" / "check_glossary.py"
            if glossary_script.exists():
                proc = subprocess.run(
                    ["python", str(glossary_script), "--violations-only"],
                    capture_output=True, text=True, cwd=project_dir,
                )
                if proc.returncode != 0:
                    violation_lines = [l for l in proc.stdout.splitlines() if l.strip() and l.strip()[0] != "="]
                    results.append(("Glossary", ISSUE, f"{len(violation_lines)} violation(s)"))
                    issues.append("glossary")
                else:
                    results.append(("Glossary", OK, "No violations"))
            else:
                results.append(("Glossary", OK, "No glossary (skipped)"))

            # Check 4: Reference resolution
            sections_dir = project_dir / "paper" / "sections"
            unresolved: list[str] = []
            if sections_dir.exists():
                from seldon.paper.build import load_named_artifacts
                artifacts = load_named_artifacts(driver, database)
                for section_file in sorted(sections_dir.glob("*.md")):
                    text = section_file.read_text(encoding="utf-8")
                    for match in REFERENCE_PATTERN.finditer(text):
                        reftype, name, field = match.group(1), match.group(2), match.group(3)
                        key = f"{reftype}:{name}"
                        if key not in artifacts:
                            unresolved.append(f"{key} in {section_file.name}")

            if unresolved:
                results.append(("References", ISSUE,
                                 f"{len(unresolved)} unresolvable: {unresolved[0]}{'...' if len(unresolved) > 1 else ''}"))
                issues.append("references")
            else:
                results.append(("References", OK, "All tokens resolve"))

            # Check 5: Stale artifacts
            stale = check_stale_artifacts(session, database)
            if stale:
                names = ", ".join(s["name"] for s in stale[:3])
                suffix = "..." if len(stale) > 3 else ""
                results.append(("Stale artifacts", WARN,
                                 f"{len(stale)} stale: {names}{suffix}"))
                warnings.append("stale")
            else:
                results.append(("Stale artifacts", OK, "None"))

            # Check 6: Blocking tasks
            blocking = check_blocking_tasks(session, database)
            if blocking:
                detail = f"{len(blocking)} blocking task{'s' if len(blocking) != 1 else ''}"
                results.append(("Blocking tasks", WARN, detail))
                warnings.append("blocking_tasks")
            else:
                results.append(("Blocking tasks", OK, "None"))

            # Check 7: Unregistered files
            unregistered = check_unregistered_files(session, database, project_dir)
            if unregistered:
                names = ", ".join(Path(p).name for p in unregistered[:3])
                suffix = "..." if len(unregistered) > 3 else ""
                results.append(("Unregistered files", ISSUE,
                                 f"{len(unregistered)} unregistered: {names}{suffix}"))
                issues.append("unregistered")
                if fix:
                    from seldon.paper.sync import _register_section
                    domain_name = config["project"].get("domain", "research")
                    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
                    domain_config = load_domain_config(domain_yaml)
                    for path_str in unregistered:
                        _register_section(driver, database, project_dir, domain_config,
                                          Path(path_str), actor="human")
            else:
                results.append(("Unregistered files", OK, "None"))

    finally:
        driver.close()

    if quiet:
        exit_code = 2 if issues else (1 if warnings else 0)
        raise SystemExit(exit_code)

    # Print report
    project_name = config["project"].get("name", project_dir.name)
    click.echo(f"\nseldon verify — {project_name}\n")

    label_width = max(len(r[0]) for r in results) + 2
    for check_name, symbol, detail in results:
        label = check_name.ljust(label_width)
        click.echo(f"  {symbol} {label} {detail}")

    total_issues = len(issues)
    total_warnings = len(warnings)
    if total_issues or total_warnings:
        parts = []
        if total_issues:
            parts.append(f"{total_issues} issue{'s' if total_issues != 1 else ''}")
        if total_warnings:
            parts.append(f"{total_warnings} warning{'s' if total_warnings != 1 else ''}")
        fix_hint = "" if fix else " Run `seldon verify --fix` to auto-resolve fixable issues."
        click.echo(f"\n  {', '.join(parts)}.{fix_hint}")
    else:
        click.echo("\n  All checks passed.")

    click.echo()
    exit_code = 2 if issues else (1 if warnings else 0)
    raise SystemExit(exit_code)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_verify.py -v 2>&1 | tail -20
```

Expected: all 9 tests PASSED.

- [ ] **Step 5: Run full test suite**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 379 + 9 = 388 passed, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add seldon/commands/verify.py tests/test_verify.py
git commit -m "feat: seldon verify project integrity gate with 7 checks and --fix mode (AD-018)"
```

---

## Task 5: Register commands, update closeout, and update CLAUDE.md

**Files:**
- Modify: `seldon/cli.py`
- Modify: `seldon/commands/session.py`
- Modify: `seldon/CLAUDE.md`

No tests needed — CLI registration is covered by the integration tests in Tasks 3 and 4.

- [ ] **Step 1: Register `verify` in `seldon/cli.py`**

In `seldon/cli.py`, add import:

```python
from seldon.commands.verify import verify_command
```

And after the last `main.add_command` line:

```python
main.add_command(verify_command, name="verify")
```

- [ ] **Step 2: Verify the command is reachable**

```bash
seldon verify --help
```

Expected output shows: `Usage: seldon verify [OPTIONS]` with `--fix` and `--quiet` options.

- [ ] **Step 3: Add verify tip to `seldon/commands/session.py` closeout**

In `closeout_command`, after the final `click.echo(f"{border}\n")` line, add:

```python
    click.echo("Tip: run `seldon verify` before committing to check project integrity.\n")
```

- [ ] **Step 4: Update `seldon/CLAUDE.md` Skills table**

Find the Skills table in `CLAUDE.md` and add two new rows after the `paper build` row:

```markdown
| `verify`       | Before committing, or after any edit session | `seldon verify [--fix]` |
| `paper impact` | Check blast radius of a change | `seldon paper impact <name>` |
```

Also update the Session Protocol section — replace the End step:

```markdown
**End:**
1. `/closeout` — structured handoff, then `seldon verify` before commit
2. Commit and push
```

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 388 passed, 0 failures.

- [ ] **Step 6: Push all changes**

```bash
git add seldon/cli.py seldon/commands/session.py seldon/CLAUDE.md
git commit -m "feat: register seldon verify, add closeout tip, update CLAUDE.md (AD-018)"
git push
```

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|-------------|------|
| `compute_figure_numbers`: flat (Figure 1, 2, 3) | Task 1 Step 3 |
| `compute_figure_numbers`: chaptered (Figure 2.1, 2.3) | Task 1 Step 3 |
| `compute_table_numbers`: same patterns | Task 1 Step 3 |
| `{{figure:NAME}}` resolves in paper build | Task 2 Step 3 |
| `{{table:NAME}}` resolves in paper build | Task 2 Step 3 |
| `{{section:NAME}}` resolves in paper build | Task 2 Step 3 |
| `seldon paper impact` shows blast radius tree | Task 3 Step 3 |
| `seldon verify` runs all 7 checks | Task 4 Step 3 |
| `seldon verify` exit codes 0, 1, 2 | Task 4 Step 3 |
| `seldon verify --fix`: file sync, ontology sync, file registration | Task 4 Step 3 |
| `seldon verify --fix` does NOT auto-fix: glossary, references, staleness, tasks | Task 4 Step 3 |
| `seldon verify --quiet` no output, exit code only | Task 4 Step 3 |
| `seldon closeout` suggests running verify | Task 5 Step 3 |
| CLAUDE.md updated | Task 5 Step 4 |

All requirements covered.

### Placeholder scan

No TBD, TODO, or "similar to above" entries. All code is complete.

### Type consistency

- `_compute_xref_lookups(session, database)` returns `tuple[dict, dict, dict]` — matches `resolve_xref_tokens` call signature `(text, figure_by_name, table_by_name, section_by_name)` ✓
- `build_name_lookup(session, fig_numbers, tbl_numbers, sec_display)` returns `tuple[dict, dict, dict]` ✓
- `_compute_impact(session, root_artifact_id)` returns `list[dict]` — each dict has keys `artifact`, `rel_type`, `depth`, `parent_id` ✓
- `check_file_hashes(session, database, project_dir)` returns `list[str]` ✓
- `check_stale_artifacts(session, database)` returns `list[dict]` with `name` key — tests access `entry["name"]` ✓
- `check_unregistered_files(session, database, project_dir)` returns `list[str]` ✓
- `_register_section` imported from `seldon.paper.sync` — used in verify --fix for check 7 ✓

### Known constraint: `_compute_xref_lookups` monkeypatch path

Tests monkeypatch `"seldon.paper.build._compute_xref_lookups"`. This requires `_compute_xref_lookups` to be defined in `build.py` (not imported into the namespace — which it is, as a local function). The import of `build_name_lookup` from `numbering.py` is internal to `_compute_xref_lookups`. The monkeypatch targets the function by its fully-qualified name in the module where it's called, which is correct for this pattern ✓
