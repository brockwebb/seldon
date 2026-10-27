# AD-034 ADDENDUM 06: a cross-repo task's commits are pushed in every repository its Repo line names

**Date:** 2026-10-27. **Written by:** DISP-004R (`cc_tasks/2026-10-27_DISP-004R_a_cross_repo_task_is_pushed_in_every_repository_it_names.md`).
**Amends:** AD-034's finish step (§1, "fast-forward, complete the task, record, push"), which pushed only the project's
own main. **Applies:** AD-036-R12 (a session files into another repository by path). One new ruling.

## Evidence

SQ-019 (squiddy, 2026-10-21) committed ai-readiness-kg 04c26099. Its RESULT says "committed and not pushed". The task
header said L4 push in both repositories. The launch prompt forbids the session to push (`WORKTREE_CLAUSE`), and
squiddy's dispatcher pushed only squiddy. A seldon task left squiddy 805e333 unpushed the same way on 2026-10-20. The
cause is that the push step read only its own repository, and the session is not allowed to push.

## Prior art

- **git-push(1), `--recurse-submodules=check|on-demand`.** A superproject push can require each submodule's commits to
  be on a remote first. With `on-demand`, git pushes each submodule that changed in the pushed revisions, and the push
  aborts if one of them cannot be pushed. Adopted: the finish pushes every other repository the task changed. The
  departure is that the other repositories are sibling checkouts the task names, not submodules. Their pushes come
  after this repository's merge, so a refusal there is recorded and alarmed but does not undo the merge.
- **`seldon.core.dispatch.push_if_ahead`** (`ai-readiness-kg/cc_tasks/2026-09-16_dispatcher_commits_its_record.md`
  decision 2) supplies the push itself. It reads "ahead" from git, it never raises, and an offline machine is an ordinary
  state there. Applied unchanged, once per repository.
- **c7's clean-tree rule** (DN-006 decision 2) supplies the refusal. A dirty tree means someone's work is in progress
  there, and the dispatcher does not act on top of it. Applied to the other repository's push.

### Internal

- internal receipt: query "push main in every repository the task commits in" | repo seldon@7730d60e0cb840a949b9cd6ea12785210c0bb7d4 | hits docs/design/AD-034_ADDENDUM_01_worktree_is_the_only_mode.md:26, docs/decisions/REGISTER.md:9
- internal receipt: query "push main in every repository the task commits in" | repo squiddy@0f6a8830caa2d099c5e573e99a0e0fdef85f97b7 | hits none

### External

- library receipt: query "multi-repository atomic change push submodules" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-04-05_arXiv_2604_01007#p5:40:151-409

The library is a corpus of AI-research lessons and returned nothing about pushing across repositories. The receipt
above records that search. The source for this addendum is the git manual (`git help push`).

## The rule

- **AD-034-R12. At launch the dispatcher reads the task's `**Repo:**` line for the other repositories its L4 clause says to push, and records each one's HEAD on `dispatch_launched`. At a merged finish it pushes main in each of them whose HEAD moved during the session, whose current branch is `dispatch.cross_repo_branch` and whose tree is clean. It records each repository's reading on `dispatch_finished.push_repos`. A refusal (a dirty tree, another branch, no upstream, a failed push, a missing checkout) raises one alarm through the notify channel, naming every refused repository. An unmerged finish pushes nothing elsewhere and records `held_unmerged` for each repository that moved.**

### How the Repo line is read

The Repo line is free prose. The reading is narrow, and a line it cannot read pushes nothing beyond the project's own
main, which is the behaviour before this addendum.

1. Only the `L4:` clause decides, up to the end of its sentence. Within it, only the `;`-separated segments that say
   `push` count.
2. A push segment that names repositories pushes those (`push in squiddy; the hazbrief graph release commits in
   hazbrief-mcp` pushes squiddy alone).
3. A push segment that names none pushes every repository the line names up to the end of the clause, and only when it
   uses a quantifier (`all`, `every`, `each`, `both`). This task's own line, "`seldon (primary); squiddy and
   ai-readiness-kg (...). L4: commit, merge, push in all three.`", is an example. A bare `L4: commit, merge, push.`
   applies to the primary only, so a repository the line names as read-only evidence is never pushed.
4. A repository is named by an absolute path to a git checkout, or by a bare word that is the directory name of a
   checkout under `dispatch.cross_repo_root` (default `..`, the parent of the project directory, where the governed
   repositories live). A word that names no checkout is ordinary prose.
5. "Every repo touched" is decided at the finish: a named repository whose HEAD did not move is `unmoved` and is not
   pushed, even if it is ahead of its origin from other work.

### What it does not cover

- The broad form "every git repository directly under `/Users/brock/GitHub/`" (STD-001R) names no repository and
  pushes nothing. A task that commits in many repositories names them.
- The other repository's push is made under this project's pass lease, not under that repository's lease. A push
  writes no working tree, and git updates the remote ref atomically. If that repository's own dispatcher is appending
  to its event store at that moment, its tree reads dirty and the push is refused and alarmed. The next push of that
  repository, by its own dispatcher or by hand, carries the commits.

## Parameters

| parameter | value | basis |
|---|---|---|
| `dispatch.cross_repo_root` | `..` | the governed repositories are siblings (`seldon.yaml prior_art.internal_roots`) |
| `dispatch.cross_repo_branch` | `main` | sessions commit on a sibling's main by path (AD-036-R12) |

## Code

`seldon/core/dispatch.py`: `repo_push_targets`, `cross_repo_launch`, `push_cross_repo`, `CROSS_REPO_REFUSALS`.
`seldon/commands/dispatch_worktree.py`: `push_named_repos`, `held_cross_repo`, `CROSS_REPO_PUSH_REFUSED`.
`seldon/commands/dispatch.py` `_launch_inplace` and `dispatch_worktree._start_claimed` record `push_repos` at launch.
Tests: `tests/test_disp004r_cross_repo_push.py`.

**Transition.** The supervisor that merges this branch runs the code from before it, so this task's own finish does
not push squiddy or ai-readiness-kg. Part B's readings are in the RESULT.
