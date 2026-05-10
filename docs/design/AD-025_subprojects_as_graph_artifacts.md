# AD-025 — Subprojects as First-Class Graph Artifacts

**Status:** Proposed, 2026-04-21.
**Supersedes:** None.
**Related:** AD-017 (Central Validity Ontology — structural precedent for registry + extensions pattern), AD-022 (CLI-default), AD-018 (Document structure graph).

---

## Context

Seldon was designed around single-project repositories: one `seldon.yaml`, one Neo4j database, one domain-specific configuration. The `brock_projects` repository violates this implicit assumption — it is a staging area for multiple small projects (papers, presentations, position papers, code demos) that share infrastructure but differ in document type, conventions, and lifecycle.

As currently built, the `brock_projects/seldon.yaml` has calcified around the first active sub-project (SFV paper), with SFV-specific paths, citation conventions, bibliography location, and audit `document_type` pinned at the top level. The repo-level `CLAUDE.md` has similarly absorbed SFV-specific guidance. Adding a second sub-project — the NSF AI Day 2026 presentation — exposed the structural problem: there is no mechanism for sub-project-scoped configuration, and every additional sub-project on top of the current config deepens the tech debt.

Three forces constrain the fix:

1. **Graph-first philosophy.** The graph is already the source of truth for artifacts, tasks, results, and relationships. Sub-project metadata belongs in the graph, not in layered YAML. Per AD-017, the ontology pattern demonstrated that a registry-in-graph with explicit extension edges works well.

2. **Promotability.** If a sub-project grows unwieldy, it must be promotable to a standalone repository without architectural rework. This requires clean sub-graph isolation — no arbitrary cross-sub-project edges — and event-log scopability.

3. **Factory mindset.** Flat files that duplicate state the graph already knows are clutter. `seldon go`, task listings, handoff resolution, and session continuity should all route through the graph, not through directory walks or YAML parsing.

The calcification problem will only get worse. With exactly one active sub-project (SFV) and one proposed sub-project (NSF AI Day 2026), this is the cheapest moment to introduce the abstraction.

## Decision

**Sub-projects are first-class graph artifacts within a repo-scoped Seldon instance. The `seldon.yaml` is reduced to bootstrap-only configuration. All sub-project metadata — paths, conventions, document type, lifecycle state — lives in the graph as `Subproject` nodes. All non-ontology artifacts belong to exactly one sub-project or to the repo as a whole, via an explicit `BELONGS_TO` edge.**

### 1. `Subproject` artifact type

New artifact type registered in the research domain config. Properties:

- `artifact_id` (UUID)
- `slug` (unique within repo, matches directory name)
- `name` (display name)
- `document_type` (`academic_paper`, `book_chapter`, `policy_brief`, `presentation`, `position_paper`, etc. — drives audit gate selection per existing `GATE_PROFILES`)
- `paths` (map property: `paper`, `sections`, `book`, `slides`, `handout`, `assets`, etc. — sub-project-specific directory locations, relative to repo root)
- `conventions` (JSON string: citation style, bibliography path, glossary path, writing rules, prohibited tools, etc.)
- `state` (`active`, `dormant`, `retired` — matches existing vocabulary; see userMemory "projects are never retired, only dormant")
- `created_at`, `updated_at`
- `description` (optional prose)

### 2. `BELONGS_TO` edge

Every non-repo-wide artifact carries a `BELONGS_TO` edge to exactly one `Subproject` node:

```
(:ResearchTask)-[:BELONGS_TO]->(:Subproject)
(:PaperSection)-[:BELONGS_TO]->(:Subproject)
(:Result)-[:BELONGS_TO]->(:Subproject)
(:Issue)-[:BELONGS_TO]->(:Subproject)
(:DesignNote)-[:BELONGS_TO]->(:Subproject)
```

Artifacts with no `BELONGS_TO` edge are repo-scoped (ontology terms, repo-level ADs, migration events). This mirrors the ontology pattern where project-specific terms simply omit `references_ontology` when no canonical term exists.

### 3. Isolation invariant

**No direct edges between artifacts in different sub-projects.** Cross-sub-project relationships MUST route through:

- The central ontology (repo-wide, survives promotion), or
- An explicit repo-scoped `CrossReference` artifact that names both endpoints and is preserved if either side is promoted.

This invariant is what makes promotion to standalone repository tractable. Violations are caught by a new `seldon verify` check.

### 4. `seldon.yaml` reduced to bootstrap

