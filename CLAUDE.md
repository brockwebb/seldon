# Seldon — Research Operating System

The queen of the colony. Persistent graph intelligence that decomposes research work, provides agents with precisely-scoped context slices, validates what comes back, and maintains collective state.

**The graph is the mind. The agents are the hands.**

See `README.md` for full vision and architectural properties.

## Current State

Working engine: Neo4j graph + JSONL event store + CLI. 341 tests passing. Domain config with property schemas (AD-013). Paper assembly pipeline (AD-012). Documentation-as-traceability infrastructure. `seldon go` MCP server for Desktop orientation with project management MCP tools (AD-021). Agent role + workflow definitions in graph (AD-014). Paper sync for iterative editing workflow. Paper foundations workflow (glossary, keyword index, evidence map). Shared ontology with master/replica inheritance (AD-017): `seldon-ontology` master DB with 51 terms, epoch-based sync to project replicas.

## Environment

**Neo4j credentials are in `.env`.** CC: you have the password. Load it with `dotenv` or read `.env` directly. Do NOT skip Neo4j-dependent tests. Do NOT ask for the password. Run the suite via python-dotenv: `python -m dotenv -f .env run -- python -m pytest tests/ -v`. Do NOT use `source .env && pytest` — line 4 of `.env` does not `source` cleanly in zsh, so that form silently skips every DB test (recorded in `cc_tasks/2026-09-02_snapshot_artifacts_verify_RESULT.md`). Passing `NEO4J_PASSWORD` explicitly also works.

**Database:** Each project gets its own Neo4j database. Seldon self-dogfood uses `seldon-seldon-self`. Leibniz-pi uses its own database per `seldon.yaml`. Shared ontology uses `seldon-ontology` (master — never modified by project-level commands).

**Python:** Seldon is pip-installed in the active environment. `seldon` CLI is available on PATH.

**MCP default project:** Set `SELDON_DEFAULT_PROJECT=/path/to/project` in the `seldon-mcp` env block in `claude_desktop_config.json`. When `seldon_go` is called without `project_dir`, it falls back to this path if it contains `seldon.yaml`.

## Skills

| Skill | When | Invoke |
|-------|------|--------|
| `briefing` | Session start | `/briefing` or `seldon briefing` |
| `closeout` | Session end | `/closeout` or `seldon closeout` |
| `handoff` | Desktop session end | `seldon handoff --slug <s> --summary <s> --next <s>` |
| `result-register` | Computation produces a citable result | `/result-register` |
| `task-track` | Work item must survive across sessions | `/task-track` |
| `research` | Writing lab notebook entries, lit notes, citations | `/research` |
| `paper audit`  | After writing/editing prose | `seldon paper audit paper/sections/*.md` |
| `paper sync`   | **After any edit to section files** | `seldon paper sync` |
| `paper register` | Register section files as graph artifacts | `seldon paper register --all` |
| `paper build`  | Assembling manuscript       | `seldon paper build` |
| `docs check`   | Verify documentation completeness | `seldon docs check` |
| `docs generate`| Project docs from graph     | `seldon docs generate` |
| `go`           | Orient any Claude instance   | `seldon go` |
| `ontology ingest` | After updating VALIDITY_VOCABULARY.md | `seldon ontology ingest` (writes to master) |
| `ontology sync`   | Pull latest vocabulary into project | `seldon ontology sync` (reads from master) |
| `ontology list`   | Check inherited terms | `seldon ontology list [--master]` |
| `verify`          | Before committing, or after any edit session | `seldon verify [--fix]` |
| `governed sync`   | After editing any docs/design, docs/requirements, cc_tasks or handoffs file | `seldon governed sync` |
| `governed search` | Find a ruling or a section by its words | `seldon governed search <terms>` |
| `governed status` | What the graph holds vs. what the ledger says | `seldon governed status` |
| `paper impact`    | Check blast radius of a change | `seldon paper impact <n>` |
| `paper context`   | Structured context for drafting/revision | `seldon paper context <section-name> [--format yaml\|text]` |
| `task precede`    | One task must finish before another starts | `seldon task precede <A> <B> [--reason ...]` |
| `task chain`      | Order a whole sequence of tasks | `seldon task chain <A> <B> <C> ...` |
| `task unprecede`  | Retire an ordering that no longer holds | `seldon task unprecede <A> <B>` |
| `cc complete`     | After executing a CC task | `seldon cc complete <task-filepath>` |
| `cc register`     | When writing a new CC task | `seldon cc register <task-filepath>` |

