# AD-034 ADDENDUM 13: the full suite runs on main on a schedule, its red closes the merges that can change a test, and a lane branch is planned like any other

**Date:** 2026-11-27. **Status:** Accepted. Implemented by SEL-055
(`cc_tasks/2026-11-27_SEL-055_the_gate_runs_what_a_change_can_break_and_no_queue_waits_an_hour_for_a_one_line_change.md`
and its ADDENDUM 01). It answers four filings: hazbrief-mcp's `a844c156` (2026-11-21, the gate is one command and
ran in full for a one-slide change), factory's of 2026-11-24 (seldon's merge gate holds every queue), hazbrief's of
2026-11-24 (HB-218 and SEL-041), and factory's of 2026-11-27 (seldon main's full gate is red, and a docs-only return
is parked behind it). **Amends:** AD-034-R29. The cadence is withdrawn as a promotion of a task's gate. R31 is
extended for a red main, and R34 does not admit evidence that skipped the closure. **Code:** `seldon/core/gate_plan.py`
(`scheduled_due`, `main_red`, the closure in `plan`); `seldon/commands/dispatch_gate.py` (the scheduled run);
`seldon/commands/dispatch.py` (the pass calls it); `seldon/commands/dispatch_worktree.py` (`_gate`, `_merge`);
`seldon/commands/gate.py` (`seldon gate main`); `seldon/commands/verify.py` (the lane warning).
**Tests:** `tests/test_sel055_scheduled_gate.py`.

## 1. Evidence

1. **Where SEL-041's work is.** All of it is on main. SEL-041 (`9d9caf94`) was blocked `regate_red`, as its RESULT
   predicted: its own merge ran main's 3,600 s timeout against an 82-minute serial gate. SEL-045 (`09520bb0`), filed
   to land the kept branch, was itself blocked `regate_red`. SEL-045R (`8315cc7a`, merged 2026-11-24T22:27Z) replayed
   both branches' commits onto main. AD-034 ADDENDUM 12's nine records (R29 to R37) are numbered (00372 to 00380),
   and `seldon/core/gate_plan.py` and `seldon gate plan|run` are on main. hazbrief took the return: its `seldon.yaml`
   declares three slices (HB-218R, merged 2026-11-25T15:32Z). The filing's "superseded" was SEL-041's graph state
   after its block, and SEL-045R is the task that overtook it. Nothing is left to land or replace.
2. **What the cadence did once it was live.** seldon's event store holds 9 `gate_run` records, hazbrief's 14
   (2026-11-21 to 11-27). SEL-051 changes one file, its own RESULT. It was gated twice at merge on the full tier, both
   times `cadence_due` (1,900 s and 3,094 s), and both runs were red on tests it does not touch
   (`test_sel019_project_new`, then `test_sel052_held_alarm` and the `union_merge` flake). Factory parked it under
   F-027 item 2. So the cadence made a RESULT-only branch pay for main's drift: it ran the full gate, then blocked the
   branch on failures that were main's.
3. **What the selected gate would have run, by today's declarations** (SEL-055 Part B,
   `docs/evidence/sel055/README.md`). Of seldon's last 20 merged tasks, 18 change package code, which goes full by
   design (R30: `tests/conftest.py` imports `seldon.cli`); 2 are scoped (26 and 29 of 205 test files). Of hazbrief's
   last 20, 14 change code and 1 is scoped; 5 go full only because of non-code paths no slice names
   (`docs/evidence/**`, `CLAUDE.md`, `docs/submission/**`). More than 60 of hazbrief's test files read
   `docs/evidence`, so declaring those paths is hazbrief's work (HB-230 kept `docs/` unmatched).
4. **No safe selector for code exists in either suite.** SEL-041 Part C measured testmon on seldon's suite: it missed
   39 of the 41 test files that reach code through `git commit` hooks. HB-230 measured testmon on hazbrief's suite: it
   missed failing tests for 12 of 20 Python seeds and for all 16 non-Python seeds. HB-230 also found the static reach
   wrong for anything `src` reads. A one-line code change therefore runs the full suite, in both suites. This addendum
   does not change that. It stops a change that is not code from paying the full suite, and it stops a task from
   paying for main's drift.
5. **Lane writes are not test-inert.** SEL-054's lane declares `writes` (for factory, `cc_tasks/**` and
   `for_operator/**`) so that the merge round can refuse anything else (AD-038-R41). Those writes are not code, but
   tests read them. seldon's `task_records` slice names three test files that read `cc_tasks/`. hazbrief's `records`
   slice names 39. So the lane's `writes` cannot by themselves declare that no test needs to run.

## 2. Prior art

### External

