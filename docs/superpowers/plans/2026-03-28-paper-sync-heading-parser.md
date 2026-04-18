# Paper Sync Heading Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `seldon paper sync` to parse `##` headings within section files, creating depth+1 PaperSection nodes linked via `contains_section`, with token-based edges (`cites`, `references_figure`, `references_table`) tracked at subsection granularity.

**Architecture:** Add `_parse_subsections()` as a pure function that reads a file and returns structured subsection data without touching the graph. A new `_sync_subsections()` function handles the create/update/deprecate lifecycle in the graph. `sync_section()` is extended to call both: if subsections are found, their edges replace parent-level cites edges; if none, existing behavior is unchanged (additive, not breaking).

**Tech Stack:** Python 3.11, Neo4j via `neo4j` driver, existing `seldon.core.artifacts` (create_artifact, create_link, remove_link, update_artifact), `REFERENCE_PATTERN` from `seldon.paper.build`, `XREF_PATTERN` from `seldon.paper.numbering`.

---

## File Structure

- **Modify:** `seldon/paper/sync.py` — add `_parse_subsections()`, `_get_subsection_edges()`, `_sync_subsections()`, extend `sync_section()`
- **Modify:** `tests/test_paper_sync.py` — add subsection tests (unit + integration)

No new files needed. All new logic belongs in `sync.py` alongside the existing sync functions.

---

## Task 1: `_parse_subsections()` — pure function, no Neo4j

**Files:**
- Modify: `seldon/paper/sync.py`
- Test: `tests/test_paper_sync.py`

Add `_parse_subsections` and the helper `_slugify_heading` immediately after `scan_references` in `sync.py`.

- [ ] **Step 1: Write failing unit tests for `_parse_subsections`**

Add to `tests/test_paper_sync.py`, in the unit tests section (before the `@needs_neo4j` integration tests):

```python
from seldon.paper.sync import _parse_subsections


def test_parse_subsections_empty_file(tmp_path):
    """File with no ## headings returns empty list."""
    f = tmp_path / "intro.md"
    f.write_text("# Introduction\n\nSome prose without subheadings.")
    result = _parse_subsections(f, "01_introduction", 0)
    assert result == []


def test_parse_subsections_single_heading(tmp_path):
    """Single ## heading produces one subsection."""
    f = tmp_path / "methods.md"
    f.write_text("# Methods\n\n## Experimental Setup\n\nSome content here.")
    result = _parse_subsections(f, "03_methods", 0)
    assert len(result) == 1
    sub = result[0]
    assert sub["name"] == "03_methods:experimental_setup"
    assert sub["title"] == "Experimental Setup"
    assert sub["sequence"] == 1
    assert sub["depth"] == 1
    assert isinstance(sub["content_hash"], str) and len(sub["content_hash"]) == 64


def test_parse_subsections_multiple_headings(tmp_path):
    """Multiple ## headings produce correctly sequenced subsections."""
    f = tmp_path / "results.md"
    f.write_text(
        "# Results\n\n"
        "## Discovery Rates\n\nContent A.\n\n"
        "## Wrong-Limit Attractors\n\nContent B.\n\n"
        "## Parsimony Effects\n\nContent C."
    )
    result = _parse_subsections(f, "05_results", 0)
    assert len(result) == 3
    assert result[0]["name"] == "05_results:discovery_rates"
    assert result[1]["name"] == "05_results:wrong_limit_attractors"
    assert result[2]["name"] == "05_results:parsimony_effects"
    assert [s["sequence"] for s in result] == [1, 2, 3]
    assert all(s["depth"] == 1 for s in result)


def test_parse_subsections_extracts_result_tokens(tmp_path):
    """Tokens in each subsection's range are attributed to that subsection."""
    f = tmp_path / "results.md"
    f.write_text(
        "# Results\n\n"
        "## Section A\n\nSee {{result:metric_a:value}} here.\n\n"
        "## Section B\n\nSee {{result:metric_b:value}} here."
    )
    result = _parse_subsections(f, "05_results", 0)
    assert result[0]["tokens"]["results"] == ["metric_a"]
    assert result[1]["tokens"]["results"] == ["metric_b"]


def test_parse_subsections_extracts_xref_tokens(tmp_path):
    """Figure and table tokens are attributed to the correct subsection."""
    f = tmp_path / "results.md"
    f.write_text(
        "# Results\n\n"
        "## Figures Section\n\nSee {{figure:fig2_plot}} and {{table:table_5}}.\n\n"
        "## Other\n\nPlain text."
    )
    result = _parse_subsections(f, "05_results", 0)
    assert result[0]["tokens"]["figures"] == ["fig2_plot"]
    assert result[0]["tokens"]["tables"] == ["table_5"]
    assert result[1]["tokens"]["figures"] == []
    assert result[1]["tokens"]["tables"] == []


def test_parse_subsections_content_hash_differs_per_section(tmp_path):
    """Each subsection has a content hash computed from its own text range."""
    f = tmp_path / "results.md"
    f.write_text(
        "# Results\n\n"
        "## Section A\n\nContent unique to A.\n\n"
        "## Section B\n\nContent unique to B."
    )
    result = _parse_subsections(f, "05_results", 0)
    assert result[0]["content_hash"] != result[1]["content_hash"]


def test_parse_subsections_slugify_special_chars(tmp_path):
    """Heading text with special characters is slugified correctly."""
    f = tmp_path / "methods.md"
    f.write_text("# Methods\n\n## GP-Based Search: Results & Analysis\n\nContent.")
    result = _parse_subsections(f, "03_methods", 0)
    assert result[0]["name"] == "03_methods:gp_based_search_results_analysis"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/brock/Documents/GitHub/seldon
source .venv/bin/activate 2>/dev/null || true
export NEO4J_PASSWORD="i'llbeback"
python -m pytest tests/test_paper_sync.py::test_parse_subsections_empty_file -v
```

