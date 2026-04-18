# AD-018 Part A: Document Structure Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Table artifact type, extend PaperSection/Figure properties, and add document hierarchy relationship types to `seldon/domain/research.yaml`, with full schema and graph integration tests.

**Architecture:** Pure data model changes — no CLI code. All changes are YAML edits to `research.yaml` plus tests in `test_domain.py` (schema, no Neo4j) and a new `tests/test_document_structure.py` (graph integration, requires Neo4j). Part B depends on this being merged first.

**Tech Stack:** PyYAML, Pydantic (DomainConfig validation), Neo4j (integration tests), pytest

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `seldon/domain/research.yaml` | Modify | Table type, PaperSection/Figure property extensions, 5 new relationship types, 2 relationship updates |
| `tests/test_domain.py` | Modify | Fix artifact count assertion (13→14), add 12 schema tests |
| `tests/test_document_structure.py` | Create | 7 graph integration tests for the new types and relationships |

---

## Task 1: Add Table artifact type and state machine

**Files:**
- Modify: `seldon/domain/research.yaml` (artifact_types and state_machines sections)
- Modify: `tests/test_domain.py` (artifact count assertion + 3 new schema tests)

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_domain.py`:

```python
# ---------------------------------------------------------------------------
# Table artifact type tests (AD-018 Part A)
# ---------------------------------------------------------------------------


def test_table_artifact_type_exists(research_config):
    """Table is a valid artifact type in domain config."""
    assert "Table" in research_config.artifact_types


def test_table_required_properties(research_config):
    """Table requires name and caption."""
    required = research_config.get_required_properties("Table")
    assert "name" in required
    assert "caption" in required


