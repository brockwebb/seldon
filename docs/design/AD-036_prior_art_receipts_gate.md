# AD-036: A design note carries a two-part prior-art section made of receipts, and a note without one cannot be committed or cited

**Date:** 2026-10-09
**Status:** Accepted (L4, operator directive 2026-10-09 12:51 ET: "have we consulted the actual science before we start guessing").
**Implements:** plan action E (`workbench/2026-10-03_audit_and_decision_probe/2026-10-04_next_actions_plan.md`), Issue `2f46e15a`, squiddy DN-009 R-40, EX-REQ-13.
**Carries:** the findings of withdrawn MODEL-002 (`7a232604`) and AD-035 erratum 01.

## 1. The condition

Problem 1 of the cross-project audit (`G5_governance.md`): internal prior art not searched before a design is written. It is ranked first and marked REGRESSED. Its timeline:

| when | what happened | cost |
|---|---|---|
| Wintermute 2026-06-08 | entity-resolution literature read after three failures | |
| ai-readiness-kg 2026-08-27 | whole-document extraction unit | about 60M tokens |
| Squiddy DN-004 to DN-008 | | 97M tokens |
| Squiddy DN-035, 2026-10-02 | | |
| this repo, 2026-10-09 | AD-035 was written from one vendor document and memory. Its prior-art section claimed a content search of five repositories that was a filename match (AD-035 erratum 01) | |

The rule exists in prose in three places and binds nowhere outside one repository:
- ai-readiness-kg `kg_construction_methodology.md` §7 rule 1 (a pilot without a `prior_art` block is refused at registration);
- Squiddy DN-009 R-40 ("enforcement belongs in Seldon, not in each repo");
- EX-REQ-13 (Seldon gate NOT BUILT).

The internal search that AD-035 skipped would have found its own rulings already written:
- ai-readiness-kg §1: "Model identity is a gate: a response reporting a different model is discarded and the run STOPs. A model change is a new instrument." That is AD-035-R6 and R7.
- §7 rule 5: "Verify product facts in platform docs before pinning a model. Desktop product knowledge is stale by construction. (Defect: Opus 5 pin.)" That is the MODEL-001 defect, already paid for once, in August.

## 2. Prior art

Library receipts are from squiddy-library `search`, release `exports/library_graph_20260930_m002_2026-09-30.json`, sha256 `fc7f3173...2576543`, run 2026-10-09. Each cites the query, the `doc_id` and the row.

### External

- **Mandatory checklists change behavior; voluntary guidance does not hold.**
  - Query: "checklist compliance enforced gate pre-registration systematic review protocol reduces errors".
  - `lesson:2026-04-13_arXiv_2406_14325` row `#p16:104:1865-2521`. Citing Han et al. 2017 (PLoS ONE 12(9) e0183591), mandatory checklists increased the reporting of methodological information needed to reproduce experiments by 65% across 943 articles.
  - Same doc, row `#p21:138:1384-1675`: guidelines and checklists may not be enforced consistently.
  - `lesson:2026-02-22_arXiv_2502_12110` row `#p22:436:25-451`: NeurIPS desk-rejects a paper without its checklist. The enforcement is refusal, not reminder.
- **Prose instructions decay inside an agent's session.**
  - Query: "LLM agents fail to follow instructions in long context, constraints ignored, instruction adherence degrades".
  - `lesson:2026-02-22_arXiv_2410_15553` row `#p10:200:2341-3477`: models show a pronounced tendency toward decreased adherence to previously followed instructions as turns progress (their instruction-forgetting rate).
  - `lesson:2026-02-22_arXiv_2401_07128` row `#p8:229:96-130`: "fail to follow instructions" is a measured error class of LLM agents (8.74% of failures).
  - A rule held in CLAUDE.md or memory is therefore an instruction that decays. The gate is outside the agent.
- **A search is reportable only with its strings, sources and dates.**
  - Query: "PRISMA-S reporting literature search strategy databases search strings dates reproducible search".
  - `lesson:2026-05-09_arXiv_2604_23338` row `#p4:54:1802-2716` and `lesson:2026-02-02_arXiv_2501_05435` row `#p4:36:519-1392`: reviews report databases, search terms and date ranges so the search can be re-run.
  - The PRISMA-S extension itself (Rethlefsen et al. 2021, Systematic Reviews 10:39) is **not in the library**. It is cited from knowledge, unverified, under the citation policy (capture, verify where impact is high). It is filed for acquisition.
