# RESULT: SEL-046, the merge round drops a line main already holds, whichever task it was reconciled for

The change is on branch `worktree-immutable-sleeping-treehouse` and reaches main only when the dispatcher merges it.
The measurement matches what the task expected (14, 14, 0).

Recall used: seldon:AD-038-R25, seldon:2026-11-09_SEL-034_a_terminal_task_stops_its_session_and_a_kept_worktrees_events_reach_mains_log_or_are_discarded_on_record_RESULT

## Part A
- `seldon/core/kept_events.py`: `reconciled_ids(project_dir, store_rel, task_id=None)`. With no task id it returns
  the ids of every `kept_events_reconciled` record on main's store. With a task id it behaves as before; the two
  existing callers in the SEL-034 and SEL-042 tests still pass. The cheap line pre-filter stays: a line is parsed
  only if it contains the record's name, and also the task id when one is given. I rewrote the docstring of
  `drop_reconciled` and its commit message to say the line may belong to another task whose branch this one merged.
- `seldon/commands/dispatch_worktree.py` `_merge`: `reconciled = KE.reconciled_ids(project_dir, store)` (all
  tasks). Nothing else in the round changed. `kept_events_deduped` still names the finishing task.
- `tests/test_sel046_merged_kept_branch_dedupes.py` has 2 tests, built on the SEL-034 fixtures. The first sets up
  the case: X is kept and reconciled under its own id, Y merges X's branch, main moves and Y rebases. It then shows
  the defect: looking up Y's task finds nothing, and the union check names exactly X's ids. Next it checks the fix:
  the all-task lookup holds X's ids, `drop_reconciled` drops them, the union check passes, the tree is clean, and
  after the fast-forward each id appears once. The second test checks that a later copy under one id that DIFFERS
  is not dropped, and that `check_union_text` still names that id.
- Acceptance: `tests/test_sel046… tests/test_sel034… tests/test_sel042…`: **18 passed** (213 s), Neo4j live.
  On main the first test fails, because `reconciled_ids` there requires a task id.

## Part B
- `docs/evidence/sel046/measured.txt`, made by `docs/evidence/sel046/measure.py` from `git show` of the two blobs:
  14 ids held twice, 14 returned by the all-task lookup, 0 not returned. The old lookup on SEL-045R's full id
  returned 0. All 14 are under SEL-045's record `09520bb0`.

Not touched: SEL-045R, its branch, its worktree, Issue `1a448a6f`. No full-suite run (the task's spend basis).
