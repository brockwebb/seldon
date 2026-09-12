# CC Task: `seldon handoff` Desktop closeout tool

**Date:** 2026-09-12
**Project:** seldon (`/Users/brock/GitHub/seldon`)
**Seldon task:** a5c372d1
**Governing doc:** `docs/design/AD-030_governed_documents_as_graph_content.md`, ruling AD-030-R9
**Mode:** L4. Commit, merge to main, push are this task's job. Close a5c372d1 citing the commit hash.

## Goal

One command, `seldon handoff`, with MCP parity as `seldon_handoff`, that closes a Desktop session: writes the handoff file from graph state, returns the resume block for the next Desktop thread, returns the CC dispatch block for the thread's last task, and enforces AD-030-R9.

## Prerequisites

- Read `CLAUDE.md`, then `docs/design/AD-030_governed_documents_as_graph_content.md` in full.
- Glob and read any `cc_tasks/2026-09-12_seldon_handoff_tool*ADDENDUM*.md` before starting.
- Test suite green at start: `python -m dotenv -f .env run -- python -m pytest tests/ -v`.

## Steps

1. **Session window.** Define "this session" as events since the newest LabNotebookEntry or handoff file, whichever is later; fall back to the last 12 hours. Put the fallback window in `seldon.yaml` under `handoff.session_window_hours`; never hardcode.
2. **R9 check.** If the window contains any ResearchTask created with `created_by` = desktop AND no file under `docs/design/` was created or modified in the window (filesystem mtime; the DesignNote node check is added when AD-030 ingest lands), refuse with the message "Desktop design session closed without a design note (AD-030-R9). Write docs/design/<note>.md, then rerun." Config key `handoff.require_design_note: true` in `seldon.yaml`; when false, warn instead of refuse.
3. **Handoff file.** Write `handoffs/YYYY-MM-DD_<slug>.md` (slug from `--slug`, required). Sections, generated from the graph, not typed: One line (from `--summary`, required); Graph changes (tasks created, closed, withdrawn, superseded in the window, with IDs); Files written (docs/design and cc_tasks files touched in the window); Open tasks (ready first); Resume line; CC dispatch. Match the existing handoff format in `handoffs/` for headings.
4. **Resume block.** Return, and embed in the file, exactly:
   ```
   seldon go --brief <absolute handoff path>
   Read the handoff in full. Verify listed task IDs against the graph before acting.
   First action: <from --next, required>
   ```
5. **CC dispatch block.** For each cc_task file registered in the window and still `proposed`, return in order:
   ```
   Read CLAUDE.md, then execute cc_tasks/<file>.md. Glob and read all sibling *ADDENDUM*.md first.
   ```
   If none, the block says "No CC task ready" and why.
6. **`seldon go` line.** Add one line to the Desktop contract printed by `seldon go`: "Close with `seldon handoff --slug <s> --summary <s> --next <s>`; a design session must write docs/design first (AD-030-R9)." Also report, at orient, if the previous handoff's window created desktop tasks and no docs/design file: "Previous Desktop session violated AD-030-R9."
7. **MCP parity.** `seldon_handoff(project_dir, slug, summary, next)` in the MCP server returns the same two blocks as text.
8. **Tests.** New test file covering: R9 refuse and warn paths; handoff file content generated from a seeded graph; resume block exact text; dispatch block ordering; config keys read from `seldon.yaml`.
9. `seldon verify --strict`, full suite, commit, push, `seldon cc complete cc_tasks/2026-09-12_seldon_handoff_tool.md`, close a5c372d1 with the hash.

## Success contract

- `seldon handoff --slug x --summary y --next z` on this repo writes a file and prints both blocks.
- Refuses when a desktop task exists in the window and no docs/design file changed.
- Suite green; `seldon verify --strict` exit 0.

## What NOT to do

- Do not introduce a second term for closeout. The command is `handoff`.
- Do not edit `docs/design/AD-030_*.md`.
- Do not implement the DesignNote-node form of the R9 check; that belongs to the AD-030 ingest task.
- Do not stop on an unmerged branch.
