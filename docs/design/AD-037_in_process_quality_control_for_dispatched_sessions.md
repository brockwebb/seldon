# AD-037: In-process quality control for dispatched sessions. Checks run by execution first; a reading judge is the next tier up and is calibrated for self-preference; four inspection stations sit inside every long session

**Date:** 2026-10-11
**Status:** Accepted (L4). Decided by the squiddy/seldon Desktop session from the 2026-10-11 workbench notebook's section 4 positions.
**Builds on:** AD-032 FC-10 (statistical process control), FC-27 (positive controls), FC-28 (andon), FC-29 (huddle). Those controls are proposed for factory stages; this note specifies them for Claude Code sessions launched by the dispatcher.
**Amends:** AD-032 FC-33's rater rule (AD-037-R10).
**Evidence:** `/Users/brock/GitHub/workbench/2026-10-11_judge_bias_and_inprocess_qc/NOTEBOOK.md`, filed by QC-001.
**Implemented by:** QC-001, which finalizes this note's internal receipts before it can be committed (AD-036-R4), and QC-002, authored after QC-001's calibration measurement.

## 1. The condition

Dispatched sessions run for hours with no inspection between launch and RESULT. This week's record:

- **Wrong premises surface too late.** Every RESULT this week lists "premises found wrong" (MODEL-001, PA-001, HOOK-001, SQ-010). They are found mid-run or at the end, never before launch.
- **Defects ship inside green runs.** MODEL-001 shipped implicit effort under a green suite. AD-035's rulings went unparsed and uncounted.
- **SQ-010 ran blind.** It had no checkpoint on disk and filled the volume's last 4.4 GB before anyone looked.
- **The one judge calibration on record does not measure self-preference.** DN-022 calibrated its judge with ABBA counterbalancing and replicate kappa. Those measure position bias and test-retest reliability, not self-preference (notebook section 3).

The operator's rule for judges (2026-10-11):
- the next higher tier checks the work;
- no paid ensemble and no second API;
- in-process evaluation inside long-running agentic processes, framed as process control.

## 2. Prior art

### External

**Sources S1 to S8 were fetched on 2026-10-11 by the ai-readiness-kg Desktop session** (notebook section 2). Each was read at its abstract or conclusion, not in full.

**The operator puts no stock in LLM-behaviour findings from 2024 or earlier.** S9 (2024) is cited only as the origin of a finding S1 replicates in 2026. S8 (preprint October 2024, ICML 2025) is supporting evidence only; S7 carries the in-process claim.

- web receipt: url https://arxiv.org/abs/2604.06996 | retrieved 2026-10-11
- web receipt: url https://doi.org/10.1609/aaai.v40i44.41105 | retrieved 2026-10-11
- web receipt: url https://arxiv.org/abs/2508.09724 | retrieved 2026-10-11
- web receipt: url https://arxiv.org/abs/2608.00243 | retrieved 2026-10-11
- web receipt: url https://arxiv.org/abs/2502.08788 | retrieved 2026-10-11
- web receipt: url https://arxiv.org/abs/2609.35875 | retrieved 2026-10-11
- web receipt: url https://arxiv.org/abs/2609.14637 | retrieved 2026-10-11
- web receipt: url https://arxiv.org/abs/2410.10934 | retrieved 2026-10-11
- web receipt: url https://saemobilus.sae.org/standards/as9102b-aerospace-first-article-inspection-requirement | retrieved 2026-10-11
- web receipt: url https://www.pmi.org/learning/library/earned-value-controlling-forecasting-performance-7653 | retrieved 2026-10-11

**What they establish:**

- **Judges favor their own family, even on checkable criteria.** S1, Pombal, Rei and Martins 2026, arXiv:2604.06996: on objective, programmatically verifiable rubrics the generator failed, judges were more than 50% more likely to mark the rubric satisfied when the output was their own. The bias extends to the judge's model family.
  - Consequence: a Sonnet checking Haiku is not free of family bias. Anything a program can decide must not be read by a judge (R1).
  - The bias is measured, not assumed (R3).
- **Obfuscation helps only partly.** S2, Mahbub and Feng 2026 (AAAI 40): light perturbation of authorship reduces self-preference. Fuller style neutralization lets it recover, so obfuscation is a partial fix (R2, top tier).
- **The bias varies by judge.** S3, arXiv:2508.09724: self-preference ranges from -38% to +90% across judges. It must be measured per judge on this portfolio's work, never borrowed (R3).
- **Same-model panels do not help.** S4, Ji 2026, arXiv:2608.00243: a homogeneous three-agent panel went from +8.5 to -4.4 points against a single agent across six benchmarks, with correlated persona errors. S5, arXiv:2502.08788: debate often fails to beat a single agent; model heterogeneity is what helps. Together they rule out same-model persona panels (R4).
- **Capability beats diversity.** S6, arXiv:2609.35875: accuracy rises with member capability, not diversity. This supports a higher-tier checker. The study is of small models, so its transfer to frontier tiers is unmeasured.
- **Stage-wise review inside a run pays.** S7, DynSTEER 2026, arXiv:2609.14637: stage-wise evaluation at key execution nodes and early termination of unrecoverable runs saved 17.74% of execution steps (R6 b and c).
- **A judge with tools beats a reading judge.** S8, Zhuge et al., arXiv:2410.10934: an agent judge that inspects intermediate steps with tools matched human consensus about 90% of the time, against about 70% for an LLM judge. It supports R1 and R6, as 2024 work.
- **First article inspection.** SAE AS9102B (doi:10.4271/AS9102B): the first part off a new or changed process is inspected to give objective evidence that every requirement was understood, accounted for and verified. Production continues only on that evidence (R6 b).
- **Earned value.** ANSI/EIA-748 earned value management:
  - cost performance index (CPI) = earned value / actual cost;
  - schedule performance index (SPI) = earned value / planned value.

  Both compare work done against budget at milestones (PMI, Earned value: the good, the bad, and the ugly, 2003) (R6 c).

**Library arm.** One `seldon prior-art search --library` query per source title, run 2026-10-12 by QC-001 Part A, one at a time:

- library receipt: query "Self-Preference Bias in Rubric-Based Evaluation of Large Language Models" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-04-03_arXiv_2411_16594#p20:261:0-193, lesson:2026-04-03_arXiv_2411_16594#p16:223:4087-4694, lesson:2026-04-03_arXiv_2411_16594#p13:177:1980-2504, lesson:2026-02-22_arXiv_2408_16673#p15:277:934-1180, lesson:2026-02-22_arXiv_2408_16673#p12:234:46-489, lesson:2026-02-22_arXiv_2408_16673#p14:265:491-714, lesson:2026-04-07_arXiv_2506_14092#p1:13:1986-2115, lesson:2026-04-07_arXiv_2506_14092#p1:12:416-1984, lesson:2026-04-07_arXiv_2506_14092#p14:140:1568-1781, lesson:2026-03-29_arXiv_2412_05579#p55:611:3892-4076, lesson:2026-03-29_arXiv_2412_05579#p52:555:3035-3510, lesson:2026-03-29_arXiv_2412_05579#p49:507:4853-5046, lesson:2026-02-22_arXiv_2504_15585#p62:1409:3005-3244, lesson:2026-02-22_arXiv_2504_15585#p59:1346:2251-3071, lesson:2026-02-22_arXiv_2504_15585#p59:1345:2054-2249, lesson:2026-05-09_arXiv_2505_08245#p55:800:504-934, lesson:2026-05-09_arXiv_2505_08245#p57:829:0-181, lesson:2026-05-09_arXiv_2505_08245#p55:805:1762-2042, lesson:2026-02-22_arXiv_2405_20309#p1:0:0-38, lesson:2026-02-22_arXiv_2405_20309#p13:226:302-484, lesson:2026-02-22_arXiv_2405_20309#p11:200:356-509, lesson:2026-02-22_arXiv_2505_08827#p11:190:43-498, lesson:2026-02-22_arXiv_2505_08827#p2:23:2110-2294, lesson:2026-02-22_arXiv_2412_16075#p31:302:1072-1519, lesson:2026-02-22_arXiv_2401_16107#p9:227:2564-2760, lesson:2026-04-03_arXiv_2502_01534#p14:301:3272-3405, lesson:2026-04-03_arXiv_2502_01534#p13:281:1494-1981, lesson:2026-04-03_arXiv_2502_01534#p15:314:3665-3792, lesson:2026-03-29_arXiv_2411_15594#p58:759:4178-4775, lesson:2026-03-29_arXiv_2411_15594#p54:701:41-298, lesson:2026-03-29_arXiv_2411_15594#p61:801:1729-2140, lesson:2026-04-07_arXiv_2511_19956#p6:134:6938-7158, lesson:2026-04-07_arXiv_2511_19956#p1:2:126-1899, lesson:2026-02-22_arXiv_2304_05128#p11:210:0-44, lesson:2026-02-22_arXiv_2304_05128#p12:228:0-44, lesson:2026-02-22_arXiv_2304_05128#p13:249:0-44, lesson:2026-02-22_arXiv_2411_00816#p15:272:2742-3443, lesson:2026-02-22_arXiv_2411_00816#p17:303:2667-3144, lesson:2026-02-22_arXiv_2409_12917#p15:354:1101-1508, lesson:2026-02-22_arXiv_2409_12917#p14:346:2906-3033, lesson:2026-02-22_arXiv_2409_12917#p1:1:11-55, lesson:2026-02-22_arXiv_2507_20534#p31:750:2871-3665, lesson:2026-02-22_arXiv_2507_20534#p12:373:2580-3297, lesson:2026-02-22_arXiv_2507_20534#p22:541:26-305, lesson:2026-02-22_arXiv_2409_18475#p21:191:2175-2390, lesson:2026-02-22_arXiv_2503_09567#p90:1289:2233-2721, lesson:2026-02-22_arXiv_2503_09567#p47:767:3777-3996, lesson:2026-02-22_arXiv_2503_09567#p100:1429:3044-3583, lesson:2026-02-22_arXiv_2410_08164#p14:223:976-1468
- library receipt: query "Mitigating Self-Preference by Authorship Obfuscation" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-02-22_arXiv_2503_09567#p63:946:294-740, lesson:2026-02-22_arXiv_2503_09567#p57:881:2335-2575, lesson:2026-02-22_arXiv_2503_09567#p94:1337:151-658, lesson:2026-04-03_arXiv_2411_16594#p30:399:3948-4294, lesson:2026-04-03_arXiv_2411_16594#p10:141:3231-3895, lesson:2026-04-03_arXiv_2411_16594#p34:497:1055-1223, lesson:2026-02-22_arXiv_2507_21046#p71:972:2786-3015, lesson:2026-02-22_arXiv_2507_21046#p21:284:1733-4195, lesson:2026-02-22_arXiv_2507_21046#p70:956:66-482, lesson:2026-02-22_arXiv_2504_16084#p17:361:3056-3283, lesson:2026-02-22_arXiv_2506_10943#p15:254:1666-1903, lesson:2026-02-22_arXiv_2505_08827#p11:190:43-498, lesson:2026-02-22_arXiv_2505_08827#p7:122:1458-2390, lesson:2026-02-22_arXiv_2505_08827#p2:21:1362-2089, lesson:2026-03-21_arXiv_2602_16935#p18:246:589-836, lesson:2026-03-17_arXiv_2601_10338#p21:576:5503-5726, lesson:2026-03-17_arXiv_2601_10338#p22:602:3874-3899, lesson:2026-03-17_arXiv_2601_10338#p18:433:743-1072, lesson:2026-02-22_arXiv_2505_15872#p34:658:1048-1236, lesson:2026-02-22_arXiv_2505_15872#p30:587:0-1273, lesson:2026-02-22_arXiv_2507_02592#p5:60:0-892, lesson:2026-02-22_arXiv_2507_02592#p2:23:2412-4008, lesson:2026-02-22_arXiv_2510_01524#p10:109:1035-1259, lesson:2026-03-29_arXiv_2412_05579#p41:428:1805-3968, lesson:2026-03-29_arXiv_2412_05579#p58:667:4358-4645, lesson:2026-03-29_arXiv_2412_05579#p17:188:504-2093, lesson:2026-04-12_arXiv_2303_08774#p15:236:0-108, lesson:2026-04-12_arXiv_2303_08774#p17:365:4002-4261, lesson:2026-04-12_arXiv_2303_08774#p1:9:3237-3478, lesson:2026-04-07_arXiv_2511_19956#p6:134:6938-7158, lesson:2026-04-07_arXiv_2511_19956#p3:60:2781-2817, lesson:2026-04-07_arXiv_2511_19956#p8:155:3991-4875, lesson:2026-02-22_arXiv_2505_08728#p5:70:1499-3453, lesson:2026-02-22_arXiv_2505_08728#p7:92:1385-1551, lesson:2026-02-22_arXiv_2505_08728#p4:64:2246-3894, lesson:2026-02-22_arXiv_2505_12348#p11:255:1702-1779, lesson:2026-02-22_arXiv_2505_12348#p4:103:868-911, lesson:2026-02-22_arXiv_2505_12348#p4:81:299-342, lesson:2026-02-01_arXiv_2204_02311#p65:1160:1733-1832, lesson:2026-02-01_arXiv_2204_02311#p46:953:5056-5166, lesson:2026-04-03_arXiv_2502_01534#p10:227:46-2174, lesson:2026-04-03_arXiv_2502_01534#p15:314:3665-3792, lesson:2026-04-03_arXiv_2502_01534#p19:368:2534-2761, lesson:2026-02-22_arXiv_2504_15585#p57:1318:5812-5991, lesson:2026-02-22_arXiv_2504_15585#p62:1414:4297-4535, lesson:2026-02-22_arXiv_2504_15585#p23:597:4986-6357, lesson:2026-02-04_arXiv_2503_16233#p5:188:1134-5221, lesson:2026-02-04_arXiv_2503_16233#meta, lesson:2026-02-04_arXiv_2503_16233#p1:12:1769-3360
- library receipt: query "UDA: Unsupervised Debiasing Alignment for Pair-wise LLM-as-a-Judge" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-04-03_arXiv_2411_16594#p6:105:3085-3764, lesson:2026-04-03_arXiv_2411_16594#p2:28:2010-2401, lesson:2026-04-03_arXiv_2411_16594#p24:327:2433-2659, lesson:2026-03-29_arXiv_2411_15594#p29:433:2369-2462, lesson:2026-03-29_arXiv_2411_15594#p60:778:50-321, lesson:2026-03-29_arXiv_2411_15594#p13:187:2110-2267, lesson:2026-02-22_arXiv_2410_10934#p10:178:1390-1786, lesson:2026-02-22_arXiv_2410_10934#p16:262:436-663, lesson:2026-02-22_arXiv_2410_10934#p9:158:0-578, lesson:2026-06-16_arXiv_2602_09801#p25:286:253-609, lesson:2026-06-16_arXiv_2602_09801#p24:276:1435-1729, lesson:2026-06-16_arXiv_2602_09801#p24:273:509-536, lesson:2026-02-22_arXiv_2502_11903#p12:433:4696-5240, lesson:2026-02-22_10_18653_v1_2024_findings_acl_259#p12:374:3378-3451, lesson:2026-02-22_10_18653_v1_2024_findings_acl_259#p13:380:901-1016, lesson:2026-02-22_10_18653_v1_2024_findings_acl_259#p29:642:1453-1569, lesson:2026-06-16_arXiv_2506_11068#p13:198:2571-3836, lesson:2026-06-16_arXiv_2506_11068#p4:68:1639-2812, lesson:2026-06-16_arXiv_2506_11068#p2:39:1297-1799, lesson:2026-02-22_arXiv_2406_14283#p2:13:2212-3383, lesson:2026-03-27_arXiv_2510_07777#p4:58:1267-2183, lesson:2026-03-27_arXiv_2510_07777#p14:217:1387-1735, lesson:2026-03-27_arXiv_2510_07777#p14:206:0-16, lesson:2026-03-29_arXiv_2412_05579#p55:597:75-310, lesson:2026-03-29_arXiv_2412_05579#p38:410:2164-4463, lesson:2026-03-29_arXiv_2412_05579#p56:631:5139-5379, lesson:2026-03-01_arXiv_2602_23271#p5:107:1692-2415, lesson:2026-03-17_arXiv_2303_18223#p62:1237:27-1708, lesson:2026-03-17_arXiv_2303_18223#p41:899:1902-2334, lesson:2026-03-17_arXiv_2303_18223#p36:816:4552-5835, lesson:2026-02-22_arXiv_2411_02337#p19:433:3109-3176, lesson:2026-02-22_arXiv_2503_22732#p49:1223:5268-5485, lesson:2026-02-22_arXiv_2503_22732#p44:1141:2997-4282, lesson:2026-02-22_arXiv_2503_22732#p50:1245:413-630, lesson:2026-03-27_arXiv_2406_12334#p4:74:3505-3579, lesson:2026-05-23_arXiv_2412_04690#p12:115:918-1476, lesson:2026-05-23_arXiv_2412_04690#p3:17:499-992, lesson:2026-05-23_arXiv_2412_04690#p21:223:0-526, lesson:2026-04-03_arXiv_2502_01534#p5:109:3075-3138, lesson:2026-04-03_arXiv_2502_01534#p3:66:268-3468, lesson:2026-04-03_arXiv_2502_01534#p1:2:94-108, lesson:2026-02-22_arXiv_2601_03515#p20:519:2056-2945, lesson:2026-02-22_arXiv_2601_03515#p4:130:1094-1103, lesson:2026-02-22_arXiv_2601_03515#p22:541:0-21, lesson:2026-02-22_arXiv_2505_16938#p30:499:1129-1276, lesson:2026-02-22_arXiv_2503_22164#p19:205:2529-2673
- library receipt: query "More Debate, Same Evidence: Structural Limits of Homogeneous Multi-Agent Groundedness" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-02-22_arXiv_2309_17288#p5:56:20-460, lesson:2026-02-22_arXiv_2309_17288#p2:27:150-161, lesson:2026-03-17_arXiv_2601_04748#p6:132:1833-2649, lesson:2026-03-17_arXiv_2601_04748#p20:395:3323-3878, lesson:2026-03-17_arXiv_2601_04748#p1:6:230-2348, lesson:2026-02-22_arXiv_2510_08529#p11:282:2908-3441, lesson:2026-02-22_arXiv_2510_08529#p9:258:1158-4555, lesson:2026-02-22_arXiv_2510_08529#p9:241:896-1002, lesson:2026-02-22_arXiv_2502_02533#p5:110:851-874, lesson:2026-02-22_arXiv_2502_02533#p21:361:558-601, lesson:2026-02-22_arXiv_2502_02533#p4:67:2947-4454, lesson:2026-02-22_arXiv_2504_16129#p21:751:0-2356, lesson:2026-02-22_arXiv_2504_16129#p22:801:1139-1891, lesson:2026-02-22_arXiv_2504_16129#p35:925:0-1061, lesson:2026-02-22_arXiv_2412_01928#p15:364:1054-1085, lesson:2026-02-22_arXiv_2412_01928#p15:369:1623-1725, lesson:2026-02-22_arXiv_2412_01928#p15:367:1561-1597, lesson:2026-02-22_arXiv_2508_04903#p16:420:2467-2716, lesson:2026-02-22_arXiv_2508_04903#p5:152:253-781, lesson:2026-02-22_arXiv_2507_22606#p6:48:3038-3773, lesson:2026-02-22_arXiv_2507_22606#p16:217:710-929, lesson:2026-02-22_arXiv_2507_22606#p6:41:1452-2147, lesson:2026-02-22_arXiv_2306_07542#p12:181:920-1114, lesson:2026-02-22_arXiv_2410_10762#p4:53:280-331, lesson:2026-02-22_arXiv_2510_05445#p3:18:428-1523, lesson:2026-02-22_arXiv_2510_05445#p18:248:220-433, lesson:2026-02-22_arXiv_2510_05445#p18:254:1359-1372, lesson:2026-02-22_arXiv_2502_18439#p4:69:1415-1473, lesson:2026-02-22_arXiv_2502_18439#p11:315:2509-2690, lesson:2026-02-22_arXiv_2502_18439#p11:316:2692-2906, lesson:2026-02-22_arXiv_2508_07407#p26:360:0-1331, lesson:2026-02-22_arXiv_2508_07407#p4:58:598-749, lesson:2026-02-22_arXiv_2508_07407#p42:543:399-690, lesson:2026-03-13_arXiv_2603_10062#p3:97:1861-2037, lesson:2026-03-13_arXiv_2603_10062#p3:98:2039-2395, lesson:2026-03-13_arXiv_2603_10062#p1:27:1483-2031, lesson:2026-05-09_arXiv_2510_04886#p2:27:3741-4260, lesson:2026-05-09_arXiv_2510_04886#p30:537:1572-1787, lesson:2026-05-09_arXiv_2510_04886#p22:359:705-866, lesson:2026-02-22_arXiv_2506_02718#p5:200:1477-3361, lesson:2026-02-22_arXiv_2506_02718#p5:203:4234-4385, lesson:2026-02-22_arXiv_2506_02718#p8:292:3791-4775, lesson:2026-02-22_arXiv_2508_15144#p3:64:1411-2558, lesson:2026-02-22_arXiv_2508_15144#p7:149:3608-4910, lesson:2026-02-22_arXiv_2409_00717#p12:255:773-918, lesson:2026-02-22_arXiv_2409_00717#p24:667:1510-1663, lesson:2026-02-22_arXiv_2409_00717#p14:290:0-415, lesson:2026-02-22_arXiv_2405_14314#p9:381:328-1589, lesson:2026-02-22_arXiv_2405_14314#p1:11:408-1854, lesson:2026-02-22_arXiv_2405_14314#p1:0:0-71, lesson:2026-01-23_arXiv_2601_08815#p15:187:1110-1639, lesson:2026-01-23_arXiv_2601_08815#p17:212:279-335, lesson:2026-01-23_arXiv_2601_08815#p10:110:21-1077
- library receipt: query "Stop Overvaluing Multi-Agent Debate: We Must Rethink Evaluation and Embrace Model Heterogeneity" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-02-22_arXiv_2412_01928#p15:369:1623-1725, lesson:2026-02-22_arXiv_2412_01928#p15:365:1087-1529, lesson:2026-02-22_arXiv_2412_01928#p15:367:1561-1597, lesson:2026-02-22_arXiv_2508_07407#p22:340:3558-3786, lesson:2026-02-22_arXiv_2508_07407#p29:382:3041-3836, lesson:2026-02-22_arXiv_2508_07407#p4:58:598-749, lesson:2026-02-22_arXiv_2503_09567#p108:1520:0-228, lesson:2026-02-22_arXiv_2503_09567#p108:1532:2660-3131, lesson:2026-02-22_arXiv_2504_09037#p32:405:2397-3954, lesson:2026-02-22_arXiv_2504_09037#p54:585:0-526, lesson:2026-02-22_arXiv_2504_09037#p46:507:665-829, lesson:2026-02-22_arXiv_2505_14996#p11:211:2664-3139, lesson:2026-02-22_arXiv_2505_14996#p22:437:620-1379, lesson:2026-02-22_arXiv_2505_14996#p8:169:2587-3601, lesson:2026-03-29_arXiv_2412_05579#p48:482:2472-2646, lesson:2026-03-29_arXiv_2412_05579#p20:213:1467-2444, lesson:2026-03-29_arXiv_2412_05579#p48:488:4711-5204, lesson:2026-02-22_arXiv_2501_05707#p5:179:2556-3214, lesson:2026-02-22_arXiv_2501_05707#p8:241:1138-3029, lesson:2026-02-22_arXiv_2501_05707#p6:186:213-469, lesson:2026-03-17_arXiv_2303_18223#p81:1461:4-465, lesson:2026-03-17_arXiv_2303_18223#p137:2372:4599-4785, lesson:2026-03-17_arXiv_2303_18223#p131:2269:5129-5315, lesson:2026-02-22_arXiv_2508_08997#p9:153:2586-3061, lesson:2026-02-22_arXiv_2508_08997#p9:154:3063-3358, lesson:2026-02-22_arXiv_2508_08997#p11:168:3926-4166, lesson:2026-02-22_arXiv_2502_02533#p5:110:851-874, lesson:2026-02-22_arXiv_2502_02533#p21:361:558-601, lesson:2026-02-22_arXiv_2502_02533#p13:293:3113-3560, lesson:2026-02-22_arXiv_2504_16129#p14:427:2026-2841, lesson:2026-02-22_arXiv_2504_16129#p14:422:236-375, lesson:2026-02-22_arXiv_2504_16129#p21:751:0-2356, lesson:2026-04-07_arXiv_2509_09705#p14:147:2456-2580, lesson:2026-02-22_arXiv_2510_08529#p11:282:2908-3441, lesson:2026-02-22_arXiv_2510_08529#p9:241:896-1002, lesson:2026-02-22_arXiv_2510_08529#p12:290:1097-1506, lesson:2026-02-22_arXiv_2506_02718#p1:4:397-1800, lesson:2026-02-22_arXiv_2506_02718#p4:108:1978-2530, lesson:2026-02-22_arXiv_2506_02718#p2:10:0-2180, lesson:2026-02-22_arXiv_2410_10762#p4:53:280-331, lesson:2026-02-22_arXiv_2502_18439#p4:69:1415-1473, lesson:2026-02-22_arXiv_2502_18439#p4:70:1475-2388, lesson:2026-02-22_arXiv_2502_18439#p11:315:2509-2690, lesson:2026-02-22_arXiv_2505_05428#p14:361:2249-2793, lesson:2026-03-13_arXiv_2603_10062#p3:97:1861-2037, lesson:2026-03-13_arXiv_2603_10062#p3:98:2039-2395, lesson:2026-02-22_arXiv_2507_21046#p53:732:66-1862, lesson:2026-02-22_arXiv_2507_21046#p76:1043:3152-3404, lesson:2026-02-22_arXiv_2507_21046#p16:220:1638-2758, lesson:2026-02-22_arXiv_2505_16938#p20:364:1082-1142
- library receipt: query "Beyond Symmetric Agents: Cognitive Diversity and Multi-Agent Debate in Small Language Models" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-02-22_arXiv_2403_03031#p9:237:3213-3450, lesson:2026-02-22_arXiv_2403_03031#p9:233:1705-2353, lesson:2026-04-03_arXiv_2411_16594#p18:239:0-236, lesson:2026-02-22_arXiv_2503_18102#p22:152:543-778, lesson:2026-02-22_arXiv_2410_11782#p10:351:2129-2332, lesson:2026-02-22_arXiv_2410_11782#p2:31:5381-5662, lesson:2026-02-22_arXiv_2410_11782#p9:338:3479-3844, lesson:2026-02-22_arXiv_2508_04652#p8:328:3539-3738, lesson:2026-02-22_arXiv_2508_04652#p8:324:2145-2585, lesson:2026-02-22_arXiv_2508_04652#p8:323:1660-2143, lesson:2026-02-22_arXiv_2406_07155#p14:320:46-339, lesson:2026-02-22_arXiv_2406_07155#p17:361:1149-1658, lesson:2026-02-22_arXiv_2406_07155#p12:302:2753-3025, lesson:2026-02-22_arXiv_2502_18439#p11:316:2692-2906, lesson:2026-02-22_arXiv_2502_18439#p4:69:1415-1473, lesson:2026-02-22_arXiv_2502_18439#p1:5:2144-2660, lesson:2026-02-22_arXiv_2506_07398#p12:337:421-650, lesson:2026-02-22_arXiv_2506_07398#p11:331:2359-2827, lesson:2026-02-22_arXiv_2506_07398#p16:391:2461-2983, lesson:2026-02-22_arXiv_2507_08616#p11:222:1192-1490, lesson:2026-02-22_arXiv_2507_08616#p10:213:3247-3468, lesson:2026-02-22_arXiv_2507_08616#p10:207:1223-1364, lesson:2026-02-22_arXiv_2505_14996#p11:211:2664-3139, lesson:2026-02-22_arXiv_2505_14996#p22:441:1458-1534, lesson:2026-02-22_arXiv_2505_14996#p22:444:1646-1748, lesson:2026-03-29_arXiv_2411_15594#p56:730:2661-2939, lesson:2026-03-29_arXiv_2411_15594#p56:727:655-913, lesson:2026-03-29_arXiv_2411_15594#p55:712:267-1222, lesson:2026-02-22_arXiv_2505_05428#p14:361:2249-2793, lesson:2026-03-27_arXiv_2509_18970#p15:361:8977-9218, lesson:2026-03-27_arXiv_2509_18970#p14:324:5318-5558, lesson:2026-03-27_arXiv_2509_18970#p20:469:169-410, lesson:2026-02-22_arXiv_2502_11133#p11:265:354-1145, lesson:2026-02-22_arXiv_2502_11133#p23:470:696-926, lesson:2026-02-22_arXiv_2502_11133#p13:294:153-334, lesson:2026-02-22_arXiv_2410_02506#p13:342:1049-1353, lesson:2026-02-22_arXiv_2410_02506#p15:368:12-553, lesson:2026-02-22_arXiv_2410_02506#p24:539:878-1366, lesson:2026-02-22_arXiv_2510_08529#p11:282:2908-3441, lesson:2026-02-22_arXiv_2510_08529#p12:294:2846-2995, lesson:2026-02-22_arXiv_2510_08529#p12:290:1097-1506, lesson:2026-02-22_arXiv_2508_07407#p42:545:1386-1837, lesson:2026-02-22_arXiv_2508_07407#p23:341:0-508, lesson:2026-02-22_arXiv_2508_07407#p22:340:3558-3786, lesson:2026-02-22_arXiv_2311_10537#p11:266:3333-3882, lesson:2026-02-22_arXiv_2311_10537#p13:292:1156-1613, lesson:2026-02-22_arXiv_2311_10537#p9:234:3484-4078, lesson:2026-02-22_arXiv_2503_01935#p10:257:2364-2636, lesson:2026-02-22_arXiv_2503_01935#p1:13:330-1424, lesson:2026-02-22_arXiv_2503_01935#p4:89:372-387, lesson:2026-02-22_arXiv_2503_09567#p108:1520:0-228, lesson:2026-02-22_arXiv_2503_09567#p108:1532:2660-3131, lesson:2026-02-22_arXiv_2503_09567#p38:653:1429-1922
- library receipt: query "DynSTEER: Dynamic Stage-wise Trajectory Evaluation and Execution-time Review for Agents" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-02-22_arXiv_2503_01935#p34:647:2682-3399, lesson:2026-02-22_arXiv_2503_01935#p5:130:737-2803, lesson:2026-02-22_arXiv_2503_01935#p28:503:0-162, lesson:2026-02-22_arXiv_2503_15478#p5:72:3901-3979, lesson:2026-02-22_arXiv_2504_09037#p29:380:1679-2831, lesson:2026-02-22_arXiv_2504_09037#p30:384:0-1511, lesson:2026-02-22_arXiv_2504_09037#p29:379:1298-1677, lesson:2026-02-22_arXiv_2501_11733#p7:157:1433-4600, lesson:2026-02-22_arXiv_2501_11733#p3:13:0-1707, lesson:2026-02-22_arXiv_2501_11733#p6:143:2187-2447, lesson:2026-02-22_arXiv_2506_09049#p16:317:3374-3616, lesson:2026-02-22_arXiv_2506_09049#p19:328:0-231, lesson:2026-02-22_arXiv_2506_09049#p8:187:117-771, lesson:2026-02-22_arXiv_2501_18944#p18:844:646-1432, lesson:2026-02-22_arXiv_2507_16853#p3:35:3975-4168, lesson:2026-02-22_arXiv_2507_16853#p6:159:1138-2508, lesson:2026-02-22_arXiv_2507_16853#p4:113:3239-3473, lesson:2026-02-22_arXiv_2403_03031#p4:89:196-227, lesson:2026-02-22_arXiv_2403_03031#p4:106:423-1120, lesson:2026-02-22_arXiv_2403_03031#p11:259:1645-2994, lesson:2026-02-22_arXiv_2508_15144#p5:102:2237-3223, lesson:2026-02-22_arXiv_2508_15144#p19:417:4415-5306, lesson:2026-02-22_arXiv_2508_15144#p5:101:0-2235, lesson:2026-02-22_arXiv_2309_17288#p4:51:0-505, lesson:2026-02-22_arXiv_2309_17288#p6:79:2720-2739, lesson:2026-02-22_arXiv_2309_17288#p7:84:0-620, lesson:2026-02-22_arXiv_2507_07445#p12:148:18-444, lesson:2026-02-22_arXiv_2507_07445#p14:211:392-3093, lesson:2026-02-22_arXiv_2507_07445#p4:36:0-2398, lesson:2026-02-22_arXiv_2404_05902#p7:163:1330-1655, lesson:2026-02-22_arXiv_2510_02387#p24:488:736-1090, lesson:2026-02-22_arXiv_2510_02387#p24:483:0-517, lesson:2026-02-22_arXiv_2405_00461#p1:20:3406-3423, lesson:2026-02-22_arXiv_2405_00461#p2:38:1513-1539, lesson:2026-02-22_arXiv_2405_00461#p1:30:4372-4450, lesson:2026-02-22_arXiv_2506_04405#p5:108:2521-3744, lesson:2026-02-22_arXiv_2506_04405#p9:216:1081-2588, lesson:2026-02-22_arXiv_2506_04405#p7:150:2394-4098, lesson:2026-02-22_arXiv_2502_17110#p3:51:1128-1630, lesson:2026-02-22_arXiv_2505_23762#p5:102:1004-1055, lesson:2026-02-22_arXiv_2505_23762#p4:63:1208-1469, lesson:2026-02-22_arXiv_2502_18836#p1:9:283-1597, lesson:2026-02-22_arXiv_2502_18836#p8:211:1646-1771, lesson:2026-02-22_arXiv_2502_18836#p21:666:2335-2418, lesson:2026-02-22_arXiv_2505_22648#p4:65:458-881, lesson:2026-02-22_arXiv_2505_22648#p6:182:2090-2722, lesson:2026-02-22_arXiv_2505_22648#p5:134:2249-3540, lesson:2026-02-22_arXiv_2411_04983#p5:102:4030-4968, lesson:2026-02-22_arXiv_2411_04983#p13:225:1534-2552
- library receipt: query "Agent-as-a-Judge: Evaluate Agents with Agents" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-02-22_arXiv_2410_10934#p18:290:25-79, lesson:2026-02-22_arXiv_2410_10934#p8:146:1894-2288, lesson:2026-02-22_arXiv_2410_10934#p2:40:683-733, lesson:2026-02-22_arXiv_2504_07079#p15:232:3006-3262, lesson:2026-02-22_arXiv_2504_07079#p6:110:1327-1528, lesson:2026-02-22_arXiv_2412_11716#p13:211:2151-2408, lesson:2026-04-03_arXiv_2502_01534#p17:332:1707-1966, lesson:2026-04-03_arXiv_2502_01534#p14:296:2253-2454, lesson:2026-04-03_arXiv_2502_01534#p3:66:268-3468, lesson:2026-02-22_arXiv_2506_21506#p14:241:3023-3286, lesson:2026-02-22_arXiv_2506_21506#p10:185:3053-3599, lesson:2026-02-22_arXiv_2506_21506#p2:31:4884-5282, lesson:2026-03-29_arXiv_2411_15594#p64:850:1975-2274, lesson:2026-03-29_arXiv_2411_15594#p15:236:207-436, lesson:2026-03-29_arXiv_2411_15594#p50:657:924-2331, lesson:2026-04-03_arXiv_2411_16594#p28:377:4320-4583, lesson:2026-04-03_arXiv_2411_16594#p2:17:0-990, lesson:2026-04-03_arXiv_2411_16594#p27:361:0-273, lesson:2026-02-22_arXiv_2505_08638#p14:194:3376-3680, lesson:2026-02-22_arXiv_2505_08638#p11:149:3607-3810, lesson:2026-02-22_arXiv_2601_12538#p132:1287:2294-2644, lesson:2026-02-22_arXiv_2601_12538#p33:352:45-417, lesson:2026-02-22_arXiv_2601_12538#p77:681:3006-3253, lesson:2026-02-22_arXiv_2508_07407#p31:401:4030-4566, lesson:2026-02-22_arXiv_2508_07407#p31:400:4006-4028, lesson:2026-02-22_arXiv_2508_07407#p55:718:1034-1513, lesson:2026-05-09_arXiv_2510_04886#p10:117:0-405, lesson:2026-05-09_arXiv_2510_04886#p25:423:1726-1816, lesson:2026-05-09_arXiv_2510_04886#p2:23:1266-2252, lesson:2026-02-22_arXiv_2510_05445#p18:259:1997-2210, lesson:2026-03-17_arXiv_2602_12670#p20:425:881-919, lesson:2026-03-17_arXiv_2602_12670#p20:433:2797-2841, lesson:2026-03-17_arXiv_2602_12670#p11:239:0-200, lesson:2026-02-22_arXiv_2401_10019#p3:30:2278-2477, lesson:2026-02-22_arXiv_2401_10019#p5:77:3297-3522, lesson:2026-02-22_arXiv_2401_10019#p1:0:0-86, lesson:2026-02-22_arXiv_2408_08089#p10:209:4624-4758, lesson:2026-02-22_arXiv_2408_08089#p3:55:4530-4670, lesson:2026-02-22_arXiv_2408_08089#p14:300:1235-1261, lesson:2026-02-22_arXiv_2501_07572#p19:343:1941-2289, lesson:2026-02-22_arXiv_2501_07572#p12:233:2650-3081, lesson:2026-02-22_arXiv_2503_01935#p36:673:451-773, lesson:2026-02-22_arXiv_2503_01935#p28:513:2700-2877, lesson:2026-02-22_arXiv_2503_01935#p1:16:2588-3224, lesson:2026-03-29_arXiv_2412_05579#p60:700:3832-4534, lesson:2026-02-22_arXiv_2507_20534#p10:311:271-296, lesson:2026-02-22_arXiv_2505_09970#p13:286:0-133

