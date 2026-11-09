# AD-013 ADDENDUM 01: a requirement is graph content, the requirements table and the RTM are projections of it, and a project without a decision register is told so

**Date:** 2026-11-09. **Status:** Accepted. Implemented by SEL-033
(`cc_tasks/2026-11-09_SEL-033_requirements_and_decisions_live_in_the_graph_and_the_rtm_is_a_projection.md`),
answering hazbrief-mcp's filings SEL-031 and SEL-032 together. **Extends:** AD-013 (documentation as traceability,
which declared `SRS_Requirement`), AD-033 (the decision register). **Depends on:** AD-002, AD-006, AD-012, AD-030.
Four rulings: AD-013-R1 to R3 and AD-033-R13.
**Code:** `seldon/core/requirements.py`; `seldon/commands/req.py`; `seldon/commands/docs.py`; `seldon/commands/verify.py`
(`check_requirements`, `check_decisions`); `seldon/commands/go.py`; `seldon/commands/init.py`;
`seldon/core/project_new.py`; `seldon/domain/research.yaml`.
**Tests:** `tests/test_sel033_requirements.py`, `tests/test_sel033_register_warning.py`.

## 1. Evidence

1. **The type was declared and never wired.** AD-013 section 2 declares `SRS_Requirement` (`requirement_id`,
   `description`); `seldon/domain/research.yaml` gives it a state machine (proposed, accepted, implemented, verified,
   stale, rejected) and the edges `implements`, `satisfies` and `mentions` reach it. Nothing loaded requirements but
   `seldon artifact create` by hand, nothing rendered them, `seldon verify` did not count them, and `verified_by` and
   `derived_from` did not accept the type at all. hazbrief-mcp's graph on 2026-11-09 held no requirement node
   (SEL-032 observation 1).
2. **The files became the truth.** hazbrief-mcp keeps 149 view requirements in `docs/VIEW_REQUIREMENTS.md` and about
   sixty more in `docs/REQUIREMENTS_TRACE.md`; the graph holds each file as one `Document` and its hash. HB-134R2's
   "four-place ratchet" keeps one counts sentence identical by hand in four files, and HB-131R, HB-136R, HB-140R and
   HB-141 each paid for it (SEL-032 observation 3).
3. **A register is optional by omission.** hazbrief-mcp's `seldon.yaml` declares no `decisions:` block. Twenty days,
   143 tasks and seventeen design notes passed, and `seldon init`, `seldon go` and `seldon verify` said nothing; a
   ruling of 2026-10-25 (the basemap) was found on 2026-11-09 only by searching chat transcripts (SEL-031). AD-033-R1
   already says each repository that registers tasks keeps a register; `check_decisions` passed a project without
   one as "skipping".
4. **The operator's own earlier system had the projection.** ANTS v0.4 (`brockwebb/ai-native-traceability-system`,
   found in the library search below) had `export_rtm` and `export_coverage_report` over the same shape. It did not
   carry forward into seldon (AD-001).

## 2. Prior art

### External

- **ISO/IEC/IEEE 29148:2018, requirements engineering.** A requirement carries an identifier, a statement, its
  source, its verification method and its status, and the set is traced in both directions (to its origin and to
  what satisfies and verifies it). Adopted as the attribute set of R1: `requirement_id`, `description` (the
  statement), `set_by` (the source), the `verified_by` edge (the verification), the state (the status).
- **ReqIF 1.2 (OMG, Requirements Interchange Format).** A requirement is a `SpecObject` with typed attribute values; a
  `SpecRelation` is a typed link between objects; a `Specification` is a hierarchy that orders objects for a
  document. The document is a view over the objects, not their container. Adopted: R1's object with typed attributes
  and typed edges, and R2's projection, where a document's sections (`section`) order the objects it shows.
