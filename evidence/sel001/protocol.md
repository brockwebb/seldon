# SEL-001 measurement protocol: what AD-031 section 4 leaves open, fixed before any number is computed

**Date:** 2026-10-02. **Governs:** `scripts/sel001/`. **Implements:** AD-031 section 4 (pre-registered TEVV),
SEL-001 steps 4 to 9. Committed before the first arm run. A change after that is an erratum, with the reason, in
the delivery report.

AD-031 section 4 fixes the gold sets, the measures and the bar. It does not say how a ruling is "retrieved" by a
retriever whose unit is a row, what counts as the task's own text, or which completed tasks are "clean". Each of
those is decided here, with its reason.

## 1. The candidate pool

- **Scope.** A Squiddy task is scored over Squiddy's governed graph. An Arnold task is scored over Arnold's and
  Squiddy's (AD-031-R1). Seldon's governed graph is not in scope for either; a cited Seldon AD resolves to
  nothing and is reported as such.
- **The task's own family is excluded from its candidates, in both arms.** A governed document belongs to a
  task's family when its file stem (date prefix removed) starts with the task's code (`H-009`, `KG-004`), or, for
  a task with no code, with the task's slug. A task's own file, its addenda, errata and RESULT restate its text;
  retrieving them is retrieving the query. Nothing else is excluded: the graph is scored as it stands today,
  including documents written after a task (a stated limitation, not a correction).
- **Only Ruling nodes are candidates.** Phase 2 sends candidate Rulings to a validator (AD-031-R2), so k counts
  Rulings. Section rows are in arm H's index and compete for its sub-arm ranks; they are not candidates.

## 2. The arms

- **Arm O.** `seldon.core.governed.match_rulings`, the function `seldon cc register` runs, over the Rulings
  `seldon.core.governed.read_rulings` reads from each graph's Seldon database (`seldon-squiddy`,
  `seldon-arnold`), read-only. It is called with `threshold=0.0` and `limit` equal to the number of rulings, so it
  returns its own ranking (its overlap score, then its own name tiebreak) without its truncation. A ruling with
  score 0.0 shares no term with the task and is dropped: ranking it would be ranking by name. The count above
  registration's binding threshold uses `ruling_match_threshold` read from the task's own repository config.
- **Arm H.** Squiddy's served index for each graph in scope, opened through `squiddy.index.Index.open`, which
  verifies the database hash and the shard set its manifest binds. Per task, per index: the two sub-arms as the
  served verb runs them (`Index.lex.search`, `Index.dense.search`, 200 candidates each), fused by
  `squiddy.index.rrf` at the configured `rrf_k`. Nothing is re-implemented and nothing is tuned. The fused row
  lists of the graphs in scope are merged by fused score (ties by graph, then row id), the family is removed, and
  the Ruling rows in that order are the candidates.
- **Run conditions.** Arm H and the index build run as child processes under Squiddy's egress policy `none`
  (`squiddy.egress.child`: closed proxy, offline switches, `sandbox-exec` deny-network profile where available);
  the run record keeps the enforcement it reports. Zero model calls in either arm.

## 3. The gold sets

- **Identifiers.** Extracted from the task file by `\b[A-Z]{2,4}-\d+-R\d+(?![0-9])` (a compound ruling
  identifier), `\b(?:DN|AD)-\d+(?![0-9])` and `\bR-\d+(?![0-9])`; a token ends where its digits end, so
  `R-112s` is one. Arnold's document-local `R1`, `R2` are not identifiers outside their
  document and are not extracted.
- **Resolution.**
  - A ruling identifier (`R-110`, `DN-002-R1`) resolves to the Ruling nodes in scope carrying it as their label.
    Its home node is the one in a design or ontology document; others are restatements.
  - A document identifier (`DN-025`) resolves to the document in scope whose title or file name opens with it,
    and then to every Ruling that document states. An Arnold task's `DN-nnn` resolves in Arnold first, and in
    Squiddy only when Arnold has no such document or the text writes `Squiddy DN-nnn`.
  - An identifier that names no document in scope, or a document with no Ruling, is reported by kind and is not a
    pair.
- **Stripping.** Every token matching the four patterns above is deleted from the task text before either arm
  sees it. Everything else in the text stays.
- **Set B's tasks** are stripped the same way. KG-004's pairs use the whole task file; "step 6" names where the
  contradiction was, not a different text. The intensity-constructs ruling is the 2026-08-16 paragraph of
  `docs/ontology/intensity-constructs.md` section 2 that closes per-set RPE capture. If no Ruling node carries
  that paragraph, the pair is scored a miss in both arms with cause "parse gap", and nothing is hand-entered.
- **"The RPE task"** is `cc_tasks/2026-09-01_pb-03-plan-json-api.md`. AD-031 names one task; Arnold's own record
  (`cc_tasks/2026-09-01_plan-builder-rebuild.addendum-02.md` R2) names two, "pb-03/pb-04 (Desktop spec error)
  reintroduced `rpe` in the compressed JSON contract and a gear-popover field", and pb-03 is the one that put the
  per-set field into a contract, which is what AD-030 section 1 describes. pb-04, and pb-01 (which added the
  `RPE <n>` grammar token), are scored the same way and reported as diagnostics, outside B and outside the bar.
  Also reported, outside the bar: where intensity-constructs section 12's R2 ("per-set effort is gone from
  PLANNING too", written 2026-09-12 in response) ranks, because it is the ruling a registration today would need.
- **Set C.** The pool is every task in `completed` state whose file is on disk, that is not itself an addendum,
  erratum or correction (file name), and that no later addendum or erratum names by its code or slug. 20 tasks,
  `random.Random(20261002).sample` over the pool sorted by file path.

## 4. The measures

- **A hit.** For a pair (task, gold ruling), the gold's rank is the first position in the arm's candidate list
  holding a Ruling that IS the gold: for a globally labelled ruling (`R-nnn`, a compound identifier), any Ruling
  carrying that label; otherwise the gold node itself. Recall@k counts ranks at or below k.
- **Recall@5 and recall@10 on A**, over pairs (micro), each with a Wilson score interval at z = 1.96 (Wilson
  1927). Also reported over tasks (macro), as information.
- **MRR on A**: the mean over pairs of 1/rank when the rank is at or below 10, else 0.
- **B**: each pair, hit or miss at k = 10, with its rank (or "beyond k", or "no Ruling node").
- **C**: per task, arm O's count of rulings with score > 0, its count at or above registration's threshold, and
  what registration would bind (that count, capped at its limit of 8); arm H's candidate count at k = 10 and the
  number of distinct documents among them.
- **Diagnostics, never the bar.** For every A and B miss: the task's top 3 candidates and the missed ruling's
  text. For arm H, also whether a Section row containing the gold's span ranked in the top 10 among Section and
  Ruling rows (a granularity signal).
- **The bar (AD-031 section 4, unchanged):** recall@10 on A at or above 0.80, with the Wilson lower bound
  reported, and every B pair retrieved at k = 10. Per arm.
