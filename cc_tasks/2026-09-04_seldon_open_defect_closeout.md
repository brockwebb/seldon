# CC Task — Seldon open-defect closeout

**Date:** 2026-09-04
**Project:** seldon
**Authored by:** Desktop session
**Closes:** `42be368d`, `0977c79a`, `c9fdef46`, `3376805b`, `1581c3ec`, `f6b32bbe`
**Spend:** zero model spend.
**Scope rule:** these six and nothing else. The April/May design backlog stays open.

**Immutable once written. Changes require a new task file or an `_ADDENDUM-NN.md` sibling.**

---

Each task's description in the graph is its spec; read all six by query before starting. Lanes as subagents where file ownership is disjoint; sequence where the descriptions say so. Worktree per the 2026-09-04 precedent, with the console-script trap from that RESULT §6.6 in mind: force the module path when verifying from a worktree and record the SHA.

## Sequence and constraints

1. `42be368d` recoverability — first, alone. Replay-into-scratch verify check runs against all 30 DBs; report every failure. Legacy lines are never rewritten.
2. `0977c79a` small defects and `f6b32bbe` resolver options — parallel, disjoint (ontology parsers + `paths.py` + `__main__.py` vs `paper/build.py`). For `f6b32bbe`, add a test that the ai-readiness-kg shim's two workarounds become unnecessary: render `26.0` as `26` via the hook and a `proposed` value with no marker via the flag.
3. `3376805b` placeholder regex — with `f6b32bbe` (same file). Test: `{{result:<n>:value}}` is not a reference; `{{result:G1_x:value}}` is.
4. `c9fdef46` replica sync-all — after 2 lands, so each replica syncs once. Dry-run report for all DBs first, then live. Drop `seldon-test-project` only after grepping every project dir for a reference to it.
5. `1581c3ec` SI-09 removal — last, and conditional. The removal condition is *all projects at zero fallback resolutions*; only ai-readiness-kg has been measured. Find every project with `{{result:` tokens in tracked files (grep each project dir listed by the DB inventory), run the resolver in check mode, report per project. Remove the fallback only if every count is zero; otherwise leave it, report the non-zero projects, and note in the task that removal is blocked by named projects.

## Integration

Full suite green, count ≥ 1180 + new. `seldon verify` clean including the new replay check. Close each task with `seldon task close` and a note; `cc complete` this file. Commit and push; task file and RESULT both tracked.

## RESULT must report

Per task: shipped / deferred / premise contradicted. Replay-check results across all 30 DBs. The SI-09 per-project table. Test counts.
