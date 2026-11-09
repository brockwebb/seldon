# SEL-034: a task that goes terminal stops its running session at the next tool boundary, and the events a kept worktree's session wrote reach main's log or are discarded on record

**Status:** proposed
**Author:** Desktop session (seldon), 2026-11-09, answering hazbrief filing SEL-030 (`cc_tasks/2026-11-09_SEL-030_...md`).
**Repo:** seldon (primary); hazbrief-mcp (Part C reconciles the one measured case and Part D files the return). L4: commit, merge, push in both.
**After:** none
**Governing:** AD-037-R12 (a hard stop refuses the session's next tool call and records `andon_halted`); AD-038-R1 (the machine reconciles its own state); ATTR-001 (append-only logs merge by union); AD-034 (worktree outcomes, `session_failed`). Number new rulings under AD-037 and AD-038.
**Model:** primary
**Spend:** est. 0.5M tokens. Basis: one state read in the PreToolUse hook, one reconcile step for kept worktrees, one fixture per Part, the hazbrief reconcile. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits the stations hook and the dispatcher's finish and reap)
**Parts:** A 0.35, B 0.35, C 0.15, D 0.15.
**Premises:**
- premise: the hard-stop refusal exists at the tool boundary | check: grep -q "andon_halted" seldon/core/stations.py
- premise: session_failed is a worktree outcome | check: grep -q '"session_failed"' seldon/commands/dispatch_worktree.py
- premise: the logs merge by union | check: grep -q "union" seldon/commands/dispatch_worktree.py

Checks are single commands with no shell.

Read SEL-030 in full before Part A.

## The condition

hazbrief HB-140 (249b85dc) was launched at about 05:05Z on 2026-11-09 and withdrawn at 05:10:20Z. Its session ran on for ninety minutes to completion on `worktree-sunny-shimmying-pebble` (4d97f03a), 14 briefs and live network calls, full gate. The dispatcher kept the worktree as `session_failed` and merged nothing. In those minutes the session wrote two graph events (Issue 8b992307 to resolved, Issue 5b737052 created) through the live graph; neither reached main's `seldon_events.jsonl`, so the live graph and a rebuild from the log now disagree, and HB-140R had to re-open 8b992307 by hand. Two defects: a terminal state does not stop a running session, and a session's events in a worktree that is never merged are lost to the log while present in the graph.

## What to build

**A. Terminal stops the session.** The PreToolUse hook that refuses on a hard stop also reads the task's state from the graph at each boundary (cheap, cached per minute); when the task is `withdrawn`, `superseded`, `rejected` or `verified` by another hand, the next tool call is refused with the state and the actor, `andon_halted` is recorded with reason `task_terminal`, and the session ends. `seldon task withdraw` and `task supersede` on an `in_progress` task also signal the dispatcher, which reaps the session at the next pass if the hook has not already ended it. Fixture: a withdrawn fixture task's session is refused at its next call.

**B. A kept worktree's events are reconciled.** At `session_failed`, `merge_blocked` and every other kept outcome, the dispatcher takes the worktree's `seldon_events.jsonl` lines that main's log lacks and either union-merges them into main's log (the default, since the live graph already holds their effect and the log must agree) or, when the task is terminal, writes them to `docs/evidence/<task>/discarded_events.jsonl` and records `events_discarded` with the count and ids so a rebuild and the live graph agree. Issues the session created on a terminal task are closed `premise_false` with the task named. Fixture: both branches.

**C. hazbrief's case.** Apply B's reconcile to `worktree-sunny-shimmying-pebble`: 5b737052 and the 8b992307 transition are recorded one way or the other, the choice named in the RESULT (HB-140R already re-opened 8b992307, so the discard path with the Issue left as HB-140R set it is the expected answer). Commit in hazbrief through the hooks.

**D. The return.** `seldon cc return --to hazbrief-mcp` answering SEL-030's questions point by point.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.6M.

## Deliverables

A to D with tests; rulings under AD-037 and AD-038; `cc_tasks/2026-11-09_SEL-034_a_terminal_task_stops_its_session_and_a_kept_worktrees_events_reach_mains_log_or_are_discarded_on_record_RESULT.md`.
