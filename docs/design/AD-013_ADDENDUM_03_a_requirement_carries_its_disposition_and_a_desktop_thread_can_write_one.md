# AD-013 ADDENDUM 03: a requirement carries its disposition, with its grounds, and a Desktop thread can write one

**Date:** 2026-11-26. **Status:** Accepted. Implemented by SEL-052 Part A
(`cc_tasks/2026-11-26_SEL-052_what_factory_reported_this_week_is_answered.md`), from factory's filing
`cc_tasks/2026-11-26_filing_from_factory_the_prior_art_search_does_not_read_four_registered_repositories_and_a_need_stated_in_a_thread_cannot_enter_the_graph.md`
items 2 and 3 (factory F-020, F-034).
**Extends:** AD-013-R1's authored fields with four, and its Status cell (AD-013-R4) with the disposition. One new
ruling, AD-013-R7.
**Code:** `seldon/core/requirements.py` (`DISPOSITIONS`, `DISPOSITION_NEEDS`, `check_disposition`,
`disposition_text`, `status_cell`); `seldon/domain/research.yaml` (`SRS_Requirement`); `seldon/commands/req.py`
(`--disposition` and its companions); `seldon/mcp_server.py` (`seldon_req_add`, `seldon_req_update`).
**Tests:** `tests/test_sel052_filing_answers.py`.

## 1. Evidence

1. **A need had no first-class disposition.** factory records every stakeholder need with a disposition (F-034:
   built, planned with a task, deferred with a reason and an ending condition, declined with a reason, undecided) and,
   with no property for it on `SRS_Requirement`, wrote it as the first clause of `note` in a form its own check parses.
   The Issue type already carries `disposition` (SEL-021).
2. **A need stated in a thread could not enter the graph in that turn.** `seldon req add` and `seldon req update` were
   CLI-only, and factory's coordinator works through seldon-mcp (F-020: a need enters the graph in the turn it is said).

## 2. Prior art

### External

- **ISO/IEC/IEEE 29148:2018** requirement attributes (rationale, status) and **change-request disposition** in
  configuration management (IEEE 828; approved, deferred, rejected, each with its reason). Named, not fetched. Adopted:
  the disposition is an attribute with its grounds, not free text.
- The library arm's nearest rows are tool documentation (OpenFastTrace, Doorstop), read only as hits:
  - library receipt: query "requirement status rationale deferred rejected" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_sw_openfasttrace_ug_use_cases_writing_a_specification#b43:5804-6131, doc_sw_openfasttrace_ug_use_cases_delegating_requirement_coverage#b15:2009-2128, doc_sw_sphinx_needs_2#b78:3441-3628, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b24:4121-4415, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b25:4416-4666, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b23:4031-4120, doc_omg_reqif_1_2_1#b365:80354-80592, doc_omg_reqif_1_2_1#b337:76738-77036, doc_omg_reqif_1_2_1#b314:73305-73903, doc_nasa_swe_072_1#b249:38769-39127, doc_nasa_swe_072_1#b766:124087-124470, doc_nasa_swe_072_1#b163:21269-22012, doc_who_trs1033_annex4_1#b757:262434-262545, doc_who_trs1033_annex4_1#b1898:508487-508561, doc_who_trs1033_annex4_1#b1897:508289-508485, nygard2011adr#b44:3998-4255, doc_sw_openfasttrace_ug_reference_console_tracing_report#b10:1113-1182, zhuge2024agentjudge#b340:88683-88904, zhuge2024agentjudge#b371:105637-106471, zhuge2024agentjudge#b291:76783-77723, gotel1994traceability#b181:54147-54346, gotel1994traceability#b147:47952-48233, gotel1994traceability#b68:24771-25021, doc_rfc9162_1#b226:37317-38082, doc_rfc9162_1#b189:31088-31560, doc_sw_openfasttrace_ug_use_cases_filtering_by_status#meta, doc_omg_sysml_v2_1#b1209:429431-429981, doc_omg_sysml_v2_1#b1223:434369-434521, doc_omg_sysml_v2_1#b1258:444566-444788, doc_sw_sphinx_needs_1#b1463:26247-26253, doc_sw_openfasttrace_ug_use_cases_use_cases#b6:807-998, doc_sw_openfasttrace_ug_use_cases_use_cases#b9:1353-1510, doc_sw_cog_2#b1:180-290, doc_premis_3_0_1#b314:98188-98280, doc_premis_3_0_1#b292:95092-95114, doc_premis_3_0_1#b3:74-337, doc_slsa_v1_0_1#b3:222-238, doc_sw_openfasttrace_2#b9:1445-1463

### Internal

- internal receipt: query "requirement disposition" | repo factory@2df06838aa7150aae0eddad71b9f8ae4ab850759 | hits docs/design/2026-11-26_DN-002_what_the_operator_says_is_a_need_with_a_disposition.md:44, docs/design/2026-11-26_DN-002_what_the_operator_says_is_a_need_with_a_disposition.md:95, docs/decisions/register/00044_factory-f-034_accept.yaml:37

What the record held: factory's DN-002 and its F-034 record define the five values and what each needs; this adopts
them unchanged.

## 3. Rulings

- **AD-013-R7. A requirement may carry `disposition` (built, planned, deferred, declined or undecided) with its grounds: planned needs `disposition_task`, deferred needs `disposition_reason` and `disposition_ends_when`, declined needs `disposition_reason`; a write that would leave a disposition without its grounds is refused, and the Status cell shows the disposition after the state; `seldon_req_add` and `seldon_req_update` on seldon-mcp are `seldon req add` and `update`, one core call, the same fields and refusals.**
  The grounds are read over the requirement as it would stand, so an update that changes only the disposition must
  carry what the new value needs. A requirement with no disposition renders exactly as before, so no projection goes
  stale by this ruling. Checking that every need in a project has a disposition stays the project's own check for now
  (factory's F-034); a `seldon docs check` rule for it waits on a second project asking.
