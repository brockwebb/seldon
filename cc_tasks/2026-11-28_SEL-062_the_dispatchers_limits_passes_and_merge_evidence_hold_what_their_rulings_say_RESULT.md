# RESULT: SEL-062, the dispatcher's limits, passes and merge evidence hold what their rulings say

**Task:** `cc_tasks/2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say.md`
(`67146282`). **Branch:** `worktree-snuggly-crunching-walrus`. Not merged or completed here; the dispatcher merges on
green and completes.
**Addenda:** none existed (`*SEL-062*ADDENDUM*.md` matched nothing).
**Findings:** REVIEW-001 F-05 to F-22, 18 Issues. All 18 are `fixed`, each with `REMEDIATED_BY` this task, its tests
as `VERIFIED_BY`, and the ruling it changed as `CHANGES` where that ruling's record is projected.
**Decisions:**
- AD-038 ADDENDUM 17: amends R40, R43, R44 and R45, and adds R46.
- AD-034 ADDENDUM 15: amends R26, R38, R39 and R41.
- AD-037 erratum 01: amends R23's default.
- Ten pending register records. `seldon decision check`: clean.
- `seldon prior-art verify` passed on both addenda before any code commit (ledger events `ca4354e6`, `4f05cba8`).
- PL-018 records the deferred OS-enforced deny.

**Commits:**
- `1c38f86`: red tests. 31 of 39 failed at HEAD and Part C did not import; the 8 that passed are controls.
- `90f8dd2`: the notes and records.
- `ac8e20a`: Part A.
- `604872a`: Part B.
- `c27a3d3`: Part C.
- `47429e4`: the Issue trace.

Recall used: none. Of the eight hits I opened only the SEL-055 RESULT, and only to grep how it ran `prior-art verify`
before its code. That was the procedure I had already planned, so it changed nothing. The other hits (the SEL-054
RESULT, SEL-041/043 kept trees, AD-038-R16, AD-034-R39/R41, AD-036-R13) were not opened. The inputs were the task
file, REVIEW-001's `review.md` and `findings.yaml`, AD-038 ADDENDUM 16, and the code at `2c0f861`.

## Part A: the limits and their controls (F-05, F-06, F-22)

| Finding | Fix | Ruling | Tests (`tests/test_sel062_part_a.py::`) |
|---|---|---|---|
| F-05 | A plant the harness could not run (an `OSError`, a timeout over `HOOK_TIMEOUT_S`, or the spend inspector raising) is `untried`, not `refused: False`. It refuses its own pass as `limit_control_untried` and the next pass tries again; a real go-through still latches. `seldon dispatch controls` writes the state a pass reads (`_record_limits`, shared with the gate) and exits 3 on untried. The fingerprint adds a sha256 of `controls.py`, `dispatch_stations.py` and `stations.py`. One `limits_tried` per fingerprint and outcome. | R45 amended | `..._a_harness_error_is_an_untried_control...`, `..._a_harness_error_refuses_its_pass_and_the_next_pass_tries_again`, control `..._a_limit_that_went_through_still_latches...`, `..._the_controls_command_writes_the_state_a_pass_reads`, `..._the_fingerprint_covers_the_code...` |
| F-06 | `controls.refusal` now resolves a file tool's path against the call's cwd, a search tool's root (Grep, Glob, LS) when it is the guarded directory or a parent of it, an absolute Glob pattern's prefix, and a Bash command's words after `shlex` (quote-split names, redirections, `--flag=value`, `~` and variables expanded, relative words resolved through the command's own `cd`s). The raw-text spellings still run too. Each guarded path is tried with five plants: `canonical_read`, `canonical_cat`, `cd_relative`, `quote_split` and `search_parent`. | R44 amended: a denylist, not complete mediation | the 10 probe spellings refused, 5 neighbours allowed; `..._the_probe_spellings_are_planted_controls`; control of the control `..._a_guard_that_misses_one_spelling_fails_its_control` (a text-only hook lets `cd_relative` through) |
| F-22 | `hive.record` keeps a failed mint's exit, its stderr's length and its 12-character sha256. It never keeps the text, which goes to the dispatcher's stderr only. | R43 amended | `..._a_failed_mints_stderr_never_reaches_the_recorded_event` |

**F-06, the decision the task asked for.** I narrowed R44's claim. I did not adopt an OS-enforced deny now. Read on
2026-11-28 (code.claude.com/docs/en/sandboxing), Claude Code's sandbox:
- covers Bash only. Read, Grep, Glob and Edit follow permission rules, so the complete form also needs `Read(//...)`
  deny rules;
