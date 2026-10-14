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
   stream-json usage) and the wall time since launch, and prints the tokens. The dispatcher then runs that Part's
   `check:` criteria and records `milestone` with the CPI. **Exit 3 means a stop is written:** write the RESULT with
   what stands and end the session.
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

## Where the dispatcher reads the records

The lease holder (the pass that launched the session) inspects every `poll_interval_s` while it waits. launchd does
not start another pass while that one runs, so the holder is the only inspector for a session it launched. A pass that
finds the lease held by a holder from before QC-002 (no `stations` field in the lease body) inspects in its place and
reaps nothing; `seldon dispatch inspect` runs the same inspection by hand. Worktree sessions (`max_parallel > 1`) are not
inspected yet, which is why AD-037-R9's opt-in stays closed (`stations_live()["worktree"]`).