S8 is held: its rows are S8's own text (`arXiv_2410_10934`). S1 to S7 are not. Their rows are other works:
- S1 and S3: the LLM-as-a-judge survey arXiv:2411.16594;
- S2: arXiv:2503.09567;
- S4: AutoAgents, arXiv:2309.17288;
- S5: MALT, arXiv:2412.01928;
- S6: arXiv:2403.03031;
- S7: arXiv:2503.01935.

SQ-011 admits S1 to S9.

### Internal

**Receipts**, from `seldon prior-art search --internal`, run 2026-10-12 by QC-001 Part A, one query at a time. The arm also returned this note itself, read uncommitted from disk. Those self-hits are left out of the seldon lines: a receipt naming this note's own bytes cannot verify once the receipt is inserted.

- internal receipt: query "first article inspection" | repo seldon@6a692b456b7adf5bda2e0d629dc79f0066b56c8e | hits none
- internal receipt: query "first article inspection" | repo squiddy@c7393b11b39426fad6b4ac72e823a787333923d6 | hits none
- internal receipt: query "first article inspection" | repo ai-readiness-kg@8684a286b46d2a48fd4db927d5d680ffe6e1f3a9 | hits none
- internal receipt: query "first article inspection" | repo arnold@e528e125337159f4191318ede58a384783b2ab10 | hits none
- internal receipt: query "first article inspection" | repo icsp_notebook@68723d09c29f5be602c7caf95b1f154935dae4e3 | hits none
- internal receipt: query "first article inspection" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "first article inspection" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "earned value" | repo seldon@6a692b456b7adf5bda2e0d629dc79f0066b56c8e | hits none
- internal receipt: query "earned value" | repo squiddy@c7393b11b39426fad6b4ac72e823a787333923d6 | hits docs/HV-001_delivery_report.md:292, docs/decisions/register/00360_squiddy-di-181_accept.yaml:1, docs/EXTRACTION_DESIGN_SPEC.md:60, docs/DECISIONS_INHERITED.md:270
- internal receipt: query "earned value" | repo ai-readiness-kg@8684a286b46d2a48fd4db927d5d680ffe6e1f3a9 | hits none
- internal receipt: query "earned value" | repo arnold@e528e125337159f4191318ede58a384783b2ab10 | hits none
- internal receipt: query "earned value" | repo icsp_notebook@68723d09c29f5be602c7caf95b1f154935dae4e3 | hits docs/runbook_document_admission.md:454
- internal receipt: query "earned value" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits docs/decisions/2026-08-23_litellm-adoption-spike.md:228
- internal receipt: query "earned value" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "self-preference judge" | repo seldon@6a692b456b7adf5bda2e0d629dc79f0066b56c8e | hits none
- internal receipt: query "self-preference judge" | repo squiddy@c7393b11b39426fad6b4ac72e823a787333923d6 | hits docs/S-008_rules.md:1652, docs/Q-003_delivery_report.md:500, docs/Q-005_delivery_report.md:90, docs/Q-001_delivery_report.md:247, docs/decisions/register/00365_squiddy-di-188_accept.yaml:1, docs/design/2026-09-23_competency_questions.md:33, docs/decisions/register/00076_squiddy-r-66_accept.yaml:23, docs/design/2026-09-23_competency_questions.md:15, docs/decisions/register/00076_squiddy-r-66_accept.yaml:13, docs/design/2026-09-29_kill_stands_postmortem_before_any_lift.md:8, docs/decisions/register/00787_squiddy-r-66_amend.yaml:1, docs/DECISIONS_INHERITED.md:296
- internal receipt: query "self-preference judge" | repo ai-readiness-kg@8684a286b46d2a48fd4db927d5d680ffe6e1f3a9 | hits docs/design_decisions.md:135
- internal receipt: query "self-preference judge" | repo arnold@e528e125337159f4191318ede58a384783b2ab10 | hits none
- internal receipt: query "self-preference judge" | repo icsp_notebook@68723d09c29f5be602c7caf95b1f154935dae4e3 | hits none
- internal receipt: query "self-preference judge" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits docs/p4_exam/G4_DISPOSITION.md:59, docs/tevv/context/A2.txt:1
- internal receipt: query "self-preference judge" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "premises found wrong" | repo seldon@6a692b456b7adf5bda2e0d629dc79f0066b56c8e | hits none
- internal receipt: query "premises found wrong" | repo squiddy@c7393b11b39426fad6b4ac72e823a787333923d6 | hits none
- internal receipt: query "premises found wrong" | repo ai-readiness-kg@8684a286b46d2a48fd4db927d5d680ffe6e1f3a9 | hits handoffs/2026-09-07_projection_repair_and_eda_dispatched.md:17#sha256=ceb3ade393bc
- internal receipt: query "premises found wrong" | repo arnold@e528e125337159f4191318ede58a384783b2ab10 | hits none
- internal receipt: query "premises found wrong" | repo icsp_notebook@68723d09c29f5be602c7caf95b1f154935dae4e3 | hits none
- internal receipt: query "premises found wrong" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "premises found wrong" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "ABBA judge order" | repo seldon@6a692b456b7adf5bda2e0d629dc79f0066b56c8e | hits none
- internal receipt: query "ABBA judge order" | repo squiddy@c7393b11b39426fad6b4ac72e823a787333923d6 | hits docs/design/2026-09-29_kill_stands_postmortem_before_any_lift.md:8
- internal receipt: query "ABBA judge order" | repo ai-readiness-kg@8684a286b46d2a48fd4db927d5d680ffe6e1f3a9 | hits none
- internal receipt: query "ABBA judge order" | repo arnold@e528e125337159f4191318ede58a384783b2ab10 | hits none
- internal receipt: query "ABBA judge order" | repo icsp_notebook@68723d09c29f5be602c7caf95b1f154935dae4e3 | hits none
- internal receipt: query "ABBA judge order" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits docs/tevv/answers/A2.md:38, docs/tevv/context/A2.txt:1
- internal receipt: query "ABBA judge order" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "andon huddle" | repo seldon@6a692b456b7adf5bda2e0d629dc79f0066b56c8e | hits docs/design/AD-032_factory_control_design.md:275, docs/design/AD-032_factory_control_design.md:86
- internal receipt: query "andon huddle" | repo squiddy@c7393b11b39426fad6b4ac72e823a787333923d6 | hits handoffs/2026-10-04_desktop_audit_and_planning_to_decision_layer_design.md:39, handoffs/2026-10-04_desktop_audit_and_planning_to_decision_layer_design.md:18
- internal receipt: query "andon huddle" | repo ai-readiness-kg@8684a286b46d2a48fd4db927d5d680ffe6e1f3a9 | hits none
- internal receipt: query "andon huddle" | repo arnold@e528e125337159f4191318ede58a384783b2ab10 | hits none
- internal receipt: query "andon huddle" | repo icsp_notebook@68723d09c29f5be602c7caf95b1f154935dae4e3 | hits none
- internal receipt: query "andon huddle" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "andon huddle" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits design/2026-10-03_factory_control_design_DRAFT.md:274#sha256=6e77a0631484, design/2026-10-03_factory_control_design_DRAFT.md:85#sha256=6e77a0631484, 2026-10-03_SESSION_NOTEBOOK.md:5#sha256=457205a3d8b9
- internal receipt: query "different family rater" | repo seldon@6a692b456b7adf5bda2e0d629dc79f0066b56c8e | hits docs/design/AD-032_factory_control_design.md:266, docs/decisions/register/00087_seldon-ad-032-fc-33_propose.yaml:1, docs/decisions/register/00183_seldon-ad-032-fc-33_amend.yaml:1, docs/decisions/REGISTER.md:213, docs/decisions/REGISTER.md:9
- internal receipt: query "different family rater" | repo squiddy@c7393b11b39426fad6b4ac72e823a787333923d6 | hits docs/decisions/REGISTER.md:9
- internal receipt: query "different family rater" | repo ai-readiness-kg@8684a286b46d2a48fd4db927d5d680ffe6e1f3a9 | hits docs/design_decisions.md:651, docs/research/2026-09-03_g1_eval_findings.md:204, docs/design_decisions.md:657, docs/research/2026-09-03_g1_eval_findings.md:243, docs/design_decisions.md:755, docs/design_decisions.md:667
- internal receipt: query "different family rater" | repo arnold@e528e125337159f4191318ede58a384783b2ab10 | hits none
- internal receipt: query "different family rater" | repo icsp_notebook@68723d09c29f5be602c7caf95b1f154935dae4e3 | hits docs/2026-06-10_extraction_pipeline_design.md:54
- internal receipt: query "different family rater" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits docs/specs/2026-06-21-bridge-calibration-loop-design.md:144, docs/tevv/context/A2.txt:1
- internal receipt: query "different family rater" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits cross_project/synthesis/G1_quality.md:31#sha256=a20ca28f5c9d, design/2026-10-03_factory_control_design_DRAFT.md:265#sha256=6e77a0631484
- internal receipt: query "pilot first checkpoint" | repo seldon@6a692b456b7adf5bda2e0d629dc79f0066b56c8e | hits docs/decisions/REGISTER.md:213
- internal receipt: query "pilot first checkpoint" | repo squiddy@c7393b11b39426fad6b4ac72e823a787333923d6 | hits docs/S-008_rules.md:1897, docs/Q-003_delivery_report.md:380, docs/Q-003_delivery_report.md:437, handoffs/2026-09-23_q003_encoder_then_part_c.md:9, docs/Q-001_delivery_report.md:183, docs/Q-005_delivery_report.md:23, docs/L-001_delivery_report.md:7, handoffs/2026-09-21_desktop_h009_verdict_none_cleared_decontext_floor_budget_rules.md:37, docs/design/2026-09-29_factory_runner_dag_valves_stop.md:9, docs/DECISIONS_INHERITED.md:479, handoffs/2026-09-25_desktop_dn019_daemon_livelock_e002_dispatched.md:38, docs/EXTRACTION_DESIGN_SPEC.md:342, docs/EXTRACTION_DESIGN_SPEC.md:38, docs/EXTRACTION_DESIGN_SPEC.md:60, docs/decisions/REGISTER.md:9
- internal receipt: query "pilot first checkpoint" | repo ai-readiness-kg@8684a286b46d2a48fd4db927d5d680ffe6e1f3a9 | hits docs/design/2026-09-22_DN-008_operator_rulings_and_brief_destination.md:9
- internal receipt: query "pilot first checkpoint" | repo arnold@e528e125337159f4191318ede58a384783b2ab10 | hits none
- internal receipt: query "pilot first checkpoint" | repo icsp_notebook@68723d09c29f5be602c7caf95b1f154935dae4e3 | hits none
- internal receipt: query "pilot first checkpoint" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "pilot first checkpoint" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none

