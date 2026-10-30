# RESULT: SEL-017, a session's link to gitignored data is clean, the worktree's hook resolves, a task without Parts is one Part

**Task:** `dff55b9d`, `cc_tasks/2026-10-29_SEL-017_a_linked_gitignored_directory_is_clean_the_worktree_hook_resolves_and_parts_defaults_to_one.md`.
No addenda were filed.
**Branch:** `worktree-groovy-plotting-swing`. Commits:
- `afa7322`: the code, the tests, AD-034 ADDENDUM 07 and the three pending rulings.
- The prior-art record commits (`292ee23`, `8d03245`, `c77c4a1`, `4ddcafc`, `d09ca7b` and the earlier duplicates
  `41a9baf`, `ce7e091`). The first round of searches printed receipts that I re-ran to capture them to a file, so
  each search is recorded twice.
- The closing commit carries this file, the re-recorded serial transcript and its erratum.

There was no merge, push or `cc complete`: the dispatcher does those.
**Parts:** A, B and C are all recorded with `seldon dispatch part-complete`. Part A was 121,683 tokens at 457 s; B
and C were recorded at 122,179 tokens.
**Premises:** all four checks held when I read them. `exclude=linked` is at `dispatch_worktree.py:895`, and
`def dirty_paths` is in `seldon/core/worktree.py`. hazbrief's `.gitignore:79` reads `graphs/*/work/`, and
`seldon.yaml` there has no `worktree_links`.
**Rulings:** AD-034-R13 (A), R14 (B) and R15 (C), in `docs/design/AD-034_ADDENDUM_07_session_links_worktree_hook_default_part.md`
lines 86 to 88. `seldon prior-art verify` passes on the note (verdict `784d6f14`). All three were accepted
`--decided-by cc:dff55b9d` and are pending under `docs/decisions/register/pending/` (00001 to 00003). The merge step
numbers them.

Recall used: none

None of the recall hits changed the approach. The prior work that did is SEL-012's RESULT, which was not one of the
hits. It found seldon's and squiddy's shared `core.hooksPath` absolute and set it relative, and that value is absolute
again today. That is why B overrides the value per worktree and does not rewrite the shared value again.
DISP-004R's RESULT supplied the pattern for the addendum, its receipts and the pending records.

## Part A: a session's link to gitignored data is clean (AD-034-R13)

**Cause, confirmed by probe.** I built a scratch repository ignoring `graphs/*/work/` and `corpus/raw/`, with a
worktree that symlinks both from the primary:
- `git status --porcelain` lists both links.
- `git check-ignore graphs/g/work` exits 1, because a symlink is a file and a `dir/` pattern matches only
  directories (gitignore(5)).
- `git check-ignore graphs/g/work/` exits 128 with `fatal: pathspec ... is beyond a symbolic link`.

So git cannot be asked the question directly. Plain porcelain also collapses a parent directory the session created
(`?? corpus/`).

**Built** (`seldon/core/worktree.py`):
- `_porcelain` parses `git status --porcelain -z`, so paths are never quoted and a rename's source record is consumed.
- `_ignored_as_directory(repo, rel)` asks git whether `rel` is ignored as a directory. The scratch work tree holds
  `rel` as an empty directory plus the `.gitignore` files of `rel`'s ancestors. It uses the repository's own
  `--git-dir`, so `info/exclude` and `core.excludesFile` apply. It runs `check-ignore --no-index`. No gitignore
  matching is re-implemented.
- `_clean_link` passes a symlink that meets either rule: its own path is ignored as a directory, or its target
  resolves inside the primary checkout (`primary_checkout`) at a path the primary ignores.
- `session_links(repo, exclude)` lists such links. A collapsed untracked directory is expanded with `-uall`, and it
  counts as clean only when every untracked path inside it is such a link.
- `dirty_paths` drops those entries. Its other callers inherit the same rule: the remerge path, the sweep and the
  regate.
- In `dispatch_worktree.py`, the merged finish's `merge` record gains `linked_by_session`.

A symlink that replaces a tracked file is a type change (` T`), not `??`, so it still blocks. So does a symlink to a
tracked target.

**Tests** (`tests/test_sel017_links_hook_parts.py`):
- hazbrief's four links come out clean, and the test first asserts that raw `git status` reports them, as the plant.
- The own-path rule holds with a target outside the primary.
- The target rule holds for a link at an unignored path.
- A symlink to a tracked path blocks. So does a symlink that replaces a tracked file.
- A directory the session made is clean holding only links, and dirty once it also holds a file.
- Configured links are excluded and not listed as the session's.
- End to end: a stub session links `graphs/g/work` itself, and the task merges with
  `merge.linked_by_session == ["graphs/g/work"]`. The test uses the real dispatcher pass, Neo4j and a bare origin.
  The stub gained a `symlink` spec key in `tests/dispatch_scaffold.py`.

**Not done here, as the task says.** HB-64 and HB-72 are not redriven or merged. HB-73 in hazbrief does that.

## Part B: the worktree's hook resolves (AD-034-R14)

