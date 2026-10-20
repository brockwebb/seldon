# AD-034 ADDENDUM 02: the classifier breaker does not veto green work; allow rules; kept trees that hold nothing are swept; the kill rule applied

**Date:** 2026-10-19
**Status:** Accepted. Implemented by DISP-002 (`cc_tasks/2026-10-19_DISP-002_breaker_does_not_veto_a_green_merge.md`).
**Amends:** AD-034-R5 and R6 (merge on green; the dispatcher completes), AD-034 ADDENDUM 01 section 3.4 ("Nothing deletes a branch"), FRICTION-002 Part D (the breaker as a line stop; the kill rule, ResearchTask `65037d58`). No new ruling label: DISP-001R's branch, not yet on main, holds register records 292 to 294 chained from 291, and a record written here would fork that chain. The three rules below amend R5, R6 and ADDENDUM 01 in place, as ADDENDUM 01 did; a later task may register them once both branches are on main.
**Applies:** AD-036-R11 (an automatic writer commits what it writes) to `scripts/sec001/rewrite_desktop_config.py`.
**Code:** `seldon/commands/dispatch_worktree.py` (`finish_session`, `is_green`, `remerge_breaker_green`, `sweep_stale_kept`), `seldon/commands/dispatch.py` (`_classifier_reading`, `_breaker_and_stale`, `_session_settings`), `seldon/core/dispatch.py` (`_load_allow`), `seldon.yaml` (`dispatch.allow`, `dispatch.gate_command`, `dispatch.permission_mode`).
**Tests:** `tests/test_disp002_breaker.py`, `tests/test_disp002_allow.py`, `tests/test_sec001_rewrite.py`, `tests/test_friction002_auto_mode.py`.

## 1. Evidence

DISP-001R (`eadf9e03`) ran under `permission_mode: auto`. At 14:40 to 14:41Z the classifier refused three actions in a row: `git worktree remove --force` of an empty kept tree ("Irreversible Local Destruction"), a `cp` out of that tree ("Interfere With Workloads"), and a `pytest` run with `PYTHONPATH` set to the worktree. The CLI's breaker text was written. The session went on for two more hours, declared Parts B and C, and its Stop gate passed at 16:51:23Z (`stop_gate`, verdict `pass`, nothing failed). It exited 0 with its RESULT committed. The finish read the breaker and recorded `classifier_breaker`: blocked, worktree kept, line stop written. Its full suite had passed on `2316793` (2648 passed). Green work was thrown away because of three refusals that were false positives against what its task file ordered.

## 2. The rulings

**Rule 1 (amends R5, R6). The breaker does not veto green work.** When a worktree session's breaker tripped (the CLI's text in its log) and the session exited 0, committed its RESULT on its branch, and its Stop gate ran and passed (`stop_gate` verdict `pass`), the finish goes on to the merge as for any green session. The finish record carries `breaker: {outcome: breaker_tripped_merged, blocks, denials}`, with every denial's reason, and the notification's outcome is `breaker_tripped_merged`. No line stop is written for it. A gate that never ran is not evidence here: an ordinary finish with no declared Part still merges, but only a gate that ran and passed lifts the breaker's veto. A breaker with the gate unpassed is a line stop and `blocked`, as before. Everything after the gate still applies: model receipt, rebase, re-gate, union check, and spec hash.

*The case on disk.* A pass with no session in flight applies rule 1 to a finish recorded before it (`remerge_breaker_green`). The task must be `blocked`, its last `dispatch_finished` a worktree finish of outcome `classifier_breaker` that is green, and its tree still present. It is walked `blocked -> in_progress` and handed to `_merge`. The result is a new `dispatch_finished`, `merged` or `merge_blocked`, so each task is reconsidered once. A task redriven in the meantime is left to its relaunch. DISP-001R's branch changes the dispatcher files this task also changes, so its rebase overlaps and needs a re-gate. `dispatch.gate_command` is therefore now set to the full suite on the worktree's own code (`PYTHONPATH=.`) with the primary's `.env`. Before this, a serial task with such an overlap was blocked `regate_unavailable`.

**Rule 2. Allow rules, each with its instruction.** A dispatched session's launch settings carry `permissions.allow` from `dispatch.allow`. Each entry pairs a `Bash(...)` rule with the task-file instruction that needs it, quoted. The loader refuses an entry without its instruction, and anything other than a Bash rule. Seldon's five are the shapes of DISP-001R's three false positives: `Bash(git worktree *)`, `Bash(git branch -D *)`, `Bash(cp *)`, `Bash(pytest *)`, `Bash(python -m pytest *)`. Nothing else is allowed: SEC-001R's two blocks (writing secret values into `.env` files, rewriting `claude_desktop_config.json`) were the classifier working as intended, and secrets stay operator writes.

