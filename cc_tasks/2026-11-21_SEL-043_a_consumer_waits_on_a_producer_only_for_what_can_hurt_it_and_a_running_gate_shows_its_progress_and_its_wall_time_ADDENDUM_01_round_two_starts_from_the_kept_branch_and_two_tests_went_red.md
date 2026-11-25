# SEL-043 ADDENDUM 01: round two starts from the kept branch, and two tests went red in the merge round's full gate

**Author:** Desktop session (seldon, SLD-3), 2026-11-24 20:55 EST, from the OODA on SEL-043 round one (`merge_blocked: regate_red`, Issue `0a3097ab`).
**Amends:** how the round starts, and adds one piece of work before the RESULT. The task's Parts and Acceptance lists are unchanged.

## What happened (read from the event store and the gate log)

Round one finished its six Parts and its Stop gate passed (verdict pass, no failed check). The merge round then ran the full `gate_command` as tier `full`, reason `conftest: tests/conftest.py`, for 5,176 s and it ended red: 2 failed, 3,538 passed, 7 skipped, 1 deselected. Log: `logs/dispatch/2026-11-21_SEL-043_a_consumer_waits_on_a_producer_only_for_what_can_hurt_it_and_a_running_gate_shows_its_progress_and_its_wall_time.gate.log` in the primary checkout.

The two failures:

- `tests/test_friction002_stop_hook_gate.py::test_a_session_let_go_with_its_gate_unpassed_is_never_merged[passing]`, line 192: the finish record says `merged` and the gate verdict is `pass`, and `task_states(...)["a"]` is `blocked` where `completed` is expected.
- `tests/test_friction002_worktree_only.py::test_an_unmerged_task_keeps_its_worktree_and_branch_with_a_worktree_kept_record`, line 120: the stub exits 1, and `task_states(...)["a"]` is `completed` where `blocked` is expected.

Neither is one of the three failures every earlier full run listed (the pa002 test, now deselected, and the two load failures of Issue `d6040ce8`). SEL-045's full run of main's tree before this branch had these two green. Not established: whether they fail alone, fail only after certain other tests, or fail only under a long serial run. One observation, not a finding: `task_states` in `tests/dispatch_scaffold.py` keys its result by task NAME, both tests name their task `a`, and each got the state the other expects, so a second `a` node in the test database would produce exactly this. This branch changed `tests/dispatch_scaffold.py`, `tests/conftest.py` and added `tests/r9_shim.py`.

## How round two starts

Do not redo the Parts. The work is on kept branch `worktree-iterative-moseying-clock`. Measured in a scratch clone before this was written: its 29 commits replay onto main with no conflict.

Before any commit of your own:

1. Note this branch's tip: `git rev-parse HEAD`.
2. `git reset --hard worktree-iterative-moseying-clock`
3. `git rebase <the tip noted in step 1>`
4. Any stop is a finding: `git rebase --abort`, `git reset --hard <the tip noted in step 1>`, write the RESULT saying so, and end.

Do not remove duplicated event lines yourself; the merge round drops them.

## The added work

1. Run the two test files alone on the replayed branch. Record pass or fail for each.
2. If they pass alone, find what makes them fail: run them after the test files that sort before them, narrowing by halves, until the smallest set that reproduces it is known. Record it.
3. Fix the cause. Do not change what either test asserts, do not deselect or skip either, and do not change `gate_command`. If the cause is in code or tests this branch did not touch, say so in the RESULT's first line and fix it anyway only if the fix is under twenty lines; otherwise stop there.
4. If neither step 1 nor step 2 reproduces a failure, say exactly that in the RESULT's first line with what was run, and change nothing.
5. `docs/evidence/sel043/round_two.txt`: the replayed tip, what steps 1 and 2 ran and their counts, the cause, the fix, and the two test files' counts after it.

The RESULT from round one stays; add a short "Round two" section at its top. File no task into any other repository in this round beyond what the task file's own Parts already wrote on the kept branch.