## MCP Tools (Desktop Housekeeping)

Desktop sessions (Claude Desktop, claude.ai threads) can do graph housekeeping via MCP without writing CC tasks. All tools are project-scoped via `project_dir` — they resolve the database from `seldon.yaml`, bypassing the neo4j-mcp single-database limitation.

| Tool | Use |
|------|-----|
| `seldon_go` | Orient to project |
| `seldon_task_create` | Create a ResearchTask |
| `seldon_task_update` | Single state transition |
| `seldon_task_close` | Walk any task to `completed` in one call |
| `seldon_task_list` | List tasks by state filter (marks ready tasks) |
| `seldon_task_precede` | Order one task before another |
| `seldon_task_chain` | Order a whole sequence of tasks in one call |
| `seldon_task_unprecede` | Remove a `precedes` edge |
| `seldon_issue_create` | Create Issue (Eisenhower 3×3) |
| `seldon_issue_update` | Update Issue state/priority |
| `seldon_cc_complete` | Mark CC task file as completed |
| `seldon_cc_register` | Register CC task file as proposed |
| `seldon_handoff` | Close the session: write the handoff, return the resume and CC dispatch blocks |
| `seldon_cc_register` | ...also returns the Rulings the task is constrained by, and refuses a task citing no AD/DN (AD-030-R9) |
| `seldon_query` | Read-only Cypher against project graph |

`seldon_query` is read-only — write operations (CREATE, MERGE, SET, DELETE, REMOVE) are rejected. Use the typed tools for mutations.

## Session Protocol

1. **Start**: `seldon go` or `/briefing` — orient to project, read handoff, surface open tasks
2. **Work**: `/result-register` for quantitative output, `/task-track` for cross-session items
   **CC task contracts:** Complex CC tasks (3+ deliverables, schema + code changes, new test files, or tasks where the spec says "check whether X exists and handle accordingly") should include a `## Success Contract` section in the task file or produce a separate `cc_tasks/<date>_<name>_contract.md` before execution begins. The contract lists deliverables, verification commands with expected results, scope boundaries, and assumptions. Simple tasks (single-function fixes, doc updates, file registration) do not need contracts. Template: `docs/templates/cc_task_contract.md`.
3. **After each CC task**: `seldon cc complete <task-filepath>` — records completion in graph so `seldon go` can reconcile stale handoff references
4. **End**: `/closeout` — structured handoff, then **run `seldon verify`**, then commit

**Desktop sessions close with `seldon handoff` (AD-030-R9).** The command derives the session
window from the newest LabNotebookEntry or handoff file, generates the handoff document from the
event log, the graph and the filesystem, and returns two blocks: the resume line for the next
Desktop thread and the CC dispatch text for the CC tasks it registered. It **refuses** to close a
Desktop session that created ResearchTasks and wrote no file under `docs/design/` — a design
session that ships tasks without a ruling leaves the decision addressable nowhere. Window length
and the gate live in `seldon.yaml` under `handoff.session_window_hours` and
`handoff.require_design_note`. `seldon go` reports, at the next orient, a previous Desktop session
that closed in violation.

**Multi-task plans belong in the graph too (AD-029).** `seldon task chain A B C` records the
order; `seldon go` then renders **Next ready** and **Chains**, and `seldon task list` marks ready
tasks with `▸`. Ordering carried as prose in each task's description drifts — that is the defect
this replaced. The `precedes` subgraph must stay acyclic and is advisory: starting a task ahead of
its predecessor warns and proceeds.

Long-lived tasks belong in the graph as ResearchTask or Issue artifacts, not as prose in CLAUDE.md or handoff files. Desktop sessions can create tasks and issues via MCP tools (`seldon_task_create`, `seldon_issue_create`). If a task must survive across sessions, create a graph artifact.

## Governed Documents (AD-030)

**Every markdown file under `docs/design/`, `docs/requirements/`, `cc_tasks/` and `handoffs/` is a
Document node in the graph.** The file is the serialization; parsing it is the single write path.
Its sections, its rulings (deontic text: `AD-NNN-Rn`, BINDING, MUST, never), its citations and its
quoted passages are child nodes with stable ids and verbatim spans.

