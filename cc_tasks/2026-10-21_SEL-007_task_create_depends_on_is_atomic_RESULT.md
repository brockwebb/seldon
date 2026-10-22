# RESULT — SEL-007: `seldon task create --depends-on` is atomic, or it creates nothing

**Date:** 2026-10-21
**Session:** interactive Claude Code session (operator-launched, not dispatched), branch `worktree-SEL-007`
**Addenda:** none (`cc_tasks/*SEL-007*ADDENDUM*.md` globbed: no match)
**Premise:** `grep -q "7b76e2c3" /Users/brock/GitHub/hazbrief-mcp/seldon_events.jsonl` → exit 0 (orphan present)

## Governing decisions, and the prior art this implements

- **AD-001** (`docs/seldon_architectural_decisions_updated.md`): the event-sourced, append-only JSONL log is the
  source of truth; the graph is its projection. This is where the ledger's write discipline lives, so the
  all-or-nothing boundary is the ledger append, not the Neo4j writes. The task header names AD-030; AD-030
  governs governed documents (R1: parsing is the single write path) and does not define the event-write
  discipline. AD-001 does.
- **AD-029 §2** (`docs/design/AD-029_task_precedence.md`): `seldon task chain` is already all-or-nothing:
  "every pair is validated ... before the first write". SEL-007 applies that rule to every multi-line command
  and adds the missing half: one ledger write for all lines.
- The prior art is the **atomic batch append of an event store**: validate the whole command, then commit all
  of its events as one unit (EventStoreDB `AppendToStream` with several events, the transactional outbox, and a
  write-ahead log record group). The local equivalent is one `write` plus `fsync` of every line. AD-001's
  `append_event` already wrote one line this way; `append_events` extends the same guarantee to N lines.

## What was wrong

`seldon task create` called `create_artifact`, which appended `artifact_created`, and only then called
`create_link`, which validated the edge and refused it. Two more faults in the same code path:

- An unknown `--blocks` or `--depends-on` id was a warning ("not found — skipping"), and the task was created
  without the link the operator had asked for.
- The MCP `seldon_task_create` had the same order for `blocks`, and returned a warning when the target could
  not be resolved.

## Part A — atomic create

- `seldon/core/events.py`: new `append_events(project, events)`. It serialises every line first, then makes one
  `write` and one `fsync`. `append_event` is now `append_events([event])`.
- `seldon/core/artifacts.py`:
  - `PlannedWrite` (an event plus its graph projection) and `commit_writes`, which makes one ledger append and
    then projects the writes in order.
  - `plan_artifact`, `plan_link`, `plan_update_artifact` and `plan_state_change` hold the validation and event
    building that used to sit inside `create_artifact`, `create_link`, `update_artifact` and
    `transition_state`. Each of those four is now plan plus commit, with unchanged behaviour.
  - `ledger_only(event)` covers observation events that the graph does not project.
  - New `create_task(description, links)`. It resolves every target (unknown or ambiguous → `ValueError`),
    plans every edge, then makes one commit. The CLI `task create` and the MCP `seldon_task_create` both use it.
- A graph failure after the append is a projection fault, and `seldon rebuild` repairs it from the log (AD-001).
  It is not a partial command.

## Part B — the error text

- `seldon/domain/loader.py` `validate_relationship`: a refusal still names the legal `to_types` / `from_types`.
  It now also names every relationship type under which the refused pair *is* legal. This reaches every write
  path, `seldon link create` included. Example: "A 'ResearchTask' -> 'ResearchTask' edge is legal as:
  'precedes'."
- `create_task` prefixes the refused link (`'depends_on' link to '<id>': ...`). When the target is a
  ResearchTask, it adds: "To order this task after another task, create it without that option, then run
  `seldon task precede <predecessor> <new task>` (MCP: seldon_task_precede)."
- The CLI and MCP refusals end with "Nothing was written: no task was created." That statement is true
  because every refusal is raised before the append.
- `--depends-on` help text now names the legal target types and points at `seldon task precede`.

## Part C — the other multi-event commands

Found by a read-only survey of every CLI command and MCP tool that can append more than one line, following the
helper call chains. Every test below is in `tests/test_sel007_atomic_multi_event.py`.

### Converted to plan + one append (each has a test)