def test_table_state_machine(research_config):
    """Table state machine: proposed → draft → review → published → stale transitions valid."""
    sm = research_config.state_machines["Table"]
    assert "draft" in sm["proposed"]
    assert "review" in sm["draft"]
    assert "published" in sm["review"]
    assert "stale" in sm["published"]
    assert "draft" in sm["stale"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/brock/Documents/GitHub/seldon
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_domain.py -k "table" -v 2>&1 | tail -15
```

Expected: `KeyError: 'Table'` or `AssertionError` — confirms tests are real.

- [ ] **Step 3: Add Table to `research.yaml`**

In `seldon/domain/research.yaml`, add under `artifact_types:` after the `Figure:` block:

```yaml
  Table:
    properties:
      name:
        required: true
        description: "Table identifier (e.g., 'table_comparison_results')"
      caption:
        required: true
        description: "Table caption text"
      table_number:
        category: documentation
        description: "Display number (e.g., '5.1' for Chapter 5, Table 1) — computed from graph position at build time"
      generating_script:
        category: documentation
        description: "Name of Script artifact that produces this table"
      data_sources:
        category: documentation
        description: "DataFile artifacts that feed this table"
      file_path:
        category: documentation
        description: "Path to generated table file if applicable"
```

In `seldon/domain/research.yaml`, add under `state_machines:` after the `Figure:` block:

```yaml
  Table:
    proposed: [draft, review]
    draft: [review, stale]
    review: [published, draft]
    published: [stale]
    stale: [draft]
```

- [ ] **Step 4: Fix the artifact count assertion in `tests/test_domain.py`**

Find and update the count in `test_load_domain_config`:

```python
# OLD:
assert len(research_config.artifact_types) == 13  # dict with 13 keys (OntologyTerm added in AD-017)

# NEW:
assert len(research_config.artifact_types) == 14  # Table added in AD-018
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_domain.py -k "table or load_domain" -v 2>&1 | tail -15
```

Expected: `test_table_artifact_type_exists PASSED`, `test_table_required_properties PASSED`, `test_table_state_machine PASSED`, `test_load_domain_config PASSED`.

- [ ] **Step 6: Run full test suite**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 349 + 3 = 352 passed, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add seldon/domain/research.yaml tests/test_domain.py
git commit -m "feat: add Table artifact type and state machine (AD-018 Part A)"
```

---

## Task 2: Extend PaperSection and Figure properties

**Files:**
- Modify: `seldon/domain/research.yaml` (PaperSection and Figure artifact_types entries)
- Modify: `tests/test_domain.py` (3 new schema tests)

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_domain.py`:

```python
# ---------------------------------------------------------------------------
# PaperSection and Figure property extension tests (AD-018 Part A)
# ---------------------------------------------------------------------------


def test_papersection_has_sequence_property(research_config):
    """PaperSection has a sequence property for document ordering."""
    props = research_config.get_all_schema_properties("PaperSection")
    assert "sequence" in props


def test_papersection_has_depth_property(research_config):
    """PaperSection has a depth property: 0=chapter, 1=section, 2=subsection."""
    props = research_config.get_all_schema_properties("PaperSection")
    assert "depth" in props


def test_figure_has_caption_property(research_config):
    """Figure has caption as a required property."""
    required = research_config.get_required_properties("Figure")
    assert "caption" in required
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_domain.py -k "sequence or depth or caption" -v 2>&1 | tail -15
```

Expected: `AssertionError` — confirms tests are real.

- [ ] **Step 3: Extend PaperSection in `research.yaml`**

In `seldon/domain/research.yaml`, replace the `PaperSection:` artifact type entry with:

```yaml
  PaperSection:
    properties:
      name:
        required: true
        description: "Section identifier"
      title:
        required: true
        description: "Section title"
      file_path:
        category: documentation
        description: "Path to the section markdown file"
      content_hash:
        category: documentation
        description: "SHA-256 hash of file content at last sync"
      sequence:
        category: documentation
        description: "Ordering within parent (1, 2, 3...). Determines document order and figure/table numbering."
      depth:
        category: documentation
        description: "Hierarchy depth: 0 = chapter/top-level, 1 = section, 2 = subsection"
```

- [ ] **Step 4: Extend Figure in `research.yaml`**

In `seldon/domain/research.yaml`, replace the `Figure:` artifact type entry with:

```yaml
  Figure:
    properties:
      name:
        required: true
        description: "Figure identifier (e.g., fig_1_convergence)"
      caption:
        required: true
        description: "Figure caption text"
      description:
        required: true
        description: "What the figure shows"
      figure_number:
        category: documentation
        description: "Display number (e.g., '2.3' for Chapter 2, Figure 3) — computed from graph position at build time"
      interpretation:
        category: documentation
        description: "Key takeaway from this figure"
      data_source:
        category: documentation
        description: "Which DataFiles/Results this figure renders"
      file_path:
        category: documentation
        description: "Path to the generated figure file"
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_domain.py -k "sequence or depth or caption" -v 2>&1 | tail -15
```

Expected: all 3 tests PASSED.

- [ ] **Step 6: Run full test suite**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 352 + 3 = 355 passed, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add seldon/domain/research.yaml tests/test_domain.py
git commit -m "feat: extend PaperSection (sequence, depth) and Figure (caption, figure_number) properties (AD-018)"
```

---

## Task 3: Add new relationship types

**Files:**
- Modify: `seldon/domain/research.yaml` (relationship_types section)
- Modify: `tests/test_domain.py` (6 new schema tests)

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_domain.py`:

```python
# ---------------------------------------------------------------------------
# New relationship type tests (AD-018 Part A)
# ---------------------------------------------------------------------------


def test_contains_section_relationship(research_config):
    """contains_section: PaperSection → PaperSection (document hierarchy)."""
    assert "contains_section" in research_config.relationship_types
    rel = research_config.relationship_types["contains_section"]
    assert "PaperSection" in rel.from_types
    assert "PaperSection" in rel.to_types


def test_appears_in_relationship(research_config):
    """appears_in: Figure or Table → PaperSection."""
    assert "appears_in" in research_config.relationship_types
    rel = research_config.relationship_types["appears_in"]
    assert "Figure" in rel.from_types
    assert "Table" in rel.from_types
    assert "PaperSection" in rel.to_types


def test_references_figure_relationship(research_config):
    """references_figure: PaperSection → Figure."""
    assert "references_figure" in research_config.relationship_types
    rel = research_config.relationship_types["references_figure"]
    assert "PaperSection" in rel.from_types
    assert "Figure" in rel.to_types


def test_references_table_relationship(research_config):
    """references_table: PaperSection → Table."""
    assert "references_table" in research_config.relationship_types
    rel = research_config.relationship_types["references_table"]
    assert "PaperSection" in rel.from_types
    assert "Table" in rel.to_types


def test_tabulates_relationship(research_config):
    """tabulates: Table → Result."""
    assert "tabulates" in research_config.relationship_types
    rel = research_config.relationship_types["tabulates"]
    assert "Table" in rel.from_types
    assert "Result" in rel.to_types


def test_generated_by_includes_table(research_config):
    """Table can be the source of a generated_by relationship."""
    rel = research_config.relationship_types["generated_by"]
    assert "Table" in rel.from_types
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_domain.py -k "contains_section or appears_in or references_figure or references_table or tabulates or generated_by_includes" -v 2>&1 | tail -15
```

Expected: `AssertionError` or `KeyError` — confirms tests are real.

- [ ] **Step 3: Add new relationship types to `research.yaml`**

In `seldon/domain/research.yaml`, add to `relationship_types:` after the `references_ontology:` entry:

```yaml
  contains_section:
    from_types: [PaperSection]
    to_types: [PaperSection]

  appears_in:
    from_types: [Figure, Table]
    to_types: [PaperSection]

  references_figure:
    from_types: [PaperSection]
    to_types: [Figure]

  references_table:
    from_types: [PaperSection]
    to_types: [Table]

  tabulates:
    from_types: [Table]
    to_types: [Result]
```

- [ ] **Step 4: Update `generated_by` and `contains` in `research.yaml`**

Find and replace `generated_by:` in `relationship_types:`:

```yaml
# OLD:
  generated_by:
    from_types: [Result, Figure]
    to_types: [Script]

# NEW:
  generated_by:
    from_types: [Result, Figure, Table]
    to_types: [Script]
```

The `contains` relationship stays as-is (Figure→Result data relationship, not document hierarchy).

- [ ] **Step 5: Run tests to confirm they pass**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_domain.py -k "contains_section or appears_in or references_figure or references_table or tabulates or generated_by_includes" -v 2>&1 | tail -15
```

Expected: all 6 tests PASSED.

- [ ] **Step 6: Run full test suite**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 355 + 6 = 361 passed, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add seldon/domain/research.yaml tests/test_domain.py
git commit -m "feat: add document structure relationship types (AD-018): contains_section, appears_in, references_figure, references_table, tabulates"
```

---

## Task 4: Graph integration tests for document structure

**Files:**
- Create: `tests/test_document_structure.py`

These tests verify that the new types and relationships can be created and traversed in Neo4j. They use real Neo4j (require `neo4j_driver`, `project_dir`, `domain_config`, `clean_test_db` fixtures from conftest.py).

- [ ] **Step 1: Create the test file**

Create `tests/test_document_structure.py`:

```python
"""
Graph integration tests for AD-018 document structure types and relationships.

Requires Neo4j. Uses seldon-test database (cleaned before each test).
Tests create Table, PaperSection hierarchy, Figure with appears_in edges,
and verify traversal.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.domain.loader import load_domain_config

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def test_create_table_artifact(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Create a Table artifact; verify it exists in graph with correct labels."""
    table_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Table",
        properties={
            "name": "table_comparison",
            "caption": "Comparison of fitness functions across seed counts",
        },
        actor="human",
        authority="accepted",
    )
    assert table_id is not None

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (t:Artifact:Table {artifact_id: $id}) RETURN t",
            id=table_id,
        ).single()
    assert result is not None
    node = dict(result["t"])
    assert node["name"] == "table_comparison"
    assert node["caption"] == "Comparison of fitness functions across seed counts"
    assert node["state"] == "proposed"


