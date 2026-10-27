# DESK-004R: every file the machine writes is committed by the tool that wrote it (hooks and late addenda)

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-27. Re-filing, with candidacy headers, of DESK-004 (2f2f1174) and 60fb6b11 (late addenda left untracked); same class, neither had a source file.
**Repo:** seldon (primary). L4: commit, merge, push in seldon.
**After:** bacacc4c
**Governing:** DESK-001's rule (the tool that writes a governed file commits it); AD-038-R1 (the dispatcher reconciles machine-written state before c7). Number new rulings under AD-038.
**Model:** primary
**Spend:** est. 0.3M tokens. Basis: the hook installer commits its file, the addendum sweep drops one condition, two clean-tree tests. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits the dispatcher's commit sweep and the hooks installer)
**Parts:** A 0.50, B 0.50.
**Premises:**
- premise: the dispatcher sweeps registered files with _commit_registered | check: grep -rq _commit_registered seldon
- premise: a hooks installer exists | check: grep -rq "commit-msg" seldon

Checks are single commands with no shell.

## The condition

A. `seldon hooks install` writes `.githooks/commit-msg` and leaves it untracked; `seldon_commit_governed` refuses `.githooks/` paths. Measured 2026-10-22 in squiddy: untracked since 2026-10-21 21:17, every pass failed c7 for every candidate (SUITE-001 9324622d included).

B. The dispatcher's `_commit_registered` sweeps `<stem>_ADDENDUM*.md` only when the base file is untracked, so an addendum written after its base was committed, and not itself registered, is committed by nobody and fails c7 for the queue (ai-readiness-kg 1267b87d: three tasks stuck 2026-10-02 to 10-04).

## What to build

**A.** The installer commits the hook it writes, through the hooks, path-limited; test that a fresh install in a scratch repo leaves `git status --porcelain` empty.

**B.** The sweep commits untracked addenda of every open registered task, base tracked or not, in the same path-limited commit as today; test with a tracked base and an untracked addendum.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.4M.

## Deliverables

A and B with tests; 2f2f1174 and 60fb6b11 superseded in the closing commit; `cc_tasks/2026-10-27_DESK-004R_every_file_the_machine_writes_is_committed_by_the_tool_that_wrote_it_RESULT.md`.
