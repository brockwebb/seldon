# ADDENDUM 01 to 2026-11-27_SEL-055_the_gate_runs_what_a_change_can_break_and_no_queue_waits_an_hour_for_a_one_line_change: lane merges are a new caller of the merge gate

**Author:** OODA knowledge source on 5ef8838d (AD-038-R16)
**Source:** `cc_tasks/2026-11-27_SEL-054_four_things_the_factory_needs_from_the_dispatcher_are_built_RESULT.md`,
AD-038 ADDENDUM 16 (R40, R41), `seldon/commands/dispatch_worktree.py` merge round (read at HEAD `b722297`).

SEL-054 merged before this task. Its premise still holds. No Part is false, but SEL-054 changed what the merge
gate serves in three ways that this task must account for.

## 1. A lane branch now goes through the merge gate

Under R40 and R41, a coordination-lane task (factory's OODAs, `^OODA-\d+`) runs beside an exclusive build. Its
branch may change only the lane's declared `writes` (for factory, `cc_tasks/**` and `for_operator/**`). The merge
round checks that first (`lane_wrote_outside`) and then reaches the same AD-034-R26 evidence check as any branch.
If the branch has no evidence, the round runs the project's full `dispatch.gate_command`. As it stands, an
addendum-only lane branch can therefore run the full gate, which is about an hour on hazbrief. This is the
"one-line change" case in this task's title, and SEL-054 has made it a regular event.

- **Part A:** the AD-034 addendum states how a lane branch is classified. A branch whose changed paths R41 has
  already confined to declared non-code `writes` is a change the selector can classify. Say what it runs (it may
  be nothing beyond the record), and state that rule; do not leave lane branches as an unstated exception.
- **Part B:** cover the lane path in the tests: a lane branch with no gate evidence merges on the selected gate,
  and the record names which gate ran. If any lane-task merges exist in either repository's last twenty merges,
  include them in the measurement.

## 2. `merge_wait_s` was sized to the gate time this task shortens

A lane supervisor waits up to `dispatch.coordination_lane.merge_wait_s` for the pass lease when it finishes. The
default is 14,400 s, and SEL-054's RESULT says it has "no measured basis, chosen to exceed FAC-31's ninety
minutes". In the RESULT, report the measured selected-gate and full-gate times next to that default. Do not change
the default unless a measurement supports the new value (AD-038-R40 owns it).

## 3. Smaller items

- **Serial transcript fixture.** SEL-054 re-recorded `tests/fixtures/dispatch_serial_transcript.txt`: `limits_tried`
  now joins the first launch's record commit, making 5 lines. Re-record it against that version only for a change
  this task intends, and name the change in the RESULT.
- **One more filing to read.** Read `cc_tasks/2026-11-27_filing_from_factory_seldon_main_full_gate_is_red_on_two_tests_and_sel051_is_parked.md`
  with the four filings this task already lists. SEL-054 did not answer it, and SEL-053's RESULT does not cite it.
  It is evidence for the scheduled full-suite backstop in Part A. Return to it in Part C only if this task's work
  answers it.
- **Known flake.** In SEL-054's related-suite run, `test_dispatch_parallel.py::test_union_merge_of_two_event_appends_is_valid`
  failed under load (`main_kept_moving`, Issue `88c9f4d8`). The test passed when run alone. When this task
  measures a selected gate on seldon, do not count that test's intermittent failure as a selection miss.
