# SEL-024: the merge gate requires the project's declared pass record for the tip it merges, and "environmental" is not green

**Status:** proposed
**Author:** Desktop session (seldon), 2026-11-03, from the SQ11 work-order addendum of 2026-10-30 (`handoffs/2026-10-30_desktop_sq11_work_order_addendum_01_merge_gate_hand_dispatch_register_race.md`, W6).
**Repo:** seldon (primary). squiddy is read by path for the evidence (its pass ledger and DN-043 R-188, DN-052 R-237), never written; squiddy adds its own `gate_record:` declaration by a return task.
**After:** 2026-11-03_SEL-023_a_consumer_filing_is_a_kind_the_registrar_accepts_and_a_desktop_commit_reaches_origin
**Governing:** AD-034 (the merge round and its gate); AD-037-R6 (stations); SQ-096's seldon side (`seldon/core/pass_ledger.py`, the forked-ledger refusal). Number new rulings under AD-034.
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: one config key, one check in the merge round, one classification refusal, fixtures against a scratch ledger. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `dispatch_worktree.py`'s merge round)
**Parts:** A 0.60, B 0.40.
**Premises:**
- premise: the merge round is in dispatch_worktree | check: grep -q "merge_attempts" seldon/commands/dispatch_worktree.py
- premise: the pass-ledger module exists | check: test -f seldon/core/pass_ledger.py
- premise: squiddy's ledger is where W6 measured | check: test -f /Users/brock/GitHub/squiddy/kit/ledger/passes.jsonl

Checks are single commands with no shell.

## The condition

On squiddy main, four tasks merged between the 2026-10-27 pass (`bc345c09`) and SQ-099's (`d31501c7`) with no kit pass record, and SQ-101 merged at `67cde2da` with none; its RESULT classed 17 failures as worktree-environmental and reported that ruff was not installed in the kit venv, so no lint ran. squiddy's DN-043 R-188 requires a pass per kit commit and DN-052 R-237 makes the ledger main's. The merge gate accepts a branch whose RESULT says green-except-environmental, so the rule holds only when a session chooses to honour it.

## What to build

**A. A declared pass record gates the merge.** `dispatch.gate_record:` in seldon.yaml names the command that records a pass and the ledger it appends to (squiddy: `kit record-pass`, `kit/ledger/passes.jsonl`; seldon: its own suite's record, or `none` where a project has no ledger). The merge round refuses `pass_unrecorded` when the ledger carries no line for the exact tip it is about to merge; the gate command runs in the worktree before the record, under the project's declared interpreter (AD-037-R15). The refusal is a block with reason, like `uncommitted_changes`, and the same redrive applies.

**B. "Environmental" is a refusal, not a pass.** A gate run whose output the session classifies as environmental (a missing tool, a missing link, an uninstalled linter) is `gate_unrunnable`, which blocks the merge and opens a huddle naming the tool; it is never recorded as a pass. Fixture: a scratch ledger, a tip with a record merges, a tip without one is refused, a gate with ruff absent is `gate_unrunnable`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.

## Deliverables

A and B with tests; ruling under AD-034; the return to squiddy per AD-036-R16 saying what to declare in `gate_record:`; `cc_tasks/2026-11-03_SEL-024_the_merge_gate_requires_the_projects_declared_pass_record_for_the_tip_it_merges_RESULT.md`.
