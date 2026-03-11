# Seldon — Research Operating System

Per-project artifact traceability, result provenance, task tracking, and session continuity for AI-assisted research. Domain-agnostic core with swappable domain configurations.

Makes AI-assisted research reproducible by default instead of reproducible by heroic effort.

## Current State

Seldon is in **Phase A**: skills and conventions, no engine yet. The skills in `.claude/skills/` ARE Seldon at this stage — they encode the workflow. The engine (NetworkX + JSONL + CLI) gets built when the markdown pattern hits scaling limits.

**Proof-of-concept project:** `sas_graph_code_conversion/` — SAS pipeline migration via graph intermediate representation.

## Skills (invoke these)

| Skill | When | Command |
|-------|------|---------|
| `briefing` | Session start | `/briefing` |
| `closeout` | Session end | `/closeout` |
| `result-register` | Computation produces a citable number | `/result-register` |
| `task-track` | Work item must survive across sessions | `/task-track` |
| `research` | Writing lab notebook entries, lit notes, citations | `/research` |

## Key Directories

| Directory | Purpose |
|-----------|---------|
| `docs/` | Requirements, architecture, design decisions, references |
| `handoffs/` | Session handoff notes (gitignored) |
| `cc_tasks/` | Claude Code task files (gitignored) |
| `templates/` | Markdown templates for lab notebook entries, lit notes |
| `output/` | Generated reports, registered results (gitignored) |
| `output/results/` | Registered results as YAML (created by result-register skill) |

**Absolute paths:**
- **Seldon repo:** `/Users/brock/Documents/GitHub/seldon/`
- **SAS conversion repo:** `/Users/brock/Documents/GitHub/sas_graph_code_conversion/`

## Session Protocol

1. **Start**: Invoke `/briefing` — reads handoffs, surfaces open tasks, identifies critical path
2. **Work**: Use `/result-register` for any quantitative output, `/task-track` for cross-session items
3. **End**: Invoke `/closeout` — writes structured handoff, commits

## Principles

1. **Do it right the first time.** No shortcuts, no lazy band-aids.
2. **Adopt before create.** Evaluate existing solutions before building.
3. **Sessions are discontinuous.** Write handoffs like you'll have amnesia tomorrow.
4. **Register results immediately.** Unregistered numbers drift and lose provenance.
5. **Tasks that aren't tracked don't get done.** If it blocks something, it's a tracked task.

## Architecture (for when the engine gets built)

See `docs/design/seldon_architectural_decisions.md` for full AD registry. Key decisions:
- AD-001: Clean build from ANTS patterns, not refactor
- AD-002: Domain-agnostic core + domain config
- AD-003: CLI commands, not MCP servers
- AD-004: Per-project database, no shared infrastructure
- AD-005: Standard update/retrieve interface
- AD-006: Result Registry as first-class artifact
- AD-007: Task tracking as first-class artifact

## Citation Standard

APA 7th Edition. Maintain `docs/references/references.bib` as canonical bibliography.
