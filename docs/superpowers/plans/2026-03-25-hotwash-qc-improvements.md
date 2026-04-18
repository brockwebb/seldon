# Hotwash QC Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four targeted improvements to Seldon derived from the ai4stats hotwash: citation coverage check in `paper audit`, out-of-band edit detection in `paper sync`, bootstrap task list in `seldon init`, and citation health line in `seldon briefing`.

**Architecture:** All four changes are additive — no existing behavior changes. Citation coverage is a new `check_PQ_08` function in `qc.py` wired into `run_tier2`. OOB detection is a new field on `SyncResult` with display changes in the paper command. Init bootstrap creates ResearchTask artifacts via the existing `create_artifact` API. Citation health is a new graph query + one briefing output line.

**Tech Stack:** Python, Click, Neo4j (neo4j driver), pytest. All changes follow existing patterns in the codebase.

---

## File Map

| File | Change |
|------|--------|
| `seldon/paper/qc.py` | Add `check_PQ_08` (citation coverage), add to `run_tier2` |
| `templates/paper/paper_qc_config.yaml` | Add `min_cite_tokens: 1` to `prose_rules` |
| `seldon/paper/sync.py` | Add `suspected_oob: bool` to `SyncResult`, set in `sync_section` |
| `seldon/commands/paper.py` | Display `suspected_oob` prominently in `paper_sync` output |
| `seldon/commands/init.py` | Create 5 bootstrap `ResearchTask` artifacts after graph setup |
| `seldon/commands/session.py` | Add citation health query to `get_briefing_data`, print in `briefing_command` |
| `tests/test_paper_qc.py` | Tests for `check_PQ_08` |
| `tests/test_paper_sync.py` | Tests for `suspected_oob` detection |
| `tests/test_session_commands.py` | Test for citation health in briefing data |

---

## Task 1: Citation Coverage Check (PQ-08)

**Files:**
- Modify: `seldon/paper/qc.py`
- Modify: `templates/paper/paper_qc_config.yaml`
- Test: `tests/test_paper_qc.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_qc.py — add after existing SP tests

def _qc_with_cite_threshold(min_cite_tokens=1):
    cfg = _qc()
    cfg["prose_rules"]["min_cite_tokens"] = min_cite_tokens
    return cfg

class TestCheckPQ08:
    def test_no_cite_tokens_flags_violation(self):
        text = "This section makes several claims about methodology.\n\nAnother paragraph here."
        viols = check_PQ_08(text.splitlines(), _qc_with_cite_threshold(1), "test.md")
        assert len(viols) == 1
        assert viols[0].check_id == "PQ-08"
        assert "0 citation" in viols[0].message

    def test_with_cite_token_no_violation(self):
        text = "As shown by {{cite:smith2020:bibtex_key}}, the method works.\n\nMore text here."
        viols = check_PQ_08(text.splitlines(), _qc_with_cite_threshold(1), "test.md")
        assert viols == []

    def test_threshold_zero_never_flags(self):
        text = "This section has no citations at all."
        viols = check_PQ_08(text.splitlines(), _qc_with_cite_threshold(0), "test.md")
        assert viols == []

    def test_below_threshold_flags(self):
        text = "{{cite:a2020:key}} is one cite.\n\nMore text."
        viols = check_PQ_08(text.splitlines(), _qc_with_cite_threshold(2), "test.md")
        assert len(viols) == 1
        assert "1 citation" in viols[0].message

    def test_run_tier2_includes_pq08(self):
        text = "No citations here at all.\n\nJust plain prose with no formal references."
        cfg = _qc_with_cite_threshold(1)
        viols = run_tier2(text, cfg, "test.md")
        assert any(v.check_id == "PQ-08" for v in viols)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /Users/brock/Documents/GitHub/seldon
python -m pytest tests/test_paper_qc.py::TestCheckPQ08 -v 2>&1 | head -20
```
Expected: `ImportError` or `AttributeError` — `check_PQ_08` does not exist yet.

- [ ] **Step 3: Add `min_cite_tokens` to template config**

In `templates/paper/paper_qc_config.yaml`, add to `prose_rules`:
```yaml
  # Citation coverage
  min_cite_tokens: 1             # Min {{cite:...}} tokens per section; 0 disables
```

- [ ] **Step 4: Implement `check_PQ_08` in `seldon/paper/qc.py`**

Add the constant after the existing `_AMBIGUOUS_PRONOUN_RE`:
```python
_CITE_TOKEN_RE = re.compile(r'\{\{cite:[^:}]+:[^}]+\}\}')
```

