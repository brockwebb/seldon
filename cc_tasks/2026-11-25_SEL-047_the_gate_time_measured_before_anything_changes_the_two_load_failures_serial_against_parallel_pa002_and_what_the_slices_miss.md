# SEL-047: seldon's gate time measured before anything changes: the two "load" failures, serial against parallel, pa002, and what the slices miss

**Status:** proposed
**Author:** Desktop session (factory coordinator, FCT-4), 2026-11-25 11:05 EST, from factory F-027 item 1 (filing `a8863e12`) and SLD-3's handoff first action, item 2.
**Repo:** seldon only. No other repository is written. L4: commit on the task branch; the dispatcher merges.
**After:** none
**Governing:** AD-034-R29 to R37 (AD-034 ADDENDUM 12, the scoped gate); AD-034-R26 (a check-less merge gates on `gate_command`). No new ruling: this task measures and changes no code, test or configuration.
**Model:** primary
**Spend:** est. 1.0M tokens. Basis: four full-suite runs and about forty single-file runs, each launched detached and polled (about 3 hours of wall time, mostly waiting); one read of one test file and its two code paths; one scan of git history with the existing planner; one evidence README. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.10, B 0.45, C 0.15, D 0.20, E 0.10.
**Premises:**
- premise: the scoped tier is on main | check: grep -q "test_command:" seldon.yaml
- premise: SEL-043's scaffold fix is on main | check: grep -q "def register" tests/dispatch_scaffold.py
- premise: pa002 is still deselected by name | check: grep -q "deselect tests/test_pa002_release_resolve.py" seldon.yaml

## Why, and what this task costs the queue (stated from the code before registration)

