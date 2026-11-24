# SEL-045R: the finished gate work reaches main, on checks the Stop gate actually reads

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-24 12:50 EST, from the OODA on SEL-045 (`09520bb0`, blocked `merge_blocked: regate_red`). Resumes SEL-045, which this task supersedes.
**Repo:** seldon only. No other repository is written. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-034-R26 (a merge needs gate evidence; a Stop gate that ran at least one check is evidence); AD-037-R1 and `seldon/core/criteria.py` (what a check is and where it is read); AD-034 ADDENDUM 12 as it stands on the kept branch; Issue `d6040ce8` (the full gate cannot pass on main).
**Model:** primary
**Spend:** est. 0.25M tokens. Basis: one merge of a finished branch, three test files, one line of configuration, one record. No full-suite run: SEL-045 ran it on this tree (3,509 passed, the three listed failures, 1,740 s). Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.5, B 0.3, C 0.2.
**Premises:**
- premise: SEL-045's kept branch exists | check: git rev-parse --verify --quiet worktree-modular-knitting-hinton
- premise: main does not carry the gate planner | check: sh -c "! test -f seldon/core/gate_plan.py"

Read first: SEL-045's task file on main and its RESULT on the kept branch (`git show worktree-modular-knitting-hinton:cc_tasks/2026-11-24_SEL-045_sel041s_kept_branch_lands_on_main_with_no_task_filed_into_any_consumer_RESULT.md`).

## The condition (measured 2026-11-24)

SEL-045 did its work: branch `worktree-modular-knitting-hinton` holds SEL-041's merge (`7a49fd24`), the full suite at `-n 6` green but for three listed failures, and its RESULT. It did not merge. Its Parts each carried a bare `check: <command>` line under the Part heading, the form seldon's own SEL-042 RESULT told consumers to use. `seldon/core/criteria.py` reads a criterion only as a list item under an `Acceptance:` label (or an Acceptance heading), and reads every list item under that label as a criterion until the next heading. So the Stop gate parsed zero checks, the round ran the serial `gate_command` as its evidence gate, and that was killed at main's 3,600 s timeout at 81 percent (`EXIT=-9`, `logs/dispatch/2026-11-24_SEL-045_*.gate.log`). hazbrief measured the same on HB-221 and HB-222 (`"checks": []`, `checks_run: 0`; filing `1e367024`). The seldon run held seldon's lease for about 100 minutes and hazbrief's ready queue waited on it.

SEL-045 also closed hazbrief's filing `f478f2ea` as landed before its merge, as its task file ordered. That statement was false for the hours since, and hazbrief found it so.

This task states its checks in the form `criteria.py` reads and `tests/stations_scaffold.py` uses: the last thing in each Part, under `Acceptance:`, with nothing but checks in that list. The first draft of this file put the steps after the label and registration refused it (`criterion_unmarked`, seven items), which is the parser working.

## Part A: the branch comes in, and the checks are seen

1. **Before any other work**, confirm what the dispatcher will read from this file: `python -c "from pathlib import Path; from seldon.core import criteria as c; print(c.acceptance_criteria(Path('cc_tasks/2026-11-24_SEL-045R_the_finished_gate_work_reaches_main_on_checks_the_stop_gate_reads.md').read_text()))"` must list exactly four criteria, each beginning `check:`. If it lists anything else, stop and write the RESULT saying so; merge nothing.
2. Merge `worktree-modular-knitting-hinton` into this task's branch (a merge; keep its commits). It brings SEL-041's work, SEL-045's evidence and RESULT, and `gate_timeout_s: 7200`. A code conflict is a finding and stops the Part.

Acceptance:
- `check: test -f seldon/core/gate_plan.py` passes.

## Part B: the tests, and one line of configuration

3. Run this Part's first check yourself before the Stop gate does. Do not run the full suite.
4. In `seldon.yaml`, `dispatch.gate_command` gains `--deselect tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index`, with a comment beside it naming Issue `d6040ce8` and the reason: the test reads squiddy's live library and has failed on main in every recorded run since 2026-11-09, so with it in the command no full gate can be green. Change nothing else about which tests run. The test file stays; the Issue stays open.

Acceptance:
- `check: sh -c "python -m dotenv -f .env run -- env PYTHONPATH=. python -m pytest tests/test_sel041_gate_plan.py tests/test_sel041_gate_call_sites.py tests/test_sel042_stopped_session_never_merges.py -q -p no:cacheprovider"` passes.
- `check: grep -q d6040ce8 seldon.yaml` passes.

## Part C: the record, and nothing said before it is true

5. `docs/evidence/sel045r/landed.txt`: the merge commit, the criteria item 1 printed, the Part B test counts, and the `gate_command` line as changed.
6. RESULT, short. Its first line states what is true at the time of writing: the work is on this branch and reaches main only when the dispatcher merges it. Say what the Stop gate recorded for each Part (`checks` and `checks_run`), read from the event store after the hook ran if the session can see it, otherwise say it cannot.
7. Close nothing, file nothing, tell no other repository anything. The Desktop thread reads the merge record and answers hazbrief's filings itself.

Acceptance:
- `check: test -s docs/evidence/sel045r/landed.txt` passes.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.35M.

## Deliverables

The kept branch's work on this task's branch; four criteria parsed; the one configuration line; the evidence file; `cc_tasks/2026-11-24_SEL-045R_the_finished_gate_work_reaches_main_on_checks_the_stop_gate_reads_RESULT.md`.
