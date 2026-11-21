# RESULT: SEL-042, a stopped session is never merged or completed, the merge round cannot refuse itself, verify reads pending records, and a name too long is a refusal

**Date:** 2026-11-21. **Branch:** `worktree-iridescent-nibbling-ritchie` (not merged by this session; the dispatcher
merges on green). **Task:** `3c39bd22`. **Addenda read:** ADDENDUM 01 (the stray `uv.lock`), carried out below.
Recall used: none. Registration listed eight hits (FRICTION-001, FRICTION-002, SEL-004, DESK-002, SEL-038, squiddy
R-252, AD-034-R6, LOOP-001). None was opened. The approach came from the four filings, the code, and the operator's
memory notes (worktree guard shapes, how register records are made, the known suite failures).

## In plain terms

- **A session the dispatcher stopped is never merged or completed.** HB-197 and HB-198 were stopped by the disk
  ceiling in their gates, and the round merged and completed both anyway. Now such a task is blocked
  `hard_stopped: disk_ceiling`, its work stays on its branch, and no successor is released.
- **Nothing merges without evidence that a gate passed.** A Stop gate that "passed" with no check to run is no longer
  counted. With no other evidence, the round runs the project's `gate_command` itself. A project with no gate command
  gets its task blocked `ungated`. **This changes factory:** factory declares no gate command, so a factory task whose
  Parts declare no `check:` will now block `ungated`. The recipe to fix it is under "For the operator".
- **The disk stop now leaves a run alone while it stays inside what it was admitted with.** Both hazbrief runs used
  more than that (12.8 GB and 9.6 GB against a 5 GB allowance), so both would still have been stopped. What was wrong
  was the merge after the stop.
- **The merge round can no longer refuse its own fast-forward.** Its `kept_events_deduped` line is written after the
  fast-forward, not between the journal commit and it. HB-189's replay shows which commit put the lines back on each
  rebase: its own `docs(HB-189 Part C item 9)` commit.
- **`seldon verify` runs with pending register records.** It prints every check and says which records are "numbered
  at merge". Nobody needs to move `pending/` aside any more.
- **A file name that is too long is refused before anything is written**, with the byte count and the room left.
  Registration warns when a task's name leaves under 60 bytes for an addendum's slug.
- **The stray `uv.lock` was written by seldon's own OODA knowledge source**, running in hazbrief, which ran
  `cd ../../../../seldon && uv run ...`. Its prompt now forbids that. The file sat unseen for fourteen hours because
  the queue was empty, and a task's dirt check runs only for a candidate.

## Part A: rulings (prior-art verify PASS on all three)

- `docs/design/AD-034_ADDENDUM_11_a_stopped_session_is_never_merged_and_the_round_cannot_refuse_itself.md`:
  AD-034-R25 (hard-stopped, never merged), R26 (gate evidence, else the round's gate, else `ungated`), R27 (nothing
  written to main between the journal commit and the fast-forward), R28 (the disk station reads a run against its
  allowance). Verdict PASS, event `47ffac3c`.
- `docs/design/AD-033_ADDENDUM_02_verify_reads_a_branchs_pending_records.md`: AD-033-R14. The first verify FAILED
  (`### External` carried no receipt); it now cites RFC 9162 from seldon-biblio. PASS, event `1a277e64`.
