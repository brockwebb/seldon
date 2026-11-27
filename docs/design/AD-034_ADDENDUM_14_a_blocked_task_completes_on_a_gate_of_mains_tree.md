# AD-034 ADDENDUM 14: a task the dispatcher blocked completes only on a passing gate of the tree main holds

**Date:** 2026-11-27. **Status:** Accepted. Implemented by SEL-058 Part A
(`cc_tasks/2026-11-27_SEL-058_three_open_filings_from_hazbrief_and_factory_are_answered.md`), answering hazbrief's filing
`cc_tasks/2026-11-24_filing_from_hazbrief_a_parts_check_line_is_not_read_a_blocked_merge_was_completed_ungated_and_a_lease_wait.md`
(`1e367024`), item 2. **Extends:** AD-034-R26 (a merge needs recorded gate evidence) to the one completion path that
does not go through the merge round, `seldon cc complete`. One new ruling, AD-034-R41.
**Code:** `seldon/core/gate_plan.py` (`completion_evidence`); `seldon/commands/cc.py` (`_blocked_completion`,
`cc complete --ungated`); `seldon/domain/research.yaml` (`completion_gate`, `completed_ungated`).
**Tests:** `tests/test_sel058_hazbrief_filings.py`.

## 1. Evidence

1. **What happened.** The merge round blocked HB-221 (`regate_red`). A person regenerated one file and merged by hand
   (`c8bc9fb8`, 2026-11-23 20:47:51Z). `seldon cc complete` then walked the task from `blocked` to `completed`, and the
   OODA released HB-222 on that completion. Nothing on record gated the tree that reached main. HB-223's first full gate
   on 2026-11-24 found main red.
2. **At HEAD `a5616f4`.** `cc complete` checks the spec hash, the `Recall used:` line and the return of a filing. It
   reads nothing about gates. A `blocked` task walks to `completed` through `blocked -> in_progress -> completed`.
   Reproduced by `test_cc_complete_refuses_a_blocked_task_with_no_gate_on_main_then_completes_on_one`.
3. **What evidence exists to read.** Since SEL-041 and SEL-055, every gate run is one `gate_run` record with its tree
   hash, outcome and whether the tree was dirty (R33). `passing_record` (R34) finds the newest passing clean run of a
   tree. The scheduled run (R38) and `seldon gate main` write such a record for main's head.

## 2. Prior art

### External

These are cited from memory (Network `none`). The library receipt shows nothing on-topic in the shared library.

- **The "not rocket science" rule** (Graydon Hoare, 2014, on bors and monotone-rs): keep a repository whose main
  always passes its tests by letting only a bot merge, and only after testing the merge result. A hand merge is
  outside that rule. R41 restores it at the next point the system controls, which is the completion that releases
  successors.
- **Required status checks** (GitHub branch protection): a merge into a protected branch needs passing checks on the
  head commit, and an administrator may override, which is recorded. R41 does the same: evidence on the tree main
  holds, or the operator's override with its reason on the task.