Expected: `FAILED` with `ImportError: cannot import name '_parse_subsections'`

- [ ] **Step 3: Implement `_parse_subsections` in `sync.py`**

Add after the `scan_references` function (around line 74) and before `get_paper_section_artifacts`:

```python
import re

from seldon.paper.numbering import XREF_PATTERN


def _slugify_heading(text: str) -> str:
    """Convert a heading string to a lowercase underscore slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return slug.strip("_")


def _parse_subsections(file_path: Path, parent_name: str, parent_depth: int) -> list[dict]:
    """
    Parse ## headings from a section file into structured subsection dicts.

    Returns list of dicts with keys:
        name, title, sequence, depth, content_hash, tokens (results/figures/tables)

    Only ## headings are parsed. ### and deeper are ignored.
    Files with no ## headings return [].
    """
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Find line indices of all ## headings (not ### or deeper)
    heading_lines = []
    for i, line in enumerate(lines):
        if re.match(r"^## [^#]", line):
            heading_lines.append(i)

    if not heading_lines:
        return []

    subsections = []
    for seq, start_idx in enumerate(heading_lines, start=1):
        end_idx = heading_lines[seq] if seq < len(heading_lines) else len(lines)
        heading_text = lines[start_idx].lstrip("#").strip()
        body_lines = lines[start_idx:end_idx]
        body_text = "".join(body_lines)

        content_hash = hashlib.sha256(body_text.encode("utf-8")).hexdigest()

        # Extract result tokens (type:name from REFERENCE_PATTERN)
        result_names = []
        for m in REFERENCE_PATTERN.finditer(body_text):
            if m.group(1) in CITES_REF_TYPES:
                name = m.group(2)
                if name not in result_names:
                    result_names.append(name)

        # Extract figure and table tokens (XREF_PATTERN: {{figure:NAME}} etc.)
        figure_names = []
        table_names = []
        for m in XREF_PATTERN.finditer(body_text):
            token_type = m.group(1)
            name = m.group(2)
            if token_type == "figure" and name not in figure_names:
                figure_names.append(name)
            elif token_type == "table" and name not in table_names:
                table_names.append(name)

        subsections.append({
            "name": f"{parent_name}:{_slugify_heading(heading_text)}",
            "title": heading_text,
            "sequence": seq,
            "depth": parent_depth + 1,
            "content_hash": content_hash,
            "tokens": {
                "results": result_names,
                "figures": figure_names,
                "tables": table_names,
            },
        })

    return subsections
```

Note: The `import re` is likely already at the top or needs to be added. The `from seldon.paper.numbering import XREF_PATTERN` goes in the imports block at the top of the file.

- [ ] **Step 4: Run unit tests to verify they pass**

```bash
python -m pytest tests/test_paper_sync.py::test_parse_subsections_empty_file \
  tests/test_paper_sync.py::test_parse_subsections_single_heading \
  tests/test_paper_sync.py::test_parse_subsections_multiple_headings \
  tests/test_paper_sync.py::test_parse_subsections_extracts_result_tokens \
  tests/test_paper_sync.py::test_parse_subsections_extracts_xref_tokens \
  tests/test_paper_sync.py::test_parse_subsections_content_hash_differs_per_section \
  tests/test_paper_sync.py::test_parse_subsections_slugify_special_chars \
  -v
```

Expected: `7 passed`

- [ ] **Step 5: Run full suite to check for regressions**

```bash
python -m pytest tests/test_paper_sync.py -v 2>&1 | tail -15
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add seldon/paper/sync.py tests/test_paper_sync.py
git commit -m "feat: _parse_subsections() parses ## headings into structured subsection dicts"
```