- `docs/design/AD-038_ADDENDUM_13_a_name_too_long_is_a_refusal_and_the_ooda_runs_nothing_outside_its_worktree.md`:
  AD-038-R30 (name limit) and R31 (the OODA's boundary). PASS, event `16b5f7d1`.
- Seven pending register records (`docs/decisions/register/pending/`), numbered at merge.
- Prior art: Saltzer and Schroeder's fail-safe defaults (R26) and Kubernetes' ephemeral-storage limits (R28) are cited
  from memory, unfetched. The library arm was searched for both, and neither seldon-biblio nor the squiddy library
  holds them (2026-11-21, logged in `state/prior_art_queries.jsonl`). RFC 9162 (AD-033-R14) is held and is cited by
  receipt.
- **Order departure.** The task put the rulings' `prior-art verify` before the code. I built and reproduced Parts B to
  E first, then wrote and verified the rulings from what the reproductions showed. No code was changed because of the
  verify.

## Part B: the stop that merged

**Reproduced first.** The fixture is cut from hazbrief's store (`docs/evidence/sel042/cut_fixture.py` writes
`tests/fixtures/sel042/hb197_hb198_events.jsonl`: each task's launch c12, its hard stop, `andon_halted`, its Stop
gate, its completion and its `dispatch_finished`). On the old code, `test_a_hard_stopped_session_...` merges
(`'merged' == 'hard_stopped'` fails), and so do the ungated and red-gate cases
(`docs/evidence/sel042/reproduction_old_code.txt`).

**What the finish read.** HB-197's Stop gate passed over three Parts whose `checks` were all `[]`. HB-198's passed
with no Part. `_gate_reading` returned `passed: True`, and with no file overlap and no declared pass record nothing
else was asked. The hard stop was in the store, and the finish never read it.

**Built** (`seldon/commands/dispatch_worktree.py`):
- `launch_hard_stops` and `finish_session`: any `session_stop` of kind `hard` since this launch blocks the task
  `hard_stopped: <reasons>` and keeps its worktree. A terminal task still takes SEL-034's path first.
- `gate_evidence` and `_merge`: the evidence is the declared pass record, the overlap re-gate, a kept branch's regate,
  or a Stop gate that passed after running at least one check (`_gate_reading` now returns `checks_run`). With none of
  these, `_merge` runs `dispatch.gate_command`: green merges with `gate_evidence.source = merge_gate`, red is
  `regate_red` with `evidence_gate: true`, and no command is `ungated`. The merge record carries `gate_evidence`.
- `seldon/core/dispatch.py` `disk_in_run` and `dispatch_stations.py`: the station's reading is compared with the
  launch's c12. A run is stopped only when the volume lost more than `need_bytes` since launch AND free is below
  `need`.

**The disk measurement** (Part B's question):

| | launch free | need (2 x tree) | free at stop | lost since launch | lost / need |
|---|---|---|---|---|---|
| HB-197 | 16,870,010,880 | 4,982,362,106 | 4,073,521,152 | 12,796,489,728 | 2.57 |
| HB-198 | 14,122,819,584 | 4,993,090,550 | 4,563,726,336 | 9,559,093,248 | 1.91 |

`need_bytes` is twice the tree git measures. `free_bytes` is `statvfs` on the project's volume, read at launch by c12
and every `poll_interval_s` by the station with the same `free >= need` test. HB-198's own record shows where the
space went: its worktree, a 3.78 GB clean clone in `/tmp` with its install, then the clone's gate (7.85 GB free down to
4.56 GB). The filing's "twice its footprint" (10.46 GB) was read after the worktree existed. **Seldon's own suite**,
sampled every 5 s through a full run (`docs/evidence/sel042/seldon_suite_free_disk.tsv`): the volume's free space fell
at most 853,196,800 bytes below its start (79.93 GB free). That is an upper bound, since anything on the machine
counts. It is over seldon's 114 MB allowance (2 x a 57 MB tree), but nowhere near `need`, so R28 never stops it.
hazbrief's gate is the one that writes GBs.

**HB-197 and HB-198** stay completed in hazbrief's graph, as hazbrief recorded them. seldon does not rewrite another
project's graph, and `completed` has no edge back. HB-202 and HB-203 already redo the work.

Tests (`tests/test_sel042_stopped_session_never_merges.py`): the fixture's Stop gates are not evidence; the evidence
order; both runs exceed their allowance; a run inside its allowance is not stopped; a hard-stopped session is blocked
and unmerged; no evidence and no gate gives `ungated`; a normal green finish merges on the round's gate; a red gate
keeps it off main. SEL-024's pass-record projects behave as before: `tests/test_sel024_gate_record.py` passes in the full suite, except its one known load flake, which passes alone.