def test_create_hierarchy(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Create chapter (depth 0) + section (depth 1), link via contains_section, verify traversal."""
    chapter_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={
            "name": "chapter_02",
            "title": "Methods",
            "depth": 0,
            "sequence": 2,
        },
        actor="human",
        authority="accepted",
    )

    section_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={
            "name": "section_02_01",
            "title": "Fitness Functions",
            "depth": 1,
            "sequence": 1,
        },
        actor="human",
        authority="accepted",
    )

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=chapter_id,
        to_id=section_id,
        rel_type="contains_section",
        actor="human",
        authority="accepted",
    )

    # Verify traversal: chapter -[CONTAINS_SECTION]-> section
    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (ch:PaperSection {artifact_id: $ch_id})-[:CONTAINS_SECTION]->(sec:PaperSection) "
            "RETURN sec.name AS name",
            ch_id=chapter_id,
        ).data()
    assert len(result) == 1
    assert result[0]["name"] == "section_02_01"


def test_figure_appears_in_section(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Create Figure, link to PaperSection via appears_in, verify edge exists."""
    section_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={"name": "sec_results", "title": "Results"},
        actor="human",
        authority="accepted",
    )

    figure_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Figure",
        properties={
            "name": "fig_convergence",
            "caption": "Convergence curves for 4-terminal experiments",
            "description": "GP convergence over generations",
        },
        actor="human",
        authority="accepted",
    )

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=figure_id,
        to_id=section_id,
        rel_type="appears_in",
        actor="human",
        authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (f:Figure {artifact_id: $fid})-[:APPEARS_IN]->(s:PaperSection) "
            "RETURN s.name AS name",
            fid=figure_id,
        ).data()
    assert len(result) == 1
    assert result[0]["name"] == "sec_results"


