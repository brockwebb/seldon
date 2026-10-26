# The Desktop OODA between chained tasks: what a project runs so c18 can release its chain

**Governing:** AD-038-R10 (`docs/design/AD-038_ADDENDUM_03_the_ooda_between_chained_tasks_and_adoption.md`).
**Built by:** SEL-010R2 (`cc_tasks/2026-10-26_SEL-010R2_dispatch_waits_for_the_desktop_ooda_between_chained_tasks.md`).
**Code:** `seldon/core/dispatch.py` (`ooda_waits`), `seldon/commands/dispatch.py` (`dispatch ooda pending|record`),
`seldon/mcp_server.py` (`seldon_ooda_pending`, `seldon_ooda_record`).

The dispatcher holds task N+1 after its `precedes` predecessor N completes (criterion c18), until an OODA record for N
exists or the project's grace runs out. The dispatcher counts the record. Reading the RESULT is the Desktop's job.
This document covers that half of the loop: who reads, when, what they write, and in what order.

## 1. Turn it on

In the project's `seldon.yaml`, under `dispatch:`:

```yaml
  # AD-038-R10 (c18): seconds a chained task waits for the Desktop OODA on its predecessor; 0 never.
  ooda_grace_s: 3600
```

**Schedule the wake-up (section 2) before you raise the grace.** With a grace and no reader, every chain waits the
full grace and gains nothing. That is why seldon's own block stays at 0. Choose a grace of at least twice the
wake-up interval: a record then lands inside the grace even when a RESULT arrives just after a wake-up. That factor
of two is a starting value, not a measurement. Revise it from the `released_by` counts on `dispatch_launched`. If
`grace` keeps releasing tasks, the wake-up is too slow or not running.

A project without a `dispatch:` block adopts the dispatcher first: `seldon dispatch adopt --project <dir>`
(AD-038-R11). It writes `ooda_grace_s: 0`.

## 2. Who reads, and when

Pick one. Each is a Desktop process; the dispatcher does not care which one wrote the record.

**A. A scheduled Claude Code session (unattended).** In the project's primary checkout, in a Claude Code window,
paste this (30 minutes is the interval that pairs with the grace of 3600 above):

```
/loop 30m Run `seldon dispatch ooda pending`. If it prints "ooda: nothing pending", stop. Otherwise, for each predecessor it lists, follow docs/conventions/desktop_ooda.md section 3 in the seldon repository: read the RESULT, write any addendum for the successor first, then the _OODA.md record last.
```

**B. A Claude Desktop thread (seldon-mcp).** When the thread opens: call `seldon_ooda_pending(project_dir=<dir>)`, then
follow section 3, writing the files with the Filesystem tools. `seldon_ooda_record(task=<N>, note=<one line>)` is the
event form for an OODA that amends nothing.

**C. The operator by hand.** `seldon dispatch ooda pending` in a shell, then section 3. A stuck alarm on
`ooda_pending` (`dispatch_stuck`, after `stuck_after_passes` passes) means a chain is waiting on this step.

## 3. The OODA, per predecessor N that `ooda pending` lists

Order matters. A record releases N+1, so everything N+1 must see has to be on main first.

1. **Observe.** Read N's RESULT (`read:` in the listing) and any Issues it filed.
2. **Orient.** For each premise and Part of N+1's task file (`amend:` in the listing), ask whether N's RESULT made it
   false or out of date.
3. **Decide and act, in this order:**
   - **N+1 must not run as written, and an amendment fixes it:** write
     `cc_tasks/<N+1 stem>_ADDENDUM_<NN>_<slug>.md` first. An addendum amends what the task does. It cannot supply a
     missing candidacy header (AD-038-R11). For that, file a new task.
   - **N+1 must not run at all:** block it (`seldon task update <N+1> --state blocked --reason "<why>"`, MCP
     `seldon_task_update(..., state="blocked", reason=...)`) or supersede it **before** writing the record. Otherwise
     the record, or the grace, would release it.
   - **N+1 is right as written:** go to the record.
4. **Record, last.** Write `cc_tasks/<N stem>_OODA.md` (the `release:` path in the listing) in the shape below, or
   run `seldon dispatch ooda record <N> --note "<one line>"` when there is nothing to say beyond "read, no change".

You do not have to commit. The dispatcher's next pass commits an untracked `_OODA.md` or addendum beside a
registered task before it evaluates anything (AD-038-R1, R10), and c18 counts the file once it is committed. A
Desktop thread may still commit at once with `seldon_commit_governed` (root `cc_tasks/`). Committing the addendum and
the record together keeps the order above.

### The record's shape

```markdown
# OODA on <N id prefix> <N stem>

**Task:** <N full id>
**RESULT:** cc_tasks/<N stem>_RESULT.md
**Read by:** <desktop thread | claude code /loop | operator>, <date>
**Successors:** <N+1 id prefix> <N+1 file>[, ...]
**Premises found wrong:** none | <the premise, and what the RESULT showed>
**Amends:** none | cc_tasks/<N+1 stem>_ADDENDUM_<NN>_<slug>.md
**Decision:** proceed | amended | blocked <N+1> | superseded <N+1>

<Anything else the next session should know, in a few lines.>
```

## 4. What the dispatcher records

`dispatch_launched`'s criteria carry c18 for a chained task: each predecessor's `released_by` (`ooda_event`,
`ooda_file` or `grace`), the completion time and its source, and the seconds elapsed. If the grace released a task,
nobody read the RESULT before it launched. That is the measure to drive down.