- library receipt: query "merge only after tests pass main always green" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_omg_kerml_1#b6273:920256-920639, doc_omg_kerml_1#b6259:915133-915247, doc_omg_kerml_1#b6262:915513-915751, doc_rfc9162_1#b84:16765-16937, doc_rfc9162_1#b506:88371-88406, doc_rfc9162_1#b300:51813-52278, doc_sw_madr_1#b52:5959-5994, doc_sw_madr_1#b36:4554-4634, doc_omg_sysml_v2_1#b940:370174-370719, doc_omg_sysml_v2_1#b5769:1016150-1016193, doc_omg_sysml_v2_1#b3974:873157-873350, doc_sw_sphinx_needs_2#b234:13653-13741, doc_sw_openfasttrace_ug_use_cases_tracing_the_whole_chain_in_the_same_file_system#b8:842-1113, chen2023chatgpt#b86:32756-33226, chen2023chatgpt#b19:9389-9978, chen2023chatgpt#b114:47292-47714, browning2014doorstop#b58:15401-15590, browning2014doorstop#b79:18742-19176, browning2014doorstop#b44:11151-12006, doc_sw_sphinx_needs_1#b1048:19436-19452, arxiv_2104_03986#b81:32292-32638, arxiv_2104_03986#b63:26245-26803, arxiv_2104_03986#b149:57624-58011, zhang2026rlm#b275:135805-136153, zhang2026rlm#b180:98109-98324, zhang2026rlm#b64:29790-30137, xiong2026alma#b215:87376-87415, xiong2026alma#b34:21372-21859, xiong2026alma#b406:128276-128704, ilyas2022saga#b80:26712-27039, ilyas2022saga#b71:22992-23359, ilyas2022saga#b67:20534-21059, doc_sw_strictdoc_1#b47:1417-1424, zhuge2024agentjudge#b88:24460-24843, zhuge2024agentjudge#b380:108632-109019, zhuge2024agentjudge#b80:21630-22314, doc_sw_openfasttrace_ug_use_cases_partial_tracing_by_responsibility#b17:2528-2622, li2024selfroute#b88:30656-30899, li2024selfroute#b82:28083-28590, li2024selfroute#b49:16848-17483, doc_nasa_swe_072_1#b364:57686-58363, doc_nasa_swe_072_1#b496:85751-85957, doc_nasa_swe_072_1#b459:79770-79861, doc_who_trs1033_annex4_1#b1674:450729-451410, doc_who_trs1033_annex4_1#b767:264738-265128, doc_who_trs1033_annex4_1#b520:136088-136130, fuchss2025lissa#b109:33215-33236, fuchss2025lissa#b110:33238-34039, fuchss2025lissa#b127:46746-47339

### Internal

- internal receipt: query "gate evidence" | repo seldon@a5616f4a981bff9c85e15b95bcaa64dc1036543d | hits docs/decisions/register/00366_seldon-ad-034-r26_accept.yaml:1, docs/design/AD-034_ADDENDUM_12_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points.md:3, docs/decisions/register/00378_seldon-ad-034-r35_accept.yaml:1, docs/SEL-001_delivery_report.md:82
- internal receipt: query "cc complete blocked" | repo seldon@a5616f4a981bff9c85e15b95bcaa64dc1036543d | hits docs/design/AD-036_ADDENDUM_09_an_answer_files_its_own_return.md:65, handoffs/2026-11-24_desktop_sld2_final_gate_work_not_yet_on_main_and_what_the_thread_got_wrong.md:24, handoffs/2026-11-25_desktop_sld3_final_gate_work_on_main_thread_retires_to_factory.md:30, docs/decisions/register/00365_seldon-ad-034-r25_accept.yaml:1

What the record already held: R26 (a branch merges only on recorded gate evidence; a Stop gate that ran no check is
none), R33 and R34 (the `gate_run` record and its lookup by tree), R38 (`seldon gate main`). The operator's doctrine
says gates bind the machine and not the operator, so the override is his and is recorded.

## 3. Rulings

- **AD-034-R41. `seldon cc complete` completes a task in `blocked` only on a passing, clean `gate_run` record of the tree the dispatch branch holds at that moment (a scheduled run, `seldon gate main`, or a full `seldon gate run` there), and records that record's id on the task as `completion_gate`; otherwise it refuses as `blocked_ungated` and writes nothing. The operator's `--ungated "<reason>"` completes it anyway and records the reason on the task as `completed_ungated`. A project with no dispatch block has no gate to require.**
  The tree is main's current one, not the hand merge's, because a successor released on the completion runs on what
  main holds now. A run on a dirty tree is not evidence (R34). The machine never passes `--ungated`.

## 4. What the ruling changes for each project

- **Every dispatched project.** Completing a blocked task by hand takes one more command: run `seldon gate main` (or
  wait for the scheduled run), then `seldon cc complete`. A project whose full gate is long can use `--ungated` with its
  grounding, for example "HB-223's full gate passed on this tree".

## 5. What this does not change

- The merge round's own completion (`dispatch_worktree`) is unchanged; it completes on R26's evidence.
- Completing a task that is not `blocked` is unchanged.
