# DISP-001R: the CLI names the worktree; a launch failure is not a session failure; the spend ceiling is never below the cost of loading a session, and a hard stop is delivered at a tool boundary, never by SIGTERM mid-call

**Repo:** seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green (AD-034 ADDENDUM 01).
**Date:** 2026-10-19. **Authored by:** a Desktop session in squiddy (SQ8). **Re-issues:** DISP-001 (`98d14c80`) and its ADDENDUM 01. DISP-001 was reaped by station (d) five minutes after launch: `session_tokens` read 134,746 against a ceiling of 80,000 x 1.2, because the estimate I wrote was below what any session costs to load its context, and the reap fired one poll later while the session was inside a five-minute pytest call with no boundary at which to read the stop. The author's error (an estimate below the floor) and the station's two defects (a ceiling that can sit below the floor; a kill that does not wait for a boundary and reads no liveness) are both fixed here.
**Governing:** AD-034 ADDENDUM 01 (worktree is the only mode); AD-037-R6 (d) (the dispatcher's hard stops); AD-037-R7 (inspection reserve); AD-038-R6 (a control ships with its negative control and a toil measure). Write the station changes as AD-037 ADDENDUM (next number) with the DISP-001 events (`session_stop` 04926773, `andon_reaped` d787bf17) as evidence. No new ruling beyond the three below.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.35M tokens. Basis: SEC-001R, two Parts of comparable size, ran 0.10M by the station's own counter plus the context floor; DISP-001 read 0.13M at five minutes before doing anything. Three Parts here.
**Parts:** A 0.3, B 0.5, C 0.2.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: DISP-001's reap is on record | check: `grep -q '"reason": "spend_ceiling"' seldon_events.jsonl`
- premise: the two long-name launch failures are on disk | check: `grep -q "must be 64 characters or fewer" logs/dispatch/2026-10-17_RECALL-001_registration_retrieves_the_repos_own_history.log`
- premise: the station reads tokens from the session log | check: `grep -q "def session_tokens" seldon/core/stations.py`

Glob and read every sibling `*DISP-001R*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.

## Part A: the CLI names the worktree; a launch that never ran is `launch_failed`

1. The dispatcher passes `--worktree` with no name. The CLI generates one ("If you omit the name, Claude generates one such as `bright-running-fox`", code.claude.com/docs/en/worktrees). The dispatcher reads the worktree path from the session's first `stream-json` message (verify the field in CLI 2.1.302's actual output on the first launch; quote the line in the RESULT) and records task id, stem, worktree path and branch in `dispatch_launched`. Only if the output carries no path: fall back to `<8 of task id>_<stem truncated to 60 total>` and say so in the RESULT.
2. A CLI exit before the first `assistant` message is recorded as `launch_failed` with the CLI's stderr line in the event and in the notification text, and the task returns to `proposed`, not `blocked`. The dispatcher does not relaunch a `launch_failed` task until the recorded stderr line differs from the last one for that task.
3. Tests, each failing on HEAD: a 90-character stem launches without error; a stubbed CLI exiting 1 with "Invalid worktree name" leaves the task `proposed`, writes `launch_failed` with that text, and is not relaunched on the next pass.
4. Remove the three empty kept worktrees and branches (RECALL-001, MCP-001, DISP-001); verify each holds no commits beyond its base and record the names and counts.

Acceptance:
- `check: pytest tests/test_disp001_launch.py -q`
- `check: ! git worktree list | grep -qE "RECALL-001|MCP-001|DISP-001_worktree_name_capped"`

## Part B: the ceiling has a floor; a hard stop waits for a boundary; the reap reads liveness

1. **Floor.** The spend ceiling is `max(estimate x spend_ceiling_factor, floor)`, where `floor` is measured, not configured: the median of `session_tokens` at the first inspection across the last ten completed launches in this repository (read from `dispatch_launched` and the session logs; DISP-001's 134,746 at five minutes is one data point). Record the floor in the `session_stop` reading when it is the binding term. `seldon qc chart` reports it weekly.
2. **Boundary.** A hard stop is delivered to the session, not only written to the ledger: the dispatcher's `PreToolUse` hook (the hooks are already in the launch settings) reads the ledger for an unanswered hard stop on this task and refuses the next tool call with the stop's reason, so the session halts at its next boundary and writes `andon_halted` itself. The reap stays as the backstop.
3. **Liveness.** The reap fires only when, in addition to the unanswered hard stop aging past `reap_after_intervals x poll_interval_s`, the session log has not grown for that same interval. A session that is writing heartbeats is alive and gets its boundary. Record `last_log_growth_s` in `andon_reaped`.
4. Tests, each failing on HEAD: an estimate below the floor does not produce a hard stop at the first inspection; a hard stop on the ledger makes the next tool call refuse with the reason; a hard stop aged past the interval with a log that grew 10 s ago is not reaped, and with a log that last grew `wait_s + 1` ago is.
5. AD-037 ADDENDUM with the three rules and the DISP-001 evidence.

Acceptance:
- `check: pytest tests/test_disp001r_stations.py -q`
- `check: ls docs/design/AD-037_ADDENDUM_*.md | grep -q .`

## Part C: redrive

1. `seldon dispatch redrive` for `ca92adf2` (RECALL-001) and `d0728ec7` (MCP-001). Do not run them.
2. Read `cc_tasks/2026-10-17_MCP-001_*.md`'s `**Spend:**` (0.15M). If 0.15M x 1.2 is below the floor measured in Part B, write `MCP-001 ADDENDUM 01` stating the floor applies, so the operator sees why the header's number is not the ceiling.

Acceptance:
- `check: seldon task list --state accepted | grep -qE "ca92adf2|d0728ec7"`

## Report

RESULT under 20 lines: the naming line quoted from the CLI's output, the measured floor and the ten launches it came from, the three tests' names per Part, the redriven ids, the removed branches with commit counts, tokens against 0.35M.
