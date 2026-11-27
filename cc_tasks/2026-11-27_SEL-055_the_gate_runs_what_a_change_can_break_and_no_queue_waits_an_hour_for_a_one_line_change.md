# SEL-055: the gate runs what a change can break, and no queue waits an hour for a one-line change

**Status:** proposed
**Author:** the factory coordinator (FCT-7, a Desktop session), 2026-11-27 06:05 EST. Second of today's two seldon tasks.
**Repo:** seldon. L4: commit on the task branch; the dispatcher merges.
**After:** 2026-11-27_SEL-054_four_things_the_factory_needs_from_the_dispatcher_are_built
**What is known before this starts (nothing re-measured by Desktop).** Read each in full first, and find SEL-041 and its state (hazbrief reported it "is not on main").
- `cc_tasks/2026-11-21_filing_from_hazbrief_the_gate_is_one_command_per_repository_and_ran_in_full_for_a_one_slide_change.md`
- `cc_tasks/2026-11-24_filing_from_factory_seldons_merge_gate_holds_every_queue_and_the_portfolio_order_is_gate_first.md`
- `cc_tasks/2026-11-24_filing_from_hazbrief_hb218_cannot_be_applied_sel041_is_not_on_main.md`
- `cc_tasks/2026-11-24_filing_from_hazbrief_a_parts_check_line_is_not_read_a_blocked_merge_was_completed_ungated_and_a_lease_wait.md`
- hazbrief-mcp `cc_tasks/2026-11-24_HB-230_can_a_code_changes_blast_radius_be_measured_and_trusted_RESULT.md` and factory `docs/evaluations/2026-11-21_pytest-testmon.md`.
- The operator, 2026-11-26: hazbrief ran 8,000-plus tests on every small change, "where he wanted tests within the blast radius of the change"; his correction was itself misread. factory F-027 sets a 30-minute target; on 2026-11-27 hazbrief's last gate took 56 minutes for 8,508 tests and seldon's own full gate was red on main for part of the night (SEL-053).
**Governing:** AD-034 (the merge gate, R18, R26), AD-038, factory F-022 and F-027 as the consumer's requirement. The change is a decision: an AD-034 addendum with prior art and a register record, `seldon prior-art verify` passing before code.
**Prior art:** hazbrief HB-230's measurement and the pytest-testmon evaluation are held; use them. From memory and UNVERIFIED unless confirmed and cited: regression test selection (Rothermel and Harrold 1997, safe selection); Google's TAP and Bazel's affected-target testing; the full suite run on a schedule as the backstop to selection.
**Spend:** est. 1.7M tokens. Basis: SEL-052 class; a launch-path change with a measured comparison.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.25, B 0.5, C 0.25.
**Premises:**
- premise: the gate filing is on main | check: test -f cc_tasks/2026-11-21_filing_from_hazbrief_the_gate_is_one_command_per_repository_and_ran_in_full_for_a_one_slide_change.md

Glob and read every sibling `*SEL-055*ADDENDUM*.md`. Other repositories are read by path and never written.

## Part A: what exists, and the decision

Say where SEL-041's work is (a kept branch, parked, partly merged) and land or replace it. The decision the coordinator has made, to be corrected by the evidence: a project may declare a selected gate (the tests a change can affect, by a declared selector) for the merge round, with the full suite as a scheduled run whose red result stops the project's merges and raises it; a change the selector cannot classify runs the full suite; the record says which gate ran and why.

Acceptance:
- `check: sh -c "git log --oneline main..HEAD -- docs | grep -q ."` passes.

## Part B: built and measured

Build it in the dispatcher. Measure on seldon itself and, read-only on a copy, on hazbrief-mcp: for the last twenty merged tasks of each, what the selected gate would have run and how long, against the full suite; and for five seeded breaking changes each, whether the selected gate catches them. A selection that misses a seeded break is a finding that stops the rollout for that repository.

Acceptance:
- `check: sh -c "git log --oneline main..HEAD -- tests | grep -q ."` passes.

## Part C: returned

RESULT with `## For the consumer` for hazbrief-mcp and factory: the `seldon.yaml` lines to declare, the measured times, and the misses if any. `seldon cc return` for each filing answered.

Acceptance:
- `check: sh -c "grep -q '^## For the consumer' cc_tasks/2026-11-27_SEL-055_the_gate_runs_what_a_change_can_break_and_no_queue_waits_an_hour_for_a_one_line_change_RESULT.md"` passes.
