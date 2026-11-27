# RESULT: SEL-055. The full suite moves off the merge path to a schedule on main, a red main closes the merges that can change a test, and lane branches get a stated rule

**Task:** `cc_tasks/2026-11-27_SEL-055_the_gate_runs_what_a_change_can_break_and_no_queue_waits_an_hour_for_a_one_line_change.md`
(`67b23ffd`). **Branch:** `worktree-ethereal-enchanting-valiant`. This session did not merge, push or complete the
task; the dispatcher merges on green.
**Addenda read:** ADDENDUM 01 (lane merges are a new caller of the merge gate). Its three items are answered below
under "ADDENDUM 01".
**Decisions:** AD-034 ADDENDUM 13
(`docs/design/AD-034_ADDENDUM_13_the_full_suite_runs_on_main_on_a_schedule_and_its_red_closes_the_merges_that_can_change_a_test.md`),
rulings AD-034-R38 to R40, three pending register records. `seldon prior-art verify` passed before the code commit
and again after R39 was amended.
**Evidence:** `docs/evidence/sel055/README.md` (tools, data, the seeds' protocol and its deviations).

Recall used: none. I opened none of the eight recall hits. The inputs were the task file, its addendum, the five
filings, hazbrief's HB-230 RESULT, factory's testmon evaluation, SEL-041's RESULT and AD-034 ADDENDUM 12.

## In plain terms

- **The full suite no longer runs as part of some task's merge just because a day has passed.** Under SEL-041 the
  daily full run was attached to whichever task merged next. SEL-051, whose only change is its own RESULT file, paid
  the full suite twice (1,900 s and 3,094 s), and both runs were red on tests it never touched. Now, where a project
  declares slices, the dispatcher runs the full suite on main itself, in a fresh checkout. It does so on an idle pass
  once a day, or before a launch once two days have passed. `seldon gate main` runs it by hand.
- **A red full run on main stops the merges that could change a test, and says so.** It rings `notify` once, opens
  one `main_red` Issue, and `seldon go` shows it. While main is red, every merge that selects any test also has to
  pass the tests that failed on main. A fix can merge; most other changes cannot. A change whose every path the
  project has declared as touching no test (a `tests: none` slice) still merges, because it cannot change the result.
  The closure ends when a scheduled run passes, or when a branch merges on a passing full gate.
- **Lane branches (factory's OODAs) follow the same rule, now written down.** The paths a lane may write are not
  automatically treated as touching no test: tests do read `cc_tasks/` (3 test files in seldon, 39 in hazbrief).
  A project that runs a lane declares a slice for those paths. `seldon verify` and `seldon go` warn until it does.
  The gate record and the merge record say "lane".
- **A one-line code change still runs the whole suite, in seldon and in hazbrief.** No safe way to select tests for
  code exists in either suite yet. testmon missed tests reached through `git commit` hooks (seldon, SEL-041) and
  through caches, subprocesses and import-time code (hazbrief, HB-230). Static imports select everything, because
  seldon's conftest imports the whole CLI. This task removes the full suite only from changes that are not code.
  Changes that are code keep it.
- **Measured.** Of seldon's last 20 merged tasks, 18 change code and run the full suite (2,408 s); 2 are scoped
  (430 s and 638 s). Of hazbrief's last 20, 14 change code, 1 is scoped (about 267 s against 2,677 s), and 5 run the
  full suite only because nobody has declared which tests read `docs/evidence/**`.
- **Seeded breaks.** hazbrief caught 5 of 5. seldon caught 3 of 5 under the slices on main: two real files that tests
  read were missing from their slices. This branch adds both readers, and with them seldon catches 5 of 5. Until it
  merges, main's slices still have those two holes.
- **seldon main's full suite was red on two tests, and one is fixed here.**
  `test_sel052_held_alarm` failed because it read leftover tasks from an earlier test in the same Neo4j test
  database. I reproduced that in one process and fixed it by giving the test a clean database. The other,
  `test_union_merge_of_two_event_appends_is_valid`, is the known intermittent failure (Issue `88c9f4d8`) and is not
  touched here.

## Part A: what exists, and the decision

**Where SEL-041's work is.** All of it is on main. SEL-041 (`9d9caf94`) was blocked `regate_red` by its own merge's
3,600 s timeout, as its RESULT predicted. SEL-045 (`09520bb0`) was filed to land the kept branch and was itself
blocked `regate_red`. SEL-045R (`8315cc7a`, merged 2026-11-24T22:27Z) replayed both branches' commits. AD-034
ADDENDUM 12's records R29 to R37 are numbered (00372 to 00380), and `seldon gate plan|run` and
`seldon/core/gate_plan.py` are on main. hazbrief took SEL-041's return as HB-218R, merged 2026-11-25. So nothing is
left to land or replace. The graph's `superseded` on SEL-041 is its state after the block, and SEL-045R overtook it.

**The decision, and what the evidence corrected** (AD-034 ADDENDUM 13):

| the coordinator's decision | ruling | correction from the evidence |
|---|---|---|
| a project declares a selected gate for the merge round | R30 already (SEL-041) | none; a declaration's holes are found by seeds (Part B) |
| the full suite as a scheduled run | **R38** | the cadence (R29) was a promotion of the next task's gate; it is withdrawn, because SEL-051 paid for main's drift twice |
| a red scheduled run stops the project's merges and raises it | **R39** | "stops" means "closes to every change that can change a test": a selecting plan must also pass the red run's failed files, so a fix can merge; a plan whose every path is declared `tests: none` is not closed (factory's item 3; tree closure's own purpose). R31's "last recorded gate" excludes scheduled runs, or the closure would catch inert branches too (found by this task's tests) |
| a change the selector cannot classify runs the full suite | R32 already | none |
| the record says which gate ran and why | R33 already | the record gains `main_red` (the closure applied) and `lane` |
| (ADDENDUM 01) a lane branch is classifiable | **R40** | the lane's `writes` are not test-inert (tests read `cc_tasks/`), so the slices classify a lane's paths; the project declares a slice for them, and is warned until it does |

Prior art: the library holds no software-testing source on these terms. The failed search is kept as a library
receipt in the note. Cited without reading, because the task's Network line is `none`: Rothermel and Harrold 1997
(safe regression test selection); Google TAP (Memon et al. 2017), as squiddy DN-043 read it under a web receipt
(selection at submission, the whole suite on a batched schedule); Bazel's affected targets; and tree closure on a
red continuous build (Chromium's tree status).

Acceptance: `git log --oneline main..HEAD -- docs` lists `6240d5d` and later commits.

## Part B: built and measured

### Built

- `seldon/core/gate_plan.py`:
  - `plan` no longer reads the cadence. It takes `closure` (R39) and judges whether a plan is inert on the branch's
    own paths.
  - New functions: `scheduled_due` (idle, overdue, and a merge under a red main), `main_red`, `merged_after`,
    `scheduled_plan`, `closure_admits` (which R26 evidence stands under a closure), and `lane_uncovered` with its
    warning.
  - New keys `full_overdue_s` (172,800 s, no measured basis) and `scheduled_worktree` (`.seldon/gate_main`).
  - New call site `scheduled`. Records carry `main_red` and `lane` only when they hold, so a record from a project
    that uses neither is unchanged.
- `seldon/commands/dispatch_gate.py` (new) runs the scheduled gate:
  - checks out main detached at `scheduled_worktree`, links `worktree_links`, runs `gate_command` under
    `gate_timeout_s`, records it and removes the checkout;
  - holds a non-blocking lock against a second run;
  - on red, notifies once per closure and opens one `main_red` Issue; on a pass that ends a closure, notifies
    `main_green`.
- `seldon/commands/dispatch.py` (serial pass) and `dispatch_worktree.pass_parallel` call it with no session in flight,
  and commit its record.
- `dispatch_worktree._merge` reads the closure once per round and passes it to the re-gate and the evidence gate. It
  drops evidence that skipped the closure. The merge record carries `main_red` and `lane`.
- `seldon gate main` (new). `seldon gate plan|run` apply the closure, so a session's own record stands as evidence.
  `seldon go` prints **Main is RED** while the closure holds.
- `seldon.yaml`:
  - the `full_every_s` comment now describes the schedule;
  - `task_records` gains `tests/test_criteria_marked.py` and `documents` gains `tests/test_qc_chart.py` (the two
    seeds' misses).
- `seldon/core/issue_utils.py` adds the `main_red` issue type.

### Tests

- `tests/test_sel055_scheduled_gate.py`, 22 tests, all passing. The schedule's rules; the closure's rules (a
  selecting plan runs the red files, an inert plan is not closed, a red run with no named file goes full); which
  evidence stands; the record fields; the lane warning; and the scheduled run in a real git repository (checkout,
  record, no leftover checkout, one ring per closure, `main_green`, the lock). At the dispatcher, on scaffold
  projects with Neo4j:
  - an idle pass runs the scheduled gate, and a red one opens one `main_red` Issue and is committed;
  - under a red main, a branch that selects tests is blocked, and a branch that fixes the failing file merges;
  - an inert branch merges through the closure;
  - **a lane branch with no evidence merges on its selected gate, and both records name the lane** (ADDENDUM 01
    item 1);
  - `seldon go` says main is red.
- `tests/test_sel041_gate_plan.py`: the cadence test now asserts R38, with the amendment cited in it, and the CLI
  test's first plan is scoped. 32 of 32 pass.
- `tests/test_sel052_held_alarm.py`: the through-the-pass test cleans its database. It reproduced red in one process
  after `tests/test_dispatch_stuck_and_journal.py`, and passes 25 of 25 in that order with the fix.
- **The full suite on this branch at `322a25f`** (`-n 6`, `/tmp` clone, load 130 to 160): `1 failed, 3668 passed,
  2 skipped in 3054.75s`. The failure is `test_dispatch_parallel.py::test_union_merge_of_two_event_appends_is_valid`,
  the known intermittent (Issue `88c9f4d8`). After that commit came `seldon go`'s line, the slice correction and its
  test. Run afterwards: `test_dispatch_parallel_held`, `test_go`, `test_sel041_gate_plan`,
  `test_sel055_scheduled_gate`, `test_verify_event_log`, `test_criteria_marked` and `test_qc_chart`: 121 passed. The
  serial transcript test passed in the full run, so the fixture was not re-recorded (ADDENDUM 01 item 3).

Acceptance: `git log --oneline main..HEAD -- tests` lists `322a25f` and `b427688`.

### Measured (`docs/evidence/sel055/README.md`)

**The last 20 merged tasks, under today's declarations** (planned from main's reflog `prev_main..tip`, read-only
clones):

| repository | full: code | full: undeclared non-code only | scoped | selected gate, summed | full gate on every merge, summed |
|---|---|---|---|---|---|
| seldon | 18 | 0 | 2 (26 and 29 of 205 files; 430 s and 638 s measured) | 44,541 s | 48,160 s |
| hazbrief-mcp | 14 | 5 (`docs/evidence/**`, `CLAUDE.md`, `docs/submission/**`) | 1 (HB-229, 39 files, est. 267 s) | 51,130 s | 53,540 s |

The full gates were 2,408 s for seldon (this task's baseline at `-n 6`, load 50 to 60) and 2,677 s for hazbrief (the
median of its 9 passing full records). Estimates use a junit's per-file seconds. They check against seldon's two
measured scoped gates: 462 s estimated against 430 s measured, and 735 s against 638 s. No lane merge is in either
list: neither repository declares a lane.

**Seeded breaks** (protocol in `tools/seeds.py`, written before the first run). A seed counts only if its reader test
passes unseeded and fails seeded.

| repository | caught | misses |
|---|---|---|
| seldon, slices as on main | 3 of 5 (S3 task header 157 s, S4 convention doc 896 s, S5 code: full) | **S1** (QC-001's task file, read by `test_criteria_marked.py`), **S2** (QC-002's evidence YAML, read by `test_qc_chart.py`) |
| seldon, this branch's slices | 5 of 5 (S1 94 s, S2 425 s) | none |
| hazbrief-mcp, slices as on its main | 5 of 5 (H1 event store, H2 task addendum, H3 task file: `records`; H4 `scripts/gate_ledger.py`; H5 `src/`: full) | none |

**The misses stop the rollout of seldon's slices as main declares them,** as the task's rule says. The slices have
been live since SEL-041, so this branch corrects them instead of withdrawing them. An independent scan for tests that
join the real repository root to a sliced directory finds exactly those two readers and no other. Deviations from the
protocol are in the README: hazbrief's tests ran on HB-230's scratch environment; its scoped gates were not run to
their end once the failing reader was selected, because a 39-file gate at load 150 progressed about 1% a minute; and
two void hazbrief seeds were replaced.

## ADDENDUM 01

1. **Lane branches.** R40 states the rule, and the scenario test above covers the lane path. No lane merges exist in
   either repository's last 20.
2. **`merge_wait_s` beside the measured gates.** The default is 14,400 s.

   | gate | seconds |
   |---|---|
   | seldon full gate | 2,408 measured; 1,900 to 5,788 on record |
   | seldon scoped gate | 94 to 942 under load; 430 and 638 on record |
   | hazbrief full gate | median 2,677; 2,155 to 4,069 on record |
   | hazbrief scoped gate | about 267, estimated |
   | factory full gate | about 11 |

   The longest gate on record is 40% of the default. A lane task behind a build also waits for the build's session,
   which is not measured here. Nothing supports a new value, so the default is unchanged (AD-038-R40 owns it).
3. **The serial transcript fixture** was not re-recorded. Its test passes: the scheduled run happens only where slices
   are declared, and the transcript's project declares none. The known flake failed in both full runs and is not
   counted as a selection miss.

## Not done, and why

- **`test_union_merge_of_two_event_appends_is_valid` still fails intermittently** (Issue `88c9f4d8`, `main_kept_moving`
  after 3 attempts). It failed in both of this task's full runs. It is a merge-round race and not this task's work.
  Once this merges, a red scheduled run caused by it opens a closure. That is the honest signal: merges that select
  tests then also run `tests/test_dispatch_parallel.py`, which usually passes, and the next scheduled run usually
  lifts the closure.
- **I did not run `seldon gate main` on the primary checkout.** It would hold the machine for about 40 minutes at
  this load, and the code is not on main yet. After the merge the dispatcher's first idle pass runs the schedule
  once it is due: the newest full pass on record is SEL-054's of 2026-11-27T12:42Z, so the run is due a day after
  that.
- **hazbrief's `docs/evidence/**` readers are not declared.** More than 60 of its test files read that directory, so
  listing them is hazbrief's own declaration (HB-230 left `docs/` unmatched).
- **Seldon's own code still runs the whole suite** (R30). Making that cheaper means changing how the suite is built
  (conftest imports, hooks reached through `git commit`), which belongs to its own task.

## For the consumer

Two returns, one per consumer, each written from its section below and filed with `seldon cc return`:

- hazbrief-mcp answers hazbrief's gate filing `a844c156` (2026-11-21) and its HB-218 filing `f478f2ea`
  (2026-11-24, question 4: HB-230 measured testmon on hazbrief's suite).
- factory answers factory's filings `3619898e` (2026-11-27, seldon main's full gate is red) and `a8863e12`
  (2026-11-24, the merge gate holds every queue).

hazbrief's filing `1e367024` (a Part's bare check line, a blocked merge completed ungated, a lease wait) is not
answered here. Only its third item touches the gate's time, and its first two are other work.

## For hazbrief-mcp

When seldon's dispatcher merges SEL-055, hazbrief's gate changes in three ways with no edit to hazbrief. Seldon
decisions: AD-034-R38 to R40 (`seldon/docs/design/AD-034_ADDENDUM_13_...md`); evidence:
`seldon/docs/evidence/sel055/README.md`.

1. **The daily full suite moves off your merges.** A scoped merge never runs the whole suite because a day has passed
   (`cadence_due` is gone). Your dispatcher instead runs `dispatch.gate_command` on main in a fresh checkout
   (`.seldon/gate_main`, already covered by your `.seldon/` ignore line). It runs on an idle pass once a day has passed
   since the newest full gate, or before a launch once two days have. To run it by hand: `seldon gate main`.
2. **A red full run on main closes the merges that can change a test.** You get one `notify`, one `main_red` Issue,
   and a **Main is RED** line in `seldon go`. While it holds, every merge whose plan selects a test also runs the test
   files that failed on main, so only a fix, or a change those files still pass on, merges. A change whose every path
   matches a `tests: none` slice still merges. The closure ends when a scheduled run passes or a branch merges on a
   passing full gate.
3. **Nothing new to declare.** The defaults are `full_every_s: 86400`, `full_overdue_s: 172800` and
   `scheduled_worktree: .seldon/gate_main`, all under `dispatch.gate`. Set them only to change them.

**What was measured on a read-only copy of your main (`1a92c283`), with your slices as declared:**

- Of your last 20 merged tasks, 14 change code and run the full suite (median 2,677 s on record). 1 (HB-229) is
  scoped: 39 of 200 files, about 267 s estimated. 5 go full only because no slice names their non-code paths:
  HB-224, HB-226, HB-230 and HB-240 (`docs/evidence/**` alone), and HB-225 (`CLAUDE.md`, `docs/decisions`,
  `docs/submission`).
- More than 60 of your test files read `docs/evidence`. A slice per evidence directory naming its readers would make
  those 5 scoped. A blanket `docs/evidence/**` slice would select a large share of the suite. HB-230 left `docs/`
  unmatched; this measurement does not change that.
- Five seeded breaks, all caught: three in `records` (the event store, a task addendum, a task file), one in
  `scripts/gate_ledger.py`, and one in `src/`, which plans full. No miss.
- HB-218's question 4 was answered by your own HB-230: testmon is not safe on your suite. Keep `coverage_map: none`.

### Acceptance

- `check: sh -c "seldon gate --help | grep -q 'main '"` passes.

## For factory

When seldon's dispatcher merges SEL-055, the following holds. Decisions: AD-034-R38 to R40
(`seldon/docs/design/AD-034_ADDENDUM_13_...md`); evidence: `seldon/docs/evidence/sel055/README.md`.

1. **Filing `3619898e`, item 3 (should a RESULT-only branch pay a cadence-due full gate): no, and it no longer
   does.** The cadence is off the merge path (R38). SEL-051's branch changes only `cc_tasks/..._RESULT.md`, so it
   plans `scoped: task_records`: four test files, 94 to 157 s for that slice in this task's seeds under load. The
   whole suite runs on seldon's main on a schedule. Redrive SEL-051 after this merges.
2. **Item 1 (make main's full gate green for the two ids).**
   `test_sel052_held_alarm::test_a_merge_blocked_task_rings_notify_with_its_reason_and_age` is fixed on this branch.
   It read leftover tasks from an earlier test on the same xdist worker, because its module never cleaned the test
   database. `test_union_merge_of_two_event_appends_is_valid` is not fixed: it is the known intermittent (Issue
   `88c9f4d8`) and failed in both of this task's full runs.
3. **Item 2 (say when main's full gate has passed once): not yet.** This task's last full run on the branch had one
   failure, the intermittent above. After the merge, seldon's dispatcher reports it itself. A red scheduled run rings
   `notify` (`main_red`), opens a `main_red` Issue and shows **Main is RED** in `seldon go`. The next pass rings
   `main_green`.
4. **Filing `a8863e12` (the merge gate holds every queue).** What this changes: no task pays the daily full suite at
   its merge, and seldon's full suite runs on main on an idle pass. What it does not change: a seldon change to
   package code, `tests/conftest.py` included, still runs the whole suite, measured at 2,408 s at `-n 6` under load
   50 to 60. That is above F-027's 30 minutes, and about 26 minutes on a quiet machine (SEL-049). No safe way to
   select tests for code exists in seldon's suite (SEL-041's testmon measurement), so F-027 item 1's target is not
   met by this task.
5. **Your lane.** Factory declares no `dispatch.gate.slices`, so every gate it runs is full (about 11 s) and it has
   no scheduled run. That is fine at 11 s. If factory declares slices later, it should declare one for the lane's
   `writes`; `seldon verify` warns until it does (R40).
6. **`merge_wait_s`** (14,400 s default) against the measured gates: seldon full 2,408 s (1,900 to 5,788 on record),
   hazbrief full median 2,677 s (up to 4,069), factory about 11 s. The default is unchanged.

### Acceptance

- `check: sh -c "seldon gate --help | grep -q 'main '"` passes.
