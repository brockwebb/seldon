# Handoff: 2026-09-12 Seldon design session, governed documents as graph content

**Date:** 2026-09-12 (Saturday)
**From:** Desktop session (claude.ai, Seldon project)
**To:** Next Desktop session
**Prior handoff:** `handoffs/2026-04-18_session_close.md` (five months stale; graph state was current, handoff was not)

---

## One line

Diagnosed that Seldon's own ADs, design notes, requirements, cc_tasks and handoffs are file pointers in the graph with zero edges (same disease as Arnold, cause of the RPE reintroduction); wrote AD-030; wrote and registered two CC tasks, chained, not yet run.

## Files written

- `docs/design/AD-030_governed_documents_as_graph_content.md` (draft, rulings AD-030-R1..R10). Not in the graph until the ingest task runs.
- `cc_tasks/2026-09-12_seldon_handoff_tool.md`
- `cc_tasks/2026-09-12_ad030_governed_docs_ingest.md`
- This handoff.

## Graph changes

- ResearchTask `dbe3d2dd` (proposed): AD-030 decision record.
- ResearchTask `a5c372d1` (proposed): `seldon handoff` feature record.
- ResearchTask `343cb6fe` (proposed): CC task, handoff tool.
- ResearchTask `d7fb603f` (proposed): CC task, AD-030 ingest and backfill.
- `precedes`: 343cb6fe -> d7fb603f.

## Decisions

All in AD-030; read the file, do not reconstruct from here. One implementation finding recorded in the ingest task as a fixed assumption: Squiddy's DI-005 guard refuses `seldon-*` projection targets, so the governed-docs graph is a Squiddy graph inside the Seldon repo with its own ledger and no Neo4j backend; Seldon imports that ledger through its own write path.

## Open / next

1. Run the two CC tasks in order (dispatch text below). Nothing from this session has executed.
2. After both RESULT files exist: verify against the graph, read the RESULT findings for any AD-030 ruling that failed in implementation, write addenda if needed, then close dbe3d2dd and a5c372d1.
3. Arnold rulings are the second corpus for the recipe; not yet tasked.
4. 13 older open Seldon tasks are paper-pipeline polish and rank below all of the above.

## Resume line (copy/paste to open the next Desktop thread)

```
seldon go --brief /Users/brock/GitHub/seldon/handoffs/2026-09-12_ad030_governed_documents_design.md
Read the handoff in full, then docs/design/AD-030_governed_documents_as_graph_content.md.
Verify tasks dbe3d2dd, a5c372d1, 343cb6fe, d7fb603f against the graph before acting.
First action: read cc_tasks/*2026-09-12*_RESULT.md if present and reconcile against the graph;
if absent, the CC tasks have not run yet.
```

## CC dispatch text (Seldon Claude Code window, run in this order)

```
Read CLAUDE.md, then execute cc_tasks/2026-09-12_seldon_handoff_tool.md. Glob and read all sibling *ADDENDUM*.md files first. When complete and pushed, continue with cc_tasks/2026-09-12_ad030_governed_docs_ingest.md, same rule on addenda. Both tasks are L4: commit, merge to main, push, close the Seldon task IDs named in each file.
```
