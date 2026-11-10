# AD-013 ADDENDUM 02: a requirement is authored once, every other cell is computed, a generated block is never a second source, and a test declares what it verifies

**Date:** 2026-11-09. **Status:** Accepted. Implemented by SEL-035
(`cc_tasks/2026-11-09_SEL-035_a_requirement_is_authored_once_every_other_cell_is_computed_and_a_generated_block_is_never_a_second_source.md`),
from the OODA on SEL-033 (review findings `83b09573` and `1cc32488`; part (a) of `f42b75b2`). **Amends:** AD-013-R1 and
AD-013-R2 (AD-013 ADDENDUM 01). **Extends:** AD-013, AD-013 ADDENDUM 01. **Depends on:** AD-001, AD-012, AD-030
section 4, AD-036, AD-038-R15, SEL-021. Five rulings: AD-013-R1 and R2 amended, AD-013-R4 to R6 new.
**Code:** `seldon/core/requirements.py`; `seldon/core/req_trace.py`; `seldon/core/req_migrate.py`;
`seldon/commands/req.py`; `seldon/commands/docs.py`; `seldon/commands/verify.py` (`check_requirements`);
`seldon/core/project_new.py`; `seldon/domain/research.yaml`.
**Tests:** `tests/test_sel035_authored_once.py`, `tests/test_sel033_requirements.py`.

## 1. Evidence

Measured on hazbrief-mcp's graph on 2026-11-09, after SEL-033 (read-only; `/tmp/sel035/survey.py`):

1. **One fact, two places.** 226 `SRS_Requirement` nodes: 226 carry `status_text`, 226 `verified_by_text`, 161
   `validated_by`, 65 `satisfied_by_text` and 59 `decision_text`, each beside the state or the edge that is the same
   fact. The projection renders the text, so SEL-033's "214 rows byte-identical" was a storage round trip, not a render
   from the edges. Already, before any later change: 19 rows say `satisfied`, `changed` or `met` while their state is
   `implemented`, because AD-013-R1 held them below `verified` for want of a test, and the cell does not say so.
2. **Two sources for one table.** AD-013-R2 says a markdown table is never the truth, and the return to hazbrief-mcp
   (HB-146 step 1) offered "or edit the table and re-run `seldon req import`" inside the blocks the renderer replaces.
   `seldon docs generate requirements` overwrites a hand-edited block without a word (SEL-035 Part B).
3. **The verification column is typed, then parsed.** A `verified_by` edge exists because a cell named a test in one
   of three text forms. 21 RTM rows name a harness, "inspection", "judged, not tested", a commit pair or bare function
   names, and count as unverified with no record of how they were checked.
4. **A vocabulary finer than the machine.** hazbrief-mcp maps nine status words onto four states, in two documents
   with two vocabularies (`satisfied`, `changed` / `met`, `partial`, `not met` all reach `verified` or `accepted`). A
   state label alone cannot say `changed` or `partial`; the word is a qualifier of the state, not the state.

## 2. Prior art

### External

