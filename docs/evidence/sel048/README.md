# SEL-048 evidence: three timing and order tests, fixed in their own test files

Task `6e90a498`, `cc_tasks/2026-11-25_SEL-048_three_timing_and_order_tests_are_fixed_in_their_own_test_files_on_a_scoped_gate.md`.
Its diagnosis is SEL-047's (`docs/evidence/sel047/README.md` Parts B and E). This directory holds the runs.

## Files

- `run.py`: runs one pytest command in the gate's form and appends one row to `runs.jsonl` (`run, command,
  started_at, ended_at, wall_s, load_before, passed, failed, failed_ids`, plus `load_after`, `returncode`, `summary`).
  Each run's full output went to `logs/<run>.log`, which is gitignored (`*.log`); the rows keep the summary line.
- `sequence.sh`: the task's runs in order, one at a time, launched detached under `caffeinate -i`.
- `stress.sh`: one test under induced CPU contention (N busy-loop processes on this 10-core machine). Not asked for by
  the task; added because the sequence ran at a 1-minute load of 5.5 to 12, where SEL-047's old test also passed (its
  alone runs 1 to 3 and 19). Without it the ten passes would not show that the fix fixes anything.
- `show.py`: prints `runs.jsonl` one short line per run.

## Runs (all on `runs.jsonl`, 22 rows)

| runs | what | result |
|---|---|---|
| `sel018_polluter_then_victim_{1,2,3}` | Part B: polluter then the fixed victim, `-p no:randomly` | 3 of 3 passed (2 tests each) |
| `sel018_file_alone_1` | Part B acceptance: the sel018 file alone | 13 passed |
| `sel024_alone_01..10` | Part A: the sel024 file alone, random order on (as `gate_command`) | 10 of 10 passed, 24 tests each, 208 to 230 s, load 5.5 to 12.0 |
| `union_merge_file_alone_1` | Part C: the dispatch_parallel file alone | 14 passed, 456 s |
| `stress20_old_{1,2,3}` | main's `lock_wait` test (a temporary copy of main's file) with 20 busy loops | **0 of 3**: each failed `gate_running_at_end: False`, "the filing landed mid-gate", SEL-047's form |
| `stress20_new_{1,2,3}` | this branch's `lock_wait` test, same 20 busy loops | **3 of 3 passed**, 115 to 134 s |
| `sel018_old_victim_after_polluter_1` | the polluter then main's victim (a temporary copy), `-l` | failed, `JSONDecodeError`; the output began `waits_on: 328e414a -> other:214b7da8-...: the other graph could not be read (ValueError: ...` ahead of the JSON |

The temporary copies (`tests/test_sel048_tmp_old_*.py`) were deleted after their runs and are not committed.
The stress rows' `load_before` includes the busy loops themselves, and, from about 23:20 local, an unrelated
`squiddy.parse` from another repository's worktree at about 150% CPU.