Add the function before the public API section:
```python
def check_PQ_08(lines: List[str], config: dict, filename: str = "<string>") -> List[Violation]:
    """PQ-08: Flag sections with fewer {{cite:...}} tokens than the configured minimum."""
    threshold = config["prose_rules"].get("min_cite_tokens", 1)
    if threshold <= 0:
        return []
    text = "\n".join(lines)
    count = len(_CITE_TOKEN_RE.findall(text))
    if count < threshold:
        return [Violation(
            check_id="PQ-08",
            file=filename,
            line=1,
            message=f"Section has {count} citation token{'s' if count != 1 else ''} (min {threshold})",
            text=f"{{{{cite:...}}}} tokens found: {count}",
        )]
    return []
```

Add `check_PQ_08` to `run_tier2`:
```python
def run_tier2(text: str, qc_config: dict, filename: str = "<string>") -> List[Violation]:
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
        check_PQ_08,   # ← add here
    ):
        violations.extend(check_fn(lines, qc_config, filename))
    return violations
```

Also add `check_PQ_08` to the imports in `tests/test_paper_qc.py`.

- [ ] **Step 5: Run tests to confirm passing**

```bash
python -m pytest tests/test_paper_qc.py::TestCheckPQ08 -v
```
Expected: 5 tests pass.

- [ ] **Step 6: Run full QC test suite**

```bash
python -m pytest tests/test_paper_qc.py -v
```
Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add seldon/paper/qc.py templates/paper/paper_qc_config.yaml tests/test_paper_qc.py
git commit -m "feat: PQ-08 citation coverage check — flag sections with zero cite tokens"
```

---

## Task 2: Out-of-Band Edit Detection in `paper sync`

**Files:**
- Modify: `seldon/paper/sync.py`
- Modify: `seldon/commands/paper.py`
- Test: `tests/test_paper_sync.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_sync.py — add to unit tests section (no Neo4j needed)

class TestSuspectedOOB:
    """Out-of-band edit detection — unit tests using SyncResult directly."""

    def test_syncresult_has_suspected_oob_field(self):
        from seldon.paper.sync import SyncResult
        r = SyncResult(filename="test.md", status="updated")
        assert hasattr(r, "suspected_oob")
        assert r.suspected_oob is False

    def test_oob_false_by_default(self):
        from seldon.paper.sync import SyncResult
        r = SyncResult(filename="test.md", status="updated", suspected_oob=False)
        assert r.suspected_oob is False

    def test_oob_true_when_set(self):
        from seldon.paper.sync import SyncResult
        r = SyncResult(filename="test.md", status="updated", suspected_oob=True)
        assert r.suspected_oob is True
```

Add integration tests (Neo4j required) for the detection trigger:

```python
# Add inside the @needs_neo4j integration class

def test_oob_flag_set_when_review_section_changes_without_auto_stale(
    self, tmp_path, neo4j_driver, domain_config
):
    """Hash changes on review-state section without auto_stale → suspected_oob=True."""
    paper_dir = tmp_path / "paper"
    (paper_dir / "sections").mkdir(parents=True)
    section = _make_section(paper_dir, "ch01.md", "# Chapter 1\n\nOriginal text.\n")
    artifact_id = _create_paper_section(
        tmp_path, neo4j_driver, domain_config,
        name="ch01", title="Chapter 1",
        file_path=str(section),
        content_hash=compute_file_hash(section),
    )
    # Transition to review state
    from seldon.core.artifacts import transition_state
    transition_state(
        project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=artifact_id,
        artifact_type="PaperSection", current_state="proposed",
        new_state="review", actor="human", authority="accepted",
    )
    # Simulate out-of-band edit
    section.write_text("# Chapter 1\n\nEdited without going through CC task.\n")
    artifact = {"artifact_id": artifact_id, "state": "review",
                "content_hash": "old_hash_that_wont_match", "name": "ch01"}
    result = sync_section(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=tmp_path,
        domain_config=domain_config, section_path=section,
        artifact=artifact, dry_run=False, auto_stale=False,
    )
    assert result.suspected_oob is True

