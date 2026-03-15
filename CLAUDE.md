# Seldon — Research Operating System

The queen of the colony. Persistent graph intelligence that decomposes research work, provides agents with precisely-scoped context slices, validates what comes back, and maintains collective state.

**The graph is the mind. The agents are the hands.**

See `README.md` for full vision and architectural properties.

## Current State: Phase A (Skills + Conventions)

No engine yet. The skills in `.claude/skills/` ARE Seldon at this stage. The engine (NetworkX + JSONL + CLI) gets built when the markdown pattern hits limits.

**Proof-of-concept project:** `sas_graph_code_conversion/`

## Skills

| Skill | When | Invoke |
|-------|------|--------|
| `briefing` | Session start | `/briefing` |
| `closeout` | Session end | `/closeout` |
| `result-register` | Computation produces a citable result | `/result-register` |
| `task-track` | Work item must survive across sessions | `/task-track` |
| `research` | Writing lab notebook entries, lit notes, citations | `/research` |
| `paper audit`  | After writing/editing prose | `seldon paper audit paper/sections/*.md` |
| `paper build`  | Assembling manuscript       | `seldon paper build` |

## Session Protocol

1. **Start**: `/briefing` — reads handoffs, surfaces open tasks, identifies critical path
2. **Work**: `/result-register` for quantitative output, `/task-track` for cross-session items
3. **End**: `/closeout` — structured handoff, commit

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

## Architecture Decisions

`docs/design/seldon_architectural_decisions.md` — AD-001 through AD-010.
