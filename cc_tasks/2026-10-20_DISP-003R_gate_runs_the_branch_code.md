# DISP-003R: a stop-gate check runs the branch's own code; a receipt that cites its own note is a self-citation, not a failure; a blocked task whose kept worktree is complete is re-gated in place and merged; a path named in a task's body is not a governing note

**Repo:** seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green (AD-034 ADDENDUM 01).
**Date:** 2026-10-20. **Authored by:** a Desktop session in squiddy (SQ8). **Re-issues:** DISP-003 (`7f5de59e`), held `governing_unverified` because a premise named the AD-036 addendum this task repairs, and registration treats any `docs/design/` path in the body as a governing note. That is the fourth defect below.
**Governing:** AD-038-R4 (a station inspects the tree the session works in), AD-034-R5 and R6, AD-036-R2 and R7, AD-038-R6. Write the rules as AD-037 ADDENDUM 02 (gate code path), AD-036 ADDENDUM 07 (self-citation; governing is the header), and no new control without its negative control.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.3M tokens. Basis: PA-002's RESULT names the first two defects and the fix for each; four small changes with tests, then one re-gate. The floor is 131K.
**Parts:** A 0.35, B 0.3, C 0.35.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: PA-002's branch is complete and kept | check: `test -f .claude/worktrees/delegated-floating-coral/cc_tasks/2026-10-19_PA-002_receipts_verify_against_the_release_they_name_RESULT.md`
- premise: the stop gate ran PA-002's checks with the primary's code | check: `grep -q "stop_gate_unpassed" logs/seldon_dispatch.log`
- premise: a receipt citing the AD-036 base note's own line exists in its addenda | check: `grep -rq "AD-036_prior_art_receipts_gate.md:95" docs/design`

Glob and read every sibling `*DISP-003R*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.45M.

## The defects

1. A `check:` that starts with `seldon ...` runs the console script, which imports the primary checkout's code. A branch that changes the code a check depends on can never pass its own gate. PA-002's Part B check failed for that reason alone (branch `worktree-delegated-floating-coral`, RESULT present, tests green, verdicts recorded).
2. The AD-036 addendum on prior art by reference cites the base note's own line 95 at its line 106. Since SQ-012 the internal arm leaves the note under verification out of its own prior art, so that receipt reads `id_not_returned` and AD-036 fails on it forever; addenda are immutable (R7).
3. A task blocked `stop_gate_unpassed` with green tests and a committed RESULT has no path back except a fresh launch that redoes the work.
4. Registration treats every `docs/design/` path in a task's body as a governing note (STD-001 on 2026-10-19 and DISP-003 today were both held for naming a note they repair). Governing is the `**Governing:**` header, nothing else.

## Part A: the gate runs the branch

1. The milestone and stop-gate stations run every `check:` with the session's tree on the path: `seldon` in a check resolves to `python -m seldon` with `PYTHONPATH=<worktree>` and cwd the worktree. Record interpreter and path in the `stop_gate` record.
2. Tests, failing on HEAD: a check `seldon --version` in a worktree whose code prints a marker reports the marker; a check that passes only with the branch's code passes.

Acceptance:
- `check: pytest tests/test_disp003_gate_path.py -q`

## Part B: self-citation, and governing is the header

1. In the verifier, an internal receipt whose cited location is inside the note under verification (base or any addendum) is reported `self_citation` and neither passes nor fails the note. AD-036 ADDENDUM 07, with the line-106 receipt as evidence.
2. `cc register` derives the governing set from the `**Governing:**` header only. A `docs/design/` path elsewhere in the body is text.
3. Tests, failing on HEAD: a note whose only failing receipt is a self-citation verifies PASS with one `self_citation` line; a task whose body names an unverified note outside its Governing header registers without a hold.

Acceptance:
- `check: pytest tests/test_disp003_self_citation.py tests/test_disp003_governing_header.py -q`

## Part C: re-gate in place

1. `seldon dispatch regate <task>`: for a task blocked `stop_gate_unpassed` whose kept worktree holds a committed RESULT, rebase the worktree branch onto main, run its `check:` lines through Part A's path, and on pass hand the branch to the existing merge path (merge on green, complete, sweep). On fail, leave it blocked with the failing check quoted. The dispatcher runs this on every pass for every such task.
2. Run it for `314a3942` (PA-002). Record the outcome.
3. Test, failing on HEAD: a stubbed blocked task with a kept worktree and passing checks ends `merged`.

Acceptance:
- `check: pytest tests/test_disp003_regate.py -q`

## Report

RESULT under 15 lines: the two addenda, the four test files, PA-002's regate outcome and merge sha, tokens against 0.3M.
