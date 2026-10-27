# AD-038 ADDENDUM 06: the hooks installer commits what it writes, and the reconciler commits seldon's hook files

**Date:** 2026-10-27. **Status:** Accepted. Implemented by DESK-004R
(`cc_tasks/2026-10-27_DESK-004R_every_file_the_machine_writes_is_committed_by_the_tool_that_wrote_it.md`, task
`f7a1d2f0`).
**Amends:** AD-038-R1 (the reconciler's class table gains `hooks`).
**Resolves:** ResearchTasks `2f2f1174` (DESK-004) and `60fb6b11` (late addenda left untracked).
**Code:** `seldon/core/hooks.py` (`seldon_hook_scripts`, `uncommitted_hooks`, `commit_hooks`, `install`,
`ensure_installed`); `seldon/commands/hooks.py` (`seldon hooks install`); `seldon/core/reconcile.py` (class `hooks`).
**Tests:** `tests/test_desk004r_tool_commits_what_it_writes.py`.

## 1. Evidence

1. `seldon hooks install` wrote `.githooks/commit-msg` (DESK-001) and printed "commit them". In squiddy the file was
   untracked from 2026-10-21 21:17 (measured 2026-10-22), and every dispatcher pass refused every candidate on c7,
   SUITE-001 `9324622d` included. `seldon_commit_governed` refuses `.githooks/` paths, so no tool could commit it.
2. `ensure_installed`, the dispatcher's launch-path call, runs `install` when git is not pointed at the tracked
   hook. It runs before the lease is taken, so it cannot commit without racing another pass for `index.lock`.
3. The late-addendum case (ai-readiness-kg `1267b87d`: three tasks stuck 2026-10-02 to 10-04) was caused by the
   retired `_commit_registered`, which swept `<stem>_ADDENDUM*.md` only beside an untracked base (read at
   `3f19acf^`). The AD-038-R1 reconciler that replaced it on 2026-10-17 checks the addendum's own untracked state
   against the registered base path, tracked or not. All 452 `source_file` values in the seldon, squiddy and
   ai-readiness-kg graphs are relative `cc_tasks/*.md` paths (surveyed 2026-10-27), so that match finds every base.
   No new ruling is needed. The behaviour is now pinned by tests, at the class table and through a dispatcher pass.

## 2. Ruling

- **AD-038-R15. The hooks installer commits the hook files it writes, and the reconciler commits seldon's own hook
  files.**
  - `seldon hooks install` (`hooks.install`, `commit=True` by default) commits seldon's hook files that are untracked
    or differ from HEAD and whose bytes are exactly seldon's text, whether it wrote them now or an earlier install
    left them. It commits them alone, path-limited, through the hooks it has just pointed git at. A refused commit
    raises, unstages the paths and leaves the files on disk.
  - `ensure_installed` calls `install(commit=False)`: it runs outside the lease.
  - The reconciler's class `hooks` admits `.githooks/pre-commit` and `.githooks/commit-msg` whose bytes on disk are
    exactly seldon's text, and commits them under the lease like every other class. A hook file with other bytes is
    someone's hook, and c7 names it ("a hook file that is not seldon's text").

## 3. Negative control

- `test_the_reconciler_does_not_commit_a_hook_file_that_is_not_seldons`: a foreign `commit-msg` is left for c7.
- `test_the_commit_runs_through_the_hooks_and_leaves_other_staged_work_alone`: an unrelated staged file stays staged.
- `test_a_refused_hook_commit_raises_and_leaves_the_index_as_found`: the commit goes through the hooks, and a hook
  refusal is reported, not swallowed.

## 4. Prior art

### External

- **Hook managers that keep hooks in the tree.** Husky's `husky init` writes `.husky/pre-commit` and leaves the
  commit to the user. pre-commit.com's `pre-commit install` writes into `.git/hooks/`, which is untracked by design.
  *Departed from:* both leave the file for a person. Here an uncommitted file in the tree is the dirt that stops the
  queue (§1 item 1), so the installer commits it.
- **Reconciliation (OpenGitOps principle 4)**, as AD-038-R1 adopted it: the agent that observes drift repairs it.
  *Adopted:* the dispatcher's reconciler gains one class.

### Internal

- AD-036-R11 and DESK-001: an automatic writer commits what it writes, path-scoped, through the hooks.
  `declare_union` already commits `.gitattributes` this way during the same install (AD-034 ADDENDUM 05). R15 applies
  the same rule to the hook files.
- AD-038-R1: what qualifies a path is its class and the shape of its change. The `hooks` class qualifies on exact
  bytes, the strictest shape the table uses.
