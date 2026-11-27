# AD-033 ADDENDUM 03: an importer's graph follows its imports, a worktree reads them, and a binding to a record that no longer binds is ended by `verify --fix`

**Date:** 2026-11-27. **Status:** Accepted. Implemented by SEL-058 Part A
(`cc_tasks/2026-11-27_SEL-058_three_open_filings_from_hazbrief_and_factory_are_answered.md`), answering hazbrief's filing
`cc_tasks/2026-11-27_filing_from_hazbrief_mcp_from_a_worktree_the_decision_register_reads_i.md`. **Extends:**
AD-034-R24 (the merge projects what it numbers) with a projection on the pass when an import changes; AD-033-R4 (only
accepted records bind) with its repair. Applies AD-034-R8, as SEL-018 applied it to the dispatch paths, to
`decisions.repositories` and `decisions.import`; that part needs no new ruling. Two new rulings, AD-033-R15 and R16.
**Code:** `seldon/core/decisions.py` (`settings`, `imports_fingerprint`, `non_binding_decision_edges`,
`prune_non_binding_decision_edges`); `seldon/commands/dispatch_worktree.py` (`project_imports`, `pass_parallel`);
`seldon/commands/dispatch.py` (`_pass`); `seldon/commands/verify.py` (`check_decisions`, `_fix_decisions`).
**Tests:** `tests/test_sel058_hazbrief_filings.py`.

## 1. Evidence

1. **A worktree read no imports.** `decisions.settings` resolved `repositories` and the side-by-side default for
   `import` against `Path(project_dir).resolve()`. From `<repo>/.claude/worktrees/<name>` that is
   `<repo>/.claude/worktrees/seldon`, which does not exist, so the register read zero records with no error. In
   hazbrief's HB-240 worktree on 2026-11-27, `seldon decision list --repo seldon` printed `0 record(s)` and the
   worktree's `seldon verify` reported no projection finding. The primary's verify reported 59 records not projected.
   Reproduced at HEAD `a5616f4`: the test's resolved path was `hazbrief/.claude/worktrees/seldon`.
2. **Nothing projected an import's records.** The merge round projects only when the merged branch brought pending
   records of the importer's own register (`number_merged_register` returns before `_project_register` otherwise).
   A record seldon or squiddy adds stays out of hazbrief's graph until a person runs `seldon decision project` on
   hazbrief's primary. Factory's spec check (2026-11-26) rated hazbrief's `seldon_verify` CRITICAL on that finding.
3. **A dead binding had no command.** `seldon verify` fails on a `constrained_by` edge to a Decision that is not
   `accepted`, whatever the task's state. A supersession never moves or ends those edges. `seldon link` can only create,
   and the finding was not fixable. HB-240 ended HB-214's edge to the superseded `hazbrief-mcp:HBD-474` with a script
   calling `artifacts.remove_link`, which is what `verify --fix` already does for a Ruling
   (`governed.prune_non_binding_constraints`, AD-030).

## 2. Prior art

### External

These are cited from memory (Network `none`).

