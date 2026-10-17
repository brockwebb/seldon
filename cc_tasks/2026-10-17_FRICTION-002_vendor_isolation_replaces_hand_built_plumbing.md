# FRICTION-002: every dispatched task runs in a Claude Code worktree; the Stop hook is the completion gate; sessions run in auto mode with the breaker. The vendor survey is filed.

**Repo:** seldon. L4: commit, merge, push. Work on a branch; merge before each `part-complete`.
**Date:** 2026-10-17. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** AD-034 (worktree per task; this task removes its `max_parallel > 1` and `Exclusive: yes` carve-outs so worktree is the only mode), AD-038-R1 (reconciler), AD-038-R4 (stations inspect the session's tree; satisfied here by there being one tree per task), AD-038-R6 (no control without a negative control). No new ruling; where AD-034's text must change, write AD-034 ADDENDUM with the three stalls as evidence.
**After:** c48b3fd6
**Resolves:** Issue `02d52bc4` if FRICTION-001 did not; the `max_parallel: 1` carve-out.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 1.0M tokens. Basis: FRICTION-001's estimate for five areas was 1.5M; this is three, each a replacement of existing code with a vendor feature.
**Parts:** A 0.15, B 0.35, C 0.30, D 0.20.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: FRICTION-001 merged the reconciler | check: `grep -q "reconcile" seldon/commands/dispatch.py`
- premise: the pinned Claude CLI supports worktrees | check: `/Users/brock/.local/share/seldon/claude-cli/2.1.300/node_modules/.bin/claude --help | grep -q -- --worktree`
- premise: the vendor survey is in the workbench | check: `test -f /Users/brock/GitHub/workbench/2026-10-17_codex_claude_and_the_friction_problem.html`

Glob and read every sibling `*FRICTION-002*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Token ceiling 1.2M. A Part whose full suite fails on the branch is not merged; record and stop.

## Part A: file the survey

1. Move `/Users/brock/GitHub/workbench/2026-10-17_codex_claude_and_the_friction_problem.html` and `2026-10-17_where_things_stand.md` into `docs/research/2026-10-17_vendor_survey_codex_claude_code.html` and `docs/research/2026-10-17_where_things_stand.md`. Commit them so the governed graph admits them on the next sweep (AD-030-R1). Leave the workbench copies.
2. Read the survey's section 1 table before Parts B to D; it names the vendor features this task adopts and the source pages.

Acceptance:
- `check: test -f docs/research/2026-10-17_vendor_survey_codex_claude_code.html`

## Part B: worktree is the only mode

1. The dispatcher launches every task with the CLI's `--worktree` (branch `worktree-<task-stem>`), in every repository it serves. `Exclusive:` stays a header for the lease, not for the checkout. `max_parallel` stays 1 for now.
2. The primary checkout is touched by three things only: the dispatcher's own commits, merges on green, and Desktop's governed commits. Verify the CLI's hard isolation blocks a session's write to the primary; record the refusal text as evidence.
3. The session merges to main on green, as AD-034-R5 says. A task that ends unmerged keeps its worktree and branch; the dispatcher records `worktree_kept` with the branch name and the RESULT's reason. Nothing deletes a branch.
4. Tests, each failing on HEAD: a launched task runs in a worktree; a write to the primary from inside the session is refused; an unmerged task leaves its branch and a `worktree_kept` record; a merged task's worktree is removed by the sweep.

Acceptance:
- `check: pytest tests/test_friction002_worktree_only.py -q`

## Part C: the Stop hook is the completion gate

1. A `Stop` hook, installed per launch, runs the task's `check:` criteria for every Part the session has declared complete and refuses to end the session while any fails and the token ceiling is not reached. Its output is a record the milestone station reads; the station runs no check of its own.
2. The `first article` station keeps its own check, because it runs mid-loop.
3. Negative control (AD-038-R6): a correct session with all checks passing ends on the first Stop.
4. Tests, each failing on HEAD: a failing check keeps the session alive and the record names it; a passing session ends; the ceiling ends a session with failing checks and writes a hard stop.

Acceptance:
- `check: pytest tests/test_friction002_stop_hook_gate.py -q`

## Part D: auto mode with the breaker

1. Dispatched sessions launch with `--permission-mode auto` instead of `bypassPermissions`. The classifier's breaker (3 consecutive or 20 total blocks) becomes a `session_stop` of kind `line` with the classifier's reason, redriven by the operator or Desktop (AD-038-R2).
2. Record, per launch, how many actions the classifier blocked; `qc chart` reports it.
3. Measure over this task's own run and the first three after it whether any block was a false positive. If the false-positive count after three tasks exceeds one per task, write the finding as an Issue and switch the default back; do not argue it in the RESULT.
4. Tests: launch command carries the mode; a classifier block becomes a `session_stop`.

Acceptance:
- `check: pytest tests/test_friction002_auto_mode.py -q`

## Report

RESULT under 30 lines: tokens per Part against 1.0M; each test's failure on HEAD; the isolation refusal text; the first classifier block count; premises found wrong. Then `seldon verify`, `seldon cc complete`, merge, push.