def test_oob_flag_not_set_when_auto_stale_true(
    self, tmp_path, neo4j_driver, domain_config
):
    """auto_stale=True means deliberate edit — no OOB flag."""
    paper_dir = tmp_path / "paper"
    (paper_dir / "sections").mkdir(parents=True)
    section = _make_section(paper_dir, "ch02.md", "# Chapter 2\n\nOriginal.\n")
    artifact_id = _create_paper_section(
        tmp_path, neo4j_driver, domain_config,
        name="ch02", title="Chapter 2",
        file_path=str(section),
        content_hash="stale_hash",
    )
    artifact = {"artifact_id": artifact_id, "state": "review",
                "content_hash": "stale_hash", "name": "ch02"}
    result = sync_section(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=tmp_path,
        domain_config=domain_config, section_path=section,
        artifact=artifact, dry_run=False, auto_stale=True,
    )
    assert result.suspected_oob is False
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/test_paper_sync.py::TestSuspectedOOB -v 2>&1 | head -20
```
Expected: `AttributeError` — `suspected_oob` field does not exist.

- [ ] **Step 3: Add `suspected_oob` to `SyncResult` in `seldon/paper/sync.py`**

```python
@dataclass
class SyncResult:
    filename: str
    status: str  # "unchanged" | "updated" | "untracked" | "registered"
    refs_added: list = field(default_factory=list)
    refs_removed: list = field(default_factory=list)
    state_changed: bool = False
    artifact_id: Optional[str] = None
    suspected_oob: bool = False   # ← add this field
```

In `sync_section`, after computing `state_changed_would`, set `suspected_oob`:

```python
    current_state = artifact.get("state", "proposed")
    state_changed_would = current_state in STALE_ON_EDIT and auto_stale
    suspected_oob = current_state in STALE_ON_EDIT and not auto_stale
```

Pass it through in the return statement:
```python
    return SyncResult(
        filename=filename,
        status="updated",
        refs_added=added_refs,
        refs_removed=removed_refs,
        state_changed=state_changed_would,
        artifact_id=artifact["artifact_id"],
        suspected_oob=suspected_oob,   # ← add
    )
```

- [ ] **Step 4: Update `paper_sync` output in `seldon/commands/paper.py`**

In the `elif r.status == "updated":` block, add OOB warning:
```python
        elif r.status == "updated":
            parts = []
            if r.refs_added:
                parts.append(f"{len(r.refs_added)} ref{'s' if len(r.refs_added) != 1 else ''} added")
            if r.refs_removed:
                parts.append(f"{len(r.refs_removed)} ref{'s' if len(r.refs_removed) != 1 else ''} removed")
            if r.state_changed:
                parts.append("→ stale")
            detail = f" ({', '.join(parts)})" if parts else ""
            prefix = "[dry-run] " if dry_run else ""
            click.echo(f"  {name_col} {prefix}UPDATED{detail}")
            if r.suspected_oob:
                click.echo(
                    f"  {'':>{col_width}} ⚠ SUSPECTED OUT-OF-BAND EDIT — section was in "
                    f"'{r.status}' state and changed without --auto-stale flag. "
                    "Was this edit tracked via a CC task?",
                    err=True,
                )
```

Wait — `r.status` here would be "updated", not the old state. Let me store the old state in `SyncResult` instead. Actually I should store the original state to display it properly in the warning. Let me add `prior_state: Optional[str] = None` to `SyncResult` too.

Revised `SyncResult`:
```python
@dataclass
class SyncResult:
    filename: str
    status: str
    refs_added: list = field(default_factory=list)
    refs_removed: list = field(default_factory=list)
    state_changed: bool = False
    artifact_id: Optional[str] = None
    suspected_oob: bool = False
    prior_state: Optional[str] = None   # ← add
```

In `sync_section`, set `prior_state=current_state` in the return:
```python
    return SyncResult(
        ...
        suspected_oob=suspected_oob,
        prior_state=current_state,
    )
```

In `paper.py` display:
```python
            if r.suspected_oob:
                click.echo(
                    f"  {'':>{col_width}} ⚠ SUSPECTED OUT-OF-BAND EDIT "
                    f"(was '{r.prior_state}') — was this tracked via a CC task?",
                    err=True,
                )
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_paper_sync.py::TestSuspectedOOB -v
```
Expected: unit tests pass; integration tests pass if Neo4j available.

- [ ] **Step 6: Run full sync test suite**

```bash
python -m pytest tests/test_paper_sync.py -v
```
Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add seldon/paper/sync.py seldon/commands/paper.py tests/test_paper_sync.py
git commit -m "feat: out-of-band edit detection in paper sync — warn when review/published section changes without --auto-stale"
```

---

## Task 3: Bootstrap Task List in `seldon init`

