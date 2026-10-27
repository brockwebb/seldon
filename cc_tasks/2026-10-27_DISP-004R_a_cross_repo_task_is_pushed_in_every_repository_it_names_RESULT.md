# RESULT: DISP-004R, a cross-repo task's commits are pushed in every repository its Repo line names

**Task:** `2909ce0f`, `cc_tasks/2026-10-27_DISP-004R_a_cross_repo_task_is_pushed_in_every_repository_it_names.md`.
No addenda were filed.
**Branch:** `worktree-fluttering-noodling-twilight`. Commits:
- `b111a1f`: code, tests, AD-034 ADDENDUM 06, the pending ruling, and the supersession events.
- `30bf98b`: `push_repos` written only when non-empty.
- the prior-art record commits (`eeb9a8b`, `430d724`, `0d6d482`, `c6cd983`).
- the closing commit, which carries this file.

There was no merge, push or `cc complete`: the dispatcher does those.
**Suite:** 2989 passed, 1 failed, 7 skipped (13 min 7 s, `-n 8`, run detached and polled; log `/tmp/disp004r/suite2.log`). The one failure, `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`, also fails on main (squiddy library index drift, Issue dbe38fac). The first run (`/tmp/disp004r/suite.log`) also failed `test_dispatch_serial_transcript` twice, on the `push_repos: []` field; `30bf98b` fixed that.
**Parts:** Part A is done; `seldon dispatch part-complete --part A` recorded it (190,000 tokens, 2,679 s, against the 0.5M stop). **Part B is not done.**
B is not declared complete, and the reason is in Part B below.
**Ruling:** AD-034-R12 is new, numbered under AD-034 as the task asked.
- Its note is `docs/design/AD-034_ADDENDUM_06_cross_repo_task_pushed_in_every_repo_it_names.md`. `seldon prior-art
  verify` passes on it.
- It was accepted with `--decided-by cc:2909ce0f` and is pending at
  `docs/decisions/register/pending/00001_7edc8b0782d912dc_seldon-ad-034-r12_accept.yaml`. The merge step numbers it.

Recall used: seldon:AD-036-R12, seldon:2026-10-17_FRICTION-002_vendor_isolation_replaces_hand_built_plumbing_RESULT

AD-036-R12 says a filing into another repository is committed on that repository's main by path. That is why the
push targets main (`cross_repo_branch`), and why the test stub commits in the sibling by path. FRICTION-002 made
`finish_session` shared by the serial pass and the parallel supervisor. That is why the reading is wired into both
launch paths and carried on the finish record, so the remerge and regate paths read it too.

## Part A: the launch reads the Repo line; a merged finish pushes each named repository

- **Launch** (`_launch_inplace` for serial, `_start_claimed` for parallel). `D.cross_repo_launch` reads the task's
  `**Repo:**` header. `D.repo_push_targets` returns the other repositories its L4 clause says to push. Each one's HEAD
  is recorded on `dispatch_launched.push_repos` and carried to the finish in the session's `extra`. For the parallel
  supervisor it travels in `LEASE_EXTRA_KEYS`.
- **The reading of the line** (AD-034 ADDENDUM 06 "How the Repo line is read"). Only the `L4:` clause decides, and
  within it only the `;` segments that say `push`.
  - A segment that names repositories pushes those.
  - A segment that names none pushes every repository named up to the end of the clause, and only when it uses a
    quantifier (`all`, `every`, `each`, `both`).
  - A bare `L4: commit, merge, push.` applies to the primary only.
  - A repository is named by an absolute path to a checkout, or by a bare word that is a checkout's directory name
    under `dispatch.cross_repo_root` (default `..`).
  - This task's own line resolves to squiddy and ai-readiness-kg.
  - Lines naming hazbrief-mcp as read-only evidence resolve to nothing.
  - The tests use the line shapes the three repositories actually carry.
- **Finish** (`push_named_repos`, called by `_finish_merged` before `dispatch_finished` is written). For each named
  repository, `D.push_cross_repo` records `head_at_launch`, `head_at_finish` and `push`. The `push` value is one of:
  - `unmoved`: HEAD did not move. Nothing is pushed, even if the repository is ahead of origin from other work.
  - `pushed`, with `ahead`, or `up_to_date`.
  - a refusal: `dirty_tree` (with the paths), `wrong_branch`, `read_error`, `no_upstream`, `push_failed` or `missing`.

  Each repository gets a `push:` line on stdout. Refusals raise one alarm through the notify channel, with outcome
  `cross_repo_push_refused`, and the message names every refused repository. A refusal does not undo this
  repository's merge.
