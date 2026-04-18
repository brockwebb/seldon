# AD-020 Calibration Point 002: Chapter 4 (ai-workflow-design)

**Date:** 2026-04-02
**Document type:** `book_chapter`
**Pipeline:** AD-020 Multi-Lens Review Pipeline (manual Phase 1)
**Operator:** Claude Opus 4.6

---

## Calibration Observations

### 1. Tier 1 (Content Audit) Sensitivity

Chapter 4 has only 2 citations for 48 assertions. Unlike Ch 3 which had many unsupported factual claims (NAICS codes, fine-tuning costs, deployment timelines), Ch 4's uncited assertions are mostly design judgments and principles. The distinction matters for calibration: the Tier 1 audit correctly classifies most of Ch 4's content as judgment rather than factual claim, resulting in fewer citation_gap findings (6 vs 14 for Ch 3). This is appropriate — design principle chapters have different citation profiles than empirical chapters.

### 2. Practitioner Stress Test Results

0/9 fully answerable, 6/9 partially answerable, 3/9 not answerable. This is a worse score than might be expected from a chapter that feels well-written. The gap is consistent: the chapter operates at the design pattern level and never descends to implementation. For a `book_chapter` document type targeting practitioners who need to build things, the implementation gap is the dominant finding.

Calibration note: the stress test persona ("build by next quarter") may be too implementation-focused for a chapter that is explicitly about design patterns. The chapter's own framing positions itself as architectural guidance, not a tutorial. However, the AD-020 spec says the stress test for `book_chapter` is "Can I use this?" — and "use" implies implementation. The stress test is calibrated correctly; the chapter's scope is the issue, not the test.

### 3. Bloom Check Structural Finding

The non-monotonic Bloom progression (Evaluate -> Analyze -> Evaluate -> Create -> Apply -> Understand) is a structural observation unique to this chapter. The thought experiment placement inside the Confidence Laundering section rather than after the synthesis creates a cognitive descent at the end. This is not something the Ch 3 audit surfaced because Ch 3's thought experiment was at the end.

Calibration note for `book_chapter` type: check whether the chapter's cognitive peak (highest Bloom level) occurs at or near the end of the chapter. If the peak occurs in the middle and the chapter descends afterward, that is a structural finding worth flagging.

### 4. Secondary Sweep — Visual Gap as Primary Finding

The zero-figures observation (SS-09) was flagged as "major" severity. For a chapter about pipeline design, the absence of any pipeline diagram is a significant communication gap. This finding converged with practitioner (need a reference architecture), clarity (SFV mapping is hard to follow in prose), and narrative (second half is abstract without visual anchoring).

Calibration note for `book_chapter` type: chapters about architectural patterns or pipeline design should always be checked for visual representation. If zero figures exist, that is almost certainly a major finding.

### 5. Cascade Finding — SFV Sub-dimensions Not in Ch 9

The highest-severity cascade finding is that Ch 4 uses SFV sub-dimension names (CF, TC, SP) that are defined in the ai4stats predecessor and this book's glossary but NOT in this book's Ch 9, which only defines threats (T1-T5). This is a terminology consistency issue that affects multiple chapters.

Calibration note: cascade checks on terminology references should verify the term is defined in the specific target chapter, not just that it exists somewhere in the book. The glossary is not a substitute for in-chapter introduction, especially when the using chapter comes before the defining chapter in reading order.

### 6. Comparison to Ch 3 Calibration (AD-020_calibration_001)

No prior chapter-level calibration exists for this book (calibration_001 was for the leibniz-pi paper). Comparing to the Ch 3 content audit:

| Metric | Ch 3 | Ch 4 |
|--------|------|------|
| Total assertions | 52 | 48 |
| Citations | 1 | 2 |
| Citation gaps | 14 | 6 |
| Judgments as fact | 5 | 3 |
| Thin sections | 2 | 0 |
| Cross-section impacts | 8 | 9 |

Ch 4 is better-cited relative to its claims, has no thin sections, and has fewer judgments stated as fact. The main gaps are implementation guidance and visual representation, not factual support. This suggests Ch 4 is a more mature draft than Ch 3 was at audit time.

---

## Pipeline Performance Notes

- Total time: single session, ~30 minutes operator time
- The cascade checking step is the most valuable for cross-chapter consistency. The SFV sub-dimension gap would not have been found by any single-chapter lens.
- The synthesis clustering worked well: 8 clusters with clear convergence ordering. No unclustered findings, which suggests the lenses produced overlapping rather than orthogonal findings for this chapter.
- For `book_chapter` type, the practitioner stress test and visual gap check are the highest-value gates. The Bloom check adds structural insight but rarely produces actionable findings on its own — it converges with other lenses.
