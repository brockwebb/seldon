# SEL-045R ADDENDUM 02: the kept branch comes in as replayed commits, not as a merge

**Author:** Desktop session (seldon, SLD-3), 2026-11-24 17:15 EST, from the OODA on SEL-045R round three (`merge_blocked: rebase_conflict`, file `seldon/commands/dispatch_worktree.py`, Issue `94c2d2fa`).
**Replaces:** Part A item 2 of the task file, and the method in ADDENDUM 01 (its conflict and its resolution still hold; where the resolution is made changes). Nothing else changes.

## What happened

Round three did what ADDENDUM 01 ordered: it merged `worktree-modular-knitting-hinton`, resolved the one conflict in the merge commit, and its Stop gate passed. The merge round then ran `git rebase main` on the branch (`seldon/core/worktree.py`, `rebase`), as it does whenever main has moved since the fork, and main always has: the dispatcher's own record commits move it. A plain rebase does not keep a merge commit. It replays the kept branch's commits one by one, so commit `9fbb780` (SEL-041 Parts C and E) met SEL-046's line on main again and the resolution made in the merge commit was gone. A resolution that lives in a merge commit cannot survive the round. ADDENDUM 01 did not account for that; the error is this thread's.

## Measured before this addendum was written (scratch clone, nothing written to the repository)

- `git rebase main` on a copy of `worktree-modular-knitting-hinton` replays 20 commits and stops once, at `9fbb780`, in `_merge()` at the `reconciled = KE.reconciled_ids(...)` line. Keeping both sides there (SEL-041's comment and `session_tree = _tree_of(wt, "HEAD")`, then SEL-046's comment and `reconciled = KE.reconciled_ids(project_dir, S._store_rel(config))`, and NOT the old three-argument call) lets the other commits replay with no further conflict.
- With main then moved by a commit that appends to `seldon_events.jsonl`, a second `git rebase main` of that result is clean, and `seldon/core/gate_plan.py` is present.
- The replayed branch holds 14 event ids twice. `KE.reconciled_ids` (all tasks) returns those 14, `KE.drop_reconciled` drops 14, and `WT.check_union_text` against main is then ok with 0 malformed and 0 duplicates.

## Item 2, as it now reads

Do this before any commit of your own on this task's branch.

1. Note this branch's tip (it is main's tip at launch): `git rev-parse HEAD`.
2. `git reset --hard worktree-modular-knitting-hinton`
3. `git rebase <the tip noted in step 1>`
4. Exactly one stop is expected: `9fbb780`, in `seldon/commands/dispatch_worktree.py`, the hunk described above. Resolve it by keeping both sides as described, `git add` the file, `git rebase --continue`.
5. Any other stop, or this one in a different shape, is a finding: `git rebase --abort`, `git reset --hard <the tip noted in step 1>`, and stop the Part.

Then confirm, and record each in `docs/evidence/sel045r/landed.txt`:

- `git log --oneline --merges <tip from step 1>..HEAD` prints nothing.
- `git rev-list --count <tip from step 1>..HEAD` prints 20.
- The five test files ADDENDUM 01 names give 55 passed.

Do not remove the duplicated event lines yourself. The merge round drops them (SEL-046) and writes the record for it.

The task's Acceptance lists are unchanged. `landed.txt` says this was round four and names the replayed tip.
