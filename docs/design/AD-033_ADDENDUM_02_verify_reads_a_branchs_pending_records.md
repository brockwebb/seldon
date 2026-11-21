# AD-033 ADDENDUM 02: `seldon verify` reads a branch's pending register records and reports them

**Date:** 2026-11-21. **Status:** Accepted. Implemented by SEL-042 Part D
(`cc_tasks/2026-11-21_SEL-042_a_stopped_session_is_never_merged_or_completed_the_merge_round_cannot_refuse_itself_and_verify_reads_pending_records.md`),
from squiddy's filing `5b76278b` (2026-11-06) and hazbrief's report in `6a9c00fa` (2026-11-16). **Extends:**
AD-033-R12 (a branch's records are written pending and numbered at merge) to the verifier. One new ruling, AD-033-R14.
**Code:** `seldon/commands/verify.py` (`check_decisions`, `_pending_line`).
**Tests:** `tests/test_sel042_verify_pending_and_name_limit.py`.

## 1. Evidence

squiddy SQ-124 (worktree `cosmic-launching-cray`, 2026-11-06) committed three pending records (two `accept`, one
`amend` of the numbered `squiddy:R-237`) as AD-033-R12 directs; `seldon verify` then raised `KeyError: 'record_hash'`
at `seldon/core/decisions.py:772` (`Record.last_hash`) from `check_decisions`, and printed no check at all. hazbrief
HB-193 met it with HB-189's 21 pending records (2026-11-16), seldon's own SEL-040 session skipped verify for it, and
each of them worked around it by moving the pending directory aside. Reproduced here with SQ-124's shape; on the code
before this addendum the test fails with the same `KeyError` at the same line
(`docs/evidence/sel042/reproduction_old_code.txt`).

The cause: the projection check folded the register WITH its pending records and compared each record's
`last_hash` with the graph. A record whose last event is pending has no `record_hash` until the merge numbers it, and
the graph is projected from numbered records only (AD-033-R12, AD-034-R24), so the comparison could never hold.

## 2. Prior art

### Internal

- internal receipt: query "pending records" | repo seldon@6a74a6a82c5c73c7f40fc91952bfc9f0d46b477f | hits docs/design/evolution_burst_2026-04/cc1_pattern_extraction.md:316, docs/design/AD-033_ADDENDUM_01_register_numbers_at_merge.md:20, docs/design/AD-033_ADDENDUM_01_register_numbers_at_merge.md:30, docs/decisions/register/00301_seldon-ad-033-r12_accept.yaml:1
- internal receipt: query "pending records" | repo squiddy@0a00d72d79c1799fc095f5b2cd25904318aecad6 | hits docs/H-006_delivery_report.md:149, docs/design/2026-09-25_daemon_livelock_at_size_deferral.md:27, docs/Q-002_delivery_report.md:168, docs/EXTRACTION_DESIGN_SPEC.md:3

### External

- **Certificate Transparency 2.0** (RFC 9162, seldon-biblio `doc_rfc9162_1`): a log accepts a submission at once
  and incorporates it into the tree within its maximum merge delay; a client verifies the signed tree head and
  holds the accepted-but-unincorporated submission separately, never as part of the tree. The same split as a
  branch's pending record (accepted, numbered at merge) against the chain. Adopted for the reader: verify compares
  the graph with the numbered chain and reports the pending records beside it. A staged write is not a committed
  write: the write-ahead log's records before their commit point, and AD-033 ADDENDUM 01's broker-assigned offset,
  are the same model (named, not fetched).

- library receipt: query "write-ahead log commit point staged records" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_rfc9162_1#b300:51813-52278, doc_rfc9162_1#b19:3535-4066, doc_rfc9162_1#b302:52542-52565, doc_sw_madr_1#b41:4856-4935, doc_sw_madr_1#b49:5614-5624, doc_sw_madr_1#b44:5082-5227, doc_who_trs1033_annex4_1#b1123:322753-322806, doc_who_trs1033_annex4_1#b1374:381146-381870, doc_who_trs1033_annex4_1#b1327:366822-366978, yu2026multiagentmemory#b0:0-89, doc_omg_kerml_1#b5421:813088-813119, doc_omg_kerml_1#b6288:924007-924067, doc_omg_kerml_1#b6257:914873-915009, crosby2009tamper#meta, doc_omg_sysml_v2_1#b6746:1054819-1054850, doc_omg_sysml_v2_1#b4087:899262-899584, doc_omg_sysml_v2_1#b4104:902540-902749, doc_sw_openfasttrace_ug_reference_oft_command_line#b71:3782-3813, fuchss2025lissa#b127:46746-47339, fuchss2025lissa#b141:56140-57037, fuchss2025lissa#b140:55685-56138, ilyas2022saga#b94:32003-32788, ilyas2022saga#b209:77821-77969, ilyas2022saga#b143:55901-56815, doc_w3c_prov_o_1#b249:28185-28916, doc_w3c_prov_o_1#b41:5231-5290, doc_w3c_prov_o_1#b44:5333-5410, browning2014doorstop#b44:11151-12006, browning2014doorstop#b53:14046-14462, browning2014doorstop#b83:19886-20176, doc_rfc8493_1#b283:46313-46567, doc_premis_3_0_1#b752:344506-344845, doc_premis_3_0_1#b148:55603-56329, doc_premis_3_0_1#b164:61203-62067, doc_nasa_swe_072_1#b564:97597-97644, doc_nasa_swe_072_1#b584:99110-99164, doc_nasa_swe_072_1#b516:90026-90157, arxiv_2104_03986#b38:15342-15572, arxiv_2104_03986#b148:57321-57622, arxiv_2104_03986#b25:10267-10552, zhang2026rlm#b72:33601-33981, zhang2026rlm#b15:5072-5935, zhang2026rlm#b233:120313-120714, ilyas2023growing#b72:24931-25580, liu2024lostmiddle#b116:40970-41103, liu2024lostmiddle#b56:16983-17930, liu2024lostmiddle#b126:42693-42858, amodei2016concrete#b301:110564-110728

## 3. Rulings

- **AD-033-R14. `seldon verify` runs with a branch's pending register records present: it compares the graph with the numbered chain alone, reports the pending records as `N pending record(s), numbered at merge: <id> <event>, ...`, and runs every other check.**
  The pending records' own checks (name, canonical bytes, provisional id, shape, no duplicate create) still run in
  `Register.verify`, as AD-033-R12 made them. Verify is meant to run on a branch; moving `pending/` aside to make it
  run is never needed and hides the records the merge will number.

## 4. What this does not change

The numbering at merge, the projection after it (AD-034-R24) and the pending records' format are unchanged.
`seldon decision project` is not changed here; it is the merge's step, run on the primary after numbering.
