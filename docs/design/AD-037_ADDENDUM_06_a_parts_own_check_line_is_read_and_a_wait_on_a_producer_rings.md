# AD-037 ADDENDUM 06: a Part's own check line is read, and a wait on a producer rings once it has lasted an hour

**Date:** 2026-11-27. **Status:** Accepted. Implemented by SEL-058 Part A
(`cc_tasks/2026-11-27_SEL-058_three_open_filings_from_hazbrief_and_factory_are_answered.md`), answering hazbrief's filing
`cc_tasks/2026-11-24_filing_from_hazbrief_a_parts_check_line_is_not_read_a_blocked_merge_was_completed_ungated_and_a_lease_wait.md`
(`1e367024`), items 1, 3 and 4. **Extends:** AD-037-R1 (marked criteria) with a second form the stations read;
AD-037-R19 (an `environment_in_flight` refusal says who holds the lease) with a bell. Two new rulings, AD-037-R22 and
R23.
**Code:** `seldon/core/stations.py` (`bare_marked_lines`, `part_criteria`); `seldon/core/dispatch.py`
(`ENVIRONMENT_WAIT_PASSES_DEFAULT`); `seldon/commands/dispatch.py` (`_environment_wait`, `_environment_cleared`,
`_premise_review`, `_stuck`).
**Tests:** `tests/test_sel058_hazbrief_filings.py`.

## 1. Evidence

1. **The form hazbrief was told.** SEL-042's return (its RESULT, "For hazbrief-mcp") said "give each Part a `check:`
   line". hazbrief HB-221 and HB-222 put `check: uv run pytest ...` on its own line directly under every `## Part X:`
   heading, and HB-223 to HB-227 did the same. `stations.part_criteria` read only the criteria under an Acceptance
   label (`criteria.acceptance_criteria`), so the Stop gate recorded `"checks": []` with `"section_found": true`, the
   finish recorded `checks_run: 0`, and the merge round ran `gate_command` as its evidence gate: 36 min 18 s for
   HB-221 and 52 min 54 s for HB-222. Registration did not refuse these files, since a line outside an Acceptance list
   is not a criterion. Desktop's handoff of 2026-11-24
   (`handoffs/2026-11-24_desktop_sld2_final_gate_work_not_yet_on_main_and_what_the_thread_got_wrong.md`) found the same
   in code and recorded that the relayed form was wrong. Reproduced at HEAD `a5616f4` by
   `test_a_parts_bare_check_line_is_read_as_its_check`.
2. **A wait nobody heard.** hazbrief's event store holds one `dispatch_refused` `environment_in_flight` at
   2026-11-24T15:34:02Z, and no `dispatch_stuck`, for a wait that lasted until about 17:06Z. Station (a) runs after the
   task streak (`_stuck`), on eligible tasks, so a wait was never counted in any streak. SEL-043 (AD-037-R17, merged
   2026-11-25) narrowed when a consumer waits: in the producer's pass and merge phases, or while its task writes what the
   consumer reads. The 2026-11-24 wait was in SEL-045's session phase and would not happen today. A merge window
   still holds the consumer. It is one gate long, and seldon's full gate took 2,408 s at `-n 6` (SEL-055's baseline).
3. **The task streak wiped the standing streaks.** `_stuck` rewrote the streak file from task refusals alone on every
   pass. A `dispatcher:<reason>` streak counted after it, such as SEL-054's `project_premise_false`, restarted at one
   on every pass, so a threshold above one never rang. Found while building R23
   (`test_the_task_streak_pass_keeps_the_standing_streaks`).
4. **The governing-note hold did ring.** hazbrief's store has `dispatch_stuck` `governing_unverified` for HB-225
   (`86830c40`) at 2026-11-24T08:04:15Z, after three passes, and its log has the `STUCK:` line. So the alarm ran
   `notify` once. Nobody saw the notification, and Desktop found the hold by reading `seldon go`. That is a
   delivery question for the notifier the project declares, not a missing alarm. Nothing here changes it.

## 2. Prior art

### External

None of these was read for this task (its Network line is `none`). They are cited from memory. The library receipt
below shows the shared library holds nothing on-topic for alerting.

- **Freshness alarms.** The stuck alarm already cites the dead man's switch, Nagios freshness checks and Prometheus
  `absent()` with a `for:` duration (`seldon/core/dispatch.py`, `EVENT_STUCK`). R23 adds one more condition with its
  own `for:`.
- **Pages must be actionable** (Google SRE book, "Monitoring Distributed Systems", 2016). An alert on a condition that
  clears by itself trains people to ignore alerts. A producer's normal merge window clears by itself, so R23 rings only
  past it, not at the task streak's three passes.
- **Postel's robustness principle** (RFC 761, section 2.10; RFC 9413 on its limits). R22 accepts a second, unambiguous
  form that authors were told to use. It does not guess at an ambiguous one: a line inside a fenced block, or one that
  is not at the start of a line, is not read.