---

## Task 2: `_sync_subsections()` — create and update subsection artifacts

**Files:**
- Modify: `seldon/paper/sync.py`
- Test: `tests/test_paper_sync.py`

This task handles the create/update path (not deprecation — that's Task 3).

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_paper_sync.py` after the existing integration tests:

```python
from seldon.paper.sync import _parse_subsections, _sync_subsections


@needs_neo4j
def test_sync_subsections_creates_nodes(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """_sync_subsections creates PaperSection nodes for each parsed subsection."""
    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\n## Experimental Setup\n\nContent A.\n\n## Data Collection\n\nContent B."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=compute_file_hash(path),
    )
    # Set depth=0 on parent (required for subsection depth calculation)
    from seldon.core.artifacts import update_artifact
    update_artifact(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                    artifact_id=parent_id, properties={"depth": 0}, actor="human", authority="accepted")

    parent_artifact = {"artifact_id": parent_id, "name": "03_methods",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}
    subsections = _parse_subsections(path, "03_methods", 0)

    _sync_subsections(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        parent_artifact=parent_artifact,
        subsections=subsections,
        dry_run=False,
        actor="human",
    )

    # Both subsection artifacts should exist in graph
    artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    assert "03_methods:experimental_setup" in artifacts
    assert "03_methods:data_collection" in artifacts

    # contains_section edges from parent to each subsection
    with neo4j_driver.session(database=NEO4J_DB) as session:
        rels = session.run(
            "MATCH (p:Artifact {artifact_id: $pid})-[:CONTAINS_SECTION]->(c:Artifact) "
            "RETURN c.name AS name ORDER BY c.sequence",
            pid=parent_id,
        ).data()
    names = [r["name"] for r in rels]
    assert names == ["03_methods:experimental_setup", "03_methods:data_collection"]


@needs_neo4j
def test_sync_subsections_unchanged_is_noop(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """Calling _sync_subsections twice with same content creates no duplicate artifacts."""
    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\n## Setup\n\nContent here."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=compute_file_hash(path),
    )
    parent_artifact = {"artifact_id": parent_id, "name": "03_methods",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}
    subsections = _parse_subsections(path, "03_methods", 0)

    # First sync
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=subsections, dry_run=False, actor="human")

    events_after_first = event_count(project_dir)

    # Second sync — nothing changed
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=subsections, dry_run=False, actor="human")

    # No new events
    assert event_count(project_dir) == events_after_first


@needs_neo4j
def test_sync_subsections_updated_content_changes_hash(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """When subsection text changes, its content_hash is updated in the graph."""
    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\n## Setup\n\nOriginal content."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=compute_file_hash(path),
    )
    parent_artifact = {"artifact_id": parent_id, "name": "03_methods",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}

    # First sync
    subsections_v1 = _parse_subsections(path, "03_methods", 0)
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=subsections_v1, dry_run=False, actor="human")
    old_hash = subsections_v1[0]["content_hash"]

    # Edit file — change subsection content
    path.write_text("# Methods\n\n## Setup\n\nEdited content.")
    subsections_v2 = _parse_subsections(path, "03_methods", 0)
    new_hash = subsections_v2[0]["content_hash"]
    assert old_hash != new_hash

    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=subsections_v2, dry_run=False, actor="human")

    artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    assert artifacts["03_methods:setup"]["content_hash"] == new_hash
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_paper_sync.py::test_sync_subsections_creates_nodes -v
```

Expected: `FAILED` with `ImportError: cannot import name '_sync_subsections'`

- [ ] **Step 3: Implement `_sync_subsections` in `sync.py`**

Add after `_parse_subsections` (before `get_paper_section_artifacts`):

```python
def _get_existing_subsections(driver: Driver, database: str, parent_id: str) -> dict:
    """
    Return existing subsection artifacts linked to parent via CONTAINS_SECTION.

    Returns dict keyed by subsection name → artifact dict.
    """
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (p:Artifact {artifact_id: $pid})-[:CONTAINS_SECTION]->(c:Artifact) "
            "RETURN c",
            pid=parent_id,
        ).data()
    return {dict(r["c"])["name"]: dict(r["c"]) for r in records}


