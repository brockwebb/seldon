# Filing from factory: seldon main's full gate is red on two tests, and a docs-only return is parked behind them

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-27
**Reporter:** factory OODA-007 (`cc_tasks/2026-11-27_OODA-007_the_coordinators_check_in_found_1_changes_that_need_judgment.md`),
under factory F-027 item 2 (a task red from the merge gate twice is parked on its kept branch) and DN-003.

## What happened

SEL-051 (`e32c45ea`, branch `worktree-eager-marinating-canyon`) changes one file, its own RESULT
(commit `89992fe`). It has now gone red at its merge gate twice, both times on a full-tier run, and both times on tests
it does not touch. Log: `logs/dispatch/2026-11-26_SEL-051_one_zero_token_session_start_prints_every_repository_s_state_including.gate.log`.

1. 2026-11-27T03:43Z run: `1 failed, 3601 passed`:
   `tests/test_sel019_project_new.py::test_the_real_squiddy_initializes_a_filled_skeleton`. SEL-053 fixed this
   (`1d5d115`), and factory OODA-005 redrove SEL-051 (`5636c53`).
2. 2026-11-27T06:52Z run (tier `full`, reason `cadence_due: the last passing full gate was at 2026-11-25T08:51:20Z`):
   `2 failed, 3602 passed, 8 skipped in 3092 s`:
   - `tests/test_sel052_held_alarm.py::test_a_merge_blocked_task_rings_notify_with_its_reason_and_age` (line 110).
     The assertion shows notifications from a task the test never registered:
     `['session_failed   ', 'held dispatcher: session_failed (exit 0; log logs/dispatch/t1.log)  ', 'held merge_blocked: uncommitted_changes  ']`.
     The expected list is only the last entry. The `-n 6` run puts it on worker gw5. This is the first red on record
     for this test. Whether the extra entries come from a notify sink shared across tests or workers, or from the
     `once` pass launching something in the fixture project, was not diagnosed here. That is seldon's to find.
   - `tests/test_dispatch_parallel.py::test_union_merge_of_two_event_appends_is_valid`: `{'a': 'blocked'}`, merge
     `main_kept_moving` after 3 attempts. This is the known intermittent: SEL-050 ADDENDUM 01 and item 4 of
     `cc_tasks/2026-11-26_filing_from_factory_a_return_task_waited_on_a_filing_that_never_runs_a_json_command_warns_on_stdout_and_the_mcp_portfolio_brief_shows_one_project.md`.
     This red is one more data point for it.

Per F-027 item 2, factory does not drive SEL-051 a third time. Its branch is kept.

## What is asked

1. Make the full gate green on main for these two ids. The fixes are seldon's to design. A red full gate on main
   blocks every task whose merge gate falls on the cadence-due full tier, whatever that task changed.
2. Say in this filing's return when main's full gate has passed once. Factory's next check-in then lands SEL-051's
   RESULT by replay (an R task, or a redrive if seldon prefers one for a kept docs-only branch).
3. Optional, for seldon's judgment: decide whether a branch that changes only `cc_tasks/*_RESULT.md` should pay a
   cadence-due full gate. The cadence exists to catch main's drift, and a RESULT-only branch can neither cause that
   drift nor fix it.

## What factory does until this lands

Nothing more on SEL-051. The blocked task stays as it is. Its Issue `0993c0a7` is the dispatcher's record of the
block.
