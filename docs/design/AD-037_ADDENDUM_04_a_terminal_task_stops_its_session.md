# AD-037 ADDENDUM 04: a task that goes terminal stops its running session at the next tool boundary

**Date:** 2026-11-09. **Status:** Accepted. Implemented by SEL-034 Part A
(`cc_tasks/2026-11-09_SEL-034_a_terminal_task_stops_its_session_and_a_kept_worktrees_events_reach_mains_log_or_are_discarded_on_record.md`),
answering hazbrief-mcp's filing SEL-030. **Extends:** AD-037-R12 (a hard stop refuses the session's next tool call and
records `andon_halted`). One new ruling.
**Code:** `seldon/core/stations.py` (`TERMINAL_TASK_STATES`, `terminal_transition`, `terminal_stop_due`,
`signal_terminal`, the inspection's backstop and its undeferred reap); `seldon/core/artifacts.py` (`transition_task`'s
signal); `seldon/commands/dispatch_stations.py` (`_terminal_gate` in `tool-gate`, the Stop gate's early return);
`seldon/commands/dispatch_worktree.py` (`finish_session`: a terminal task's finish is `session_failed`).
**Tests:** `tests/test_sel034_terminal_task_stops_session.py`.

## 1. Evidence

1. **HB-140.** hazbrief-mcp task `249b85dc` was launched at about 05:05Z on 2026-11-09 and withdrawn at 05:10:20Z. Its
   session ran on to 06:39Z on `worktree-sunny-shimmying-pebble` (`4d97f03a`): 14 briefs, live network calls and the
   full gate, all after the withdrawal. The dispatcher kept the tree `session_failed`; nothing merged (SEL-030).
2. **Why it ran on.** The PreToolUse gate (AD-037-R12, DISP-001R) delivered only hard `session_stop` records, and a
   withdrawal wrote none. The holder's inspection read spend and disk, never the task's state. Nothing in the
   machine connected "the task is withdrawn" to "the session is still spending".

## 2. Prior art

- **Graceful termination with a forced backstop (Kubernetes pod termination; POSIX SIGTERM then SIGKILL).** A process
  is asked to stop at a point of its choosing, and is killed only when it has not stopped within a grace period.
  Adopted as AD-037-R12 already shaped it: the tool gate is the ask, delivered at a tool boundary; the holder's reap
  is the backstop. A terminal task's reap is not deferred by a growing log, because no work the session does after
  the ask is wanted (HB-140's log grew for the whole ninety minutes).
- **Claude Code hooks, the common JSON output.** `"continue": false` ends the session after the hook runs, with
  `stopReason` shown; `permissionDecision: "deny"` refuses only the one call. The gate writes both: the call is refused
  and the session ends. Cited from the hooks reference by name; not fetched (the task's Network header allows nothing
  beyond git).
- **Internal:** AD-037-R12 (the hard stop at the tool boundary), AD-038-R1 (the event log is the record; the graph is
  its projection), AD-028 (withdrawn and superseded are terminal and carry a reason).

## 3. Ruling

- **AD-037-R16. A task moved to a terminal state by another hand while its session runs stops that session at its next tool boundary.**
  The tool gate reads the task's newest state change from the primary's event store at every call; when it moved the
  task to `withdrawn`, `superseded`, `rejected` or `verified` and was written by any session but the running one, the
  call and every later call are refused with the state and the actor, `andon_halted` is recorded once with
  `stop_reason: task_terminal`, and the hook ends the session. A transition from `in_progress` to such a state writes
  a hard `session_stop` with reason `task_terminal` (the signal), the holder's inspection writes it for a transition
  that came another way, and its reap is not deferred by a growing log. The Stop gate runs no check for such a task,
  and its finish is `session_failed`.

## 4. Details

1. **The log, not the graph, and no cache.** The task proposed a graph read cached per minute. The gate already reads
   the event store at every call (the hard-stop lines); the state-change lines come from the same read, so the halt
   costs no connection, no credentials in the hook's environment and no minute of staleness. Every terminal transition
   (CLI, MCP, dispatcher) appends its line before it projects to the graph (`commit_writes`).
2. **Another hand.** A session's own events carry its `SELDON_SESSION_ID`. A session that withdraws its own task (its
   premise turned out false) is not halted by its own act and writes its RESULT. In a worktree its own transitions go
   to the worktree's store, which the gate does not read, so this matters for in-place sessions only.
3. **`verified` is in the set** as the task file names it: a task verified by another hand needs no more work from its
   session. `completed` is not: a session may complete its own task (against the worktree clause), which the finish
   records as `graph_completed_unmerged`.
4. **What the session's tree then holds** is AD-038-R25's: its events are discarded on record at the finish.