Seldon's merge gate held its lease 5,176 s, 4,854 s and 5,788 s on 2026-11-25 (`gate_run` records, call site `merge_gate`), and every other repository's dispatcher waited on it. Issue `d6040ce8` names three tests waved off at every merge since 2026-11-09: `test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index` (reads squiddy's live library), `test_sel024_gate_record` (lock_wait) and `test_dispatch_parallel`, the last two called "load". SLD-3 found that dispatcher scenarios shared one test database and task names, which SEL-043 fixed in `tests/dispatch_scaffold.py`, and that `test_dispatch_parallel` failed in that round's bisect the same way. That is the order-dependent kind Lam et al. describe (iDFlakies, ICST 2019: a polluter and a victim), and Luo et al. (An Empirical Analysis of Flaky Tests, FSE 2014) rank async wait, concurrency and test-order dependency as the leading causes. So "load" is a hypothesis, measured here before the gate is changed.

This task's own gate, from `seldon/core/gate_plan.py` and `seldon.yaml` on main at 593e07a:

- It may change only `cc_tasks/**` (slice `task_records`, 3 test files), `docs/evidence/sel047/**` (slice `documents`, 23 files), `state/**` (slice `ledgers`, 11 files) and `seldon_events.jsonl` (slice `event_store`, `tests: none`). Every path matches a slice, no `conftest.py`, no `seldon.yaml` gate key, no full path: the plan is **scoped**, about 30 of 205 test files at `-n 4`.
- The cadence (`full_every_s: 86400`) turns it full if no passing full gate is newer than a day. The last passing full gate is 2026-11-25T08:51:20Z (SEL-044's merge gate). A merge after 2026-11-26T08:51Z gates full and holds the lease about 90 minutes. That is the one way this task costs the queue a full gate.
- The merge round reads `dispatch.gate_command` from the primary's `seldon.yaml` (`seldon/commands/dispatch_worktree.py`, `_gate`, `cfg` from `D.load_dispatch_config(project_dir)`), not the branch's. A later task that moves `gate_command` to `-n` therefore gates its own merge on main's serial command, and full (`gate_config_changed`): one more 81-to-96-minute lease, paid once. Part E states it for that task.
- There is no scoped `gate_run` on seldon's record yet. This task's is the first, and its seconds are evidence too.

## Rules for every run in this task

- Every command longer than a few minutes is launched detached (`nohup ... > <log> 2>&1 &`, under `caffeinate -i` so the Mac does not sleep: SLD-3 lost an hour of SEL-045R that way) and polled. Never block a tool call on a full suite.
- Every suite run uses the worktree's code and the primary's credentials, exactly as `gate_command` does: `python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest ...`, with `-p no:cacheprovider`. Pass `-n`, `-p no:randomly`, `--deselect` and `-v` on the command line. **Do not edit `seldon.yaml`, any test, `conftest.py`, `tests/dispatch_scaffold.py` or anything under `seldon/`.**
- Before and after every run, record `uptime` (load average) and the count of running `pytest` processes on the machine (`pgrep -f pytest | wc -l`). hazbrief's HB-230 may be running beside this task; record it, do not wait for it.
- Every run is one JSON line in `docs/evidence/sel047/runs.jsonl`: `{run, command, started_at, ended_at, wall_s, load_before, load_after, pytest_procs_before, pytest_procs_after, passed, failed, errors, failed_ids, log}`. Logs go to `docs/evidence/sel047/logs/` (each log trimmed to its failures and its summary if over 2 MB; say so in the line).

## Part A: what the planner says from the primary

1. From the primary checkout (`$SELDON_PRIMARY_CHECKOUT`), run `seldon gate plan` and `seldon gate plan --json`. No thread has run it from the primary since SEL-045R landed (SLD-3's handoff). Save both to `docs/evidence/sel047/gate_plan_primary.txt`.
2. In this worktree, after Part D's files exist, run `seldon gate plan --base main` and append it to the same file. It must print `scoped`. If it prints `full`, stop and write why in the RESULT before any further run: the premise of this task's cost is wrong.

Acceptance:
- `check: grep -q "scoped" docs/evidence/sel047/gate_plan_primary.txt` passes.

## Part B: the two "load" failures and serial against parallel (Issue d6040ce8, SLD-3 items a and c)

1. **Alone.** Run `tests/test_sel024_gate_record.py` and `tests/test_dispatch_parallel.py`, each by itself, serial, 20 times each. Record each run.
2. **In the suite, serial.** One full run with `gate_command`'s arguments as they stand (serial, pa002 deselected), plus `-v` so the order is in the log. This is also the serial wall time for item 4.
3. **In the suite, parallel.** Three full runs at `-n 6`, otherwise identical, with `-v` (the log names each test's worker, `[gwN]`).
4. **Serial against `-n 6`.** From items 2 and 3: wall seconds, pass/fail counts, and which test ids failed in which run, beside the earlier figures (81 to 96 minutes serial in the three merge gates; 26 to 29 minutes at `-n 6` in SEL-041 and SEL-042). Say whether any test fails at `-n 6` and not serial, and the reverse.
5. **Classify each of the two tests** by iDFlakies' scheme (Lam et al. 2019), from what was observed only:
   - fails alone in any of 20: non-order-dependent; report the rate.
   - passes alone 20 of 20, fails in a suite run: order-dependent candidate. Find the polluter: from that run's log, take the tests that ran before the victim in the same process (same `[gwN]` worker, or all earlier tests serial), and run `<candidate file> <victim>` in that order, halving the candidate list each time (delta debugging, as iDFlakies does). Stop at one polluter file or after 45 minutes of wall time, and record what was tried.
   - never fails in any run: report 0 of N with N stated, and the load average range it was observed under. That is a result, not a missing one.
6. Write the table and the classification to `docs/evidence/sel047/README.md`, section "Part B".

Acceptance:
- `check: sh -c "test $(grep -c . docs/evidence/sel047/runs.jsonl) -ge 44"` passes.
- `check: grep -q "^## Part B" docs/evidence/sel047/README.md` passes.

## Part C: what pa002's deselected test needs (SLD-3 item b), read only

1. Read `tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index` and the code it reaches in `seldon/core/prior_art.py`. State which seldon function it exercises and which part of its assertion is about seldon's code and which is about squiddy's library on disk.
2. Read squiddy's release check (its stage 18, release-receipt; search squiddy's `docs/` and `squiddy/` read-only) and state whether it already asserts the same property (a rebuilt served release reproduces the served index).
3. Run the test alone once on main and record the failure text.
4. State, with the evidence above, which of the two exits Issue `d6040ce8` names fits: the test owns a fixture (say how small a committed library would exercise the same seldon path), or it leaves the gate for a check where squiddy's release already runs it. Do not write the fixture.
5. Write it to the README, section "Part C".

Acceptance:
- `check: grep -q "^## Part C" docs/evidence/sel047/README.md` passes.

## Part D: what the slices miss (SLD-3 item d)

1. For every task merge on seldon's main since 2026-10-25 (`git log --first-parent main`, the dispatcher's merge commits and fast-forwards that close a task), make a scratch worktree at the commit, run `seldon gate plan --base <its first parent> --json`, and remove the scratch worktree. Use `git worktree add --detach` under a temporary directory outside the repository.
2. Tabulate per merge: task, tier, first reason, all reasons, unmatched paths. Then count, over all merges, how often each unmatched path's top two directory levels sent a merge full (for example `seldon/commands/`, `tests/dispatch_scaffold.py`).
3. State which full reasons are by design (a change under `seldon/` is unmatched on purpose: the `seldon.yaml` comment above `gate:` and SEL-041's evidence) and which are paths a slice could name without the planner losing its fail-safe default (Saltzer and Schroeder, as AD-034 ADDENDUM 12 cites it). Do not edit the slices.
4. Save the table as `docs/evidence/sel047/slice_misses.json` and the summary in the README, section "Part D".

Acceptance:
- `check: python -c "import json; d=json.load(open('docs/evidence/sel047/slice_misses.json')); assert len(d) >= 10"` passes.
- `check: grep -q "^## Part D" docs/evidence/sel047/README.md` passes.

## Part E: what the change task should be, from this evidence

1. In the README, section "Part E", state from Parts B to D, each point with its evidence line: whether `gate_command` should run at `-n 6`; what each of the two "load" tests needs; which exit pa002 takes; which paths a slice should name. Then state the tier the change task will gate at and its lease hold: full (`gate_config_changed`, and main's serial `gate_command` is the one that runs), one serial run measured in Part B item 2.
2. If the evidence says one of the changes can land on its own on a scoped gate (a test file alone matches `test_globs` and runs as a changed test), say so: a change that can gate light should not wait for the one that cannot.
3. This task files nothing into any other repository and registers no task. Factory writes the change task from this RESULT.
4. Before the RESULT, run `seldon gate plan --base main` in this worktree and quote its first line in the RESULT.

Acceptance:
- `check: grep -q "^## Part E" docs/evidence/sel047/README.md` passes.
- `check: sh -c "! git diff --name-only main...HEAD | grep -v -E '^(cc_tasks/|docs/evidence/sel047/|state/|seldon_events\.jsonl$)'"` passes.