**The loop is: edit → ingest → sync.**

```bash
make -C governed catalog        # enumerate new governed files into the manifest
make -C governed sweep          # parse, extract, append to governed/ledger/events.jsonl
seldon governed sync            # import that ledger into seldon-seldon-self
```

`seldon verify --fix` runs `governed sync` for you; `seldon verify --strict` fails on an unsynced
governed document, which is what puts ingest on the commit rather than on a cron (AD-030-R3).

**What this buys, concretely.** `seldon cc register` now returns the rulings a new task is
constrained by — found by identifier when the task names one, and by concept overlap when it does
not — and writes a `constrained_by` edge for each. That is the mechanism whose absence let a
retired per-set RPE field be reintroduced on 2026-09-01. It also **refuses** a CC task that
references no `AD-` or `DN-` identifier (AD-030-R9); set `handoff.require_design_note: false` to
downgrade that to a warning.

**Two ledgers, one write path each.** Squiddy's DI-005 guard refuses any `seldon-*` projection
target, and rightly. So `governed/` is a Squiddy graph inside this repo with its own ledger and no
Neo4j backend; Seldon imports that ledger through its own event store. `seldon/core/governed.py`
imports nothing from Squiddy — the coupling is a file format, not an awareness (AD-030-R10).

**Config:** `governed.graph_dir`, `governed.ruling_match_threshold` in `seldon.yaml`.
Extraction rules — what counts as a ruling, an identifier, a CiTO marker — live in
`governed/config.yaml` under `domain:`, never in code, and every node records which rule produced
it.

## Paper Editing Workflow

**The loop is: edit → sync → build.** This is mandatory, not optional.

After ANY edit to `paper/sections/*.md` — whether manual prose edits, CC tasks that rename result references, or anything that changes section file content:

```bash
python paper/check_glossary.py       # check terms + regenerate keyword index
seldon paper sync                    # reconcile graph with disk (hashes, edges, state)
seldon paper build --no-render       # verify references still resolve
```

For CC tasks, append `seldon verify --strict` to the cycle. If it exits non-zero, fix Tier A violations before state transition or commit.

`paper sync` computes content hashes, updates `cites` edges for changed `{{result:...}}` references, and transitions modified sections to `stale` if they were in `review` or `published` state. Without sync, the graph doesn't know your edits happened and provenance edges go stale silently.

`paper register --all` is the initial setup step — run once to create PaperSection artifacts for all section files. After that, sync handles updates.

`--dry-run` on either command to preview without writing.

## Paper Foundations Phase

Before iterative editing of sections, establish the constraint surface. This reduces drift, terminological inconsistency, and whack-a-mole fixing across sections. Constraint propagation: reduce degrees of freedom before searching the solution space.

**Foundation files (in `paper/`):**

1. **`glossary.md`** — Controlled vocabulary. Every technical term with definition, correct usage, and banned synonyms. All sections must conform. Machine-checkable via `check_glossary.py`.

2. **`keyword_index.md`** — Auto-generated concordance. Shows which glossary terms appear in which sections. Run `python paper/check_glossary.py` to regenerate and check for banned synonym violations. Zero tokens needed.

3. **`evidence_map.md`** — Which results support which claims, which figures visualize which data, which scripts produced what. The human-readable provenance reference.

4. **`conventions.md`** — Style and terminology rules (already exists). Paper-specific rules section covers term usage.

**Recommended writing order:** Conclusion first (backwards from reader order, forwards from argument logic). Establish claims → evidence that supports them → methods that produced the evidence → background/framing → intro → abstract last. Each layer constrains the next.

**The glossary and evidence map ensure that whatever order you write in, terminology and results stay consistent.** Any section that uses an undefined term or an unregistered result is a detectable violation.

## Key Directories

| Directory | Purpose |
|-----------|---------|
| `docs/design/` | Architectural decisions, design insights |
| `docs/requirements/` | Requirements specifications |
| `handoffs/` | Session handoff notes (gitignored) |
| `cc_tasks/` | Claude Code task files and RESULTs. `cc_tasks/` is intentionally tracked; `handoffs/` is not. |
| `output/results/` | Registered results as YAML |
| `ontology/` | Shared ontology definitions (validity vocabulary) |

**Seldon repo:** `/Users/brock/Documents/GitHub/seldon/`
**SAS conversion repo:** `/Users/brock/Documents/GitHub/sas_graph_code_conversion/`

