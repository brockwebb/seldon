# SEL-046: the merge round drops a line main already holds, whichever task it was reconciled for

**Status:** proposed
**Author:** Desktop session (seldon, SLD-3), 2026-11-24 14:50 EST, from the OODA on SEL-045R (`8315cc7a`, blocked `merge_blocked: union_invalid`, Issue `1a448a6f`).
**Repo:** seldon only. No other repository is written. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-038-R25 (AD-038 ADDENDUM 11: a kept worktree's lines reach main's store, and main never holds an event id twice); AD-034-R27 (the `kept_events_deduped` record is written once nothing stands before the fast-forward). No new ruling: the rule is about the event id, and the code looks it up by the finishing task.
**Model:** primary
**Spend:** est. 0.3M tokens. Basis: one function widened, one call site, one new test file, two existing test files run. No full-suite run. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.7, B 0.3.
**Premises:**
- premise: the lookup is still keyed on one task id | check: grep -q "def reconciled_ids(project_dir: Path, store_rel: str, task_id: str)" seldon/core/kept_events.py
- premise: SEL-045R's kept branch exists | check: git rev-parse --verify --quiet worktree-cached-noodling-minsky

## The condition (measured 2026-11-24, read-only, from the primary)

SEL-045R's session finished in 11 minutes and its Stop gate passed with four checks run (A 1, B 2, C 1). The merge round then refused the branch: `union_invalid`, file `seldon_events.jsonl`.

- The tip of `worktree-cached-noodling-minsky` holds 14 event ids twice. Each pair is byte-identical and each id is already on main. Zero malformed lines.
- The 14 are SEL-045's lines (timestamps 15:30 to 16:02 UTC). Main received them at 17:03 UTC through one `kept_events_reconciled` record whose `task_id` is SEL-045's (`09520bb0`).
- SEL-045R merged SEL-045's kept branch (`worktree-modular-knitting-hinton`), which carries the same 14 lines. The union driver kept both copies.
- `_merge` in `seldon/commands/dispatch_worktree.py` (line 1040) calls `KE.reconciled_ids(project_dir, store, finish["task_id"])`. For SEL-045R that is `8315cc7a`, which has no reconciled record, so `dedupe()` returned at once and `union_bad` named the 14.

So any task that merges another task's kept branch ends `merge_blocked`, after its work and its gate are done. SEL-045 met one case and patched it by hand; this is the general one.

What this changes for a consumer with a 60-minute gate and no slices, from the code: nothing in its gate, its lease or its launch order. `reconciled_ids` already reads main's store once per merge round; it reads the same file once and keeps more ids. `drop_reconciled` still drops only a LATER copy that is byte-identical to the first, so a pair that differs is still left for the union check to name. The only merges whose outcome changes are ones that today end `union_invalid` on identical copies.

## Part A: the lookup follows the id, and a test shows the case

1. `seldon/core/kept_events.py`: `reconciled_ids` returns the event ids of every `kept_events_reconciled` record on main's store when no task id is given, and keeps its present behaviour when one is given (two tests call it with a task id). Keep the cheap line pre-filter.
2. `seldon/commands/dispatch_worktree.py`, `_merge`: `reconciled` is the all-task set. Change nothing else in the round: `dedupe`, `flush_deduped`, `union_bad` and the order of the lease and the fast-forward stay as they are. The `kept_events_deduped` record still names the finishing task and the ids dropped.
3. `drop_reconciled`'s docstring and commit message say what is now true (a line already reconciled into main, for this task or another whose branch this one merged).
4. New test file `tests/test_sel046_merged_kept_branch_dedupes.py`, built on the fixtures `tests/test_sel034_kept_worktree_events.py` uses: task X is kept and its lines reconciled into main under X's id; task Y's branch merges X's branch; main moves; Y rebases. Assert that the all-task lookup holds X's ids, that `drop_reconciled` drops Y's copies, that `check_union_text` against main is ok, that the tree is clean, and that after the fast-forward `read_events` holds each id once. Add one test that a pair under one id that DIFFERS is not dropped and is still named by `check_union_text`.

Acceptance:
- `check: sh -c "python -m dotenv -f .env run -- env PYTHONPATH=. python -m pytest tests/test_sel046_merged_kept_branch_dedupes.py tests/test_sel034_kept_worktree_events.py tests/test_sel042_stopped_session_never_merges.py -q -p no:cacheprovider"` passes.

## Part B: the record

5. `docs/evidence/sel046/measured.txt`. Read-only, from this worktree, with `git show worktree-cached-noodling-minsky:seldon_events.jsonl` and `git show main:seldon_events.jsonl` (run no command in any other worktree, write nothing there): the count of ids held twice at that tip, how many of them the new all-task lookup returns, and how many it does not. Expected 14, 14, 0. Any other numbers are a finding: write them as measured and say so in the RESULT's first line.
6. RESULT, short. First line states what is true at the time of writing: the change is on this branch and reaches main only when the dispatcher merges it.
7. Do not touch SEL-045R, its branch, its worktree or Issue `1a448a6f`. Close nothing, file nothing, tell no other repository anything. The Desktop thread redrives SEL-045R after this merges.

Acceptance:
- `check: test -s docs/evidence/sel046/measured.txt` passes.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.45M.

## Deliverables

The widened lookup and its one call site; `tests/test_sel046_merged_kept_branch_dedupes.py`; `docs/evidence/sel046/measured.txt`; `cc_tasks/2026-11-24_SEL-046_the_merge_round_drops_a_line_main_already_holds_whichever_task_it_was_reconciled_for_RESULT.md`.
