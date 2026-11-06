# RESULT: SEL-024 (task 0d115437): the merge gate requires the project's declared pass record for the tip it merges, and "environmental" is not green

**Date:** 2026-11-06. **Branch:** `worktree-prancy-crunching-eagle` (the dispatcher merges it).
**Rulings:** AD-034-R16, R17 and R18 (`docs/design/AD-034_ADDENDUM_08_the_merge_requires_the_declared_pass_record.md`).
Their records are in `docs/decisions/register/pending/` (00001 to 00003), numbered on main by the merge step.
**Tests:** `tests/test_sel024_gate_record.py` (24). Suite results: §6.
**Return to squiddy:** SQ-124 (`673d2f02`), filed with `seldon cc file` (squiddy commit `266f3991`), and its
ADDENDUM 01 (squiddy commit `f83bf3df`). See §5.

Recall used: none

## 1. What was measured before building

- **squiddy's ledger and record command** (`/Users/brock/GitHub/squiddy/kit/ledger/passes.jsonl`,
  `squiddy/kitpass.py`). Each line names `payload.commit` and `payload.package_tree` and carries `payload.passed`.
  `record-pass` runs three clean-clone suite runs: 2201.0 s, 2178.8 s and 2154.7 s on the 2026-10-30 line, about 108
  minutes in total. It appends to the checkout's ledger and exits 0 (pass), 1 (fail), 2 (fatal), 3 (lock drift) or
  4 (ceiling). `kitpass.pass_for` treats a pass as covering a later commit whose `squiddy/` tree is unchanged.
- **squiddy DN-052 R-237 item 1**: a pass line a branch records "is never merged into main's ledger; the tip that
  merges is re-recorded on main". The task's Part A, read literally (run the gate, then require a line for the tip),
  would have the merge carry the branch's line into main. That is why `branch_line` exists (§3).
- **The filing-lock window** (ADDENDUM 01 section 1) is as described. `_breaker_and_stale` runs inside it in both
  the serial pass and `pass_parallel`, and calls `remerge_breaker_green` and `regate`, which call `_merge`.
- **In-repo prior art reused.** `seldon.core.stations.run_check` already classifies 126, 127 and usage errors as
  `unrunnable`, which opens a huddle and never counts as a pass (AD-037 ADDENDUM 02). Huddles (`huddle_payload`,
  `open_huddles`) are AD-037-R6's. `seldon.core.pass_ledger` (SQ-096) established the pattern this task follows: the
  rule lives in the project, and seldon only runs it.

## 2. What landed, by Part

**A. A declared pass record gates the merge** (AD-034-R16).
- `seldon/core/gate_record.py` (new): `parse` validates `dispatch.gate_record` at load (from
  `load_dispatch_config`). The value is `none`, or a mapping of `command`, `ledger`, `commit_field`, `pass_field`
  and `timeout_s`, plus optional `requires`, `unrunnable_exits`, `tree_paths` and `branch_line`. `coverage` reads the
  ledger as the tip carries it. A line covers the tip when the commit it names differs from the tip, under
  `tree_paths`, only in the ledger and the merge round's housekeeping (`merge=union` files and `shared_paths`). The
  newest covering line decides, so a newer fail for the same tree is not a pass.
- `seldon/commands/dispatch_worktree.py`, `_merge(run_record=True)`. After the rebase, union, register and spec
  checks, `_ensure_record` reads the coverage. If no pass covers the tip, `record_pass` runs the command in the
  worktree through `run_check`, under the declared interpreter and outside the pass lease, and commits the appended
  line on the branch (`branch_line: commit`). Under `branch_line: discard` it reads the line into `gate_recorded` and
  restores the ledger. Coverage is then checked again. Still uncovered is `merge_blocked: pass_unrecorded`, naming
  the ledger. A housekeeping rebase under the lease is re-checked. The merge record carries `gate_record`.
- `seldon.yaml` declares `gate_record: none`, since seldon keeps no pass ledger.