def test_table_tabulates_result(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Create Table, link to Result via tabulates, verify edge exists."""
    result_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={
            "name": "accuracy_4t",
            "value": 0.95,
            "units": "fraction",
            "description": "Accuracy with 4 terminals",
        },
        actor="human",
        authority="accepted",
    )

    table_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Table",
        properties={
            "name": "table_accuracy",
            "caption": "Accuracy by terminal count",
        },
        actor="human",
        authority="accepted",
    )

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=table_id,
        to_id=result_id,
        rel_type="tabulates",
        actor="human",
        authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (t:Table {artifact_id: $tid})-[:TABULATES]->(r:Result) "
            "RETURN r.name AS name",
            tid=table_id,
        ).data()
    assert len(result) == 1
    assert result[0]["name"] == "accuracy_4t"


def test_cross_reference_edge(neo4j_driver, project_dir, domain_config, clean_test_db):
    """PaperSection -[references_figure]-> Figure edge exists after create_link."""
    section_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={"name": "sec_discussion", "title": "Discussion"},
        actor="human",
        authority="accepted",
    )
    figure_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Figure",
        properties={
            "name": "fig_comparison",
            "caption": "Comparison of search strategies",
            "description": "Side-by-side comparison",
        },
        actor="human",
        authority="accepted",
    )

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id,
        to_id=figure_id,
        rel_type="references_figure",
        actor="human",
        authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (s:PaperSection {artifact_id: $sid})-[:REFERENCES_FIGURE]->(f:Figure) "
            "RETURN f.name AS name",
            sid=section_id,
        ).data()
    assert len(result) == 1
    assert result[0]["name"] == "fig_comparison"


def test_staleness_traversal_through_table(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Result goes stale → Table that tabulates it can be found via downstream traversal."""
    result_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={
            "name": "metric_old",
            "value": 0.8,
            "units": "fraction",
            "description": "Old metric",
        },
        actor="human",
        authority="accepted",
    )
    # Transition to verified so we can then go to stale
    transition_state(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=result_id,
        artifact_type="Result",
        current_state="proposed",
        new_state="verified",
        actor="human",
        authority="accepted",
    )
    transition_state(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=result_id,
        artifact_type="Result",
        current_state="verified",
        new_state="stale",
        actor="human",
        authority="accepted",
    )

    table_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Table",
        properties={"name": "table_old_metrics", "caption": "Old metrics table"},
        actor="human",
        authority="accepted",
    )
    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=table_id,
        to_id=result_id,
        rel_type="tabulates",
        actor="human",
        authority="accepted",
    )

    # Verify: can find the table via upstream of the stale result
    from seldon.core.graph import get_dependents
    with neo4j_driver.session(database=NEO4J_DB) as session:
        dependents = get_dependents(session, result_id)
    dep_names = [d["name"] for d in dependents]
    assert "table_old_metrics" in dep_names