None of the four sources below was read for this task: its Network line is `none`. The shared library holds no
software-testing source on these terms. The search that shows it is the library receipt below: its rows are
off-topic, and the receipt keeps the gap on the record.

- **Regression test selection.** Rothermel and Harrold, "A safe, efficient regression test selection technique"
  (ACM TOSEM 6(2), 1997), cited from memory. "Safe" means a selection that omits no test whose outcome the change
  can alter. R39's closure and R32's fail-safe default (a path no declaration vouches for goes full) keep the scoped
  tier safe in that sense, by declaration rather than by analysis. Evidence 4 is why the analysis route is closed
  here.
- **Google TAP.** Memon et al. 2017, "Taming Google-Scale Continuous Testing" (ICSE-SEIP). It is catalogued in
  seldon-biblio as `memon2017tap#meta`, metadata only. squiddy's DN-043 (2026-10-10, section 2) read it under a web
  receipt and reports that very few tests ever fail, and that those that fail are close to the code they test, so
  running every test on every change is the cost TAP exists to avoid. TAP runs affected tests before a change is
  submitted, and runs further tests after submission on a batched schedule. R38 takes that split: selection at merge,
  the whole suite on a schedule.
- **Affected-target testing** (Bazel and its peers): the tests a change needs are read from declared dependencies.
  R30's slices are that declaration, made per path (ADDENDUM 12, section 2).