## Part C: the round that refused itself

**The commit that restores the lines**, found by replaying HB-189's branch in a shared clone onto a main moved by one
journal line (`docs/evidence/sel042/hb189_replay.py`, `hb189_replay.txt`): `34984e36`
`docs(HB-189 Part C item 9): EVALUATION's paragraph ...` (`8dbe12c4` and `f9f168f6` before the rounds' rebases). It
appended HB-189's own three `artifact_updated` lines (`30730309`, `b1ab2033`, `dfa7ae1e`, written 07:39:30Z to
07:39:32Z). The kept-events reconcile had already put those lines on main. On every replay the count goes 1 to 2 at
that commit. The later removals (the hand edit `9e977247`, each drop commit) replay as no-ops: `merge=union` keeps both
sides of the conflicting hunk at the store's end.

**Reproduced first**: `test_a_branch_whose_rebase_restores_reconciled_lines_merges_in_one_attempt`. A session commit
appends three lines, the first finish reconciles them onto main, a second session's lines follow on the branch, and a
station line waits in main. On the old code it ends `ff_refused` after 3 attempts over `seldon_events.jsonl`
(reproduction file). Without the second session's lines it does not reproduce: the fast-forward then never touches
the store, which is why HB-189 (two sessions) hit it.

**Fixed**: `_merge` collects the `kept_events_deduped` payloads and writes them after `git merge --ff-only`, or in
`unmerged` when the round gives up. The test now merges in 1 attempt, with each id once on main and the dedupe
recorded.

## Part D: verify and pending records

`check_decisions` folds each register's numbered chain (`events(include_pending=False)`) for the projection
comparison and appends `N pending record(s), numbered at merge: <id> <event>, ...`. Reproduced with SQ-124's shape
(two accepts and an amend of a numbered record). On the old code it raised `KeyError: 'record_hash'` at
`seldon/core/decisions.py:772`, as the filing traced. Tests: the report line, and all 22 checks print. Dogfood: in
this worktree, with its seven pending records, `seldon verify` prints every check and the pending line
(`docs/evidence/sel042/verify_in_this_worktree.txt`). Its failures (File hashes, Governed docs, and a 53-record
projection gap) are main's own, read with main's code in the primary (`verify_on_main_primary.txt`). No seldon doc or
CLAUDE.md taught the "move pending aside" workaround (searched `docs/`, `CLAUDE.md`, `README.md`); only the operator's
memory note did, and it is updated.

## Part E: the name limit

`seldon/core/filing.py`: `name_limit` (`pathconf(PC_NAME_MAX)`, fallback 255), `addendum_slug_room`, `name_refusal`.
`file_task` and `file_addendum` refuse `name_too_long` before the lock or any write, as does `returns.write_return`
(dry run included). `cc.stem_room_warning` warns `addendum_slug_room` at registration below
`filings.addendum_slug_warn_bytes` (60, a first value). Tests at 255 bytes and at 256, with and without a two-byte
`é`. **Measured:** APFS took a 256-byte name of 255 characters (it counts characters), while a 256-byte ASCII name is
refused. The refusal counts UTF-8 bytes, ext4's rule, so a name filed here also fits every clone. HB-207's stem
(153 bytes) leaves 86 bytes of slug.

## ADDENDUM 01: the stray `uv.lock`

Full trace: `docs/evidence/sel042/uv_lock_writer.md`.
- **Writer:** the OODA knowledge source seldon's dispatcher launched in hazbrief-mcp on HB-212 (`f44dd32b`), session
  `a829d9a0`, worktree `wiggly-giggling-pine`. At 23:01:36.696Z on 2026-11-20 it ran
  `cd ../../../../seldon && uv run --quiet python -c "...addendum_header_refusal..."`, to check the HB-213 addendum it
  had just written. The lock locks `seldon` as `editable = "."`, and its mtime is 23:01:38Z. The same command made
  `seldon/.venv/`, which is gitignored, so it was not dirt.
