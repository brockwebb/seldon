# AD-034 ADDENDUM 15: a presence check is no evidence, a scoped record does not end a red main, and R41 guards the transition

**Date:** 2026-11-28. **Status:** Accepted. Implemented by SEL-062 Parts B and C
(`cc_tasks/2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say.md`), from
REVIEW-001's findings F-08, F-12, F-16, F-18, F-19 and F-21
(`docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/review.md`).
**Amends:** AD-034-R26 (what a Stop gate's checks prove), R38 (the schedule is shown and its call never raises), R39
(a scoped pass record), R41 (a guard on the transition, and the branch on main).
**Code:** `seldon/core/returns.py` (`render`), `seldon/commands/dispatch.py` (`_gate_reading`, `dispatch status`),
`seldon/commands/dispatch_worktree.py` (`gate_evidence`, `evidential_check`), `seldon/commands/dispatch_gate.py`
(`maybe_run`), `seldon/core/gate_plan.py` (`closure_admits`, `_merged_on_full_pass`, `full_gate_age`,
`branch_on_main`), `seldon/core/artifacts.py` (`plan_task_transition`, `walk_to_completed`, `R41Refused`),
`seldon/commands/cc.py` (`r41_completion`).
**Tests:** `tests/test_sel062_part_b.py`, `tests/test_sel062_part_c.py`.

## 1. Evidence

Read again at this branch's base (`2c0f861`):

1. **F-08. Every return passed its own Stop gate by construction.** `returns.render` wrote one check into every
   return: `check: test -f cc_tasks/<its own stem>_RESULT.md`. The finish already refuses a session that committed
   no RESULT. So that check passed whenever the merge was possible at all, and `gate_evidence` counted "a Stop gate
   that passed and ran at least one check" as merge evidence under R26. SEL-052 added the line so that
   critical-thinking-ai's return CTAI-008, in a project that declares no gate command, would merge. It did merge, on
   a check that could not fail.
2. **F-16. R41 lived at two entry points.** REVIEW-001 put the CLI's and the MCP tool's checks into one function,
   `cc.r41_completion`. But `seldon task close` and the MCP `seldon_task_close` walk a `blocked` task to `completed`
   through `walk_to_completed`, and `seldon task update` steps it `blocked → in_progress → completed`. Neither
   path calls R41. The state machine (`research.yaml`: `blocked: [accepted, in_progress, superseded, withdrawn]`)
   allows both walks.
3. **F-19. A scoped pass record ended a red main.** `gate_plan._merged_on_full_pass` returned true for any
   `gate_record` source, and `closure_admits` admitted one under the closure. squiddy's record is scoped by
   `tree_paths: [squiddy/]` (seldon's `gate_record.coverage` accepts a later commit whose `squiddy/` tree is unchanged).
   So a pass record that never ran the red run's failed files outside `squiddy/` lifted the closure R39 sets.
4. **F-21. R41 checked main's tree, not the task's work.** `completion_evidence` asks for a passing full gate of
   the tree main holds now. A blocked task whose branch never reached main completed on main's unrelated green.
5. **F-18. Nothing showed the schedule's age.** Since SEL-055, only a dispatcher pass runs the full suite.
   `dispatch status` and `seldon go` said nothing about how old the newest full gate is, so a dispatcher that stopped
   passing left main's last full gate ageing unseen.
6. **F-12.** `dispatch_gate.maybe_run` says it never raises, but caught only `ScheduledBusy` and `GateConfigError`.
   An `OSError` from the checkout crashed every pass.

## 2. Prior art

### External

- **Guard conditions on state-machine transitions** (OMG SysML v2: "A transition usage can also have a Boolean-valued
  guard expression. The guard expression is evaluated during the perform..."; KerML: "all Evaluations identified by
  guard must have result value true"; UML 2.5 §14.2.3.8 and Harel statecharts, named, not fetched). A guard belongs
  to the transition, so every path that takes the transition meets it. Adopted for R41: the guard is in
  `plan_task_transition`, the one planner every ResearchTask move goes through.
- **Fail-safe defaults** (Saltzer and Schroeder 1975, named, not fetched): access is decided by permission, not by
  exclusion. A check that cannot fail grants by exclusion. Adopted for R26: a presence check of the task's own RESULT
  proves nothing the finish does not already require, so it is not evidence.
- **Patch identity** (`git cherry`, `git patch-id`: a commit's change is identified by the hash of its diff, so a
  cherry-picked or rebased commit is recognised on the upstream). Adopted for R41's branch condition, because a
  blocked task's work reaches main by hand through a rebase or a cherry-pick as often as through a merge.
- **Alert and action levels set from historical data** (WHO TRS 1033 Annex 4: "Alert and action levels should be
  established based on historically reported data"). Used by AD-037 erratum 01 for R23's threshold; named here because
  R38's age is shown against the levels a project declares.
- The library arm:
  - library receipt: query "guard condition on a state machine transition" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_omg_sysml_v2_1#b1122:409292-409687, doc_omg_sysml_v2_1#b1078:400803-401718, doc_omg_sysml_v2_1#b1132:412287-412403, doc_omg_kerml_1#b5052:794480-794572, doc_omg_kerml_1#b5053:794574-794639, doc_omg_kerml_1#b5097:799627-799868, zhang2026rlm#b28:10771-11058, doc_nasa_swe_072_1#b624:107287-107624, doc_nasa_swe_072_1#b350:56219-56290, doc_nasa_swe_072_1#b363:57527-57684, doc_who_trs1033_annex4_1#b2327:632360-632481, doc_who_trs1033_annex4_1#b2329:632815-632978, doc_who_trs1033_annex4_1#b1564:423957-424043, amodei2016concrete#b261:104351-104523, amodei2016concrete#b33:15885-16224, amodei2016concrete#b169:89969-90077, doc_rfc8493_1#b185:31121-31218, xiong2026alma#b188:73984-74296, xiong2026alma#b319:103092-103204, xiong2026alma#b256:94326-94404, doc_omg_reqif_1_2_1#b6:154-179, ilyas2022saga#b127:46344-46368, clark2014micropublications#b27:3781-3840, lehman2020creativity#b313:118797-118963, lehman2020creativity#b6:1357-1407, lehman2020creativity#b23:2258-2309, arxiv_2406_14325#b5:1872-1962, arxiv_2406_14325#b131:69021-69095, arxiv_2406_14325#b162:75108-75374, doc_rfc9162_1#b640:119032-119240, zhuge2024agentjudge#b147:45701-45766, zhuge2024agentjudge#b166:48638-48838, zhuge2024agentjudge#b216:59255-59429, liu2024lostmiddle#b89:30013-30427, zhao2024expel#b151:51286-51352, aaai_v40i44_41105#b90:29987-30211, aaai_v40i44_41105#b80:28095-28257, doc_premis_3_0_1#b873:394161-394361, doc_sw_cog_1#b39:5226-5470
  - library receipt: query "a test that passes vacuously is not evidence" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_omg_sysml_v2_1#b4318:957377-957528, doc_omg_sysml_v2_1#b1310:456189-456284, doc_omg_sysml_v2_1#b1324:459105-459605, doc_sw_sphinx_needs_2#b329:19308-19892, doc_who_trs1033_annex4_1#b1326:366770-366820, doc_who_trs1033_annex4_1#b1024:309886-310231, doc_who_trs1033_annex4_1#b691:251899-252271, clark2014micropublications#b396:95853-95861, clark2014micropublications#b248:61932-61985, clark2014micropublications#b98:29764-30639, chen2023chatgpt#b133:52071-52217, chen2023chatgpt#b33:16920-17385, chen2023chatgpt#b127:51000-51127, arxiv_2406_14325#b41:21779-22379, arxiv_2406_14325#b40:21418-21777, arxiv_2406_14325#b39:21064-21416, han2017checklists#b132:47382-47491, han2017checklists#b47:19977-20450, han2017checklists#b78:33550-33962, doc_argondigital_verification_methods_1#b11:1651-1778, lehman2020creativity#b77:28487-29112, lehman2020creativity#b67:23231-23831, lehman2020creativity#b82:33109-33923, doc_nasa_swe_072_1#b546:94066-94119, doc_nasa_swe_072_1#b364:57686-58363, doc_nasa_swe_072_1#b491:84786-85070, doc_sw_sphinx_needs_1#b1124:20917-20949, doc_rfc9162_1#b616:113865-114415, zhuge2024agentjudge#b342:88916-89155, zhuge2024agentjudge#b106:33901-34326, zhuge2024agentjudge#b316:86682-87242, arxiv_2104_03986#b81:32292-32638, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b24:4121-4415, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b25:4416-4666, doc_rfc8493_1#b190:31898-32082, amodei2016concrete#b114:64460-64924, amodei2016concrete#b113:63684-64458, amodei2016concrete#b117:66722-67865, li2024selfroute#b73:25040-25783, li2024selfroute#b82:28083-28590, li2024selfroute#b29:9289-9925, browning2014doorstop#b63:15645-15785, browning2014doorstop#b53:14046-14462, doc_sw_strictdoc_1#b97:2365-2375
  - library receipt: query "alert threshold above the normal duration of a condition that clears itself" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_who_trs1033_annex4_1#b1097:320938-321025, doc_who_trs1033_annex4_1#b1567:424430-424674, doc_who_trs1033_annex4_1#b939:299333-299573, doc_omg_sysml_v2_1#b8811:1182548-1183018, doc_omg_sysml_v2_1#b8809:1181998-1182469, doc_omg_sysml_v2_1#b440:236239-236687, doc_nasa_swe_072_1#b358:56980-57085, doc_nasa_swe_072_1#b624:107287-107624, doc_nasa_swe_072_1#b364:57686-58363, doc_omg_kerml_1#b5334:809809-809900, doc_omg_kerml_1#b5206:805709-805861, doc_omg_kerml_1#b476:203448-203536, ilyas2023growing#b31:8279-8652, xiong2026alma#b266:96056-96538, xiong2026alma#b319:103092-103204, xiong2026alma#b330:105210-105302, doc_sw_sphinx_needs_1#b733:12995-13007, browning2014doorstop#b20:4782-5214, lehman2020creativity#b102:48709-49666, lehman2020creativity#b315:119068-119216, doc_rfc9162_1#b316:56481-56947, nygard2011adr#b13:293-308, li2024kgllm#b68:19386-20369, li2024kgllm#b67:18900-19384, liu2024lostmiddle#b82:26753-27388, liu2024lostmiddle#b109:39482-39655, liu2024lostmiddle#b72:22359-22841, fuchss2025lissa#b127:46746-47339, fuchss2025lissa#b161:66106-66889, fuchss2025lissa#b117:35319-37067, amodei2016concrete#b81:44084-44441, amodei2016concrete#b301:110564-110728, amodei2016concrete#b112:62379-63682, zhang2026rlm#b150:68756-69338, zhang2026rlm#b35:12798-13182, zhang2026rlm#b280:137380-137890, gotel1994traceability#b86:29804-30103, gotel1994traceability#b128:43942-44506, doc_premis_3_0_1#b795:366817-367760, doc_premis_3_0_1#b322:99592-99927, doc_premis_3_0_1#b818:375789-375818, arxiv_2104_03986#b104:44468-44783, arxiv_2104_03986#b186:69453-69763, arxiv_2104_03986#b171:64776-65231, doc_sw_sphinx_needs_2#b566:51251-51431

  The first returned SysML v2's and KerML's transition guards. The third returned WHO TRS 1033's alert levels. The
  second returned nothing on point (verification verdicts, not vacuous passes).

### Internal

- internal receipt: query "blocked_ungated completion gate" | repo seldon@2c0f8617e188c5c31e03f1906b45f3bd3af63cff | hits docs/design/AD-034_ADDENDUM_14_a_blocked_task_completes_on_a_gate_of_mains_tree.md:52, docs/decisions/register/00413_seldon-ad-034-r41_accept.yaml:1, docs/decisions/REGISTER.md:9
- internal receipt: query "blocked_ungated completion gate" | repo squiddy@659c0addc962b71cac63fe674867b8059eafc636 | hits none
- internal receipt: query "blocked_ungated completion gate" | repo ai-readiness-kg@f3ef4a311c8b10d6c4f7c28ced718302ae2cf6c1 | hits none
- internal receipt: query "blocked_ungated completion gate" | repo arnold@8c491f6c98586894787f5727560bf37a9d08c2fc | hits none
- internal receipt: query "blocked_ungated completion gate" | repo icsp_notebook@619179538d53afa65a6390b3feda17d7c30061aa | hits none
- internal receipt: query "blocked_ungated completion gate" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "blocked_ungated completion gate" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "blocked_ungated completion gate" | repo hazbrief-mcp@b84ca95637b681202b203d3837a42d91fcb5821e | hits none
- internal receipt: query "blocked_ungated completion gate" | repo aacps-ai-policy@1370530ba3433d24f15fa214505f77fc719504c5 | hits none
- internal receipt: query "blocked_ungated completion gate" | repo critical-thinking-ai@3d7a1069211ee2eb1a191b3e75c23ccc0a04dd92 | hits none
- internal receipt: query "blocked_ungated completion gate" | repo factory@25155801f46d3ec2fe3215f244b53f06600db634 | hits none
- internal receipt: query "check test -f RESULT evidence" | repo seldon@2c0f8617e188c5c31e03f1906b45f3bd3af63cff | hits docs/decisions/register/00303_seldon-ad-035-r13_accept.yaml:1, docs/design/AD-034_ADDENDUM_12_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points.md:78, docs/decisions/REGISTER.md:9
- internal receipt: query "check test -f RESULT evidence" | repo squiddy@659c0addc962b71cac63fe674867b8059eafc636 | hits docs/decisions/REGISTER.md:9, docs/DECISIONS_INHERITED.md:508, docs/EXTRACTION_DESIGN_SPEC.md:518
- internal receipt: query "check test -f RESULT evidence" | repo ai-readiness-kg@f3ef4a311c8b10d6c4f7c28ced718302ae2cf6c1 | hits none
- internal receipt: query "check test -f RESULT evidence" | repo arnold@8c491f6c98586894787f5727560bf37a9d08c2fc | hits docs/KG-008_delivery_report.md:300, docs/ACQ-001_delivery_report.md:94
- internal receipt: query "check test -f RESULT evidence" | repo icsp_notebook@619179538d53afa65a6390b3feda17d7c30061aa | hits none
- internal receipt: query "check test -f RESULT evidence" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "check test -f RESULT evidence" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "check test -f RESULT evidence" | repo hazbrief-mcp@b84ca95637b681202b203d3837a42d91fcb5821e | hits none
- internal receipt: query "check test -f RESULT evidence" | repo aacps-ai-policy@1370530ba3433d24f15fa214505f77fc719504c5 | hits none
- internal receipt: query "check test -f RESULT evidence" | repo critical-thinking-ai@3d7a1069211ee2eb1a191b3e75c23ccc0a04dd92 | hits none
- internal receipt: query "check test -f RESULT evidence" | repo factory@25155801f46d3ec2fe3215f244b53f06600db634 | hits none

What the record held:
- AD-034 ADDENDUM 14 (R41) and its register record, which this amends.
- REVIEW-001's `cc.r41_completion`, whose held test (blocked now, or blocked after the newest launch) this keeps.
- SEL-052's RESULT, which added the return's check line, and AD-034 ADDENDUM 08 (R16, R17), which defines a pass
  record and its `tree_paths`.

## 3. Rulings

- **Amends AD-034-R26: A branch shall merge only on recorded evidence that a gate passed for its tip (a declared pass record, the round's re-gate, a kept branch's regate, or a Stop gate that ran a check other than a test that the task's own RESULT exists, which the finish already requires); with none the round shall run the project's gate command, and with no gate command the task shall be blocked ungated.**
  F-08. `seldon cc return` no longer writes that check. A return in a project that declares no gate command is
  blocked `ungated`, as R26 says of any task there. Its remedy is the consumer's own `dispatch.gate_command`, not a
  check that cannot fail.
- **Amends AD-034-R38: Where a project declares slices, its full suite runs on main on a schedule, not on a task's change: the dispatcher's pass runs `dispatch.gate_command` in a detached checkout of main's head (call site `scheduled`, one `gate_run` record) when `dispatch.gate.full_every_s` has passed since the newest full gate on record, on a pass with no session in flight and nothing eligible to launch, and before a launch once `dispatch.gate.full_overdue_s` has passed; `seldon gate main` runs it by hand; `seldon dispatch status` shows the newest full gate's time and age against both thresholds; the pass's call never raises, and an error other than a busy checkout or a configuration error is recorded as `gate_scheduled_error` and printed. The cadence never promotes a task's gate.**
  F-18 and F-12. Status is the operator's eye when no pass runs. It reads the same anchor `scheduled_due` reads.
- **Amends AD-034-R39: While the newest scheduled run is red, the project's merges are closed to every change that can change a test's outcome, and the dispatcher says so: the red run rings `dispatch.notify` once and opens one Issue (`main_red`). Under closure the merge round's plans (re-gate and evidence gate) also run the test files the red run failed, and a red run that named none (a timeout, unparsed output) makes them full; a plan that selects nothing, because every changed path matched a slice declared `tests: none`, is not closed. Evidence that skipped the closure is not evidence under R26 while it holds, and a declared pass record scoped by `tree_paths` is such evidence. The closure ends when a later scheduled run passes, or when a branch merges on a passing full gate of its tip, of which a pass record counts only when it covers the whole tree; after any merge under closure the scheduled run is due on the next pass.**
  F-19. A scoped record still merges a branch when main is green (R16, R17 unchanged).
- **Amends AD-034-R41: A ResearchTask the dispatcher blocked (blocked now, or blocked after its newest launch) moves into `completed` only through a guard on that transition, met by every path (`seldon cc complete` and the MCP `seldon_cc_complete`, `seldon task close` and `seldon_task_close`, `seldon task update`, any walk): it passes on a passing, clean, full `gate_run` record of the tree the dispatch branch holds at that moment (a scheduled run, `seldon gate main`, or a full `seldon gate run` there) when the task's own dispatch branch on record has every commit's patch on that branch (`git cherry`), and records that record's id on the task as `completion_gate`; otherwise it refuses as `blocked_ungated` (no evidence) or `branch_not_on_main` (naming the branch and its unmerged commits) and writes nothing. The dispatcher's own completion after a merge passes with that merge's R26 evidence. The operator's `seldon cc complete --ungated "<reason>"` completes it anyway and records the reason on the task as `completed_ungated`. A project with no dispatch block has no gate to require.**
  F-16 and F-21. A branch that is on record but no longer resolves (deleted after a hand merge) cannot be shown to
  have reached main: it refuses as `branch_not_on_main`, and `--ungated` is the remedy. A task with no branch on
  record (in place, before FRICTION-002) is held to the gate alone.

## 4. What this does not change

- The held test (REVIEW-001 F-04), `--ungated` as the CLI's override alone, and the full-tier requirement (F-03).
- The R26 evidence order for every other source.
- A project with no slices has no schedule, so status shows `full gate: no schedule (no slices declared)`.
- R45 keeps its own state file (`dispatch_controls.json`). F-16's note on it was read. That file holds the tried
  fingerprint and its outcome, and that is not a standing condition. The condition itself is in the shared stuck
  streak, as every standing condition's is.