- **SysML v2, requirement relations.** `satisfy` (a design element satisfies a requirement), `verify` (a verification
  case verifies it) and `derive` (a requirement derived from another). Seldon's edges already match them:
  `satisfies`, `verified_by`, `derived_from`. Adopted with no new edge type; `verified_by` and `derived_from` are
  widened to the requirement.
- **IBM DOORS (the operator's reference).** A formal module is a view over a database of objects with attributes;
  a heading is an object; the document is generated from the module, and an edit is made to the object, not to the
  printed document. Adopted as R2: the markdown table is generated, and the graph is edited.
- **Gotel and Finkelstein 1994, "An analysis of the requirements traceability problem".** Pre-requirements-
  specification traceability (where a requirement came from) fails most often, because the source is not recorded
  as a link. Adopted: the `Set by` column is resolved to a `derived_from` edge where its key names a file or a task,
  and what does not resolve is listed, not dropped.
- **Cleland-Huang, Gotel, Zisman et al., software and systems traceability (2012; trace link maintenance).** Trace
  links kept by hand decay with every change, and the remedy is to derive the trace from the artifacts. The
  four-place ratchet is a hand-maintained trace; R2 renders it.
- **Cog (Ned Batchelder), generated regions in hand-written files.** A file keeps its prose, and only the region
  between two markers is generated, with a check mode that fails when the region differs from a fresh run. Adopted as
  R2's marker blocks: hazbrief's files keep their prose (the TEVV reading, the review-cycle rule), and only the tables
  and the counts are generated.

The external sources are cited by their published names and were not fetched: the task's Network header allows
nothing beyond git.

- library receipt: query "requirements traceability matrix" | release library_graph_20261106_sq125_c_2026-11-06.json sha256:bbd841d3b5ab8822258c824656a1b80365d3a4707f0456ddb4f73d508a120cd3 | rows lesson:2026-04-05_arXiv_2603_28589#p6:37:644-713, lesson:2026-04-05_arXiv_2603_28589#p6:38:715-905, lesson:2026-08-25_arXiv_2607_02771#p2:53:807-820, lesson:2026-08-25_arXiv_2607_02771#p1:9:4822-5461, lesson:2026-02-22_arXiv_2505_24876#p36:772:400-429, lesson:2026-02-22_arXiv_2505_24876#p5:135:3135-3585, lesson:2026-02-22_arXiv_2505_24876#p5:125:218-595, lesson:2026-04-12_arXiv_2502_02617#p11:363:1131-1386, lesson:2026-04-12_arXiv_2502_02617#p9:268:56-88, lesson:2026-02-22_arXiv_2311_05965#p2:38:3422-3561, lesson:2026-08-25_arXiv_2512_03541#p25:298:420-595, lesson:2026-08-25_arXiv_2512_03541#p18:200:0-247, lesson:2026-08-25_arXiv_2512_03541#p17:194:1085-1423, lesson:2026-03-07_arXiv_2508_21038#p16:336:3693-3886, lesson:2026-03-07_arXiv_2508_21038#p17:343:809-1275, lesson:2026-03-07_arXiv_2508_21038#p16:323:3052-3062, lesson:2026-06-09_arXiv_2512_22473#p15:405:267-322, lesson:2026-06-09_arXiv_2512_22473#p15:409:388-408, lesson:2026-08-25_arXiv_2606_08317#p14:284:182-369, lesson:2026-08-25_arXiv_2606_08317#p15:326:4939-5361, lesson:2026-08-25_arXiv_2606_08317#p16:330:0-310, lesson:2026-02-02_github_com_brockwebb_ai_native_traceability_system#meta, lesson:2026-02-22_arXiv_2503_22732#p17:342:3621-3686, lesson:2026-02-22_arXiv_2503_22732#p39:1016:4215-4235, lesson:2026-02-22_arXiv_2503_22732#p39:1019:4252-4270, lesson:2026-02-22_arXiv_2506_06972#p14:407:46-265, lesson:2026-02-22_arXiv_2509_02547#p38:425:284-538, lesson:2026-02-22_arXiv_2509_02547#p27:331:5284-5502, lesson:2026-06-16_arXiv_2602_09801#p7:106:271-389, lesson:2026-06-16_arXiv_2602_09801#p4:49:1255-1489, lesson:2026-06-16_arXiv_2602_09801#p34:391:1071-1152, lesson:2026-03-27_arXiv_2509_18970#p20:468:0-167, lesson:2026-04-12_arXiv_2404_00456#p3:35:1782-2086, lesson:2026-04-12_arXiv_2404_00456#p3:46:2283-2314, lesson:2026-02-22_arXiv_2410_16946#p22:380:351-420, lesson:2026-02-22_arXiv_2410_16946#p17:308:189-281, lesson:2026-02-22_arXiv_2410_16946#p20:354:878-890, lesson:2026-02-22_arXiv_2311_13743#p8:136:3368-3888, lesson:2026-02-22_arXiv_2311_13743#p8:158:5181-5566, lesson:2026-02-22_arXiv_2311_13743#p4:29:1695-2681, lesson:2026-02-22_arXiv_2402_11451#p25:541:2972-4071, lesson:2026-02-22_arXiv_2402_11451#p25:537:1988-2941, lesson:2026-02-22_arXiv_2405_09783#p19:452:894-1027, lesson:2026-02-22_arXiv_2405_09783#p14:342:4242-4267, lesson:2026-02-22_arXiv_2405_09783#p15:366:3326-3351
- library receipt: query "trace link maintenance" | release library_graph_20261106_sq125_c_2026-11-06.json sha256:bbd841d3b5ab8822258c824656a1b80365d3a4707f0456ddb4f73d508a120cd3 | rows lesson:2026-02-22_arXiv_2510_02387#p27:559:698-718, lesson:2026-02-22_arXiv_2510_02387#p27:557:643-663, lesson:2026-02-22_arXiv_2510_02387#p55:1118:2886-3378, lesson:2026-08-25_arXiv_2606_08317#p12:242:2886-2949, lesson:2026-03-17_arXiv_2601_10338#p11:317:5714-6099, lesson:2026-03-17_arXiv_2601_10338#p20:516:906-1307, lesson:2026-03-17_arXiv_2602_02474#p4:71:318-406, lesson:2026-03-17_arXiv_2602_02474#p4:72:408-415, lesson:2026-03-17_arXiv_2602_02474#p4:73:417-424, lesson:2026-02-22_arXiv_2505_15155#p4:136:3401-3419, lesson:2026-02-22_arXiv_2505_15155#p4:131:2848-2880, lesson:2026-02-22_arXiv_2505_15155#p4:127:2631-2825, lesson:2026-02-21_arXiv_2510_09517#p14:204:1811-1984, lesson:2026-02-21_arXiv_2510_09517#p12:110:0-187, lesson:2026-02-21_arXiv_2510_09517#p15:255:2215-3777, lesson:2026-02-22_arXiv_2412_05255#p47:660:1096-1107, lesson:2026-02-22_arXiv_2304_05128#p8:126:944-1191, lesson:2026-02-22_arXiv_2304_05128#p4:34:1078-1889, lesson:2026-02-22_arXiv_2304_05128#p8:128:1227-1234, lesson:2026-02-22_arXiv_2407_08713#p17:290:1345-1360, lesson:2026-02-22_arXiv_2410_10934#p13:216:1424-1600, lesson:2026-02-22_arXiv_2505_24876#p19:485:160-175, lesson:2026-02-22_arXiv_2505_24876#p36:772:400-429, lesson:2026-02-22_arXiv_2505_24876#p38:808:562-588, lesson:2026-04-12_arXiv_2407_21783#p13:190:186-212, lesson:2026-04-12_arXiv_2407_21783#p13:191:214-233, lesson:2026-04-12_arXiv_2407_21783#p5:58:1363-1841, lesson:2026-07-09_arXiv_2603_23420#p6:71:105-129, lesson:2026-07-09_arXiv_2603_23420#p8:100:497-550, lesson:2026-07-09_arXiv_2603_23420#p6:73:221-283, lesson:2026-02-22_arXiv_2306_05301#p10:184:2705-2718, lesson:2026-02-22_arXiv_2306_05301#p11:199:1502-1515, lesson:2026-02-22_arXiv_2306_05301#p12:212:1594-1607, lesson:2026-02-22_arXiv_2601_03515#p4:127:1021-1074, lesson:2026-02-22_arXiv_2601_03515#p19:465:1561-1593, lesson:2026-02-22_arXiv_2601_03515#p19:466:1595-1622, lesson:2026-04-06_arXiv_2410_21680#p11:452:4433-5701, lesson:2026-04-06_arXiv_2410_21680#p12:491:4115-5546, lesson:2026-04-06_arXiv_2410_21680#p6:147:4007-4034, lesson:2026-02-22_arXiv_2311_05657#p18:314:968-1262, lesson:2026-02-22_arXiv_2406_12373#p5:123:2068-2911, lesson:2026-02-22_arXiv_2406_12373#p23:362:0-497, lesson:2026-02-22_arXiv_2406_12373#p29:476:2196-2288, lesson:2026-02-22_arXiv_2505_08638#p15:211:3942-4167, lesson:2026-02-22_arXiv_2505_08638#p21:353:2507-2603, lesson:2026-02-22_arXiv_2505_08638#p2:32:2204-3028, lesson:2026-02-22_arXiv_2506_21506#p19:294:538-577, lesson:2026-02-22_arXiv_2506_21506#p48:657:189-383, lesson:2026-02-22_arXiv_2506_21506#p26:396:335-371

The library is a corpus of AI-research lessons; its one row on this subject is the operator's ANTS repository
(evidence item 4). Its other rows are about model training and are not cited.

### Internal

- **Seldon's own record:** AD-013 section 1 ("documentation is a projection, not a source"); AD-012 (paper sections as graph
  assembly); AD-006 (every cited quantity a graph artifact); AD-030 (governed documents as graph content); AD-033-R1
  (each repository that registers tasks keeps a register); SEL-021 (a test node is a `Script` with `test_node`, the
  target of `verified_by`), whose test-reference grammar the importer reuses.