## Principles

1. Do it right the first time. No shortcuts.
2. Adopt before create.
3. Sessions are discontinuous. Write handoffs like you'll have amnesia tomorrow.
4. Register results immediately. Unregistered numbers drift.
5. Tasks that aren't tracked don't get done.

## Guaranteed Properties (-ilities)

Recoverability, Scalability, Composability, Auditability, Reproducibility, Resilience, Evolvability. See `README.md` for definitions.

## Paper Authoring

Seldon tracks paper manuscripts as graph-connected artifacts. Section prose uses reference tokens that resolve against the graph at build time.

**Reference syntax:**
- `{{result:NAME:value}}` — resolves to a verified Result's value
- `{{result:NAME:units}}` — resolves to units
- `{{figure:NAME:path}}` — resolves to figure file path
- `{{cite:NAME:bibtex_key}}` — resolves to BibTeX key

**Never write literal numbers for research results.** Use `{{result:NAME:value}}`. The build step resolves them from the graph — this prevents drift.

**QC tiers:**
- Tier 1 (structural): Build fails if references are missing, stale, or unverified. Always runs.
- Tier 2 (prose quality): Sentence length, paragraph length, formatting. Flags violations.
- Tier 3 (style): Banned words, clichés, repetition. Informational.

**Config files:** `paper/paper_qc_config.yaml` (Tier 2), `paper/paper_style_config.yaml` (Tier 3)
**Conventions:** `paper/conventions.md` — READ before writing any prose.

## Documentation Standards

Every artifact in the Seldon graph has documentation properties defined in the domain config (`research.yaml`). Required properties are enforced at creation time. Documentation properties are tracked for completeness.

Run `seldon docs check` to see documentation gaps. Run `seldon docs generate` to produce reference documentation from the graph.

Every public function gets a docstring (Args/Returns/Raises). Every module gets a top-level docstring. Every CLI command has useful `--help` text. When registering artifacts via `seldon artifact create`, include all required properties and as many documentation properties as reasonable.

## Architecture Decisions

`docs/design/seldon_architectural_decisions.md` — AD-001 through AD-014.
AD-017: Central Validity Ontology — `docs/design/AD-017_central_validity_ontology.md`
AD-021: Session Continuity Fidelity — `docs/design/AD-021_session_continuity_fidelity.md`
AD-026: `seldon init` Project Templates — `docs/design/AD-026_init_templates.md`
AD-027: Snapshot Artifacts Are Exempt From Drift Checking — `docs/design/AD-027_snapshot_artifacts.md`
AD-028: Result Names, Transitional Units Fallback, and ResearchTask Terminal Semantics — `docs/design/AD-028_result_names_and_task_lifecycle.md`
AD-029: `precedes` — Task Ordering as a First-Class Relationship — `docs/design/AD-029_task_precedence.md`
AD-030: Governed Documents as Graph Content — `docs/design/AD-030_governed_documents_as_graph_content.md`

## Project Templates

`seldon init <name>` applies a project template (YAML under `seldon/templates/`).
Default is `blank` (empty graph). Use `--template paper` for manuscript projects.
`seldon init --list-templates` enumerates available templates. The chosen template
is recorded at `project.template` in the generated `seldon.yaml`. Adding a new
project type is a new YAML file, not a code change. See AD-026.

## Shared Ontology

The validity vocabulary is centralized in `seldon-ontology` (master Neo4j database).
Projects hold read-only replicas synced via `seldon ontology sync`.
All writes go to master via `seldon ontology ingest`.
Projects cannot create or modify OntologyTerm artifacts locally.
Project-specific terms link to shared terms via `references_ontology` relationships.

`ingest` compares the parsed vocabulary against master before writing: the master
epoch moves, and an `ontology_ingested` event is written, **only** when master
content actually changed. An ingest that finds nothing to do writes nothing and
leaves every replica current. `--dry-run` reports the same plan without writing.

Terms present in master but absent from the source are **reported, not retired**.
Pass `--deprecate-missing` to retire them; `deprecated` is terminal for an
OntologyTerm, so this is irreversible and a term retired this way cannot be
re-ingested under the same `term_id`. `sync` propagates a master deprecation to
replicas that already carry the term and does not introduce deprecated terms into
replicas that never had them.
