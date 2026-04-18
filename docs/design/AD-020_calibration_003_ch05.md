# AD-020 Calibration Point 003: Chapter 5 (ai-workflow-design)

**Date:** 2026-04-03
**Document type:** `book_chapter`
**Pipeline:** AD-020 Multi-Lens Review Pipeline (manual Phase 1)
**Operator:** Claude Opus 4.6

---

## Calibration Observations

### 1. Tier 1 (Content Audit) — Citation Density Shift

Chapter 5 has 14 citations for 58 assertions, making it by far the most citation-dense chapter audited. Compare:

| Metric | Ch 3 | Ch 4 | Ch 5 |
|--------|------|------|------|
| Total assertions | 52 | 48 | 58 |
| Citations | 1 | 2 | 14 |
| Citation density | 1.9% | 4.2% | 24.1% |
| Citation gaps (medium+) | 14 | 6 | 4 |
| Cross-reference checks | n/a | 9 | 6 |

The higher citation density changes the Tier 1 audit's character. For Ch 3 and Ch 4, the dominant finding was "not enough citations." For Ch 5, the dominant findings shift to citation quality issues: context mismatch (fortier_2011/wolf_2016 supporting "structured output comparison"), content overlap with Ch 1, and unverified quantitative claims (Self-Refine ~20%, TWIX 520x). This is the correct calibration shift: as citation density increases, the audit should transition from "cite more" to "cite better."

### 2. Practitioner Stress Test — Decision-Making Chapter Signal

The stress test produced markedly different results for Ch 5 vs Ch 4:

| Metric | Ch 4 | Ch 5 |
|--------|------|------|
| Fully answerable | 0 | 3 |
| Partially answerable | 6 | 6 |
| Not answerable | 3 | 1 |
| Top gap type | Implementation (tools, code) | Composition & measurement |

Ch 4's gap was implementation guidance: the chapter operates at design-pattern level and the practitioner cannot build from it. Ch 5's gap is different: the practitioner can build individual topologies but cannot compose them, measure independence, or operate under cost constraints. This is a higher-level gap — the chapter successfully communicates "what to build" but insufficiently addresses "how to choose and combine."