- internal receipt: query "export_rtm coverage report" | repo seldon@06ddffae306910aa5840c4d55346e63a45167a27 | hits none
- internal receipt: query "export_rtm coverage report" | repo squiddy@0a3cfcce41827a1b5c8d818b261d89ff36d50f09 | hits none
- internal receipt: query "export_rtm coverage report" | repo ai-readiness-kg@662295e212f7c4bb132cbeb2ade1e75ff2a4f218 | hits none
- internal receipt: query "export_rtm coverage report" | repo arnold@6114fe89226c455af64e3142bd6bee841769aeeb | hits none
- internal receipt: query "export_rtm coverage report" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "export_rtm coverage report" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "export_rtm coverage report" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "SRS_Requirement" | repo seldon@06ddffae306910aa5840c4d55346e63a45167a27 | hits docs/design/AD-013_documentation_as_traceability.md:182, docs/design/seldon_architectural_decisions.md:123, docs/seldon_architectural_decisions_updated.md:121, docs/design/seldon_architectural_decisions.md:110, docs/seldon_architectural_decisions_updated.md:108, docs/design/seldon_architectural_decisions.md:223, docs/seldon_architectural_decisions_updated.md:177, docs/design/AD-030_governed_documents_as_graph_content.md:18, docs/design/paper_authoring_convention.md:56, handoffs/2026-11-09_desktop_sld1_final_requirements_in_the_graph_and_the_open_filings.md:7
- internal receipt: query "SRS_Requirement" | repo squiddy@0a3cfcce41827a1b5c8d818b261d89ff36d50f09 | hits docs/Q-001_delivery_report.md:70, docs/COMPETENCY_QUESTIONS.md:32, docs/S-011_delivery_report.md:57
- internal receipt: query "SRS_Requirement" | repo ai-readiness-kg@662295e212f7c4bb132cbeb2ade1e75ff2a4f218 | hits none
- internal receipt: query "SRS_Requirement" | repo arnold@6114fe89226c455af64e3142bd6bee841769aeeb | hits none
- internal receipt: query "SRS_Requirement" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "SRS_Requirement" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "SRS_Requirement" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "project declares no decision register" | repo seldon@06ddffae306910aa5840c4d55346e63a45167a27 | hits docs/decisions/REGISTER.md:9
- internal receipt: query "project declares no decision register" | repo squiddy@0a3cfcce41827a1b5c8d818b261d89ff36d50f09 | hits docs/M-002_delivery_report.md:79, docs/EXTRACTION_DESIGN_SPEC.md:283, docs/decisions/register/01002_squiddy-r-213_accept.yaml:1, docs/decisions/register/00320_squiddy-di-169_accept.yaml:1, docs/decisions/register/00972_squiddy-r-202_accept.yaml:1, docs/design/2026-10-21_DN-049_ai_readiness_kg_onto_the_kit.md:59, docs/decisions/register/00357_squiddy-di-178_accept.yaml:1, docs/decisions/register/00436_squiddy-di-178_amend.yaml:1, docs/decisions/REGISTER.md:9, docs/design/2026-09-29_knowledge_factory_conops.md:48, docs/DECISIONS_INHERITED.md:508, docs/DECISIONS_INHERITED.md:251, docs/EXTRACTION_DESIGN_SPEC.md:344, docs/EXTRACTION_DESIGN_SPEC.md:500
- internal receipt: query "project declares no decision register" | repo ai-readiness-kg@662295e212f7c4bb132cbeb2ade1e75ff2a4f218 | hits none
- internal receipt: query "project declares no decision register" | repo arnold@6114fe89226c455af64e3142bd6bee841769aeeb | hits none
- internal receipt: query "project declares no decision register" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "project declares no decision register" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "project declares no decision register" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "generated region between markers in a hand written markdown file" | repo seldon@06ddffae306910aa5840c4d55346e63a45167a27 | hits none
- internal receipt: query "generated region between markers in a hand written markdown file" | repo squiddy@0a3cfcce41827a1b5c8d818b261d89ff36d50f09 | hits none
- internal receipt: query "generated region between markers in a hand written markdown file" | repo ai-readiness-kg@662295e212f7c4bb132cbeb2ade1e75ff2a4f218 | hits none
- internal receipt: query "generated region between markers in a hand written markdown file" | repo arnold@6114fe89226c455af64e3142bd6bee841769aeeb | hits none
- internal receipt: query "generated region between markers in a hand written markdown file" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "generated region between markers in a hand written markdown file" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "generated region between markers in a hand written markdown file" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "requirements traceability matrix rendered from the graph" | repo seldon@06ddffae306910aa5840c4d55346e63a45167a27 | hits none
- internal receipt: query "requirements traceability matrix rendered from the graph" | repo squiddy@0a3cfcce41827a1b5c8d818b261d89ff36d50f09 | hits none
- internal receipt: query "requirements traceability matrix rendered from the graph" | repo ai-readiness-kg@662295e212f7c4bb132cbeb2ade1e75ff2a4f218 | hits none
- internal receipt: query "requirements traceability matrix rendered from the graph" | repo arnold@6114fe89226c455af64e3142bd6bee841769aeeb | hits none
- internal receipt: query "requirements traceability matrix rendered from the graph" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "requirements traceability matrix rendered from the graph" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "requirements traceability matrix rendered from the graph" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none

