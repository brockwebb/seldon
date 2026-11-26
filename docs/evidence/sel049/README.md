# SEL-049 evidence: the gate at `-n 6`, and three dispatcher tests that wait on a condition

Task: `cc_tasks/2026-11-25_SEL-049_the_gate_runs_in_parallel_and_the_dispatcher_timing_tests_wait_on_a_condition.md`.
Branch `worktree-dazzling-yawning-oasis`, from main `d67f9ef`. All runs used work commit `98139c4` (the scaffold, the
test file and `seldon.yaml` as merged; nothing under `tests/` or `seldon.yaml` changed after it). Zero model calls, no
network. Machine on AC power throughout; no run spanned a sleep (`sleep_spanned: false` on every row).

| file | what it holds |
|---|---|
| `runs.jsonl` | one line per pytest run: the task's fields (run, command, started_at, ended_at, wall_s, load_before, passed, failed, failed_ids) plus load_after, returncode, summary, sleep_spanned |
| `run.py` | the recorder. `run.py <name> <pytest args>` is the gate's prefix with the given arguments (SEL-048's form); `run.py <name> --gate-command` runs `dispatch.gate_command` from this tree's `seldon.yaml` verbatim through `/bin/sh -c`, as `seldon/core/gate_plan.py` `run` does |
| `sequence.py` | Parts A and B's runs, one at a time, resume by skip |
| `stress.py` | the added old-against-new comparison under 20 busy loops (SEL-048's method) |
| `launch.py` | starts either script detached under `caffeinate -i`, output to `logs/<script>.out` ending `EXIT=<rc>` |
| `logs/` | one pytest log per run (`*.log` is gitignored; added with `git add -f`, as SEL-047's) |

## The full run at `-n 6` (Part B)

`full_n6_1`: `gate_command` exactly as `seldon.yaml` now reads it, from the tree's root.

| run | started (UTC) | wall s | 1-min load before / after | passed | failed | failed id |
|---|---|---|---|---|---|---|
| full_n6_1 | 05:17 | **1,573 (26:13)** | 6.88 / 13.16 (rose to about 21 mid-run) | 3,558 | 1 | `test_union_merge_of_two_event_appends_is_valid` |

That one failure is the one the task allows. It is not one of this task's three tests, and it was not fixed here.
SEL-048's richer message gives its cause for the first time: task a ended `merge_blocked`, reason `main_kept_moving`,
`attempts: 3`, while task b merged and the dispatcher's record commits (`record: dispatch_worktree_named`, `gate_run`,
`dispatch_finished` ...) moved main under a's merge. a used up the dispatcher's default `merge_attempts: 3`
(`seldon/core/dispatch.py`; the test's config does not set it). The message is
quoted in full in the RESULT.

## The file alone, ten times (Part A)

`tests/test_dispatch_parallel.py`, gate form, pytest-randomly left on (random order each run).

| run | started (UTC) | wall s | 1-min load before | passed | failed |
|---|---|---|---|---|---|
| alone_dispatch_parallel_01 | 05:43 | 431.5 | 13.16 | 14 | 0 |
| alone_dispatch_parallel_02 | 05:50 | 431.0 | 4.45 | 14 | 0 |
| alone_dispatch_parallel_03 | 05:57 | 432.7 | 5.20 | 14 | 0 |
| alone_dispatch_parallel_04 | 06:05 | 432.6 | 7.39 | 14 | 0 |
| alone_dispatch_parallel_05 | 06:12 | 430.6 | 6.32 | 14 | 0 |
| alone_dispatch_parallel_06 | 06:19 | 431.9 | 9.13 | 14 | 0 |
| alone_dispatch_parallel_07 | 06:26 | 435.2 | 5.45 | 14 | 0 |
| alone_dispatch_parallel_08 | 06:33 | 434.4 | 5.14 | 14 | 0 |
| alone_dispatch_parallel_09 | 06:41 | 432.1 | 6.87 | 14 | 0 |
| alone_dispatch_parallel_10 | 06:48 | 431.7 | 6.35 | 14 | 0 |

**10 of 10 passed, every test.** `union_merge` passed all ten too. SEL-047's alone runs of the old file took 462 to
852 s at loads of 6 to 99. These took 431 to 435 s, and part of the difference is the quieter machine.

## Old against new under contention (added; not asked for)

The ten alone runs ran at a 1-minute load of 4 to 13. SEL-047's old tests mostly passed there too: its `two_disjoint`
failures came at loads of 99, 47 and 18. So, as SEL-048 did for `lock_wait`, the three tests ran under 20 busy-loop
processes on this 10-core machine. Each round ran main's file (a temporary copy, `tests/test_sel049_old_parallel_tmp.py`,
deleted after and never committed) and then this branch's, `-p no:randomly -k` the three tests.

| run | wall s | 1-min load before | result |
|---|---|---|---|
| stress20_old_1 | 221 | 14.7 (still climbing) | 3 passed |
| stress20_new_1 | 241 | 48.0 | 3 passed |
| stress20_old_2 | 277 | 43.8 | **`two_disjoint` failed**: a ran 11.2 s, b started 0.26 s after a ended |
| stress20_new_2 | 279 | 42.3 | 3 passed |
| stress20_old_3 | 278 | 46.2 | **`two_disjoint` failed**: a ran 10.9 s, b started 0.07 s after a ended |
| stress20_new_3 | 278 | 45.5 | 3 passed |

- **`two_disjoint`**: at a sustained load of about 45, main's test failed 2 of 2 in the same form as SEL-047's run 10
  (the `sleep: 3` did not cover b's launch), and this branch's passed 3 of 3. That confirms the mechanism and the fix.
- **The two budget tests** passed in both versions at this load. This comparison does not distinguish them: SEL-047
  saw each fail once, at a 5-minute load above 70 next to another repository's `-n 6` suite. Their fix rests on its
  construction (below and in the RESULT), not on a measured old failure.

## What a seldon merge now holds the lease for

The merge round holds the lease for the length of the gate plus the merge's own git and record work (seconds).
Since AD-034-R26, every seldon task that changes `seldon/` gets a full gate. So the full tier's wall time is what the
lease costs.

| gate | measured | source |
|---|---|---|
| serial (main's `gate_command` until this merges) | 81 to 96 min on quiet nights (4,854 to 5,788 s); **124 min (7,463 s) under load, over the 7,200 s ceiling** | SEL-047 Part B and the 2026-11-25 merge gates |
| `-n 6`, loaded (another repository's `-n 6` suite beside it) | 37 to 42 min (2,193 to 2,508 s), 2 to 4 failures each before these fixes | SEL-047 Part B |
| `-n 6`, quiet | 25:40 and 25:51 | SEL-042 |
| **`-n 6`, this task's run** (load 7 rising to about 21) | **26:13 (1,573 s)**, only `union_merge` failing | `full_n6_1` above |

So a seldon full gate should hold the lease for **about 26 minutes quiet and about 40 minutes loaded**, against 81 to
124 minutes serial: roughly a third. `gate_timeout_s` stays 7,200 s, about three times the worst `-n 6` run measured.

**This task's own merge is the last serial one.** The merge round reads `gate_command` and `gate_timeout_s` from the
primary's `seldon.yaml` (`seldon/commands/dispatch_worktree.py`, `_gate`), and that is main's serial command until
this branch lands. That merge plans full (`gate_config_changed: seldon.yaml`, `unmatched: tests/dispatch_scaffold.py`),
and it holds the lease about 81 to 124 minutes, once. Every full gate after it runs `-n 6`.

What `-n 6` does not fix: `union_merge` (`main_kept_moving`, above) is now the one known intermittent in the full
tier. It failed in 1 of 1 `-n 6` runs here and in 0 of 10 alone runs. At `-n 6` it can still turn a merge gate red.