def test_section_references_table_edge(neo4j_driver, project_dir, domain_config, clean_test_db):
    """PaperSection -[references_table]-> Table edge created and traversable."""
    section_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={"name": "sec_results", "title": "Results"},
        actor="human",
        authority="accepted",
    )
    table_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Table",
        properties={"name": "table_summary", "caption": "Summary statistics"},
        actor="human",
        authority="accepted",
    )
    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id,
        to_id=table_id,
        rel_type="references_table",
        actor="human",
        authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (s:PaperSection {artifact_id: $sid})-[:REFERENCES_TABLE]->(t:Table) "
            "RETURN t.name AS name",
            sid=section_id,
        ).data()
    assert len(result) == 1
    assert result[0]["name"] == "table_summary"
```

- [ ] **Step 2: Run tests to confirm they pass**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/test_document_structure.py -v 2>&1 | tail -20
```

Expected: all 7 tests PASSED.

- [ ] **Step 3: Run full test suite**

```bash
NEO4J_PASSWORD="i'llbeback" python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 361 + 7 = 368 passed, 0 failures.

- [ ] **Step 4: Commit**

```bash
git add tests/test_document_structure.py
git commit -m "test: graph integration tests for document structure types and relationships (AD-018)"
```

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|-------------|------|
| Table artifact type with name (required), caption (required), table_number, generating_script, data_sources, file_path | Task 1 Step 3 |
| Table state machine matches Figure state machine | Task 1 Step 3 |
| PaperSection `sequence` property | Task 2 Step 3 |
| PaperSection `depth` property | Task 2 Step 3 |
| Figure `caption` (required) | Task 2 Step 4 |
| Figure `figure_number` | Task 2 Step 4 |
| `contains_section`: PaperSection → PaperSection | Task 3 Step 3 |
| `appears_in`: Figure/Table → PaperSection | Task 3 Step 3 |
| `references_figure`: PaperSection → Figure | Task 3 Step 3 |
| `references_table`: PaperSection → Table | Task 3 Step 3 |
| `tabulates`: Table → Result | Task 3 Step 3 |
| `generated_by` updated to include Table | Task 3 Step 4 |
| Schema validation tests (12 tests) | Tasks 1–3 |
| Graph integration tests (7 tests) | Task 4 |

All requirements covered. No gaps.

### Placeholder scan

No TBD, TODO, or "similar to above" entries. All code blocks are complete.

### Type consistency

- `create_artifact(..., artifact_type="Table", ...)` — matches Table in domain config ✓
- `create_link(..., rel_type="contains_section", ...)` — matches new relationship ✓
- `get_dependents(session, result_id)` — `session` is a Neo4j session object (from `neo4j_driver.session(database=...).__enter__()`) ✓
- All Cypher queries use uppercase relationship names (CONTAINS_SECTION, APPEARS_IN, etc.) — correct, as `create_link` stores them uppercase ✓
