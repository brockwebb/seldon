# DESK-002 Part B: does registration leave its own event-store lines uncommitted?

**Issue:** `70bf1a21` (registration_leaves_governed_sync_lines_uncommitted). **Measured:** 2026-10-16.
**Instrument:** `tests/test_desk002_registration_event_lines.py`. It uses a temp git repository with a tracked
`seldon_events.jsonl` and one governed ruling (`AD-900-R1`) synced into the test Neo4j database. The store is
committed clean. Then `seldon_cc_register` (the MCP path, actor `desktop`) registers a task whose `**Governing:**`
names the ruling. The test runs both orders the issue asked about.

## Result on the code before the fix (branch HEAD 01835ba, Part A only)

| order | uncommitted store lines after registration (event_type, actor) |
|---|---|
| task file committed first (as `seldon_commit_governed` leaves it; squiddy SQ-016R) | `artifact_created` desktop, `link_created` governed_sync |
| task file untracked (registration commits it) | `artifact_created` desktop, `link_created` governed_sync |

Both parametrizations failed with `AssertionError: [('artifact_created', 'desktop'), ('link_created', 'governed_sync')]`.

**The defect exists, and the order does not cause it.** Registration committed none of the lines it appended,
in either order. The order decides only whether the dispatcher's fallback later rescues the lines:
- `_commit_registration_records` (`seldon/commands/dispatch.py`) commits the store only when it finds an
  `artifact_created` line whose `source_commit` is set. That happens only when registration committed the
  task file itself (the untracked order).
- With a task file committed first, `source_commit` is null and that sweep skips. `_record_own_lines` then
  refuses the store because `governed_sync` is not in `COMMITTABLE_ACTORS`, so c7 refuses every task.

squiddy's own log matches this. Registration on 2026-10-15 14:42 (SQ-016, untracked) wrote nine `governed_sync`
`link_created` lines, and the dispatcher's sweep committed them in `3c60482` ("register: record of ...").
Registration on 2026-10-16 09:42 (SQ-016R, already committed) wrote nine more. Nothing committed those until
the operator's hand commit `bbd0dfa` ("record: seldon_events.jsonl for SQ-016R registration ..., seldon issue
70bf1a21").

## Decision

Registration commits its own lines (`_commit_registration_lines` in `seldon/commands/cc.py`). It runs after its
last write: a path-scoped commit of the store, through the hooks, titled
`register: record of <task> (<id>) — N line(s) (...) written by its registration (DESK-002)`.

- **A second commit, not the task's commit.** The task's `artifact_created` line carries `source_commit`,
  which is the sha of the commit that holds the task file, so that line cannot go inside that commit. This
  departs from the task's wording ("in the same commit as the task"), because that wording cannot be met. The
  lines go in the next commit, the same place the dispatcher's sweep has always put them. Only the committer
  changes.
- **It commits only its own lines.** The store must be clean when registration starts, and every appended
  line must come from the registering actor or `governed_sync`. Otherwise registration commits nothing and
  says why: `store_dirty_before_registration` or `foreign_lines`. The dispatcher's existing paths remain the
  fallback.
- **The test pins it.** Both orders now pass: the store is clean, the tree is clean, and the newest commit is
  the `register: record` commit.