Fetched by the Desktop thread on 2026-11-09 and carried in the task file, because this task runs with no network
(AD-036-R1's web receipt records that fetch). Each source is an entry in `graphs/seldon-biblio`
(`intake/seeds.yaml`, block "AD-013 ADDENDUM 01 section 2 and SEL-035", SEL-036); the entry id is given beside each so
that an AD-036-R22 bridge run can resolve these citations without a second reading. The served release of
seldon-biblio was absent from the primary checkout when this note was verified, so no receipt names
`graph seldon-biblio` (SEL-035 ADDENDUM 01 section 3).

- **Doorstop** (`sw_doorstop`; Browning and Adams, "Doorstop: Text-Based Requirements Management Using Version
  Control", JSEA 2014, `browning2014doorstop`, metadata only). One item, one YAML file; the published document is
  generated and never edited; a `reviewed` fingerprint makes a child link suspect when its parent changes. Adopted:
  one authored record per requirement (R1), a view is output only (R2). Not adopted here: the suspect-link
  fingerprint, which is a later task's.
- **OpenFastTrace** (`sw_openfasttrace`). The task file cited `doc/user_guide.md`; that path returned 404 on
  2026-11-09 (SEL-036 `evidence/sel036/units.jsonl`, `texts_moved`) and the guide is now at the URL below; the held
  page is the guide's index. The covering artifact declares coverage by a tag, and the tracer computes each item's
  status (covered, uncovered, outdated, orphaned). Adopted: R5 (the test declares the link) and R4 (status is
  computed, never typed).
- **StrictDoc** (`sw_strictdoc`). The matrix and the coverage screens are exports; source and test files link to
  requirements by markers, bound to their function by language-aware parsing. Adopted: R5's AST binding of a marker
  to its test node.
- **sphinx-needs** (`sw_sphinx_needs`, `needtable` and dynamic functions). A need is defined once; a table is a filter
  over needs; a field that depends on other needs is a function evaluated at build. Adopted: R4.
- **Cog** (`sw_cog`, `running.html`). `-c` writes a checksum beside each generated block; an edited block stops the
  next run instead of being overwritten; `--check` fails when a rerun would change the file. Adopted: R2's refusal and
  its `--discard-edits` override, with the revision stamp as the checksum.
- **ISO/IEC/IEEE 15288 and 29148** (`iso15288_2023`, `iso29148_2018`; `access: purchase`, metadata only, not read) and
  **INCOSE verification methods** (`scukanec2010verification`, `argondigital_verification_methods`): inspection,
  analysis, demonstration and test, carried per requirement in a verification cross-reference matrix. Adopted: R1's
  `verification_method` and R6.
- **Requiem** (`sw_requiem`, added under SEL-035 by SEL-036): suspect links by fingerprint, the nearest prior art for
  Doorstop's `reviewed` field. Considered and not adopted, for the same reason as Doorstop's fingerprint: no ruling
  here makes links suspect.

Not adopted as the store: each tool keeps its truth in files, and Seldon keeps it in the event log, which is the same
rule one level down (AD-001). Their shape is what is adopted.

- web receipt: url https://doorstop-dev.github.io/doorstop/ | retrieved 2026-11-09
- web receipt: url https://github.com/itsallcode/openfasttrace/blob/main/doc/user_guide/user_guide.md | retrieved 2026-11-09
- web receipt: url https://strictdoc.readthedocs.io/en/stable/ | retrieved 2026-11-09
- web receipt: url https://sphinx-needs.readthedocs.io/en/latest/directives/needtable.html | retrieved 2026-11-09
- web receipt: url https://cog.readthedocs.io/en/latest/running.html | retrieved 2026-11-09

The library arm searched squiddy's library (receipts below). As SEL-036 Part F found, it answers none of this
domain's queries: its one row on the subject is again the operator's ANTS repository
(`brockwebb/ai-native-traceability-system`, already cited by ADDENDUM 01); the other rows are about model training,
chemistry fingerprints and agent tool calls, and are not cited.

- library receipt: query "requirements traceability tool coverage tag" | graph library | release library_graph_20261106_sq125_c_2026-11-06.json sha256:bbd841d3b5ab8822258c824656a1b80365d3a4707f0456ddb4f73d508a120cd3 | rows lesson:2026-02-22_arXiv_2505_01441#p8:151:1513-1653, lesson:2026-02-22_arXiv_2505_01441#p24:416:746-1330, lesson:2026-02-22_arXiv_2509_08827#p39:511:1295-1456, lesson:2026-08-25_arXiv_2607_02771#p2:53:807-820, lesson:2026-08-25_arXiv_2607_02771#p6:96:3858-4461, lesson:2026-02-02_github_com_brockwebb_ai_native_traceability_system#meta, lesson:2026-02-22_arXiv_2503_10970#p54:536:2738-2928, lesson:2026-02-22_arXiv_2503_10970#p32:282:455-1268, lesson:2026-02-22_arXiv_2503_10970#p51:503:0-2454, lesson:2026-02-22_arXiv_2501_09136#p34:439:51-468, lesson:2026-02-22_arXiv_2407_16741#p21:362:1393-1674, lesson:2026-02-22_arXiv_2407_16741#p21:365:1797-1892, lesson:2026-02-22_arXiv_2407_16741#p21:364:1706-1795, lesson:2026-02-03_arXiv_2311_07509#p22:296:871-1615, lesson:2026-02-03_arXiv_2311_07509#p22:294:398-829, lesson:2026-02-03_arXiv_2311_07509#p23:303:0-806, lesson:2026-02-22_arXiv_2601_01885#p14:466:2290-2399, lesson:2026-02-22_arXiv_2601_01885#p8:322:1166-1600, lesson:2026-02-22_arXiv_2410_21317#p18:343:1787-2537, lesson:2026-02-22_arXiv_2410_21317#p2:26:3308-3316, lesson:2026-02-22_arXiv_2507_21046#p42:555:0-191, lesson:2026-02-22_arXiv_2507_21046#p52:710:0-177, lesson:2026-02-22_arXiv_2507_21046#p52:729:3457-3981, lesson:2026-02-22_arXiv_2405_07960#p16:109:821-986, lesson:2026-05-09_arXiv_2604_23338#p29:396:1334-1824, lesson:2026-05-09_arXiv_2604_23338#p32:442:3403-3531, lesson:2026-05-09_arXiv_2604_23338#p29:394:970-1209, lesson:2026-04-05_arXiv_2603_28589#p6:37:644-713, lesson:2026-04-05_arXiv_2603_28589#p6:38:715-905, lesson:2026-04-05_arXiv_2603_28589#p10:65:67-75, lesson:2026-04-12_arXiv_2407_21783#p44:685:834-892, lesson:2026-04-12_arXiv_2407_21783#p5:60:2021-2250, lesson:2026-02-21_arXiv_2510_09517#p16:300:2325-3174, lesson:2026-02-21_arXiv_2510_09517#p15:255:2215-3777, lesson:2026-02-21_arXiv_2510_09517#p14:203:56-1809, lesson:2026-02-22_arXiv_2502_05453#p427:6510:2360-2429, lesson:2026-02-22_arXiv_2502_05453#p499:7573:2436-2551, lesson:2026-02-22_arXiv_2502_05453#p15:252:960-1070, lesson:2026-02-22_arXiv_2401_16107#p8:218:3948-4145, lesson:2026-02-22_arXiv_2503_19633#p13:109:1248-1279, lesson:2026-02-22_arXiv_2503_19633#p13:110:1281-1327, lesson:2026-02-22_10_18653_v1_2024_findings_acl_259#p6:190:219-644, lesson:2026-02-22_10_18653_v1_2024_findings_acl_259#p6:215:1240-1442, lesson:2026-02-22_10_18653_v1_2024_findings_acl_259#p6:198:746-1075
- library receipt: query "verification method inspection analysis demonstration test" | graph library | release library_graph_20261106_sq125_c_2026-11-06.json sha256:bbd841d3b5ab8822258c824656a1b80365d3a4707f0456ddb4f73d508a120cd3 | rows lesson:2026-02-22_arXiv_2504_07952#p7:124:4462-4560, lesson:2026-02-22_arXiv_2504_07952#p7:130:5254-5719, lesson:2026-02-22_arXiv_2505_14963#p14:118:44-110, lesson:2026-05-09_arXiv_2503_13657#p26:421:1687-1725, lesson:2026-05-09_arXiv_2503_13657#p25:405:2808-3644, lesson:2026-05-09_arXiv_2503_13657#p8:132:2050-2882, lesson:2026-03-17_arXiv_2602_12670#p16:354:998-1395, lesson:2026-03-17_arXiv_2602_12670#p37:683:1874-2276, lesson:2026-03-17_arXiv_2602_12670#p17:372:2284-2485, lesson:2026-02-22_arXiv_2505_16517#p7:193:1280-1598, lesson:2026-03-17_10_18653_v1_2024_emnlp_main_64#p5:139:0-71, lesson:2026-03-17_10_18653_v1_2024_emnlp_main_64#p2:51:463-476, lesson:2026-03-17_10_18653_v1_2024_emnlp_main_64#p2:79:1967-1980, lesson:2026-02-22_arXiv_2410_10762#p10:172:406-560, lesson:2026-02-22_arXiv_2410_10762#p25:550:708-885, lesson:2026-02-22_arXiv_2410_10762#p10:173:562-646, lesson:2026-02-22_arXiv_2305_16504#p16:287:0-245, lesson:2026-02-22_arXiv_2305_16504#p6:136:831-1845, lesson:2026-02-22_arXiv_2305_16504#p7:156:626-723, lesson:2026-02-22_arXiv_2411_04329#p2:33:2107-2337, lesson:2026-02-22_arXiv_2411_04329#p5:138:2453-3049, lesson:2026-02-22_arXiv_2411_04329#p5:130:933-1211, lesson:2026-02-22_arXiv_2110_14168#p10:134:114-225, lesson:2026-02-22_arXiv_2110_14168#p7:76:0-1641, lesson:2026-02-22_arXiv_2110_14168#p12:179:14-662, lesson:2026-02-22_arXiv_2506_04178#p18:289:803-1654, lesson:2026-02-22_arXiv_2506_04178#p31:473:1038-1352, lesson:2026-02-22_arXiv_2506_04178#p31:475:2134-2868, lesson:2026-02-22_arXiv_2412_05255#p5:129:3313-3748, lesson:2026-02-22_arXiv_2412_05255#p4:74:657-670, lesson:2026-02-22_arXiv_2412_05255#p45:617:2480-2626, lesson:2026-02-22_arXiv_2505_19768#p3:53:5808-6472, lesson:2026-02-22_arXiv_2505_19768#p2:38:419-1695, lesson:2026-02-22_arXiv_2505_19768#p7:187:750-1594, lesson:2026-02-22_arXiv_2506_01341#p4:112:2640-3068, lesson:2026-02-22_arXiv_2506_01341#p18:317:913-1135, lesson:2026-02-22_arXiv_2506_01341#p25:506:1354-1682, lesson:2026-03-17_arXiv_2602_03587#p40:853:2120-2249, lesson:2026-02-22_arXiv_2510_04618#p7:95:2213-2264, lesson:2026-02-22_arXiv_2510_04618#p9:136:1760-1811, lesson:2026-02-22_arXiv_2510_04618#p17:243:0-93, lesson:2026-03-27_arXiv_2509_18970#p11:257:2863-3645, lesson:2026-03-27_arXiv_2509_18970#p11:258:3647-4929, lesson:2026-03-27_arXiv_2509_18970#p11:240:377-389, lesson:2026-02-22_arXiv_2401_07128#p7:224:3432-4301, lesson:2026-02-22_arXiv_2401_07128#p25:606:8924-8996, lesson:2026-02-22_arXiv_2310_14628#p5:138:2008-3693, lesson:2026-02-22_arXiv_2310_14628#p4:103:3719-4070, lesson:2026-02-22_arXiv_2310_14628#p4:101:2539-3014, lesson:2026-03-17_arXiv_2512_17102#p18:410:3116-3134, lesson:2026-03-17_arXiv_2512_17102#p16:355:2216-2333
- library receipt: query "suspect link fingerprint requirement" | graph library | release library_graph_20261106_sq125_c_2026-11-06.json sha256:bbd841d3b5ab8822258c824656a1b80365d3a4707f0456ddb4f73d508a120cd3 | rows lesson:2026-02-22_arXiv_2311_10776#p8:94:1225-1284, lesson:2026-02-22_arXiv_2311_10776#p13:167:2213-2295, lesson:2026-02-22_arXiv_2311_10776#p8:93:617-1223, lesson:2026-02-22_arXiv_2410_05080#p36:535:3135-3202, lesson:2026-02-22_arXiv_2410_05080#p31:368:1968-2113, lesson:2026-02-22_arXiv_2410_05080#p43:703:594-628, lesson:2026-02-22_arXiv_2112_09332#p15:268:739-1121, lesson:2026-02-22_arXiv_2112_09332#p15:267:618-737, lesson:2026-02-22_arXiv_2310_02172#p7:126:1406-1428, lesson:2026-02-22_arXiv_2310_02172#p7:111:983-1009, lesson:2026-02-22_arXiv_2310_02172#p7:119:1212-1238, lesson:2026-02-22_arXiv_2410_04223#p13:365:308-441, lesson:2026-02-22_arXiv_2501_13299#p10:195:160-382, lesson:2026-02-22_arXiv_2506_21506#p40:498:1690-1965, lesson:2026-02-22_arXiv_2506_21506#p40:502:2199-2305, lesson:2026-02-22_arXiv_2506_21506#p43:560:377-625, lesson:2026-02-22_arXiv_2410_16946#p22:386:2368-2433, lesson:2026-02-22_arXiv_2410_16946#p21:364:150-167, lesson:2026-02-22_arXiv_2410_16946#p7:109:1304-1321, lesson:2026-07-15_arXiv_2003_02320#p93:1254:536-676, lesson:2026-07-15_arXiv_2003_02320#p92:1237:0-311, lesson:2026-07-15_arXiv_2003_02320#p102:1389:885-1260, lesson:2026-02-22_arXiv_2306_05301#p10:184:2705-2718, lesson:2026-02-22_arXiv_2306_05301#p11:199:1502-1515, lesson:2026-02-22_arXiv_2306_05301#p12:212:1594-1607, lesson:2026-02-22_arXiv_2411_15692#p8:114:2304-2740, lesson:2026-02-22_arXiv_2411_15692#p2:35:901-936, lesson:2026-02-22_arXiv_2411_15692#p10:152:871-1113, lesson:2026-04-12_arXiv_2403_05530#p61:978:1334-1565, lesson:2026-04-12_arXiv_2403_05530#p61:992:1976-2204, lesson:2026-04-12_arXiv_2403_05530#p61:970:0-668, lesson:2026-02-22_arXiv_2311_05657#p18:314:968-1262, lesson:2026-03-17_arXiv_2601_10338#p19:471:974-1197, lesson:2026-03-17_arXiv_2601_10338#p6:162:6659-7035, lesson:2026-03-17_arXiv_2601_10338#p18:432:476-741, lesson:2026-02-22_arXiv_2503_22164#p20:219:1297-1665, lesson:2026-02-22_arXiv_2601_03515#p19:465:1561-1593, lesson:2026-02-22_arXiv_2601_03515#p19:466:1595-1622, lesson:2026-02-22_arXiv_2601_03515#p19:468:1654-1683, lesson:2026-02-22_arXiv_2504_19314#p5:70:0-701, lesson:2026-02-22_arXiv_2505_10468#p18:331:623-682, lesson:2026-02-22_arXiv_2505_10468#p19:359:349-353, lesson:2026-02-22_arXiv_2505_10468#p19:365:621-625, biolink_model_spec#meta, lesson:2026-01-28_10_1007_s11135_017_0533_4#p31:455:195-206, lesson:2026-01-28_10_1007_s11135_017_0533_4#p14:127:357-399

### Internal

- **Seldon's own record:** AD-013 ADDENDUM 01 (R1 kept the load source's verbatim cells on the node, the thing R1 now
  removes; R2's marker blocks and revision stamp, which R2 now makes one-directional); SEL-021 (a test node is a
  `Script` with `test_node`, the target R5 links); AD-030 section 4 (the closed edge set on governed documents, which
  keeps `Document` out of R6's evidence targets as it kept it out of R1's sources); `check_prior_art` (`seldon verify`
  reads verdicts and does not run them, the precedent for R5's verify-reads-the-plan).
- The internal arm found nothing else: no repository declares a test's requirement by a marker, types verification
  methods, or refuses an edited generated block. The two hits in squiddy's and arnold's registers are lexical
  matches over a whole register paragraph and say nothing on the subject.

- internal receipt: query "pytest marker declares the requirement a test verifies" | repo seldon@358d6f967c155c357b815c2b492513f585971bd5 | hits none
- internal receipt: query "pytest marker declares the requirement a test verifies" | repo squiddy@aa2feb38753e8bceb8ea0cbac8e7df82804e002a | hits docs/decisions/REGISTER.md:9
- internal receipt: query "pytest marker declares the requirement a test verifies" | repo ai-readiness-kg@662295e212f7c4bb132cbeb2ade1e75ff2a4f218 | hits none
- internal receipt: query "pytest marker declares the requirement a test verifies" | repo arnold@c603e049eefe78570b4fac66d5e819626693f801 | hits none
- internal receipt: query "pytest marker declares the requirement a test verifies" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "pytest marker declares the requirement a test verifies" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "pytest marker declares the requirement a test verifies" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "verification method inspection analysis demonstration" | repo seldon@358d6f967c155c357b815c2b492513f585971bd5 | hits none
- internal receipt: query "verification method inspection analysis demonstration" | repo squiddy@aa2feb38753e8bceb8ea0cbac8e7df82804e002a | hits none
- internal receipt: query "verification method inspection analysis demonstration" | repo ai-readiness-kg@662295e212f7c4bb132cbeb2ade1e75ff2a4f218 | hits none
- internal receipt: query "verification method inspection analysis demonstration" | repo arnold@c603e049eefe78570b4fac66d5e819626693f801 | hits none
- internal receipt: query "verification method inspection analysis demonstration" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "verification method inspection analysis demonstration" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "verification method inspection analysis demonstration" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "generated block edited by hand refuse checksum" | repo seldon@358d6f967c155c357b815c2b492513f585971bd5 | hits none
- internal receipt: query "generated block edited by hand refuse checksum" | repo squiddy@aa2feb38753e8bceb8ea0cbac8e7df82804e002a | hits none
- internal receipt: query "generated block edited by hand refuse checksum" | repo ai-readiness-kg@662295e212f7c4bb132cbeb2ade1e75ff2a4f218 | hits none
- internal receipt: query "generated block edited by hand refuse checksum" | repo arnold@c603e049eefe78570b4fac66d5e819626693f801 | hits none
- internal receipt: query "generated block edited by hand refuse checksum" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "generated block edited by hand refuse checksum" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "generated block edited by hand refuse checksum" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "status computed from trace links not typed" | repo seldon@358d6f967c155c357b815c2b492513f585971bd5 | hits none
- internal receipt: query "status computed from trace links not typed" | repo squiddy@aa2feb38753e8bceb8ea0cbac8e7df82804e002a | hits none
- internal receipt: query "status computed from trace links not typed" | repo ai-readiness-kg@662295e212f7c4bb132cbeb2ade1e75ff2a4f218 | hits none
- internal receipt: query "status computed from trace links not typed" | repo arnold@c603e049eefe78570b4fac66d5e819626693f801 | hits docs/decisions/REGISTER.md:10
- internal receipt: query "status computed from trace links not typed" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "status computed from trace links not typed" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "status computed from trace links not typed" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "status_text verified_by_text" | repo seldon@358d6f967c155c357b815c2b492513f585971bd5 | hits docs/design/AD-013_ADDENDUM_01_requirements_as_graph_content.md:123, docs/decisions/register/00336_seldon-ad-013-r1_accept.yaml:1
- internal receipt: query "status_text verified_by_text" | repo squiddy@aa2feb38753e8bceb8ea0cbac8e7df82804e002a | hits none
- internal receipt: query "status_text verified_by_text" | repo ai-readiness-kg@662295e212f7c4bb132cbeb2ade1e75ff2a4f218 | hits none
- internal receipt: query "status_text verified_by_text" | repo arnold@c603e049eefe78570b4fac66d5e819626693f801 | hits none
- internal receipt: query "status_text verified_by_text" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "status_text verified_by_text" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "status_text verified_by_text" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none

## 3. Rulings

- **Amends AD-013-R1: A requirement's authored fields are `requirement_id`, `description`, `set_by`, `document`, `section`, `verification_method` (test, inspection, analysis or demonstration; default test) and `note` (free text, optional); nothing else about it is stored as text, and a load source's verbatim cells (`status_text`, `verified_by_text`, `satisfied_by_text`, `validated_by`, `decision_text`) are not kept, because what each said is an edge, the state, the method or the note.**
  The rest of AD-013-R1 stands: the requirement is `derived_from` its source, `verified_by` what verifies it,
  `satisfies` points at it from what meets it, and it reaches `verified` only with a `verified_by` edge (for the
  method, AD-013-R6). The task named four columns; `decision_text`, added for hazbrief-mcp's `Decision` column
  (HB-144), is the fifth of the same kind, and its trace is the `derived_from` edges to register records.

- **AD-013-R4. Every cell of a projection that is not an authored field is computed at render: Status is the state's label (the projection's `state_labels`, else `requirements.state_labels`, else the state's name) followed by `: ` and the note when there is one; Verified-by lists the `verified_by` targets; Satisfied-by the `satisfies` sources; Derived-from the `derived_from` targets; Decision the `derived_from` targets that are register records; and a column whose source is none of these and no authored field is refused when the projection is read.**
  One refinement, from evidence item 4: a note that opens with a word `requirements.status_map` maps to the
  requirement's current state is rendered without the label, because the word is the project's finer name for that
  state (`changed`, `partial`, `not met`); when the state moves, the word no longer maps to it and the label is
  prefixed, so a stale qualifier shows rather than hides. A requirement with no `verified_by` edge renders the
  projection's `none_text` when its method is test, and `<method>: <none_text>` otherwise. `{status:<word>}` in a
  counts template counts the rendered Status cells that open with the word.

- **Amends AD-013-R2: A table inside projection markers is output only: `seldon req import` refuses a file that carries projection markers and names `seldon req add` and `seldon req update`, so import is the onboarding route for an unmarked table and nothing else; `seldon docs generate` refuses a file whose marker blocks no longer hash to the revision stamped on its line 1, prints the rows that differ, and writes nothing, and `--discard-edits` is the only override; the rest of AD-013-R2 stands.**
  The stamp is Cog's checksum: the revision is the sha256 of the rendered blocks, so a block edited by hand no longer
  hashes to it. A file the graph has moved under, but nobody edited, still hashes to its stamp and is rendered. The
  return to hazbrief-mcp's "or edit the table and re-run `seldon req import`" (HB-146 step 1) is withdrawn.

- **AD-013-R5. A test declares what it verifies: `@pytest.mark.verifies("VR-012", ...)` on a test function or class; `seldon req trace` reads the project's test files with the standard library's `ast` (no import, no collection), makes a `verified_by` edge marked `declared_by: marker` from each named requirement to the SEL-021 test `Script` of the marked node, removes a marker edge whose marker is gone and the imported test edges of a requirement a marker now names, and lists a marker that names no requirement and a file that does not parse; `seldon verify` reports the trace's plan; and no new text grammar for test references is added.**
  `seldon verify` is the commit gate and reads; it does not write (as `check_prior_art` reads verdicts it does not
  run), so it reports the edges a trace would add or remove and the marker findings, and `seldon req trace` writes
  them through the event log. Edges SEL-033 imported from table cells stay until a marker names their requirement.
  The trace moves no state; a `verified` requirement left with no verifying edge is reported by `seldon verify`.

- **AD-013-R6. Verification counts follow the method: `seldon verify` and `seldon docs check` report the requirements whose method is test and that have no test separately from those whose method is inspection, analysis or demonstration and that have no evidence, and such a requirement reaches `verified` on a `verified_by` edge to the Result or Issue that records its evidence.**
  The task said "Document, Result or Issue". A governed `Document` is left out, as AD-013-R1 left it out of the
  sources: the domain's endpoint sets are independent, so admitting it would admit `Issue -> Document`, which AD-030
  section 4's closed edge set refuses. Evidence that exists only as a document is registered as a Result or recorded
  in an Issue.

## 4. Details

1. **The migration (`seldon req migrate`, once, idempotent, through the event log).** Per requirement that still
   carries a verbatim cell: the status cell's word, when it is the state's label, is dropped and the rest becomes the
   note; a word that maps to the state but is not its label is kept at the head of the note (R4's qualifier); a word
   that maps to another state, or none, keeps the whole cell in the note and is listed. A verification or validation
   cell that is only the none text is dropped; one whose every word is a test reference an edge carries is dropped;
   any other is kept whole in the note under its column's name (`verified by: ...`, `validated by: ...`), and one
   that names inspection, analysis, demonstration or a judgment sets `verification_method` (a judgment is
   inspection). A satisfied-by or decision cell whose every key an edge carries is dropped; any other is kept in the
   note under its name and listed. Nothing is dropped that no edge carries. Then the five properties are removed.
2. **Editing after this addendum.** `seldon req add <id>` creates; `seldon req update <id>` changes the authored
   fields (`--statement`, `--set-by`, `--section`, `--document`, `--method`, `--note`), moves the state (`--state`,
   walked on the domain machine, `verified` only with a qualifying edge), and links evidence (`--evidence <artifact
   id>`, a Result or Issue). Then `seldon docs generate requirements` and `rtm`.
3. **The marker.** `seldon project new` registers it in the new project's pytest configuration; an existing project
   adds one line under `[tool.pytest.ini_options]` in `pyproject.toml`: `markers = ["verifies(*ids): the
   requirements this test verifies (AD-013-R5)"]`. A class marker binds the class's node (`path::Class`); a method's
   binds `path::Class::test`; a parametrized test binds its function, not each case. Test files are those under
   `requirements.test_paths` (default `tests`) named `test_*.py` or `*_test.py`.
