# Design Note: Regression Audit Loop for Revision Verification

**Date:** 2026-04-05
**Status:** Design
**Relates to:** AD-020 (Iterative Content Review Pipeline), AD-018 (Document Structure Graph), AD-019 (Agentic Content Audit)
**Provenance:** Pattern identified from analysis of 8 AD-020 calibration runs (leibniz-pi, Ch 3-10). The pipeline produces audit findings and the author revises, but no structured step verifies whether revisions resolved the findings. This note designs the verification loop.
**note_type:** pattern_proposal

---

## 1. The Gap

AD-020's current workflow is open-loop:

```
Audit → Findings → Author revises → ???
```

There is no structured step that evaluates whether a revision addressed the audit findings. The author revises, the chapter moves forward, and whether the revision landed is left to the author's judgment or the next full audit run — which rediscovers everything from scratch rather than checking against prior findings.

This is the TEVV gap. NIST AI RMF's TEVV framework (Test, Evaluate, Verify, Validate) requires continuous evaluation integrated into the development lifecycle. The current pipeline implements Test (audit gates) and Evaluate (synthesis and scoring) but lacks Verify (did the revision resolve the findings?) and Validate (does the revised chapter serve its purpose?).

## 2. What a Regression Audit Does

A regression audit is a targeted re-evaluation of a chapter against its prior audit findings. It is NOT a full re-audit. It answers three questions:

1. **Resolution scoring:** For each cluster in the prior `review_synthesis.yaml`, is the finding resolved, partially resolved, or still open?
2. **Regression detection:** Did the revision introduce new issues not present in the prior audit?
3. **Improvement measurement:** Did measurable scores change? (Practitioner stress test answerability, Bloom ceiling, citation density, etc.)

### Input

- The revised chapter (full text)
- The prior `review_synthesis.yaml` (baseline findings)
- Compressed cross-chapter context: all sibling sections' semantic anchor data from `seldon paper context` (core_argument, claims, forward_promises, terminology_defined, open_threads). This is already populated in the graph for ai-workflow-design.
- The prior gate-specific YAML files if needed for detailed checking (content_audit, practitioner_stress_test, bloom_depth_check, etc.)

### Output

A `regression_audit.yaml` file with:

```yaml
regression_audit:
  chapter: "book/chapter-09.md"
  date: "2026-04-XX"
  baseline_audit: "audits/chapter-09_review_synthesis.yaml"
  baseline_date: "2026-04-05"

  resolution_summary:
    total_clusters: 8
    resolved: N
    partially_resolved: N
    still_open: N
    new_issues: N

  cluster_resolutions:
    - cluster_id: C1
      title: "SFV Definition Incompleteness and Sub-dimension Absence"
      baseline_severity: high
      resolution: resolved | partially_resolved | still_open
      evidence: "Complete SFV definition now present at line XX. Sub-dimension table added. Crosswalk table added."
      remaining_gaps: []  # or list of what's still missing

    - cluster_id: C2
      title: "Framework Actionability Gap"
      resolution: partially_resolved
      evidence: "Threat triage table added. Two reflection prompts added."
      remaining_gaps:
        - "Operationalization metrics section still absent"
        - "Apply-level scaffolded exercise not yet added"

  score_changes:
    practitioner_stress_test:
      baseline: "0/10 fully answerable"
      current: "4/10 fully answerable"
      delta: "+4"
    bloom_ceiling:
      baseline: "Evaluate"
      current: "Evaluate"
      delta: "unchanged"
    reflection_prompts:
      baseline: 1
      current: 3
      delta: "+2"
    visual_elements:
      baseline: 0
      current: 2
      delta: "+2"

  new_issues: []  # findings not present in baseline

  verdict: "revision_accepted" | "revision_partial" | "revision_insufficient"
```

## 3. Cross-Chapter Awareness via Semantic Anchors

The regression audit must check cross-chapter findings — bridge promises, forward references, terminology consistency, number discrepancies. This requires context beyond the single chapter being audited.

The infrastructure already exists: `seldon paper context` queries the graph for a section's semantic anchor properties and its dependency relationships. The semantic anchors for all 14 ai-workflow-design chapters are populated with core_argument, claims, forward_promises, and terminology_defined.

For the regression audit, the auditor needs a **compressed context block** containing all sibling sections' semantic anchors. This is a read from the graph — no new data structures needed. The audit prompt includes:

```
CROSS-CHAPTER CONTEXT (compressed from graph):

Chapter 05: "Multi-model design is the correct baseline..."
  Forward promises: chapter-06 (topology execution), chapter-08 (evaluation harness), chapter-09 (model selection drift)

Chapter 06: "LLM API calls are the bottleneck..."
  Forward promises: chapter-07 (checkpoint architecture), chapter-11 (infrastructure reinvention), chapter-14 (batch economics)

[etc. for all siblings]
```

This lets the regression audit verify:
- Did the Ch 5→Ch 6 bridge promise ("$15 vs $1,500") get fulfilled?
- Did the Ch 6→Ch 10 forward reference (knowledge graph treatment) get resolved?
- Did the 6,954/6,987/7,000 number get unified across chapters?

Without re-reading every chapter in full.

## 4. When to Run

The regression audit is triggered by the author, not automated. It runs after a revision pass on a chapter that has a prior audit. Natural integration point:

```
Author revises chapter → seldon paper sync → regression audit → score resolution
```

The regression audit is lighter than a full audit — it checks specific findings against the revised text rather than discovering findings from scratch. Estimated token cost: 30-50% of a full audit run.

## 5. What This Enables

### Authoring Stage Awareness

The calibration analysis identified that the pipeline lacks stage awareness — it treats every chapter as if it should be submission-ready. The regression audit solves this differently than a `draft_stage` parameter would. Instead of suppressing findings on early drafts, the regression audit tracks **progress across revisions**. A chapter that scores 0/10 on the practitioner stress test in its first audit and 4/10 after revision is making measurable progress. The score is meaningful at both stages — it just means different things.

### Recurring Finding Aggregation

The visual gap finding (zero figures) appeared in 7/7 chapter audits. A regression audit would score this per-chapter: Ch 4 still has zero figures (still_open), Ch 6 now has 2 figures (resolved). The book-level pattern becomes a tracked metric rather than a repeated discovery.

### TEVV Completion

The regression audit closes the TEVV loop:

| TEVV Phase | Seldon Implementation |
|------------|----------------------|
| **Test** | AD-020 audit gates (content audit, stress test, Bloom, secondary sweep) |
| **Evaluate** | Synthesis engine (clustering, convergence scoring, verdict) |
| **Verify** | Regression audit (did the revision resolve the findings?) |
| **Validate** | Practitioner stress test score improvement across revisions (does the chapter serve its purpose?) |

This is not theoretical TEVV bolted onto a separate process. The audit data, the revisions, the regression scores, and the cross-chapter dependencies are all tracked through the same graph that the book itself is assembled from. The book about TEVV-integrated AI workflows is produced through a TEVV-integrated AI workflow.

## 6. Implementation Options

### Option A: CC Task Template (Immediate)

Write a `cc_task_regression_audit.md` template that:
1. Loads the prior `review_synthesis.yaml`
2. Reads the revised chapter
3. Queries `seldon paper context` for all siblings' semantic anchors
4. Walks each prior cluster, checks resolution against revised text
5. Re-runs practitioner stress test (subset — only questions that were unanswerable)
6. Outputs `regression_audit.yaml`

No new CLI commands. No new code. Just a structured CC task that uses existing infrastructure.

### Option B: `seldon paper regression` Command (Near-term)

A CLI command that automates the template:
```
seldon paper regression chapter-09 --baseline audits/chapter-09_review_synthesis.yaml
```

Loads baseline, revised chapter, and cross-chapter context automatically. Invokes the auditor agent with a regression-specific prompt. Outputs the regression YAML.

### Option C: Integrated into `seldon paper audit` (Future)

`seldon paper audit chapter-09.md` detects that a prior `review_synthesis.yaml` exists and automatically runs in regression mode rather than full discovery mode. The author doesn't have to specify — the pipeline is stage-aware by virtue of tracking its own history.

### Recommendation

Option A first. Dogfood the regression audit as a CC task template on the next chapter revision (Ch 9 is the obvious candidate — it has the most findings and the clearest revision spec). If the pattern proves useful, implement Option B as a CLI command. Option C is the long-term target but requires the regression YAML format to stabilize first.

## 7. Calibration Data That Motivates This

From 8 AD-020 runs:

| Chapter | Practitioner Score | Visual Elements | Key Finding | Revision Status |
|---------|-------------------|-----------------|-------------|-----------------|
| leibniz-pi | n/a | ~1 | t=15 overstatement | Revised, no regression audit |
| Ch 3 | n/a | n/a | Citation density | Revised, no regression audit |
| Ch 4 | 0/9 | 0 | Implementation gap | Revised, no regression audit |
| Ch 5 | 3/10 | 0 | Composition gap | Revised, no regression audit |
| Ch 6 | n/a | 0 | Number inconsistency | Unknown |
| Ch 7 | n/a | 0 | GPT-5 temp claim | Unknown |
| Ch 8 | n/a | 0 | Cost discrepancy | Unknown |
| Ch 9 | 0/10 | 0 | SFV definition truncated | Not yet revised |
| Ch 10 | 0/10 | 0 | KG forward ref broken | Not yet revised |

"Revised, no regression audit" — revisions happened but nobody checked whether the findings were resolved. The regression audit fills this gap.

## 8. Open Questions

1. **Scope of re-testing:** Should the regression audit re-run all gates or only the ones that produced findings? Running all gates catches regressions but costs more tokens. Running only affected gates is cheaper but misses new issues introduced by the revision.

2. **Cross-chapter regression:** When a revision in Ch 10 resolves a forward reference from Ch 6, should the regression audit update Ch 6's audit record too? Or is that a separate regression audit on Ch 6?

3. **Baseline staleness:** If a chapter has been revised multiple times, which audit is the baseline? The most recent one, or the original discovery audit? The most recent is more relevant, but the original establishes the full finding set.

4. **Automation boundary:** The regression audit template uses the auditor agent, which is an LLM. The resolution scoring is therefore a judgment call, not a mechanical check. How much should the pipeline trust the agent's resolution assessment vs. requiring human confirmation?

---

*This design note will be registered as a DesignNote artifact with `informs` edges to AD-020, AD-018, and AD-019.*