- **Tree closure.** In large shared-trunk projects (Chromium's tree status is the known instance, cited from memory),
  a red continuous build "closes the tree": commits stop, except those that fix the break, until it is green. The
  reason is to keep a broken trunk from collecting further changes that make the culprit harder to find and the
  build harder to fix. R39 is that rule. Its exception, a change whose every path is declared inert, comes from the
  same reason: such a change cannot add a failure, by the project's own declaration.

- library receipt: query "regression test selection safe" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_nasa_swe_072_1#b492:85072-85306, doc_nasa_swe_072_1#b360:57129-57184, doc_nasa_swe_072_1#b822:159089-159157, arxiv_2104_03986#b139:55103-55392, arxiv_2104_03986#b141:55476-55883, arxiv_2104_03986#b149:57624-58011, amodei2016concrete#b254:103209-103347, amodei2016concrete#b15:7075-7815, amodei2016concrete#b205:95454-95624, doc_who_trs1033_annex4_1#b688:250764-251103, doc_who_trs1033_annex4_1#b704:254498-254552, doc_who_trs1033_annex4_1#b767:264738-265128, arxiv_2406_14325#b39:21064-21416, arxiv_2406_14325#b169:76407-76690, arxiv_2406_14325#b41:21779-22379, doc_sw_sphinx_needs_1#b1411:25497-25503, fuchss2025lissa#b110:33238-34039, fuchss2025lissa#b155:63035-63934, fuchss2025lissa#b136:52522-53662, han2017checklists#b32:12226-12246, han2017checklists#b71:27524-28300, han2017checklists#b124:45369-45590, niosh_hierarchy_of_controls#b52:4712-4733, clark2014micropublications#b75:21631-21684, clark2014micropublications#b316:75716-76272, aaai_v40i44_41105#b35:10556-11519, aaai_v40i44_41105#b72:24135-24869, aaai_v40i44_41105#b73:24871-25400, doc_omg_sysml_v2_1#b2554:673416-673502, doc_omg_sysml_v2_1#b5798:1017165-1017260, doc_omg_sysml_v2_1#b4155:913049-913303, gwet2008ac1#meta, doc_sw_sphinx_needs_2#b380:23966-24002, zhao2024expel#b87:38679-39117, zhao2024expel#b189:61184-61793, zhao2024expel#b86:37857-38677, xiong2026alma#b420:133751-134024, xiong2026alma#b31:19906-20601, xiong2026alma#b370:114957-115101, liu2024lostmiddle#b67:20868-21404, liu2024lostmiddle#b91:31275-32088, liu2024lostmiddle#b109:39482-39655, lehman2020creativity#b300:116693-116817, lehman2020creativity#b314:118965-119066, lehman2020creativity#b315:119068-119216, liang2026skillnet#b361:137708-138611, liang2026skillnet#b77:23011-23410, liang2026skillnet#b76:22391-23009, zhuge2024agentjudge#b106:33901-34326, zhuge2024agentjudge#b381:109021-109466, zhuge2024agentjudge#b88:24460-24843

### Internal

- internal receipt: query "cadence_due" | repo seldon@a2d5be401aeb8f3bc52ca716b680dddb31b940b3 | hits docs/decisions/register/00372_seldon-ad-034-r29_accept.yaml:1, docs/design/AD-034_ADDENDUM_12_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points.md:78
- internal receipt: query "nightly full suite" | repo squiddy@b2fa3ecb715c6ed8365b000d15b015447500a7d4 | hits docs/design/2026-10-10_DN-043_governed_admission_in_seconds_tiered_tests_holder_leases.md:26

What the record already held: ADDENDUM 12 (R29) made the cadence "a promotion of the next gate, not a separate
scheduled job", so that it needed no new daemon. Evidence 2 is the cost of that choice: the next gate belongs to
whichever task merges next, and that task pays for main's state. The dispatcher's pass is already a scheduled job
(launchd, every `poll_interval_s`), so a scheduled run needs no new daemon either. squiddy's DN-043 tiered its kit
tests on the same TAP reading. The search for "tree closed red build" found nothing on tree closure in any
repository.

## 3. Rulings

- **AD-034-R38. Where a project declares slices, its full suite runs on main on a schedule, not on a task's change: the dispatcher's pass runs `dispatch.gate_command` in a detached checkout of main's head (call site `scheduled`, one `gate_run` record) when `dispatch.gate.full_every_s` has passed since the newest full gate on record, on a pass with no session in flight and nothing eligible to launch, and before a launch once `dispatch.gate.full_overdue_s` has passed; `seldon gate main` runs it by hand. The cadence never promotes a task's gate.**
  Amends R29. The checkout is `dispatch.gate.scheduled_worktree`, made fresh for each run and removed after it, with
  `dispatch.worktree_links` linked in. A plan's reasons no longer include `cadence_due`, so a branch whose paths are
  all declared is scoped at the Stop gate and at merge, whatever the day. The overdue bound keeps a queue that is
  never empty from starving the schedule; its default (two cadences) has no measured basis. A project with no slices
  has no scheduled run: every one of its gates is already full (R37).
- **AD-034-R39. While the newest scheduled run is red, the project's merges are closed to every change that can change a test's outcome, and the dispatcher says so: the red run rings `dispatch.notify` once and opens one Issue (`main_red`). Under closure the merge round's plans (re-gate and evidence gate) also run the test files the red run failed, and a red run that named none (a timeout, unparsed output) makes them full; a plan that selects nothing, because every changed path matched a slice declared `tests: none`, is not closed. Evidence that skipped the closure is not evidence under R26 while it holds. The closure ends when a later scheduled run passes, or when a branch merges on a passing full gate of its tip; after any merge under closure the scheduled run is due on the next pass.**
  Extends R31: the red run's failed files stay selected for as long as the closure holds, not only until the next
  gate of any branch. The Stop gate does not apply the closure, because a session cannot be required to fix main
  before it may end. The merge round applies it, and refuses evidence a session or a `seldon gate run` made without
  it: a scoped `gate_run`, a Stop gate's checks, or a kept regate. It then runs its own evidence gate. A fix merges
  when the failing files pass on its tree. A declared-inert branch (SEL-051's case once `cc_tasks/**` is so declared)
  merges, because by the project's declarations it cannot change main's result.
- **AD-034-R40. A lane branch (AD-038-R40, R41) is planned like any other branch: R41 confines its paths to the lane's `writes`, and the slices classify them. A lane's `writes` are not a declaration that no test reads those paths. A project that runs a lane declares slices for its writes, and `seldon verify` warns when a lane's writes are not covered by a slice. The merge record and the `gate_run` record name the lane.**
  Evidence 5 is why the lane's `writes` are not treated as `tests: none`. A lane task whose writes match a slice
  declared `tests: none` merges with nothing run beyond the record (R34's `declared_none`). One whose writes select
  tests runs those tests. One whose writes match no slice runs the full tier, and the warning says why. Since R38 no
  lane branch pays a cadence-promoted full gate.

## 4. What the rulings change for each project

- **seldon**: the cadence's full gate leaves the merge path. SEL-051's RESULT-only branch would have run the
  `task_records` slice (three test files) instead of the whole suite twice. A one-line code change still runs the
  whole suite (evidence 4).
- **hazbrief-mcp**: its scoped merges no longer pay a cadence-promoted full gate, and its full suite runs on its
  schedule. Five of its last 20 tasks went full only on non-code paths; declaring their readers is its own work
  (evidence 3, HB-230).
- **factory** declares no slices: no scheduled run, and every gate stays full (11 s). R40's warning tells it that a
  lane merge runs the full tier until it declares its lane's writes.
- **squiddy** declares a pass record and no slices: unchanged.

## 5. What this does not change

The planner's other rules (R30 to R32), the re-gate's trigger, the evidence order (R34) outside a closure, the Stop
gate's Part checks, and the full tier's command are unchanged. `dispatch.coordination_lane.merge_wait_s` is
unchanged: AD-038-R40 owns it, and SEL-055's RESULT reports the measured gate times beside it.
