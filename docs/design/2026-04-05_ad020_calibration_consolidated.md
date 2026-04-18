# AD-020 Consolidated Calibration Analysis — 8 Discovery Runs + 2 TEVV Verifications

**Date:** 2026-04-05
**Status:** Active
**Relates to:** AD-020 (Iterative Content Review Pipeline), AD-019 (Agentic Content Audit), AD-016 (Prose QC)
**Provenance:** Synthesized from 8 discovery audit runs (1 academic paper, 7 book chapters) and 2 TEVV verification runs (Ch 8, Ch 9). Individual calibration notes exist for leibniz-pi (AD-020_calibration_001), Ch 4 (002), and Ch 5 (003). This document supersedes those as the authoritative cross-run analysis.
**note_type:** calibration_analysis

---

## 1. Dataset

| Run | Document | Type | Model | Gates Run | Clusters | Signal:Noise |
|-----|----------|------|-------|-----------|----------|--------------|
| 001 | leibniz-pi | academic_paper | Sonnet | T1, T2a, T2b, T3 | 8 | 7/8 (87.5%) |
| 002 | Ch 4 | book_chapter | Opus | T1, T2a, T2b, T3, cascade | 8 | 8/8 (100%) |
| 003 | Ch 5 | book_chapter | Opus | T1, T2a, T2b, T3, cascade | 8* | 8/8* |
| 004 | Ch 6 | book_chapter | Opus | T1, T2a, T2b, T3, cascade | — | — |
| 005 | Ch 7 | book_chapter | Opus | T1, T2a, T2b, T3, cascade | — | — |
| 006 | Ch 8 | book_chapter | Opus | T1, T2a, T2b, T3, cascade | 8 | 8/8 (100%) |
| 007 | Ch 9 | book_chapter | Opus | T1, T2a, T2b, T3, cascade | 8 | 8/8 (100%) |
| 008 | Ch 10 | book_chapter | Opus | T1, T2a, T2b, T3, cascade | — | — |
| V-001 | Ch 9 (post-rev) | book_chapter | Sonnet | Full + delta | 8 baseline | — |
| V-002 | Ch 8 (post-rev) | book_chapter | Sonnet | Full + delta | 8 baseline | — |

*Runs 004, 005, 008 have synthesis YAMLs but were not individually analyzed in calibration notes. Findings are incorporated here at the aggregate level.*

---

## 2. Gate Effectiveness Ranking

Ranked by ratio of unique actionable findings to total output tokens consumed.

### Tier 1: Practitioner Stress Test — HIGHEST VALUE

The single highest-signal gate across all 8 runs. Findings from this gate drove the majority of revision work.