- **Versioned instruments drift** (bears on section 5).
  - Query: "LLM behavior drift over time model version changes reproducibility of results".
  - `lesson:2026-04-07_arXiv_2307_09009` rows `#p1:8:1723-2355`, `#p2:40:494-2812` (Chen, Zaharia, Zou 2023).
  - `lesson:2026-03-29_arXiv_2411_15594` rows `#p22:329:2228-3056`, `#p44:613:2025-3138` (evaluation drift).
- **Reproducible builds.** Reproducible-builds.org and Bazel hermeticity: a result is trusted when a second party can re-derive it from declared inputs. That is the receipt model here, a re-runnable query, rather than a logged assertion. Cited from knowledge; not in the library.

### Internal

Searched by reading, 2026-10-09, not by a logged tool. This note is written before the tool exists, so the bootstrap is the receipt `seldon prior-art verify` will check after the fact: R7.

- `workbench/2026-10-03_audit_and_decision_probe/cross_project/synthesis/G5_governance.md` problem 1, its 14-entry timeline with file:line citations, and its best answer: a two-part block, refused at registration.
- `ai-readiness-kg/docs/research/kg_construction_methodology.md`:
  - §1 (model identity gate);
  - §7 rules 1 and 5;
  - §7.6: a verdict cited in a decision names the instrument version and its positive control. Applied here as R5's recall control.
- `squiddy/docs/design/2026-09-20_internal_prior_art_packs_anchors.md` R-40: two parts, each naming what was searched and found; enforcement in Seldon.
- Plan action E exit check: library query p95 under a stated bound on the 24 frozen questions; a design note without the two-part section is refused.
- `seldon/docs/design/AD-030`:
  - R9: register checks a DN or AD citation and nothing about its content;
  - R16: governed ingest;
  - AD-033 design-note label patterns in `seldon.yaml`.
- Issue `25da4d06`: the governed pin is stale, so the governed graph does not hold the last 12 notes. The governed graph cannot yet be the internal corpus (R3).

## 3. Decisions

- **AD-036-R1. Every new design note carries `## Prior art` with two subsections, `### External` and `### Internal`, and each entry is a receipt.**
  - A **library receipt** names the query string, the index release and its sha256, and one or more returned row ids.
  - An **internal receipt** names the query string, the repository and its commit sha, and file:line hits.
  - A **web receipt** names the URL and the retrieval date. It is allowed in External, but a section of web receipts only must also carry at least one library query, even one that found nothing.
  - A finding of "no prior art" is a receipt of the query that found nothing. It is never a sentence.

- **AD-036-R2. Receipts are verified by re-running them, not by trusting a log.**
  - `seldon prior-art verify <note>` re-runs each library query against the named release and each internal query against the named commit. It passes a receipt only when the cited ids or lines are in the result.
  - A release or commit that is no longer loadable fails with `release_unavailable`, naming it. The verification is recorded once, at commit (R4), so a later library rebuild does not orphan an accepted note.
  - Prior art: reproducible builds. A second party re-derives the claim.

- **AD-036-R3. The internal arm searches a declared corpus with a logged, deterministic tool, until governed graphs cover it.**
  - `seldon prior-art search --internal "<query>"` searches, at each repository's HEAD:
    - `docs/design`, `docs/research`, `docs/decisions`, `CLAUDE.md`, `DECISIONS_INHERITED.md` and `handoffs`;
    - in every repository listed under a new `prior_art.internal_roots` key, seeded with seldon, squiddy, ai-readiness-kg, arnold, icsp_notebook, the `~/.wintermute/docs` tree, and the workbench audit folder.
  - It prints receipts in R1's form and appends the query, the commits and the hits to `state/prior_art_queries.jsonl`.
  - The match is lexical (ripgrep, case-insensitive, all terms within one paragraph). It is a search, not an admission test, so DI-075 does not bar it. R5 measures its recall.
  - `seldon prior-art search --library "<query>"` wraps squiddy-library `search` in-process and logs the same way.
  - Both are exposed as one MCP tool, `seldon_prior_art_search`, so Desktop design sessions use them.
  - When governed graphs cover the sibling repositories (AD-031-R1, Issue `25da4d06`), a governed-graph arm is added beside the lexical one. It is not substituted, since the lexical arm is the recall control's baseline.

- **AD-036-R4. The gate refuses at two points.**
  - **Commit:** `seldon verify` (pre-commit) refuses a commit that adds a design note under `docs/design/` whose prior-art section is missing, has an empty subsection, or fails R2. The verdict is written to the governed ledger beside the note's hash.
  - **Registration:** `seldon cc register` refuses a task whose governing note has no passing verdict.
  - Notes on main at this AD's merge commit are baseline. They are listed and grandfathered, not re-litigated.
  - The refusal quotes the missing part and names this AD.

