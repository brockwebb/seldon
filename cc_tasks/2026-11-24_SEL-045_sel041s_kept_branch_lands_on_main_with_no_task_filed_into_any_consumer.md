# SEL-045: SEL-041's kept branch lands on main, with its RESULT, and no task is filed into any consumer

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-24 00:30 EST. Answers hazbrief-mcp's filing `f478f2ea` (`cc_tasks/2026-11-24_filing_from_hazbrief_hb218_cannot_be_applied_sel041_is_not_on_main.md`). The operator lifted his hold of 2026-11-21 in hazbrief's thread at 23:52 EST on 2026-11-23, after the GSA submission, and sent this thread to the filing at 00:02 EST.
**Repo:** seldon only. No other repository is written: no return task, no file, no graph write. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-034 (R5 merge on green; R25, R26 from SEL-042: a stopped session never merges, and a merge needs gate evidence, of which a Stop gate that ran a `check:` is one); AD-034 ADDENDUM 12 as it stands on the kept branch (R29 to R37); AD-038-R25 (a superseded task's unlogged events are discarded on record); AD-033-R12 (pending records are numbered at merge).
**Model:** primary
**Spend:** est. 0.5M tokens. Basis: one merge of a finished branch, its tests, one full-suite run at `-n 6` (26 to 29 minutes in SEL-041 and SEL-042), one record. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.45, B 0.35, C 0.20.
**Premises:**
- premise: the kept branch exists | check: git rev-parse --verify --quiet worktree-splendid-seeking-russell
- premise: SEL-041's RESULT is on that branch | check: git cat-file -e worktree-splendid-seeking-russell:cc_tasks/2026-11-21_SEL-041_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points_RESULT.md
- premise: main does not carry the gate planner | check: sh -c "! test -f seldon/core/gate_plan.py"

Read first: SEL-041's task file, its ADDENDUM 01, and its RESULT on the kept branch (`git show worktree-splendid-seeking-russell:cc_tasks/2026-11-21_SEL-041_..._RESULT.md`), all of it.

## The condition

SEL-041 finished on 2026-11-21: its code, its rulings (AD-034 ADDENDUM 12), its tests and its RESULT are committed on `worktree-splendid-seeking-russell`. It is not on main for two reasons. (1) The Desktop thread marked the task `superseded` at 14:30 EST that day, on the operator's word "hold", as the one state the round is certain not to merge. Nothing overtook it; the word was used as a stop. (2) The round's merge gate had no chance anyway: since SEL-042 (AD-034-R26) a seldon task whose Parts declare no `check:` is gated at merge by the serial `gate_command`, which takes about 82 minutes against main's 3,600 s timeout, and which contains a test that fails on main (`test_pa002_release_resolve`). Issue `aa93bfb4` records `regate_red`.

hazbrief's HB-218 (SEL-041's return) tells hazbrief to declare `dispatch.gate.slices` and check them with `seldon gate plan`. The seldon that answers hazbrief has no `gate` command, and the RESULT HB-218 points to is not at its path on main. hazbrief's thread holds HB-218 on this.

This task's own merge does not go through the serial gate: each Part below carries a `check:`, so its Stop gate is the evidence (AD-034-R26).

## Part A: the branch comes in

check: test -f seldon/core/gate_plan.py

1. In this task's worktree, merge `worktree-splendid-seeking-russell` (a merge, keeping its commits; do not rebase or squash it). Union-merged journals resolve by attribute. Anything else that conflicts is reported and stops the Part; main has moved only in records since the branch was cut, so a code conflict is a finding.
2. SEL-041 is `superseded`, so AD-038-R25 discarded its session's unlogged events on record and compensated their graph effects. Find that evidence file and say what was discarded. Re-make only what main needs and the merge does not bring: the pending register records for AD-034-R29 to R37 if `seldon decision check` says they are missing (through `seldon decision accept`, never by hand), and the addendum's prior-art verdict if `prior-art verify` has none on record.
3. SEL-041's RESULT arrives with the merge at `cc_tasks/2026-11-21_SEL-041_..._RESULT.md`. Do not edit it. The timeout commit `ae6c38d` (`gate_timeout_s: 7200`) arrives with the branch; confirm it is in.
4. Do not change SEL-041's state (terminal). The Desktop thread records that this task overtook it.

## Part B: the tests

check: sh -c "python -m dotenv -f .env run -- env PYTHONPATH=. python -m pytest tests/test_sel041_gate_plan.py tests/test_sel041_gate_call_sites.py tests/test_sel042_stopped_session_never_merges.py -q -p no:cacheprovider"

5. Run the whole suite once at `-n 6` (`python -m dotenv -f .env run -- env PYTHONPATH=. python -m pytest tests/ -q -p no:cacheprovider -n 6`), detached with a log and polled to its end. Expected failures, and no others: `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` (fails on main), and the load flakes SEL-041's RESULT lists, each of which must pass when run alone. Any other failure stops the task with the failure named. List every failure in the RESULT with whether it fails on main.
6. Prove the claim hazbrief depends on, on real configuration and read only: with hazbrief-mcp's `seldon.yaml` as it stands (a `gate_command`, no slices), `seldon gate plan --json` in a `git clone --shared` of hazbrief's main under `/tmp` plans `full`, reason `no_slices`, and the command it would run is hazbrief's `gate_command` byte for byte. Do not run that gate. Write the plan to `docs/evidence/sel045/hazbrief_no_slices_plan.json` and delete the clone.

## Part C: the record

check: test -s docs/evidence/sel045/landed.txt

7. `docs/evidence/sel045/landed.txt`: the merge commit, the files of SEL-041 now on this branch, the suite's counts, and item 6's plan in one line.
8. Update Issue `aa93bfb4` (`remediated_by` this task, `verified_by` Part B's test files).
9. RESULT, short and plain. Its first lines say what a consumer needs: after this task's merge, `seldon gate plan` and `seldon gate run` exist; a project with no slices is gated exactly as before (item 6's evidence); SEL-041's RESULT is at its path on main. Then a section "For hazbrief-mcp" with the same three facts and nothing to do beyond what HB-218 already says.
10. File NO return (`seldon cc return` is not run). Close the filing with `seldon task close f478f2ea --note "<the three facts and this task's merge commit>"` as the last step before the RESULT's final commit. The Desktop threads tell each other; a notice does not run a consumer's gate.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.65M.

## Deliverables

SEL-041's work on main with its RESULT; the three checks green; the evidence files; Issue `aa93bfb4` updated; the filing closed; `cc_tasks/2026-11-24_SEL-045_sel041s_kept_branch_lands_on_main_with_no_task_filed_into_any_consumer_RESULT.md`.
