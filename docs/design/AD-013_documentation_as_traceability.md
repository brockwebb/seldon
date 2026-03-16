# AD-013: Documentation as Traceability

**Date:** 2026-03-15
**Status:** Design
**Depends on:** AD-002 (domain-agnostic core), AD-006 (Result registry), AD-009 (database-as-context)
**Context:** Seldon tracks artifacts but has no concept of artifact completeness beyond state machine transitions. A Script with 215 tests and zero docstrings, or a Result with no interpretation, are structurally indistinguishable from fully documented ones. Documentation is a property of artifact completeness, and completeness is Seldon's job.

---

## 1. Design Principle

**An undocumented artifact is an incomplete artifact.**

Documentation is not a post-hoc deliverable. It is a measurable property of each artifact in the graph, tracked the same way Seldon tracks state, provenance, and staleness. If Seldon can tell you "this Result has no GENERATED_BY link," it should also tell you "this Script has no description of its inputs."

**Corollary: Documentation is a projection, not a source.**

Hand-maintained docs/ directories are the docstring equivalent of flat-file registries — they drift. The graph is the source of truth. Documentation files are projections of graph properties, regenerated on demand, same pattern as `seldon paper build`.

---

## 2. Schema Extension: Property Schemas on Artifact Types

### 2.1 The Problem

`DomainConfig.artifact_types` is currently a flat `List[str]`. Seldon knows that "Script" is a valid type but knows nothing about what properties a Script should have. This means:

- No validation at creation time ("you created a Script with no `name`")
- No completeness checking ("this Script is missing `inputs`, `outputs`, `parameters`")
- No ability to distinguish operational properties (name, path, state) from documentation properties (description, usage, interpretation)

### 2.2 The Change

Extend `artifact_types` from a list of strings to a dict mapping type names to property schemas. Each property schema defines: name, whether it's required or documentation, a brief description, and an optional type hint.

**research.yaml — before:**

```yaml
artifact_types:
  - Script
  - Result
  - DataFile
  # ...
```

**research.yaml — after:**

```yaml
artifact_types:
  Script:
    properties:
      name:
        required: true
        description: "Human-readable script name"
      path:
        required: true
        description: "Filesystem path relative to project root"
      description:
        category: documentation
        description: "What this script does (1-2 sentences)"
      inputs:
        category: documentation
        description: "Input data files or parameters"
      outputs:
        category: documentation
        description: "What the script produces"
      parameters:
        category: documentation
        description: "Configurable parameters and their defaults"
      usage:
        category: documentation
        description: "How to run: command, arguments, environment"
      dependencies:
        category: documentation
        description: "Required packages, data files, other scripts"

  Result:
    properties:
      value:
        required: true
        description: "The numeric or categorical result value"
      units:
        required: true
        description: "Units of measurement"
      description:
        required: true
        description: "What this result measures"
      interpretation:
        category: documentation
        description: "What the value means in context"
      methodology_note:
        category: documentation
        description: "Brief note on how it was computed"

  DataFile:
    properties:
      name:
        required: true
        description: "Filename"
      path:
        required: true
        description: "Filesystem path relative to project root"
      format:
        category: documentation
        description: "File format (CSV, JSON, JSONL, etc.)"
      schema_description:
        category: documentation
        description: "Columns/fields and their meanings"
      provenance_description:
        category: documentation
        description: "How this data was produced or obtained"
      row_count:
        category: documentation
        description: "Number of records (approximate is fine)"

  Figure:
    properties:
      name:
        required: true
        description: "Figure identifier (e.g., fig_1_convergence)"
      description:
        required: true
        description: "What the figure shows"
      interpretation:
        category: documentation
        description: "Key takeaway from this figure"
      data_source:
        category: documentation
        description: "Which DataFiles/Results this figure renders"

  PipelineRun:
    properties:
      script_id:
        required: true
        description: "Artifact ID of the Script that was run"
      run_timestamp:
        required: true
        description: "When the run started"
      environment:
        category: documentation
        description: "Python version, OS, key package versions"
      runtime:
        category: documentation
        description: "Wall-clock time"
      reproduction_command:
        category: documentation
        description: "Exact command to reproduce this run"

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

  Citation:
    properties:
      key:
        required: true
        description: "BibTeX key"
      title:
        required: true
        description: "Paper/source title"

  ResearchTask:
    properties:
      description:
        required: true
        description: "What needs to be done"

  LabNotebookEntry:
    properties:
      summary:
        required: true
        description: "Session summary"

  SRS_Requirement:
    properties:
      requirement_id:
        required: true
        description: "Formal requirement identifier (e.g., FR-001)"
      description:
        required: true
        description: "What the requirement specifies"
```

