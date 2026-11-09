# RESULT: SEL-034, a terminal task stops its session, and a kept worktree's events reach main's log or are discarded on record

**Task:** `cc_tasks/2026-11-09_SEL-034_a_terminal_task_stops_its_session_and_a_kept_worktrees_events_reach_mains_log_or_are_discarded_on_record.md`
(e6a20ced). **Answers:** hazbrief-mcp filing SEL-030. **Branch:** `worktree-expressive-wobbling-fairy` (the dispatcher
merges it). **Rulings:** AD-037-R16 (`docs/design/AD-037_ADDENDUM_04_a_terminal_task_stops_its_session.md`),
AD-038-R25 (`docs/design/AD-038_ADDENDUM_11_a_kept_worktrees_events_reach_mains_log_or_are_discarded_on_record.md`),
both registered as pending records for the merge to number.

Recall used: seldon:2026-10-17_FRICTION-002_vendor_isolation_replaces_hand_built_plumbing_RESULT, seldon:AD-034-R5

(FRICTION-002's RESULT is where the kept-tree record (`worktree_kept`) and the Stop gate this task extends come from,
and it fixed the rule that a session never merges or completes, so Part C runs the reconcile from the dispatcher's
command rather than from the session. AD-034-R5 (merge on green, never resolved by the dispatcher) set the limit on
Part B's merge-time dedupe: it drops only byte-identical copies of lines the dispatcher itself reconciled, and leaves
any differing line for the union check to refuse.)

## Outcome

All four Parts done. (A) A task moved to a terminal state by another hand while its session runs now has its
session refused at the next tool call and ended; withdraw/supersede also write a `task_terminal` hard stop that the
holder reaps if the gate has not ended the session. (B) At every kept finish, the lines the worktree's event store holds
and main's lacks are union-merged into main's store, or, for a withdrawn, superseded or rejected task, written to a
committed evidence file with their live-graph effects compensated. (C) Applied to HB-140's kept tree in hazbrief by the
discard path: it held **25** unlogged lines, not the two SEL-030 named. After the reconcile, main's log and the live
graph agree on state, links and the touched properties for all 22 artifacts involved. (D) The return answers SEL-030's
three questions.

Two things beyond the task text. (1) The halt reads the event log, not a cached graph read; see Part A. (2) The discard
cannot remove the nodes a session created (no event deletes a node), so their creation is carried into the log and the
Issues among them are closed `premise_false`. That is how the task's "closed premise_false" and "a rebuild and the live
graph agree" both hold.

## Part A: a terminal task stops its session (AD-037-R16)

- **The gate.** `seldon dispatch tool-gate` (the PreToolUse hook) now also reads the task's newest
  `artifact_state_changed` from the primary's event store, in the same read it already made for hard stops. When it
  moved the task to `withdrawn`, `superseded`, `rejected` or `verified` and was written by any session but the running
  one, the call is refused with the state, the actor and the event, `andon_halted` is recorded once with
  `stop_reason: task_terminal`, and the hook output carries `"continue": false`, which ends the session. Every later
  call is refused too.