**Files:**
- Modify: `seldon/commands/init.py`
- Test: `tests/test_session_commands.py` (or new `tests/test_init.py`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_commands.py — add new test class

class TestInitBootstrapTasks:
    """Bootstrap ResearchTask creation during seldon init."""

    def test_bootstrap_tasks_created(self, tmp_path, neo4j_driver, domain_config):
        """After init, 5 ResearchTask artifacts should exist in the graph."""
        from seldon.commands.init import _create_bootstrap_tasks
        from seldon.core.graph import get_artifacts_by_type

        _create_bootstrap_tasks(
            project_dir=tmp_path,
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
        )

        with neo4j_driver.session(database=NEO4J_DB) as session:
            tasks = get_artifacts_by_type(session, "ResearchTask")

        assert len(tasks) == 5

    def test_bootstrap_task_descriptions_present(self, tmp_path, neo4j_driver, domain_config):
        from seldon.commands.init import _create_bootstrap_tasks
        from seldon.core.graph import get_artifacts_by_type

        _create_bootstrap_tasks(
            project_dir=tmp_path,
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
        )

        with neo4j_driver.session(database=NEO4J_DB) as session:
            tasks = get_artifacts_by_type(session, "ResearchTask")

        descriptions = [t.get("description", "") for t in tasks]
        assert any("citation" in d.lower() or ".bib" in d.lower() for d in descriptions)
        assert any("structure" in d.lower() or "section" in d.lower() for d in descriptions)
        assert any("pipeline" in d.lower() or "build" in d.lower() for d in descriptions)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/test_session_commands.py::TestInitBootstrapTasks -v 2>&1 | head -20
```
Expected: `ImportError` — `_create_bootstrap_tasks` does not exist.

- [ ] **Step 3: Implement `_create_bootstrap_tasks` in `seldon/commands/init.py`**

Add after the imports:

```python
_BOOTSTRAP_TASKS = [
    (
        "SETUP-01: Establish bibliography — create paper/references.bib and use "
        "{{cite:key:field}} tokens from chapter 1 onward. Every claim with a source "
        "gets a BibTeX entry in the same CC task. No exceptions."
    ),
    (
        "SETUP-02: Lock section structure before writing — define all PaperSection "
        "artifacts (outline level) and get them to accepted state before any section "
        "enters draft. Restructuring after 60% completion is expensive."
    ),
    (
        "SETUP-03: Validate build pipeline on 2-3 section prototype — test headings, "
        "tables, figures, code blocks, and page breaks on real content before scaling "
        "to all sections. Build the pipeline early, not after content is done."
    ),
    (
        "SETUP-04: Verify deploy workflow fires on first push — after initial deploy, "
        "confirm GitHub Actions triggers and smoke-test the output URL. Don't assume "
        "it works because the YAML looks right."
    ),
    (
        "SETUP-05: Decide tracked vs. gitignored build artifacts at project setup — "
        "if users need to download a file from the repo, it must be tracked. "
        "Document this decision in the project setup."
    ),
]
```

Add the helper function before `init_command`:

```python
def _create_bootstrap_tasks(project_dir, driver, database, domain_config):
    """Create standard project setup ResearchTask artifacts."""
    from seldon.core.artifacts import create_artifact
    for description in _BOOTSTRAP_TASKS:
        create_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_type="ResearchTask",
            properties={"description": description},
            actor="human",
            authority="accepted",
        )
```

In `init_command`, call it after the Neo4j setup succeeds (inside the `try` block, after `create_indexes`):

```python
        # Load domain config and create bootstrap tasks
        from seldon.domain.loader import load_domain_config
        domain_yaml = Path(__file__).parent.parent / "domain" / "research.yaml"
        domain_config = load_domain_config(domain_yaml)
        _create_bootstrap_tasks(project_dir, driver, database, domain_config)
        bootstrap_status = "5 setup tasks created."
```

Update the `neo4j_status` output:
```python
        neo4j_status = f"Neo4j database '{database}' created with indexes. {bootstrap_status}"
```

Handle the case where Neo4j fails (the `except` branch): bootstrap tasks can't be created without a DB, so just note it:
```python
    except Exception as e:
        neo4j_status = f"Warning: Neo4j setup failed: {e}"
```
(No change needed in the except branch — bootstrap tasks simply won't be created if DB init fails.)

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_session_commands.py::TestInitBootstrapTasks -v
```
Expected: both tests pass.

- [ ] **Step 5: Run full session test suite**

