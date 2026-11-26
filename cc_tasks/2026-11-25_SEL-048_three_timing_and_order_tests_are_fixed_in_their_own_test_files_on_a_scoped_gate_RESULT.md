# RESULT: SEL-048. Three timing and order tests, fixed in their own test files, on a scoped gate

**Date:** 2026-11-25 (EST; 2026-11-26 UTC). **Task:** `6e90a498`. **Branch:** `worktree-robust-bouncing-meerkat`, from
main `3d95c77`. This session did not merge, push or complete the task.
**Addenda read:** none exist (searched for the `_ADDENDUM*` sibling files: none).
Recall used: none

Changed: `tests/test_sel024_gate_record.py`, `tests/test_sel018_relative_dispatch_paths.py`,
`tests/test_dispatch_parallel.py`, `docs/evidence/sel048/**` and this RESULT. Nothing under `seldon/`, no
`conftest.py`, not `tests/dispatch_scaffold.py`, not `seldon.yaml`. Zero model calls, no network. Filed nothing,
registered nothing. Runs and method: `docs/evidence/sel048/README.md`, rows on `docs/evidence/sel048/runs.jsonl`.

`seldon gate plan --base main` in this worktree, after the work commit `ec22156` (Part D), first line:

    gate plan against main (fork 3d95c779, tree f0d387d3): scoped: 26 of 205 test files; scoped: documents

The three changed test files are on its R31 "always run" line. Planned at 04:28Z, before the 08:51Z cadence.

## Part A: `test_sel024_gate_record::..._lock_wait_...`

- **What changed.** `RECORDER` takes `--wait-for <path>` and `--wait-ceiling <s>`. Given them, after writing
  `started` it polls until the path exists, or gives up at the ceiling and says so on its output. The test passes
  `tmp_path/filed.mark` and `FILER_CEILING_S = 120` (the filer's own 120 s). The filer thread writes `filed.mark` in
  a `finally` after `F.file_task` returns or is refused, and after it reads `gate_running_at_end`. So the gate
  outlasts the filing by construction. A refused filing still releases the gate, so a regression fails on
  `"refused" not in seen`, not on a hang. `GATE_SLEEP_S` is gone. `--sleep` is kept, default 0, and no other test
  passed it. Every other `_recorder` caller passes neither new flag, so it behaves as before.
- **Runs.** The file alone, ten times (`sel024_alone_01..10`), random order on as in `gate_command`: **10 of 10
  passed**, 24 tests each, 208 to 230 s, 1-minute load 5.5 to 12.0. No timeout was widened.
- **What Part E did not predict.** The ten passes alone prove little: the machine was quiet, and at that load
  SEL-047's old test also passed (its alone runs 1 to 3 and 19). So I added a controlled comparison, under 20
  busy-loop processes on this 10-core machine (`stress.sh`):
  - main's test, from a temporary copy that is now deleted: **0 of 3** (`stress20_old_*`). Every run failed SEL-047's
    way, `gate_running_at_end: False`, "the filing landed mid-gate".
  - this branch's test: **3 of 3** (`stress20_new_*`), 115 to 134 s.
  
  That confirms Part E's mechanism (a fixed window, Luo et al.'s async wait) and the fix, in 6 runs.
- The acceptance check (three runs of the file) was not run as a separate command. The ten alone runs are a
  superset of it, and `part-complete` runs it again.

## Part B: `test_sel018_relative_dispatch_paths::test_dispatch_status_reads_the_cap_from_a_worktree`

- **What changed.** The test takes `clean_test_db`, with a comment naming the polluter.
- **Runs.**
  - The polluter (`test_sel008_...::test_task_show_prints_the_edge_with_the_other_tasks_state_and_the_precedes_edges`)
    then the victim, `-p no:randomly`: **3 of 3 passed** (`sel018_polluter_then_victim_*`).
  - The file alone: 13 passed (`sel018_file_alone_1`, the acceptance command).
- **The warning line (item 3).** With the fix it cannot show, because the leftover task is cleaned away. To answer
  the question, I ran the polluter then main's victim, from a temporary copy (`sel018_old_victim_after_polluter_1`,
  `-l`). It **failed again** with `JSONDecodeError`. The parsed string began
  `waits_on: 328e414a -> other:214b7da8-...: the other graph could not be read (ValueError: ...`, ahead of the JSON.
  So `dispatch status --json` still writes a warning into its JSON stream. I did not change it. SEL-047 says it is
  filed separately, and this task files nothing.

## Part C: `test_dispatch_parallel::test_union_merge_of_two_event_appends_is_valid`

- **What changed.** The post-settle assertion's message now carries the task states, the `dispatch_finished`
  payloads, and both supervisors' logs (the same `_supervisor_log` that `_wait_settled` uses). I changed no timing,
  no stub and no other test.
- **Runs.** The file alone once (`union_merge_file_alone_1`): 14 passed, 456 s, load 6.5. The new message was not
  exercised, because the test passed. Its cause is still not determined. The next failure will carry the logs.

## Part D

- The diff against main contains only the paths the Part D check allows. That check was run before this RESULT was
  committed.
- Seen and not predicted by SEL-047 Part E:
  - the stress comparison above. It is new evidence, not a contradiction.
  - an unrelated `squiddy.parse` from another repository's worktree ran at about 150% CPU after about 04:20Z. It
    overlapped only the last stress runs and the sel018 replay. Their `load_before` also counts my own busy loops.

## Remaining for the full-gated change (unchanged from SEL-047 Part E)

- the `two_disjoint` rendezvous, which needs `tests/dispatch_scaffold.py`;
- `gate_command -n 6`;
- the two gw5 budgets;
- `dispatch status --json` warnings to stderr.
