# Design Note: AD-020 Feynman Pedagogy Gate Gap

**Date:** 2026-04-03
**Related:** AD-020 (Iterative Content Review Pipeline), AD-020 Calibration 002 (Ch 4)
**Status:** Open question — not a decision yet

---

## The Gap

During the Ch 4 review, the author identified a class of pedagogical failure that the current AD-020 pipeline detects imprecisely:

**"The chapter talks about cool things and why they're cool, but where are the design philosophies? We're just telling people about stuff instead of helping them develop the right principles."**

The Bloom gate flagged Ch 4's synthesis section as stopping at Apply. That's the correct symptom. But the Bloom gate doesn't distinguish between:

1. **Acceptable Apply:** A reference table, a checklist, a summary of patterns. These are *supposed* to be at Apply. The reader has already done the evaluative work; the summary consolidates it.

2. **Failed Apply:** A section that *should* scaffold to Evaluate/Create but instead just presents information. The reader learns *what to think* but not *how to think*. They get knowledge but not judgment.

The Feynman teaching method — the stated pedagogical foundation for the book — specifically targets (2). The technique is: can you explain it simply? Can the reader derive the insight, not just receive it? Do the examples develop reasoning skills, or just illustrate facts?

## What the Current Gates Catch

| Gate | What It Detects | What It Misses |
|------|----------------|----------------|
| Bloom (Tier 2b) | Highest cognitive level per section. Sections that stop at Apply when content supports Evaluate. | *Why* the section stops at Apply — is it structural (checklist at end of chapter) or pedagogical (lectures instead of teaches)? |
| Practitioner Stress Test (Tier 2a) | Whether the reader can answer design questions from the material. | Whether the reader can *generate* the right questions themselves. "Can I use this?" is not the same as "Can I reason about this domain?" |
| Narrative (Tier 3) | Story arc, hook, tension. | Whether the narrative develops the reader's judgment or just tells them a story. A well-structured narrative can still be a "book report." |
| Motivation (Tier 3) | Does the reader know why they should care? (Keller ARCS) | Does the reader know how to *decide* what to care about in a new situation? |

## Possible Responses

### Option A: Add a Feynman Pedagogy Gate (Tier 2c)

A dedicated gate that asks: "Does this chapter develop the reader's ability to reason independently about the domain, or does it present conclusions for the reader to absorb?"

Evaluation criteria:
- Does each section teach a *transferable principle* or just describe a *specific case*?
- Could the reader apply the chapter's reasoning to a situation the chapter doesn't cover?
- Are the reflection prompts genuine reasoning exercises or comprehension checks?
- Does the chapter develop heuristics and evaluation frameworks, or just present patterns to follow?

Risk: Overlap with Bloom and practitioner stress test. Another gate adds token cost and potential noise.

### Option B: Calibrate the Existing Bloom Gate

Add Feynman-specific criteria to the Bloom check for `book_chapter` document type:

- When a section scores at Apply: is it a consolidation section (acceptable) or a teaching section (flag as pedagogical gap)?
- Check whether reflection prompts ask "how would you evaluate?" vs "what would happen?"
- Check whether examples develop transferable reasoning vs illustrate specific cases

Risk: Makes the Bloom gate more complex. May be harder to calibrate cleanly.

### Option C: Add a Feynman Criterion to the Practitioner Stress Test

Currently the stress test asks: "Can the reader answer real questions using only this material?"

Add: "Can the reader *generate* the right questions to ask about a new extraction/classification/wrangling problem they haven't seen before?"

This tests whether the chapter develops reasoning ability, not just knowledge transfer. If the reader can only answer questions the chapter explicitly addresses, they learned *what* but not *how*.

Risk: Changes the stress test's scope. May make it harder to score consistently.

### Option D: Do Nothing — Author Catches This

The author caught this gap in Ch 4 without a gate. The pipeline surfaced the symptoms (Bloom non-monotonicity, implementation gap, narrative structure). The author's domain expertise identified the root cause. Maybe this class of problem is inherently an author judgment call that a gate can't automate well.

Risk: If the author doesn't review every chapter with this lens, the gap persists in chapters they skim. The pipeline's value is catching what the author misses on a tired read.

## Recommendation

No recommendation yet. Run the existing pipeline on 2-3 more chapters. Check whether the Bloom gate + practitioner stress test combination consistently surfaces "what-to-think vs how-to-think" gaps, or whether some chapters have this problem and the pipeline misses it. If it misses it, Option B (calibrate Bloom) is the lightest-weight fix. Option C (stress test enhancement) has the most upside if the question-generation test works in practice.

Defer until calibration runs 003-005 provide more data.