What each found:
- **"first article inspection"**: no repository uses it outside this note.
- **"earned value"**: none uses earned value management. The hits match the two words apart.
- **"self-preference judge"**: squiddy's S-008 rules and its Q-001, Q-003 and Q-005 reports, and the ai-readiness-kg and wintermute judges, declare self-preference as a risk. They mitigate it by rubric design and never measure it.
- **"premises found wrong"**: one ai-readiness-kg handoff. The RESULTs §1 cites are not returned.
- **"ABBA judge order"**: DN-022 (squiddy) and wintermute's TEVV A2, the calibrations R5 corrects.
- **"andon huddle"**: AD-032 FC-28 and FC-29, their draft, and squiddy's 2026-10-04 audit handoff. All proposed; none built for dispatched sessions.
- **"different family rater"**: AD-032 FC-33 and its register records, which R10 amends, and the different-family raters of ai-readiness-kg, wintermute and icsp_notebook.
- **"pilot first checkpoint"**: the pilot-first rule in seldon's register, squiddy's S-008 and Q-003, and ai-readiness-kg DN-008. R6 (b) makes it a station.

Queries, fixed now:
- "first article inspection"
- "earned value"
- "self-preference judge"
- "premises found wrong"
- "ABBA judge order"
- "andon huddle"
- "different family rater"
- "pilot first checkpoint"