- **AD-036-R5. The internal search tool carries a pre-registered recall control.**
  - The positive set is the 14 file:line entries of G5 problem 1's timeline and the four ai-readiness-kg §1 and §7 lines cited in section 2: 18 known-relevant locations.
  - Queries are fixed before the run. One per entry, written from the entry's topic, never from its wording:
    - "prior art search before design";
    - "unit of extraction";
    - "model pin" (bears on "Opus 5 pin");
    - and so on, one per entry.
  - The tool passes when Wilson-95 lower bound of recall at top 20 is at or above 0.70.
  - A failure is reported with the misses and does not block R4. The gate checks presence and verifiability, not search quality. It opens a design task for the governed-graph arm.
  - The control is re-run on every change to the tool.

- **AD-036-R6. What the gate does not check, stated so nobody relies on it.** It proves a search happened and that its cited hits exist. It does not prove the author read the hits, weighed them or used them. Han et al. measured reporting, not quality. Quality stays with review (AD-020 multi-lens) and with the operator.

- **AD-036-R7. This note is its own first test.** After the tool lands, `seldon prior-art verify docs/design/AD-036_prior_art_receipts_gate.md` must pass. Its internal section's prose is then converted into receipts by re-running each internal search with the tool, recorded in an addendum, never by editing this file. AD-035 is checked the same way and its result recorded in an AD-035 addendum.

## 4. Library access (plan action E's first exit check)

On 2026-10-09 the squiddy-library MCP answered six queries in seconds each. The 2026-10-04 handoff recorded a 4-minute timeout. Neither is a measurement.

The exit check is p95 latency on the 24 frozen questions, cold and warm, under a bound stated before the run. Basis for the 10 s ceiling: Desktop tool-call patience; no measured basis otherwise. A failure is a design task.

## 5. Carried from withdrawn MODEL-002: declared inputs beyond the model id

- **AD-036-R8. Effort is a declared input, as the model id is (extends AD-035-R1, R3, R6).**
  - `effort: default` is refused in `models/registry.yaml`. Each role names a level.
  - Values are the documented default of the model the lock now serves:
    - `medium` for opus, sonnet and haiku;
    - `high` for fable;
    - `document_extractor` and `demand_judge` stay `high` as measured.
  - This makes today's behavior explicit and changes nothing.
  - Launchers pass `--effort`. Receipts record it.
  - A lock bump records any change in a family's documented default effort.
  - Basis:
    - Chen et al. 2023, above: anything that changes the instrument is part of its identity;
    - code.claude.com/docs/en/model-config, retrieved 2026-10-09: default effort moved from `high` on Opus 5 and Sonnet 5 to `medium` on the 5.5 models.

- **AD-036-R9. A test never spends unasked.** arnold's live seed-scan test calls a model whenever `claude` is on PATH. Any test that can reach a model launcher without a fake runs only under an explicit opt-in variable named in its skip reason, in every repository MODEL-001 touched. A PATH shim that records invocations proves zero calls by default.

## 6. Premises corrected

1. **The decision register cannot see AD-035.**
   - `seldon.yaml` reads ruling labels as `**AD-NNN-Rn` (bold, optionally bulleted).
   - AD-035 was edited before commit to `## AD-035-Rn.` headings.
   - So no register record exists for any AD-035 ruling (none under `docs/decisions/register/`), and `seldon verify` did not flag it, because a label it cannot parse is a label it cannot miss.
   - The cause is SEL-001's measured cause again: a ruling not parsed.
   - Correction:
     - write the AD-035 records through `seldon decision`;
     - add to `seldon verify` a check that any line in a design note matching `AD-\d{3}-R\d+` or `\bR-?\d{1,3}\b` in a heading or bold position is captured by a configured pattern;
     - an uncaptured label fails as `ruling_label_unparsed`.
2. **The standing dispatcher runs only for ai-readiness-kg.**
   - The only launchd job is `com.brock.airkg-dispatch`.
   - Neither `seldon/seldon.yaml` nor `squiddy/seldon.yaml` has a `dispatch:` block.
   - The Desktop statements on 2026-10-09 that the dispatcher "may pick up" MODEL-001 and MODEL-002 were wrong.
   - Enabling it for seldon and squiddy is SEL-005, which follows the standing dispatcher note's "what a second project must do".