**What it catches that nothing else does:**
- Argument-level gaps invisible to assertion-by-assertion audit (e.g., "the chapter describes the framework but never shows how to use it")
- Perspective absences (e.g., Ch 9's System Owner question revealed the framework had no operationalization path)
- Bloom floor problems framed as practitioner frustration rather than abstract taxonomy

**Cross-run patterns:**
- Ch 9: 0/7/3 (worst) → 2/7/1 after revision. The 0/10 fully-answerable score was the clearest signal that the chapter needed structural work, not polish.
- Ch 8: 5/5/0 (strongest). Stable across revision — the chapter was already structurally sound.
- Ch 4: 0/9/0. Zero fully answerable — implementation guidance gap.
- leibniz-pi: 7/10 questions produced actionable findings. The adversarial framing surfaced the submission-blocking t=15 overstatement.

**Recommendation:** Run this gate on every chapter. If budget constrains to a single gate, run this one. The Feynman test (can a practitioner answer real questions from this material?) catches what correctness audits cannot.

### Tier 2: Cross-Chapter Cascade Checks — HIGHEST ROI FOR BOOKS

Unique to multi-chapter documents. Justifies its token cost on every run where it was applied.

**What it catches:**
- Number inconsistencies across chapters (6,954 vs 7,000 vs 6,987 across Ch 2/6/8/14)
- Broken bridge promises (Ch 5→Ch 6 "$15 vs $1,500" promise never fulfilled in the stated terms)
- Forward reference failures (Ch 4 uses SFV sub-dimensions before Ch 9 defines them)
- Attribution errors (Ch 9 attributed golden test set to Ch 7 instead of Ch 8)

**Cross-run pattern:** Every chapter audit that included cascade checks found at least one cross-chapter issue. The cascade check is the only gate that can detect inter-chapter drift — no single-chapter gate can see these.

**Recommendation:** Always run cascade checks for book chapters. The semantic anchor data from `seldon paper context` provides the cross-chapter context without reading every chapter in full.

### Tier 3: Content Audit (Assertion Classification) — FOUNDATION

The workhorse gate. Not the highest signal, but provides the structured data that other gates build on.

**What it catches:**
- Citation gaps (facts without sources)
- Judgments stated as facts (no framing language)
- Terminology inconsistencies against the glossary/ontology
- Content depth assessment (thin vs substantive sections)

**Limitation:** High assertion count but many findings are bookkeeping (add a citation) rather than structural. Citation density is a useful meta-signal: chapters with low citation density produce "cite more" findings; chapters with high citation density produce "cite better" findings. The content audit itself doesn't distinguish these — the pattern emerges in synthesis.

**Recommendation:** Always run. Fast, mechanical, provides the data layer for synthesis.

### Tier 4: Bloom Depth Check — MODERATE VALUE

Useful as a structural diagnostic but has high overlap with the practitioner stress test.

**What it catches:**
- Non-monotonic Bloom profiles (cognitive peaks before structural conclusions)
- Sections stuck at Remember/Understand when Apply is needed
- Missing scaffolding (reflection prompts, exercises)

**Overlap:** Most Bloom findings were also surfaced by the practitioner stress test through different framing. The two gates converge on the same issues — Bloom through taxonomy, practitioner through "can you do anything with this?"

**Unique contribution:** The Bloom floor/ceiling framing is useful for quantifying improvement across revisions (Ch 9: unchanged ceiling but better scaffolding density). Also useful for identifying the specific cognitive level a section fails at.

**Recommendation:** Run for discovery audits. May be skippable for TEVV verification passes where the practitioner score already captures the delta.

### Tier 5: Secondary Sweep (Narrative, Visual, Motivation, Clarity) — VARIABLE

Four lenses with uneven value:

- **Visual:** Consistently useful. Zero-figure finding appeared in 7/7 book chapters — but this is a book-level production issue, not a per-chapter finding. Once identified, suppress in subsequent chapter audits and track at book level.
- **Motivation:** Moderate. Catches urgency/relevance framing issues. Most useful for early-stage chapters where the "why should I care" question isn't answered.
- **Narrative:** Low value on mature chapters, moderate on drafts. Catches structural arc problems (front-loaded concrete / back-loaded abstract) but these are usually obvious to the author.
- **Clarity:** Moderate. Catches forward-reference problems and definition gaps. Overlaps with terminology check in content audit.

**Recommendation:** Run all four for discovery audits. For TEVV verification, run visual (to check if visual gaps were addressed) and skip narrative/clarity unless the revision was structural.

---

## 3. Document-Type Adjustments

The pipeline was calibrated on an academic paper first, then applied to book chapters. Key differences:

### Academic Paper vs. Book Chapter

| Dimension | Academic Paper | Book Chapter |
|-----------|---------------|--------------|
| Passive voice tolerance | Standard in Methods/Background — suppress flags | Active voice expected throughout |
| Citation density baseline | High (every claim cited) | Moderate (expert judgment acceptable if framed) |
| Practitioner stress test persona | Reviewer 2 (adversarial peer reviewer) | Working practitioner (trying to apply the material) |
| Bloom depth target | Analyze/Evaluate (reader evaluates argument) | Apply/Analyze (reader applies to own work) |
| Cross-chapter cascade | N/A for single paper | Essential — highest-ROI gate for books |
| Visual elements expectation | Figures and tables standard | Zero figures was universal (7/7) — production gap |
| Self-citation tolerance | Low (external grounding expected) | Higher (book can self-reference) but not 100% |

### Original Framework Chapters (Ch 9) vs. Applied Chapters (Ch 4, Ch 8)

Ch 9 (SFV) is an original theoretical contribution within the book. Applied chapters (Ch 4: extraction, Ch 8: evaluation) apply established or semi-established patterns. The audit should weight differently:

| Dimension | Original Framework | Applied Chapter |
|-----------|--------------------|-----------------|
| Canonical baseline check | Critical — does the chapter match its own defining document? | N/A or light — the chapter applies, doesn't define |
| External literature requirement | High — the framework must be positioned in the field | Moderate — references to prior work on the topic |
| Operationalization demand | High — the framework must be actionable | Already operational by nature |
| Self-citation tolerance | Low — novel claims need external anchoring | Higher — referencing other chapters is natural |

**Pipeline implication:** The `document_type` field in the synthesis YAML should include a `chapter_type` sub-field: `original_theoretical_framework`, `applied_engineering`, `survey_and_positioning`, `capstone_integration`. Gate weights and findings routing adjust per type. Ch 9 already has this (`chapter_type: original_theoretical_framework`).

---

## 4. Pipeline-Level Findings

### 4.1 Zero-Figure Finding Is a Book-Level Issue

The visual gap (zero figures) appeared in 7/7 book chapters audited. This is not 7 independent findings — it's one finding about the book's production state. Repeating it per-chapter wastes audit tokens and clutters the synthesis.

**Recommendation:** Track visual element counts at book level. In per-chapter audits, note the count but do not generate a cluster for it unless the chapter has uniquely visual content that's missing (e.g., a pipeline architecture chapter with no pipeline diagram).

### 4.2 Citation Density Predicts Audit Character

Chapters with low citation density produce content audit findings that say "cite more." Chapters with high citation density produce findings that say "cite better" (wrong source, outdated reference, claim overstates the citation).

This is a meta-pattern the synthesis engine should track: if a chapter's citation density is below a threshold (e.g., <1 citation per 500 words for book chapters), the content audit will be dominated by gap-filling. If above threshold, it shifts to accuracy-checking. The author should know this upfront — it changes the revision task from "find sources" to "verify sources."

### 4.3 Self-Citation Rate Is a Quality Signal for Framework Chapters

Ch 9 had 100% self-citation rate at discovery audit. This dropped to 55.6% after revision (3 external citations added). For an original framework chapter, high self-citation rate signals the framework hasn't been positioned in the literature — a trust problem for readers and reviewers.

**Threshold recommendation:** Framework chapters should target <70% self-citation for substantive citations (excluding cross-chapter references to the book's own content). Applied chapters can tolerate higher self-citation since they naturally reference other chapters.

### 4.4 Single-Model Audit→Revise→Re-Audit Is a Closed Loop

The TEVV verification runs used the same model family (Sonnet for V-001/V-002) as the pipeline that generated findings (Opus for discovery). The Ch 9 delta summary demonstrated a T2 error (False State Injection) where the auditor recalled scores from a rogue thread instead of reading the baseline YAML.

This is a single-model feedback loop: the same model generates findings, the author revises, and the same model evaluates the revision. Diminishing returns are inevitable — the model has blind spots that persist across runs.

**Next TEVV extension:** Multi-model evaluation. Use Gemini or OpenRouter as a second auditor on a subset of gates (practitioner stress test is the obvious candidate). Defer until same-model TEVV is fully validated — which it now is.

### 4.5 Delta Summary Must Mechanically Copy Baseline Scores

The Ch 9 TEVV verification revealed a concrete pipeline failure: the delta summary reported baseline practitioner scores as 2/5/3 when the actual run-001 scores were 0/7/3. The auditor recalled scores from a contaminated thread instead of reading the file.

**Hard rule:** Delta summaries must include a `# Copied verbatim from` comment with the source filepath for every baseline score. The CC task template must instruct the auditor to read the baseline YAML file and copy the numbers — not recall them.

This is an instance of SFV Threat T2 (False State Injection): the wrong state entered the pipeline and would have produced a false improvement signal if not caught. The correction was only possible because the baseline YAML existed as ground truth.

---

## 5. TEVV Verification Results

Two chapters completed full TEVV cycles (discovery → revision → re-audit → delta):

### Ch 9: `revise_before_use` → `conditionally_ready`

| Metric | Baseline (run-001) | Post-revision (run-002) | Delta |
|--------|-------------------|------------------------|-------|
| Practitioner score | 0/7/3 | 2/7/1 | +2 fully, -2 not answerable |
| Canonical baseline | FAILED | CONFIRMED | Critical resolution |
| External citation rate | 0% | 33% | Major improvement |
| Self-citation rate | 100% | 55.6% | Meets threshold |
| Visual elements | 0 | 3 tables | From zero to functional |
| Reflection prompts | 1 | 3 | Distributed at pause points |
| Word count | 2,160 | 3,210 | +49% (all substantive) |
| Clusters resolved | — | 5/8 resolved, 3/8 partial | No clusters still fully open |

### Ch 8: Stable (`conditionally_ready`)

| Metric | Baseline (run-001) | Post-revision (run-002) | Delta |
|--------|-------------------|------------------------|-------|
| Practitioner score | 5/5/0 | 5/5/0 | No change (already strong) |
| Visual elements | 0 | 0 | Still open (structural decision) |
| Citation gaps | 2 | 1 | FCSM/NIST/SWE-CI cited |
| Factual corrections | — | 3 | 6,954 count, $15/$100 scope, RLI reconnect |
| Clusters resolved | — | 4/8 resolved, 2/8 partial, 2/8 still open | Structural items deferred |

**Key observation:** Ch 8's revision was factual cleanup, not structural change. The practitioner score didn't move because the chapter was already structurally sound — the open items (visual gap, crosswalk Bloom valley) are authorial scope decisions, not audit-driven fixes. The TEVV verification correctly classified this as "stable" rather than "improved."

---

## 6. Recommendations for Pipeline Configuration

### Gate Selection by Purpose

| Purpose | Gates to Run |
|---------|-------------|
| Discovery audit (first pass) | All: content audit, practitioner stress test, Bloom depth, secondary sweep, cascade (if multi-chapter) |
| TEVV verification (post-revision) | Content audit, practitioner stress test, cascade. Skip Bloom and secondary sweep unless revision was structural. |
| Quick quality check | Practitioner stress test only |
| Pre-submission review | Full discovery + multi-model second opinion |

### Synthesis Engine Adjustments

1. **Cluster zero-figure findings at book level**, not per-chapter. Track visual element count per chapter as a metadata field in the run manifest.

2. **Include `chapter_type` in synthesis config.** Adjust canonical baseline check weight, external citation requirements, and operationalization demand per type.

3. **Citation density as a meta-signal.** Report it in the synthesis summary. If below threshold, prepend a note to the content audit findings: "This chapter has low citation density. Content audit findings will be dominated by gap-filling rather than accuracy-checking."

4. **Self-citation rate for framework chapters.** Report in synthesis summary. Flag if >70% for `original_theoretical_framework` chapters.

5. **Delta summary baseline scores must be mechanically copied.** The CC task template must include explicit instructions to read the baseline YAML and copy verbatim. No derivation from memory.

### Audit Directory Convention

```
project/audits/
├── run-001_YYYY-MM-DD/      # Discovery audit
│   ├── chapter-NN_*.yaml    # Gate outputs per chapter
│   └── run_manifest.yaml    # Run metadata
├── run-002_YYYY-MM-DD/      # TEVV verification
│   ├── chapter-NN_*.yaml    # Gate outputs for audited chapters only
│   ├── chapter-NN_delta_summary.yaml  # Comparison to baseline
│   └── run_manifest.yaml
└── ...
```

Run numbering is sequential per project. Run manifests link back to baseline runs for TEVV verification.

---

## 7. Open Questions

1. **Gate cost tracking:** Token counts per gate per chapter would enable actual ROI calculation rather than qualitative ranking. Not yet instrumented.

2. **Multi-model TEVV:** Which gates benefit most from a second model's perspective? Hypothesis: practitioner stress test (different models generate different questions) and cascade checks (different models catch different cross-chapter inconsistencies).

3. **Automation boundary for delta summaries:** The delta summary is currently a judgment call by the auditor (is this cluster resolved?). How much should the pipeline trust this vs. requiring mechanical verification (e.g., regex for the presence of specific content)?

4. **Diminishing returns curve:** At what point does re-auditing a chapter produce noise rather than signal? The Ch 8 TEVV run was useful (factual corrections confirmed) but the structural open items were already known. A third run on Ch 8 would likely produce zero new findings.

---

*This document supersedes the per-run calibration notes (AD-020_calibration_001, _002, _003) as the authoritative cross-run analysis. Individual notes remain as historical records of per-run findings.*
