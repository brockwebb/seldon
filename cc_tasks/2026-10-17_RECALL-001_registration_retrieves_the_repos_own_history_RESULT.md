# RECALL-001 RESULT: registration recalls the repositories' own history, and the use of it is measured

**Status:** all three Parts done on branch `worktree-agile-giggling-bird` (570a96e A, c5e34e8 B, 148cc20 C, a809432 fix). Full suite 2687 passed, 7 skipped, EXIT=0 (45 min, before a809432; the 28 recall and chart tests re-ran green after it). Not merged, not completed: that is the dispatcher's job (ADDENDUM 01).
**Tokens** (from the `part_complete` records, cumulative since launch): A 203,374 (orientation and reading the code included), B 213,690 (+10K), C 230,083 (+16K). About 0.26M at the end, against the 0.6M estimate.

**What was built.** `seldon/core/recall.py`. `cc register` (CLI and MCP) prints `Recall:` and records `recall_listed`. The list covers RESULTs, Issues (open and resolved), decision records of any status, and kept or superseded tasks, for seldon plus its `decisions.repositories` siblings, which resolve against the primary checkout. Retrieval is BM25 over all of it, fused by RRF with squiddy's served hybrid search, with zero model calls. A kept or superseded task whose reason names a failure is marked `DEAD END`. The dispatcher puts the list ahead of the dispatch line in all three launch-prompt paths. `cc complete` refuses a RESULT without `Recall used:`. `decision operator-catch` (CLI and MCP) adds a new `catch` kind to the register schema, which binds nothing. `qc chart` gains both weekly series. The config is the `recall:` block in seldon.yaml, and a project without the block gets no recall.

**First `Recall:` output on a real task** (this one, from the worktree, served arm against the primary's built graphs, 28.6 s):
```
- result  squiddy:2026-10-10_SQ-010_governed_admission_dn043_RESULT  2026-10-10  SQ-010 RESULT: governed admission in seconds ...
- result  squiddy:2026-10-11_SQ-011_admit_judge_bias_literature_s1_s9_by_maintenance_RESULT  2026-10-11  ...
- result  seldon:2026-09-12_ad030_governed_docs_ingest_RESULT  2026-09-12  RESULT: AD-030 governed documents ingest ...
- decision [accepted]  seldon:AD-036-R3 / seldon:AD-031-R3 / squiddy:R-110;  [proposed] seldon:AD-032-FC-17, FC-20
```
The lexical arm alone takes 7.2 s. Reading roughly 1,300 register files and three event stores is most of that.

**First chart reading** (`qc chart`, worktree): recall per week shows "no task registered with a Recall list yet"; operator catches show "none recorded yet". Both series start at the first registration after the merge.

**Decisions taken on the grounding (L4), so the operator can override them:**
1. The dispatcher completes worktree tasks, so it records the RESULT's `Recall used:` line at the merge (`recall_used`, with `missing`/`refused` when the line is absent or bad). It does not refuse the merge. Refusing would put a new merge gate under every task already in flight.
2. Tasks registered before this change have no `recall_listed` record and owe no line. This follows the `criteria_baseline`/`parts_baseline` precedent.
3. `Recall used:` must name ids from the task's own list, or `none`. Anything else is refused, so the measured rate is clean.
4. Prior art: case-based reasoning (Aamodt and Plaza 1994), active lessons-learned delivery (Weber, Aha and Becerra-Fernandez 2001), and ReMe (arXiv 2512.10696, found by a squiddy library search). Ranking uses BM25 (Robertson and Zaragoza 2009) and RRF k=60 (Cormack et al. 2009). The module docstring cites them.

**Premises found wrong or weaker than stated.**
- Premise 1 ("seldon's governed graph is served") is true only in the primary checkout. A worktree has no gitignored export, and squiddy then raises `SystemExit("FATAL: no served export")`. The served arm let that through and would have aborted the registration. Fixed in a809432, with a test.
- The served graph cannot be the only source. seldon's manifest holds 179 documents, against 50 RESULT files and over 1,100 cc_tasks files on disk, so the lexical arm reads the files directly.
- Premise 2 holds, and squiddy also imports from seldon's own interpreter.

**Open.** `min_shared_terms: 3` is an untuned first value. The chart is the evidence for moving it. Recall is off in squiddy and arnold until their seldon.yaml gains a `recall:` block.

Recall used: none (this task's list was produced by its own code after the design; AD-036-R3's BM25 parameters were adopted from reading `seldon/core/prior_art.py`, not from the list)
