# SEL-001: AD-031 Phase 1. Governed graphs for Squiddy and Arnold, then measure whether retrieval finds the rulings a task should have seen

**Repo:** seldon. It also writes `governed/` in squiddy and arnold, through AD-030's own path. Branch `feat/SEL-001` in
each repository touched. L4: commit, merge, push.
**Cites:** AD-031 (R1 to R3 and section 4, the pre-registered TEVV), AD-030 (R1, R3, R4, R9, R10), Squiddy DN-025 R-110.
**Read first, in full:** `docs/design/AD-031_rulings_reach_the_task_by_retrieval.md`,
`docs/design/AD-030_governed_documents_as_graph_content.md`, `seldon/core/governed.py`,
`seldon/commands/governed.py`, and the 2026-09-12 AD-030 RESULT file. Glob and read sibling `*SEL-001*ADDENDUM*.md`.
This file and its addenda are immutable once read.
**Model spend:** zero. The dense encoder is Squiddy's pinned local one, run offline under Squiddy's egress tier.
**Network:** none.

## Part 1. Build the governed graphs (AD-031 R1)

1. Run AD-030's ingest (`seldon governed sync` or its documented equivalent) on squiddy and on arnold. Governed
   directories per AD-030 R1: `docs/design/`, `docs/requirements/` if present, `cc_tasks/`, `handoffs/`, and Arnold's
   `docs/ontology/`.
2. Print, per repository:
   - documents;
   - sections;
   - rulings, by `matched_pattern`;
   - documents that parsed to zero rulings.

   Squiddy's design notes write rulings as `**R-nnn (...)**` and `**AD-030-Rn.**` style lines. If the Ruling detector
   misses that form, report it with three examples and extend the detector, with a test per form. No ruling is
   hand-entered.
3. Build Squiddy's served index over each governed graph through the kit's normal index stage. Use the Ruling and
   Section text as units and documents as metadata rows, with the frozen RRF configuration (DN-025 R-110). Index
   parity must pass.

## Part 2. Gold sets (AD-031 section 4)

4. **Set A.** For every registered CC task in squiddy and arnold, extract the DN-, AD- and R- identifiers it cites and
   resolve each to Ruling nodes.
   - Strip every such identifier, and every "DN-nnn", "AD-nnn" or "R-nnn" token, from the task text before retrieval.
   - Write `evidence/sel001/gold_a.jsonl`.
   - Report pairs, tasks, and identifiers that resolved to no Ruling.
5. **Set B.** The hand-labeled misses named in AD-031 section 4, resolved to Ruling nodes.
   - If the intensity-constructs ruling is not in a governed directory, record that and score B without it.
   - Write `evidence/sel001/gold_b.jsonl`.
6. **Set C.** 20 tasks, seed 20261002, from tasks completed with no later correction or supersession. Write
   `evidence/sel001/gold_c.jsonl`.

## Part 3. Measure (AD-031 section 4, unchanged)

7. Run both arms of AD-031 R3 on the stripped task text at k = 10, over squiddy's governed graph plus arnold's for
   arnold tasks. Nothing is tuned.
   - **Arm O:** registration's existing concept-overlap scorer, run read-only. Find it in the code; do not
     reimplement it. Rank by its score.
   - **Arm H:** Squiddy's hybrid `search` over the index from step 3.
8. Report, per arm:
   - recall@5 and recall@10 on A, with Wilson intervals;
   - MRR on A;
   - each B pair, hit or miss, with its rank;
   - C's candidate counts. For arm O, also the count above registration's own binding threshold.
9. For every A miss and every B miss: the task's top 3 hits and the missed ruling's text. Name the cause where the
   evidence shows it, such as granularity, vocabulary or a parse gap. No fix is applied in this task.
10. Write `docs/SEL-001_delivery_report.md` in seldon.
    - Order: B first, then A, then C, then misses, then the governed-graph counts.
    - Close with the AD-031 bar verdict, pass or fail.
    - `seldon cc complete`.

## Stop conditions

- AD-030's ingest refuses a repository; report why.
- Index parity fails.