def _sync_subsections(
    driver: Driver,
    database: str,
    project_dir: Path,
    domain_config: DomainConfig,
    parent_artifact: dict,
    subsections: list[dict],
    dry_run: bool = False,
    auto_stale: bool = False,
    actor: str = "human",
) -> None:
    """
    Create, update, or deprecate subsection PaperSection nodes based on parsed headings.

    - New subsections are created and linked via contains_section.
    - Existing unchanged subsections (same content_hash) are skipped.
    - Existing changed subsections have their content_hash updated.
    - Subsections present in graph but absent from file are marked deprecated.
    """
    parent_id = parent_artifact["artifact_id"]
    existing = _get_existing_subsections(driver, database, parent_id)
    parsed_names = {s["name"] for s in subsections}

    for sub in subsections:
        name = sub["name"]
        if name in existing:
            # Check if content changed
            stored_hash = existing[name].get("content_hash")
            if stored_hash == sub["content_hash"]:
                continue  # Unchanged — skip
            # Updated — write new hash
            if not dry_run:
                update_artifact(
                    project_dir=project_dir,
                    driver=driver,
                    database=database,
                    artifact_id=existing[name]["artifact_id"],
                    properties={"content_hash": sub["content_hash"]},
                    actor=actor,
                    authority="accepted",
                )
        else:
            # New subsection — create artifact and link
            if not dry_run:
                sub_id = create_artifact(
                    project_dir=project_dir,
                    driver=driver,
                    database=database,
                    domain_config=domain_config,
                    artifact_type="PaperSection",
                    properties={
                        "name": name,
                        "title": sub["title"],
                        "sequence": sub["sequence"],
                        "depth": sub["depth"],
                        "content_hash": sub["content_hash"],
                    },
                    actor=actor,
                    authority="accepted",
                )
                create_link(
                    project_dir=project_dir,
                    driver=driver,
                    database=database,
                    domain_config=domain_config,
                    from_id=parent_id,
                    to_id=sub_id,
                    from_type="PaperSection",
                    to_type="PaperSection",
                    rel_type="contains_section",
                    actor=actor,
                    authority="accepted",
                )

    # Deprecate subsections no longer in the file
    for name, artifact in existing.items():
        if name not in parsed_names and not artifact.get("deprecated"):
            if not dry_run:
                update_artifact(
                    project_dir=project_dir,
                    driver=driver,
                    database=database,
                    artifact_id=artifact["artifact_id"],
                    properties={"deprecated": True},
                    actor=actor,
                    authority="accepted",
                )
```

- [ ] **Step 4: Run the three integration tests**

```bash
export NEO4J_PASSWORD="i'llbeback"
python -m pytest tests/test_paper_sync.py::test_sync_subsections_creates_nodes \
  tests/test_paper_sync.py::test_sync_subsections_unchanged_is_noop \
  tests/test_paper_sync.py::test_sync_subsections_updated_content_changes_hash \
  -v
```

Expected: `3 passed`

- [ ] **Step 5: Run full sync test suite**

```bash
python -m pytest tests/test_paper_sync.py -v 2>&1 | tail -15
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add seldon/paper/sync.py tests/test_paper_sync.py
git commit -m "feat: _sync_subsections() creates/updates subsection PaperSection nodes"
```

---

## Task 3: Deprecation of removed headings

**Files:**
- Modify: `seldon/paper/sync.py` (deprecation already in `_sync_subsections` from Task 2 — add test coverage)
- Test: `tests/test_paper_sync.py`

- [ ] **Step 1: Write failing test for deprecation**

```python
@needs_neo4j
def test_sync_subsections_removed_heading_deprecated(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """A ## heading removed from a file marks its subsection artifact as deprecated."""
    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\n## Setup\n\nContent.\n\n## Teardown\n\nContent."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=compute_file_hash(path),
    )
    parent_artifact = {"artifact_id": parent_id, "name": "03_methods",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}

    # First sync — creates both subsections
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=_parse_subsections(path, "03_methods", 0),
                      dry_run=False, actor="human")

    # Remove "## Teardown" from file
    path.write_text("# Methods\n\n## Setup\n\nContent.")

    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=_parse_subsections(path, "03_methods", 0),
                      dry_run=False, actor="human")

    artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    # Setup still present
    assert "03_methods:setup" in artifacts
    # Teardown deprecated
    teardown = artifacts.get("03_methods:teardown")
    assert teardown is not None
    assert teardown.get("deprecated") is True


@needs_neo4j
def test_sync_subsections_deprecated_not_double_deprecated(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """A subsection already deprecated is not re-deprecated on subsequent syncs."""
    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\n## Setup\n\nContent.\n\n## Teardown\n\nContent."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=compute_file_hash(path),
    )
    parent_artifact = {"artifact_id": parent_id, "name": "03_methods",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}

    # First sync
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=_parse_subsections(path, "03_methods", 0),
                      dry_run=False, actor="human")

    # Remove Teardown
    path.write_text("# Methods\n\n## Setup\n\nContent.")
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=_parse_subsections(path, "03_methods", 0),
                      dry_run=False, actor="human")
    events_after_first_deprecation = event_count(project_dir)

    # Third sync — teardown still absent, should not produce new events
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=_parse_subsections(path, "03_methods", 0),
                      dry_run=False, actor="human")

    assert event_count(project_dir) == events_after_first_deprecation