- **View maintenance.** A materialized view is refreshed when its base tables change, either eagerly or on a schedule
  that checks for change. The graph's Decision nodes are a view of the registers (R11). R15 refreshes on the
  dispatcher's existing schedule, and detects change by a content hash of each import's numbered files, the way a
  content-addressed build (Bazel's action cache) skips work whose inputs hash the same. The library hit
  `ilyas2022saga` (Saga, continuous construction of a knowledge graph from changing sources) is on the same problem at
  far larger scale. It was not read beyond its receipt row.

- library receipt: query "incremental view maintenance change detection" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows ilyas2022saga#b97:33214-34056, ilyas2022saga#b261:89734-89956, ilyas2022saga#b46:14919-15402, amodei2016concrete#b241:100759-100904, amodei2016concrete#b230:99026-99195, amodei2016concrete#b114:64460-64924, doc_sw_requiem_1#b35:2540-2585, ilyas2023growing#b44:14970-15162, ilyas2023growing#b72:24931-25580, ilyas2023growing#b15:3746-3983, doc_sw_sphinx_needs_2#b400:25620-25796, doc_omg_kerml_1#b4889:784624-784708, doc_omg_kerml_1#b5250:806810-807003, doc_omg_kerml_1#b4897:785156-785380, doc_omg_sysml_v2_1#b1396:471754-472284, doc_omg_sysml_v2_1#b4035:887843-887956, doc_omg_sysml_v2_1#b5755:1015414-1015665, doc_premis_3_0_1#b795:366817-367760, doc_premis_3_0_1#b913:402692-402993, doc_premis_3_0_1#b329:101346-101465, doc_sw_openfasttrace_ug_introduction_concepts_and_terms#b31:2491-2783, doc_sw_sphinx_needs_1#b43:735-753, xiong2026alma#b43:24551-24817, xiong2026alma#b343:107079-107745, xiong2026alma#b188:73984-74296, doc_who_trs1033_annex4_1#b1106:321727-321829, doc_who_trs1033_annex4_1#b1075:317379-317419, doc_who_trs1033_annex4_1#b1122:322712-322751, doc_nasa_swe_072_1#b508:88525-88615, doc_nasa_swe_072_1#b576:98819-98848, doc_nasa_swe_072_1#b417:69603-70010, doc_rfc9162_1#b611:112870-112898, doc_rfc9162_1#b189:31088-31560, doc_rfc9162_1#b26:5700-5893, fuchss2025lissa#b179:72567-72748, fuchss2025lissa#b181:72924-73257, fuchss2025lissa#b178:72211-72565, doc_sw_openfasttrace_ug_product_lifecycle_product_lifecycle#b18:3403-3727, browning2014doorstop#b44:11151-12006, browning2014doorstop#b74:16896-17506, browning2014doorstop#b41:9916-10378, doc_argondigital_verification_methods_1#b102:12629-12696, doc_sw_doorstop_1#b62:1129-1155, nygard2011adr#b30:1901-1919

### Internal

- internal receipt: query "decision project" | repo seldon@a5616f4a981bff9c85e15b95bcaa64dc1036543d | hits docs/design/seldon_architectural_decisions.md:156, docs/seldon_architectural_decisions_updated.md:156, docs/design/AD-013_ADDENDUM_01_requirements_as_graph_content.md:143, docs/decisions/register/00339_seldon-ad-033-r13_accept.yaml:1
- internal receipt: query "constrained_by superseded" | repo seldon@a5616f4a981bff9c85e15b95bcaa64dc1036543d | hits none

What the record already held: R11 (projection idempotent by record hash), AD-034-R24 (the merge projects), SEL-052 (only
numbered records are projected), AD-034-R8 and SEL-018 (`worktree.anchor`), and AD-030's prune of Ruling edges.

## 3. Rulings

- **AD-033-R15. The dispatcher's pass, with no session in flight, projects the register when an imported repository's numbered register files differ from those it last projected: a sha256 per import over its numbered files (pending ones excluded), kept beside the lease. A projection that changes or fails writes one `register_projected` record (a failure once per distinct error) and its lines are committed by the pass; a failure keeps the old fingerprint, so the next pass retries.**
  A project that imports nothing is unchanged. The projection is the same call the merge round makes, idempotent, so
  the first pass after this merges does a full projection once, and later passes do nothing until an import changes.
- **AD-033-R16. `seldon verify --fix` ends each `constrained_by` edge to a Decision that is not `accepted`, after re-projecting, as a `link_removed` event; the finding names the fix.**
  It ends the edge and does not move it to the superseding record. Binding a task to a record is registration's
  matching (R4, `cc register`), and a repair that re-bound would be making that judgment. The removal is on the record,
  so the next reader can tell a repair from a gap (AD-030's reason).

## 4. What the rulings change for each project

- **hazbrief-mcp, and any project that imports a register.** A worktree's `decision list`, `verify` and registration
  binding read the imports from the primary checkouts. A new seldon or squiddy record reaches the graph on the next pass
  with no session in flight. hazbrief's `seldon.yaml` comment, "Resolved against the primary checkout from a worktree",
  is now true. A stale binding is one `seldon verify --fix`.

## 5. What this does not change

- The importer's own register in a worktree is still the worktree's (pending records, numbered at merge).
- Which task a record binds is still decided at registration (R4).
