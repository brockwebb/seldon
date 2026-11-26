# SEL-047 evidence: seldon's gate time measured before anything changes

Task: `cc_tasks/2026-11-25_SEL-047_the_gate_time_measured_before_anything_changes_the_two_load_failures_serial_against_parallel_pa002_and_what_the_slices_miss.md`
(task `5ca015e0`). Measured on main at `e42c25b` (the worktree's base). Nothing under `seldon/`, `tests/`, or
`seldon.yaml` was changed. Zero model calls, no network.

Files:

| file | what it holds | written by |
|---|---|---|
| `gate_plan_primary.txt` | Part A: `seldon gate plan` (text and `--json`) from the primary, then `--base main` in this worktree | `scripts/plan_primary.py`, then the shell |
| `runs.jsonl` | Part B: one line per pytest run (the task's fields, plus `summary`, `exit_code`, `timed_out`, `log_trimmed`) | `scripts/runs.py` (launched by `scripts/launch.py` under `caffeinate -i`) |
| `logs/` | Part B: one log per run, trimmed to failures and summary when over 2 MB (its line says so; none was). `*.log` is gitignored (`.gitignore` line 131), so these were added with `git add -f`: they are the evidence the ledger's `log` field names | `scripts/runs.py` |
| `pa002_probe.json`, `pa002_probe2.json` | Part C: what the live-library test compares, side by side | `scripts/pa002_probe.py`, `scripts/pa002_probe2.py` |
| `slice_misses.json` | Part D: one row per task merge since 2026-10-25 | `scripts/slice_misses.py` |
| `scripts/part_d_table.py` | Part D: the table below, from `slice_misses.json` | |

## Part A

From the primary (`$SELDON_PRIMARY_CHECKOUT`, HEAD `e42c25b`), the first run since SEL-045R landed:

    gate plan against main (fork e42c25bc, tree 52849cfa, DIRTY): scoped: 0 of 205 test files; declared_none: every changed path matched a slice declared `tests: none`
      slice event_store: 1 path(s): seldon_events.jsonl

The primary differs from main only by its event store, which is unflushed dispatcher lines. That path is in the
`event_store` slice (`tests: none`), so the primary plans scoped with zero tests. In this worktree, after Part D's
files existed: `scoped: 23 of 205 test files; scoped: documents`, the premise of this task's cost holds. The cadence
did not turn it full: the last passing full gate is SEL-044's merge gate at 2026-11-25T08:51:20Z.

## Part B

All runs used the worktree's code and the primary's credentials, the way `gate_command` does:
`python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest -p no:cacheprovider -p no:randomly -v ...`.
The full runs add `--deselect` for pa002's live-library test, and the parallel runs add `-n 6`.

`-p no:randomly` matters because pytest-randomly 3.16.0 is installed in this interpreter. The real `gate_command`
does not pass `-p no:randomly`, so every gate runs in a fresh random order. These runs fix the order, so each log is
the true order, the delta debugging is reproducible, and every polluter search below uses it.

Rows are on `runs.jsonl` (59 lines: 44 planned runs plus 15 polluter-search replays). No run spanned a machine
sleep. The Mac went into clamshell sleep on battery at 14:07 and woke after about 50 minutes; the one run it
interrupted (`alone_test_dispatch_parallel_10`, first attempt) was killed unrecorded and run again from scratch, and
from then on `runs.py` flags any run whose wall-clock span exceeds its monotonic seconds.

**The machine was not quiet, and the record says so.** hazbrief-mcp's HB-230 ran its own suites from
`/tmp/hb230/{root,pre}/hazbrief-mcp` at `-n auto --maxprocesses 6` and `-n 3 -m load_sensitive` for most of the
afternoon. The 1-minute load average ranged from 3 to 99 across these runs.

`pgrep -f pytest`, the task's process count, does not see xdist workers: execnet starts them as
`python -c import sys;exec(eval(...))`. So from run 6 of the first file, every line also records
`xdist_workers_before/after` and `other_suites_before/after` (each other `-m pytest` process with its working
directory, from `lsof`).

### Alone, 20 serial runs per file

| file | runs | runs with a failure | failing test ids (count) | wall s (min / median / max) | 1-min load before (min to max) | other suites' xdist workers before (min to max, measured from run 6) |
|---|---|---|---|---|---|---|
| `test_sel024_gate_record.py` | 20 | 16 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` (16) | 210 / 337 / 454 | 6.61 to 59.87 | 6 to 14 |
| `test_dispatch_parallel.py` | 20 | 4 | `test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` (3); `test_union_merge_of_two_event_appends_is_valid` (2) | 462 / 649 / 852 | 6.47 to 99.38 | 0 to 9 |

### Per alone run

| run | wall s | load before (1/5/15 min) | load after | other xdist workers before / after | failed |
|---|---|---|---|---|---|
| test_sel024_gate_record_01 | 210 | [6.61, 5.0, 4.7] | [10.72, 7.71, 5.9] | - / - | - |
| test_sel024_gate_record_02 | 226 | [10.72, 7.71, 5.9] | [9.86, 9.03, 6.9] | - / - | - |
| test_sel024_gate_record_03 | 237 | [9.86, 9.03, 6.9] | [8.24, 9.26, 7.55] | - / - | - |
| test_sel024_gate_record_04 | 341 | [8.24, 9.26, 7.55] | [54.46, 35.66, 20.12] | - / - | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_05 | 454 | [54.46, 35.66, 20.12] | [61.94, 70.52, 45.52] | - / - | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_06 | 415 | [59.87, 69.95, 45.46] | [58.86, 65.15, 52.34] | 14 / 14 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_07 | 402 | [58.86, 65.15, 52.34] | [45.42, 52.38, 50.85] | 14 / 14 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_08 | 339 | [45.42, 52.38, 50.85] | [15.0, 27.79, 39.73] | 14 / 8 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_09 | 306 | [15.0, 27.79, 39.73] | [12.57, 17.91, 31.46] | 8 / 8 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_10 | 308 | [12.57, 17.91, 31.46] | [9.37, 13.23, 25.19] | 8 / 8 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_11 | 325 | [9.37, 13.23, 25.19] | [11.69, 11.74, 20.7] | 8 / 8 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_12 | 356 | [12.04, 11.81, 20.67] | [16.15, 14.15, 18.76] | 8 / 8 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_13 | 366 | [16.15, 14.15, 18.76] | [22.08, 17.85, 18.7] | 8 / 8 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_14 | 332 | [22.08, 17.85, 18.7] | [18.15, 16.54, 17.6] | 8 / 6 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_15 | 351 | [18.15, 16.54, 17.6] | [17.33, 16.13, 16.9] | 6 / 6 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_16 | 352 | [17.33, 16.13, 16.9] | [16.07, 14.77, 15.87] | 6 / 8 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_17 | 347 | [16.07, 14.77, 15.87] | [12.53, 14.17, 15.36] | 8 / 6 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_18 | 335 | [12.53, 14.17, 15.36] | [10.0, 12.84, 14.51] | 6 / 6 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_sel024_gate_record_19 | 260 | [10.0, 12.84, 14.51] | [8.78, 10.57, 13.05] | 6 / 6 | - |
| test_sel024_gate_record_20 | 234 | [8.78, 10.57, 13.05] | [11.76, 10.97, 12.56] | 6 / 3 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| test_dispatch_parallel_01 | 472 | [11.76, 10.97, 12.56] | [8.99, 11.21, 12.25] | 3 / 3 | - |
| test_dispatch_parallel_02 | 486 | [8.99, 11.21, 12.25] | [6.68, 8.73, 10.62] | 3 / 0 | - |
| test_dispatch_parallel_03 | 490 | [6.47, 8.65, 10.58] | [11.86, 10.03, 10.29] | 0 / 6 | - |
| test_dispatch_parallel_04 | 705 | [13.63, 10.42, 10.43] | [18.03, 14.82, 12.54] | 6 / 6 | - |
| test_dispatch_parallel_05 | 791 | [18.03, 14.82, 12.54] | [22.32, 18.1, 15.26] | 6 / 6 | - |
| test_dispatch_parallel_06 | 580 | [22.32, 18.1, 15.26] | [8.54, 12.58, 13.81] | 6 / 3 | - |
| test_dispatch_parallel_07 | 462 | [8.18, 12.44, 13.75] | [10.93, 10.79, 12.31] | 3 / 3 | - |
| test_dispatch_parallel_08 | 662 | [10.93, 10.79, 12.31] | [12.99, 12.47, 12.39] | 3 / 6 | - |
| test_dispatch_parallel_09 | 655 | [12.99, 12.47, 12.39] | [16.56, 19.68, 16.46] | 6 / 6 | `test_union_merge_of_two_event_appends_is_valid` |
| test_dispatch_parallel_10 | 651 | [99.38, 61.41, 35.92] | [10.27, 19.99, 26.27] | 6 / 6 | `test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` |
| test_dispatch_parallel_11 | 555 | [10.27, 19.99, 26.27] | [7.42, 10.93, 18.28] | 6 / 3 | - |
| test_dispatch_parallel_12 | 466 | [7.42, 10.93, 18.28] | [9.65, 9.65, 14.44] | 3 / 3 | - |
| test_dispatch_parallel_13 | 554 | [9.65, 9.65, 14.44] | [18.16, 16.64, 15.64] | 3 / 6 | - |
| test_dispatch_parallel_14 | 730 | [18.16, 16.64, 15.64] | [47.76, 28.05, 23.26] | 6 / 6 | `test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` |
| test_dispatch_parallel_15 | 754 | [47.76, 28.05, 23.26] | [16.83, 28.83, 29.22] | 6 / 6 | `test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge`, `test_union_merge_of_two_event_appends_is_valid` |
| test_dispatch_parallel_16 | 706 | [16.83, 28.83, 29.22] | [18.55, 19.04, 22.98] | 6 / 9 | - |
| test_dispatch_parallel_17 | 852 | [18.55, 19.04, 22.98] | [26.21, 28.42, 27.48] | 9 / 9 | - |
| test_dispatch_parallel_18 | 822 | [26.21, 28.42, 27.48] | [17.63, 32.64, 36.55] | 9 / 6 | - |
| test_dispatch_parallel_19 | 521 | [17.63, 32.64, 36.55] | [15.16, 18.35, 26.9] | 6 / 3 | - |
| test_dispatch_parallel_20 | 647 | [15.16, 18.35, 26.9] | [26.41, 23.98, 24.92] | 3 / 6 | - |

### Full suite

| run | wall s (min) | passed | failed | errors | summary | load before / after (1-min) | other xdist workers before / after | failed ids |
|---|---|---|---|---|---|---|---|---|
| full_serial_1 | 7463 (124.4) | 3558 | 1 | 0 | 1 failed, 3558 passed, 7 skipped, 1 deselected in 7460.94s (2:04:20) | 26.41 / 8.2 | 6 / 3 | `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| full_n6_1 | 2193 (36.6) | 3557 | 2 | 0 | 2 failed, 3557 passed, 7 skipped in 2191.15s (0:36:31) | 7.86 / 11.23 | 3 / 6 | `test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge`, `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| full_n6_2 | 2269 (37.8) | 3556 | 3 | 0 | 3 failed, 3556 passed, 7 skipped in 2264.77s (0:37:44) | 11.23 / 13.19 | 6 / 3 | `test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge`, `test_dispatch_status_reads_the_cap_from_a_worktree`, `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |
| full_n6_3 | 2508 (41.8) | 3555 | 4 | 0 | 4 failed, 3555 passed, 7 skipped in 2507.09s (0:41:47) | 13.19 / 11.15 | 3 / 6 | `test_a_killed_supervisor_is_marked_by_the_next_pass_and_its_worktree_kept`, `test_an_exclusive_task_waits_for_running_ones_and_blocks_new_ones`, `test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge`, `test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` |

Sleep-spanned attempts on the ledger, excluded above and run again: 0.

### Serial against `-n 6` (item 4)

| | this task | earlier figures |
|---|---|---|
| serial (`gate_command` as it stands) | **7,463 s (124 min)**: 3,558 passed, 1 failed | merge gates 2026-11-25: 5,176 s (red), 4,854 s and 5,788 s (`gate_run`, 81 to 96 min); SEL-041's run was killed at 3,600 s with 73% done |
| `-n 6` | **2,193 s, 2,269 s and 2,508 s (37 to 42 min)**: 2, 3 and 4 failed | SEL-042: 25:40 and 25:51; SEL-041: about 29 min |

On the same afternoon, under the same neighbour, `-n 6` was 3.0 to 3.4 times faster than serial. Both took longer
than their earlier figures: the serial run by 1.3 to 1.5 times the night-time merge gates, the parallel runs by 1.4
to 1.6 times. Those earlier figures came from quieter hours.

**The serial run outlasted `dispatch.gate_timeout_s` (7,200 s) by 263 s.** Run by the merge round today, it would
have timed out (`regate_red`).

**Tests that failed at `-n 6` and not serial**:

- `test_dispatch_parallel::test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` (3 of 3 `-n 6` runs).
- `test_sel018_relative_dispatch_paths::test_dispatch_status_reads_the_cap_from_a_worktree` (1 of 3).
- `test_dispatch_parallel::test_an_exclusive_task_waits_for_running_ones_and_blocks_new_ones` (1 of 3).
- `test_dispatch_parallel::test_a_killed_supervisor_is_marked_by_the_next_pass_and_its_worktree_kept` (1 of 3).

**The reverse:** none. The serial run's one failure, the `lock_wait` test, also failed in all three `-n 6` runs. No
other test id failed in any run.

### Classification (item 5, iDFlakies' scheme, Lam et al. ICST 2019, from what was observed only)

**`test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing`:
non-order-dependent.**

- It failed **alone in 16 of 20 runs (80%)**, and in all 4 full runs. The other 23 tests in its file passed every
  time.
- The 4 alone passes were runs 1 to 3 (load 6.6 to 10.7, before HB-230's suites started) and run 19 (load 10.0).
- Every failure has the same form: `gate_running_at_end: False`, "the filing landed mid-gate".
- The mechanism is a fixed time budget. The test's `RECORDER` writes `started`, sleeps `GATE_SLEEP_S = 6`, then
  writes `ended`. The filer thread must finish a whole `F.file_task` inside those 6 s: a git commit through seldon's
  commit hooks, each a fresh `python -m seldon` process, plus Neo4j writes.
- Under CPU contention the filing takes longer than 6 s. That is Luo et al.'s (FSE 2014) "async wait" class: a
  sleep standing in for a synchronisation. "Load" is the right word for the trigger, but the defect is the fixed
  window.

**`test_dispatch_parallel.py`: non-order-dependent for the two ids that failed alone. The other two ids that failed
only in a suite run were not reproduced by order.**

- `test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` failed **alone in 3 of 20 runs (15%)**
  and in all 3 `-n 6` runs (passed serial). It asserts that the two stub sessions overlap. Each stub sleeps 3 s
  (`write_stub(..., "sleep": 3)`), so b's launch must begin within about 3 s of a's.
  Alone run 10 shows it missing: a ran 8.4 s, and b started 0.21 s after a ended. Same class: a fixed window.
- `test_union_merge_of_two_event_appends_is_valid` failed **alone in 2 of 20 (10%)**, and in no full run. The
  assertion after `_wait_settled` found task a `blocked`, not `completed`. Its message prints only the states, and
  the supervisors' logs were gone with pytest's temporary directories. **Cause not determined.**
- Together, the file had a failure in **4 of 20 alone runs (20%)**; run 15 failed both ids.
- `test_an_exclusive_task_waits_for_running_ones_and_blocks_new_ones` and
  `test_a_killed_supervisor_is_marked_by_the_next_pass_and_its_worktree_kept` each passed alone 20 of 20 and failed
  once, both in `full_n6_3`, both on worker gw5. By the scheme they are order-dependent candidates, so their worker's
  prefix was replayed.
  - In `full_n6_3`, gw5 ran 2 tests of `test_dispatch_own_record.py` and then this file's tests in file order. So the
    only predecessors new against the alone runs are those 2 tests.
  - Replaying gw5's 12-test prefix in order, in one process (`od_gw5_prefix_n6_3_{1,2,3}`), **passed 3 of 3** at
    load 7 to 12.
  - No polluter: the scheme's candidate set is exhausted, and the 45-minute cap was not needed.
  - What was observed instead is load. `full_n6_3` ran with HB-230's `-n 6` suite beside it, and the 5-minute load
    average reached 70.6. The `killed_supervisor` failure is an explicit wall-clock budget missed by 1 s:
    `assert (4495988.93 - 4495957.90) < 30`, 31.0 s.
  - The `exclusive_waits` pass printed `STUCK: ... refused as dirty_tree ...; dirty: seldon_events`, not the
    expected `waits (exclusive_waits)`.
  - Classified **not order-dependent on replay; failed once at 5-minute load above 70**. That is a result over 3
    replays, not a proof of independence.

**Not one of the two named tests, but the one order-dependent failure found:
`test_sel018_relative_dispatch_paths::test_dispatch_status_reads_the_cap_from_a_worktree`.**

- It failed in `full_n6_2` on gw0 with `json.decoder.JSONDecodeError`. `dispatch status --json` printed a line
  `waits_on: bef4e024 -> other:316500f8...: the other graph could not be read (...)` ahead of the JSON.
- It passed alone 3 of 3. Run after `test_sel008_cross_project_waits_and_block_reason.py`, which ran just before it
  on gw0, it failed on the first replay.
- Delta debugging (`scripts/od_bisect.py`; 8 replays, 97 s, the `od_bisect_*` lines) isolates **one polluter**:
  `test_sel008_cross_project_waits_and_block_reason.py::test_task_show_prints_the_edge_with_the_other_tasks_state_and_the_precedes_edges`.
- That test leaves a task with a cross-project `waits_on` edge in the shared test database. The victim takes
  `neo4j_driver` but not `clean_test_db`, so `dispatch status` reads the leftover task and warns about it on the
  output the victim parses as JSON.
- In serial order, files between the two clean the database, which is why the serial runs never saw it.
- This is iDFlakies' polluter/victim pair exactly. It is the same kind SEL-043 fixed in `tests/dispatch_scaffold.py`:
  tests sharing one database and its names.

| replay | wall s | load before | passed | failed | failed id |
|---|---|---|---|---|---|
| od_gw5_prefix_n6_3_1 | 367 | 7.4 | 12 | 0 | - |
| od_gw5_prefix_n6_3_2 | 365 | 11.56 | 12 | 0 | - |
| od_gw5_prefix_n6_3_3 | 355 | 10.63 | 12 | 0 | - |
| od_sel018_alone_1 | 6 | 7.75 | 1 | 0 | - |
| od_sel018_alone_2 | 6 | 8.09 | 1 | 0 | - |
| od_sel018_alone_3 | 6 | 7.23 | 1 | 0 | - |
| od_sel008_then_sel018_1 | 36 | 6.81 | 38 | 1 | `test_dispatch_status_reads_the_cap_from_a_worktree` |
| od_bisect_01 | 20 | 3.16 | 19 | 1 | `test_dispatch_status_reads_the_cap_from_a_worktree` |
| od_bisect_02 | 6 | 7.21 | 10 | 0 | - |
| od_bisect_03 | 19 | 6.79 | 10 | 1 | `test_dispatch_status_reads_the_cap_from_a_worktree` |
| od_bisect_04 | 11 | 5.66 | 6 | 0 | - |
| od_bisect_05 | 14 | 5.16 | 5 | 1 | `test_dispatch_status_reads_the_cap_from_a_worktree` |
| od_bisect_06 | 10 | 5.11 | 2 | 1 | `test_dispatch_status_reads_the_cap_from_a_worktree` |
| od_bisect_07 | 8 | 5.81 | 2 | 0 | - |
| od_bisect_08 | 8 | 5.76 | 1 | 1 | `test_dispatch_status_reads_the_cap_from_a_worktree` |

## Part C

**What the test exercises.** `tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index`
calls one seldon function, `seldon.core.prior_art.rebuild_release(graph, sha256, work)`. That function runs
`_release_rows` (finds the release's commit in squiddy's export register through `release_commit`, reads the corpus
manifest and the `index:` block at that commit, and reads the rows from the kit's corpus checkpoint through
`checkpoint_rows`), then `squiddy.index.build_db`, then chooses the keyed dense shard for each entry, verified by
hash and row ids. It gets its inputs from squiddy's library on disk (`pa.settings` gives
`/Users/brock/GitHub/squiddy/graphs/library`). It skips when squiddy is not importable or the served index or export
is missing.

**Which part of the assertion is about which code.** The three asserts compare seldon's rebuild output (`row_fingerprint`,
`shard_set_sha256`, `rows`) with the served index's manifest, which squiddy wrote at its last build
(`work/index/index_manifest.json`, `built_utc` 2026-11-13T17:15:57Z). The left side is produced by seldon's code
(release-commit lookup, manifest-at-commit, keyed-shard selection) over squiddy's checkpoints. The right side is
entirely squiddy's artifact on disk. Neither side is fixed by this repository's tree. The assert holds only when the
code and the live library agree, which is why the test reads squiddy's state and not seldon's.

**Run alone once on main** (worktree at `e42c25b`, 2026-11-25 10:53 EST, load 9 to 13, 24.7 s):

    >       assert info["row_fingerprint"] == served["row_fingerprint"]
    E       AssertionError: assert '7a774aec1104...40fca2dceb9b0' == 'b81037645b27...045970f727009'
    FAILED tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index
    1 failed in 24.69s

Two read-only probes say what differs (`pa002_probe.json`, `pa002_probe2.json`):

- The rebuilt release has the served row count (416,365 = 416,365). Its `row_fingerprint` differs (`7a774aec…`
  against `b8103764…`), and so does its `shard_set_sha256` (`6e8b1533…` against `ed4bbfa9…`, 1,404 shards). Release
  commit: squiddy `b88ca875`.
- Today's `squiddy.index.row_fingerprint` run on the served `corpus.db` still gives the manifest's `b8103764…`. So the
  fingerprint function and the served database agree. What differs is the content of the rows the rebuild path takes
  from the checkpoint for the served release.

Whether the cause is seldon's rebuild or squiddy's checkpoint is not determined here: this part was read-only and
did not diagnose it. The failure is not noise. The rebuild path does not reproduce the release the library serves
today, and that is the property the test exists to pin (AD-036 ADDENDUM 06).

**Squiddy's release check** (`squiddy/squiddy/release_receipt.py`, run as `release-receipt` in stage 18 of
`squiddy/cli.py`'s release after `seal` and `hold`, gated). It also calls seldon's `rebuild_release`, but it checks a
different property:

- it rebuilds the release that the new one *superseded*, not the served one;
- it opens it with `open_rebuilt` and checks that a receipt's query, re-run, returns every row of the first run
  (along with the planted `text_sha256` control);
- it does not compare `row_fingerprint`, `shard_set_sha256` or `rows` with any manifest;
- it records seldon's named refusal (`release_unavailable`) as a pass.

So squiddy's release does **not** assert that a rebuilt release reproduces the served index. Today that property is
asserted nowhere except this deselected test.

**Which of Issue d6040ce8's exits fits: the first, the test owns a fixture.** The second exit (leave the gate for a
check where squiddy's release already runs it) has nowhere to go: no squiddy check asserts the property. Moving the
test there would first need a new squiddy stage. That is squiddy's change to make, and while it waits the property
goes unchecked.

A fixture that exercises the same seldon path is small, because `rebuild_release` encodes nothing. It needs:

- a scratch git repository (as `test_release_commit_is_the_first_commit_whose_register_row_carries_the_digest`
  already makes) holding a squiddy graph config with an `index:` block;
- a corpus manifest with one or two acquired documents;
- an export file with its register row committed;
- the corpus checkpoint lines for those documents (a handful of rows);
- one keyed line per document in the dense shard log, each with its `.npy` shard and row-id JSON (`pad_to`-wide
  vectors, a few kilobytes);
- an `index_manifest.json` recording that release's `row_fingerprint`, `shard_set_sha256` and `rows`.

That is tens of kilobytes, built once with the kit (`build_db`, `unit_key`, `row_fingerprint`, `shard_set_sha256`)
and committed, or built at test time from the same calls. squiddy must still be importable, as it is for every other
test in the file. The live comparison found something real today (above). Whether to keep it as a non-gating
check against the live library is a separate choice from the gate's test. This task files nothing.

## Part D

**Method.** The dispatcher lands a task by rebase and fast-forward. `git log --first-parent main --since=2026-10-25`
has 721 commits, all single-parent, so there is no merge commit to find. Main's reflog records each landing as
`merge worktree-<name>: Fast-forward`. The reflog starts 2026-10-25 22:40 and holds 34 such entries from 2026-10-26
to 2026-11-25. For each one, the merged tip is the entry's commit, and its first parent (the base) is the main tip
in the reflog entry before it. Each branch maps to its task through `dispatch_finished`. For every merge,
`scripts/slice_misses.py` added a scratch worktree at the tip (`git worktree add --detach` under `$TMPDIR`) and read
two plans, then removed it:

- `literal`: the task's command, `python -P -m seldon gate plan --base <prev> --json`, run in the scratch tree.
  `-P` keeps the scratch tree's own `seldon/` off `sys.path`; without it, every commit before SEL-041 answered
  "No such command 'gate'". This plan reads **the commit's own** `seldon.yaml`, so the 31 merges before SEL-045R
  (whose `seldon.yaml` declared no slices) plan `full: no_slices`. That is the record, and it says nothing about
  today's slices.
- `today`: the same diff planned with **today's** gate block (main at `e42c25b`), with the event store cut at the
  merge's own time, so the cadence reason is the one that merge would have seen. Applied to an older tree, today's
  slices name some test files the tree did not have yet, and the planner adds `slice_tests_missing` reasons. Those
  are an artifact of replaying the slices against old trees, and they are left out of the first-reason column below
  (the JSON keeps every reason).

| merged (main reflog) | task | literal tier: first reason | today's slices: tier, first reason (replay artifact removed) | unmatched (today) |
|---|---|---|---|---|
| 2026-10-26T12:39 | SEL-010R2 (worktree-glittery-churning-steele) | full: no_slices | full: unmatched: scripts/jobs/seldon_dispatch.sh | 8: scripts/jobs/seldon_dispatch.sh, seldon/commands/dispatch.py, seldon/commands/dispatch_worktree.py, seldon/core/adopt.py ... |
| 2026-10-26T13:47 | SEL-011 (worktree-calm-prancing-koala) | full: no_slices | full: unmatched: seldon/commands/cc.py | 3: seldon/commands/cc.py, seldon/commands/dispatch.py, seldon/core/dispatch.py |
| 2026-10-27T10:46 | NUM-001R (worktree-dynamic-imagining-rossum) | full: no_slices | full: unmatched: seldon/commands/cc.py | 5: seldon/commands/cc.py, seldon/commands/task.py, seldon/core/dispatch.py, seldon/core/numbering.py ... |
| 2026-10-27T11:41 | DESK-004R (worktree-glimmering-stirring-sunset) | full: no_slices | full: unmatched: seldon/commands/hooks.py | 4: seldon/commands/hooks.py, seldon/core/hooks.py, seldon/core/reconcile.py, tests/dispatch_scaffold.py |
| 2026-10-27T14:58 | DISP-004R (worktree-fluttering-noodling-twilight) | full: no_slices | full: unmatched: seldon.yaml | 5: seldon.yaml, seldon/commands/dispatch.py, seldon/commands/dispatch_worktree.py, seldon/core/dispatch.py ... |
| 2026-10-27T15:08 | RECALL-002R (worktree-rippling-yawning-fox) | full: no_slices | scoped: none: scoped (documents, event_store, task_records) | 0:  |
| 2026-10-28T10:08 | SEL-012 (worktree-flickering-prancing-stream) | full: no_slices | full: unmatched: .githooks/prepare-commit-msg | 5: .githooks/prepare-commit-msg, seldon/commands/hooks.py, seldon/commands/verify.py, seldon/core/hooks.py ... |
| 2026-10-28T11:47 | SEL-013R (worktree-squishy-wondering-pascal) | full: no_slices | full: unmatched: seldon/commands/cc.py | 7: seldon/commands/cc.py, seldon/commands/dispatch_worktree.py, seldon/core/dispatch.py, seldon/core/returns.py ... |
| 2026-10-28T13:24 | SEL-014R (worktree-cuddly-crunching-starfish) | full: no_slices | full: unmatched: scripts/sel014r_replay_with_the_model.py | 10: scripts/sel014r_replay_with_the_model.py, seldon.yaml, seldon/commands/cc.py, seldon/commands/dispatch.py ... |
| 2026-10-28T13:34 | SEL-015 (worktree-dreamy-herding-axolotl) | full: no_slices | scoped: none: scoped (documents, task_records) | 0:  |
| 2026-10-29T08:50 | SEL-016 (worktree-twinkling-drifting-walrus) | full: no_slices | scoped: none: scoped (task_records) | 0:  |
| 2026-10-29T23:54 | SEL-017 (worktree-groovy-plotting-swing) | full: no_slices | full: unmatched: seldon/commands/dispatch_stations.py | 7: seldon/commands/dispatch_stations.py, seldon/commands/dispatch_worktree.py, seldon/core/hooks.py, seldon/core/stations.py ... |
| 2026-10-30T07:17 | SEL-018 (worktree-breezy-popping-planet) | full: no_slices | full: unmatched: seldon/commands/dispatch.py | 9: seldon/commands/dispatch.py, seldon/commands/dispatch_ooda.py, seldon/commands/dispatch_stations.py, seldon/commands/dispatch_worktree.py ... |
| 2026-11-01T01:59 | SEL-019 (worktree-optimized-skipping-codd) | full: no_slices | full: full_path: pyproject.toml | 7: CLAUDE.md, seldon.yaml, seldon/cli.py, seldon/commands/init.py ... |
| 2026-11-01T07:29 | SEL-020 (worktree-ancient-leaping-bonbon) | full: no_slices | full: unmatched: CLAUDE.md | 8: CLAUDE.md, seldon.yaml, seldon/commands/commit_governed.py, seldon/commands/init.py ... |
| 2026-11-01T08:29 | SEL-022 (worktree-swirling-fluttering-clover) | full: no_slices | full: unmatched: seldon/commands/dispatch.py | 2: seldon/commands/dispatch.py, seldon/core/dispatch.py |
| 2026-11-01T09:19 | SEL-021 (worktree-humming-napping-quasar) | full: no_slices | full: unmatched: CLAUDE.md | 8: CLAUDE.md, seldon/commands/cc.py, seldon/commands/issue.py, seldon/core/dispatch.py ... |
| 2026-11-06T09:18 | SEL-023 (worktree-delegated-honking-lighthouse) | full: no_slices | full: unmatched: seldon.yaml | 14: seldon.yaml, seldon/commands/cc.py, seldon/commands/commit_governed.py, seldon/commands/dispatch.py ... |
| 2026-11-06T11:12 | SEL-024 (worktree-prancy-crunching-eagle) | full: no_slices | full: unmatched: seldon.yaml | 5: seldon.yaml, seldon/commands/dispatch.py, seldon/commands/dispatch_worktree.py, seldon/core/dispatch.py ... |
| 2026-11-06T12:49 | SEL-025 (worktree-linked-rolling-parasol) | full: no_slices | full: unmatched: .gitignore | 4: .gitignore, scripts/jobs/seldon_dispatch.sh, seldon/commands/dispatch.py, seldon/core/reconcile.py |
| 2026-11-08T14:47 | SEL-029 (worktree-witty-meandering-rivest) | full: no_slices | full: unmatched: seldon.yaml | 6: seldon.yaml, seldon/commands/cc.py, seldon/core/desktop_commit.py, seldon/core/dispatch.py ... |
| 2026-11-09T11:04 | SEL-033 (worktree-zesty-cuddling-rain) | full: no_slices | full: unmatched: seldon/cli.py | 12: seldon/cli.py, seldon/commands/dispatch_worktree.py, seldon/commands/docs.py, seldon/commands/go.py ... |
| 2026-11-09T12:59 | SEL-034 (worktree-expressive-wobbling-fairy) | full: no_slices | full: unmatched: seldon/commands/dispatch.py | 6: seldon/commands/dispatch.py, seldon/commands/dispatch_stations.py, seldon/commands/dispatch_worktree.py, seldon/core/artifacts.py ... |
| 2026-11-09T20:30 | SEL-036 (worktree-jaunty-nibbling-brook) | full: no_slices | full: unmatched: scripts/sel036/bridge.py | 12: scripts/sel036/bridge.py, scripts/sel036/build_candidates.py, scripts/sel036/proof.py, scripts/sel036/resolve.py ... |
| 2026-11-09T22:14 | SEL-035 (worktree-gentle-chasing-minsky) | full: no_slices | full: unmatched: seldon/commands/docs.py | 10: seldon/commands/docs.py, seldon/commands/project.py, seldon/commands/req.py, seldon/commands/verify.py ... |
| 2026-11-12T00:38 | SEL-037 (worktree-curried-mixing-bubble) | full: no_slices | full: unmatched: scripts/sel036/build_candidates.py | 9: scripts/sel036/build_candidates.py, scripts/sel036/sel036.yaml, scripts/sel037/counts.py, scripts/sel037/fetch.py ... |
| 2026-11-12T02:41 | SEL-038 (worktree-calm-riding-melody) | full: no_slices | full: unmatched: seldon/commands/dispatch.py | 6: seldon/commands/dispatch.py, seldon/commands/dispatch_worktree.py, seldon/core/hooks.py, seldon/core/prior_art.py ... |
| 2026-11-16T00:49 | SEL-039 (worktree-fluffy-chasing-pond) | full: no_slices | full: unmatched: seldon.yaml | 6: seldon.yaml, seldon/commands/go.py, seldon/commands/prior_art.py, seldon/commands/verify.py ... |
| 2026-11-18T01:02 | SEL-040 (worktree-vectorized-greeting-river) | full: no_slices | full: unmatched: seldon/commands/cc.py | 12: seldon/commands/cc.py, seldon/commands/dispatch.py, seldon/commands/dispatch_stations.py, seldon/commands/dispatch_worktree.py ... |
| 2026-11-21T10:41 | SEL-042 (worktree-iridescent-nibbling-ritchie) | full: no_slices | full: unmatched: seldon/commands/cc.py | 12: seldon/commands/cc.py, seldon/commands/dispatch.py, seldon/commands/dispatch_stations.py, seldon/commands/dispatch_worktree.py ... |
| 2026-11-24T14:54 | SEL-046 (worktree-immutable-sleeping-treehouse) | full: no_slices | full: unmatched: seldon/commands/dispatch_worktree.py | 2: seldon/commands/dispatch_worktree.py, seldon/core/kept_events.py |
| 2026-11-24T17:27 | SEL-045R (worktree-logical-hatching-cocke) | full: gate_config_changed: seldon.yaml | full: gate_config_changed: seldon.yaml | 12: seldon.yaml, seldon/cli.py, seldon/commands/dispatch_stations.py, seldon/commands/dispatch_worktree.py ... |
| 2026-11-25T01:10 | SEL-043 (worktree-joyful-zooming-zebra) | full: conftest: tests/conftest.py | full: conftest: tests/conftest.py | 11: seldon/commands/dispatch.py, seldon/commands/dispatch_stations.py, seldon/commands/dispatch_worktree.py, seldon/core/dispatch.py ... |
| 2026-11-25T03:51 | SEL-044 (worktree-enchanted-cuddling-cake) | full: unmatched: seldon/commands/go.py | full: unmatched: seldon/commands/go.py | 4: seldon/commands/go.py, seldon/commands/handoff.py, seldon/core/portfolio.py, seldon/mcp_server.py |

| top two levels of an unmatched path | merges it sent full |
|---|---|
| `seldon/commands/` | 30 |
| `seldon/core/` | 30 |
| `seldon/mcp_server.py` | 12 |
| `seldon.yaml` | 11 |
| `tests/dispatch_scaffold.py` | 7 |
| `seldon/domain/` | 6 |
| `tests/fixtures/` | 5 |
| `seldon/cli.py` | 3 |
| `CLAUDE.md` | 3 |
| `scripts/jobs/` | 2 |
| `scripts/sel036/` | 2 |
| `.githooks/prepare-commit-msg` | 1 |
| `scripts/sel014r_replay_with_the_model.py` | 1 |
| `seldon/templates/` | 1 |
| `.gitignore` | 1 |
| `scripts/sel037/` | 1 |
| `tests/r9_shim.py` | 1 |

**What sent each merge full, under today's slices** (34 merges):

| class | merges | which |
|---|---|---|
| a change under `seldon/` (unmatched on purpose: the comment above `gate:` in `seldon.yaml`; SEL-041 Part A section 3, `tests/conftest.py` imports `seldon.cli`, whose import closure is the whole package) | 30 | every merge except the four below |
| no code change, and no reason at all once the replay artifact is removed: scoped today | 3 | RECALL-002R, SEL-015, SEL-016 |
| no code change, full only on paths a slice could name | 1 | SEL-037 (`scripts/sel036/`, `scripts/sel037/`, the task's own build scripts) |

Of the 30 code merges, 29 are full on `unmatched: seldon/...` alone or alongside other paths. The 30th, SEL-045R, is
full on `gate_config_changed` as well. Naming more paths in a slice would change the tier of **none** of the 30,
because each still changes `seldon/`. The non-code paths that went unmatched beside the code (with the merges they
appeared in) are listed by design below, so a reader can see that none of them was the only cause:

- **By design, keep unmatched (full):**
  - `seldon/**` (30 merges; R32, the planner's fail-safe default, Saltzer and Schroeder as AD-034 ADDENDUM 12 cites
    it).
  - `tests/conftest.py` (rule `conftest`).
  - `seldon.yaml` gate keys (`gate_config_changed`).
  - `pyproject.toml` (`full_paths`).
  - `.githooks/**`: hook code runs in git's child processes, which SEL-041's testmon measurement showed static
    selection misses (testmon selected 2 of the 41 test files that reach `seldon hooks pre-commit`,
    `docs/evidence/sel041/testmon/README.md` item 3).
  - `tests/r9_shim.py`: `tests/conftest.py` imports it, so it reaches every test.
  - `.gitignore`: it changes what every git-driven test sees.
- **A slice could name these and keep the fail-safe**, each mapped to the tests that read it. Each mapping is static,
  so an unlisted reader is still caught by the cadence's daily full gate (R29) and R33's escape check:
  - `tests/fixtures/<file>` (5 merges), to the one test that opens each fixture: `dispatch_serial_transcript.txt` to
    `test_dispatch_serial_transcript.py`; `sel040/hb189_log_tail.jsonl` to `test_sel040_interrupted_session_resumed.py`;
    `sel042/hb197_hb198_events.jsonl` to `test_sel042_stopped_session_never_merges.py`.
  - `scripts/sel0NN/**` and `scripts/sel014r_*.py`, a task's own one-off scripts (3 merges), to the tests that name
    them. The SEL-041 real-reads scan (`docs/evidence/sel041/tools/real_reads.py`, re-run 2026-11-25) finds one test
    file naming `scripts/` (`test_result_registry.py`, the bare directory). `test_sel014r_replay_script_checkpoint.py`
    and `test_sel037_fetch_checkpoint.py` run their task's script by path (`ROOT / "scripts" / ...`), and
    `test_sel036_resolve_checkpoint.py` names `scripts/sel036`.
  - `tests/dispatch_scaffold.py` (7 merges): it can be named, but it selects its 44 importers, about a fifth of the
    205 files and most of the dispatcher's slow tests. That is less than full, but not light.
  - `CLAUDE.md` (3 merges): three tests name a `CLAUDE.md` (`test_go.py`, `test_init.py`,
    `test_prune002_go_generated.py`), mostly a scratch project's. It could be a `documents`-style slice to those three.
- **Not settled from this evidence:** `seldon.yaml` with no gate-key change (11 merges). The real-reads scan matches
  the literal string `seldon.yaml` in 95 test files, nearly all of them a scratch project's own file. Telling which
  of those read the root file needs a narrower scan than this task ran. Until then it stays full.
- **Also:** `scripts/jobs/seldon_dispatch.sh` (2 merges, the launchd job). No test names it. It could be
  `tests: none`, but it is the dispatcher's own entry point, and a wrong edit to it shows only at the next launch, so
  it is best left full.

**Prefix counts.** The second table above counts the merges each unmatched path's top two levels sent full:
`seldon/core/` 30, `seldon/commands/` 30, `seldon/mcp_server.py` 12, `seldon.yaml` 11, `tests/dispatch_scaffold.py` 7,
`seldon/domain/` 6, `tests/fixtures/` 5, and the rest 3 or fewer.

**What this says about the slices.** In seldon's own history they are not the lever. 30 of 34 task merges change
`seldon/` and are full by design. Of the remaining 4, today's slices already scope 3. Naming every nameable path
above would have scoped one more merge (SEL-037) in a month: 1 of 34. The time a seldon task spends holding the
lease is set by how long the full tier takes, not by how often the planner chooses it.

## Part E

What the change task should be, from Parts B to D. Each point names its evidence.

1. **`gate_command` should run at `-n 6`, but only together with the test fixes in point 2, or after them.**
   - Measured the same afternoon under the same neighbour: serial took 7,463 s, `-n 6` took 2,193, 2,269 and
     2,508 s (Part B, "Full suite"), 3.0 to 3.4 times less. That cuts the time every other repository's dispatcher
     waits on seldon's lease from about 2 hours to about 40 minutes under today's load. It is about 26 minutes on
     quiet nights (SEL-042's 25:40 and 25:51).
   - The serial gate is the riskier of the two today. Its 7,463 s exceeds `gate_timeout_s` 7,200 (Part B,
     item 4).
   - `-n 6` alone does not make the gate green. Every `-n 6` run had 2 to 4 failures. Both timing tests failed in all
     three: `two_disjoint` 3 of 3 and `lock_wait` 3 of 3. The serial run failed `lock_wait` too, so neither form
     is green today.
   - Moving to `-n 6` without the fixes adds four ids the serial run did not fail: `two_disjoint`, the `sel018`
     victim, and the two gw5 timing budgets.

2. **What each test needs.**
   - **`test_sel024_gate_record::..._lock_wait_...`** (non-order-dependent, 16 of 20 alone): replace the fixed
     window with a synchronisation. `RECORDER` should block until a file the filer thread writes after
     `F.file_task` returns, with a ceiling such as the filer's own 120 s, not `time.sleep(6)`. Then "the filing
     lands while the gate runs" holds by construction. The recorder script lives in the test file (`RECORDER`,
     `_recorder`), so this is a **test-file-only** change.
   - **`test_dispatch_parallel::test_two_disjoint_...`** (non-order-dependent, 3 of 20 alone, 3 of 3 at `-n 6`):
     the stubs' `sleep: 3` must cover the second launch. Overlap should come from a rendezvous: each stub writes its
     `start` mark and waits, with a ceiling, until both marks exist. The stub interpreter is in
     `tests/dispatch_scaffold.py` (`spec.get("sleep")`), so this needs the scaffold. That is an unmatched path:
     **full**.
   - **`test_dispatch_parallel::test_union_merge_...`** (non-order-dependent, 2 of 20 alone): **cause not
     determined.** Its post-settle assertion should carry the supervisors' logs in its message, as `_wait_settled`
     already does on a timeout, so its next failure says why task a ended `blocked`. A test-file-only change.
   - **`test_dispatch_parallel::test_a_killed_supervisor_...` and `::test_an_exclusive_task_waits_...`** (1 of 3 `-n 6`
     runs, 0 of 20 alone, 0 of 3 prefix replays): explicit wall-clock budgets (`< 30` s) and pass timing under a
     5-minute load above 70. They are the same class as the two above, at a lower rate. The budget should be a
     ceiling on a condition that is waited for, not a race.
   - **`test_sel018_relative_dispatch_paths::test_dispatch_status_reads_the_cap_from_a_worktree`** (order-dependent;
     polluter `test_sel008_...::test_task_show_prints_the_edge_with_the_other_tasks_state_and_the_precedes_edges`):
     add the `clean_test_db` fixture to the victim, a **test-file-only** change. A deeper defect showed in passing:
     `dispatch status --json` writes a warning line into the same output stream as its JSON. A JSON command's
     warnings belong on stderr. That is a code change under `seldon/` (full), and it should be filed separately, not
     folded in.
   - Portfolio prior art for running load-sensitive tests apart: hazbrief's run that was visible in `ps` during
     Part B, `pytest tests/ -n 3 --dist loadgroup -m load_sensitive`, is a marker lane for exactly these tests. It was
     only observed here, not read. If the fixes above are not wanted, it is the other way to keep timing tests out
     of a parallel gate.

3. **pa002 takes the first exit: the test owns a fixture** (Part C). No squiddy check asserts that a rebuilt release
   reproduces the served index. Stage 18's `release-receipt` checks a receipt re-run on the superseded release and
   passes seldon's `release_unavailable`, so there is nowhere for the second exit to send it. A fixture built inside
   the test file with the kit's calls keeps the change test-file-only. Committed fixture files under
   `tests/fixtures/` would be unmatched, so full.
   - Separately, the live comparison is red for a real reason: same 416,365 rows, different row fingerprint and
     shard set, served `corpus.db` still matching its manifest. Factory may want that filed. This task files
     nothing.

4. **Paths a slice could name** (Part D):
   - `tests/fixtures/<file>`, each to the one test that reads it;
   - `scripts/sel0NN/**` and `scripts/sel014r_*.py`, to the tests that run them;
   - `CLAUDE.md`, to `test_go.py`, `test_init.py` and `test_prune002_go_generated.py`;
   - optionally `tests/dispatch_scaffold.py`, to its 44 importers.

   In this history that buys **1 of 34** merges (SEL-037). 30 of 34 changed `seldon/` and are full by design.
   Slices are worth naming for tidiness, not for queue time.

5. **The change task's own gate.** Any change to `gate_command` or the slices changes `seldon.yaml`'s gate keys, so it
   plans **full** (`gate_config_changed`). The merge round reads `dispatch.gate_command` and `gate_timeout_s` from
   the primary's `seldon.yaml` (`seldon/commands/dispatch_worktree.py`, `_gate`, `GP.run(..., timeout_s=cfg["gate_timeout_s"])`).
   So that merge runs **main's serial command under main's 7,200 s ceiling**.
   - The one serial run measured here took **7,463 s** (Part B). Under this afternoon's neighbour load that merge
     gate would time out (`regate_red`). The three merge gates of 2026-11-25 took 81 to 96 minutes, at night.
   - So the full-gated change should merge when no other repository's suite runs. It will hold the lease about 81
     to 124 minutes (measured range), once.
   - The cadence is a second source of full gates. The last passing full gate was 2026-11-25T08:51:20Z
     (`full_every_s` 86,400), so any seldon gate after 2026-11-26T08:51Z plans full until a full gate passes.

6. **What can land first, on a scoped gate.** Three of the fixes touch only one test file each:
   - the `lock_wait` recorder,
   - the `sel018` victim's `clean_test_db`,
   - the `union_merge` diagnostic message,
   - and pa002's fixture if it is built inside its test file.

   A changed test file matches `test_globs` and always runs as a changed test (R31). With only `cc_tasks/`,
   `docs/`, `state/` and the event store beside it, each plans scoped: about 1 to 30 test files at `-n 4`. That is
   true unless the cadence is due, so it should land before 2026-11-26T08:51Z, or right after a full gate passes.
   - These should not wait for the full-gated change.
   - The full-gated change carries the scaffold rendezvous for `two_disjoint`, `gate_command -n 6`, and any slices.
     It should land after them, so its single serial gate runs against tests that can pass.