```bash
python -m pytest tests/test_session_commands.py -v
```
Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add seldon/commands/init.py tests/test_session_commands.py
git commit -m "feat: seldon init creates 5 bootstrap ResearchTask artifacts for project setup hygiene"
```

---

## Task 4: Citation Health in `seldon briefing`

**Files:**
- Modify: `seldon/commands/session.py`
- Test: `tests/test_session_commands.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_commands.py — add to existing briefing tests

class TestCitationHealthBriefing:

    def test_citation_health_in_briefing_data_no_sections(
        self, tmp_path, neo4j_driver, domain_config
    ):
        from seldon.commands.session import get_briefing_data
        data = get_briefing_data(neo4j_driver, NEO4J_DB, domain_config)
        assert "citation_health" in data
        ch = data["citation_health"]
        assert ch["total_sections"] == 0
        assert ch["cited_sections"] == 0

    def test_citation_health_counts_sections_with_cites(
        self, tmp_path, neo4j_driver, domain_config
    ):
        from seldon.commands.session import get_briefing_data
        from seldon.core.artifacts import create_artifact, create_link

        # Create two PaperSection artifacts
        s1_id = create_artifact(
            project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="PaperSection",
            properties={"name": "ch01", "title": "Chapter 1"},
            actor="human", authority="accepted",
        )
        s2_id = create_artifact(
            project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="PaperSection",
            properties={"name": "ch02", "title": "Chapter 2"},
            actor="human", authority="accepted",
        )
        # Create one Citation artifact
        c_id = create_artifact(
            project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="Citation",
            properties={"key": "smith2020", "title": "A Paper"},
            actor="human", authority="accepted",
        )
        # Link only ch01 to the citation
        create_link(
            project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config,
            from_id=s1_id, to_id=c_id,
            from_type="PaperSection", to_type="Citation",
            rel_type="cites", actor="human", authority="accepted",
        )

        data = get_briefing_data(neo4j_driver, NEO4J_DB, domain_config)
        ch = data["citation_health"]
        assert ch["total_sections"] == 2
        assert ch["cited_sections"] == 1
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/test_session_commands.py::TestCitationHealthBriefing -v 2>&1 | head -20
```
Expected: `KeyError: 'citation_health'`.

- [ ] **Step 3: Add citation health query to `get_briefing_data` in `session.py`**

Inside the `with driver.session(database=database) as session:` block, add after the graph stats query:

```python
        # 5. Citation health: PaperSection artifacts with ≥1 CITES edge to Citation
        total_sections = session.run(
            "MATCH (s:Artifact:PaperSection) RETURN count(s) AS n"
        ).single()["n"]
        cited_sections = session.run(
            "MATCH (s:Artifact:PaperSection)-[:CITES]->(:Artifact:Citation) "
            "RETURN count(DISTINCT s) AS n"
        ).single()["n"]
```

Add to the returned dict:
```python
    return {
        "open_tasks": open_tasks,
        "stale_artifacts": stale,
        "incomplete_provenance": no_script,
        "docs_health": docs_data,
        "graph_stats": stats,
        "citation_health": {           # ← add
            "total_sections": total_sections,
            "cited_sections": cited_sections,
        },
    }
```

- [ ] **Step 4: Add citation health line to `briefing_command` output**

After the documentation line and before the graph stats line, add:

```python
    citation_health = data["citation_health"]
    total_s = citation_health["total_sections"]
    cited_s = citation_health["cited_sections"]
    if total_s > 0:
        cite_pct = int(cited_s / total_s * 100)
        cite_icon = "✓" if cited_s == total_s else "⚠"
        click.echo(
            f"\nCITATIONS: {cited_s}/{total_s} sections have ≥1 cite edge ({cite_pct}%)"
            + (f"  {cite_icon} {total_s - cited_s} uncited" if cited_s < total_s else "  ✓ all cited")
        )
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_session_commands.py::TestCitationHealthBriefing -v
```
Expected: both tests pass.

- [ ] **Step 6: Run full session test suite**

```bash
python -m pytest tests/test_session_commands.py -v
```
Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add seldon/commands/session.py tests/test_session_commands.py
git commit -m "feat: citation health line in seldon briefing — N/M sections have cite edges"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
cd /Users/brock/Documents/GitHub/seldon
python -m pytest tests/ -v 2>&1 | tail -20
```
Expected: all tests pass (290+ including new ones).

- [ ] **Smoke test `paper audit`**

```bash
echo "# Test\n\nThis is a test section with no citations." > /tmp/test_section.md
seldon paper audit /tmp/test_section.md
```
Expected: PQ-08 violation reported.

- [ ] **Final commit message note**

Each task gets its own commit (as specified in task steps). No squashing needed.
