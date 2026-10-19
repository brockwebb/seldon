# DISP-001 ADDENDUM 01: let the CLI name the worktree; cap only as the fallback

Written 2026-10-19 by a Desktop session in squiddy (SQ8), before DISP-001 launched.

The CLI already solves this. Its worktree page states: "If you omit the name, Claude generates one such as `bright-running-fox`." FRICTION-002 invented a naming scheme and hit the CLI's limit; DISP-001 Part A step 1 as written invents a second scheme. Replace step 1 with:

1. The dispatcher passes `--worktree` with no name. It reads the worktree path the CLI chose from the session's first `stream-json` message (the `init` record carries `cwd`; verify the field name against CLI 2.1.302's actual output in the first launch and record the line in the RESULT). The branch is `worktree-<that name>`. The dispatcher records the mapping (task id, stem, worktree path, branch) in `dispatch_launched`, as before.
2. Only if the CLI's output does not carry the path: fall back to the capped name from the original step 1, and say so in the RESULT with the raw first message quoted.

Tests from the original step 2 become: a launch with no name yields a recorded worktree path under `.claude/worktrees/` and a branch that exists; a 90-character stem launches without error. Steps 3 and 4 stand.

Also, in the same change: a launch that fails before any model turn (CLI exit before the first `assistant` message) is recorded as `launch_failed`, not `session_failed`, with the CLI's stderr line in the event and in the notification, and the task returns to `proposed`, not `blocked`, because it never ran. The dispatcher does not retry a `launch_failed` task on the next pass until the recorded stderr line differs from the last one for that task, so a repeating launcher defect is noticed once and does not loop. One test: a stubbed CLI that exits 1 with "Invalid worktree name" leaves the task `proposed`, writes `launch_failed` with that text, and is not relaunched on the next pass.