### 2.3 Property Categories

Each property has one of two categories:

| Category | Meaning | Enforcement |
|----------|---------|-------------|
| `required` | Must be present at creation time | `seldon artifact create` rejects if missing |
| `documentation` | Should be present for completeness | `seldon docs check` reports if missing |

No `optional` category — if a property isn't worth tracking completeness for, it shouldn't be in the schema. Freeform properties can still be passed via `-p key=value`; the schema only governs what gets *checked*.

### 2.4 DomainConfig Model Change

```python
class PropertyDef(BaseModel):
    """Definition of a single property on an artifact type."""
    description: str
    required: bool = False
    category: str = "documentation"  # "documentation" or inferred from required

    @model_validator(mode="after")
    def set_category_from_required(self) -> "PropertyDef":
        if self.required:
            self.category = "required"
        return self

class ArtifactTypeConfig(BaseModel):
    """Schema for an artifact type including its property definitions."""
    properties: Dict[str, PropertyDef] = {}

class DomainConfig(BaseModel):
    domain: str
    version: str
    artifact_types: Dict[str, ArtifactTypeConfig]  # was List[str]
    relationship_types: Dict[str, RelationshipConfig]
    state_machines: Dict[str, Dict[str, List[str]]]
    # ... rest unchanged
```

### 2.5 Backward Compatibility

The `validate_artifact_type` function currently checks `if artifact_type not in domain_config.artifact_types`. Since `artifact_types` becomes a dict, this still works — `in` checks dict keys. The `get_initial_state` method indexes into `state_machines` by type name, also unchanged.

The only breaking change: any code that iterates `artifact_types` as a list needs to iterate `.keys()` instead. Grep for this and fix.

---

## 3. CLI Commands

### 3.1 `seldon docs check`

Scans all artifacts in the graph and reports documentation property completeness.

```
$ seldon docs check

DOCUMENTATION COMPLETENESS
══════════════════════════

Script (3 artifacts):
  ✗ entropy_leibniz_v3_minimal.py — missing: inputs, outputs, parameters, usage
  ✗ scaling_heatmap.py — missing: description, inputs, outputs
  ✓ fitness_sensitivity_test.py — complete

Result (12 artifacts):
  ✗ entropy_minimal_5_5 — missing: interpretation
  ✗ entropy_hostile_5_5 — missing: interpretation, methodology_note
  ... (8 more with gaps)
  ✓ gp_baseline_error — complete
  ✓ gp_baseline_generations — complete

DataFile (6 artifacts):
  ✗ minimal_data.json — missing: format, schema_description
  ... 

SUMMARY: 4/44 artifacts fully documented (9%)
  Required properties: 44/44 complete (100%)
  Documentation properties: 31/198 complete (16%)
```

**Flags:**
- `--type Script` — filter to one artifact type
- `--strict` — exit code 1 if any documentation gaps (for pre-commit hooks)
- `--threshold 80` — exit code 1 if below N% documentation completeness
- `--json` — machine-readable output

**Implementation:** Cypher query pulls all artifacts with their properties. For each, compare present properties against the schema's documentation properties for that type. Missing = gap.

### 3.2 `seldon docs generate`

Reads the graph. Projects documentation files into a `docs/` directory.

```
$ seldon docs generate

Generated:
  docs/experiment_catalog.md — 12 experiments from Script + Result artifacts
  docs/scripts_reference.md — 8 Scripts with documented properties
  docs/data_dictionary.md — 6 DataFiles with format/schema
  docs/results_registry.md — 12 Results with provenance chains
  docs/reproduction_guide.md — 3 PipelineRuns with reproduction commands
```

Each generated file includes a header: `<!-- Generated by seldon docs generate. Do not edit manually. -->`

**What each file contains:**