The internal arm found AD-013's declaration of the type, AD-030's mention of it and squiddy's competency
questions naming it; no repository loads or renders requirements, and no note rules on a project without a
register beyond AD-033-R1.

## 3. Rulings

- **AD-013-R1. A requirement is a graph artifact: an `SRS_Requirement` with `requirement_id` (unique in the project), `description` (the statement), `set_by` (its source, verbatim), `document` and `section` (the projection and the heading it belongs to), and its state on the domain's machine; it is `derived_from` its source (a Document, DesignNote, ResearchTask, Decision, ArchitecturalDecision or a parent requirement), `verified_by` a test `Script`, and `satisfies` points at it from the ResearchTask, Script, Result or PaperSection that meets it; a requirement reaches `verified` only with at least one `verified_by` edge.**
  A project's status words map to states through `seldon.yaml` `requirements.status_map`; a status the map does not
  name leaves the requirement where it is and is listed. The verbatim columns of a load source (`verified_by_text`,
  `validated_by`, `satisfied_by_text`, `status_text`) are kept on the node, so a projection reproduces the source's
  wording while the edges carry the trace. The task text asked for `satisfies` from the note the `Set by` column
  names; a note does not satisfy a requirement, it is its source, so that column becomes `derived_from` (29148's
  source attribute, SysML's derive), and `satisfies` comes from a task the status names.

- **AD-013-R2. A requirements table and a requirements traceability matrix are projections of the graph: `seldon docs generate requirements` and `seldon docs generate rtm` render the projections `seldon.yaml` `docs.projections` declares, replacing only the blocks between `seldon:projection` markers, stamp each file with the graph revision (the sha256 of what it renders), and commit the files they changed, path-scoped, through the hooks; a markdown requirements table is a load source for `seldon req import`, idempotent on the id, and never the truth.**
  A counts block renders the counts sentence from the graph, so a sentence kept identical by hand in several files
  (HB-134R2's ratchet) is retired. `seldon req import --mark` puts the markers around the tables it loaded, once.
  `seldon req add` creates or updates one requirement.

- **AD-013-R3. `seldon docs check` and `seldon verify` report every requirement with no `verified_by` edge and every projection whose file differs from a fresh render (the graph moved, or the file was edited by hand); the finding is advisory, as a stale Result is, and names the command that clears it.**

- **AD-033-R13. A Seldon-managed project with no `decisions:` block is told so: `seldon init`, `seldon go` and `seldon verify` report "no decision register declared (AD-033); rulings made in this project have no record", and `seldon project new` declares one by default (`decisions.repository: <the directory's name>`).**
  AD-033-R1 already makes the register every task-registering repository's; what was missing was a reader. `verify`
  warns and does not fail: declaring the register is the project's own one-block act, and a Tier A failure would hold
  every task in a project that has not yet made it. A project declares its register itself; this ruling does not
  write one into an existing project.

## 4. Details

1. **The load route (SEL-032's question).** `seldon req import <file>` reads every pipe table whose header names an
   id column and a statement column (defaults `ID` and `Requirement` or `Criterion`; `--id-column` and the
   `requirements.columns` block override). A `Key | File` table in the same file is the key map for `Set by`. A test
   reference is SEL-021's grammar (`<path>::<node>`), or a backticked test file followed by backticked test names,
   or a test file alone (a pytest node id too).
2. **The revision.** A projection's header names the sha256 of the rows it renders, not a timestamp, so rendering
   twice from an unchanged graph writes the same bytes and commits nothing.
3. **What stays hand-written.** Prose outside the markers, tables that are not requirements (hazbrief's Set-by keys
   and its F-n findings) and any export a project builds from the projection (hazbrief's `rtm.md`, written by its own
   tool from the rendered table).
4. **The register route after the fact (SEL-031's third question).** One block, `decisions: {repository:
   <name>}`; records then go in through `seldon decision propose|accept --from <yaml>`. A record whose source is a
   chat cites it as a receipt (the URL and the date) with `--operator-stated`; its `source` is the design note that
   records the ruling where one exists, and otherwise the RESULT or handoff that quotes it.
