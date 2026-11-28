# AD-033 ADDENDUM 04: a task that has finished keeps the record of what bound it, and a branch's pending acceptance binds

**Date:** 2026-11-28. **Status:** Accepted. Implemented by SEL-063 Part A
(`cc_tasks/2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings.md`),
from REVIEW-001's finding F-27
(`docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/review.md`).
**Amends:** AD-033-R16 (ADDENDUM 03), on which edges `seldon verify --fix` ends.
**Code:** `seldon/core/decisions.py` (`non_binding_decision_edges`, `prune_non_binding_decision_edges`,
`pending_acceptances`); `seldon/commands/verify.py` (`check_decisions`, `_fix_decisions`).
**Tests:** `tests/test_sel063_part_a.py`.

## 1. Evidence

Read at this branch's base (`1c8d372`):

1. **A finished task lost what bound it.** `non_binding_decision_edges` matched every
   `(t)-[:CONSTRAINED_BY]->(d:Decision)` with `d.state <> 'accepted'`, whatever `t`'s state. A task completed under
   `X` and `X` superseded a week later: the next `verify` failed on the edge and `--fix` ended it. The edge was the
   graph's only statement that the task ran bound by `X`. The `link_removed` event keeps it on the record, so nothing
   was lost, but the graph no longer answered "what bound this task when it ran".
2. **A branch's acceptance was read as not binding.** The projection writes numbered records only (SEL-052), so a
   record a worktree has just accepted is still `proposed` in the shared graph. `verify --fix` run in that worktree
   ended every edge to it, in the graph every checkout shares, before the merge numbered the acceptance.

## 2. Prior art

### External

- **Bitemporal data** (Snodgrass, *Developing Time-Oriented Database Applications in SQL*, 1999; SQL:2011's
  application-time periods), from memory: a fact holds over a valid-time interval, and ending the interval is not
  deleting the fact. The edge from a finished task is a fact whose interval is the task's run. Adopted: the repair ends
  only edges whose interval is still open, a source still in an open state.
- **W3C PROV-O**: provenance is a record of what was used and what influenced an activity that has ended, and is not
  revised when the influencing entity later changes. The library's `doc_w3c_prov_o_1` row below is the ontology,
  returned for the query; it was not read beyond its receipt row.
  - library receipt: query "constraint recorded as history at the time a task ran, valid time" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_omg_sysml_v2_1#b1187:423987-424727, doc_omg_sysml_v2_1#b4215:930013-930863, doc_omg_sysml_v2_1#b1197:426584-427048, zhuge2024agentjudge#b352:90928-91603, zhuge2024agentjudge#b67:14851-15559, zhuge2024agentjudge#b289:75486-76755, xiong2026alma#b63:37093-37155, xiong2026alma#b57:33944-34603, xiong2026alma#b408:129399-130094, liang2026skillnet#b168:69926-69957, liang2026skillnet#b30:9483-9767, liang2026skillnet#b169:69959-70282, doc_who_trs1033_annex4_1#b1237:346477-346700, doc_who_trs1033_annex4_1#b1122:322712-322751, doc_who_trs1033_annex4_1#b1116:322453-322489, doc_premis_3_0_1#b59:26828-26843, doc_premis_3_0_1#b847:382512-382898, doc_premis_3_0_1#b219:74815-75214, doc_rfc9162_1#b253:44300-44695, yu2026multiagentmemory#b21:1237-1344, yu2026multiagentmemory#b49:7664-8528, yu2026multiagentmemory#b48:7344-7662, doc_sw_autoresearch_1#b10:2676-2970, doc_sw_autoresearch_1#b24:4365-4975, doc_w3c_prov_o_1#b1246:100215-100495, lehman2020creativity#b108:52501-52533, doc_omg_kerml_1#b415:193365-193481, doc_omg_kerml_1#b6100:884897-884943, doc_omg_kerml_1#b3484:656293-656740, doc_rfc8493_1#b161:27663-27690, doc_rfc8493_1#b20:4033-4105, li2024selfroute#b79:26727-27166, li2024selfroute#b17:4504-5116, li2024selfroute#b20:5965-6947, doc_sw_openfasttrace_ug_use_cases_distributing_the_detailing_work#b8:1736-1806, zhang2026rlm#b11:2613-3572, zhang2026rlm#b35:12798-13182, zhang2026rlm#b25:9735-10224, clark2014micropublications#b476:109184-109280, doc_nasa_swe_072_1#b270:42887-42953, doc_nasa_swe_072_1#b545:93930-94064, doc_nasa_swe_072_1#b442:75205-75302, gotel1994traceability#b114:38376-39079, gotel1994traceability#b185:54973-55098, gotel1994traceability#b136:46347-46532, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b24:4121-4415
  - library receipt: query "constraint recorded as history at the time a task ran, valid time" | graph library | release library_graph_20261110_sq133r_b.r1_2026-11-13.json sha256:c38db2b4106bbc762c984d545e044a60ac0a91923254ba2e4de8cf8a3964d784 | rows lesson:2026-06-16_arXiv_2506_07853#p5:44:352-1893, lesson:2026-06-16_arXiv_2506_07853#p4:40:1850-2603, lesson:2026-02-22_arXiv_2309_09971#p7:114:3854-4153, lesson:2026-02-22_arXiv_2309_09971#p8:138:138-1251, lesson:2026-02-22_arXiv_2309_09971#p1:1:40-84, lesson:2026-03-17_arXiv_2602_03587#p56:1160:588-896, lesson:2026-03-17_arXiv_2602_03587#p56:1171:1787-3047, lesson:2026-03-17_arXiv_2602_03587#p54:1116:400-755, lesson:2026-02-22_arXiv_2410_10934#p28:412:1764-1887, lesson:2026-02-22_arXiv_2410_10934#p32:459:116-684, lesson:2026-02-22_arXiv_2410_10934#p31:447:1212-1321, lesson:2026-01-23_arXiv_2601_08815#p7:67:2017-2441, lesson:2026-01-23_arXiv_2601_08815#p13:158:1320-1345, lesson:2026-01-23_arXiv_2601_08815#p7:64:1775-1971, lesson:2026-05-09_arXiv_2602_22302#p33:544:774-1285, lesson:2026-05-09_arXiv_2602_22302#p22:388:1186-1464, lesson:2026-05-09_arXiv_2602_22302#p25:430:2714-3154, lesson:2026-02-22_arXiv_2410_02958#p15:426:68-202, lesson:2026-02-22_arXiv_2410_02958#p47:1153:571-1008, lesson:2026-02-22_arXiv_2410_02958#p6:192:5569-5689, lesson:2026-02-22_arXiv_2310_02374#p7:39:0-300, lesson:2026-02-22_arXiv_2404_07972#p13:278:2575-3958, lesson:2026-02-22_arXiv_2404_07972#p35:605:860-1194, lesson:2026-04-13_arXiv_2510_00615#p4:85:1129-2375, lesson:2026-04-13_arXiv_2510_00615#p21:501:905-1551, lesson:2026-04-13_arXiv_2510_00615#p30:716:276-644, lesson:2026-02-22_arXiv_2410_13825#p16:273:46-380, lesson:2026-02-22_arXiv_2410_04223#p10:327:1682-1729, lesson:2026-05-09_arXiv_2604_01707#p4:133:1371-1669, lesson:2026-02-22_arXiv_2510_24168#p4:130:3425-4082, lesson:2026-02-22_arXiv_2510_24168#p14:344:879-1468, lesson:2026-02-22_arXiv_2510_24168#p15:367:1761-1778, lesson:2026-04-16_arXiv_2602_22790#p4:26:0-231, lesson:2026-04-16_arXiv_2602_22790#p4:34:2048-2251, lesson:2026-04-16_arXiv_2602_22790#p5:55:2078-2583, lesson:2026-02-22_arXiv_2507_21035#p40:644:1502-2211, lesson:2026-02-22_arXiv_2507_21035#p39:627:2589-2606, lesson:2026-02-22_arXiv_2507_21035#p41:655:1316-1333, lesson:2026-02-22_arXiv_2511_20857#p22:305:1751-1843, lesson:2026-02-22_arXiv_2511_20857#p22:297:966-1108, lesson:2026-02-22_arXiv_2511_20857#p9:182:0-221, lesson:2025-06-28_arXiv_2506_05790#p12:334:26-2050, lesson:2025-06-28_arXiv_2506_05790#p17:414:2007-2531, lesson:2025-06-28_arXiv_2506_05790#p1:47:2639-3876, lesson:2026-02-22_arXiv_2502_14932#p4:123:3287-3339, lesson:2026-02-22_arXiv_2303_16434#p16:250:2269-2498

