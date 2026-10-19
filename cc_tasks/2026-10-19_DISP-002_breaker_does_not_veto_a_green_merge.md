# DISP-002: a classifier breaker trip does not veto a merge the stop gate passed; the three commands auto mode refused in two tasks are allow-listed; an evidence-writing script commits what it writes

**Repo:** seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green (AD-034 ADDENDUM 01).
**Date:** 2026-10-19. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** AD-034-R5 and R6 (merge on green; the dispatcher completes the task), AD-036-R11 (an automatic writer commits what it writes), AD-038-R6 (negative control and toil measure), FRICTION-002 Part D step 3 (the kill rule, ResearchTask `65037d58`). Write the ruling as AD-034 ADDENDUM 02; close `65037d58` with the measurement below.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.3M tokens. Basis: three small code changes with tests; the floor is 131K (AD-037-R11).
**Parts:** A 0.4, B 0.3, C 0.3.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: DISP-001R's branch holds its RESULT | check: `git cat-file -e worktree-2026-10-19_DISP-001R_worktree_name_and_spend_floor:cc_tasks/2026-10-19_DISP-001R_worktree_name_and_spend_floor_RESULT.md`
- premise: the breaker finish is on record | check: `grep -q "finished eadf9e03 classifier_breaker" logs/seldon_dispatch.log`
- premise: DISP-001R's ruling is on its branch | check: `git cat-file -e worktree-2026-10-19_DISP-001R_worktree_name_and_spend_floor:docs/design/AD-037_ADDENDUM_01_spend_floor_tool_boundary_liveness.md`

Glob and read every sibling `*DISP-002*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.45M.

## The measurement (the kill rule, 65037d58)

Three tasks have run under `permission_mode: auto`: SEC-001R (2 blocks: writing secret values into `.env` files; rewriting `claude_desktop_config.json`), DISP-001R (3 blocks: `git worktree remove --force` of empty trees; a plain `cp` out of a kept worktree; a `pytest` run with `PYTHONPATH` set to the worktree), DISP-001 (0; reaped before any). Classified: SEC-001R's two are the policy working as intended (secrets are operator writes, and that is now doctrine); DISP-001R's three are false positives against work the task file ordered. That is 1.0 false positive per task over three tasks, over the kill rule's threshold of one. The rule's remedy, back to `bypassPermissions`, would also remove the one block that was right. This task takes the narrower remedy: allow rules for the command classes a task may legitimately run, and a breaker that cannot throw away green work. If a fourth task under auto mode shows a new false positive class, the kill rule applies as written.

## Part A: the breaker cannot veto green

1. In the dispatcher's finish path: when the session exited 0 with its RESULT committed on the branch and the stop gate (`stop_gate` record, verdict `pass`) and the suite are green, the dispatcher merges and completes, whatever the breaker count. `classifier_breaker` with green work is recorded as `breaker_tripped_merged`, with the three denials' reasons, and notified as such. `classifier_breaker` with the gate unpassed stays `blocked`.
2. Then apply it to the case on disk: merge `worktree-2026-10-19_DISP-001R_worktree_name_and_spend_floor` into main through the hooks (its suite passed on 2316793; re-run the full suite on the merge commit), complete `eadf9e03` with the branch's RESULT, and remove its worktree. Record the merge sha in the RESULT.
3. Tests, failing on HEAD: a stubbed finish with `classifier_blocks: 3`, exit 0, RESULT present and `stop_gate: pass` ends `merged`; the same with `stop_gate: fail` ends `blocked`.

Acceptance:
- `check: pytest tests/test_disp002_breaker.py -q`
- `check: git merge-base --is-ancestor worktree-2026-10-19_DISP-001R_worktree_name_and_spend_floor main`

## Part B: allow rules for what a task is allowed to do

1. The launch settings the dispatcher passes gain `permissions.allow` for exactly these shapes, each with the task-file instruction that needs it quoted beside it in `seldon.yaml`: `Bash(git worktree *)`, `Bash(git branch -D *)`, `Bash(cp *)`, `Bash(pytest *)`, `Bash(python -m pytest *)`. Nothing else. Secrets writes stay with the classifier.
2. Remove the three empty kept worktrees and branches the classifier refused in DISP-001R (RECALL-001, MCP-001, DISP-001; 0 commits beyond main each), and DISP-001's untracked `tests/test_disp001_worktree_name.py` with them.
3. Test: a launch's settings JSON carries the five rules and no others.

Acceptance:
- `check: pytest tests/test_disp002_allow.py -q`
- `check: ! git worktree list | grep -qE "RECALL-001|MCP-001|DISP-001_worktree_name_capped"`

## Part C: a script that writes evidence commits it

1. `scripts/sec001/rewrite_desktop_config.py --evidence DIR` commits what it writes under `docs/evidence/` with a path-scoped commit through the hooks (AD-036-R11), as `sec001: evidence: <dir>`. It refuses to run from a worktree other than the primary when `--apply` is given (the config names the primary's launcher).
2. Commit the two files the operator's run left untracked on main, `docs/evidence/sec001/applied/config_after.json` and `servers.txt`, the same way. They are redacted; verify with the secret scanner before committing.
3. Test: the script, run with `--evidence` on a temp repo, leaves a clean tree.

Acceptance:
- `check: pytest tests/test_sec001_rewrite.py -q`
- `check: git ls-files --error-unmatch docs/evidence/sec001/applied/config_after.json docs/evidence/sec001/applied/servers.txt`

## Report

RESULT under 20 lines: the merge sha for DISP-001R, the three removed branches, the five allow rules, the kill-rule measurement table (task, blocks, classification), tokens against 0.3M.
