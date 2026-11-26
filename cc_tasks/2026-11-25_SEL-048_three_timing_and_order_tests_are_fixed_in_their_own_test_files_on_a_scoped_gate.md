# SEL-048: three timing and order tests are fixed in their own test files, on a scoped gate

**Status:** proposed
**Author:** Desktop session (factory coordinator, FCT-4), 2026-11-25 22:35 EST, from SEL-047's RESULT and `docs/evidence/sel047/README.md` Part E items 2 and 6.
**Repo:** seldon only. No other repository is written. L4: commit on the task branch; the dispatcher merges.
**After:** none
**Governing:** AD-034-R29 to R37 (AD-034 ADDENDUM 12, the scoped gate); AD-034-R31 (a changed test file always runs). No new ruling: three test files change, and nothing under `seldon/`, no `conftest.py`, not `tests/dispatch_scaffold.py`, not `seldon.yaml`.
**Model:** primary
**Spend:** est. 0.6M tokens. Basis: SEL-047 read these tests and their failures for under 0.3M; this changes three test files and runs them (about fifteen single-file runs, detached and polled). Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.45, B 0.2, C 0.2, D 0.15.
**Premises:**
- premise: SEL-047's evidence is on main | check: grep -q "^## Part E" docs/evidence/sel047/README.md
- premise: the recorder still sleeps a fixed window | check: grep -q "time.sleep(a.sleep)" tests/test_sel024_gate_record.py
- premise: the sel018 victim does not take clean_test_db | check: grep -q "def test_dispatch_status_reads_the_cap_from_a_worktree(tmp_path, neo4j_driver):" tests/test_sel018_relative_dispatch_paths.py

## Why, and this task's own gate (from the code, before registration)

SEL-047 measured that `test_sel024_gate_record.py::test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` fails 16 of 20 runs alone and in every full run, serial and `-n 6`. It is not load. `test_sel018_relative_dispatch_paths.py::test_dispatch_status_reads_the_cap_from_a_worktree` is an order-dependent victim (polluter found: `test_sel008_...::test_task_show_prints_the_edge_with_the_other_tasks_state_and_the_precedes_edges`). `test_dispatch_parallel.py::test_union_merge_of_two_event_appends_is_valid` fails 2 of 20 alone, cause not determined. With these in the suite no gate is reliably green, serial or parallel, and every red gate costs every repository 81 to 124 minutes.

This task changes only test files, `cc_tasks/`, `docs/evidence/sel048/` and the event store. Each changed test file runs as a changed test (R31) and the rest matches a slice, so the plan is **scoped**. That holds only until the daily cadence falls due at 2026-11-26T08:51Z (03:51 EST): a merge after that gates full and serial. Work in the order below and do not add scope.

Read `docs/evidence/sel047/README.md` Parts B and E in full before changing anything. Every run longer than two minutes is launched detached under `caffeinate -i` and polled. Runs use the gate's form: `python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest -p no:cacheprovider ...`. Record each run as one line in `docs/evidence/sel048/runs.jsonl` (`run, command, started_at, ended_at, wall_s, load_before, passed, failed, failed_ids`).

## Part A: the lock_wait recorder waits for the filing, not for six seconds

1. In `tests/test_sel024_gate_record.py` only: the recorder script (`RECORDER`, `_recorder`) blocks until a file the filer thread writes after `F.file_task` returns, with a ceiling (the filer's own 120 s), in place of `time.sleep(a.sleep)` for this test. "The filing lands while the gate runs" then holds by construction. Other tests' use of the recorder keeps its behaviour.
2. Run the file alone ten times. All ten pass, or stop and say in the RESULT what the failures show; do not widen a timeout to get there.

Acceptance:
- `check: sh -c "for i in 1 2 3; do python -m dotenv -f \"$SELDON_PRIMARY_CHECKOUT/.env\" run -- env PYTHONPATH=. python -m pytest tests/test_sel024_gate_record.py -q -p no:cacheprovider || exit 1; done"` passes.

## Part B: the sel018 victim cleans the database it reads

1. In `tests/test_sel018_relative_dispatch_paths.py` only: `test_dispatch_status_reads_the_cap_from_a_worktree` takes the `clean_test_db` fixture.
2. Run the polluter then the victim in that order (`-p no:randomly`, the two node ids from SEL-047's Part B), three times. All pass.
3. Do not change `dispatch status --json`. SEL-047 saw it write a warning line into the stream that carries its JSON; say in the RESULT whether you saw it again. It is filed separately.

Acceptance:
- `check: sh -c "python -m dotenv -f \"$SELDON_PRIMARY_CHECKOUT/.env\" run -- env PYTHONPATH=. python -m pytest tests/test_sel018_relative_dispatch_paths.py -q -p no:cacheprovider"` passes.

## Part C: the union_merge test says why when it fails

1. In `tests/test_dispatch_parallel.py` only: the post-settle assertion of `test_union_merge_of_two_event_appends_is_valid` carries the supervisors' logs in its message, as `_wait_settled` already does on a timeout. Change no timing, no stub and no other test in the file.
2. Run the file alone once.

Acceptance:
- `check: grep -q "union_merge" docs/evidence/sel048/runs.jsonl` passes.

## Part D: the record

1. Run `seldon gate plan --base main` in this worktree and quote its first line in the RESULT. If it prints `full` for any reason but the cadence, stop and say why.
2. The RESULT states, per test: what changed, the runs, and anything seen that Part E of SEL-047 did not predict. This task files nothing and registers nothing.

Acceptance:
- `check: sh -c "! git diff --name-only main...HEAD | grep -v -E '^(cc_tasks/|docs/evidence/sel048/|state/|seldon_events\.jsonl$|tests/test_sel024_gate_record\.py$|tests/test_sel018_relative_dispatch_paths\.py$|tests/test_dispatch_parallel\.py$)'"` passes.
