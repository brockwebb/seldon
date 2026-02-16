# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Project Overview

**Seldon** — Research writing and report assembly system. Orchestrates ANTS (traceability) and Wintermute (knowledge vault) to produce coherent scholarly output with proper citations across sessions.

Systematic knowledge preservation across discontinuities.

## Key Directories

| Directory | Purpose |
|-----------|---------|
| `docs/` | Requirements, architecture, design decisions, references |
| `handoffs/` | Session handoff notes for context continuity (gitignored) |
| `cc_tasks/` | Claude Code task files (gitignored) |
| `templates/` | Markdown templates for lab notebook entries, lit notes, etc. |
| `output/` | Generated reports and documents (gitignored) |
| `notes/` | Private working notes (gitignored) |
| `tmp/` | Scratch space (gitignored) |

**Full paths (always use absolute paths):**
- **Repo root:** `/Users/brock/Documents/GitHub/seldon/`
- **Handoffs:** `/Users/brock/Documents/GitHub/seldon/handoffs/`
- **CC Tasks:** `/Users/brock/Documents/GitHub/seldon/cc_tasks/`

**Naming conventions:**
- Handoffs: `YYYY-MM-DD_<slug>.md`
- CC tasks: `YYYY-MM-DD_<slug>.md` or descriptive `<slug>.md`
- Lab notebook entries: `YYYY-MM-DD_<slug>.md`
- Literature notes: `YYYY-MM-DD_<slug>.md`

## Citation Standard

**APA 7th Edition** for all references. Maintain `docs/references/references.bib` as the canonical bibliography file. When citing in markdown, use inline format:

`(Author, Year)` for parenthetical, `Author (Year)` for narrative.

## Related Systems

| System | Role | Repo |
|--------|------|------|
| **ANTS** | Artifact traceability (requirements ↔ code ↔ tests) | `ai-native-traceability-system/` |
| **Wintermute** | Knowledge vault (entity graph, semantic search) | `wintermute/` |
| **Seldon** | Research writing orchestration (this repo) | `seldon/` |

## Principles

1. **Do it right the first time.** No shortcuts, no lazy band-aids.
2. **Adopt before create.** Evaluate existing solutions before building.
3. **APA citations everywhere.** No exceptions.
4. **Templates enforce consistency.** Use them.
5. **Sessions are discontinuous.** Write handoffs like you'll have amnesia tomorrow.