*Not verified here:* whether a command that begins with an environment assignment (`PYTHONPATH=... python -m pytest ...`, DISP-001R's third block) matches `Bash(python -m pytest *)`. The next auto-mode launch's `classifier_block` records answer it.

**Rule 3 (amends ADDENDUM 01 section 3.4). A kept tree that holds nothing is swept, and its branch deleted.** A pass with no session in flight removes a kept worktree (`worktree_kept`, never merged) when all of these hold:

- its task is no longer `blocked` or `in_progress`: redriven (`proposed`, `accepted`) or ended (`superseded`, `withdrawn`, `completed`);
- its branch has 0 commits beyond main;
- nothing tracked in it is modified.

Its branch is then deleted with `git branch -d`, which refuses a branch main does not contain, so no commit can be lost. An untracked file keeps the tree of a redriven task. In an ended task's tree it is named in the record (`discarded_untracked`) and removed. Each removal is a `worktree_removed` record with `reason: stale_kept`. A blocked task's tree stays: it is the evidence of an open stop. This is the dispatcher doing what a dispatched session may not do: RECALL-001's, MCP-001's and DISP-001's empty trees waited on an operator because the classifier refuses `git worktree remove`, and a session's worktree guard refuses git aimed at another tree.

**Part C, no new rule.** The script now follows AD-036-R11: `rewrite_desktop_config.py --evidence DIR` commits the two files it writes. The commit is path-scoped, goes through the hooks, and carries the message `sec001: evidence: <dir>`. It refuses a directory outside the repository's `docs/evidence/`. A failed commit unstages, exits 2 and says the files are uncommitted. `--apply` refuses to run from a linked worktree, because the config names the primary checkout's launcher. The operator's run of 2026-10-19 left `docs/evidence/sec001/applied/{config_after.json,servers.txt}` untracked. They were committed on main as `6ccf217` before this task launched.

## 3. Prior art

- **Circuit breaker** (Nygard, *Release It!*, 2007; Fowler, "CircuitBreaker", 2014). A breaker stops further calls into a failing dependency. It protects what is about to happen, and it does not judge work already completed. Rule 1 lets the breaker end the session and leaves the verdict on finished work to the gate that exists for that purpose.
- **Required versus advisory checks.** GitHub branch protection merges on the required status checks and shows the others without blocking. The Stop gate is this repository's required check (FRICTION-002 Part C). The classifier count is advisory evidence, recorded on the finish.
- **Claude Code permission rules** (code.claude.com/docs, settings and permissions). `permissions.allow` with `Bash(<prefix> *)` patterns, passed per launch through `--settings`, the same channel FRICTION-002's hooks use.
- **Pruning merged or empty work branches.** GitHub's "automatically delete head branches" and `git worktree prune`. A branch that main contains carries nothing. `git branch -d` is git's own guard for that claim.

## 4. Negative controls (AD-038-R6)

A breaker with the gate unpassed stays `blocked` with its line stop. A gate that never ran does not lift the veto. A remerged task is not reconsidered by the next pass. A blocked task's kept tree stays. A kept branch with a commit beyond main stays. A redriven task's tree with an untracked file stays. A project without `dispatch.allow` launches with no `permissions` block.

## 5. The kill rule (ResearchTask 65037d58), measured and applied

| task | auto-mode blocks | classification |
|---|---|---|
| SEC-001R | 2 | policy as intended: secret values into `.env`; rewriting `claude_desktop_config.json` |
| DISP-001 | 0 | reaped before any |
| DISP-001R | 3 | false positives against ordered work: `git worktree remove --force` of empty trees, `cp` out of a kept tree, `pytest` with `PYTHONPATH` |
| DISP-002 | 5 | 1 arguable: `git merge` of DISP-001R's branch into this task's own branch, which the session's own instruction ("do not merge") made doubtful. 4 false positives, all read-only: `git diff main...<branch>`, `grep` in DISP-001R's tree, `ls docs/design \| grep`, and `grep` of a test file in this task's own tree. They were labelled "Git Destructive" and "Modify Shared Resources" |

After the narrower remedy (rules 1 and 2), the task file set its own condition: "If a fourth task under auto mode shows a new false positive class, the kill rule applies as written." DISP-002 is the fourth task, and refusals of read-only commands are a class rule 2's allow list does not cover. The refusals followed a refused action, which suggests the classifier carries suspicion forward through the transcript. So `dispatch.permission_mode` goes back to `bypassPermissions`, and Issue "auto mode kill rule applied" records it. The allow rules, the `PermissionDenied` hook and the breaker handling stay, so a return to `auto` is one line in `seldon.yaml`, and the evidence for it keeps accruing in any project still on auto mode. What `bypassPermissions` gives up is SEC-001R's kind of block, a session writing secrets. The worktree isolation (ADDENDUM 01) does not depend on the permission mode: it was probed under `bypassPermissions`.
