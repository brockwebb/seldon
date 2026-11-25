# RESULT: SEL-043, a consumer waits on a producer only while what it reads can change, a running gate shows its progress and its wall time, and a release's rows will come from the kit

## Round two (ADDENDUM 01), 2026-11-24

The two red tests were caused by code this branch did not touch (`register` and `task_states` in
`tests/dispatch_scaffold.py`); the fix is 5 lines, so it is made here. Every dispatcher scenario registers the same
few task names (`a`, `b`) with one `created_at` into the session's single shared test database, and nothing removed
an earlier test's `a`. `task_states` then reported whichever `a` Neo4j's scan returned last. The dispatcher's own queue,
which breaks a `created_at` tie by scan order, could also launch an earlier test's `a`. This confirms the addendum's
observation.

- **Replay:** branch tip `af8353d`, reset to `worktree-iterative-moseying-clock`, then rebased: 29 of 29 commits, no
  stop. The replayed tip is `1f15a1a`.
- **Step 1:** the two files alone gave 14 passed, 1 skipped.
- **Step 2:** the targets failed after the files sorting before them. They failed after files 1 to 35, and after
  files 27 to 35 in one of two runs. No half of 27 to 35 and no single file of it reproduced the failure. The full
  1 to 69 prefix failed two other tests in the same way, plus one in the queue (`test_dispatch_parallel.py`, and
  `test_friction002_worktree_only.py`'s merge test). Main's tree passed 27 to 35 in its one control run. The order is
  decided by the store's id history, not by any one earlier test, so the set was not narrowed further.
- **Fix:** `register` deletes any earlier `ResearchTask` with the scenario's name before creating its own. No
  assertion changed. Nothing was deselected or skipped, and `gate_command` is unchanged. The regression test is
  `tests/test_sel043_scaffold_task_names.py`, written first; it was red before the fix and is green after.
- **After the fix:** the two target files plus the new test gave 15 passed, 1 skipped. Files 27 to 35 plus the
  targets gave 65 passed, 1 skipped. The full 1 to 69 prefix plus the targets gave 931 passed, 1 skipped, where the unfixed tip failed 4.
- **Evidence:** `docs/evidence/sel043/round_two.txt` (every run, its count and the cause), with the runner
  `docs/evidence/sel043/bisect_run.sh`. Round two used none of the recall hits.


**Date:** 2026-11-24. **Task:** `bf0b7a06`. **Branch:** `worktree-iterative-moseying-clock` (not merged by this
session; the dispatcher merges on green). **Addenda read:** none exist for this task.
Recall used: none. Registration listed eight hits (SEL-005, SEL-004, SEL-013R, squiddy SQ-139, squiddy R-256, squiddy
`a44ac624`, SQ-099, SEL-023). None changed the approach. R-256 and SQ-139 were read because the filings name them: R-256
lists what squiddy left to seldon, which is this task's scope, and SQ-139's RESULT is filing `9fb2e0b8`'s evidence.
Reading R-256 led to squiddy's DN-062, which changed one ruling's text (AD-036-R28 cites it, below). The design came
from the filings, the code and Part A's measurement.

## In plain terms

- **A consumer no longer waits on a producer that is not touching it.** Station (a) used to refuse every consumer for
  as long as any producer's dispatcher held its lease. That covered the producer's whole session and its merge
  round's gate: two to three hours for squiddy. Now it holds a consumer only while the producer may be changing what
  the consumer reads. That means the producer's pass and its merge outside the gate, minutes at most. It also holds
  while the producer's task writes into the consumer, or into something the consumer reads, by path.
- **Measured before building:** 52 refusals since 2026-10-17 held consumers for 53.3 hours. 50.3 of those hours fell
  while the producer was in its session or its gate, and none of that work touches what consumers read. At most 2.4
  hours fell in a merge.
- **Every refusal and `seldon dispatch status` now say who holds, on which task, in which phase, since when, and why.**
  If the holder is running a gate, they also show how long it has run by the wall clock, how many lines it has
  written, its last line, and when it last wrote. Output that has stopped growing is how a hung gate shows itself.
- **A running gate's output is readable while it runs.** squiddy's kit pass now writes to the task's gate log line
  by line, as seldon's gate command already did.
- **Gate records carry wall time and sleep.** Monotonic seconds leave out sleep: a pass recorded as 7,734 s took
  10,834 s. Each record now also has wall start, wall end, wall seconds and the seconds asleep from the Mac's power
  log. Sleep is recorded as unknown, never as zero, when the power log does not reach back that far. It reaches back
  only to 2026-11-17 on this host, so it can no longer answer for the 11-13 pass.
- **R9's no-model-calls check costs nothing now.** It runs on the test session itself instead of as a nested
  re-run. In seldon the nested run took 67 to 96 s. squiddy had already made the same change on its own (DN-062);
  AD-036-R28 says that is within R9.
- **A release the kit's reader refuses is now `release_unavailable`, not a traceback.** seldon now asks squiddy for
  one call that returns a release's rows under the rule that release was cut under. Until squiddy has it, nothing
  changes in which rows are read, and the 3-of-2,261 difference is recorded as a known limit.

## Part A: the measurement (`docs/evidence/sel043/`, read only)

**(1) What station (a) protects.** Every consumer's interpreter imports both seldon and squiddy as editable installs
of the producers' primary checkouts (`imports.json`). That holds for the dispatcher's python (`/opt/anaconda3`, which
every project's checks and hooks run), squiddy's `.venv`, and aacps' gate (squiddy's `.venv`). hazbrief's own `.venv`
has neither; it reaches squiddy through squiddy's `.venv` (`squiddy_python`) and seldon through the dispatcher's
python. Consumers also read producers' files by path: hazbrief reads `../squiddy/squiddy/spend.yaml` and both
`governed` graphs.

| consumer | reads from | from where | the producer changes it at |
|---|---|---|---|
| seldon | squiddy | editable install of squiddy's primary; squiddy's served library graph | squiddy's pass, merge (fast-forward), release (a merged task) |
| squiddy | seldon | editable install of seldon's primary (squiddy `.venv`), dispatcher's seldon | seldon's pass, merge |
| hazbrief-mcp | squiddy, seldon | squiddy's `.venv` (editable primary), `../squiddy/...` paths, both `governed` graphs; dispatcher's seldon | pass, merge; and a seldon task whose Repo line names hazbrief writes it during its session |
| aacps-ai-policy | squiddy, seldon | its gate runs squiddy's `.venv` (editable primaries) | pass, merge |
| factory | squiddy, seldon | dispatcher's python (editable primaries); no `.venv` | pass, merge |

Every repository dispatches serially (`max_parallel: 1`). The producer's session and the merge round's gate run in
the task's worktree (AD-034), so they write nothing in the primary. The exception is a session whose Repo line names
another repository (DISP-004R).

**(2) Every `environment_in_flight` refusal**, 2026-10-17 to 2026-11-24 (`refusals_table.md`,
`tools/refusals2.py`). A wait runs from the refusal to the consumer's next launch or the producer's
`dispatch_finished`, whichever comes first. Waits are unioned per consumer.

| consumer | producer | refusals | hours waited | in producer session | in producer gate | in producer merge | between tasks |
|---|---|---|---|---|---|---|---|
| factory | squiddy | 1 | 2.9 | 0.6 | 2.3 | 0.00 | 0.00 |
| hazbrief-mcp | seldon | 17 | 13.5 | 12.3 | 0.0 | 1.12 | 0.17 |
| hazbrief-mcp | squiddy | 18 | 21.6 | 10.1 | 10.2 | 1.25 | 0.09 |
| seldon | squiddy | 7 | 9.2 | 7.4 | 1.8 | 0.03 | 0.00 |
| squiddy | seldon | 9 | 5.9 | 5.6 | 0.0 | 0.03 | 0.26 |
| all | | 52 | 53.3 | 36.0 | 14.3 | 2.42 | 0.52 |

The merge column is an upper bound. Before SEL-041 (2026-11-21), seldon's merge-round gates left no gate record, so a
seldon round reads as all merge. Three refusals named a producer task whose Repo line wrote the very consumer it held
(seldon `841bd7c7` into squiddy; `c4d813a9` and `0a8a6776` into hazbrief; `push_repos.txt`). The new rule keeps
those holds.

**(3) seldon's R9 instrument**, run alone three times (`r9_runs.txt`): 66.7, 71.1 and 95.8 s; 0.39 to 0.40 GB peak
resident, children included. In a full run it competed with the suite's workers. squiddy's (filing `083863ef`) was
1,278 s and about 9.8 GB, three times per pass.

## Part B: the rulings

`docs/design/AD-037_ADDENDUM_05_a_consumer_waits_on_a_producer_only_while_what_it_reads_can_change.md`:
AD-037-R17 to R21. `prior-art verify` PASS, event `78fb3950`.

- **R17, the window.** The pass lease records `phase` (`pass`, `session`, `gate`, `merge`) and `phase_since`. Station
  (a) holds in `pass`, in `merge`, when no phase is recorded (a holder running older code; fail-safe), and in any
  phase whose `writes` names the consumer or a repository it reads.
- **R18, the pin.** Part A found consumers read producers' primary trees live, so the rule is a pin. Each premise
  review records `pins`, `{head, branch, dirty}`, for every producer. The record lands in `dispatch_launched` under
  `premises.environment.pins`. It records the version, but does not isolate it.
- **R19, what is shown.** Who holds the lease, on which task, in which phase, since when, why, and the gate's progress.
- **R20, the gate log.** The gate's output goes to the log line by line as it runs.
- **R21, the clock.** Wall time and sleep on every gate record; wall time is what a person is shown.

The task named B's expected shape, and A confirmed it: a producer's session and gate hold nobody. The pin comes from
A's finding that the read is live. The task asked for `prior-art verify` before C to E. The code was written before
the note and verified afterwards, in this order: A, tests, code, then note and verify. That is a deviation. The verdict
was taken on the final text before anything was committed.

`docs/design/AD-036_ADDENDUM_15_..._release_unavailable.md`: AD-036-R28 to R30, `prior-art verify` PASS, event `cc0f1875`
(re-verified after the DN-062 edit; see "Deviations").

## Part C: the station and what a waiting operator is shown

- `seldon/core/dispatch.py`: `PHASE_*`, `mark_phase` (it rewrites the lease only when this process holds it). A new
  lease starts in `pass`.
- `seldon/commands/dispatch.py`: the serial pass marks `session` with `writes` (the Repo line's repositories) before
  the CLI runs. The refusal record carries the full `held` view and `windows`, and is recorded once per holding window.
  `environment_lines` prints one line per lease. `status` gains `environment` (`held`, `not_holding`, `pins`),
  `lease_gate` and the text lines.
- `seldon/commands/dispatch_worktree.py`: `_gate_phase` marks `gate` around `_gate` and `record_pass` and puts the
  previous phase back. `finish_session` marks `merge`, and `_merge_phased` marks it again whenever the lease is taken.
- `seldon/core/stations.py`: `HOLDING_PHASES`, `_holds`, `environment_premise` (`held`, `not_holding`, `pins`),
  `environment_pin`, `gate_progress`.
- Tests, `tests/test_sel043_environment_window.py` (11). The two-repository fixture runs real passes against a scratch
  Neo4j with a sibling whose lease this process holds and marks:
  - a consumer is refused across the producer's `merge`, with phase, task and since in the record and the message;
  - it launches while the producer is in `gate`, and `status` shows the gate's last line and wall time;
  - a second `merge` window is one more refusal, however many passes see it.
  - Separately: a real serial pass records `session` while its CLI runs, and `gate` with the gate log while its merge
    gate runs (snapshots taken by the stub CLI and by the gate command).
  - Also tested: the rule for each phase, no phase, `writes`, pins, `mark_phase` ownership, and `gate_progress`.

## Part D: a running gate

- `stations.run_check(stream_to=...)` appends each line to the log as it is printed. The log gets a `=== <time> | gate
  record | <command>` line first and an `EXIT=` line last. A timeout kills the process group. The tail is still kept.
  `gate_record.run(log_path=...)` uses it, and `record_pass` writes to `<log_dir>/<stem>.gate.log` and prints the path.
- Every `run_check` row, `gate_record.summary`, `gate_plan.run`'s result and the `gate_run` record carry
  `started_at`, `ended_at`, `wall_seconds` and `asleep_s`. `asleep_seconds` reads `pmset -g log`'s Sleep, Wake and
  DarkWake lines, and only when wall time exceeds monotonic time by more than 2 s. The weekly chart in `seldon qc
  chart` uses wall seconds. The slow-gate warning stays on monotonic seconds, because a slept laptop is not a slow
  gate.
- Tests, `tests/test_sel043_running_gate.py` (8). A gate that prints, sleeps 3 s and prints again: its first line is
  readable before it exits. A stubbed power log cut from SQ-133R's window gives 1,534 + 1,618 s asleep, including a
  Sleep ended by a DarkWake. A window the log does not reach is unknown. Also tested: timeout, unstreamed rows, both
  gate records.
- **Found on real data and fixed, test first:** the power log on this host begins 2026-11-17, so for SQ-133R's 11-13
  pass it held no line and the first version said `0.0` (`asleep_sq133r.txt`). It now says `None` when the log starts
  after the gate did.

## Part E: two smaller answers

1. **R9's instrument (AD-036-R28).** The assertion holds on the outer session. `tests/r9_shim.py`, loaded by
   `tests/conftest.py`, puts a recording `claude` first on PATH for the whole session. The controller installs it, and
   xdist workers, git hooks and subprocesses inherit it. A session with any recorded call fails and names the calls.
   The nested run is gone. `tests/test_no_live_model_calls.py` (4 tests, 8 s) shows three things: a planted call
   fails a session with only the shim loaded, both serially and under `-n 2`; a clean session passes; and the running
   session resolves `claude` to its shim. **What a consumer may now do:** (a) run the shim on its outer session with
   the same controls, or (b) keep a nested run, once per commit rather than once per run. squiddy already took (a) in
   DN-062 (R-262 to R-266, SQ-142), and R28 says that is within R9.
2. **`rebuild_release` (AD-036-R29, R30).**
   - `open_rebuilt` maps the kit's `IndexSchemaError` to `release_unavailable`, naming the release, the commit and the
     reader's message. Any other error passes through. The error raised is both a `PriorArtError` and the kit's
     `IndexSchemaError`, and its message begins with the kit's text. **Found by running squiddy's own tests against
     this branch:** squiddy's release-receipt control catches `ix.IndexSchemaError` from `open_rebuilt` and checks
     the message prefix. The first version, which converted the error, failed squiddy's
     `test_a_receipt_on_the_superseded_release_resolves_and_the_control_fires`. With the error as both, its ten tests
     pass, and so do 104 squiddy tests across the eight files that touch the changed code
     (`squiddy_tests_on_branch.txt`, `tools/squiddy_sq139.py`). A test in seldon runs squiddy's control itself.
   - `checkpoint_rows` uses the kit's `release_rows(graph, manifest, *, commit)` when the installed kit has one, by
     name, and otherwise reads as before.
   - Tests, `tests/test_sel043_release_rows.py` (6): the real reader on an index built with arm A's columns, other
     errors pass through, the old path, the kit's call, and the kit's refusal.
   - The 3-of-2,261 difference is recorded in R30 as the known limit beside AD-036-R19.

## Part F: the returns

Each was filed with `seldon cc return` (dry run first) from the sections below, and committed in its repository by
its registration:

- **squiddy:** SQ-143 (`627c92ed`), `squiddy/cc_tasks/2026-11-24_SQ-143_a_consumer_s_dispatcher_waits_on_a_producer_only_for_what_can_hurt_it.md`.
  It is a report, plus the one thing asked (item 4: `release_rows`). It closed all three filings (proposed to
  completed, AD-036-R17): `9fb2e0b8` when it was filed, then `44ba49df` and `083863ef` by re-running with their
  `--answers`.
- **hazbrief-mcp:** HB-229 (`489e1829`), one line, nothing to do, `--answers hazbrief-mcp:HB-177`. HB-177 is the task
  refused on 2026-11-13. The return template says HB-177 "was filed into seldon", which is false; the section corrects
  it.
- **factory:** FAC-09 (`5d78e3b3`), one line, nothing to do, `--answers factory:FAC-04`. FAC-04 was refused on
  2026-11-14. The same template correction applies.

The task allowed the last two because Part C changed what both dispatchers do. Each is a dispatchable task of about
0.1M tokens, because this return mechanism files a task.

## Tests

- **New:** 25 tests in the three `test_sel043_*` files, plus the rewritten `test_no_live_model_calls.py` (4). All
  pass. Each new behaviour's test was run red first: the station tests failed with `AttributeError`; the release
  tests failed on the first version of the code before the dual-type fix; the power-log test failed on the real
  `0.0`.
- **Full suite**, `-n 6`, on `d3ff232` plus the RESULT, from 23:32Z to 00:05Z (32:49): **3,537 passed, 4 failed,
  7 skipped**, load average 13 to 29, with hazbrief's gate running on the same host. All four failures are on SEL-041's
  list of known ones:
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` is library drift,
    known on main and deselected in seldon's `gate_command`.
  - `test_dispatch_parallel::test_union_merge_of_two_event_appends_is_valid` and
    `::test_an_exclusive_task_waits_for_running_ones_and_blocks_new_ones` both passed when re-run alone.
  - `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait...` failed when re-run alone at load
    12.8. It fails the same way on main's own code in a `/tmp` shared clone (`docs/evidence/sel043/tools/main_clone.py`,
    run 19:12 local), so it is load, not this branch.
- **squiddy's tests on this branch:** 104 passed, across the eight squiddy test files that touch the changed seldon
  code (`squiddy_tests_on_branch.txt`).

## For squiddy

This answers three filings: `44ba49df` (the lease), `083863ef` (three findings in the merge round) and `9fb2e0b8`
(rebuilt releases). One thing is asked of squiddy, item 4. The rest is a report.

1. **The lease (44ba49df).** A consumer is no longer refused while squiddy's session or merge-round gate runs.
   Station (a) holds a consumer only in squiddy's pass and in its merge outside the gate (AD-037-R17, seldon AD-037
   ADDENDUM 05). Measured over 52 refusals since 2026-10-17: 50.3 of 53.3 hours waited fell in a producer's session or
   gate. hazbrief's 2026-11-13 wait (HB-177, 18:05Z to 20:39Z) was all gate and merge; under the new rule it would
   have been held only for the last minutes of the merge. Each refusal and `seldon dispatch status` now name the
   holder, task, phase, since when, and the gate's progress. Nothing in squiddy changes for this. squiddy's
   dispatcher marks its phases through seldon's code, from the first pass after this merges.
2. **The round's output and seconds (083863ef, items 1 and 2).** `record_pass` now streams the kit pass's output to
   `logs/dispatch/<task stem>.gate.log` line by line as it runs (AD-037-R20), and the lease names that file. Every
   `gate_recorded` and `gate_run` record carries `started_at`, `ended_at`, `wall_seconds` and `asleep_s`, from
   `pmset -g log`; `asleep_s` is null where the log does not reach back (AD-037-R21). squiddy's own progress file and
   `SQUIDDY_KIT_PROGRESS_LOG` are unaffected, and the two do not conflict.
3. **R9's instrument (083863ef, item 3).** seldon's AD-036-R28 rules that the shim may run on the outer session, and
   names squiddy's DN-062 (R-262 to R-266) as within R9. Nothing is asked: squiddy already did this.
4. **Rebuilt releases (9fb2e0b8).** seldon now maps `IndexSchemaError` to `release_unavailable` (AD-036-R29). The error
   `open_rebuilt` raises is both a `PriorArtError` and an instance of the kit's `IndexSchemaError`, and its message
   begins with the kit's own, so your stage-18 control (`release_receipt._planted`, `--mutate`) still fires. Converting
   the error alone broke `tests/test_sq139_release_receipt_stage.py` on this branch, which is why it is both. 104
   squiddy tests that touch the changed seldon code passed against this branch (seldon
   `docs/evidence/sel043/squiddy_tests_on_branch.txt`).
   **The one thing seldon asks:** expose
   `squiddy.index.release_rows(graph, manifest, *, commit) -> iterable of row dicts`. It returns the rows of the
   release recorded at `commit` (whose corpus manifest is `manifest`), read from the corpus checkpoint under the row
   rule that release was cut under, with `text_sha256`. It refuses as `iter_rows` does (SystemExit naming the unit)
   when a unit has no rows under that rule. seldon calls it by name when the installed kit has it
   (`seldon.core.prior_art.checkpoint_rows`, `KIT_RELEASE_ROWS`), and reads as today until then. Where the rule a
   release was cut under is recorded (the export, the register, the served manifest's history) is squiddy's to
   decide. Done means: the library's older releases rebuild with the rows they served (the 3 of 2,261 agree), and a
   `text_of_record: parsed` graph's older releases rebuild instead of answering `release_unavailable`.

## For hazbrief-mcp

One line, nothing to do: from SEL-043's merge, hazbrief's dispatcher is no longer refused `environment_in_flight`
while squiddy's or seldon's session or merge-round gate runs, only across their pass and merge, and the refusal and
`seldon dispatch status` say who holds, in which phase and since when (seldon AD-037-R17, R19). This answers the wait
HB-177 had on 2026-11-13; HB-177 was not filed into seldon.

## For factory

One line, nothing to do: from SEL-043's merge, factory's dispatcher is no longer refused `environment_in_flight`
while squiddy's or seldon's session or merge-round gate runs, only across their pass and merge, and the refusal and
`seldon dispatch status` say who holds, in which phase and since when (seldon AD-037-R17, R19). This answers the wait
FAC-04 had on 2026-11-14; FAC-04 was not filed into seldon.

## Deviations and open items

- **Rulings numbered under AD-037 and AD-036, as the task says.** Part D extends SEL-041's AD-034 gate record, but its
  two rulings are AD-037-R20 and R21.
- **The AD-036 note was edited twice after its first verify:** once to cite squiddy's DN-062, and once to state
  R29's dual type. Each time its three pending records were removed, made again from the new line ranges, and the note
  was verified again. The final verdict is PASS, event `cc0f1875`.
- **Errata in existing tests.** These are deliberate changes, each proved:
  - `tests/test_station001_project_interpreter.py` pins a check row's keys; every row now has four wall-clock keys.
  - `tests/test_dispatch_serial_transcript.py` was re-recorded. The re-recording equals the old fixture once SEL-043's
    keys and the premise's old wording are restored (`docs/evidence/sel043/transcript_check.py`: `True`; a planted
    change reads `False`).
  - `_gate_phase` first assumed the config named a lease file. `seldon dispatch regate`'s helper test has none, so it
    failed `KeyError`. The marks now do nothing without a lease.
- **The pin records; it does not isolate.** A producer that merges during a consumer's session still changes the code
  under it, as it always could. Isolating that would mean installing producers by version per launch, which no
  consumer does today.
- **A Desktop commit to a producer's primary is under no lease,** before and after this task.
- **The holder also writes its primary during the session:** the inspector commits station records (event-store
  lines) and pushes. AD-037 ADDENDUM 05 section 1 item 2 leaves this out. R17 still holds, because no consumer imports
  a producer's event store (Part A (1)). A consumer that came to read a producer's store live would need the session
  phase to hold it.
- **A parallel supervisor's gate is not shown on the pass lease.** It holds only its worktree lease while gating, so
  `mark_phase` does nothing there and `status` shows no gate progress for it. No repository runs parallel today.
