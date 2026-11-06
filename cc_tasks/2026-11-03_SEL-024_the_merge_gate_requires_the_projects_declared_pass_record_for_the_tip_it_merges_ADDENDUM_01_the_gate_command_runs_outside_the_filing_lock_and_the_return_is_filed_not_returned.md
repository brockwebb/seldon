# ADDENDUM 01 to 2026-11-03_SEL-024_the_merge_gate_requires_the_projects_declared_pass_record_for_the_tip_it_merges: the gate command runs outside the filing lock, and the return to squiddy is filed, not returned

**Author:** OODA knowledge source on 841bd7c7 (AD-038-R16)
**Date:** 2026-11-06
**Predecessor:** SEL-023 (841bd7c7), RESULT `cc_tasks/2026-11-03_SEL-023_a_consumer_filing_is_a_kind_the_registrar_accepts_and_a_desktop_commit_reaches_origin_RESULT.md`
**Rulings read:** AD-038-R20 and R21 (`docs/design/AD-038_ADDENDUM_08_hand_dispatch_one_call_filing_and_a_push_on_every_pass.md`); AD-036-R17 and R18 (`docs/design/AD-036_ADDENDUM_10_a_filing_is_a_kind_and_a_consumer_reports.md`).

All three premises still hold at HEAD (the dispatcher's checks passed). SEL-023 changed two things this task's Parts and
deliverables depend on. Neither changes the goal.

## 1. Part A: the declared gate command does not run while the pass holds the filing lock

SEL-023 added the project's filing lock (AD-038-R20): the pass takes `filings.lock_file` before its sweep, reconcile,
cadence and candidacy, and releases it (`_release_filing`) only after candidacy, before any launch. A filer
(`seldon_cc_file`, `seldon cc file`, `seldon cc return`) waits `filings.lock_wait_s` (120 s in seldon.yaml) and is
then refused. The ruling's stated departure is that "the lock is not held over the pass's launch, so a filer never
waits on a session".

Two of `_merge`'s callers run inside that window, in `_breaker_and_stale` (`seldon/commands/dispatch.py`, called from
`_pass` before `_release_filing`): `W.remerge_breaker_green`, which calls `_merge` (`dispatch_worktree.py`, the call
near line 1510), and `W.regate`. Part A puts the declared gate command (squiddy: `kit record-pass`, a full kit pass)
into the merge round. Built there as written, a breaker re-merge or a regate would hold the filing lock for the whole
kit pass, and every filing into that repository during it would be refused.

Amended Part A:
- The ledger check (`pass_unrecorded`: is there a line for the exact tip) may run under the lock. It is a file read.
- The gate command never runs while the pass holds the filing lock. The session chooses how: run it in the
  worktree before the merge round on the post-session path (which already runs after `_release_filing`); release the
  lock before re-merge or regate run it; or have the locked paths refuse `pass_unrecorded` and leave the record to a
  path outside the lock. Record the choice and its reason in the AD-034 ruling.
- Add one fixture: with a stub gate command that sleeps longer than a test `lock_wait_s`, a breaker re-merge or regate
  that runs it does not cause a concurrent `file_task` to be refused for the lock.

## 2. Deliverables: the return to squiddy goes out by `seldon cc file`, not by `seldon cc return`

The task asks for "the return to squiddy per AD-036-R16". SEL-024 has no `**Answers:**` header and answers no filing.
It comes from seldon's own work-order handoff (W6 of
`handoffs/2026-10-30_desktop_sq11_work_order_addendum_01_merge_gate_hand_dispatch_register_race.md`), and squiddy's
`cc_tasks/` holds no filing about the merge gate (searched 2026-11-06). `write_return` (`seldon/core/returns.py`)
refuses a task with no Answers ("answers no filing and has no consumer to return to"). Under AD-036-R18, `seldon cc
return --answers` resolves only a filing registered in seldon's graph or a task in the consumer's graph, and none exists
for this work.

Amended deliverable: write squiddy's task, which declares `dispatch.gate_record:` in squiddy's seldon.yaml, with
`seldon cc file --project /Users/brock/GitHub/squiddy --content-file <path>` (AD-038-R20). That call writes, commits
and registers it under squiddy's filing lock and squiddy's registration gates (candidacy headers, premises, number).
Name it in the RESULT as the return. If a squiddy filing about the merge gate is registered before this task runs, use
`seldon cc return --answers squiddy:<ref>` (AD-036-R16) instead and say so.

## 3. What SEL-023 changed that needs nothing here

- AD-038-R21 (a push on every pass): a merge this task gates reaches origin at the pass's end. Part A and Part B do not
  depend on it.
- AD-036-R17 (`**Kind:** filing`) does not apply. This is a task to execute, authored by seldon's own Desktop.