```

- [ ] **Step 2: Run tests to confirm they pass (deprecation logic is already in `_sync_subsections` from Task 2)**

```bash
export NEO4J_PASSWORD="i'llbeback"
python -m pytest \
  tests/test_paper_sync.py::test_sync_subsections_removed_heading_deprecated \
  tests/test_paper_sync.py::test_sync_subsections_deprecated_not_double_deprecated \
  -v
```

Expected: `2 passed` (the deprecation code was written in Task 2's `_sync_subsections`)

If either fails, the fix needed is in `_get_existing_subsections` — it must return deprecated subsections too (so we know not to re-deprecate them). Confirm the query does not filter on `deprecated`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_paper_sync.py
git commit -m "test: subsection deprecation coverage for _sync_subsections"
```

---

## Task 4: Wire subsection sync into `sync_section()`

**Files:**
- Modify: `seldon/paper/sync.py`
- Test: `tests/test_paper_sync.py`

This is the integration step: when `sync_section()` processes a file, it now also syncs subsections. When subsections exist, parent-level `cites` edges are NOT updated (references tracked at subsection granularity instead).

- [ ] **Step 1: Write failing integration test**

```python
@needs_neo4j
def test_sync_section_creates_subsections_on_update(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """sync_section creates subsection nodes when ## headings are present."""
    content_v1 = "# Results\n\nIntro text."
    path = _make_section(paper_dir, "05_results.md", content_v1)
    old_hash = compute_file_hash(path)

    artifact_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="05_results", title="Results",
        file_path=path, content_hash=old_hash,
    )
    # Set depth=0 so subsection parser knows parent depth
    from seldon.core.artifacts import update_artifact
    update_artifact(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                    artifact_id=artifact_id, properties={"depth": 0}, actor="human", authority="accepted")

    # Edit file to add ## headings
    path.write_text(
        "# Results\n\n"
        "## Discovery Rates\n\nContent A.\n\n"
        "## Attractors\n\nContent B."
    )
    artifact = {"artifact_id": artifact_id, "name": "05_results",
                "content_hash": old_hash, "state": "draft", "depth": 0}

    result = sync_section(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
        domain_config=domain_config, section_path=path, artifact=artifact,
    )

    assert result.status == "updated"
    artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    assert "05_results:discovery_rates" in artifacts
    assert "05_results:attractors" in artifacts


@needs_neo4j
def test_sync_section_with_subsections_skips_parent_cites(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """When ## headings exist, result tokens in subsections do NOT create parent-level CITES edges."""
    path = _make_section(
        paper_dir, "05_results.md",
        "# Results\n\n## Section A\n\nSee {{result:metric_a:value}}."
    )
    old_hash = compute_file_hash(path)

    artifact_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="05_results", title="Results",
        file_path=path, content_hash="stale_hash",  # Force update
    )
    _create_result(project_dir, neo4j_driver, domain_config, "metric_a")

    artifact = {"artifact_id": artifact_id, "name": "05_results",
                "content_hash": "stale_hash", "state": "draft", "depth": 0}

    sync_section(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
        domain_config=domain_config, section_path=path, artifact=artifact,
    )

    # No CITES edge from the parent section
    with neo4j_driver.session(database=NEO4J_DB) as session:
        parent_cites = session.run(
            "MATCH (s:Artifact {artifact_id: $id})-[:CITES]->(t) RETURN t.name AS name",
            id=artifact_id,
        ).data()
    assert parent_cites == []

    # But the subsection DOES have a CITES edge (tested in Task 5)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
export NEO4J_PASSWORD="i'llbeback"
python -m pytest tests/test_paper_sync.py::test_sync_section_creates_subsections_on_update -v
```

Expected: `FAILED` — `sync_section` doesn't call `_sync_subsections` yet.

- [ ] **Step 3: Extend `sync_section()` to call `_sync_subsections`**

In `sync_section()`, after the hash-changed check determines it's an update, modify the logic:

Replace the existing block that calls `scan_references(text)` with:

```python
    # Hash changed — reconcile references and subsections
    text = section_path.read_text()

    # Determine parent depth (default 0 if not set)
    parent_depth = artifact.get("depth") or 0

    # Parse ## headings into subsection dicts
    subsections = _parse_subsections(section_path, artifact.get("name", section_path.stem), parent_depth)
    has_subsections = len(subsections) > 0

    if has_subsections:
        # References tracked at subsection level — skip parent-level cites reconciliation
        current_refs = set()
    else:
        # No subsections — track refs at parent level (existing behavior)
        current_refs = scan_references(text)

    existing_edges = _get_cites_edges(driver, database, artifact["artifact_id"])
    existing_ref_keys = set(existing_edges.keys())

    added_refs = sorted(current_refs - existing_ref_keys)
    removed_refs = sorted(existing_ref_keys - current_refs)

    current_state = artifact.get("state", "proposed")
    state_changed_would = current_state in STALE_ON_EDIT and auto_stale
    suspected_oob = current_state in STALE_ON_EDIT and not auto_stale

    if not dry_run:
        # ... existing cites edge creation/removal code (unchanged) ...
        # After updating hash and state, sync subsections:
        _sync_subsections(
            driver=driver,
            database=database,
            project_dir=project_dir,
            domain_config=domain_config,
            parent_artifact=artifact,
            subsections=subsections,
            dry_run=dry_run,
            auto_stale=auto_stale,
            actor=actor,
        )
```

The complete updated `sync_section` body (replace the entire function body after the `if artifact is None:` block with this):

```python
    current_hash = compute_file_hash(section_path)
    stored_hash = artifact.get("content_hash")

    if stored_hash == current_hash:
        return SyncResult(
            filename=filename,
            status="unchanged",
            artifact_id=artifact["artifact_id"],
        )

    # Hash changed — reconcile references and subsections
    text = section_path.read_text()
    parent_depth = artifact.get("depth") or 0
    subsections = _parse_subsections(
        section_path, artifact.get("name", section_path.stem), parent_depth
    )
    has_subsections = len(subsections) > 0

    # When subsections exist, references are tracked at subsection level
    current_refs = set() if has_subsections else scan_references(text)
    existing_edges = _get_cites_edges(driver, database, artifact["artifact_id"])
    existing_ref_keys = set(existing_edges.keys())

    added_refs = sorted(current_refs - existing_ref_keys)
    removed_refs = sorted(existing_ref_keys - current_refs)

    current_state = artifact.get("state", "proposed")
    state_changed_would = current_state in STALE_ON_EDIT and auto_stale
    suspected_oob = current_state in STALE_ON_EDIT and not auto_stale

    if not dry_run:
        for ref_key in added_refs:
            ref_type, ref_name = ref_key.split(":", 1)
            target = _find_artifact_by_name(driver, database, ref_name)
            if target is None:
                continue
            create_link(
                project_dir=project_dir,
                driver=driver,
                database=database,
                domain_config=domain_config,
                from_id=artifact["artifact_id"],
                to_id=target["artifact_id"],
                from_type="PaperSection",
                to_type=CITES_REF_TYPES[ref_type],
                rel_type="cites",
                actor=actor,
                authority="accepted",
            )

        for ref_key in removed_refs:
            target_id = existing_edges[ref_key]
            remove_link(
                project_dir=project_dir,
                driver=driver,
                database=database,
                from_id=artifact["artifact_id"],
                to_id=target_id,
                rel_type="cites",
                actor=actor,
                authority="accepted",
            )

        update_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            artifact_id=artifact["artifact_id"],
            properties={"content_hash": current_hash},
            actor=actor,
            authority="accepted",
        )

        if state_changed_would:
            transition_state(
                project_dir=project_dir,
                driver=driver,
                database=database,
                domain_config=domain_config,
                artifact_id=artifact["artifact_id"],
                artifact_type="PaperSection",
                current_state=current_state,
                new_state="stale",
                actor=actor,
                authority="accepted",
            )

        _sync_subsections(
            driver=driver,
            database=database,
            project_dir=project_dir,
            domain_config=domain_config,
            parent_artifact=artifact,
            subsections=subsections,
            dry_run=dry_run,
            auto_stale=auto_stale,
            actor=actor,
        )

    return SyncResult(
        filename=filename,
        status="updated",
        refs_added=added_refs,
        refs_removed=removed_refs,
        state_changed=state_changed_would,
        artifact_id=artifact["artifact_id"],
        suspected_oob=suspected_oob,
        prior_state=current_state,
    )
```

- [ ] **Step 4: Run new and existing tests**

```bash
export NEO4J_PASSWORD="i'llbeback"
python -m pytest tests/test_paper_sync.py -v 2>&1 | tail -20
```

Expected: all pass including the two new tests.

- [ ] **Step 5: Commit**

```bash
git add seldon/paper/sync.py tests/test_paper_sync.py
git commit -m "feat: sync_section() calls _sync_subsections() when ## headings present"
```

---

## Task 5: Token edges from subsections (cites, references_figure, references_table)

**Files:**
- Modify: `seldon/paper/sync.py` — extend `_sync_subsections()` to create token edges
- Test: `tests/test_paper_sync.py`

- [ ] **Step 1: Write failing test**

