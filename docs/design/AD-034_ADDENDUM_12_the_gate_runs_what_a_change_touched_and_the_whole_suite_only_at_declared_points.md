# AD-034 ADDENDUM 12: the gate runs what a change touched, the whole suite runs only at declared points, and every gate run is timed and recorded

**Date:** 2026-11-21. **Status:** Accepted. Implemented by SEL-041
(`cc_tasks/2026-11-21_SEL-041_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points.md`
and its ADDENDUM 01), answering hazbrief-mcp's filing `a844c156`
(`cc_tasks/2026-11-21_filing_from_hazbrief_the_gate_is_one_command_per_repository_and_ran_in_full_for_a_one_slide_change.md`)
on the operator's order of 2026-11-21 ("We MUST have modular design"). **Extends:** AD-034 decision 3 (the re-gate) and
AD-034-R26 (gate evidence) with a second tier and a new evidence source. Nine new rulings, AD-034-R29 to R37.
**Code:** `seldon/core/gate_plan.py` (the planner, the runner, the record, the warnings); `seldon/commands/gate.py`
(`seldon gate plan|run`); `seldon/commands/dispatch_worktree.py` (`_gate`, `gate_evidence`, `_merge`);
`seldon/commands/dispatch_stations.py` and `seldon/core/stations.py` (the Stop gate); `seldon/commands/verify.py`,
`seldon/commands/go.py`, `seldon/commands/qc.py` (the warning and the chart line).
**Tests:** `tests/test_sel041_gate_plan.py`, `tests/test_sel041_gate_call_sites.py`.

## 1. Evidence

SEL-041 Part A (`docs/evidence/sel041/README.md`, scripts in `docs/evidence/sel041/tools/`) measured every repository
under `/Users/brock/GitHub` with a `dispatch` block:

1. **What a gate costs.** seldon's gate is its whole suite (3,482 tests): 19 recorded full runs from 2026-11-01 to
   11-21, median 1,680 s (1,340 to 4,316). hazbrief's is two pytest steps and ruff (8,469 tests): HB-194 timed five
   gates at 76 to 89 minutes; its last twenty step-1 runs took a median of 2,228 s. squiddy's kit pass runs up to three
   seeded runs of about 2,900 tests, each 1,418 s on 2026-10-16 and 3,587 s on 2026-11-15. factory and ai-readiness-kg
   declare no gate command; aacps-ai-policy declares one and has recorded no run. No merge in any repository has yet
   been recorded under AD-034-R26 (`gate_evidence`), so there are no `merge_gate` runs to time yet.
2. **What a slice would have selected.** The last thirty merges of seldon and of hazbrief, replayed against three
   static granularities (top directory, package sub-directory, module import closure): with every path no slice names
   going full, 27 of seldon's 30 and 23 of hazbrief's 30 go full at every granularity; 3 in each select nothing
   (documents only). With hazbrief's non-code paths (`scripts/`, `fixtures/`, `graphs/`, `corpus/`) declared, 12 of 30
   go full and 17 of 30 select 10% of the suite or less.
3. **Why the granularities agree.** seldon's `tests/conftest.py` imports `seldon.cli`, whose import closure is the
   whole package, and 75 of its 112 modules import more than 80% of it. hazbrief's median module is imported (with its
   closure) by 71% of the suite, and five entry modules import more than 80% of the package. A change to either
   package's code selects the whole suite by static imports: Fowler's third caveat below, met in both suites.

## 2. Prior art

### External

