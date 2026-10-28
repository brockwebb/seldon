# RESULT: SEL-015, the prepare-commit-msg hook is installed and tracked in squiddy, arnold, ai-readiness-kg and hazbrief-mcp

**Executed:** Claude Code (Opus 5.5), dispatched headless in worktree `dreamy-herding-axolotl`, 2026-10-28, on seldon
main `ba579eb`. **Addenda:** none (globbed `cc_tasks/2026-10-28_SEL-015_*ADDENDUM*.md`: no files).
**Spend:** zero model calls. **Network:** none. I pushed nothing (the launch instruction forbids it; see "Not done here").
Recall used: seldon:2026-10-27_DISP-004R_a_cross_repo_task_is_pushed_in_every_repository_it_names_RESULT

| Part | State |
|---|---|
| Step 0 | **Both facts hold.** `seldon hooks prepare-commit-msg --help` exited 0. The `seldon` on PATH imports `/Users/brock/GitHub/seldon/seldon/__init__.py`, the primary checkout, which is main. `git cat-file -e main:.githooks/prepare-commit-msg` also exited 0. |
| A, install in the four | **Done.** All four installs exited 0. Each repo now reports `installed: true, sequenced: true, problems: []` and tracks `.githooks/prepare-commit-msg`. None of the installs left an uncommitted change. |

Evidence: `docs/evidence/sel015/`. It holds the driver `run.py`, `<repo>.before.txt` and `<repo>.install.txt` (full
command transcripts with exit codes), and `checks.py`, which runs the success criteria.

## Per repository

| repo | status before | the install committed (oldest first) | status after |
|---|---|---|---|
| squiddy | installed, `sequenced: false`, drafts true | `61e75db0` `.githooks/prepare-commit-msg` | installed, `sequenced: true` |
| arnold | installed, `sequenced: false`, **drafts false** | `c0e30c0` `.githooks/commit-msg`, `.githooks/prepare-commit-msg`; then `6114fe8` `.gitattributes` (`governed/ledger/events.jsonl merge=union`) | installed, `sequenced: true`, drafts true |
| ai-readiness-kg | installed, `sequenced: false`, drafts true | `42de3f90` `.githooks/commit-msg` (was untracked), `.githooks/prepare-commit-msg` | installed, `sequenced: true` |
| hazbrief-mcp | installed, `sequenced: false`, drafts true | `df0fc03` `.githooks/prepare-commit-msg`; then `6444fc3` `.gitattributes` (`seldon_events.jsonl`, `state/prior_art_queries.jsonl` merge=union) | installed, `sequenced: true` |

`core.hooksPath` was the relative `.githooks` (local scope) in all four, both before and after. All four stayed on
`main`.

**The new hook already admits commits.** `_write_hook` writes the hook file before `commit_hooks` commits it, so git
ran `prepare-commit-msg` on every one of the commits above. In arnold and hazbrief-mcp, the later `.gitattributes`
commit also went through all three tracked hooks. Every one of them landed.

## Porcelain before and after (the judgment criterion)

| repo | before | after |
|---|---|---|
| squiddy | clean | clean |
| arnold | ` M cc_tasks/2026-10-08_per-exercise-measurement-schema.md`, ` M graphs/arnold-evidence/config.yaml` | the same two lines |
| ai-readiness-kg | ` M seldon_events.jsonl`, `?? .githooks/commit-msg` | ` M seldon_events.jsonl` (the untracked hook is now committed) |
| hazbrief-mcp | ` M seldon_events.jsonl` | ` M seldon_events.jsonl` |

The install added no uncommitted change of its own in any of the four. The only line that changed is ai-readiness-kg's
`?? .githooks/commit-msg`, and it went away because the install committed that file, as the task expected.

## Success criteria

`python docs/evidence/sel015/checks.py` runs the eight `check:` lines as written: four `seldon hooks status --repo …`
and four `git -C … ls-files --error-unmatch .githooks/prepare-commit-msg`. **All eight exited 0** (`ALL_CHECKS_EXIT 0`).

## Findings (differences from the task's list)

1. **The commit order is the reverse of what the task (and SEL-012's RESULT) lists.** In arnold and hazbrief-mcp,
   the hooks commit is the parent and the `.gitattributes` commit is the tip (`git log --format="%H %P"`).
   `seldon/commands/hooks.py:42-47` runs `H.install` (which commits the hooks) before `H.declare_union`, but it
   prints the union line first (lines 54-63). SEL-012's table took its order from that output. Nothing breaks
   either way, because both commits run through the same hooks. Only the printed order is misleading. I did not
   change it, because this task is the install, not installer code.
2. **arnold's `drafts` went from false to true.** arnold had no `.githooks/commit-msg` before. `drafts_enabled`
   (`seldon/core/hooks.py:246`) needs that file, so until now arnold's prior-art check ran in `pre-commit`, which
   fails closed. Now that the install has written and committed it, arnold admits `draft:` commits the way the other
   three do. This follows from the rehearsal's list, which shows `commit-msg` being committed in arnold, but neither
   SEL-012 nor this task said it outright.
3. **The trees were dirty in different ways than SEL-012 recorded.** SEL-012 counted 8 uncommitted files in
   hazbrief-mcp. Today there is 1 (` M seldon_events.jsonl`). ai-readiness-kg also has ` M seldon_events.jsonl`, which
   SEL-012 did not mention. This is operator or dispatcher state, and the pathspec-limited commits left it alone.

## Not done here

- **Pushes of the four siblings.** I made no push (launch instruction). Each main is now ahead of `origin/main`:
  squiddy by 1, arnold by 3, ai-readiness-kg by 7 and hazbrief-mcp by 11. Only squiddy's count is all this task's
  commits. The other three also carry earlier unpushed commits, so they are ahead by more than this task made. Per
  DISP-004R, the dispatcher pushes a sibling only when this task's `**Repo:**` clause says `push`, which it does not.
  The push also refuses on `dirty_tree`, and arnold, ai-readiness-kg and hazbrief-mcp all hold the operator's
  uncommitted files. So these pushes are the operator's. In a plain shell (Terminal), run in any order:
  ```
  git -C /Users/brock/GitHub/squiddy push origin main
  git -C /Users/brock/GitHub/arnold push origin main
  git -C /Users/brock/GitHub/ai-readiness-kg push origin main
  git -C /Users/brock/GitHub/hazbrief-mcp push origin main
  ```
  Before pushing the last three, run `git -C <repo> log origin/main..main --oneline` to see the earlier commits that
  will go out with this task's commits.
- **The merge of this branch and `cc complete`:** the dispatcher does these (launch instruction).