- **Should it exist:** no. seldon is pip-installed and has never tracked a `uv.lock`. The writer is the defect. It is
  seldon's code (the OODA prompt) that did not state the boundary, so it is fixed with a test: AD-038-R31,
  `ooda.BOUNDARY_RULE`, `tests/test_sel042_ooda_boundary.py`. The prompt is the only guard. A structural refusal would
  be a new hook, which is not built here.
- **The quarantined copy and `.venv/`** are in seldon's primary, outside this worktree, so this session does not
  delete them. The recipe is under "For the operator".
- **For SEL-044:** the file sat 14 h 0 min unseen. Every pass from 23:01Z to 12:57Z read `nothing eligible (0
  candidate(s))`, and c7 is evaluated only for a candidate. SEL-041's registration at 12:57:41Z drew the first
  refusal at 13:02:21Z (`dispatch_stuck` at threshold 1, a local banner). Desktop's move cleared it before the
  13:07:32Z pass, so the alarm itself stood one pass. What counts as dirt is unchanged.

## Part F: returns

Filed after this RESULT is committed:
`seldon cc return <this task> --to hazbrief-mcp --answers seldon:<filing stem>` for `de40f402`, then again for
`6a9c00fa` and `1639fa20`. One return closes all three. squiddy's `5b76278b` is closed with
`seldon task close 5b76278b --note ...`; squiddy has nothing to do, so it gets no task. The outcome of each command is
appended below under "Returns filed".

## For hazbrief-mcp

This answers three filings: `de40f402` (HB-197 and HB-198 merged with no gate), `6a9c00fa` (the round's dedupe line
refused its own fast-forward) and `1639fa20` (an addendum name over 255 characters was a traceback).

What changed in seldon (AD-034 ADDENDUM 11, AD-038 ADDENDUM 13):
- A session the dispatcher hard-stops (disk or spend ceiling) is never merged or completed. Its task is blocked
  `hard_stopped: <reason>`, its worktree kept, and no successor is released. Redriving it is a person's or Desktop's
  call (`seldon dispatch redrive`).
- A branch merges only on recorded gate evidence. A Stop gate that passed with no `check:` to run no longer counts.
  hazbrief declares `gate_command`, so a task whose Parts declare no check is now merged on the round's own run of
  that command, after the session's: the gate runs twice. To make the session's gate the evidence instead, give each
  Part a `check:` line, or declare `dispatch.gate_record` (SEL-024).
- The disk station leaves a run alone while the volume has lost no more than the run's launch allowance (`need_bytes`,
  2 x the tree). HB-197 and HB-198 each used more (12.8 GB and 9.6 GB against about 5 GB, through the clean clone and
  its gate), so both would still be stopped. A clean clone of hazbrief needs its own disk check before it runs.
- The round writes its `kept_events_deduped` line after the fast-forward. HB-189's lines came back on every rebase
  through its own commit `34984e36` (`docs(HB-189 Part C item 9)`), which appended the three lines main had already
  reconciled. `merge=union` then undid each later removal. A branch like HB-189's now merges in one attempt.
- `seldon cc file`, its addendum path and `seldon cc return` refuse a name longer than the file system takes,
  counted in UTF-8 bytes, with the room left. Registration warns when a stem leaves under 60 bytes for an addendum's
  slug. HB-207's stem leaves 86.
- `seldon verify` now runs with pending register records and lists them as numbered at merge. Moving `pending/` aside
  is no longer needed.

What stays as hazbrief recorded it: HB-197 and HB-198 remain completed in hazbrief's graph. seldon does not rewrite
another project's graph, and HB-202 and HB-203 already redo the work.

On the OODA between chained tasks: by design (AD-038-R16) it is the dispatcher's knowledge source, read when a task
completes, and it releases the successor. A successor that needs a person's turn says so with `**Dispatch:** hand`
or with a premise marked `| at: launch`, which is evaluated when the successor launches, not at registration.

