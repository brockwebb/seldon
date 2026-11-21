# SEL-041: the gate runs what a change touched, the whole suite runs only at declared points, and every gate run is timed and recorded

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-21. Answers hazbrief-mcp's filing `a844c156` (`cc_tasks/2026-11-21_filing_from_hazbrief_the_gate_is_one_command_per_repository_and_ran_in_full_for_a_one_slide_change.md`), on the operator's order of 2026-11-21: "it's rebuilding the whole thing, even for a slide change. We MUST have modular design", built once and used by every project.
**Repo:** seldon (primary). hazbrief-mcp and squiddy are read, never written; Part F files their returns. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-034 (the merge round; decision 3, the re-gate; R16 to R18, the pass record) and its addenda; FRICTION-002 (the Stop gate each session ends on); AD-037 (R1 criteria are checks, R6 stations, R8 `seldon qc chart`); AD-038-R11 (candidacy headers). Number new rulings under AD-034.
**Model:** primary
**Spend:** est. 1.3M tokens. Basis: one measurement across the dispatching repositories, one addendum, a gate planner with two selection sources, its use in two existing call sites, one record type and its chart line, seldon's own slices, two returns. Zero model calls.
**Network:** allowlist: pypi.org, files.pythonhosted.org
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon/commands/dispatch.py`, `seldon/commands/dispatch_worktree.py`, the stop-gate hook, seldon.yaml's `dispatch` block)
**Parts:** A 0.15, B 0.10, C 0.35, D 0.15, E 0.10, F 0.15.
**Premises:**
- premise: seldon's gate is one command | check: grep -q "gate_command:" seldon.yaml
- premise: hazbrief's gate is one command | check: grep -q "gate_command:" /Users/brock/GitHub/hazbrief-mcp/seldon.yaml
- premise: the filing is on main | check: test -f cc_tasks/2026-11-21_filing_from_hazbrief_the_gate_is_one_command_per_repository_and_ran_in_full_for_a_one_slide_change.md

Read the filing first.

## The condition

A project's gate is one shell command (`dispatch.gate_command`), run whole or not at all. hazbrief's went from 12 to 14 minutes (2026-11-11) to 76 to 89 minutes (2026-11-18, 8,321 tests) and ran in full for a one-slide change, one task at a time. seldon's own full suite, which every seldon task runs: 24 minutes on 2026-11-09 (3,307 passed), 27, 41, 39, and 72 under load on 2026-11-12 (3,386 passed). The operator asked hazbrief for slices on 2026-11-12; hazbrief added parallel workers. Nothing in the kit lets a project say "this change touches only this part", nothing times a gate, and nothing warned anyone.

hazbrief's thread proposed writing its own script that picks tests from changed files. That would be the third time a consumer builds kit machinery (the citation resolver and the fetcher in SEL-036 and SEL-037 were the first two). The mechanism is the dispatcher's and is built here once.

## Prior art

Fetched by the Desktop thread on 2026-11-21 (cite as fetched, with URL):

- **Test impact analysis** (Fowler, "The Rise of Test Impact Analysis", https://martinfowler.com/articles/rise-test-impact-analysis.html). A map from each test to the production code it exercises, built by running tests under coverage; on a change, run the tests the map links to the changed code. The page records four things this task must respect: (1) new tests and previously failing tests run unconditionally (Microsoft's implementation, Google's Testar); (2) resource files could not be linked to tests automatically and had to be listed by hand; (3) the saving disappears when a change touches code most tests use; (4) the map needs periodic rebuilding against a reference build. It names Bazel, Buck and Pants, where the same selection falls out of declared build dependencies.
- **pytest-testmon** (https://pypi.org/project/pytest-testmon, 2.3.1, released 2026-11-19, MIT, Python 3.11+): "selects tests affected by changed files and methods", from a dependency database (`.testmondata`) built on a first run. The package page states no limits for xdist, subprocesses or non-Python inputs; Part C measures them.

Found by search and not read (fetch into seldon-biblio through squiddy's path if the allowlist permits, otherwise cite as unread): Memon et al. 2017, "Taming Google-Scale Continuous Testing" (ICSE-SEIP); Gligoric 2015, regression test selection (Ekstazi); Elbaum, Rothermel and Penix 2014 (FSE), test selection and prioritisation in continuous integration.

From seldon's own record: AD-034 decision 3 already runs the re-gate only "when main changed a file the task changed", so selection by changed files is an existing idea in the merge round, applied to whether to gate and never to what the gate runs.

Run `seldon prior-art search` (internal and library arms) before the addendum.

## Rulings to write (Part B, AD-034 addendum; `prior-art verify` passing before C to F)

1. **Two tiers.** A *scoped* gate runs on every task: the tests selected for what the branch changed against main. A *full* gate runs at declared points only: a release or package cut (a command, `seldon gate run --full`, and a task header that asks for it), a cadence the project declares (nightly by default where a dispatcher runs), and whenever selection cannot be trusted (rule 4).
2. **Selection is declared first, measured second.** A project declares slices in `dispatch.gate.slices`: each a name, path globs, and the tests (paths or markers) and other commands (lint) those paths require; a slice may require nothing (`tests: none`, for documents and slides). Where a project opts in, a coverage map (testmon) adds the tests it links to the changed Python. The selected set is the union.
3. **Always run:** tests added or changed on the branch, and tests that failed in the last recorded gate.
4. **Safe default.** A changed path that no slice matches and the map does not know, a change to the gate's own configuration, to a dependency lock, to a `conftest.py`, or a missing or stale map, makes the gate full, and the record says why.
5. **Every gate run is a record** in the event store: tier, reason, tests selected of total, wall seconds, outcome. A full gate that fails a test the last scoped gate on the same change set did not select is recorded as an *escape*. Escapes per full gate is the measure of whether a project's slices are safe.
6. **A project is told.** `seldon verify` and `seldon go` warn (never fail) when a project's median scoped gate over its last ten runs exceeds `dispatch.gate.warn_seconds`, and when a project has a `gate_command` and no slices. `seldon qc chart` gains gate seconds per project per week.
7. **The mechanism is seldon's.** A consumer declares slices and a threshold. No consumer writes selection code.

A project that declares no slices behaves exactly as today, with rule 6's warning.

## What to build

**A. Measure first, read only.** For every repository under `/Users/brock/GitHub` whose seldon.yaml has a `dispatch` block: its gate command, its test count, and the wall time of its last twenty gate or suite runs from whatever it recorded (dispatch logs, RESULTs, evidence files). For hazbrief-mcp's and seldon's last thirty merged tasks: the files each changed, grouped by top-level directory, and the share of the suite a by-directory slice would have selected. Report the table. If the measurement shows a by-directory slice would still select most of a suite for most tasks, say so before building: the saving then depends on the suite's own structure, which is each project's to fix, and the return says that.

**B. The addendum,** as above, amended by what A found.

**C. The planner and its two call sites.** `seldon gate plan [--base main]` prints the tier, the reason, the slices matched, the selected tests and commands; `seldon gate run [--full]` runs them and writes rule 5's record. The merge round's re-gate and the session's Stop gate call it when slices are declared, and `gate_command` remains the full tier's command. Tests first: a documents-only change selects nothing and passes in seconds; a change in one slice selects that slice; an unmatched path, a lock change and a conftest change each go full with the reason; new and last-failed tests are always in; the record is written; an escape is recorded.
The testmon arm is built only if it earns it on seldon's own suite: build the map, then seed twenty single-function changes and record how many times the covering test was selected, and whether the map survives `-n 6` (xdist) and tests that start subprocesses. Any miss, or a map that cannot be built under xdist, and the arm is reported and left out; declared slices ship alone.

**D. seldon first.** Declare seldon's own slices from A's table, with `warn_seconds` set from A's numbers and its basis written beside it. Run this task's own remaining gates through the planner and record scoped against full time.

**E. Records, warning, chart** (rules 5 and 6), with tests.

**F. Returns.** To hazbrief-mcp (`seldon cc return`, first line: nothing here is to be applied until its submission has landed): the slice form with a worked example cut from its own directories and A's table for its suite; that "one full gate before the RESULT on every task" is its own `CLAUDE.md` rule and its own to change to "full gate before the package is cut"; that it writes no selection script; and what A found about its suite's structure (29 replayed briefs, browser tests, two engines), as measurement, with no design for it. To squiddy: how the scoped gate meets its kit pass ledger (AD-034-R16 to R18), as a report of what changed; a task there only if squiddy has something to do.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 1.6M.

## Deliverables

A to F with tests; the addendum and its rulings; A's table; seldon's slices and the before and after times; the returns; `cc_tasks/2026-11-21_SEL-041_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points_RESULT.md`.