**Reading in this worktree, 2026-10-29.** `git config --show-scope --show-origin --get-all core.hooksPath` printed
`local file:/Users/brock/GitHub/seldon/.git/config /Users/brock/GitHub/seldon/.githooks`. `seldon hooks status`
printed `installed: False, problems: ["core.hooksPath is '/Users/brock/GitHub/seldon/.githooks', not '.githooks'"]`.
SEL-012 set the value relative on 2026-10-28, so a writer outside seldon makes it absolute again. That writer is
not identified.

**Built.** `hooks.point_worktree(worktree)` turns on `extensions.worktreeConfig` and runs
`git config --worktree core.hooksPath .githooks` (git-worktree(1), CONFIGURATION FILE). The worktree's
`config.worktree` is read after the shared config and wins, so the hook resolves to the worktree's own tracked
`.githooks` whatever the shared value becomes. The function:
- never touches the primary's value;
- is idempotent;
- skips a checkout with no `.githooks/pre-commit`, because pointing git at an empty directory would only switch off
  `.git/hooks`;
- refuses, with a reason, when the shared config sets `core.worktree` or `core.bare = true`. git-worktree(1)
  requires those to be moved before the extension is turned on.

`name_worktree` calls it and records the result as `dispatch_worktree_named.hooks_path`. A failure there is recorded
and does not refuse the launch. `hooks.status` already accepted `worktree` scope, so `seldon verify`'s "Commit hook"
check needed no change.

**Tests:**
- A fresh worktree whose shared value is the absolute path is first `not installed` (the plant). After
  `point_worktree` it is installed at scope `worktree`, and `check_commit_hook` passes.
- The primary's value is unchanged, and a second call changes nothing.
- A checkout without the tracked hook is left alone, and the extension stays off.
- `name_worktree` on a worktree under `.claude/worktrees/` records `hooks_path.ok`, and the worktree reports
  installed.

**Not applied to this session's own worktree.** Doing so would turn on `extensions.worktreeConfig` in seldon's shared
`.git/config` from inside a dispatched session. The dispatcher does that at the next launch it names once this
merges. Until then, `seldon verify` in a worktree still prints "not installed". Worktrees that the dispatcher does not
name, such as interactive `claude --worktree` sessions, are not covered (addendum, "What this does not do").

## Part C: a task without Parts is one Part (AD-034-R15)

**Built.**
- `stations.task_parts(text)` returns `parse_parts`'s reading, with `defaulted: False`, when a header is present.
  When no header is present it returns `A 1.00` with `defaulted: True`.
- A header that is present but does not parse keeps its error.
- `part-complete` uses `task_parts` and adds `parts_defaulted: true` to `part_complete`. Its output says
  `no **Parts:** header, read as A 1.00 (parts_defaulted)`.
- The milestone station (`inspect`) computes CPI over that one Part and marks `parts_defaulted` on `milestone`.
- `task_checks` (the regate's Stop-gate checks) reads the same default.
- Registration still calls `parse_parts`. `parts_registration_refusal` is unchanged, so a new file without the header
  is still refused.

The grounding is the earned-value 100% rule: with no decomposition declared, the task is one work package carrying
all the planned value.

**Tests:**
- On a header-less task, `part-complete --part A` exits 0 and records `planned_share 1.0, parts_defaulted: true`.
  The milestone after the Stop gate carries `parts_defaulted`, `earned 1.0` and a computed CPI. `--part B` is
  refused.
- `task_parts` leaves a declared header undefaulted and a broken header with its error.
- Registration still refuses a header-less new file.

## Suite

The command was `python -m dotenv -f .env run -- python -m pytest tests/ -q -n 8` with `PYTHONPATH` set to this
worktree. It ran detached and was polled to `EXIT=1` (log `/tmp/sel017probe_script/suite.log`, 20 min 40 s).
Result: **3084 passed, 4 failed, 7 skipped.**
- `test_dispatch_serial_transcript` failed in both parametrizations because of the new `hooks_path` and
  `linked_by_session` keys. I re-recorded it with `SELDON_RECORD_SERIAL_TRANSCRIPT=1` and added an erratum to the
  docstring. The re-recording equals the pre-change fixture once exactly those three keys are removed (regex strip,
  `True`, `/tmp/sel017probe_script/strip_check.py`). It passes now.
- `test_friction002_worktree_only::test_an_unmerged_task_keeps_its_worktree_and_branch_with_a_worktree_kept_record`
  failed under `-n 8` and passed twice when re-run (alone, and with `-n 4` beside the SEL-017 and transcript tests).
  This is a contention flake, and nothing in this diff touches what it asserts.
- `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` fails with
  `release_unavailable`, because squiddy's library `index:` block differs from the one the release was built under.
  It also fails on main (Issue dbe38fac, recorded in DISP-004R's RESULT).

After the re-recording, the four affected files (the transcript, friction002 worktree-only, the SEL-017 tests and the
milestone tests) gave 30 passed and 1 skipped.

## Open

- The writer that makes seldon's and squiddy's shared `core.hooksPath` absolute is unidentified. R14 makes dispatched
  worktrees independent of it, and the primary is still re-pointed by `ensure_installed` on each pass.
- HB-64 and HB-72 are hazbrief's to redrive (HB-73).