```python
@needs_neo4j
def test_sync_subsections_creates_cites_edges(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """Subsection with {{result:NAME:field}} gets a CITES edge to that Result."""
    path = _make_section(
        paper_dir, "05_results.md",
        "# Results\n\n## Discovery Rates\n\nSee {{result:metric_a:value}}."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="05_results", title="Results",
        file_path=path, content_hash=compute_file_hash(path),
    )
    result_id = _create_result(project_dir, neo4j_driver, domain_config, "metric_a")
    parent_artifact = {"artifact_id": parent_id, "name": "05_results",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}

    _sync_subsections(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
        domain_config=domain_config, parent_artifact=parent_artifact,
        subsections=_parse_subsections(path, "05_results", 0),
        dry_run=False, actor="human",
    )

    subsection_artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    sub_id = subsection_artifacts["05_results:discovery_rates"]["artifact_id"]

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (s:Artifact {artifact_id: $sid})-[:CITES]->(t:Artifact {artifact_id: $tid}) RETURN r",
            sid=sub_id, tid=result_id,
        ).single()
    assert rel is not None


@needs_neo4j
def test_sync_subsections_creates_references_figure_edge(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """Subsection with {{figure:NAME}} gets a REFERENCES_FIGURE edge to that Figure."""
    from seldon.core.artifacts import create_artifact as _create_artifact

    path = _make_section(
        paper_dir, "05_results.md",
        "# Results\n\n## Figures\n\nSee {{figure:fig2_plot}}."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="05_results", title="Results",
        file_path=path, content_hash=compute_file_hash(path),
    )
    fig_id = _create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Figure",
        properties={"name": "fig2_plot", "caption": "Test figure", "description": "A test fig"},
        actor="human", authority="accepted",
    )
    parent_artifact = {"artifact_id": parent_id, "name": "05_results",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}

    _sync_subsections(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
        domain_config=domain_config, parent_artifact=parent_artifact,
        subsections=_parse_subsections(path, "05_results", 0),
        dry_run=False, actor="human",
    )

    subsection_artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    sub_id = subsection_artifacts["05_results:figures"]["artifact_id"]

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (s:Artifact {artifact_id: $sid})-[:REFERENCES_FIGURE]->(t:Artifact {artifact_id: $tid}) RETURN t",
            sid=sub_id, tid=fig_id,
        ).single()
    assert rel is not None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
export NEO4J_PASSWORD="i'llbeback"
python -m pytest tests/test_paper_sync.py::test_sync_subsections_creates_cites_edges -v
```

Expected: `FAILED` — no CITES edges from subsections yet.

- [ ] **Step 3: Extend `_sync_subsections()` to create token edges after creating a new subsection**

In the `else:` branch of `_sync_subsections` (where new subsections are created), after creating the `contains_section` link, add:

```python
                # Create token-based edges from the subsection
                for ref_name in sub["tokens"]["results"]:
                    target = _find_artifact_by_name(driver, database, ref_name)
                    if target is not None:
                        create_link(
                            project_dir=project_dir, driver=driver, database=database,
                            domain_config=domain_config,
                            from_id=sub_id, to_id=target["artifact_id"],
                            from_type="PaperSection", to_type="Result",
                            rel_type="cites", actor=actor, authority="accepted",
                        )
                for fig_name in sub["tokens"]["figures"]:
                    target = _find_artifact_by_name(driver, database, fig_name)
                    if target is not None:
                        create_link(
                            project_dir=project_dir, driver=driver, database=database,
                            domain_config=domain_config,
                            from_id=sub_id, to_id=target["artifact_id"],
                            from_type="PaperSection", to_type="Figure",
                            rel_type="references_figure", actor=actor, authority="accepted",
                        )
                for tbl_name in sub["tokens"]["tables"]:
                    target = _find_artifact_by_name(driver, database, tbl_name)
                    if target is not None:
                        create_link(
                            project_dir=project_dir, driver=driver, database=database,
                            domain_config=domain_config,
                            from_id=sub_id, to_id=target["artifact_id"],
                            from_type="PaperSection", to_type="Table",
                            rel_type="references_table", actor=actor, authority="accepted",
                        )
```

Also add similar reconciliation for the update path (when hash changed): compute added/removed token refs and create/remove edges accordingly, mirroring the pattern in `sync_section()`.

For the update path, add after updating the content_hash:

```python
            # Reconcile cites edges for updated subsection
            existing_sub_cites = _get_cites_edges(driver, database, existing[name]["artifact_id"])
            new_result_refs = {f"result:{r}" for r in sub["tokens"]["results"]}
            for ref_key in sorted(new_result_refs - set(existing_sub_cites.keys())):
                _, ref_name = ref_key.split(":", 1)
                target = _find_artifact_by_name(driver, database, ref_name)
                if target is not None:
                    create_link(
                        project_dir=project_dir, driver=driver, database=database,
                        domain_config=domain_config,
                        from_id=existing[name]["artifact_id"], to_id=target["artifact_id"],
                        from_type="PaperSection", to_type="Result",
                        rel_type="cites", actor=actor, authority="accepted",
                    )
            for ref_key in sorted(set(existing_sub_cites.keys()) - new_result_refs):
                remove_link(
                    project_dir=project_dir, driver=driver, database=database,
                    from_id=existing[name]["artifact_id"],
                    to_id=existing_sub_cites[ref_key],
                    rel_type="cites", actor=actor, authority="accepted",
                )
```

- [ ] **Step 4: Run all token-edge tests**

```bash
export NEO4J_PASSWORD="i'llbeback"
python -m pytest \
  tests/test_paper_sync.py::test_sync_subsections_creates_cites_edges \
  tests/test_paper_sync.py::test_sync_subsections_creates_references_figure_edge \
  -v
```

Expected: `2 passed`

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/test_paper_sync.py -v 2>&1 | tail -15
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add seldon/paper/sync.py tests/test_paper_sync.py
git commit -m "feat: subsections create cites/references_figure/references_table edges from tokens"
```

---

## Task 6: End-to-end test + full suite verification

**Files:**
- Test: `tests/test_paper_sync.py`

- [ ] **Step 1: Write end-to-end test**

```python
@needs_neo4j
def test_sync_all_with_subsections_full_lifecycle(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """
    Full lifecycle: file with ## headings is synced via sync_all.
    First sync creates subsections. Second sync (unchanged) is a no-op.
    Third sync (content edited) updates subsection hash.
    """
    path = _make_section(
        paper_dir, "05_results.md",
        "# Results\n\n## Discovery Rates\n\nOriginal A.\n\n## Attractors\n\nOriginal B."
    )
    section_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="05_results", title="Results",
        file_path=path, content_hash="stale_so_first_sync_triggers",
    )
    from seldon.core.artifacts import update_artifact
    update_artifact(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                    artifact_id=section_id, properties={"depth": 0}, actor="human", authority="accepted")

    # First sync — triggers update, creates subsections
    results = sync_all(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
        domain_config=domain_config, paper_dir=paper_dir,
    )
    assert results[0].status == "updated"

    artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    assert "05_results:discovery_rates" in artifacts
    assert "05_results:attractors" in artifacts

    # Second sync — hash now matches, nothing changes
    results2 = sync_all(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
        domain_config=domain_config, paper_dir=paper_dir,
    )
    assert results2[0].status == "unchanged"

    events_before_edit = event_count(project_dir)

    # Edit first subsection content
    path.write_text(
        "# Results\n\n## Discovery Rates\n\nEdited content.\n\n## Attractors\n\nOriginal B."
    )
    results3 = sync_all(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
        domain_config=domain_config, paper_dir=paper_dir,
    )
    assert results3[0].status == "updated"
    # New events were written (hash update for parent + subsection)
    assert event_count(project_dir) > events_before_edit
```

- [ ] **Step 2: Run the end-to-end test**

```bash
export NEO4J_PASSWORD="i'llbeback"
python -m pytest tests/test_paper_sync.py::test_sync_all_with_subsections_full_lifecycle -v
```

Expected: `1 passed`

- [ ] **Step 3: Run complete test suite**

```bash
python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: all 394+ tests pass, 0 failures.

- [ ] **Step 4: Final commit**

```bash
git add seldon/paper/sync.py tests/test_paper_sync.py
git commit -m "test: end-to-end subsection sync lifecycle coverage"
git push
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Parse `##` headings | Task 1 (`_parse_subsections`) |
| Create PaperSection nodes at depth = parent + 1 | Task 2 (`_sync_subsections` create path) |
| Link subsections to parent via `contains_section` | Task 2 |
| Subsection sequence = order of appearance | Task 1 (sequence field) |
| Name = `parent:slug` format | Task 1 (_slugify_heading) |
| Track tokens within subsection range | Task 1 (tokens dict) |
| Create `cites` edges from subsections to Results | Task 5 |
| Create `references_figure` edges | Task 5 |
| Create `references_table` edges | Task 5 |
| Idempotency: second sync with no changes = no-op | Task 2 (unchanged path) + Task 6 |
| Heading removed → subsection deprecated | Task 3 |
| No `###` parsing | Task 1 (regex `^## [^#]`) |
| Files without `##` = unchanged behavior | Task 4 (has_subsections guard) |
| Parent-level edges skipped when subsections exist | Task 4 |

All spec requirements covered. No placeholders.
