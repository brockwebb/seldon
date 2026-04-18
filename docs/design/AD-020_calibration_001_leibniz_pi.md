# AD-020 Calibration Data — Run 001: Leibniz-Pi Paper

**Date:** 2026-04-02
**Document type:** `academic_paper`
**Target:** leibniz-pi paper (~63KB, 8 sections + appendix)
**Pipeline version:** Manual Phase 1 (CC task, single session, all tiers)
**Model:** Claude Code (Sonnet)

---

## Run Parameters

| Parameter | Value |
|-----------|-------|
| Document type | `academic_paper` |
| Stress test persona | Reviewer 2 (GP/EC venue) |
| Depth check mode | Argument completeness (Bloom replaced) |
| Tiers run | 1, 2a, 2b, 3 |
| Synthesis format | Clustered YAML |
| Context fit | Entire paper in single window |
| Agent team used | No (paper fits in one context) |

## Results Summary

| Metric | Value |
|--------|-------|
| Total clusters produced | 8 |
| Convergence range | 2–4 |
| Unclustered items | 9 |
| Submission-blocking findings | 1 (Cluster 1: t=15 overstatement) |
| Substantive improvements | 5 (Clusters 2, 3, 5, 7, 8) |
| Bookkeeping | 1 (Cluster 4: evidence map gaps) |
| Author-dismissed (false positive) | 1 (Cluster 6: heatmap — table was deliberate) |
| Signal-to-noise ratio | 7 actionable / 8 total = 87.5% |

## Gate Effectiveness

### Tier 1: Correctness Audit
- **Useful:** Found 8 missing evidence map entries, cross-section inconsistency (t=15 claim vs Table 5), terminology gaps
- **Noise:** Automated prose QC (passive voice flags) produced 47 false positives in Methods/Background where passive voice is standard academic convention
- **Verdict:** Useful for facts and citations. Prose QC needs `academic_paper` calibration to suppress passive voice in Methods/Background.

### Tier 2a: Reviewer Stress Test
- **Most useful gate overall.** Produced the highest-impact findings: t=15 overstatement (Q1), population scaling gap (Q3), wrong-limit attractor dominance question (Q4), cross-domain evidence gap (Q7), discovery equation rigor (Q10).
- **Generated 10 questions, 7 produced actionable findings.**
- **Key insight:** The adversarial framing forces the auditor to think like a critic, not a copyeditor. This surfaces argument-level issues that Tier 1 misses entirely.
- **Noise:** Q6 (discovery criterion thoroughness) confirmed the paper handles it well — a true negative, not noise, but it consumed tokens for a non-finding.
- **Verdict:** This is the gate to run if you only run one gate.

### Tier 2b: Argument Completeness
- **Useful:** Found 3 claims-without-evidence, 2 evidence items overstated by their claims, 1 logical gap (population scaling).
- **Overlap with Tier 2a:** High. Most argument completeness findings were also surfaced by the stress test through different framing. The two gates converged on the same issues (t=15, wrong-limit attractor dominance, population scaling).
- **Unique contribution:** The overstated-claim finding (OC-01, OC-02 re: t=15) was the most precise version of the Cluster 1 issue — it identified the exact textual inconsistency while Tier 2a identified it as a reviewer question.
- **Verdict:** Valuable for convergence scoring. May be redundant as a standalone gate for papers where Tier 2a is strong.

### Tier 3: Secondary Lens Sweep
- **[motivation]**: Productive. Identified the missing cross-domain connection to AI safety/RL communities (contributed to Cluster 2).
- **[visual]**: Mixed. Correctly identified that the scaling grid has no figure (Cluster 6), but the author dismissed this as a deliberate design choice (table is more readable). Also caught a minor visual separator issue. 1 false positive / 1 useful.
- **[narrative]**: Low value for a mature paper. Mostly confirmed the paper's structure works. The Discussion roadmap suggestion (unclustered) is minor. For papers in early drafting, this lens would be more useful.
- **[clarity]**: Moderate. Found the kinetics forward-reference issue (contributed to Cluster 5) and the deceptive attractor definition gap (unclustered). These are real but minor.
- **Verdict:** The blended approach works — having one pass with tagged lenses prevented duplicate findings. For `academic_paper`, the [motivation] lens was more useful than expected; the [narrative] lens was less useful than expected.