Records already read for this note, by path:
- **AD-032**, `seldon/docs/design/AD-032_factory_control_design.md`:
  - FC-10, FC-27, FC-28 and FC-29;
  - FC-33's different-family rater;
  - FC-15's charted estimate-to-actual ratio.
- **AD-034**, `seldon/docs/design/AD-034_worktree_per_task_dispatch.md`, R2, R3 and §6: Touches is declarative, and semantic conflicts outside the write set are not re-gated.
- **AD-035**, R2 and R7: the model registry and lock; a judge re-pilots on a lock bump.
- **AD-036.** The prior-art gate.
- **DN-022 §1**, `squiddy/docs/design/2026-09-29_kill_stands_postmortem_before_any_lift.md`: ABBA 26 of 26, kappa 0.874 and 0.822, and the declared self-preference risk.
- **SQ-010's disk incident**, `squiddy/docs/evidence/sq010/disk_incident.md`.
- **The workbench notebook.**

## 3. Decisions

- **AD-037-R1. A criterion that a program can decide is decided by running the program, never by a judge reading output.**
  - Every acceptance criterion in a dispatched task is marked either `check: <command>` or `judgment: <why no program decides it>`.
  - A reading judge sees only `judgment:` criteria.
  - A task with an unmarked criterion fails registration as `criterion_unmarked`.
  - Basis: S1, self-preference persists on checkable rubrics; S8.