- confines Bash writes to the worktree and a temp directory, while `part-complete` writes the primary's store and
  `cc file` writes other repositories;
- starts network empty.

That changes every dispatched session on the machine, and it needs a sandboxed pilot dispatch that an exclusive
session cannot launch. It is PL-018. The OS-enforced form would also become the Network line's first enforced limit.

## Part B: the passes (F-07, F-09 to F-15, F-17, F-18, F-20)

- **F-15, the root of F-07 and F-13.** One evaluation stage and one alarm stage, AD-038-R46:
  - `dispatch.evaluate_queue` (band, c13, c15, union, cross-waits, OODA, FIFO with the lane, the lane's c6) is
    called by the serial pass, the parallel pass, the lane's look and both status views.
  - `dispatch.pass_alarms` (last pass, stuck streak, held alarm) is called by both passes.
  - `dispatch.review_launches` (station (a)) is called by both passes and the lane.

  Reading the code showed more drift than the review named. The parallel pass also lacked c13, c15 and station (a)'s
  premise review, not only the held alarm. No consumer runs `max_parallel > 1` today, so none of it had rung.

  The reason not to fold the serial pass into the parallel one is in R46: the serial transcript fixture holds the
  serial pass to the pre-SEL-004 dispatcher, and the in-place launch keeps the pass lease for the session where a
  worktree launch hands it to a supervisor.

  Tests:
  - `test_part_b_the_held_alarm_rings_in_the_parallel_pass_too`
  - `..._every_pass_and_status_view_evaluates_through_one_stage`
  - `..._the_parallel_pass_applies_c13_and_c15_as_the_serial_pass_does`
  - `..._the_status_views_order_the_lane_first_as_the_pass_does`
- **F-10.** In `plan_launches`, a lane task's declaration for every hold except the exclusive one is its lane's
  `writes`. It waits as `overlap` on a non-exclusive task, running or waiting, that touches them, and running or
  waiting it holds them. Tests: two overlap tests, plus the control that a lane task still runs beside an exclusive
  build and holds only its writes.
- **F-09.** Lane membership by name is kept. Nothing a filer sets is attested here: `--actor` is free text. ADDENDUM
  16 §4's "no task file can put itself in the lane" is withdrawn in R40's amendment. What bounds a self-named lane
  task is R41's `writes`, F-10's overlap and the slots. Verified by F-10's test.
- **F-11.** The serial pass runs `GATE.maybe_run` only with no lane session in flight. Test:
  `..._no_scheduled_gate_starts_while_a_lane_session_is_in_flight`, with the control that the schedule is asked once
  nothing is in flight.
- **F-12.** `maybe_run` records any other exception as `gate_scheduled_error`, prints it, and returns None.
- **F-14.** The comment now says an exclusive task launches alone apart from lane tasks.
- **F-17.** `events.pass_scope()` wraps `dispatch once`'s pass. Inside it the store is parsed once while it is
  unchanged. An append whose old bytes still hash the same (blake2b over the prefix) is parsed as its tail. Any other
  change is parsed in full, and a line still being written is never extended. Each caller gets copies of the list,
  each event and each payload.
  - Measured on the live store (20,250,081 bytes, 14,938 events): one parse takes 0.10 s, so the saving is about a
    second per pass. The finding's cost was real but small.
  - Tests: one parse while unchanged, a tail parse on append (the result equals an uncached read), a mutation that
    does not leak, a rewritten store parsed again, and a whole `once` pass with `full == 1`.
- **F-18.** `seldon dispatch status` shows `full gate: <time> (<outcome>), <age> ago, ok|due|overdue` against both
  thresholds (`gate_plan.full_gate_age`, the same anchor as `scheduled_due`), and `--json` carries `full_gate`.
- **F-20.** AD-037 erratum 01. Measured by `/tmp/sel062/windows.py` over five stores:
  - seldon's full merge gates ran p50 4,854 s and max 5,788 s (n=5);
  - hazbrief-mcp's first sightings of a held window ran p50 1,840 s and p90 8,158 s (n=35).

  Twelve passes (3,600 s) rang inside normal windows. The default is now 25 passes, the first past the 7,200 s gate
  timeout that seldon and hazbrief-mcp declare (`PRODUCER_WINDOW_BOUND_S`). `dispatch status` prints every effective
  threshold (`alarms: ...`; `stuck_thresholds` in `--json`).

## Part C: merge and completion evidence (F-08, F-16, F-19, F-21)

- **F-08 (R26 amended).** A Stop gate check whose whole command tests that the task's own RESULT exists is not
  evidence (`dispatch_worktree.evidential_check`). `_gate_reading` records `checks_evidential`, and `gate_evidence`
  counts only that. A reading recorded before this change, which has no `checks_evidential`, is read by its
  `checks_run`. `seldon cc return` no longer writes the check.
  - Consequence, by R26: a return in a project with no `gate_command` is now blocked `ungated`, as any task there
    is. critical-thinking-ai is the known case (SEL-052's CTAI-008). Its remedy is declaring a gate.
  - `tests/test_sel052_returns.py`'s assertion is inverted to match the new template.
- **F-16 (R41 amended).** The guard is on the transition. `artifacts.plan_task_transition` calls
  `completion_gate.guard` for every move into `completed`, so `task close`, `task update`, `cc complete` (CLI and
  MCP) and any walk meet it.
  - The dispatcher's merge completion passes `completion={"by": "merge", ...}`. `cc complete --ungated` passes
    `{"by": "ungated", ...}`.
  - R41's code moved from `commands/cc.py` to `core/completion_gate.py`, and `cc` re-exports `r41_completion` and
    `blocked_since_launch`.
  - The guard now records `completion_gate` and `completed_ungated` with the move, so the CLI and the MCP tool no
    longer write them in their stamp.
  - R45's own state file is kept, with the reason in ADDENDUM 15 §4: it holds a tried fingerprint, not a streak.
- **F-19 (R39 amended).** `gate_evidence` marks a declared pass record `scoped` by its declaration's `tree_paths`. A
  scoped record neither stands under a red main's closure (`closure_admits`) nor ends it (`_merged_on_full_pass`). A
  whole-tree record still does both (control test).
- **F-21 (R41 amended).** A held task also needs its own dispatch branch on main. The branch is the newest one named
  by its `dispatch_worktree_named`, `dispatch_finished` or `worktree_kept` record. On main means every commit's patch
  is there (`git cherry`, so a cherry-pick or rebase counts). A branch that no longer resolves cannot be shown on
  main, and `--ungated` is the remedy. The test refuses with `branch_not_on_main` naming the branch, then passes after
  a cherry-pick and a new full gate.

## Other tests changed

- `tests/test_sel040_addendum_files_and_launch_premises.py::test_the_dispatcher_re_checks_every_premise_at_launch_today`
  reads source. It now follows `_pass → review_launches → _premise_review`.
- `tests/fixtures/dispatch_serial_transcript.txt` was re-recorded. Its word diff is only the `limits_tried` line
  (`by`, `retry`, `spec.code`), plus the `<HEX-n>` renumbering that one new hex value causes.

## Suite

The project's gate command, `pytest tests/ -q -p no:cacheprovider -n 6` under dotenv with `PYTHONPATH=.`, ran on
this branch at `c27a3d3` (Part C's commit; the Issue trace commit after it touched only the event store). Result:
**1 failed, 3,788 passed, 8 skipped in 2,291 s**.

The one failure is `tests/test_dispatch_parallel.py::test_union_merge_of_two_event_appends_is_valid`. It ended
`merge_blocked: main_kept_moving` on task `a` after 3 attempts. That is the load behaviour SEL-049, SEL-054 and
REVIEW-001 recorded for this test (Issue 88c9f4d8). This branch changed the parallel pass, so it was rerun alone: 1
passed in 50.0 s.

Earlier, the related suites (`test_dispatch*`, `test_sel04*`, `test_sel05*`, `test_sel022*`; 569 tests) ran at Part
B's commit. Two failed, and both were answered:
- `test_sel040...re_checks_every_premise_at_launch_today` reads source; it now follows the new call chain.
- `test_dispatch_stuck_and_journal::test_a_project_with_no_dispatch_block_is_left_alone` is the known false failure
  while `seldon/` holds an uncommitted file. Mine was the new `completion_gate.py`. It passed in the full run above.

## Spend

- Part A's boundary: 341,339 tokens against a 0.4 share of 1.5M (600K).
- Part B's boundary: 421,926 cumulative.
- Part C's boundary: 445,973 cumulative against the 1.5M estimate. The estimate's 1.5M was about three times what
  the work took.
- The final figure is the dispatcher's.

## Open, for the operator or a later task

- **PL-018, the OS-enforced deny:** needs a sandboxed pilot dispatch filed as its own task.
- **critical-thinking-ai:** declares no `dispatch.gate_command`, so its returns now block `ungated` (R26 as amended).
  This is a consequence, not a regression.
- **R23's threshold:** re-read when the `scheduled` call site has its own distribution (no scheduled run is on record
  yet).
