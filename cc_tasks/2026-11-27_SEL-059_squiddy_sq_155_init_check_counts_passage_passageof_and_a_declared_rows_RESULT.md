# RESULT: SEL-059, squiddy SQ-155's init --check fix verified on seldon-biblio

**Date:** 2026-11-27. **Task:** 2872c10e. **Returns:** squiddy SQ-155 (82fa761a), which answered seldon's filing
`fb0f9767`. **Addenda read:** none exist (`ls cc_tasks | grep SEL-059` lists only the task file).
**Spend:** zero model calls; one read-only init check run twice. **Network:** none.
**Not done, per the dispatcher's launch instructions:** merge, push, `seldon cc complete`.

Recall used: none

## Step 0: the fix is on squiddy main

The return was filed before SQ-155 merged, so I checked the merged code before running the step. Squiddy main carries
SQ-155 (`bc4cc1e0` "SQ-155 Part B: init --check counts the passage and rows writers ...", then its RESULT and the
dispatcher's `04ef2791` record). `squiddy/init.py` `check` now adds the passage classes and, for a spec that
declares `rows:`, `rows.config()["writable"]` to `buildable` (lines 1545-1551). I read the SQ-155 RESULT in full.

## Part A: what was applied

Step 1, `SQ init graphs/seldon-biblio --check` with `SQ=/Users/brock/GitHub/squiddy/.venv/bin/squiddy`, run by
`/tmp/sel059_check.sh` (the worktree guard refuses a command that names the `GitHub` path inline):

```
init --check: .../worktrees/wise-brewing-nebula/graphs/seldon-biblio matches graph.yaml (spec sha256 9a27037c29a5)
EXIT=0
init --check: /Users/brock/GitHub/seldon/graphs/seldon-biblio matches graph.yaml (spec sha256 9a27037c29a5)
EXIT=0
```

Exit 0 and `matches graph.yaml` with spec sha256 `9a27037c29a5`, in this worktree and in the primary checkout, the
same as SQ-155 measured. `Passage` and `PassageOf` are no longer reported as declared but never emitted.
`git status` is clean after the check, so the check wrote nothing.

The filing `fb0f9767` is `state: completed` in squiddy's graph (`seldon artifact show fb0f9767`, run from squiddy).

## What was not applied

Nothing else. As the task says, nothing in seldon changes: no code, config or graph edit. factory-kg's matching
finding belongs to factory's return (FAC-56) and was not touched here.