- **AD-037-R2. A reading judge is the next tier above the generator, in a fresh context.**
  - The judge runs with no access to the generator's reasoning, self-assessment or chat.
  - The `checker` role in `models/registry.yaml` maps each generator family to the next tier: haiku to sonnet, sonnet to opus, opus to fable. It is resolved through the lock (AD-035-R1), never typed.
  - **Fable has no higher tier.** Its judge is a fresh Fable context reading an authorship-obfuscated text (S2, a partial fix). It carries the measured catch rate of R3, and R1 carries the rest.
  - Basis: the operator's rule; S6 on capability. S1 shows this is not independence from family bias; R3 measures how much that costs.

- **AD-037-R3. Family self-preference is measured on this portfolio's work, against a pre-registered bar, and re-measured on every lock bump.**
  - **The calibration set** is planted defects, each written twice: once into text in the generator's own style, and once into reference text not written by a model of that family (the operator's own design notes and RESULT prose he wrote).
  - **Seeding.** The first set is seeded from this week's real defects:
    - premises found wrong;
    - the effort default;
    - the unparsed ruling labels;
    - the R-181 collision.
  - **Reported numbers:**
    - the catch rate on each half, with Wilson-95 intervals;
    - their difference, which is the self-preference estimate.
  - **The bar:** a checker serves as a reading judge for a criterion class only if its Wilson-95 lower bound on generator-style plants is at least 0.70, with n of at least 30. There is no measured basis for these numbers; FC-10 control limits replace them once 3 measurements exist.
  - **Below the bar:**
    - that class moves to execution checks (R1) or to operator review of aggregates;
    - a cross-family checker is proposed only as a spend decision at operator touchpoint 1, since he has ruled out paying for a second API by default;
    - no ensemble.
  - Basis: S1, S3, notebook position 3.