### Internal

- internal receipt: query "constrained_by completed task superseded decision" | repo seldon@f8eb569dc148027761a8d6658e32a0d280bfca3c | hits docs/decisions/REGISTER.md:9
- internal receipt: query "constrained_by completed task superseded decision" | repo squiddy@c8b6b5e0de7337063791aeb6f7bed7fc78c71c16 | hits none
- internal receipt: query "constrained_by completed task superseded decision" | repo ai-readiness-kg@f3ef4a311c8b10d6c4f7c28ced718302ae2cf6c1 | hits none
- internal receipt: query "constrained_by completed task superseded decision" | repo arnold@8c491f6c98586894787f5727560bf37a9d08c2fc | hits none
- internal receipt: query "constrained_by completed task superseded decision" | repo icsp_notebook@619179538d53afa65a6390b3feda17d7c30061aa | hits none
- internal receipt: query "constrained_by completed task superseded decision" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "constrained_by completed task superseded decision" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "constrained_by completed task superseded decision" | repo hazbrief-mcp@67694d89f564002ecd8a3d6b27f68b0b5ec330d8 | hits none
- internal receipt: query "constrained_by completed task superseded decision" | repo aacps-ai-policy@1370530ba3433d24f15fa214505f77fc719504c5 | hits none
- internal receipt: query "constrained_by completed task superseded decision" | repo critical-thinking-ai@0723ead6e21d3e0c66796aef90855ac1be63124c | hits none
- internal receipt: query "constrained_by completed task superseded decision" | repo factory@9a4f9929fc8c999562445330e1b3f7155594a4cd | hits none

What the record held: R4 (only accepted records bind), R16 (the repair), SEL-052 and AD-033-R14 (the projection and
`verify` read numbered records, and report pending ones). The REGISTER.md hit is the rendered register.

## 3. Rulings

- **Amends AD-033-R16: `seldon verify` reports, and `seldon verify --fix` ends after re-projecting, as a `link_removed` event, each `constrained_by` edge from an artifact in an open state of its type to a Decision that is not `accepted` and that no pending record of the register accepts; an edge from an artifact that has left its open states (a completed, verified, withdrawn, rejected or superseded task) stays, as the record of what bound it when it ran.**
  F-27. The open states are the domain's (`artifacts.open_states`), not a list here. A pending acceptance is read from
  the register with its pending records folded in (`decisions.pending_acceptances`), the status the merge will number;
  once it is numbered the projection carries it and the exception has nothing left to do. The edge is still never
  moved to a superseding record (R16's reason).

## 4. What this does not change

- Which records a task binds at registration (R4).
- A Ruling's prune (`governed.prune_non_binding_constraints`, AD-030). A positional Ruling has no register status to
  read, and a repository with a register binds none (AD-033-R7).
