# The OODA between chained tasks: what the machine reads, and the blocks a Desktop answers

**Governing:** AD-038-R10 (`docs/design/AD-038_ADDENDUM_03_the_ooda_between_chained_tasks_and_adoption.md`), as
amended by AD-038-R16 and R17 (`docs/design/AD-038_ADDENDUM_07_the_ooda_as_a_knowledge_source.md`).
**Built by:** SEL-010R2 (the gate and the Desktop record) and SEL-014R (the knowledge source).
**Code:** `seldon/core/ooda.py`, `seldon/commands/dispatch_ooda.py` (the knowledge source), `seldon/core/dispatch.py`
(`ooda_waits`, c18), `seldon/commands/dispatch.py` (`dispatch ooda pending|record`), `seldon/mcp_server.py`
(`seldon_ooda_pending`, `seldon_ooda_record`).

Since SEL-014R the OODA between task N and task N+1 is the machine's. With `dispatch.ooda.enabled`, each dispatcher
pass runs a headless session on every completed task with an open successor and no OODA record (at most
`dispatch.ooda.max_per_pass` per pass). The session reads N's RESULT and N+1's file, and the dispatcher records one
of `ooda_ok`, `ooda_amended` (the addendum it wrote is committed first), `ooda_blocked` or `ooda_expired`. c18 holds
N+1 only while that OODA is due or when it is `ooda_blocked` (R17). Nothing waits on a person except a block.

A Desktop reads only blocks: an `ooda_blocked` record names a question no ruling answers and the design note that
would answer it. This document covers that half.

## 1. Turn it on

In the project's `seldon.yaml`, under `dispatch:` (seldon's own block carries the reasons beside each value):

```yaml
  ooda_grace_s: 1800          # AD-038-R17: the OODA session's timeout, not a gate
  ooda:
    enabled: true
    max_per_pass: 1
    token_cap: 300000         # per OODA run
    model_role: primary
```

`ooda_grace_s` no longer releases a chain on a timer. With `enabled` false (the default) nothing waits at all. A
project without a `dispatch:` block adopts the dispatcher first: `seldon dispatch adopt --project <dir>` (AD-038-R11).

## 2. Who answers a block, and when

`seldon dispatch ooda pending` (MCP `seldon_ooda_pending`) prints every block: the question, the note that would
answer it, the RESULT and the successor it holds. "ooda: nothing pending" means nothing is blocked. A stuck alarm on
`ooda_blocked` (`dispatch_stuck`, after `stuck_after_passes` passes) means a chain is waiting on a person.

**A. A Claude Desktop thread (seldon-mcp).** When the thread opens: `seldon_ooda_pending(project_dir=<dir>)`, then
section 3 for each block, then `seldon_ooda_record(task=<N>, note=<one line>)`.

**B. A scheduled Claude Code session.** In the project's primary checkout, in a Claude Code window:

```
/loop 60m Run `seldon dispatch ooda pending`. If it prints "ooda: nothing pending", stop. Otherwise, for each block, follow docs/conventions/desktop_ooda.md section 3 in the seldon repository: answer the question in the note it names, amend, block or supersede the successor, then run `seldon dispatch ooda record <N>` last.
```

**C. The operator by hand.** The same, in a shell.

## 3. Answering a block on predecessor N

Order matters. A record releases N+1, so everything N+1 must see has to be on main first.

0. **The question.** The block names it (`question:`) and the note that would answer it (`answer in:`). If it needs a
   ruling, the ruling is written there first (a design note or addendum, with its register record).
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

Every OODA run is one record in the ledger: `ooda_ok`, `ooda_amended` (with the addendum and its commit),
`ooda_blocked` (with the question and the answering note) or `ooda_expired` (with why: a timeout, the token cap, a
failed session, or a verdict the dispatcher could not check). Each carries the session's tokens and log.
`dispatch_launched`'s c18 names, per predecessor, the record that released the successor (`released_by`). A
`released_by: ooda_expired` means the machine tried and could not read the RESULT; that is the measure to drive down.