| File | Source | Content |
|------|--------|---------|
| `experiment_catalog.md` | Script + Result + GENERATED_BY edges | For each Script: what it does, what Results it generates, parameters |
| `scripts_reference.md` | Script artifacts | Name, path, description, inputs, outputs, parameters, usage, dependencies |
| `data_dictionary.md` | DataFile artifacts | Name, path, format, schema, provenance, row count |
| `results_registry.md` | Result + provenance chain | Value, units, description, interpretation, generating script, data source, SRS requirement |
| `reproduction_guide.md` | PipelineRun artifacts | Environment, command, runtime, linked Script and DataFile |

**Not generated:** `configuration_reference.md` from the handoff. Parameters are already part of `scripts_reference.md` per-script. A separate config file adds no information. Cut it.

### 3.3 `seldon docs populate` (Phase 2 — deferred)

Agent-assisted extraction from source code. Reads Python files, extracts function signatures, existing docstrings, and proposes graph property updates.

**Why deferred:** We don't yet know which documentation properties are actually worth tracking vs. ceremony. Run `docs check` on Seldon and leibniz-pi first. Let the gap report inform which properties matter. Then build tooling to fill them.

**When to build:** After dogfooding `docs check` + `docs generate` on at least one repo and confirming the schema is stable.

### 3.4 Briefing Integration

`seldon briefing` already shows open tasks, stale results, and incomplete provenance. Add a documentation health line:

```
DOCUMENTATION: 4/44 artifacts fully documented (9%)
  ⚠ 3 Scripts missing critical docs (inputs, outputs)
  ⚠ 10 Results missing interpretation
```

This is a summary, not the full `docs check` output. Keeps the briefing scannable. Run `seldon docs check` for details.

---

## 4. Enforcement Model

### 4.1 Phased Rollout

| Phase | Mode | Mechanism |
|-------|------|-----------|
| **Now** | Advisory | `seldon briefing` shows documentation health. `seldon docs check` reports gaps. No blocking. |
| **After schema stabilizes** | Soft gates | `seldon docs check --strict` returns non-zero. Usable in pre-commit hooks or CC task specs. |
| **After patterns proven** | Hard gates | Artifacts cannot transition to `verified` or `published` if required documentation properties are empty. State machine enforcement. |

### 4.2 Why Not Hard Gates Now

Hard gates require knowing which properties matter. The current schema is a best guess. Dogfooding will reveal:

- Which documentation properties are actually useful vs. noise
- Which properties are too granular (do we really need `dependencies` separate from `usage`?)
- Which properties are missing (maybe Scripts need `version` or `last_modified`)
- Whether the required/documentation split is right

Imposing hard gates on an unstable schema generates busywork and resistance. Advisory mode lets you build habits; soft gates let you enforce when ready; hard gates lock it in after validation.

### 4.3 CC Task Integration

Root CLAUDE.md Section 5 (or equivalent) should specify:

> Every public function gets a docstring (Args/Returns/Raises format). Every module gets a top-level docstring. Every new CLI command has useful `--help` text. When registering artifacts via `seldon artifact create`, include all required properties and as many documentation properties as reasonable.

This is a development standard, not Seldon enforcement. Seldon measures; the standard directs.

---

## 5. Staleness Propagation for Documentation

When a Script artifact transitions to `stale` (e.g., because the file was modified), its documentation properties are also potentially stale. Two options:

**Option A: No special handling.** Staleness already propagates via CITES edges to downstream Results, PaperSections, etc. Documentation is just another property — if the Script is stale, everything about it is suspect. No new mechanism needed.

**Option B: Documentation-specific staleness flag.** Add a `docs_stale: bool` property. Set to true when the source file changes. `seldon docs check` reports it separately.

**Recommendation: Option A.** Staleness already works. Adding a parallel staleness concept for documentation introduces complexity for no clear benefit. If a Script is stale, re-verify it, re-document it. Same workflow.

---

## 6. Relationship to TEVV (AD-012 Section 14)

Documentation completeness is a Verification metric. "Are we building the thing right?" includes "can someone understand and reproduce what we built?"

The `seldon docs check` output maps directly to TEVV's Verification phase:

| TEVV Activity | Seldon Mechanism |
|---------------|-----------------|
| Are artifacts traceable? | Provenance chain completeness (existing) |
| Are artifacts documented? | `seldon docs check` (this AD) |
| Are artifacts tested? | Test coverage (external — pytest, not Seldon's job) |
| Are artifacts reproducible? | PipelineRun with `reproduction_command` (this AD) |

The PL-011 PostToolUse hook pattern applies: after CC writes code, run `seldon docs check --strict` alongside `pytest`. Both must pass before commit.

---

## 7. Dogfood Plan

### 7.1 Target: Seldon Repo

17 source modules, 16 test files, 215 tests, zero docstrings. Known debt.

**Steps:**
1. Extend `DomainConfig` to support property schemas (code change to `domain/loader.py`)
2. Update `research.yaml` with property schemas per Section 2.2
3. Update `seldon artifact create` to validate required properties
4. Build `seldon docs check` command
5. Build `seldon docs generate` command
6. Initialize Seldon on itself (it already has `seldon.yaml`)
7. Run `seldon docs check` — establish baseline
8. Backfill documentation properties into the graph
9. Run `seldon docs generate` — produce docs/ directory
10. Iterate: adjust schema based on what feels useful vs. ceremony

### 7.2 Target: leibniz-pi (Second)

44 artifacts already in the graph. Different documentation character — experiment-level, not code-level.

**Steps:**
1. `seldon docs check` on leibniz-pi — baseline
2. Backfill experiment documentation (scripts, results, data files)
3. `seldon docs generate` — produce experiment catalog, data dictionary, results registry
4. Compare: does the schema work for research artifacts as well as infrastructure artifacts?

### 7.3 Success Criteria

AD-013 is successful when:
- `seldon docs check` produces actionable gap reports (not noise)
- `seldon docs generate` produces useful reference docs (not ceremony)
- The generated docs actually get consulted during sessions (measurable via `seldon briefing` usage)
- Schema has stabilized after 2 dogfood cycles (no more "add this property, remove that one")

---

## 8. Implementation Phases

### Phase 1: Schema Extension + Check (1 CC session)

- [ ] Extend `DomainConfig` model: `artifact_types` becomes `Dict[str, ArtifactTypeConfig]`
- [ ] Update `research.yaml` with property schemas
- [ ] Update `validate_artifact_type` and any code that iterates `artifact_types` as list
- [ ] Add required property validation to `create_artifact`
- [ ] Build `seldon docs check` command
- [ ] Wire into `seldon briefing` (summary line)
- [ ] Tests for all of the above

### Phase 2: Generate (1 CC session)

- [ ] Build `seldon docs generate` command
- [ ] Template system for each generated doc type
- [ ] Graph queries to pull artifact + relationship data
- [ ] Test with Seldon's own graph

### Phase 3: Dogfood + Iterate (desktop sessions)

- [ ] Run on Seldon repo, backfill properties
- [ ] Run on leibniz-pi, backfill properties
- [ ] Adjust schema based on experience
- [ ] Decide if soft gates are warranted

---

## 9. What This AD Does NOT Cover

- **Automated docstring extraction from source code** — deferred to `seldon docs populate` (Phase 2+, trigger: stable schema)
- **Test coverage integration** — pytest coverage is not Seldon's concern. Seldon tracks artifacts, not test metrics.
- **CI/CD enforcement via GitHub Actions** — Seldon is local-first. Pre-commit hooks and CC task specs are the enforcement mechanism, not CI pipelines.
- **Cross-project documentation** — that's Wintermute's problem, per AD-008.

---

## 10. Open Questions

1. **Property type hints:** Should the schema include type hints (`string`, `number`, `list`)? Useful for validation but adds schema complexity. Current recommendation: no. All properties are strings in Neo4j anyway. Type coercion happens at the CLI level, not the schema level.

2. **Property grouping in docs generate:** Should generated docs group by artifact type (current design) or by project structure (directory-based)? Type-based is graph-native and simpler. Directory-based requires filesystem awareness Seldon doesn't have.

3. **Freeform properties:** Properties not in the schema can still be set via `-p key=value`. Should `docs check` report them as "undocumented extras" or ignore them? Recommendation: ignore. Schema governs what's *expected*, not what's *permitted*.

---

*Documentation is traceability. Traceability is Seldon's job. This AD teaches Seldon that documentation is part of its job.*
