# ADDENDUM 01 to 2026-10-27_RECALL-002R_recall_turned_on_in_squiddy_arnold_and_ai_readiness_kg: ai-readiness-kg's dirty tree and unpushed commits at the finish

**Author:** OODA knowledge source on 2909ce0f (AD-038-R16)
**Source:** `cc_tasks/2026-10-27_DISP-004R_a_cross_repo_task_is_pushed_in_every_repository_it_names_RESULT.md` (Part A; Part B; Limits); ruling AD-034-R12 (`docs/design/AD-034_ADDENDUM_06_cross_repo_task_pushed_in_every_repo_it_names.md`); AD-036-R12.

## What the predecessor's RESULT changes here

1. **The push of all four repositories is live, and this task is the first to use it.** The RESULT says DISP-004R's
   own merge ran the pre-change supervisor, so the new step first acts on the next cross-repo task. That task is this
   one. Its Repo line (`L4: commit, merge, push in all four.`) goes through `repo_push_targets` (`seldon/core/dispatch.py:1481`)
   and resolves to squiddy, arnold and ai-readiness-kg. I checked this against HEAD, with seldon left out as the
   primary, so Part B's sentence "DISP-004R ... makes the finish step push all four" holds.
2. **ai-readiness-kg will likely refuse its push.** At the RESULT's reading (2026-10-27), ai-readiness-kg was 4 commits
   ahead of origin. The 4 commits were squiddy SQ-022b's: `570c98f8`, `089669b8`, `b742fb93` and `15548b92`. Its tree
   was dirty with ` M seldon_events.jsonl` (8 lines from its own stopped dispatcher) and `?? .githooks/commit-msg`.
   AD-034-R12's finish refuses a dirty tree (`dirty_tree`) and raises an alarm. DISP-004R's Part B recipe, Brock's
   `git push origin main` in ai-readiness-kg, may not have run. On 2026-10-28 that checkout's `refs/heads/main`
   (`620b582d`) still differed from `refs/remotes/origin/main` (`e2f0e56f`).

## What this task now does

- **Part A, ai-readiness-kg.** Commit the seldon.yaml change by path (`git commit -- seldon.yaml`, per AD-036-R12).
  Do not stage, commit, revert or delete `seldon_events.jsonl` or `.githooks/commit-msg` there. They belong to that
  repository's dispatcher and to DESK-004R's hooks installer (AD-038-R15), as the DISP-004R RESULT records. The same
  by-path rule applies in squiddy and arnold if either tree is dirty at launch.
- **Part A, every repository.** If a `recall:` block is already present, compare it with seldon's line by line and
  record that it matches or what differs. Do not add a second block. If it already matches, Part A in that repository
  is a verified no-op with no commit, and the finish reads it as `unmoved`.
- **RESULT.** Add a short table: each sibling's `git status -sb` at launch and at the session's end, and its
  `ahead` count. A `dirty_tree` refusal for ai-readiness-kg at the dispatcher's finish is the expected AD-034-R12
  behaviour on that state. It is not a failure of this task, and the session does not push by hand to work around
  it (the launch clause forbids it). If ai-readiness-kg's push does go through, it also carries SQ-022b's 4 commits.
  That closes DISP-004R's open Part B, so say so in the RESULT.

Parts, premises, weights and the stop condition are unchanged.