- **Test impact analysis** (M. Fowler's site, "The Rise of Test Impact Analysis",
  https://martinfowler.com/articles/rise-test-impact-analysis.html, fetched by the seldon Desktop thread on
  2026-11-21). A map from each test to the code it exercises, built by running tests under coverage; on a change, run
  the tests linked to the changed code. Four points are adopted as rulings: new and previously failing tests run
  unconditionally (R31, after Microsoft's implementation and Google's Testar as the page reports them); files a map
  cannot link (resources, configuration) are listed by hand (R30's declared slices); the saving disappears when a
  change touches code most tests use (evidence 3, said to each project rather than engineered around); the map needs
  periodic rebuilding against a reference build (R29's cadence and R32's stale map). The page's build-system route
  (Bazel, Buck, Pants: selection from declared dependencies) is what R30's slices are, declared per path instead of
  per build target.
- **pytest-testmon** (https://pypi.org/project/pytest-testmon, 2.3.1, released 2026-11-19, MIT; read on its package
  page by the Desktop thread on 2026-11-21, and installed here into a scratch environment for Part C's measurement):
  selects tests affected by changed files and methods from a dependency database built on a first run. R30 admits it
  as the measured arm, opt-in per project, and SEL-041 Part C reports whether it earned its place on seldon's suite.
- **Memon et al. 2017, "Taming Google-Scale Continuous Testing" (ICSE-SEIP).** Catalogued in the shared library as
  `memon2017tap#meta` (`disposition: metadata_only`, the PDF not held); not read. Gligoric et al. 2015 (Ekstazi,
  regression test selection by dynamic file dependencies) and Elbaum, Rothermel and Penix 2014 (FSE, test selection
  and prioritisation in continuous integration) were found by the Desktop thread's search and are not read: this
  task's network allowlist is pypi.org alone, so they could not be fetched into seldon-biblio.
- **Fail-safe defaults** (Saltzer and Schroeder 1975, design principle (b), as AD-034 ADDENDUM 11 cites it): base the
  decision on permission, not exclusion. R32 and R34 apply it to selection: a path that no declaration permits to be
  skipped is tested in full, and a scoped pass is evidence only because a declaration permitted each skip.

### Internal

- internal receipt: query "test impact analysis" | repo seldon@24400dd937e251d06da53a61a7c3609faaec4969 | hits docs/decisions/REGISTER.md:9
- internal receipt: query "regression test selection" | repo squiddy@0a00d72d79c1799fc095f5b2cd25904318aecad6 | hits docs/design/2026-11-14_DN-061_a_pass_is_one_random_order_run_and_more_orders_are_a_search_not_a_gate.md:39, docs/design/2026-11-14_DN-060_the_record_pass_runs_its_seeds_side_by_side_and_shows_a_pass_in_flight.md:98, docs/design/2026-11-14_DN-060_the_record_pass_runs_its_seeds_side_by_side_and_shows_a_pass_in_flight.md:86
- internal receipt: query "gate_command" | repo seldon@24400dd937e251d06da53a61a7c3609faaec4969 | hits docs/design/AD-034_ADDENDUM_01_worktree_is_the_only_mode.md:38, docs/design/AD-034_ADDENDUM_11_a_stopped_session_is_never_merged_and_the_round_cannot_refuse_itself.md:3, docs/design/AD-034_worktree_per_task_dispatch.md:57, docs/design/AD-034_ADDENDUM_02_breaker_does_not_veto_green.md:18, docs/design/AD-034_ADDENDUM_02_breaker_does_not_veto_green.md:3, docs/design/AD-034_worktree_per_task_dispatch.md:37, docs/decisions/register/00209_seldon-ad-034-r5_accept.yaml:1, docs/decisions/register/00366_seldon-ad-034-r26_accept.yaml:1, docs/design/AD-034_ADDENDUM_01_worktree_is_the_only_mode.md:26, docs/design/AD-034_ADDENDUM_11_a_stopped_session_is_never_merged_and_the_round_cannot_refuse_itself.md:80

What the record already held: AD-034 decision 3 re-gates only "when main changed a file the task changed", so selection
by changed files was already the merge round's idea, applied to whether to gate and never to what the gate runs.
squiddy's DN-060 and DN-061 (its kit pass) decided how many orders a full pass runs, not which tests a change needs;
they are unchanged here. The library's other rows for "regression test selection continuous integration"
(`lesson:2026-02-22_arXiv_2502_18449`, a section headed "Regression tests selection", and agent-benchmark passages) are
about model regression, not test selection, and are not used.

## 3. Rulings

- **AD-034-R29. A project's gate has two tiers: a scoped gate, run for every task, of the tests and commands selected for what the branch changed against main; and a full gate, `dispatch.gate_command`, run only at declared points: `seldon gate run --full`, a task whose header says `**Gate:** full`, the project's cadence, and whenever selection cannot be trusted (R32).**
  The cadence is `dispatch.gate.full_every_s` (default 86,400 s, nightly): when the project's newest passing full gate
  is older than that, or there is none, the next gate is full and its record says `cadence_due`. It is a promotion of
  the next gate, not a separate scheduled job: the full gate then runs on a real change set, and needs no new daemon.
- **AD-034-R30. Selection is declared first and measured second. A project declares slices in `dispatch.gate.slices`, each a name, path globs, and the tests (paths, or `marker:<expression>`) and other commands those paths require, or `tests: none`; where a project opts in, a coverage map adds the tests it links to changed code. The selected set is the union.**
  A path matches a slice by glob (`*` within one directory, `**` across directories). Tests are run by
  `dispatch.gate.test_command`, whose `{tests}` is replaced by the selected paths; a marker expression is run over
  `dispatch.gate.test_root`. The coverage map is `dispatch.gate.coverage_map`, `none` unless an arm has been shipped
  for it; an arm ships only on a measurement on a real suite (seeded changes whose covering test must be selected
  every time, under the project's own xdist and subprocess use), and SEL-041's RESULT (Part C) reports testmon's.
- **AD-034-R31. A scoped gate always runs the test files the branch added or changed, and the test files that failed in the project's last recorded gate, whatever the slices say.**
  A test file is a changed path matching `dispatch.gate.test_globs`; a failed one is a file named in the last gate
  record's `failed_files` that still exists in the tree.
- **AD-034-R32. The gate is full, and its record says why, when a changed path matches no slice (and no coverage map knows it), when the change alters the gate's own configuration (`dispatch.gate_command` or `dispatch.gate`), a dependency lock or project file (`dispatch.gate.full_paths`), or any `conftest.py`, or when a declared coverage map is missing or stale.**
  `reason` is the first cause found and `reasons` all of them, each naming its path. This is the fail-safe default:
  skipping a test needs a declaration that permits it.
- **AD-034-R33. Every gate run is one `gate_run` record in the project's event store: its tier, reason, call site, the commit and tree it tested, the test files selected of the total, the tests run, the wall seconds, the outcome and the files that failed. A full gate that fails a test file the last scoped gate on the same change set did not select records those files as `escapes` on the full gate's own record.**
  The change set is the branch and the sorted paths it changed against main. Escapes per full gate is the measure of
  whether a project's slices are safe; `seldon qc chart` counts them beside the seconds. The merge record's
  `gate_evidence` names the `gate_run` record it merged on (ADDENDUM 01 item 4 of SEL-041: one record, not two).
  A project with no slices gets the same record for its one tier (`tier: full`, `reason: no_slices`).
- **AD-034-R34. A passing `gate_run` record for the tree the session left is evidence under AD-034-R26, scoped or full, including a scoped gate that selected nothing because every changed path matched a slice declared `tests: none`; a record run on a dirty tree is not.**
  The declaration is the permission R26's fail-safe default asks for, which is what a Stop gate with no check lacks:
  a missing check is silence, a `tests: none` slice is a statement on the record that can be wrong and is then
  measured (R33's escapes, the cadence's full gate). A plan with a path no slice matches is full under R32, so a
  scoped record never stands for an unmatched path. The evidence order becomes: the declared pass record, the round's
  re-gate, a kept branch's regate, a passing `gate_run` for the session's tree, a Stop gate that ran a check.
- **AD-034-R35. Where a project declares slices, the gate's three call sites go through the planner: the merge round's re-gate and its evidence gate (AD-034-R26's `merge_gate`) run the plan and record it, and the session's Stop gate runs a scoped plan before the session may end and blocks it on a red one as on a failing check. A full plan is not run in the Stop hook; it is left to the merge round, which has the gate's timeout.**
  The Stop gate does not run a plan again for a tree that already has a passing record. Without slices every call
  site behaves as before: the re-gate and the evidence gate run `gate_command`, and the Stop gate runs only the
  declared Parts' checks.
- **AD-034-R36. A project is told: `seldon verify` and `seldon go` warn, never fail, when the median wall seconds of the project's last ten scoped gates exceed `dispatch.gate.warn_seconds`, and when a project declares a `gate_command` and no slices; `seldon qc chart` reports gate seconds per week by tier, with escapes.**
- **AD-034-R37. The selection mechanism is seldon's: a consumer declares slices, a threshold and a cadence, and writes no selection code. A project that declares no slices behaves as it did before this addendum, AD-034-R26's merge gate included, with R36's warning.**

## 4. What the rulings change for each project

- **seldon** declares slices for its documents, records and graphs (`tests: none`) and leaves its code unmatched, so a
  code change is full (evidence 3) and a documents-only task (3 of its last 30) is gated in seconds. Its
  `warn_seconds` is set from Part A's numbers, with the basis beside it in `seldon.yaml`.
- **hazbrief-mcp** declares nothing yet and gets R36's warning. What declaring slices for its non-code paths would
  have saved on its last thirty tasks is in evidence 2; its suite structure (evidence 3) is its own to change.
- **squiddy** declares a pass record (AD-034-R16 to R18), which stays first in the evidence order. A scoped gate is
  not a kit pass and never writes squiddy's ledger.
- **factory** and **ai-readiness-kg** declare no gate command. R26's `ungated` block is unchanged; slices without a
  gate command are refused at load (the full tier has no command to run).

## 5. What this does not change

The re-gate's trigger (decision 3: main changed a file the task changed), the merge round's rebase, union and register
checks, and the Stop gate's Part checks are unchanged. A scoped gate never replaces a declared pass record. The full
tier's command is the project's `gate_command`, as before.
