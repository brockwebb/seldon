# DISP-001: the dispatcher's `--worktree` name fits the CLI's 64-character limit for every task

**Repo:** seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green (AD-034 ADDENDUM 01).
**Date:** 2026-10-19. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** AD-034 ADDENDUM 01 (worktree is the only mode); AD-038-R6 (a control ships with its negative control). No new ruling.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.08M tokens. Basis: one function, one test, two redrives.
**Parts:** A 1.0.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: the two failed launches are on disk | check: `grep -q "must be 64 characters or fewer" logs/dispatch/2026-10-17_RECALL-001_registration_retrieves_the_repos_own_history.log`
- premise: the dispatcher passes the task stem as the worktree name | check: `grep -rq -- "--worktree" seldon/core/dispatch.py seldon/commands/dispatch.py seldon/core/worktree.py`

Glob and read every sibling `*DISP-001*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.15M.

## The defect, measured

FRICTION-002 passes the task file's stem as `--worktree <name>`. CLI 2.1.302 refuses a name over 64 characters. Two of the three launches after FRICTION-002 failed before any model turn: RECALL-001 (stem 66 chars) and MCP-001 (70 chars), each `session_failed exit=1 -> blocked` within 6 seconds, with an empty worktree directory kept. SEC-001R (56 chars) ran. The task stems in this repository run to 90 characters; the limit was not in FRICTION-002's tests.

## Part A

1. The worktree name is `<first 8 of the task artifact id>_<stem truncated so the whole name is at most 60 characters>`, with no trailing `_` or `-`. The branch name follows the same rule with the `worktree-` prefix. The dispatcher records the mapping (task id, stem, worktree name, branch) in the `dispatch_launched` event so a log reader can find the tree.
2. Tests, each failing on HEAD: a 90-character stem produces a name of at most 60 characters that starts with the id prefix; two tasks whose stems share the first 50 characters get different names; a 20-character stem is unchanged apart from the id prefix.
3. The empty kept worktrees and branches from the two failed launches are removed by the sweep (they hold no commits; verify with `git log` on each branch before removing, and record the two branch names and their commit counts in the RESULT).
4. Redrive `ca92adf2` (RECALL-001) and `d0728ec7` (MCP-001) with `seldon dispatch redrive`, so they return to the queue. Do not run them.

Acceptance:
- `check: pytest tests/test_disp001_worktree_name.py -q`
- `check: ! git worktree list | grep -q RECALL-001`

## Report

RESULT under 12 lines: the naming rule as implemented, the two redriven ids, the two removed branches with commit counts, tokens against 0.08M.