After this AD, `seldon.yaml` contains only:

```yaml
event_store:
  path: seldon_events.jsonl
neo4j:
  database: seldon-<repo-slug>
  uri: bolt://localhost:7687
project:
  created_at: ...
  domain: research
  name: <repo-name>
  slug: <repo-slug>
shared_ontology:
  source: /Users/brock/Documents/GitHub/seldon/ontology/
  vocabularies: [...]
  inheritance: read-only
conventions:     # OPTIONAL: repo-wide defaults only
  prohibited_tools:
    - "github:create_or_update_file"
```

No `paths`, no `review`, no sub-project-specific conventions. The yaml is just enough to connect to the graph; the graph tells you everything else.

### 5. Directory structure

Sub-projects own their own `cc_tasks/`, `handoffs/`, `audits/`, and `CLAUDE.md`:

```
<repo>/
├── seldon.yaml           # bootstrap
├── CLAUDE.md             # repo-wide conventions only
├── seldon_events.jsonl
├── .seldon/              # session state
├── <subproject-a>/
│   ├── CLAUDE.md         # sub-project conventions
│   ├── cc_tasks/
│   ├── handoffs/
│   ├── audits/
│   └── <content-dirs>/
└── <subproject-b>/
    ├── CLAUDE.md
    ├── cc_tasks/
    ├── handoffs/
    └── <content-dirs>/
```

Flat top-level `cc_tasks/` and `handoffs/` at the repo root are eliminated. Migration moves existing files into their sub-project's directory.

### 6. Event scoping

Every event written after this AD lands carries a `subproject_slug` field (null for repo-scoped events). This enables event-log extraction on sub-project promotion via simple filter + replay.

### 7. `seldon go` resolution

- At repo root (cwd = repo): `seldon go` returns a **repo dashboard** — list of `Subproject` nodes, states, last-updated, open task counts, recent activity. A graph query, not a directory walk.
- Inside a sub-project directory (cwd = `<repo>/<subproject-slug>/`): `seldon go` auto-scopes to that sub-project — loads its CLAUDE.md, latest handoff from its `handoffs/`, open tasks filtered by `BELONGS_TO`, audit pipeline from its `document_type`.
- Explicit override: `seldon go --subproject <slug>` from anywhere.

### 8. CLI surface

New command group:

- `seldon subproject add <slug> --document-type <type> [--name <name>]` — create `Subproject` node, scaffold directory, create minimal `CLAUDE.md`
- `seldon subproject list` — show all sub-projects with state
- `seldon subproject show <slug>` — full detail
- `seldon subproject update <slug> --state <state>` — lifecycle transitions
- `seldon subproject promote <slug> --to <path>` — **DEFERRED**; documented here as known future feature, not built in v1

Existing commands gain scope awareness:
- `seldon task list`, `seldon task create`, `seldon issue *`, `seldon cc register`, `seldon cc complete` — detect sub-project from cwd or accept `--subproject` flag; auto-create `BELONGS_TO` edge.
- `seldon paper sync/build/audit`, `seldon verify` — read paths from the active `Subproject` node, not from `seldon.yaml`.

### 9. MCP surface

Per AD-022, MCP is exception, not default. Existing MCP tools (`seldon_go`, `seldon_task_create`, `seldon_cc_register`, `seldon_query`, `seldon_task_list`, `seldon_task_update`, `seldon_task_close`, `seldon_cc_complete`) gain optional `subproject` parameter. When omitted, the tool infers from cwd if possible, otherwise operates repo-wide or errors with a "specify subproject" message.

### 10. Migration

One-time migration for `brock_projects`:

1. Create `Subproject {slug: 'sfv-paper', ...}` node with properties from current `seldon.yaml`.
2. Create `Subproject {slug: 'nsf_aiday2026', document_type: 'presentation', ...}` node.
3. Backfill `BELONGS_TO` edges: match all existing Artifacts (ResearchTask, PaperSection, Result, Issue, DesignNote) whose `source_file` prefix or `name` indicates SFV, link to `sfv-paper`.
4. Move `brock_projects/cc_tasks/*` → `brock_projects/sfv-paper/cc_tasks/` (all existing tasks are SFV).
5. Move `brock_projects/handoffs/*` → `brock_projects/sfv-paper/handoffs/`.
6. Update `source_file` properties on migrated CC task artifacts to reflect new paths.
7. Strip SFV-specific config from `brock_projects/seldon.yaml` and `brock_projects/CLAUDE.md`.
8. Scaffold `nsf_aiday2026/CLAUDE.md`, `nsf_aiday2026/cc_tasks/`, `nsf_aiday2026/handoffs/`, `nsf_aiday2026/slides/`, `nsf_aiday2026/handout/`, `nsf_aiday2026/assets/`.
9. Move `nsf_aiday2026/HANDOFF_CC.md` → `nsf_aiday2026/handoffs/2026-04-19_initial_cc_handoff.md` and register.
10. Emit a `migration` event capturing the whole operation for provenance.

