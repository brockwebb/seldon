# RESULT: SEL-041, the gate runs what a change touched, the whole suite runs only at declared points, and every gate run is timed and recorded

**Date:** 2026-11-21. **Branch:** `worktree-splendid-seeking-russell` (not merged by this session; the dispatcher
merges on green). **Task:** `9d9caf94`. **Addenda read:** ADDENDUM 01 (SEL-042's third call site and gate evidence),
carried out below: rulings start at AD-034-R29, the merge gate goes through the planner, R34 decides how a scoped gate
meets AD-034-R26, the record is the one `gate_evidence` names, and the hazbrief return updates HB-217's advice.
Recall used: none. Registration listed eight hits (SEL-004, SEL-006, SEL-024, the `precedes` and AD-030 RESULTs,
AD-034-R18, squiddy SQ-050R and SQ-048R). None was opened. The design came from the filing, the code
(`_merge`, `gate_evidence`, `stop_gate`), AD-034 ADDENDUM 11 and the measurement in Part A.

## In plain terms

- **A project can now say which tests a change needs.** `dispatch.gate.slices` maps paths to the tests and commands
  they require, or to `tests: none`. The gate runs only those (the *scoped* tier). The whole suite
  (`dispatch.gate_command`, the *full* tier) runs when asked (`seldon gate run --full`, or `**Gate:** full` in a task
  header), once a day by default, and whenever the planner cannot vouch for a change: a path no slice names, a change
  to the gate's own settings, a lock or project file, or any `conftest.py`. The record always says why.
- **For a one-slide change that means seconds, not 80 minutes**, once the project declares its slides and records as
  `tests: none`. In seldon, a documents-and-records change now runs 653 tests in 358 s instead of the whole suite
  (3,482 tests, about 82 minutes as the gate runs it, serially).
- **seldon's gate timeout was too short, and that blocks merges on main.** Measuring this showed that seldon's serial
  full gate outlasts the 60-minute gate timeout. Since SEL-042, every seldon task without `check:` lines is gated
  that way at merge, so on main each such merge would time out and be blocked, this task's included. This branch
  raises the timeout to two hours. "For the operator" has the two lines to run on main.
- **Every gate run is recorded and timed** (`gate_run` in the event store): tier, reason, tests selected of the total,
  seconds, outcome, failing files. When a full gate fails a test the last scoped gate on the same change did not
  select, the miss is recorded as an *escape*. Escapes are how a project learns whether its slices are safe.
- **Projects are told.** `seldon verify` and `seldon go` warn (never fail) when a project has a gate command and no
  slices, and when its scoped gates get slow. `seldon qc chart` shows gate seconds per week.
- **What will NOT get faster without each project's own work.** Part A found that both big suites are wired so that
  almost any code change touches almost every test. seldon's `tests/conftest.py` imports the whole CLI, and hazbrief's
  five entry modules import most of its package. So a code change still runs the full suite, in both. That is each
  suite's structure, and it is each project's to change. The kit cannot slice around it.
- **testmon (automatic test selection from coverage) was measured and left out.** It picked the right tests for all 20
  seeded in-process changes. It missed 39 of 41 test files that reach code through `git commit` hooks. That is how
  seldon's dispatcher and hooks are tested.

## Part A: the measurement (`docs/evidence/sel041/README.md`)

Every repository under `/Users/brock/GitHub` with a `dispatch` block:

| repository | gate | tests | recorded full runs | wall seconds |
|---|---|---|---|---|
| seldon | `gate_command`, the whole suite | 3,482 | 19 (11-01 to 11-21) | median 1,680 (1,340 to 4,316) |
| hazbrief-mcp | `gate_command`: two pytest steps and ruff | 8,469 | 20 step-1 runs (11-20, 11-21); HB-194's 5 whole gates | step 1 median 2,228; whole gate 76 to 89 min |
| squiddy | `gate_record` (kit pass, up to 3 seeded runs) | about 2,900 per run | 20 passes | per run 1,418 (10-16) to 3,587 (11-15) |
| aacps-ai-policy | `gate_command` | not collected | 0 | none recorded |
| ai-readiness-kg | no gate command | n/a | n/a | n/a |
| factory | no gate command (AD-034-R26: check-less tasks block `ungated`) | 21 | 2 session runs | 10.7 to 10.9 |

ADDENDUM 01 item 5: no merge in any repository has yet been recorded under AD-034-R26, so there are **zero
`merge_gate` runs** to tabulate; seldon has one recorded re-gate (DISP-001R, 2,572 s). SEL-042's two full runs were
25:40 and 25:51 at `-n 6`.

The last thirty merges of seldon and hazbrief, replayed against slices by top directory, package sub-directory and
module import closure:

| repository | reading | tasks going full (of 30) | 10% of the suite or less | nothing |
|---|---|---|---|---|
| seldon | strict (unnamed paths go full) | 27 | 3 | 3 |
| seldon | every non-code path declared | 26 | 4 | 3 |
| hazbrief-mcp | strict | 23 | 7 | 3 |
| hazbrief-mcp | every non-code path declared | 12 | 17 | 4 |

The three granularities gave identical results in both repositories. The task asked for this to be said before
building, and it was (`docs/evidence/sel041/README.md` section 4): **a by-directory slice still selects the whole suite
for most tasks.** seldon's conftest imports `seldon.cli`, whose closure is the whole package; 75 of its 112 modules
import more than 80% of it. hazbrief's median module is imported, closure included, by 71% of its suite. For hazbrief
the declarable saving lies in its non-code paths (`scripts/`, `fixtures/`, `graphs/`, `corpus/`): 17 of its last
30 tasks would have run 10% of the suite or less.

## Part B: the rulings (AD-034 ADDENDUM 12, prior-art verify PASS, event `cc63b6af`)

`docs/design/AD-034_ADDENDUM_12_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points.md`,
AD-034-R29 to R37, nine register records pending (numbered at merge). Amended by Part A as follows. R30 says that
seldon's code is not sliced, and why. R30 also says a coverage map ships only on a measurement like Part C's.
ADDENDUM 01 item 3 is decided as **R34**. A passing `gate_run` record for the clean tree the session left is
evidence, scoped or full. That includes a scoped gate that selected nothing because every changed path matched a
`tests: none` slice: that slice is a declaration on the record, which is the permission Saltzer and Schroeder's
fail-safe default asks for. A missing check is not such a declaration. A plan with any unmatched path is full under
R32, so a scoped record never stands for an unmatched path. Prior art: Fowler's test impact analysis page and the
testmon package page (both fetched by the Desktop thread), Memon et al. 2017 (catalogued in the library as
metadata only, not read), and Ekstazi and Elbaum et al. (not read: this task's network allowlist is pypi only).

## Part C: the planner and its call sites

- `seldon/core/gate_plan.py`: `dispatch.gate` is validated at load. A slice with no `test_command`, slices with no
  `gate_command`, an unknown key, or a coverage map other than `none` are each refused. The module also holds the
  planner, the runner (steps share one deadline, and pytest's exit 5 on a marker step passes), the record with its
  escapes, the evidence lookup, the warnings and the weekly chart.
- `seldon gate plan [--base main] [--full] [--task <id>] [--json]` and `seldon gate run [...]`
  (`seldon/commands/gate.py`). The record goes to the primary checkout's store.
- All three call sites go through the planner. The merge round's re-gate (`call_site: regate`) and its evidence gate
  (`merge_gate`) do so whether or not slices are declared. Without slices the plan is full (`no_slices`) and runs
  `gate_command` exactly as before; the gate log is unchanged byte for byte. The Stop gate
  (`dispatch_stations._stop_gate_plan`) runs only with slices declared. It runs a scoped plan and blocks a red one
  like a failing check, under the same ceiling and no-progress rules. A full plan is recorded `deferred` to the merge
  round, which has the gate's timeout. A tree that already has a passing record is not gated again. `gate_evidence`
  gains the `gate_run` source, after a kept regate and before a Stop gate with checks.
- Tests (`tests/test_sel041_gate_plan.py`, 32; `tests/test_sel041_gate_call_sites.py`, 5), the task's list:
  - a documents-only change selects nothing and passes in seconds;
  - a change in one slice selects that slice only;
  - an unmatched path, a lock, a conftest and a change to the gate's configuration each go full, with the reason;
  - changed tests and last-failed tests always run;
  - the record is written;
  - an escape is recorded, and a failure the scoped gate did run is not counted as one;
  - a passing clean record is evidence, in its place in the order;
  - a red scoped gate blocks the Stop;
  - at the dispatcher level: a documents-only task merges on a scoped `merge_gate` while the full `gate_command` is
    `false`, an unmatched path makes it full and red, a sliced command runs, and a project without slices records
    `no_slices` with the old log.
- **The testmon arm was measured and left out** (`docs/evidence/sel041/testmon/README.md`). The map builds under
  `-n 6`: 52:47, 3,476 passed, and the 5 failures are the known load flakes and pa002. For the twenty seeded
  single-function changes, testmon's selections were all right. One "miss" was a function its only test replaces
  with a fake, so not selecting that test was correct. The hook seed (`seldon hooks pre-commit`, which runs inside
  `git commit`) was selected for 2 of the 41 test files that reach it that way.
- The serial transcript fixture gains the `gate_run` line and four gate keys. An erratum is in the test's docstring,
  and the mechanical proof is `docs/evidence/sel041/transcript_check.py` (`True`).

## Part D: seldon first

seldon's `dispatch.gate` (`seldon.yaml`) holds five slices: the event store (`tests: none`; no test reads the real
store), task records, documents, ledgers and graphs. Each lists the test files that read the real files under its paths
(`docs/evidence/sel041/tools/real_reads.py`, `records_slice.py`). It also sets `test_command` at `-n 4`, nightly
cadence, and `warn_seconds: 600`, whose basis is written beside it: a third of the 1,680 s full median. Code is left
unmatched on purpose (Part A, section 3).

Scoped against full, measured on this task:

| gate | change | tests | wall seconds | record |
|---|---|---|---|---|
| scoped (`gate run`) | a design note, a task file, a handoff and the event store, in a `/tmp` clone of this branch | 653 (26 of 199 files) | 358 | `42522c22` (clone's store) |
| full (`gate run --full`, the serial `gate_command`) | this branch (code: full under R32, 13 reasons, the first `requested`) | killed at 73% of 3,482 | **3,600, timed out** | `ee863fab` (`outcome: timeout`) |
| full, at `-n 6` (pytest directly, for verification) | this branch | 3,505 passed, 7 failed, 7 skipped | 1,731 | not a gate run |

The scoped run's clone had no passing full gate on record, so one was seeded into the clone's store to stand for the
nightly full gate. Without it the cadence makes the first gate full, which is R29 working. This task's own remaining
gates are full: it changes `seldon/` and `seldon.yaml`'s gate keys.

**Found while measuring: seldon's full gate outlasts its own timeout.** `dispatch.gate_timeout_s` was the 3,600 s
default, "no measured basis" in the code. The serial `gate_command` was killed at 3,600 s with 73% done (load average
7 to 8), so about 82 minutes whole; SEL-024 measured 70 minutes serial on 2026-11-06. Since AD-034-R26 (SEL-042,
merged today) every check-less seldon task's merge runs that command, so on main each such merge is `regate_red` by
timeout. Main has not hit it yet: SEL-042 merged on the code before R26, and no seldon task has merged since. This
branch sets `gate_timeout_s: 7200` in its own commit (`ae6c38d`, hazbrief's value for its 76-to-89-minute gate),
with the basis beside it. **This task's own merge runs on main's code and main's 3,600 s**, so it will probably be
blocked `regate_red`. "For the operator" has the recipe.

## Part E: records, warning, chart

- One record, not two (ADDENDUM 01 item 4). The merge's `gate` and its `gate_evidence.gate` name the `gate_run`
  record by id, and escapes are counted from the same records.
- `seldon verify`'s new check **Gate** and `seldon go`'s **Gate** line warn about a gate command with no slices
  (seldon's own warning, until this branch merges), and about a scoped median over `warn_seconds`.
- `seldon qc chart` gains "gate seconds per week": n, median and total per tier, red runs and escapes.

## Part F: the returns

- **hazbrief-mcp:** filed with `seldon cc return` (`--answers seldon:<the filing>`), from the section below.
- **squiddy:** a report only (below). squiddy has nothing to do, so no task is filed there, as the task allows.

## For the operator

**Incident: on main, a check-less seldon task's merge gate times out.** The full suite run serially takes about 82
minutes, and main's gate timeout is 60. This task is probably the first to hit it (Part D). If `seldon go` shows
SEL-041 (`9d9caf94`) blocked `merge_blocked` with reason `regate_red` and `timed_out: true`, run the two steps below.
If it merged, run step 1 only.

1. Shell, in the primary checkout, on `main`. This takes this branch's timeout commit alone. It is the same patch as
   on the branch, so the branch's rebase drops it cleanly:

   ```
   cd /Users/brock/GitHub/seldon && git cherry-pick ae6c38d
   ```

2. Only if SEL-041 was blocked, in the same shell, after step 1. Nothing re-merges a `regate_red` block in place, so
   the task goes back through a launch; the kept worktree holds the finished work and its RESULT:

   ```
   seldon dispatch redrive 9d9caf94
   ```

Two more things to know:
1. Once this merges, seldon's next gate is full (`cadence_due`: no passing full gate is recorded on main yet). After
   that, documents-only tasks gate on their slices.
2. aacps-ai-policy and hazbrief-mcp will see the new "no slices" warning in `seldon go` until they declare slices.
   factory and ai-readiness-kg have no gate command; adding slices there is refused until they declare one.
   aacps-ai-policy's gate timeout is also the 3,600 s default, with no run recorded to measure it.

## For hazbrief-mcp

Nothing here is to be applied until hazbrief's submission has landed. Then, in order:

1. **Declare slices; write no selection script.** The kit now plans the gate (`seldon gate plan` shows what a branch
   would run). A worked example cut from hazbrief's own directories, for `seldon.yaml`'s `dispatch` block:

   ```yaml
   gate:
     test_command: >-
       uv run pytest -q -p no:cacheprovider -n 3 --dist loadgroup -m 'not slow' {tests}
     full_every_s: 86400
     warn_seconds: 900
     slices:
       - name: records
         paths: ["cc_tasks/**", "handoffs/**", "seldon_events.jsonl", "state/**"]
         tests: none
       - name: benchmark
         paths: ["scripts/benchmark_state.py", "scripts/benchmark_state.yaml", "scripts/benchmark_table.py",
                 "scripts/benchmark_table.yaml"]
         tests: [tests/test_hb212_benchmark_state.py, tests/test_hb214_benchmark_table.py,
                 tests/test_hb209_benchmark_numbers.py, tests/test_hb203_benchmark_words.py]
       - name: agents_md
         paths: ["scripts/agents_md.py", "scripts/agents_md.yaml", "AGENTS.md"]
         tests: [tests/test_hb209_agents_md.py]
       - name: gate_ledger
         paths: ["scripts/gate_ledger.py"]
         tests: [tests/test_gate_ledger.py]
         commands: ["uv run ruff check scripts/gate_ledger.py"]
       - name: deck
         paths: ["scripts/build_deck.py", "scripts/deck_screenshots.py"]
         tests: [tests/test_deck.py]
   ```

   Each `tests:` list is hazbrief's to check: which tests read which files. seldon found its own lists with a scan
   of literal paths and repository-root joins (`seldon/docs/evidence/sel041/tools/real_reads.py`). A slice that
   matches `src/**` or `**/*.py` with only a lint command would mark every code change as vouched for. Keep commands
   on narrow slices. `docs/**` may be `tests: none` only if no test reads the real documents.
2. **What Part A found about hazbrief's suite** (measurement only, no design for it). Of hazbrief's last 30 merged
   tasks, 23 would still go full with nothing declared. With its non-code paths declared, 12 go full and 17 run 10%
   of the suite or less. Every task that changed `src/` (12 of 30) selects the whole suite at every static
   granularity. The median module is imported, closure included, by 71% of the suite, and five entry modules
   (`hazbrief.command`, `hazbrief.brief.cli`, `.entry`, `.start`, `.web`) import more than 80% of the package. The
   suite also holds 29 replayed briefs, headless-Chrome tests and two dispersion engines. Step 1 took a median of
   2,228 s over its last 20 runs; HB-194 timed whole gates at 76 to 89 minutes.
3. **"One full gate before the RESULT on every task" is hazbrief's own rule**, in its `CLAUDE.md` and repeated in its
   task files. It is hazbrief's to change, for example to "a full gate before the package is cut". The full tier is
   still one command: `seldon gate run --full`, or `**Gate:** full` in the packaging task's header.
4. **How this changes HB-217's advice.** HB-217 said that a task whose Parts declare no `check:` gates twice (the
   session's own full run, then the round's `merge_gate`), and that a `check:` per Part or `dispatch.gate_record`
   avoids it. Both still hold. A third way now exists: with slices declared, the session's Stop gate runs the scoped
   plan, and its passing `gate_run` record is the merge evidence (AD-034-R34). A plan that is full is left to the
   round, which runs `gate_command` once. Drop the session's own full run (item 3), and each task gates once: scoped
   when its slices vouch for it, full when they do not. A change whose every path matches a `tests: none` slice (a
   slide, a document) passes in seconds, and that counts as evidence, because the slice is a declaration on the
   record.

## For squiddy

A report of what changed. squiddy has nothing to do. squiddy declares `dispatch.gate_record` (its kit pass ledger,
AD-034-R16 to R18) and no `gate_command`. Its declared pass record stays first in the merge round's evidence order
(AD-034-R34), and a scoped gate never writes or replaces a kit pass. Every gate the round runs is now recorded as a
`gate_run`, and squiddy's kit pass is not such a run, so squiddy's own records are unchanged. If squiddy ever declares
slices, the loader refuses them until it also declares a `gate_command`, because the full tier needs a command to run.

## Deviations and open items

- The task asked for the re-gate and the Stop gate to "call [the planner] when slices are declared". The re-gate and
  the merge gate call it always and plan `no_slices` (full) without slices, so that R33's record covers every gate run.
  The command, its log and its outcome are as before.
- R29's cadence promotes the next gate to full rather than starting a nightly job. A full gate then runs on a real
  change set, and no new daemon is needed. The addendum says so.
- The full suite at `-n 6` (Part D, 28:50): 3,505 passed, 7 failed. One was this branch's: `test_verify_event_log`
  counts verify's checks, and the Gate check is the 23rd. That is fixed and passes. Four are the known ones on main:
  `test_pa002_release_resolve` (library drift), and the `test_sel024_gate_record` lock_wait,
  `test_dispatch_parallel` two_disjoint and `test_friction002_auto_mode` classifier-breaker load flakes. Two pass
  when run alone (`test_dispatch_parallel::test_union_merge_of_two_event_appends_is_valid`,
  `test_sel040_interrupted_session_resumed::test_the_hb189_tail_is_interrupted_not_blocked_for_a_person`). Earlier
  runs in this session under heavier load also failed `test_dispatch_parallel`'s killed_supervisor and
  exclusive_task_waits tests. Each passes alone; the exclusive-task test was re-run alone on this code and passed.
