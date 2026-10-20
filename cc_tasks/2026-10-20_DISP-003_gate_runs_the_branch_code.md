# DISP-003: a stop-gate check runs the branch's own code; a receipt that cites its own note is a self-citation, not a failure; a blocked task whose kept worktree is complete is re-gated in place and merged

**Repo:** seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green (AD-034 ADDENDUM 01).
**Date:** 2026-10-20. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** AD-038-R4 (a station inspects the tree the session works in), AD-034-R5 and R6, AD-036-R2 and R7, AD-038-R6. Write the two rules as AD-037 ADDENDUM 02 (gate code path) and AD-036 ADDENDUM 07 (self-citation); no new control without its negative control.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.3M tokens. Basis: PA-002's RESULT names both defects and the fix for each; three small changes with tests, then one re-gate. The floor is 131K.
**Parts:** A 0.4, B 0.3, C 0.3.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: PA-002's branch is complete and kept | check: `test -f .claude/worktrees/delegated-floating-coral/cc_tasks/2026-10-19_PA-002_receipts_verify_against_the_release_they_name_RESULT.md`
- premise: the stop gate ran PA-002's checks with the primary's code | check: `grep -q "stop_gate_unpassed" logs/seldon_dispatch.log`
- premise: the self-citing receipt exists | check: `grep -q "AD-036_prior_art_receipts_gate.md:95" docs/design/AD-036_ADDENDUM_03_prior_art_by_reference.md`

Glob and read every sibling `*DISP-003*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.45M.

## The defects, from PA-002's RESULT (branch `worktree-delegated-floating-coral`)

1. A `check:` that starts with `seldon ...` runs the console script, which imports the primary checkout's code. A branch that changes the code a check depends on can never pass its own gate. PA-002's Part B check `seldon prior-art verify ...` failed for that reason alone; its tests pass and its verdicts are recorded.
2. AD-036 ADDENDUM 03 line 106 cites the base note's own line 95. Since SQ-012 the internal arm leaves the note being verified out of its own prior art, so that receipt reads `id_not_returned` and AD-036 fails on it forever; addenda are immutable (R7).
3. A task blocked `stop_gate_unpassed` with green tests and a committed RESULT has no path back except a fresh launch that redoes the work.

## Part A: the gate runs the branch

1. The milestone and stop-gate stations run every `check:` with the session's tree on the path: `seldon` in a check resolves to `python -m seldon` with `PYTHONPATH=<worktree>` and cwd the worktree (AD-038-R4 already says the station inspects that tree; this makes the code follow). Record the interpreter and path in the `stop_gate` record.
2. Tests, failing on HEAD: a check `seldon --version` in a worktree whose code prints a marker version reports the marker; a check that passes only with the branch's code passes.

Acceptance:
- `check: pytest tests/test_disp003_gate_path.py -q`

## Part B: self-citation

1. In the verifier, an internal receipt whose cited location is inside the note under verification (base or any addendum) is reported `self_citation` and neither passes nor fails the note; the verdict lists it. AD-036 ADDENDUM 07, one rule, with ADDENDUM 03:106 as the evidence.
2. Test, failing on HEAD: a note whose only failing receipt is a self-citation verifies PASS with one `self_citation` line.

Acceptance:
- `check: pytest tests/test_disp003_self_citation.py -q`

## Part C: re-gate in place

1. `seldon dispatch regate <task>`: for a task blocked `stop_gate_unpassed` whose kept worktree holds a committed RESULT, rebase the worktree branch onto main, run the task's `check:` lines through Part A's path, and on pass hand the branch to the existing merge path (merge on green, complete, sweep). On fail, leave it blocked with the failing check quoted. The dispatcher runs this on every pass for every such task, so a redrive is never needed for this case.
2. Run it for `314a3942` (PA-002). Record the outcome.
3. Test, failing on HEAD: a stubbed blocked task with a kept worktree and passing checks ends `merged`.

Acceptance:
- `check: pytest tests/test_disp003_regate.py -q`

## Report

RESULT under 15 lines: the two addenda, the three test files, PA-002's regate outcome and merge sha, tokens against 0.3M.
