# AD-031: Rulings reach the task at registration by retrieval, not by citation (extends AD-030; measured before built)

**Date:** 2026-10-02
**Status:** Draft. Desktop design session. Phase 1 (measurement) is dispatched as SEL-001; Phase 2 is not designed
until Phase 1's numbers are in.
**Extends:** AD-030 (governed documents as graph content), especially R3 (ingest on commit) and R9 (lexical DN/AD
check)
**Uses:** Squiddy's served `search` (Squiddy DN-025 R-110: hybrid FTS5 plus pinned dense encoder, RRF, located
receipts)

## 1. The failure, measured on 2026-10-01 and 2026-10-02

- Every `seldon cc register` in Squiddy and Arnold answered: "No ruling in the graph constrains this task. If that is
  wrong, the ruling is not ingested — run `seldon governed sync`." It is wrong on both counts:
  - **Not ingested:** AD-030's governed graph exists only in the Seldon repository, built 2026-09-12 from 4
    documents. Squiddy has no `governed/` directory. Squiddy's design notes hold the R-numbered rulings that should
    have bound the tasks.
  - **The binding that exists is unmeasured.** Where a governed graph exists (Seldon), registration already binds
    uncited rulings by a concept-overlap score. Registering SEL-001 in Seldon bound 8 AD-030 rulings at overlaps
    of 0.27 to 0.47. Desktop's first draft of this note said the binding was lexical-only; registration
    disproved it. How well concept overlap finds the ruling a task contradicts has never been measured.
- The concrete misses. Each is a task that contradicted a recorded ruling it did not cite:
  - Arnold KG-004 step 6, KG-005, KG-006 and Squiddy SQ-004 ran or planned extraction against Squiddy DN-025 R-112
    and R-113. That cost about 2.42M tokens. Desktop wrote them without reading DN-025.
  - Arnold's per-set RPE field (2026-09-01) was reintroduced against `docs/ontology/intensity-constructs.md`. AD-030
    section 1 records it.
- The operator was the continuity layer both times, and caught it from memory. AD-030 named this defect window, the
  gap between a ruling being written and the next task being registered, and closed it only for rulings the task
  already cites.

## 2. Prior art

- **The design-rationale "use problem."** Rationale systems (IBIS, QOC, DRL) failed in practice less on capture than
  on retrieval at the point of decision: recorded rationale was not consulted when the next decision was made (Lee
  1997, "Design rationale systems: understanding the issues", IEEE Expert). That is this failure.
- **IR-based traceability link recovery.** Candidate links between artifacts are recovered by text retrieval rather
  than by authors' explicit references, and are evaluated by precision and recall against labeled trace sets.
  - Antoniol et al. 2002, IEEE TSE: the founding work.
  - Cleland-Huang, Gotel and Zisman (eds.) 2012, *Software and Systems Traceability*.
  - The current form is retrieval plus an LLM validator. LiSSA (ICSE 2025) does generic traceability link recovery
    through retrieval-augmented generation. A 2026 GraphRAG study states the dependency plainly: the validator's
    decision is limited by which candidates retrieval delivers to it. So retrieval recall is measured first.
  - LLM validators in traceability show high precision and uneven recall (documentation-to-code evaluation, 2025:
    precision uniformly high, recall 47 to 75 percent).
- **Squiddy's own measurement** (DN-025, Q-003 to Q-005): on the kit's corpora, hybrid retrieval over text and
  metadata with receipts beat model-built structure. It is the kit's served verb, so this design uses it rather than
  building a second retriever.

## 3. Decision

- **AD-031-R1. Every repository that registers CC tasks has a governed graph, built on commit** (AD-030 R3), served
  with Squiddy's `search`. Arnold's tasks also search Squiddy's governed graph, because Arnold builds with Squiddy.
- **AD-031-R2. Registration retrieves rulings for the task's text, whether the task cites them or not.**
  - Phase 2, if Phase 1 earns it: the top-k candidate Rulings go to a validator call. The validator returns
    `constrains`, `conflicts` or `unrelated` for each, with the ruling's located receipt.
  - A `conflicts` verdict refuses registration unless the task names the ruling and supersedes it (AD-030 R5's path).
  - `constrains` writes `constrained_by` edges.
  - The validator is a separate call from the author (the work does not grade itself).
- **AD-031-R3. Phase 1 measures retrieval before anything is wired** (SEL-001). Phase 2 is designed only on Phase 1's
  numbers. Two arms, on the same gold sets:
  - **arm O:** the existing concept-overlap binding, as registration runs it today;
  - **arm H:** Squiddy's hybrid `search`.

  If O meets the bar, nothing new is built: Squiddy and Arnold get governed graphs and the existing mechanism.

## 4. TEVV (pre-registered here, before any measurement)

- **Gold set A: explicit links, labeled for free.**
  - Every registered CC task in Squiddy and Arnold that cites a DN-, AD- or R- identifier gives (task, cited ruling)
    pairs.
  - Retrieval runs on the task text with every identifier and DN/AD/R reference stripped, so the measure is recovery
    without citation.
  - Split by date: tasks before 2026-09-25 tune nothing (nothing is tuned; the configuration is frozen); all tasks
    are scored.
- **Gold set B: the known misses, labeled by hand from section 1.** Each pair is (task text, the ruling it
  contradicted):
  - KG-004 step 6 / DN-025 R-112;
  - KG-004 step 6 / R-113;
  - KG-005 / R-112;
  - SQ-004 / R-112;
  - the RPE task / the intensity-constructs ruling, if that ruling sits in an ingestible governed document.
- **Gold set C: clean negatives.** 20 tasks drawn with a fixed seed from those that completed without a later
  correction. These are used to report how many candidates retrieval returns, not to gate.
- **Measures, per arm:** recall@5 and recall@10 on A, with the Wilson interval; hit or miss for each B pair at
  k = 10; MRR on A. Arm O ranks rulings by its overlap score.
- **Bar for Phase 2:**
  - recall@10 on A at or above 0.80 (Wilson lower bound reported);
  - every B pair retrieved at k = 10.

  Below either, the report states which ruling texts were missed and why, and Phase 2 is not designed until the
  retrieval side is fixed. The fix might be section granularity, metadata documents, or query construction. It is
  never a moved bar.
