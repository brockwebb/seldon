# RESULT: SEL-045, SEL-041's kept branch lands, with its RESULT, and no task is filed into any consumer

**Date:** 2026-11-24. **Task:** `09520bb0`. **Branch:** `worktree-modular-knitting-hinton` (the dispatcher merges it).
**Addenda read:** none exist.
Recall used: none. The registration listed eight hits. None was opened: the task file named every input, and SEL-041's
RESULT was read in full from the kept branch.

After this task merges to main:

- `seldon gate plan` and `seldon gate run` exist.
- A project with no `dispatch.gate.slices` is gated exactly as before. hazbrief-mcp's main plans `full`, reason
  `no_slices`, and the one command it would run is its `dispatch.gate_command`, byte for byte
  (`docs/evidence/sel045/hazbrief_no_slices_plan.json`).
- SEL-041's RESULT is at its path on main:
  `cc_tasks/2026-11-21_SEL-041_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points_RESULT.md`.

## For hazbrief-mcp

The same three facts: `seldon gate plan` and `seldon gate run` exist on seldon's main once this merges; with no slices
declared hazbrief's gate is planned `full` (`no_slices`) and runs its `gate_command` unchanged; SEL-041's RESULT,
which HB-218 points to, is at its path on main. Nothing to do beyond what HB-218 already says. No return was filed.
Filing `f478f2ea` is closed with these facts and the merge commit as its note.

## Part A: the branch comes in

- `git merge --no-ff worktree-splendid-seeking-russell` made merge commit **`7a49fd24`** (branch tip `ff9aab8`). It had
  no conflicts; `seldon_events.jsonl` auto-merged by its union attribute. 56 files came in
  (`docs/evidence/sel045/landed.txt` lists them). `ae6c38d` (`gate_timeout_s: 7200`) is in, at `seldon.yaml:219`.
- **What the AD-038-R25 discard dropped.** Event `dc0f38f4` (2026-11-21 19:58Z), evidence
  `docs/evidence/2026-11-21_SEL-041_.../discarded_events.jsonl`. It dropped four lines, all on hazbrief's earlier filing
  `a844c156`: its moves proposed → accepted → in_progress → completed and its claim (`claimed_by: cc`). The claim was
  compensated (set back to null). The move to `completed` could not be walked back (`completed → proposed` is not a
  transition), so it was left `unreconciled`: the live graph said `completed`, main's log said `proposed`.
- **The merge brought those four lines back into main's log.** They stay. The work is now wanted, the state is true,
  and with them the log says `completed`, as the graph does. But they are appended after the compensation, so replay
  in append order would end with `claimed_by: cc` while the graph holds null. One evented `artifact_updated`
  (`fd51fd87`) nulls the claim again. Replay and the live graph now agree on both the state and the claim. The log was
  not edited. The script is `docs/evidence/sel045/recompensate_a844c156.py`, in commit `532e793`.
- **Nothing else needed re-making.** `seldon decision check` gives `register: clean`, and the nine pending records for
  AD-034-R29 to R37 arrived with the merge. ADDENDUM 12's prior-art verdict also arrived with the merge:
  `governed/ledger/events.jsonl`, event `cc63b6af`, pass.
- SEL-041's RESULT is unedited, and its state is unchanged.

## Part B: the tests

- The Part's check ran the three files and gave 48 passed.
- The full suite at `-n 6`, on this branch after the merge: **3,509 passed, 3 failed, 7 skipped, 1,740 s.** All three
  failures were expected:

| failure | fails on main? | alone |
|---|---|---|
| `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` | yes (library drift; SEL-041 and SEL-042 RESULTs) | not re-run |
| `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing` | load flake listed in SEL-041's RESULT | passes |
| `test_dispatch_parallel::test_union_merge_of_two_event_appends_is_valid` | load flake listed in SEL-041's RESULT | passes |

  The two flakes, run alone together: 2 passed in 91 s.
- **Item 6.** I made a `git clone --shared` of hazbrief-mcp's main (`01049510`) under `/tmp/sel045` and ran
  `seldon gate plan --json` there; it gave tier `full`, reason `no_slices`, and 197 of 197 test files.
  `docs/evidence/sel045/hazbrief_plan.py` builds the same plan and asks the runner's own step function (`_steps`) what
  it would run. It finds one `full` step, whose command equals `dispatch.gate_command` from a plain YAML load of
  hazbrief's `seldon.yaml`, byte for byte (`true`). The gate was not run, and the clone is deleted.

## Part C: the record

- `docs/evidence/sel045/landed.txt` holds the merge commit, the 56 files, the suite counts and item 6 in one line.
- Issue `aa93bfb4` is now `remediated_by` `09520bb0` and `verified_by` four tests:
  `test_sel041_gate_call_sites.py::test_a_project_without_slices_runs_its_gate_command_and_records_it`,
  `::test_a_documents_only_task_merges_on_a_scoped_gate_without_the_full_suite`,
  `test_sel041_gate_plan.py::test_a_project_without_slices_plans_full_as_before` and
  `test_sel042_stopped_session_never_merges.py::test_a_normal_green_finish_merges_on_the_rounds_own_gate`. Its state is
  left `open`, because the task did not ask for a transition.
- Filing `f478f2ea` was closed with `seldon task close`, moving proposed → completed. No `seldon cc return` was run.

## Deviations and open items

- **The four discarded lines re-entered main's log through the merge.** `drop_reconciled` handles only lines that a
  `kept_events_reconciled` appended; it has no case for a discarded task whose branch later merges. This is the first
  such merge. I resolved it by keeping the lines and adding one compensating event, for the reasons in Part A. The
  machine has no rule for this case yet. A future redrive of a superseded task's kept branch would hit the same gap.
  That gap is a design question for AD-038, and this task does not decide it.
- After this merge, seldon's next gate is full (`cadence_due`), as SEL-041's RESULT says.
