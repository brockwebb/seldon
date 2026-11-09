# AD-038 ADDENDUM 11: a kept worktree's events reach main's log, or are discarded on record

**Date:** 2026-11-09. **Status:** Accepted. Implemented by SEL-034 Parts B and C
(`cc_tasks/2026-11-09_SEL-034_a_terminal_task_stops_its_session_and_a_kept_worktrees_events_reach_mains_log_or_are_discarded_on_record.md`),
answering hazbrief-mcp's filing SEL-030. **Extends:** AD-038-R1 (the machine reconciles its own state), ATTR-001
(append-only logs merge by union), AD-034-R5/R6 (an unmerged worktree is kept). One new ruling.
**Code:** `seldon/core/kept_events.py` (the rule, the split, the compensation plan, the merge-time dedupe);
`seldon/commands/dispatch_worktree.py` (`reconcile_kept_events` at every kept finish and at `holder_gone`, the
dedupe in `_merge`); `seldon/commands/dispatch.py` (`seldon dispatch reconcile-kept`).
**Tests:** `tests/test_sel034_kept_worktree_events.py`.

## 1. Evidence

1. **HB-140's kept tree.** The withdrawn session of hazbrief `249b85dc` wrote 25 event lines into its worktree's
   `seldon_events.jsonl` and, through the same writers, into the live graph; its branch was kept `session_failed`, so
   none reached main's store. SEL-030 named two of them (Issue `8b992307` to `resolved`, Issue `5b737052` created);
   the reconcile's own read found 25: 17 `content_hash` updates, `8b992307`'s resolution notes, its state change and
   three links, and the creation of `5b737052` and of two Scripts.
2. **What that costs.** The live graph and a rebuild from main's log disagree (Recoverability, `seldon events
   replay-check`), and the next task met the unlogged state as fact: HB-140R found `8b992307` resolved and re-opened it
   by hand.

## 2. Prior art

- **Compensating events in event sourcing.** An event log is never edited; an effect that should not stand is undone
  by a new event that reverses it (Fowler, "Event Sourcing" and "Retroactive Event", 2005; Garcia-Molina and Salem,
  "Sagas", SIGMOD 1987, compensation as the undo of a committed step; the Compensating Transaction pattern, Azure
  Architecture Center). Adopted for the discard: the discarded lines are kept as evidence, not deleted, and every
  effect they left in the live graph is reversed by an ordinary evented write, so the log and the graph agree without
  either being edited.
- **git's union merge driver (`gitattributes`, `merge=union`).** Both sides' lines are kept. Adopted for the default:
  a kept tree's lines are what the union merge would have added, so they are appended as it would append them, byte
  for byte; and because the driver cannot see a line both sides hold, a later merge of the same branch drops its
  byte-identical copies first (decision 4's check already refuses a duplicate id).
- **Internal:** AD-038-R1 (the log is the record and the graph its projection); ATTR-001 (the store merges by union);
  AD-034-R5/R6 (kept, never resolved); AD-034 ADDENDUM 02 (`sweep_stale_kept`, which removes only trees whose branch
  holds nothing beyond main and whose tracked files are clean, so a tree with unreconciled lines is never swept).

The external sources are cited by their published names and were not fetched: the task's Network header allows
nothing beyond git.

## 3. Ruling

- **AD-038-R25. At every kept finish the lines the worktree's event store holds and main's store lacks reach main's store, or, when the task is withdrawn, superseded or rejected, are discarded on record with their live-graph effects compensated.**
  The default appends them to main's store byte for byte and records `kept_events_reconciled` with their ids. For a
  withdrawn, superseded or rejected task they are written to `docs/evidence/<task stem>/discarded_events.jsonl`
  (committed) and `events_discarded` records the count, the ids and every compensation: a state change, a property
  update or a link the session made is reversed by an evented write when the live graph still shows it, and left as
  another hand set it otherwise. Artifacts the session created cannot be removed by an event, so their creation is
  carried into main's store, the session's links between them and older artifacts are removed, and each created Issue
  is closed `wont_fix` with `resolution_notes` beginning `premise_false:` and naming the task. A reconciled branch that
  later merges has its copies dropped first. `seldon dispatch reconcile-kept <task>` applies the same rule to a tree
  kept before it.

## 4. Details

1. **Which outcomes.** Every finish that keeps a tree: `session_failed`, `merge_blocked`, `stop_gate_unpassed`,
   `classifier_breaker`, `model_substituted`, `launch_failed`, `database_unavailable` (recorded as
   `kept_events_unreconciled` when the graph cannot be read, and retried by `reconcile-kept`), and the pass's
   `holder_gone` / `released_unfinished`.
2. **Why the default is union.** The live graph already holds the lines' effect; the log must agree with it. A kept
   task is usually blocked and will be redriven or regated, and its writes were the system's own.
3. **Why `completed` and `verified` are not discarded.** Their work is done; a branch kept after `cc complete` is
   `graph_completed_unmerged`, and its lines belong in the log.
4. **Created artifacts other than Issues** (HB-140's two Scripts) are carried and left in their state; they are named
   on `events_discarded.created`. Closing a Script has no state that means "the test never reached main", and naming
   one is a design question, not this ruling's.
5. **What cannot be compensated** (a link the session removed, whose re-creation needs its endpoint types) is listed on
   `events_discarded.unreconciled` and shown on stderr; nothing is skipped silently.
6. **SEL-030's question on `5b737052`.** A consumer leaves such an Issue to the producer's reconcile; after it, the
   Issue's creation and its closing are both in the log.