**B. "Environmental" is a refusal** (AD-034-R17). `gate_record.run` reports `unrunnable` in five cases:
- a `requires` tool is not on the gate's PATH;
- the shell returns 126 or 127;
- the command prints a usage error (`run_check`'s own reading);
- python prints `No module named <module>` for its `-m` module;
- the command exits with a code declared in `unrunnable_exits`.

The round then:
- blocks `merge_blocked: gate_unrunnable`;
- opens a `huddle` with `reason: gate_unrunnable`, `tools`, `command` and `tip`;
- restores the ledger and commits nothing.

The session's RESULT is never read for this.

**ADDENDUM 01 section 1: no gate under the filing lock** (AD-034-R18). The choice was the third option, and its
reason is in the ruling. `remerge_breaker_green` and `regate` call `record_ready_under_lock` before they walk a task
to `in_progress`. It reads the ledger only. An uncovered tree with no record yet leaves the task as it was and writes
`gate_record_pending`. Both callers pass `run_record=False` to `_merge`. After `_release_filing` and before any
launch, the serial pass and `pass_parallel` run `_record_pending`, which runs the command for each pending task and
commits its event lines. The next pass merges on the record. `seldon dispatch regate`, which holds no filing lock,
passes `run_record=True`.

## 3. Departures from the brief, and why

1. **`tree_paths`.** Under the literal reading, "the exact tip", every commit main takes during a 108-minute gate
   (a filed task file, a handoff) makes a new tree, and a gate can be outrun indefinitely. squiddy's own rule
   (`pass_for`) covers a later commit whose `squiddy/` tree is unchanged. The default is still the whole tree; a
   project declares a narrower scope by its own rule. The addendum fixture shows this case: a filing lands on main
   mid-gate, and the next pass merges on the record without re-running the gate.
2. **`branch_line`.** R-237 item 1 forbids merging a branch's line into main's ledger, and the default `commit` would
   do exactly that. `discard` keeps squiddy's rule as written. Which value to use is squiddy's call (SQ-124 ADDENDUM
   01).
3. **Locked paths never block on an unrecorded tip.** They defer it. A deferred task is merged one pass later (five
   minutes) rather than blocked behind a redrive that would relaunch the whole session.

## 4. Tests

`tests/test_sel024_gate_record.py`, 24 tests:
- the declaration: `none` or absent; seven malformed forms refused at load; a parse is idempotent;
- the ledger read: a pass covers the commit it names and the ledger commit on top; housekeeping after the record
  keeps coverage; a code change after it does not; a newer fail for the same tree is not a pass; an unknown commit
  covers nothing; `tree_paths` scopes coverage;
- Part B: ruff absent, both declared in `requires` and as a bare 127, is unrunnable naming ruff; a missing `-m`
  module and a declared exit are unrunnable; a plain exit 1 is a fail;
- the task's fixtures, end to end through `seldon dispatch once` with a scratch ledger:
  - a tip with a record merges (main's line names a commit whose tree is main's apart from the ledger and the event
    store);
  - a tip without one is refused `pass_unrecorded`, both for a recorded fail and for no line;
  - with ruff absent, the task is blocked `gate_unrunnable`, a huddle names ruff, and no line reaches the branch;
  - `branch_line: discard` merges the judged commit, and no line reaches main;
  - `gate_record: none` merges as before.
- ADDENDUM 01's fixture: a regate whose stub gate sleeps 6 s, longer than a 1 s `lock_wait_s`. A `file_task`
  started while the gate runs, and finishing before it ends, is not refused. The gate ran once (in the record step);
  the next pass merged on the record.

## 5. The return to squiddy (ADDENDUM 01 section 2)

SEL-024 answers no squiddy filing, so its return to squiddy went out as a new task.
`seldon cc file --project /Users/brock/GitHub/squiddy` wrote, committed and registered
`cc_tasks/2026-11-06_SQ-124_declare_dispatch_gate_record_so_the_merge_requires_a_kit_pass_record.md` (task
`673d2f02`, number SQ-124 from `seldon task number SQ`). It asks squiddy to declare `dispatch.gate_record` with
seldon's reading of `kitpass.py`:
- `python -m squiddy.kitpass record-pass --checkout .`
- `kit/ledger/passes.jsonl`
- `payload.commit` and `payload.passed`
- `unrunnable_exits: [2, 3, 4]`
- `tree_paths: [squiddy]`

Each value is squiddy's to confirm. The task also asks squiddy to check that `$SQUIDDY_KIT_LEDGER` is unset for the
dispatcher, to decide on `requires: [ruff]`, and to record the cost of about one kit pass per merge.
`branch_line` came after the filing, so ADDENDUM 01 (squiddy `f83bf3df`) adds it and lays out the R-237 choice.

## 6. Suite

The full suite ran at this branch's second commit with `PYTHONPATH` at the worktree and `.env` loaded through
python-dotenv (`python -m dotenv -f .env run -- python -m pytest tests/ -q -p no:cacheprovider`): **3232 passed, 1
failed, 7 skipped, in 1:10:20.**

The one failure is `tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index`:
`release_unavailable: ... no commit of /Users/brock/GitHub/squiddy/graphs/library/exports/EXPORT_VERSIONS.md carries
7b72aaa89fe005d3`. It is a known failure on main: squiddy's export register has drifted from the served release, and
SEL-023's RESULT reports the same failure. This branch changes nothing under `seldon/core/prior_art.py` or the library.

`tests/test_sel024_gate_record.py` alone: 24 passed. The serial transcript test (`test_dispatch_serial_transcript`),
the DISP-002 breaker tests, the DISP-003 regate tests and the SEL-023 filing tests all pass, so the record step is
silent in a project that declares no `gate_record`.

## 7. Findings for a Desktop

- **AD-038-R18's `stale_evidence` retry turned a gating premise into a tautology.** SQ-124's first premise was
  `test -f /Users/brock/GitHub/seldon/seldon/core/gate_record.py`. It held SQ-124 until SEL-024 merges, which is its
  purpose. Registration rewrote it to `test -d ../seldon/seldon/core`, which always holds. The retry treats "the file
  this task waits for is not there yet" as stale evidence. SQ-124 ADDENDUM 01 section 2 tells its session to check by
  hand. A premise that names a sibling's not-yet-merged file is a legitimate wait, and the retry should not rewrite
  it. Not fixed here (out of scope).
- squiddy recorded `dispatch_refused 673d2f02` right after the filing (squiddy `6fde7b3e`). The reason was
  `environment_in_flight`: seldon's dispatcher holds its lease on seldon for this task (0d115437, since 14:23:18Z).
  AD-037-R6 (a) therefore holds SQ-124 until this session ends. That stands in for the weakened premise, but only
  until the session ends, not until the merge lands.
