# Seldon — Research Operating System

The queen of the colony. Persistent graph intelligence that decomposes research work, provides agents with precisely-scoped context slices, validates what comes back, and maintains collective state.

**The graph is the mind. The agents are the hands.**

See `README.md` for full vision and architectural properties.

## Current State

Working engine: Neo4j graph + JSONL event store + CLI. 290+ tests passing. Domain config with property schemas (AD-013). Paper assembly pipeline (AD-012). Documentation-as-traceability infrastructure. `seldon go` MCP server for Desktop orientation. Agent role + workflow definitions in graph (AD-014). Paper sync for iterative editing workflow. Paper foundations workflow (glossary, keyword index, evidence map).

## Environment

**Neo4j credentials are in `.env`.** CC: you have the password. Load it with `dotenv` or read `.env` directly. Do NOT skip Neo4j-dependent tests. Do NOT ask for the password. If tests fail with auth errors, run: `source .env && pytest tests/ -v` or pass `NEO4J_PASSWORD` explicitly.

**Database:** Each project gets its own Neo4j database. Seldon self-dogfood uses `seldon-seldon-self`. Leibniz-pi uses its own database per `seldon.yaml`.

**Python:** Seldon is pip-installed in the active environment. `seldon` CLI is available on PATH.

**MCP default project:** Set `SELDON_DEFAULT_PROJECT=/path/to/project` in the `seldon-mcp` env block in `claude_desktop_config.json`. When `seldon_go` is called without `project_dir`, it falls back to this path if it contains `seldon.yaml`.

## Skills

| Skill | When | Invoke |
|-------|------|--------|
| `briefing` | Session start | `/briefing` or `seldon briefing` |
| `closeout` | Session end | `/closeout` or `seldon closeout` |
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

## Session Protocol

1. **Start**: `/briefing` — reads handoffs, surfaces open tasks, identifies critical path
2. **Work**: `/result-register` for quantitative output, `/task-track` for cross-session items
3. **End**: `/closeout` — structured handoff, commit

## Paper Editing Workflow

**The loop is: edit → sync → build.** This is mandatory, not optional.

After ANY edit to `paper/sections/*.md` — whether manual prose edits, CC tasks that rename result references, or anything that changes section file content:

```bash
python paper/check_glossary.py       # check terms + regenerate keyword index
seldon paper sync                    # reconcile graph with disk (hashes, edges, state)
seldon paper build --no-render       # verify references still resolve
```

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
| `cc_tasks/` | Claude Code task files (gitignored) |
| `output/results/` | Registered results as YAML |

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