- library receipt: query "alert fatigue actionable alerts" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_who_trs1033_annex4_1#b1567:424430-424674, doc_who_trs1033_annex4_1#b1119:322562-322589, doc_who_trs1033_annex4_1#b1097:320938-321025, doc_premis_3_0_1#b872:394020-394159, doc_premis_3_0_1#b103:39511-40229, doc_premis_3_0_1#b795:366817-367760, liang2026skillnet#b209:90139-90370, liang2026skillnet#b26:8397-8644, liang2026skillnet#b233:101003-101661, arxiv_2104_03986#b106:44808-45044, arxiv_2104_03986#b217:79148-79635, arxiv_2104_03986#b149:57624-58011, doc_nasa_swe_072_1#b417:69603-70010, doc_nasa_swe_072_1#b826:159435-159970, fuchss2025lissa#b199:77846-78125, fuchss2025lissa#b196:77085-77327, fuchss2025lissa#b215:82526-82963, zhao2024expel#b107:44262-44427, zhao2024expel#b61:26069-26524, zhao2024expel#b80:34266-34822, amodei2016concrete#b80:43655-44082, amodei2016concrete#b301:110564-110728, amodei2016concrete#b180:91664-91852, doc_sw_autoresearch_1#b24:4365-4975, xiong2026alma#b58:34605-35150, xiong2026alma#b408:129399-130094, xiong2026alma#b266:96056-96538, doc_omg_sysml_v2_1#b999:383845-384333, doc_omg_sysml_v2_1#b3974:873157-873350, doc_omg_sysml_v2_1#b935:369443-369664, zhang2026rlm#b150:68756-69338, zhang2026rlm#b31:11456-11642, zhang2026rlm#b94:44191-44316, doc_rfc9162_1#b32:8570-9071, doc_omg_reqif_1_2_1#b192:64058-66150, doc_omg_reqif_1_2_1#b1642:129937-130138, doc_sw_openfasttrace_2#b10:1465-4035, doc_sw_sphinx_needs_2#b218:12521-12713, liu2024lostmiddle#b114:40683-40852, liu2024lostmiddle#b50:14833-15467, liu2024lostmiddle#b88:29311-30011, ilyas2022saga#b211:78155-78374, ilyas2022saga#b252:87476-87643, ilyas2022saga#b255:88142-88349, li2024kgllm#b68:19386-20369, doc_omg_kerml_1#b5362:810793-810922, doc_omg_kerml_1#b2543:522752-523059, doc_omg_kerml_1#b4949:787870-788059

### Internal

- internal receipt: query "environment_in_flight" | repo seldon@a5616f4a981bff9c85e15b95bcaa64dc1036543d | hits docs/design/AD-037_ADDENDUM_05_a_consumer_waits_on_a_producer_only_while_what_it_reads_can_change.md:88, docs/decisions/register/00383_seldon-ad-037-r19_accept.yaml:1, handoffs/2026-11-25_desktop_sld3_final_gate_work_on_main_thread_retires_to_factory.md:25, docs/design/AD-037_ADDENDUM_05_a_consumer_waits_on_a_producer_only_while_what_it_reads_can_change.md:3
- internal receipt: query "give each Part a check line" | repo seldon@a5616f4a981bff9c85e15b95bcaa64dc1036543d | hits handoffs/2026-11-24_desktop_sld2_final_gate_work_not_yet_on_main_and_what_the_thread_got_wrong.md:34, docs/decisions/register/00123_seldon-ad-029_amend.yaml:1, docs/decisions/REGISTER.md:9

What the record already held: AD-037-R1 (a decidable criterion is decided by running it) and `criteria.py`'s three
forms (inline, block and section). SEL-022 (AD-038-R6's outage-once pattern) made standing refusals ring through the
same `advance_stuck` under a `dispatcher:` key. SEL-043's R19 made the refusal name its holder.

## 3. Rulings

- **AD-037-R22. A Part's criteria are read in both marked forms, each command once and in order: the items under an Acceptance label (R1), and a `check:` or `judgment:` line standing on its own at the start of a line in the Part, outside a fenced block; the Stop gate, the finish's `checks_run` and the regate all read through `stations.part_criteria`.**
  The relayed form (SEL-042's return) now works, and the Acceptance form works as before. Registration still checks
  only Acceptance criteria for marks (`criterion_unmarked`), because a bare marked line is marked by its form.
- **AD-037-R23. A consumer's wait on a producer's lease is a standing condition in the stuck streak, under `dispatcher:environment_in_flight`, one streak per holding window: it rings `dispatch_stuck` and `notify` once when a window has refused `dispatch.stuck_after_passes_by_criterion.environment_in_flight` reviewed passes (default 12, one hour at a 300 s poll), and the first reviewed pass the leases allow clears it. The task streak keeps every `dispatcher:` streak it does not own.**
  The default is above the task streak's three because a merge window ends by itself (section 1, evidence 2). It is
  in passes, so a project with another poll interval sets its own. The notification names the holder, task, phase and
  gate progress (R19's lines).

## 4. What the rulings change for each project

- **hazbrief-mcp.** HB-221's form is read. A task written that way is gated by its own checks at the Stop gate, and
  the round no longer runs `gate_command` for evidence. A wait on seldon's or squiddy's lease that lasts more than an
  hour rings once.
- **Every project.** The task streak no longer drops `dispatcher:` streaks, so SEL-054's `project_premise_false` and
  `limit_control_failed` ring at their thresholds.

## 5. What this does not change

- A list item with no Acceptance label above it is still not a criterion.
- The governing-note hold (evidence 4) is unchanged. Its alarm worked.