This distinction matters for the `book_chapter` stress test calibration. Decision-making chapters (like Ch 5's "Choosing Your Topology") should be stress-tested on decision quality, not implementation detail. The Ch 5 stress test correctly targeted decision scenarios ("I have two models disagreeing on 3%," "my agency cannot afford 3x costs") rather than implementation scenarios ("what tools do I use"). The stress test persona adapted appropriately to the chapter's scope.

### 3. Bloom Gate — Decision Chapter Reaches Evaluate Consistently

Ch 5's Bloom progression: Understand -> Evaluate -> Evaluate -> Evaluate -> Evaluate -> Apply -> Create -> Understand

This is the strongest progression across all three audited chapters. Three consecutive topology sections sustain Evaluate through well-crafted reflection prompts. The Choosing Your Topology section also reaches Evaluate through the "none of the above" reversal. The thought experiment reaches Create with proper positioning (after cross-cutting principles, before bridge).

Comparison:

| Metric | Ch 4 | Ch 5 |
|--------|------|------|
| Ceiling | Create | Create |
| Sustained Evaluate sections | 2 | 4 |
| Monotonic? | No (Create -> Apply descent) | Nearly (brief Apply dip) |
| Thought experiment position | Mid-chapter (before synthesis) | End (after synthesis) |
| Scaffolding verdict | adequate_with_gaps | strong |

The Bloom gate on a decision-making chapter produces more valuable signal than on a domain workflow chapter. Decision-making chapters should naturally sustain Evaluate (the whole point is judgment), so the Bloom check confirms whether the chapter delivers on its structural promise. Ch 5 does; Ch 4 did not consistently.

Calibration note: the Bloom gate's highest value for `book_chapter` is detecting structural failures (thought experiment in wrong position, synthesis dropping to Apply). For decision-making chapters, the Bloom gate should expect sustained Evaluate across the decision-relevant sections and flag any that drop below.

### 4. Cascade Findings — Cross-Cutting Position

Ch 5 sits at a cross-cutting position in the book: it references Ch 1 (iterative refinement), Ch 2 (Concept Mapper case study), Ch 6 (parallel execution), and Ch 9 (drift/validity). The cascade check found:

- Ch 1: Content overlap confirmed (six shared citations with similar treatment)
- Ch 2: Cross-references clean
- Ch 6: Bridge promise broken ("$15 vs $1,500" not in Ch 6)
- Ch 9: Forward reference clear

The content overlap with Ch 1 is a new cascade pattern not seen in Ch 4's audit. Ch 4 had a forward reference problem (SFV terms used before defined). Ch 5 has a backward overlap problem (re-presenting material already covered). These are complementary failure modes:

- Forward reference: using terms before the reader encounters their definition
- Backward overlap: re-presenting evidence the reader already encountered

Both are chapter-ordering issues, not content errors. The recommended resolution patterns differ: forward references need framing ("Ch 9 will formalize this; here is a preview"). Backward overlaps need compression ("Ch 1 documented this in detail; the design implication is...").

The broken bridge promise ("$15 vs $1,500") is actionable and should be resolved before publication. Bridge promises are reader contracts.

### 5. Length/Maturity Interaction

Ch 5 is a longer, more developed chapter than Ch 4. The effect on signal-to-noise:

- **Higher citation density** shifted Tier 1 from "cite more" to "cite better" — better signal quality.
- **More developed topology sections** gave the practitioner stress test more material to answer from, resulting in 3 fully answerable questions (vs 0 for Ch 4). The remaining gaps are higher-quality signal: composition, measurement, cost optimization rather than basic "how do I build anything."
- **Well-positioned thought experiment** eliminated the structural Bloom finding that dominated Ch 4 (thought experiment in wrong position).
- **Consistent section structure** across three topologies reduced narrative findings to convergent issues (citation dump, visual absence) rather than structural problems.

Net assessment: more mature chapters produce higher-quality audit signal. The pipeline's value increases with chapter maturity because it shifts from detecting structural problems (which the author likely knows about) to detecting subtle gaps (citation context, composition guidance, bridge promises) that the author is less likely to notice.

### 6. Comparison Table: Run 002 vs Run 003

| Dimension | Run 002 (Ch 4) | Run 003 (Ch 5) |
|-----------|----------------|----------------|
| **Citations** | 2 for 48 assertions | 14 for 58 assertions |
| **Tier 1 dominant finding** | Citation density below claim density | Citation quality issues (context, overlap) |
| **Practitioner fully answerable** | 0/9 | 3/10 |
| **Practitioner top gap** | Implementation guidance absent | Composition & measurement gaps |
| **Bloom ceiling** | Create | Create |
| **Bloom sustained Evaluate** | 2 sections | 4 sections |
| **Bloom scaffolding** | adequate_with_gaps | strong |
| **Bloom structural issue** | Thought experiment mid-chapter | None |
| **Synthesis clusters** | 8 | 8 |
| **Highest convergence** | 4 (implementation gap) | 4 (visual absence) |
| **Visual gap** | Major (zero figures) | Major (zero figures) |
| **Cascade confirmed** | 1 (SFV forward reference) | 1 (Ch 1 content overlap) |
| **Cascade broken bridge** | 0 | 1 ($15 vs $1,500 in Ch 6) |
| **Overall maturity** | Design patterns without implementation | Decision framework with composition gaps |

### 7. Recommendations for book_chapter Gate Profile Adjustments

**Tier 1 adjustment:** Add a citation quality sub-gate for chapters with >10 citations. Once citation density is adequate, the audit should focus on: (a) citation context match (does the citation support the sentence it is attached to?), (b) content overlap with other chapters, (c) quantitative claim verification. These are higher-value findings than "add more citations."

**Practitioner stress test adjustment:** Tailor the persona to the chapter type. Domain workflow chapters (Ch 4) should test implementation scenarios. Decision/architecture chapters (Ch 5) should test decision scenarios. The persona should match the chapter's level of abstraction.

**Bloom gate adjustment:** For decision-making chapters, expect sustained Evaluate across the decision sections. Flag any decision section that drops below Evaluate as a significant gap. The Bloom gate's highest value on decision chapters is confirming that the chapter actually requires judgment, not just presenting options.

**Cascade adjustment:** Check for both forward references (terms used before defined) and backward overlaps (content re-presented from earlier chapters). Both are chapter-ordering issues with different resolution patterns.

**Visual gap:** The zero-figures finding has now appeared in both Ch 4 and Ch 5 audits. This is likely a book-wide pattern. Consider a standing visual audit across all chapters rather than discovering it chapter by chapter.

**Bridge promises:** Add bridge promise verification as a standard cascade check. Every chapter bridge makes a promise about the next chapter. Broken promises should be flagged.

---

## Pipeline Performance Notes

- Total time: single session, ~40 minutes operator time (longer than Ch 4 due to more cascade checking material)
- The cascade checking step continues to be the highest-value step for cross-chapter consistency. The Ch 1 overlap and Ch 6 bridge promise would not have been found by any single-chapter lens.
- The synthesis clustering worked well: 8 clusters with clear convergence ordering, 5 unclustered low-severity items. The lenses produced overlapping findings with good convergence.
- For `book_chapter` type on a decision-making chapter, the practitioner stress test and Bloom gate are the highest-value gates. The visual gap check and cascade check are the highest-value secondary findings.
- The pipeline is producing calibrated results: signal quality improves with chapter maturity, and the audit adapts to the chapter's structural role in the book.
