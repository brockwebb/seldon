# AD-034 ADDENDUM 09: every system-written journal is committed before the fast-forward, and a merge block names the files git named

**Date:** 2026-11-12. **Status:** Accepted. Implemented by SEL-038
(`cc_tasks/2026-11-11_SEL-038_a_system_written_journal_never_blocks_a_merge_and_a_held_library_release_is_read_through_squiddys_accessor.md`,
Parts B and C), answering hazbrief-mcp's filing
`cc_tasks/2026-11-11_the_merge_round_s_fast_forward_is_refused_when_desktop_s_prior_art_too.md` (task `a7795a22`).
**Amends:** AD-034's merge round (decision 3): the lease-held step before the fast-forward. **Extends:** AD-038-R1 (the
dispatcher commits system-written lines) to a class the round missed. Two new rulings, AD-034-R19 and R20.
**Code:** `seldon/core/reconcile.py` (`JOURNAL_CLASSES`); `seldon/commands/dispatch.py` (`_record_journals`);
`seldon/commands/dispatch_worktree.py` (`_merge`, `regate`); `seldon/core/worktree.py` (`files_named`).
**Tests:** `tests/test_sel038_journals_and_held_releases.py`.

## 1. Evidence

1. **Six hours of green work left unmerged.** hazbrief HB-155 finished green and strictly ahead of main; the round
   recorded `MERGE BLOCKED 49768b52 (ff_refused)` after three attempts. git's stderr in `dispatch_finished`
   (`8d7403aa`): "Your local changes to the following files would be overwritten by merge:
   state/prior_art_queries.jsonl". Desktop's `prior-art/1` had appended six lines to that file in main during the run,
   and the branch carried receipts of its own in it. A second task (HB-166) landed the work by hand.
2. **The lease-held step committed the event store only.** `_record_own_lines` reconciles `classes=("event_store",)`;
   the `prior_art` class was committed only by the full reconcile at the start of a pass. The comment at the step
   described this exact failure for the event store.
3. **The Issue named nothing.** The round recorded `files: []` on `ff_refused`, so Issue `1e7d1faf` said "Files: none
   named" while the stderr it carried named the file.
4. **Reproduced here before the fix** (`docs/evidence/sel038/red_merge_round_before_fix.txt`): with one merge attempt,
   a branch appending to the query log (and, separately, the verdict ledger) while main's copy is dirty ends
   `{'reason': 'ff_refused', 'files': []}`.

## 2. Prior art

### External

- **git's union merge driver** (`gitattributes(5)`, "union": "Run 3-way file level merge for text files, but take
  lines from both versions, instead of leaving conflict markers"). It is the merge for a file whose lines carry their
  own identity and whose order across sides means nothing: an append-only JSONL journal. Seldon adopted it for the event
  store and the query log in AD-034-R7 and ADDENDUM 05; every journal class here is declared with it, so the round
  rebases over the housekeeping commit without a re-gate. Cited by its published name; not fetched (Network: none).
- AD-038-R1 (the machine reconciles its own state): what qualifies a path is its class, never its writer. This
  addendum applies that ruling at the one point the round had applied it partially. It is not a new mechanism.
- **git's own refusal messages** (`unpack-trees.c`: "Your local changes to the following files would be overwritten
  by ...", "The following untracked working tree files would be ..."; and "CONFLICT (...): Merge conflict in ...").
  The paths a block names are read from these, git's words, not inferred.

### Internal

- internal receipt: query "union driver" | repo seldon@2de5bc6dc0ff37fa5d47f75749a0db41305c6989 | hits docs/design/AD-034_ADDENDUM_05_union_attribute_in_every_governed_repo.md:47, docs/design/AD-034_ADDENDUM_05_union_attribute_in_every_governed_repo.md:42, docs/design/AD-034_ADDENDUM_05_union_attribute_in_every_governed_repo.md:31
- internal receipt: query "fast-forward" | repo seldon@2de5bc6dc0ff37fa5d47f75749a0db41305c6989 | hits handoffs/2026-10-30_desktop_sq11_work_order_addendum_01_merge_gate_hand_dispatch_register_race.md:15, docs/design/AD-034_ADDENDUM_06_cross_repo_task_pushed_in_every_repo_it_names.md:3, docs/design/AD-034_worktree_per_task_dispatch.md:37
- internal receipt: query "reconcile class" | repo seldon@2de5bc6dc0ff37fa5d47f75749a0db41305c6989 | hits docs/design/AD-038_ADDENDUM_06_the_hooks_installer_commits_what_it_writes.md:3, docs/design/AD-038_ADDENDUM_09_the_dispatcher_cannot_dirty_its_own_tree.md:3, docs/design/AD-030_implementation_findings_002.md:28

## 3. Rulings

- **AD-034-R19. Before the fast-forward, under the lease, the merge round commits every dirty file of every journal class, not the event store alone.**
  The journal classes are the reconcile classes whose files are system-written append-only JSONL journals
  (`reconcile.JOURNAL_CLASSES`): `event_store` and `prior_art` (the query log and the verdict ledger). Each class is
  committed in its own commit, with the subject a pass's reconcile gives it; a refused commit is printed and the
  fast-forward that follows names what is left. The other reconcile classes are not committed there, for stated
  reasons: the decision register's records are committed with their writer's own commit (DESK-002R) and its rendering
  is regenerated, never union-merged; the cadence edits one line of seldon.yaml in place; task files, filings and hooks
  are whole files a branch does not share with main's dirt. Committing those would turn a fast-forward into
  `main_kept_moving` and fix nothing.
- **AD-034-R20. A merge block that carries git's message names the files that message names.**
  `ff_refused` records in `files` the paths git's stderr lists (`worktree.files_named`); a `rebase_conflict` whose
  unmerged-path list is empty does the same, in the round and in a regate. The Issue opened for the block names them.
  A message that names no path still gives `[]`, and the Issue says so.

## 4. What this does not change

The round's other blocks, its attempts and its housekeeping test are as AD-034 ADDENDUM 08 left them. A journal
that is not declared `merge=union` is still not housekeeping: its commit makes the round rebase again, as any move of
main does. The pass's own declaration (`_declare_union`, ADDENDUM 05) is what keeps every journal declared, and
AD-036-R23 adds the verdict ledger to it.