- **The signal.** `artifacts.transition_task` (CLI `task withdraw|supersede` and the MCP tools both go through it)
  writes a hard `session_stop` with reason `task_terminal` when an `in_progress` task goes terminal and its launch has
  no finish. The holder's inspection writes the same stop for a transition that came another way, and the reap of a
  `task_terminal` stop is not deferred by a growing log (HB-140's log grew the whole time). The Stop gate runs no
  checks for a terminal task, and `finish_session` records it `session_failed` with `task_terminal` before the gate
  reading is consulted.
- **A departure from the task text, on the record.** The task asked for a graph read cached per minute. The gate reads
  the event log instead, which it already reads on every call: no Neo4j connection or credentials in the hook, and no
  minute of staleness. Every terminal transition appends its line before projecting (`commit_writes`), and the log is
  the record (AD-038-R1). Stated in AD-037 ADDENDUM 04 section 4.1.
- **Tests:** `tests/test_sel034_terminal_task_stops_session.py`, 9 tests: the fixture (a withdrawn task's session is
  refused at its next call and ended; a second call refused; one `andon_halted`); superseded, rejected and verified;
  a session's own withdrawal does not halt it; a non-terminal move does not; the halt answers the signal's stop; the
  signal is written once and never after a finish; the inspection writes the stop and reaps a live session; the Stop
  gate lets the session end; `transition_task` writes the signal against the test database.

## Part B: a kept worktree's events reach main's log or are discarded on record (AD-038-R25)

- `seldon/core/kept_events.py` holds the rule. At every kept finish (`_finish_unmerged` for `session_failed`,
  `merge_blocked`, `stop_gate_unpassed`, `classifier_breaker`, `model_substituted`; `launch_failed`;
  `database_unavailable`; the pass's `holder_gone` / `released_unfinished`) the dispatcher reads the tree's
  `seldon_events.jsonl` (on disk, plus any line only the branch holds) and takes the lines main's store lacks by
  `event_id`.
  - **Union (default).** They are appended to main's store byte for byte and `kept_events_reconciled` names their ids.
    A later merge of the same branch (regate, re-merge) drops the branch's byte-identical copies first and commits
    that on the branch (`kept_events_deduped`); otherwise the rebase keeps both copies and `read_events` refuses the
    store. The test proves the rebase really does keep both.
  - **Discard (task withdrawn, superseded or rejected).** The lines go to
    `docs/evidence/<task stem>/discarded_events.jsonl`, committed on main. Their effects in the live graph are undone
    by evented writes when the graph still shows them: a state change walked back to the log's state, a property set
    back to the log's value, a link removed. An effect another hand has changed since stays as that hand set it.
    Artifacts the session created cannot be removed by an event, so their creation is carried into main's store, their
    links to older artifacts are removed, and each created Issue is closed `wont_fix` with `resolution_notes` starting
    `premise_false:` and naming the task. `events_discarded` records the count, the ids, the carried ids, every
    compensation and anything unreconciled.
- Prior art (AD-038 ADDENDUM 11 section 2): compensating events in event sourcing (Fowler 2005; Sagas, Garcia-Molina
  and Salem 1987; the Compensating Transaction pattern) and git's union merge driver. Cited by name, not fetched: the
  task's Network header allows only git.
- `seldon dispatch reconcile-kept <task> [--dry-run]` applies the rule to a tree kept before this build, under the pass
  lease.
- **Tests:** `tests/test_sel034_kept_worktree_events.py`, 5 tests on a git project with a real kept worktree and the
  test graph: union (log and graph disagree before, agree after, idempotent); discard (evidence, compensation, the
  created Issue closed `premise_false`, log and graph agree, the evidence committed, idempotent); another hand's later
  change left alone (HB-140R's case); links removed on record; a reconciled branch merges with its copies dropped.

## Part C: hazbrief's case (discard path)

Run from hazbrief's primary with this branch's code, `python -m seldon dispatch reconcile-kept 249b85dc` (wrapper
`/tmp/sel034/hb_reconcile.py`, PYTHONPATH = this worktree). It ran after a `--dry-run` and after hazbrief's HB-141
merged (17:56Z). HB-141 held the serial pass lease from 16:06Z, so Part C waited instead of committing next to a
working session.

- **Found:** 25 lines in `worktree-sunny-shimmying-pebble`'s store that main lacked, all from the withdrawn session
  (`2c2c29ad`): 17 `content_hash` updates (06:17Z), 8b992307's `resolution_notes`/`disposition` update and its move to
  `resolved`, three links from 8b992307 (`remediated_by` HB-140, `verified_by` two test Scripts), and the creation of
  Issue 5b737052 and of Scripts 24ce0777 and cf83f094.
- **Choice: discard**, as the task expected. HB-140 is `withdrawn`, and HB-140R had already reopened 8b992307.
  `events_discarded` in hazbrief: 20 lines to
  `docs/evidence/2026-11-08_HB-140_..._one_wind_footprints/discarded_events.jsonl` (commit `a4e222f3`). The state
  change on 8b992307 was **not** compensated: the live graph shows `open`, as HB-140R set it, and that stays. The 17
  `content_hash` updates were not compensated either, because the live values have changed since. Four compensations
  were written: 8b992307's `resolution_notes` and `disposition` cleared back to the log's (absent) values; its
  `remediated_by` link to HB-140 removed; its two `verified_by` links to the never-merged test Scripts removed. Carried
  (5 lines): the three creations and the two `verified_by` link creations. **5b737052 is closed** (`open -> wont_fix`,
  `resolution_notes: premise_false: created by the dispatched session of task HB-140 ...`). The two Scripts stay
  `proposed` (Not done, below). Unreconciled: none. Record commit `3303f22e`, pushed with the evidence commit.
- **Check** (`/tmp/sel034/hb_verify.py`): the store reads (7,524 events, 7,524 unique ids), and the kept tree holds no
  line main lacks other than the 20 named as discarded. For the 22 artifacts touched, main's log as replay projects it
  and the live graph agree on state, outgoing links and the touched properties. The only differences are
  `updated_at`, which the graph writer stamps with its own clock on every write. `replay-check` does not fingerprint
  it (ids, states, edges only).

## Part D: the return

`seldon cc return --to hazbrief-mcp --answers seldon:SEL-030` files hazbrief's return from the section below (run
after a `--dry-run`; the filed task is named in the dispatcher's merge record and in hazbrief's log).

## For hazbrief-mcp

SEL-030's three questions, point by point.

1. **Is withdrawing a task meant to stop its running session, and why did HB-140's run on?** Yes. Before seldon
   AD-037-R16 nothing connected the two: the session's tool gate delivered only hard stops written by the dispatcher
   (spend and disk ceilings), a withdrawal wrote none, and the holder's inspection never read the task's state. Now the
   gate reads the task's latest state change at every tool call. A withdrawal, supersession, rejection or verification
   by another hand refuses that call and every later one, records `andon_halted` (`task_terminal`), and ends the
   session. The withdrawal itself also writes a `task_terminal` hard stop that the dispatcher reaps if the session has
   not ended. HB-140 would have stopped at its first tool call after 05:10:20Z. Nothing on hazbrief's side changes: the
   gate is the session's PreToolUse hook, and every hazbrief launch already has it.
2. **Where do events written to the live graph by a session whose branch never merges go?** Since seldon AD-038-R25,
   to main's log, at every kept finish. If the task is still live (blocked, to be redriven or regated), the lines are
   union-merged into main's `seldon_events.jsonl` (`kept_events_reconciled`), because the graph already holds their
   effect. If the task was withdrawn, superseded or rejected, they are discarded on record: the lines go to
   `docs/evidence/<task stem>/discarded_events.jsonl`, their effects in the live graph are undone by ordinary logged
   writes unless another hand has changed them since, and `events_discarded` names every line and compensation. The
   creation of anything the session made is kept in the log, because no event removes a node, and an Issue it created
   is closed `wont_fix`, `premise_false`. Either way, the log and the live graph agree afterwards.
3. **What should a consumer do with 5b737052?** Nothing; the producer's reconcile has handled it. HB-140's kept tree
   was reconciled by the discard path on hazbrief's main (`a4e222f3` evidence, `3303f22e` record, pushed). It held 25
   unlogged lines, not two. 5b737052's creation is now in the log and it is closed `wont_fix` with
   `resolution_notes: premise_false: ...` naming HB-140. If terrain on the one-wind briefs still needs the two USGS
   elevation hosts, file it again from a task that wants it. 8b992307 is left `open`, as HB-140R set it. HB-140's
   resolution notes, its `remediated_by` link to HB-140 and its two `verified_by` links to tests that never reached main
   were removed from the live graph by logged writes. HB-140's two test Scripts (24ce0777, cf83f094) stay `proposed` in
   the graph with no links. A `seldon events replay-check` in hazbrief should no longer report any of these artifacts.

Recipe, if hazbrief ever finds another tree kept before this build: in Claude Code, in hazbrief-mcp's primary checkout,
with no session in flight, run `seldon dispatch reconcile-kept <task id prefix> --dry-run`, then the same line without
`--dry-run`.

## Verification

- Full suite on the Part A+B commit (`7ca48fe`), `-n 6`: **3320 passed, 3 failed, 7 skipped** in 26 min. The three
  failures are known and not this branch's: `test_pa002_release_resolve::test_rebuilding_the_served_release...`
  (library index drift, Issue dbe38fac), and `test_dispatch_parallel::test_two_disjoint_non_exclusive_tasks...` and
  `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait...`, both timing tests that passed
  alone (2 passed, 89 s).
- After the link fix (`e34faa1`): the two SEL-034 files (14 passed) and the nine dispatcher files that drive kept
  finishes (101 passed; the same two timing tests, plus
  `test_dispatch_parallel::test_a_killed_supervisor_is_marked...`, which passed alone in 23 s).
- Part boundaries: `part_complete` A (244,912 tokens), B (256,091 tokens), C and D recorded in the store.

## Not done, and why

- `seldon verify` was not run in this worktree: it crashes on un-numbered pending register records (known); the merge
  numbers them.
- Created artifacts other than Issues (HB-140's two Scripts) are carried and left `proposed`. Closing a Script has no
  state that means "the test never reached main"; AD-038 ADDENDUM 11 section 4.4 names it as a design question.
