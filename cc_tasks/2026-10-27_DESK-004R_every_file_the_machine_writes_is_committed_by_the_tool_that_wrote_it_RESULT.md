# RESULT: DESK-004R, every file the machine writes is committed by the tool that wrote it

**Task:** `f7a1d2f0`, `cc_tasks/2026-10-27_DESK-004R_every_file_the_machine_writes_is_committed_by_the_tool_that_wrote_it.md`.
**Branch:** `worktree-glimmering-stirring-sunset`, with commits `e6da3af` (code and tests), `34f31f6` (decision),
`74512d8` (scaffold) and the closing commit that carries this file. No merge, push or `cc complete`: the dispatcher does
those.
**Suite:** 2972 passed, 2 failed, 7 skipped (17 min 17 s, `-n 8`, run detached and polled; log `/tmp/desk004r/full2.txt`).
Neither failure is caused by this change:
- `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` also fails on main
  (squiddy library index drift, Issue dbe38fac).
- `test_dispatch_parallel::test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` is a timing flake
  under `-n 8`. It passes alone (1 passed, 46 s).

**Parts:** `seldon dispatch part-complete` recorded A at 137,669 tokens and B at 141,057, against the 0.4M stop.
**Rulings:** AD-038-R15 is new, numbered under AD-038 as the task asked.
- Its note is `docs/design/AD-038_ADDENDUM_06_the_hooks_installer_commits_what_it_writes.md`.
- It was accepted with `--decided-by cc:f7a1d2f0` and is pending under `docs/decisions/register/pending/`. The merge step
  numbers it on main.

Recall used: seldon:AD-038-R1, seldon:2026-10-15_DESK-001_desktop_writes_are_committed_RESULT, seldon:AD-036-R11

## Part A: the installer commits the hook it writes

- **`hooks.install(repo, python=None, commit=True)`** commits after it sets `core.hooksPath`, so the commit runs the
  hooks it commits. It commits seldon's hook files that are untracked or differ from HEAD and whose bytes are exactly
  seldon's text, whether written now or left by an earlier install. The commit is alone and path-limited, and its
  subject is `chore: commit seldon's tracked hooks (DESK-004R, AD-038-R15)`.
  - A refused commit raises `HookError` with git's reason and unstages the paths. The files stay on disk.
  - `InstallResult` gains `committed` and `commit`. `seldon hooks install` prints `committed <paths> as <sha>` in place
    of "wrote .githooks/ hook file(s) (commit them)".
- **`ensure_installed` does not commit.** The dispatcher calls it before it takes the lease, where a commit could
  collide with another pass. It calls `install(commit=False)`.
- **The reconciler has a new class, `hooks`** (`seldon/core/reconcile.py`, AD-038-R15).
  - It admits `.githooks/pre-commit` and `.githooks/commit-msg` whose bytes are exactly seldon's text, and commits them
    under the lease like any other class.
  - Any other bytes are someone's hook, and c7 names the file: "a hook file that is not seldon's text".
  - This class is what repairs a checkout an earlier install left dirty, without a person.
- **Shown failing on main.** Main's `install`, loaded from `git show main:seldon/core/hooks.py`, run on a scratch repo
  leaves `?? .githooks/commit-msg` and `?? .githooks/pre-commit` (`/tmp/desk004r/old_install.py`).
- **Live instance found.** ai-readiness-kg has an untracked `.githooks/commit-msg` whose bytes are exactly seldon's
  text and which is executable. Its last dispatcher pass (2026-10-24T09:04Z) names it as the only dirty path.
  - Once this merges, that dispatcher's next pass commits it as class `hooks`.
  - squiddy's `.githooks/` is clean now. So are seldon's, arnold's and wintermute's (read-only survey,
    `/tmp/desk004r/hook_state.py`).

## Part B: late addenda

**The condition was already fixed. No code changed.**
- The retired `_commit_registered` swept addenda only beside an *untracked* base (`3f19acf^:seldon/commands/dispatch.py`,
  `if ... D.is_tracked(project_dir, path): continue`).
- The AD-038-R1 reconciler replaced it on 2026-10-17 (`3f19acf`). It admits an untracked `<stem>_ADDENDUM*.md` when
  `<stem>.md` is a registered `source_file`, tracked or not.
- All 452 `source_file` values in the seldon, squiddy and ai-readiness-kg graphs are relative `cc_tasks/*.md` paths
  (`/tmp/desk004r/survey.py`), so the match finds every base.
- The spec says "every open registered task". The reconciler admits an addendum to a task in any state, which is
  broader. It is kept as is: committing a closed task's addendum is harmless, and leaving it would be dirt.

Two tests now pin the behaviour.

## Tests

`tests/test_desk004r_tool_commits_what_it_writes.py` (10, real git, and Neo4j for the dispatcher pass):

- **A:**
  - A fresh install in a scratch repo leaves `git status --porcelain` empty, and the commit holds the hook files only.
  - The CLI prints the commit.
  - An unrelated staged file stays staged.
  - An untracked hook left by an earlier install is committed.
  - A second install commits nothing.
  - A refused commit raises and leaves the index as found.
  - `ensure_installed` makes no commit, and the reconciler then commits the file as `hooks`.
  - A foreign `commit-msg` is not committed.
- **B:**
  - Class table: a tracked base with an untracked addendum, committed alone as `task_files`.
  - End to end: `seldon dispatch once` on a project whose base task is committed and whose addendum is untracked. It
    commits the addendum, does not refuse `dirty_tree`, and launches.

**Fixtures changed by intent** (they committed the hooks after `install`, which now commits them itself):
- `test_hooks.py`'s `repo` fixture: `test_commits_before_the_hook_existed_are_not_audited` now anchors on install's
  commit.
- `test_prior_art_ref.py`'s `hooked` fixture.
- `tests/dispatch_scaffold.install_commit_gate` passes `commit=False`. Without it, the fixture's `init` commit is
  preceded by install's, and `test_dispatch_serial_transcript` breaks against its recorded transcript.

## Supersession

- `2f2f1174` (DESK-004) and `60fb6b11` (late addenda left untracked) went from `proposed` to `superseded`, with
  `superseded_by f7a1d2f0`.
- Their event-store lines are in the closing commit.
