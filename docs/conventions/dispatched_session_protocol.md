# Dispatched-session protocol: what a dispatched session appends, and when

**Governing:** AD-037-R6 (a) to (d), R7, R8 (`docs/design/AD-037_in_process_quality_control_for_dispatched_sessions.md`).
**Built by:** QC-002 (`cc_tasks/2026-10-14_QC-002_ad037_r6_four_stations_in_the_dispatcher.md`). Code:
`seldon/core/stations.py`, `seldon/commands/dispatch_stations.py`.

A session the standing dispatcher launched passes four inspection stations. The dispatcher runs the checks; the
session's part is to mark its boundaries on the record, and to halt when a stop is written. `seldon go` prints the
three lines below in every Claude Code session.

## The three lines

1. **At each Part boundary:** `seldon dispatch part-complete --part <name>`. It appends `part_complete` with the
   Part's planned share, the tokens used so far (input plus cache writes plus output, read from the dispatch log's
   stream-json usage) and the wall time since launch, and prints the tokens. **Exit 3 means a stop is written:**
   write the RESULT with what stands and end the session. When the session tries to end, its Stop hook runs the
   `check:` criteria of every Part it declared complete (FRICTION-002 Part C, below); the dispatcher records
   `milestone` with the CPI from that record.
2. **After the first unit of a loop the task marks `**First article:**`:** `seldon dispatch first-article --loop
   <name> --output <path>`. It appends `first_article` and waits on the dispatcher's verdict. Continue the loop only
   on exit 0 (`first_article_pass`). Exit 3 is a stop, or no verdict within `first_article_polls` polls (a huddle).
3. **At every other loop boundary:** `seldon dispatch boundary`. Exit 0 continues; exit 3 means a stop is written and
   `andon_halted` has been recorded: halt.

`--task <id or stem>` names the task when `SELDON_SESSION_ID` (set by the dispatcher) does not.

## What every task file carries from QC-002 on

- **`**Parts:**`, required.** Each Part's share of the `**Spend:**` estimate, summing to 1:
  `**Parts:** A 0.35, B 0.25, C 0.25, D 0.15.` Each Part is a heading `## Part <name>: ...`, and its acceptance
  criteria are marked `check: <command>` or `judgment: <why>` (AD-037-R1). `seldon cc register` refuses a task without
  the header as `parts_undeclared`. Tasks registered before QC-002's merge are baseline
  (`docs/evidence/qc002/parts_baseline.txt`).
- **`**Premises:**`, optional.** One line per factual premise:
  `- premise: <statement> | check: <command>` or `- premise: <statement> | judgment: <why no command decides it>`.
  The dispatcher runs every `check:` premise before launch. A false one refuses the launch (`premise_false`) and files
  an Issue naming it; the task waits until that Issue is resolved. `judgment:` premises are listed in the launch record
  for the R2 checker and are not evaluated until QC-003 calibrates one.
- **`**First article:**`, optional.** `**First article:** <loop name>, <check command>` for a loop over units. The
  command is decided by its exit code; `{output}` in it is replaced by the first unit's output path, which is also in
  `SELDON_FIRST_ARTICLE_OUTPUT`.

**A `check:` command must be runnable as written, and exit 0 must mean pass.** "`check: seldon cc register` refuses a
fixture task" is a description: the command exits 2 (usage) and the station records it `unrunnable` and opens a
huddle (QC-002 Part A, the first one recorded).

## What the dispatcher adds and enforces

- **Premise `environment_in_flight`**, on every task: no other project's dispatcher holds its lease on a repository
  this project's environment names (`dispatch.stations.environment_ref`, else `decisions.repositories`). From SQ-015's
  kit pass, where seldon's MODEL-003 merged under a running squiddy session.
- **Stops** (`session_stop`): a failed check at a milestone or first article (`line`), the operator's
  `seldon dispatch stop <task>` (`andon`), and the dispatcher's own spend or disk ceiling, or an operator's `--hard`
  for FC-32's toxic tier (`hard`). Nothing is killed by hand. A hard stop not answered by `andon_halted` within
  `reap_after_intervals` poll intervals is reaped by the lease holder (`andon_reaped`).
- **Huddles** (`huddle`, FC-29): opened by CPI below `cpi_huddle_below`, by an unrunnable check, or by a first-article
  wait, with the reading filled and cause and gate left open. Close one with
  `seldon dispatch huddle <task> --id <id> --cause <c> --gate <g>`; `seldon go` lists the open ones.
- **R7's reserve:** `dispatch_launched` records `inspection_reserve` (10% of the estimate). Each `milestone` records
  the inspection actually spent (check seconds, model tokens: zero until QC-003).

## Every task runs in its own worktree, with a completion gate (FRICTION-002, AD-034 ADDENDUM 01)