One more thing, reported because it ran under hazbrief's dispatcher: on 2026-11-20 at 23:01Z the OODA session on
HB-212 (worktree `wiggly-giggling-pine`) ran `uv run` inside seldon's checkout. That wrote a `uv.lock` there that
stopped seldon's queue. The fix is seldon's (the OODA prompt now keeps every command inside its worktree), and hazbrief
has nothing to do.

## For the operator

1. **factory (do this before its next task launches).** factory declares no `dispatch.gate_command`, so once this
   merges, a factory task whose Parts declare no `check:` blocks `ungated`. In the factory repository, in Claude Code
   or a shell, add under `dispatch:` in `/Users/brock/GitHub/factory/seldon.yaml`:

       gate_command: python -m pytest tests/ -q -p no:cacheprovider

   then commit only that file, in a shell, 1 then 2:

       git -C /Users/brock/GitHub/factory add seldon.yaml
       git -C /Users/brock/GitHub/factory commit -m "dispatch: declare the gate (seldon AD-034-R26)" -- seldon.yaml
2. **The quarantined lock and the stray venv in seldon's primary** (both made by the OODA's `uv run`; neither is
   tracked). In a shell, after this task merges:

       rm /Users/brock/GitHub/seldon/.seldon/quarantine_uv.lock_2026-11-21
       rm -rf /Users/brock/GitHub/seldon/.venv

## Verification

- New tests: `tests/test_sel042_stopped_session_never_merges.py` (11), `tests/test_sel042_verify_pending_and_name_limit.py`
  (9), `tests/test_sel042_ooda_boundary.py` (2). All pass. The reproductions fail on the old code
  (`docs/evidence/sel042/reproduction_old_code.txt`: 10 of 11 and 9 of 9).
- Tests restated because a project with no gate now blocks `ungated`, which is the rule:
  - `tests/dispatch_scaffold.py` declares `gate_command: true`, and so does `tests/test_dispatch_launch.py`'s fixture.
  - `test_dispatch_parallel::test_main_moving_under_the_write_set_reruns_the_gate[red]` used to merge task `a` with a
    tree that failed the project's gate. Its gate is now red only on `b`'s rebased tree.
  - The serial transcript is re-recorded, with an erratum. The strip check equals the old fixture once the three
    additions are removed (`True`).
- Full suite, first run on the code commit: 11 failed, 3462 passed, 7 skipped in 25:40. The failures were:
  - 7 tests restated above;
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` (known library drift);
  - `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait...` and
    `test_dispatch_parallel::test_two_disjoint...` (known load flakes; both pass alone).
  The confirming run is recorded below under "Suite".
- `seldon verify` in this worktree: every check printed, pending line present. Its failures are main's own (see Part D).

## Spend

`seldon dispatch part-complete` read 369,782 tokens at Part E. Zero model calls by code. The estimate was 1.2M and
the stop is 1.45M.

## Returns filed

- hazbrief-mcp: `cc_tasks/2026-11-21_HB-217_a_session_the_dispatcher_stopped_is_never_merged_or_completed_the_merg.md`
  (task `084beda4`), registered and committed in hazbrief's primary through its filing lock, with a dry run first. It
  closed `de40f402`. Re-running it with `--answers` for `6a9c00fa` and `1639fa20` reported "return already filed", and
  the graph now reads all three filings `completed`.
- squiddy: `5b76278b` closed with `seldon task close` and the answer as its note (proposed -> completed). There is no
  task in squiddy, because squiddy has nothing to do.

## Suite

Confirming full run on `b9d52fa` (code, rulings and records final): **3 failed, 3472 passed, 7 skipped in 25:51**
(`python -m dotenv -f .env run -- python -m pytest tests/ -q -p no:cacheprovider -n 6`). The failures:
- `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` is the known library
  drift, failing on main as well.
- `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait...` and
  `test_friction002_auto_mode::test_a_classifier_breaker_becomes_a_line_stop_with_the_classifiers_reason` are the known
  load flakes. Both passed when run alone afterwards (2 passed, 70.9 s).

Commits after `b9d52fa` change only this RESULT, the evidence and the event store.
