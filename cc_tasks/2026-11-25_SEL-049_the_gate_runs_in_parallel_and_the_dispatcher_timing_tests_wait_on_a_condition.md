# SEL-049: the gate runs in parallel, and the dispatcher timing tests wait on a condition instead of racing a clock

**Status:** proposed
**Author:** Desktop session (factory coordinator, FCT-4), 2026-11-25 22:45 EST, from SEL-047's RESULT and `docs/evidence/sel047/README.md` Part E items 1, 2 and 5. Answers factory filing `a8863e12` (F-027 item 1) and Issue `d6040ce8`'s two "load" tests.
**Repo:** seldon only. No other repository is written. L4: commit on the task branch; the dispatcher merges.
**After:** 2026-11-25_SEL-048_three_timing_and_order_tests_are_fixed_in_their_own_test_files_on_a_scoped_gate
**Governing:** AD-034-R29 to R37 (AD-034 ADDENDUM 12); AD-034-R26 (a merge gates on `gate_command`). No new ruling: `gate_command` gains `-n 6`, which the scoped tier's `test_command` already uses at `-n 4`.
**Gate:** full
**Model:** primary
**Spend:** est. 0.9M tokens. Basis: SEL-047 ran 59 detached runs and wrote its evidence for under 0.3M; this changes one scaffold file, one test file and one configuration line, then runs about fifteen single-file runs and one full parallel suite, detached and polled. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.45, B 0.25, C 0.3.
**Premises:**
- premise: SEL-048's recorder fix is on main | check: sh -c "! grep -q 'time.sleep(a.sleep)' tests/test_sel024_gate_record.py || grep -q 'F.file_task' tests/test_sel024_gate_record.py"
- premise: the gate is still serial | check: sh -c "! grep -A3 '^  gate_command:' seldon.yaml | grep -q -- '-n 6'"
- premise: the stubs still overlap by a fixed sleep | check: grep -q 'spec.get("sleep")' tests/dispatch_scaffold.py

## Why, and what this task costs the queue (from the code and SEL-047's measurement)

Seldon's merge gate is serial: 81 to 96 minutes on quiet nights, 124 minutes (7,463 s, over the 7,200 s ceiling) under a neighbour's load, holding the lease other repositories wait on. At `-n 6` the same suite took 2,193, 2,269 and 2,508 s the same afternoon, and about 26 minutes on quiet nights. But every `-n 6` run failed `test_dispatch_parallel.py::test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` (3 of 3; also 3 of 20 alone), and two wall-clock budget tests in that file failed in 1 of 3. The gate cannot go parallel until those wait on a condition.

**This task's merge runs main's serial `gate_command` under main's 7,200 s ceiling, once** (`seldon/commands/dispatch_worktree.py`, `_gate`: the command and the timeout are read from the primary's `seldon.yaml`, and the plan is full: `gate_config_changed`, `unmatched: tests/dispatch_scaffold.py`). It holds the lease about 81 to 124 minutes. Nothing here can shorten that one run. If it comes back red, read the gate log and say in the RESULT exactly which tests failed; a second red parks this task (factory F-027 item 2).

Read `docs/evidence/sel047/README.md` Parts B and E in full first. Every run longer than two minutes is detached under `caffeinate -i` and polled; runs use the gate's own form. Record each run as a line in `docs/evidence/sel049/runs.jsonl` (`run, command, started_at, ended_at, wall_s, load_before, passed, failed, failed_ids`).

## Part A: overlap by rendezvous, budgets as ceilings on a waited condition

1. `tests/dispatch_scaffold.py`: a stub spec may ask for a rendezvous: the stub writes its `start` mark and waits, with a ceiling, until every named peer's mark exists, then proceeds. `sleep` keeps working for the tests that use it. 44 test files import the scaffold; change nothing else in it.
2. `tests/test_dispatch_parallel.py`: `test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` gets its overlap from the rendezvous, not from `sleep: 3` covering the second launch. `test_a_killed_supervisor_...` and `test_an_exclusive_task_waits_...` replace their explicit wall-clock budgets (`< 30` s) with a wait on the condition they mean, under a ceiling. What each test asserts about ordering and state does not weaken: say in the RESULT, per test, what is asserted before and after.
3. Run `tests/test_dispatch_parallel.py` alone ten times. `two_disjoint` and the two budget tests pass ten of ten. `test_union_merge_of_two_event_appends_is_valid` may still fail (2 of 20, cause not determined; SEL-048 made its failure message carry the logs): if it does, copy that message into the RESULT and do not fix it here.

Acceptance:
- `check: python -c "import json; r=[json.loads(l) for l in open('docs/evidence/sel049/runs.jsonl')]; a=[x for x in r if x['run'].startswith('alone_dispatch_parallel')]; assert len(a) >= 10; bad=[i for x in a for i in x.get('failed_ids',[]) if 'union_merge' not in i]; assert not bad, bad"` passes.

## Part B: the full tier runs at -n 6

1. `seldon.yaml`: `dispatch.gate_command` gains `-n 6`. The `--deselect` of pa002's live-library test stays (SEL-050 removes it). The comment above it states the measured basis (SEL-047: serial 7,463 s against 2,193 to 2,508 s under the same load; 25:40 and 25:51 quiet, SEL-042) and that pytest-randomly reorders every gate run. `gate_timeout_s` stays 7,200 and its comment says why it is now generous.
2. Any test that pins the command's text is brought to the new text; say which.
3. One whole-suite run with the new command exactly as `gate_command` reads, detached. Record it. It passes with zero failures, or with `union_merge` alone failing; anything else is fixed here only if it is one of this task's three tests, and otherwise named in the RESULT and the task stops before its RESULT claims green.

Acceptance:
- `check: sh -c "grep -A3 '^  gate_command:' seldon.yaml | grep -q -- '-n 6'"` passes.
- `check: python -c "import json; r=[json.loads(l) for l in open('docs/evidence/sel049/runs.jsonl')]; f=[x for x in r if x['run'].startswith('full_n6')]; assert f; bad=[i for i in f[-1].get('failed_ids',[]) if 'union_merge' not in i]; assert not bad, bad"` passes.

## Part C: the record, and what the next gate will cost

1. `docs/evidence/sel049/README.md`: the ten alone runs, the full run, and from them the lease hold a seldon merge now costs, beside SEL-047's serial figures.
2. The RESULT's first lines say: the three tests' before and after; whether the full `-n 6` run was green; and that this merge's own gate is the last serial one.
3. This task files nothing into any repository. Factory reads the RESULT.

Acceptance:
- `check: grep -q "lease" docs/evidence/sel049/README.md` passes.
- `check: sh -c "! git diff --name-only main...HEAD | grep -v -E '^(cc_tasks/|docs/evidence/sel049/|state/|seldon_events\.jsonl$|seldon\.yaml$|tests/)'"` passes.