- **AD-037-R4. No same-model persona panel or debate is used as a check.** Personas of one model are one correlated instrument. Basis: S4, S5.

- **AD-037-R5. A judge's calibration reports position bias, test-retest reliability and self-preference as three separate numbers.**
  - Position bias is the ABBA flip rate.
  - Test-retest reliability is replicate kappa.
  - Self-preference is R3's differential.
  - A calibration report missing any of the three is refused, and a judge without a passing report is not used.
  - This is the mechanism that closes DN-022's correction as an AD-032 FC-26 lesson (QC-001 Part C).

- **AD-037-R6. A dispatched session passes four inspection stations: premise review, first article, milestone, and andon with huddle.**
  - **(a) Pre-dispatch premise review.**
    - Before launch, every factual premise in the task (a count, a path, a state, a version, an id or label assumed free) is checked against live state by command.
    - A false premise blocks the task with an Issue naming it.
    - Only premises no command can check go to the R2 checker.
  - **(b) First-article inspection.**
    - In any loop over units (documents, repositories, records), the session stops after the first unit.
    - The unit's output is inspected per R1 and R2, and the loop continues only on a pass (AS9102: objective evidence before production; the doctrine's "pilot first" made a station).
  - **(c) Milestone sampling with earned value.**
    - **At each Part boundary** the session appends `part_complete`, naming the Part, its planned share of the task's estimate, and tokens used so far.
    - **The dispatcher computes CPI**, earned value over actual cost. Earned value is the planned share of the completed Parts.
    - **It runs the Part's `check:` commands every time.** It reads `judgment:` outputs on a sample (R7).
    - **CPI below 0.8 opens a huddle without stopping.** No measured basis; FC-15's charted ratio replaces it once 10 tasks exist.
    - **A failed check stops the line.**
  - **(d) Andon and huddle** (FC-28, FC-29).
    - Any station, the session or the operator writes a session stop.
    - The session halts at its next Part or loop boundary.
    - The dispatcher enforces a hard stop for FC-32's toxic class and for disk or spend ceilings.
    - The huddle record names the reading, the cause one level down and the gate that now prevents it.