- **Unmerged finish.** Nothing is pushed elsewhere, which matches the rule for the project's own main. Each repository
  that moved is recorded as `held_unmerged`, so a reader sees a sibling left ahead of origin.
- **No change to other tasks' records.** `push_repos` is written only when the task names another repository. The
  serial transcript test (`test_dispatch_serial_transcript`) failed on the first version, which wrote `[]`, and passes
  with the conditional field.
- **Config.** `seldon.yaml dispatch.cross_repo_root: ..` and `dispatch.cross_repo_branch: main` are validated at load,
  with defaults, so no other project's config has to change.
- **Fixture** (`tests/test_disp004r_cross_repo_push.py`, 16 tests, all passing). The task's own fixture is
  `test_a_session_committing_in_two_repositories_is_pushed_in_both`. A task names two repositories, the stub session
  commits in both, both are pushed, and a third repository that the line names as evidence moves and is not pushed.
  The other tests cover:
  - the same flow through the parallel supervisor;
  - an unmoved repository that is not pushed;
  - a dirty tree that refuses and alarms, while the clean sibling in the same finish is pushed;
  - an unmerged finish recording `held_unmerged`;
  - the parser on real line shapes;
  - config validation.

  `tests/dispatch_scaffold.py`'s stub gained `other_commit`, which commits on another repository's main by path.

**Prior art** (in the addendum, with receipts). git-push(1) `--recurse-submodules=on-demand` is adopted: push every
other repository the change needs. The departure is that the other repositories are siblings, pushed after this
repository's merge, so a refusal is recorded and alarmed rather than aborting. `push_if_ahead` is reused once per
repository, and the clean-tree refusal applies c7's rule. The internal and library arms found nothing on pushing
across repositories, and the receipts record those searches.

## Part B: first run, squiddy and ai-readiness-kg

Reading taken 2026-10-27 from this worktree, with `git -C <repo> status -sb` and `log origin/main..main`:

| repository | ahead of origin | tree | push |
|---|---|---|---|
| squiddy | 0 (`## main...origin/main`) | clean | `up_to_date`: nothing to push |
| ai-readiness-kg | 4 | dirty: ` M seldon_events.jsonl` (8 uncommitted lines), `?? .githooks/commit-msg` | **not pushed** |

The two commits named in the condition are already on their origins: ai-readiness-kg `04c26099` and squiddy `805e333`
(`branch -r --contains` lists `origin/main` for each).

ai-readiness-kg's 4 unpushed commits are squiddy SQ-022b's, dated 2026-10-24: `570c98f8`, `089669b8`, `b742fb93` and
`15548b92`. The 8 uncommitted event lines are ai-readiness-kg's own dispatcher's: an `artifact_updated` and a
`dispatch_observed_stop` each morning from 10-24 to 10-27, plus one `artifact_created`. That dispatcher is stopped, so
nothing commits them.

I did not push ai-readiness-kg, for two reasons:
1. Part A's own rule refuses a push over a dirty tree.
2. This session's launch clause says "Do not merge, push, ... whatever the task file says".

The isolation also refuses git that this session aims outside its worktree. Part B therefore stays open. Pushing only
sends commits, so the dirty working tree does not travel with it.

**Recipe** (Brock, in a shell, in this order):

1. `cd /Users/brock/GitHub/ai-readiness-kg && git status -sb`. Expect `[ahead 4]`, ` M seldon_events.jsonl` and
   `?? .githooks/commit-msg`.
2. `git push origin main`. This pushes the 4 SQ-022b commits.
3. `git status -sb`. Expect `## main...origin/main` and the same two uncommitted entries.

The uncommitted lines and the untracked hook are ai-readiness-kg's. DESK-004R's hooks installer (AD-038-R15) commits
the hook on its next `seldon hooks install` there, and its reconciler commits the event lines on the next pass of a
running dispatcher. Neither belongs to this task.

## Supersession

`d091760b` (DISP-004, which had no source file) went from `proposed` to `superseded`, with `superseded_by 2909ce0f`.
Its event-store lines are in `b111a1f`.

## Limits, stated

- The broad form "every git repository directly under `/Users/brock/GitHub/`" names no repository and pushes nothing.
- The other repository's push runs under this project's pass lease, not under that repository's lease. If its
  dispatcher is appending at that moment, its tree reads dirty, so the push is refused and alarmed, and the next push
  there carries the commits.
- This task's own merge runs the pre-change supervisor (the transition note in the addendum), so the new step first
  acts on the next cross-repo task.