| Command | Lines | Before SEL-007 | Test |
|---|---|---|---|
| `task create` (CLI) | created + N links | validation after the first write; unknown id skipped | `test_illegal_depends_on_target_writes_no_event_and_no_artifact`, `test_a_legal_edge_before_an_illegal_one_is_not_written_either`, `test_an_unknown_target_is_refused_not_skipped`, `test_legal_edges_land_with_the_artifact_in_one_append`, `test_a_failure_while_preparing_the_batch_writes_nothing` |
| MCP `seldon_task_create` | created + blocks link | same; unresolvable target became a warning | `test_mcp_create_with_an_unresolvable_blocks_target_writes_nothing`, `test_mcp_create_with_an_illegal_blocks_target_writes_nothing` |
| `task update/withdraw/supersede` and MCP twins (`transition_task`) | property + state + `superseded_by` | validated first, then 3 separate appends | `test_task_supersede_writes_reason_state_and_edge_in_one_append`, `test_task_claim_writes_the_marker_and_the_state_in_one_append` |
| `task close` and MCP `seldon_task_close` (`walk_to_completed`) | up to 4 | one append per step | `test_task_close_walks_in_one_append` |
| `cc complete` and MCP `seldon_cc_complete`, pre-registered path | `completed_at` + walk + `recall_used` | `completed_at` was written, then the walk raised for a superseded, withdrawn, rejected or verified task | `test_cc_complete_on_a_superseded_task_writes_nothing`, `test_a_walk_refused_at_its_start_writes_what_was_planned_before_it_neither` |
| `cc complete` and MCP twin, unregistered path | created + walk | separate appends | covered by the shared walk (`before=[creation]`) |
| `issue update` (CLI) | property + state | property written, then the transition refused | `test_issue_update_refused_transition_leaves_no_property_update` |
| MCP `seldon_issue_update` | state + property | state written, then the enum refused (uncaught) | `test_mcp_issue_update_refused_enum_leaves_no_state_change` |
| `issue create` | created + AFFECTS links | validated first, separate appends | `test_issue_create_writes_the_issue_and_its_affects_links_in_one_append` |
| `task precede` / `task chain` and MCP twins (`precedence.add_chain`) | N `precedes` | validated first, separate appends | `test_task_chain_writes_every_edge_in_one_append` |
| `dispatch redrive` and MCP twin (`core/redrive.py`) | claim clear + `dispatch_redrive` + state | formal transition check after two appends | `test_redrive_writes_its_three_lines_in_one_append` |
| `prune run`, Issue resolve | note + state | separate appends; an error row could strand half | `test_prune_resolves_an_issue_with_its_note_in_one_append` |

The ten refusal tests (Parts A and B, cc complete, both issue updates) were run against an unmodified checkout
of `main` (05eed4d), and all ten failed for the defect's own reason: an orphan `artifact_created`, a stranded
`artifact_updated`, an unguarded walk, or an uncaught enum. They pass on the branch.

### Not converted: real partial-write defects, filed as Issues

These are bulk reconciliation paths. Their unit of atomicity is one document or one record, not the command,
and each one needs a per-unit plan/commit refactor of its own sync loop. Each of the first four leaves a state
that a re-run does **not** repair, so they are defects, not exemptions:

| Issue | Command | Fault |
|---|---|---|
| `9b5aed05` | `governed sync` | `InvalidStateTransition` after writes; the retire step catches only `ValueError` |
| `87fb68d2` | `paper sync --auto-stale` | hash updated, then `review → stale` refused; the section never goes stale |
| `5e599e25` | `decision project` | `artifact_updated`, then the state change is refused; every re-run appends another line |
| `5fc33ac7` | MCP `seldon_audit_ingest` | a finding refused after the AuditRun is written; the run_id guard blocks a re-ingest |
| `764816bf` | `cc register`, `result register`, `paper register` | validated before the first write but still several appends; `cc register` needs `add_chain` to accept a not-yet-projected task |

### Exempt, with the reason

- **Dispatcher orchestration** (`dispatch once`, `supervise`, `regate`, station commands `part-complete`,
  `first-article`, `stop-gate`, `inspect`). Each line records a separate real-world occurrence (a launch, a stop,
  a merge) at the time it happens. Batching them would misdate them, and there is no command-level unit to make
  atomic. The redrive the dispatcher calls is converted (above).
- **Per-unit migrations and backfills** (`events migrate-legacy-ids`, `result migrate-names`,
  `result backfill-provenance`, `cc constrain`, `ontology ingest --deprecate-missing`, `verify --fix`
  in-process fixes, `init` bootstrap tasks). Each line is one complete, independently valid unit. Each is
  validated or pre-filtered before it is written, and a re-run skips the units already done, so a crash between
  lines leaves a smaller, consistent result rather than a contradictory one.
- **`cadence render --register`**: `cadence_rendered` records a render that did happen, and the registration
  that follows is a separate write path with its own refusals.

## Gate

- Targeted: `tests/test_sel007_atomic_multi_event.py` 22/22.
- Full suite on the branch (`python -m dotenv -f .env run -- python -m pytest tests/`, PYTHONPATH=worktree):
  **2766 passed, 7 skipped, 0 failed** (37 min).
- The first full run stopped at one failure: `tests/test_friction001_mcp_head.py` patched `mcp_server.py` by a
  12-space-indented source literal, and SEL-007 moved `seldon_task_create`'s `return` to function level. The
  test's anchor is now indentation-free (commit 996408a). The behaviour it checks is unchanged.

## Files

- `seldon/core/events.py`, `seldon/core/artifacts.py`, `seldon/domain/loader.py`, `seldon/core/precedence.py`,
  `seldon/core/redrive.py`, `seldon/core/prune.py`
- `seldon/commands/task.py`, `seldon/commands/issue.py`, `seldon/commands/cc.py`, `seldon/mcp_server.py`
- `tests/test_sel007_atomic_multi_event.py`, `tests/test_friction001_mcp_head.py` (anchor only)

## For the operator

- The hazbrief orphan `7b76e2c3` was already superseded by hand (HB-01e §10a). Nothing more is needed there.
- The five Issues above are the remaining Part C work. The first four are live defects in sync paths.