- **The worktree.** The dispatcher cuts `.claude/worktrees/<stem>` on branch `worktree-<stem>` and launches the CLI
  with `--worktree <stem>`. Claude Code refuses Edit/Write and git aimed at the primary checkout. Work, test and
  commit on the branch, the RESULT included. Do not merge, push or run `seldon cc complete`: the dispatcher merges
  on green and completes the task (AD-034-R5, R6). An unmerged task keeps its worktree and branch
  (`worktree_kept`); a merged one's worktree is removed by the sweep and its branch kept.
- **The Stop hook.** `seldon dispatch stop-gate`, installed per launch, runs the declared Parts' checks in the
  session's tree when it tries to end. While one fails and the session is under its token ceiling (the `**Spend:**`
  estimate times `spend_ceiling_factor`), the end is refused and the failing commands come back as the next
  instruction. At the ceiling the session may end and a hard stop is written. The milestone station runs no check of
  its own, so a failed check is a defect on the record, not a line stop.
- **Auto mode** (seldon). Sessions run with `--permission-mode auto`. Each classifier block is a `classifier_block`
  record (the `PermissionDenied` hook). The CLI's breaker (3 consecutive or 20 total) aborts the session, and the
  dispatcher records a `line` stop of station `classifier` with the classifier's reason. Answer it with
  `seldon dispatch redrive <task>`. Since DISP-002 (AD-034 ADDENDUM 02): a breaker trip whose session exited 0
  with its RESULT committed and its Stop gate passed is merged (`breaker_tripped_merged`), not stopped; launches
  carry `dispatch.allow`'s rules; and seldon itself is back on `bypassPermissions` by the kill rule (section 5).

## A task that answers another repository's filing files its return (SEL-013R, AD-036-R16)

- **The header.** A task that answers a filing from another repository carries `**Answers:** <repo>:<ref>`, where
  the ref is the filing's task number (`hazbrief-mcp:HB-37`), stem or id prefix. Registration resolves it in that
  repository's graph and refuses one that does not resolve (`answers_unresolved`).
- **The RESULT's section.** The RESULT holds a `## For <repo>` section: optional header lines at its top
  (`**Title:**`, `**Spend:**`, `**Network:**`, `**Parts:**`, or any candidacy header the consumer requires), then
  what the consumer does with what landed, in steps. A section may not set `Status`, `Author`, `Returns`, `Answers`
  or `After`: the writer sets those.
- **The return.** Run `seldon cc return cc_tasks/<task>.md` from the session's worktree once the RESULT is written. It
  writes the return task into the consumer's `cc_tasks/`, numbered by that repository's allocator, `After:` its
  latest open task, and registers it there, which commits it (AD-036-R12). `seldon cc complete` refuses the answering
  task (`return_unfiled`) until the return is registered and committed. When the session did not run it, the
  dispatcher's merged finish does, from the merged RESULT, and pushes the consumer. A finish that cannot file the
  return blocks the task with the reason instead of completing it.
- **Retired:** a RESULT's "For <consumer>: paste these steps" section, which the operator carried to the consumer
  by hand. The steps now go in the `## For <repo>` section, and the return task carries them. In a repository with
  no dispatcher, or one that is off, the return is registered and waits for someone to launch it by hand. That is
  the repository's own choice: hazbrief-mcp has no `dispatch:` block, so it holds a filed return until it is
  launched.

## Where the dispatcher reads the records

The lease holder (the pass that launched the session) inspects every `poll_interval_s` while it waits. launchd does
not start another pass while that one runs, so the holder is the only inspector for a session it launched. A pass that
finds the lease held by a holder from before QC-002 (no `stations` field in the lease body) inspects in its place and
reaps nothing; `seldon dispatch inspect` runs the same inspection by hand. Worktree sessions (`max_parallel > 1`) are not
inspected yet, which is why AD-037-R9's opt-in stays closed (`stations_live()["worktree"]`).

**A session working in a git worktree (AD-038-R4, FRICTION-001).** Run `part-complete`, `first-article` and `boundary`
from the worktree. The record is written to the PRIMARY checkout's event store (the parent of git's common directory),
where the dispatcher reads it, and carries the session's `cwd` and `branch`; the station runs the Part's checks in that
`cwd`. A check naming a file absent from the tree it ran in is `unrunnable` (a huddle with reason
`check_unrunnable_wrong_tree` when the session's branch holds the file), never a failed check. Merging each Part to
main before its `part-complete`, the workaround for Issue 02d52bc4, is no longer needed, and since FRICTION-002 it
is not possible: the CLI refuses a session's git aimed at the primary.

**A false stop is redriven, not re-issued (AD-038-R2).** `seldon dispatch redrive <task>` walks a blocked task back to
`accepted` with its file, id and history; the dispatcher redrives a wrong-tree or database-outage stop by itself.
