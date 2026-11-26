# RESULT: SEL-047. Seldon's gate time, measured before anything changes

**Date:** 2026-11-25. **Task:** `5ca015e0`. **Branch:** `worktree-fluffy-dancing-clock`, from main `e42c25b`.
This session did not merge, push or complete the task.
**Addenda read:** none exist (searched for the `_ADDENDUM*` sibling files: none).
Recall used: seldon:2026-11-21_SEL-041_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points_RESULT. SEL-041's evidence shaped Part D: its real-reads scan (`docs/evidence/sel041/tools/real_reads.py`, re-run here) and its testmon result (`docs/evidence/sel041/testmon/README.md`) set which unmatched paths a slice could name.

Changed: only `docs/evidence/sel047/**` and this RESULT. Nothing under `seldon/`, `tests/` or `seldon.yaml`. Zero
model calls, no network. Evidence and method: `docs/evidence/sel047/README.md`.

`seldon gate plan --base main` in this worktree, before this RESULT (Part E item 4), first line:

    gate plan against main (fork e42c25bc, tree 6793a5a7): scoped: 23 of 205 test files; scoped: documents

## Findings

1. **Serial against `-n 6`, same afternoon, same neighbour** (hazbrief's HB-230 suites ran beside every run; the
   1-minute load average ranged from 3 to 99):
   - Serial `gate_command`: **7,463 s**, 1 failed.
   - `-n 6`: **2,193 s, 2,269 s and 2,508 s**, with 2, 3 and 4 failed.
   - `-n 6` is 3.0 to 3.4 times faster.
   - **The serial run outlasted `gate_timeout_s` (7,200 s)**, so a merge gate run under today's load would have
     timed out.
2. **The `lock_wait` test is non-order-dependent.**
   - It failed **alone in 16 of 20 runs** and in all 4 full runs.
   - Cause: a fixed 6 s `time.sleep` in the test's `RECORDER` must contain a whole filing (a git commit through
     seldon's hooks, plus Neo4j writes). That is Luo et al.'s "async wait" class.
   - The fix is a test-file-only synchronisation.
3. **`test_dispatch_parallel.py` is non-order-dependent for its two alone failures.**
   - It had a failure in **4 of 20 alone runs**: `two_disjoint` 3 of 20 (a fixed 3 s overlap window; also failed 3
     of 3 at `-n 6`) and `union_merge` 2 of 20 (cause not determined; its assertion lacks the supervisors' logs).
   - Two more ids failed once each in `full_n6_3`, at a 5-minute load above 70, and passed alone 20 of 20. Replaying
     their worker's 12-test prefix passed 3 of 3, so no polluter was found.
4. **One order-dependent pair found by delta debugging** (8 replays, 97 s):
   - Polluter `test_sel008_cross_project_waits_and_block_reason.py::test_task_show_prints_the_edge_with_the_other_tasks_state_and_the_precedes_edges`
     leaves a cross-project `waits_on` task in the shared test database.
   - Victim `test_sel018_relative_dispatch_paths.py::test_dispatch_status_reads_the_cap_from_a_worktree` has no
     `clean_test_db`, so `dispatch status --json` warns about the leftover task inside the output the victim parses.
   - The pair fails only at `-n 6`: in serial order, files between the two clean the database.
5. **pa002: exit one (the test owns a fixture).**
   - Squiddy's stage-18 `release-receipt` does not assert that a rebuilt release reproduces the served index. It
     checks a receipt re-run on the *superseded* release and passes seldon's `release_unavailable`.
   - The live failure is a real divergence: same 416,365 rows, different row fingerprint and shard set, and the served
     `corpus.db` still matches its manifest. The probes are `pa002_probe.json` and `pa002_probe2.json`.
6. **Slices:**
   - There is no merge commit on main's first-parent history (rebase plus fast-forward), so the 34 task merges were
     read from main's reflog.
   - 30 of the 34 changed `seldon/` and are full by design. Today's slices already scope 3 of the other 4.
   - Naming every nameable path (`tests/fixtures/<file>`, `scripts/sel0NN/**`, `CLAUDE.md`, optionally
     `tests/dispatch_scaffold.py`) would have scoped **1 of 34** merges.

## For factory: the change task, from this evidence (README Part E)

- **Land first, each on a scoped gate** (one test file each): the `lock_wait` recorder synchronisation; `clean_test_db`
  on the `sel018` victim; supervisors' logs in `union_merge`'s assertion; pa002's fixture, if it is built inside its
  test file. Merge these before 2026-11-26T08:51Z, or after the next passing full gate. After that hour the cadence
  makes every seldon gate full.
- **Then one full-gated change:** the scaffold rendezvous for `two_disjoint`, `gate_command` at `-n 6`, and any
  slices. It plans `gate_config_changed`, and the merge round runs **main's serial command under main's 7,200 s
  ceiling**. Measured range: 81 to 96 minutes at night, 124 minutes this afternoon (a timeout). It should merge
  when no other repository's suite runs.
- **To file separately, if factory agrees:**
  - `dispatch status --json` mixes a warning line into its JSON output, a code defect under `seldon/`.
  - The pa002 live divergence, which belongs to seldon's `rebuild_release` or squiddy's checkpoints, undetermined.
  - This task filed nothing.

## Deviations, stated

- **pytest-randomly is installed.** Every run passed `-p no:randomly`, as the task orders. The real `gate_command`
  does not, so real gates run in a random order.
- **`pgrep -f pytest` misses xdist workers.** From run 6 on, the ledger also records other suites' workers and
  directories.
- **Machine sleep.** The Mac went into clamshell sleep on battery at 14:07. The interrupted run was discarded
  unrecorded and run again. From then on, `runs.py` flags any run that spans a sleep. No recorded run did.
- **`*.log` is gitignored.** The run logs were added with `git add -f`, as the evidence the ledger names. The secret
  scan passed on all 69 files, and the Neo4j password literal appears in none.
- **Part D's literal command** needed `python -P`. Without it, the scratch tree's own pre-SEL-041 `seldon/` shadowed
  today's and had no `gate` command.
- **Wall time** was about 11 hours (10.9 h at Part B's `part_complete`), against the estimate of about 3. It went on 40 alone runs at 4 to 14 minutes
  each under load, a 124-minute serial run, and the hour of sleep.

## Acceptance

All task `check:` lines pass in this worktree:

- Part A: `grep scoped`.
- Part B: `runs.jsonl` has 59 lines, at least 44.
- Parts B, C, D and E: each `^## Part` heading is present.
- Part D: `slice_misses.json` has 34 rows.
- Part E: the diff against main touches only `cc_tasks/` and `docs/evidence/sel047/`, 0 paths outside the allowed
  set.

`part_complete` was recorded for A, B, C and D. E is recorded after this RESULT is committed.