- **AD-037-R7. Inspection costs at most 10% of the task's estimate, reserved with the task.**
  - The checker's calls are reserved in the task's spend reservation (FC-11).
  - When the reserve runs low, the judgment sampling rate falls first. `check:` commands are never skipped.
  - There is no measured basis for 10%; the actual share is charted (FC-15).

- **AD-037-R8. Station outcomes are charted per project.** Charted per project (FC-10):
  - premise-false rate;
  - first-article reject rate;
  - milestone defect rate;
  - CPI;
  - huddles per task.

  A first reading is reported, not gated.

- **AD-037-R9. Parallel dispatch stays at `max_parallel: 1` in every project, ai-readiness-kg included, until R6 (a) to (d) and the dispatcher's disk preflight (SQ-010 ADDENDUM 02 D3.4) are live.**
  - After that, a project opts in only on measured demand: on 3 of 7 days, two or more gate-clean tasks with disjoint Touches waited over 24 hours. No measured basis.
  - Reasons:
    - Weekly model budget, not wall-clock, is the binding constraint, and parallel sessions spend it faster.
    - On 2026-10-11 a worktree cost 1.1 to 2.1 GiB and the disk filled.
    - AD-034 §6 leaves Touches unenforced and semantic conflicts outside the write set unchecked.
    - Without R6, two unsupervised sessions double the blind time.
  - This decides the open question of ai-readiness-kg's SEL-004 opt-in: not now.

- **AD-037-R10. AD-032 FC-33's perversity rater follows R2 and R3, not "a different model family".** FC-33 required a different family, which the operator's 2026-10-11 rule excludes by default. The rater is the next tier up, with its self-preference measured per R3; a cross-family rater is a touchpoint-1 spend decision. FC-33 is otherwise unchanged.

## 4. What this does not solve

- **Self-preference is measured, not removed.** At the top tier nothing sits above Fable, and obfuscation is partial (S2). The measured gap is the honest residue.
- **R1 depends on authors marking criteria well.** A `check:` command that checks the wrong thing passes. That is FC-27's positive control's job, per check.
- **The earned-value proxy is coarse.** Planned share per Part comes from the task's estimate, which FC-12 says must be measured. Until it is, CPI inherits the estimate's error.