## Document Type Calibration Findings

### What worked for `academic_paper`:
1. Reviewer Stress Test persona ("Reviewer 2") produced the highest-signal findings
2. Argument completeness check correctly replaced Bloom taxonomy — an academic paper doesn't scaffold cognitive levels
3. Citation checking at full intensity was appropriate — every uncited factual claim was correctly flagged
4. Clustering by topic (not by gate) correctly identified that the t=15 issue was ONE problem flagged by FOUR gates

### What needs adjustment for `academic_paper`:
1. **Suppress passive voice heuristics in Methods and Background.** Passive voice is standard in these sections. The 47 false positives are noise.
2. **Narrative lens should be lighter.** For a mature paper, compress to "does each section earn its place?" rather than a full arc analysis. Full narrative analysis is more useful for early drafts.
3. **Consider making Tier 2b optional when Tier 2a is run.** The overlap is high enough that running both may not justify the token cost for papers. Keep both for books (where argument completeness and practitioner stress test cover different ground).
4. **The [visual] lens needs a mechanism for the author to pre-declare deliberate design choices.** The heatmap false positive occurred because the pipeline didn't know the table was intentional. A `review.dismissed` config key or annotation in the section file would prevent this on re-runs.

## Synthesis Format Assessment

- **Clustering worked.** The t=15 cluster drew from 4 gates; without clustering it would have been 4 separate items the author might not have connected.
- **Convergence scoring worked as a priority signal.** Convergence 4 → fix before submission. Convergence 2 → address if time permits. This matched the author's own judgment.
- **Serial processing worked.** Each cluster was self-contained. Author could read one, decide, move on.
- **8 clusters was manageable.** The cap of 8 in the CC task was appropriate. The 9 unclustered items were correctly deprioritized.
- **Suggested scope (not suggested edits) was the right granularity.** "Qualify the t=15 claim" gives the author enough to act without prescribing prose.

## Comparison: What Would the Author Have Caught on a Manual Read?

| Finding | Author would catch? | Pipeline value-add |
|---------|--------------------|--------------------|
| Cluster 1: t=15 overstatement | Maybe — the number is in the abstract, the table is 20 pages later. Easy to miss on a skim read. | High — this is the submission-blocking issue |
| Cluster 2: Missing cross-domain citations | Probably not on a final read — the framing feels natural | Medium — reviewer will definitely ask |
| Cluster 3: Attractor dominance overstatement | Probably yes — author knows the data | Low — confirms what author suspects |
| Cluster 4: Evidence map gaps | No — this is bookkeeping nobody does on a final read | High for provenance hygiene |
| Cluster 5: Kinetics analogy scope | Maybe — depends on how fresh the author's eyes are | Medium |
| Cluster 6: Heatmap (dismissed) | N/A — author already decided against it | False positive |
| Cluster 7: Population scaling | Probably yes — author knows the limitation | Low — but the Sastry computation suggestion is new |
| Cluster 8: Discovery equation | Maybe — depends on how the reviewer reads it | Medium |

**Net assessment:** The pipeline's highest value was Cluster 1 (catching a factual inconsistency the author might miss on a final read) and Cluster 2 (identifying citation gaps the author might not notice because the prose reads naturally without them). These are exactly the failure modes the pipeline is designed to catch.

---

## Next Calibration Target

ai-workflow-design book, Chapter 4 (document_type: `book_chapter`). This will test whether the Bloom taxonomy gate, the Practitioner Stress Test with practitioner persona, and the full narrative lens produce value on pedagogical content.
