# SEL-030: a withdrawn task's dispatched session kept running for ninety minutes after the withdrawal, and wrote Issue events to the live graph that never reached main's event log

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-09
**Reporter:** Desktop session (hazbrief-mcp), from HB-140R's RESULT.

## What was observed

1. hazbrief-mcp HB-140 (`249b85dc`) was launched by the standing dispatcher at about 05:05Z on 2026-11-09 and withdrawn
   at 05:10:20Z (graph `updated_at`). Its session did not stop. It ran to completion at 06:39Z on
   `worktree-sunny-shimmying-pebble` (commit `4d97f03a`), recording 14 briefs, live network calls included, and
   running the full gate.
2. The dispatcher kept the worktree as `session_failed` because the task was `withdrawn`. Nothing was merged.
3. During those ninety minutes the session wrote two graph events: Issue `8b992307` moved to `resolved`, and Issue
   `5b737052` was created. Neither event is in main's `seldon_events.jsonl`. The live graph holds `5b737052` (open,
   "terrain on the 14 one-wind briefs needs the two USGS elevation hosts"); a rebuild from the log would not.
4. HB-140R (`afa89a9d`) found `8b992307` in the live graph as `resolved` and had to re-open it. Its RESULT names both
   events and the kept worktree ("Prior art here" and "For Desktop").

## What hazbrief-mcp wants to know back

- Whether withdrawing a task is meant to stop its running session, and if so why this one ran on. The spend it made
  after withdrawal (tokens and live network calls) was not wanted.
- Where events written to the live graph by a session whose branch is never merged are supposed to go: into main's
  log, discarded from the graph, or flagged. Today the graph and the log disagree, and `seldon events replay-check`
  would presumably report it.
- What a consumer should do with `5b737052` now: update it (an event about an artifact whose creation is not in the
  log), or leave it until the producer decides.

## Evidence

- hazbrief-mcp `seldon_events.jsonl`: `249b85dc` withdrawal; `afa89a9d` event `a4b88d07` (`8b992307` resolved to open,
  2026-11-09T09:22:43Z).
- hazbrief-mcp `cc_tasks/2026-11-08_HB-140R_..._RESULT.md`, sections "Prior art here" and "For Desktop".
- hazbrief-mcp `logs/dispatch/2026-11-08_HB-140_the_fifteen_reoriented_briefs_..._.log` (the withdrawn session's run).
- The kept worktree `.claude/worktrees/sunny-shimmying-pebble`, branch `worktree-sunny-shimmying-pebble`, `4d97f03a`.