Ontology terms, repo-level ADs, and the migration event itself do NOT receive `BELONGS_TO` edges — they are repo-wide by design.

## Consequences

**Positive:**
- Multi-sub-project support without YAML sprawl or convention collisions.
- Sub-projects are promotable to standalone repos with clean sub-graph extraction.
- `seldon go` becomes a real dashboard at repo root; scoped orientation inside a sub-project directory.
- Flat-file clutter reduced — cc_tasks and handoffs co-locate with the work they describe.
- Graph-first philosophy extends to sub-project metadata. YAML is bootstrap only.
- New sub-projects created via single CLI command; no manual YAML editing.

**Negative / cost:**
- Seldon engine code changes across `config.py`, `commands/go.py`, `commands/task.py`, `commands/cc.py`, `commands/issue.py`, `commands/verify.py`, `commands/paper.py`, and `mcp_server.py`.
- One-time migration of existing SFV artifacts, cc_tasks, and handoffs.
- MCP tool signatures gain an optional parameter; callers that hardcode empty-string defaults may need updates.
- Single-sub-project repos (icsp_notebook, ai-workflow-design, etc.) either remain as-is (backward compat: no `Subproject` nodes → treat entire repo as implicit single sub-project) or migrate to the new pattern. **Recommendation: backward compat for now, migrate if value emerges.**

**Reversibility:** Medium. The graph schema addition is additive (new artifact type, new edge type) and non-destructive. Rolling back would require a reverse migration to repopulate `seldon.yaml` with sub-project-specific config, but the data to do so lives in the graph. The CLI and MCP signature changes are reversible with default values.

**90-day review:** 2026-07-21. Check: has a sub-project been promoted to a standalone repo? Have additional sub-projects been added to brock_projects without friction? Has the isolation invariant held, or have cross-sub-project edges crept in?

## Enforcement

- `seldon verify` gains a check: "no BELONGS_TO edges cross sub-project boundaries" (isolation invariant).
- `seldon verify` gains a check: "all non-ontology artifacts have exactly one BELONGS_TO edge OR are explicitly tagged repo-wide" (completeness).
- `seldon subproject add` is the only supported path for creating a sub-project; direct graph manipulation is discouraged and not documented.
- Quarterly: review `Subproject` nodes in `state:dormant` for promotion-to-standalone or retirement-to-archive.

## Relation to Prior ADs

- **AD-017 (Central Validity Ontology):** Structural precedent. Registry-in-graph + explicit extension edges is the same pattern applied to a different concern.
- **AD-022 (CLI-default, MCP-exception):** `seldon subproject` commands are CLI-native. MCP exposure only for the tools that already have MCP for reasoning-loop reasons.
- **AD-018 (Document structure graph):** Documents (PaperSections, Subsections) are graph artifacts. This AD extends that principle one level up — the containers documents live in are also graph artifacts.
- **AD-021 (Session continuity fidelity):** Graph-backed session state meshes naturally with sub-project scoping. A session is scoped to a sub-project (or repo-wide for dashboard work).

## Open Questions

- **Single-sub-project repos (icsp_notebook, ai-workflow-design, sfv-paper-if-promoted):** should they adopt this pattern for uniformity, or stay single-project? Deferred; backward compat preserves choice.
- **Cross-sub-project queries at repo level:** what's the user-facing dashboard view? v1 is a list; richer aggregation (e.g., "all open high-priority issues across sub-projects") is a future enhancement.
- **`seldon subproject promote` implementation:** non-trivial (sub-graph extraction, event filtering, ontology handling). Deferred until a real promotion is imminent.
- **Relationship to `review.intent` field (task 369fc223):** sub-project `document_type` and per-document `review.intent` coexist; the intent refines persona selection within a document type. No conflict.

---

*This AD formalizes sub-project support ahead of multi-project growth in brock_projects. Implementation tracked under Evolution Burst 2026-04-21.*
