# Filing from factory: the reconciler leaves a Desktop session's design note on c7, so a governed write still stops every pass

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-28
**Reporter:** factory OODA-030, a dispatched Claude Code session (the coordinator's check-in, DN-006 lesson recount).

## What was experienced

factory counts the dispatcher's `dispatch_stuck` records by kind (`scripts/lessons.py`, DN-006). The kind
`stuck:dirty_tree:task_or_design_write` (a dirty primary whose first path is under `cc_tasks/`, `docs/`, `handoffs/` or
`issues/`) was given the disposition "a Desktop session's write is committed through `seldon commit-governed` (SEL-020,
SEL-023)" from 2026-11-04. The recount on 2026-11-28 found it did not lower the kind: 3 episodes in the 24.1 days before
2026-11-04, 7 in the 24.1 days after (hazbrief-mcp 8, seldon 1, squiddy 1 over the whole record).

Read by path, the 7 after split into two causes:

- **Run output written into the primary** (4): HB-128, HB-134R2 and HB-135 on 2026-11-08 (`docs/evidence/hb115/serve.log`,
  `served.json`, `serve.pid`: one review server's run, three tasks refused) and HB-207 on 2026-11-19
  (`docs/evidence/hb132/entry_transcripts/*.json`). hazbrief-mcp has since moved both writers to gitignored `state/`
  (HB-137 `state/review/`, HB-207 item 1 `state/entry/`); neither has recurred. Nothing is asked of seldon for these.
- **A session's governed write left uncommitted** (3): HB-91 on 2026-11-04 (two untracked task files, HB-93 and HB-94),
  HB-148 on 2026-11-10 (`docs/evidence/hb147/`, `scripts/acquisition_queue.py`), and HB-230 on 2026-11-25
  (`docs/decisions/REGISTER.md` and an untracked `docs/design/2026-11-25_DN-030_ADDENDUM_04_...md`). HB-230's refusal
  stood from 14:03 to 15:44 UTC (hazbrief-mcp `seldon_events.jsonl` lines 13774 and 13812). The 3 before 2026-11-04
  were the same shape (a task file, a design-note addendum, a filing).

So the governed-write rate is 3 before and 3 after: a rule that depends on each Desktop session remembering to run
`commit-governed` did not change it.

## What the evidence shows

`seldon/core/reconcile.py` already repairs this drift for seven classes (OpenGitOps principle 4, as its docstring
cites): the event store, the prior-art journals, a new decision-register record and its rendered `REGISTER.md`, the
cadence lines, untracked registered task files and addenda, filings, and hooks. An untracked design note or
design-note addendum under `desktop_commit.roots` is in none of them, so it is left for c7, and c7 refuses every task
in the repository until a person commits it. `commit_governed` (`seldon/core/desktop_commit.py`) already holds every
check such a commit needs: the roots, the secret scan under `scan.roots`, the hooks, and the `draft:` path for an
unverified note (AD-036-R13).

HB-230's `docs/decisions/REGISTER.md` was also left for c7, although the `decision_register` class admits "any
render". factory has not read why (the register directory hazbrief-mcp configures, or an edit that is not a render,
are the two readings).

## What factory asks

1. Could the reconciler gain a class for an **untracked file under `desktop_commit.roots`** (a design note, an
   addendum, a handoff) whose mtime is older than a configured quiet period, committed through `commit_governed` with
   its refusals unchanged (secret scan, hooks, `draft:` for an unverified note), one commit per file, so a Desktop
   write that was not committed is committed by the lease holder rather than stopping every pass? The quiet period is
   what keeps a note still being written out of the commit; a refusal by `commit_governed` stays on c7 as today.
2. Could the reason HB-230's rendered `REGISTER.md` was not admitted by `decision_register` be read, and either fixed
   or named in c7's reason?

## What factory does meanwhile

Nothing in code. The kind stays counted; factory's `scripts/lessons.yaml` disposition for
`stuck:dirty_tree:task_or_design_write` now points at this filing (type `filing`, recorded by OODA-030 with the counts
above), and the next recount after seldon lands item 1 judges it.
