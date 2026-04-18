# Design Note: Semantic Anchoring & Narrative Logic Passes for Content Pipelines

**Date:** 2026-04-04
**Status:** Design
**Relates to:** AD-020 (Iterative Content Review Pipeline), AD-019 (Content Audit), AD-014 (Agent Roles)
**Provenance:** Pattern extracted from Wu et al. (2026), "Towards a Medical AI Scientist" (arXiv:2603.28589v1). Their Manuscript Composer pipeline demonstrated two mechanisms absent from Seldon's current writing/review workflow. Patterns extracted and adapted here — the framework is not imported.

---

## 1. Context

Seldon's current writing pipeline has two phases:

1. **Drafting:** Sections are written independently (by CC or author), following conventions.md, using `{{result:...}}` references and glossary-controlled terminology.
2. **Review:** AD-020's multi-lens pipeline (correctness → stress test → depth check → secondary sweep → synthesis → cascade) evaluates the draft and produces structured findings for the author.

Two gaps exist between these phases:

**Gap A (Revision Awareness):** When revising Chapter N, the writer has no structured awareness of what other chapters establish, assume, or depend on. Cross-chapter consistency is checked *post hoc* by AD-020's cascade checker, but only for explicit cross-references. Implicit dependencies — where Chapter 11 assumes familiarity with a concept defined in Chapter 7, without explicitly citing it — are invisible to the cascade checker. Revising a definition in Chapter 7 can silently break Chapter 11's coherence.

In projects where all content already exists in draft form (the typical case for iterative revision of a book or long paper), the problem is bidirectional: you need to know both what prior chapters established *and* what downstream chapters assume about the chapter you're revising. The blast radius of a revision is the set of chapters that depend on the content being changed.

**Gap B (Post-Draft, Pre-Review):** AD-020's gates check correctness, comprehensiveness, cognitive depth, and narrative structure. They do not check whether the prose *argues* rather than merely *describes*. LLM-generated drafts systematically over-index on procedural description ("we did X, then Y, then Z") and under-index on argumentative structure ("X reveals Y, which motivates Z"). This is a distinct dimension from what any current gate evaluates.

---

## 2. Pattern A: Semantic Anchoring as Dependency Map

### What It Is

Every section/chapter in a project gets a structured semantic anchor — a compressed summary that captures its core argument, key claims, terminology, and cross-references. The full set of anchors forms a **bidirectional dependency map** for the document.

Each anchor contains:

- The section's core argument (1-2 sentences — thesis, not summary)
- Key claims established (falsifiable assertions, not topic labels)
- Terminology introduced or refined (cross-checked against glossary)
- Forward references (explicit promises and implicit setups for later sections)
- Backward references (what this section assumes from prior sections)
- **Depends-on-me** (which downstream sections will break if this section changes)

The `depends_on_me` field is the critical addition beyond the original Medical AI Scientist pattern. Their implementation assumes linear drafting (Section N only needs Sections 1..N-1). Real revision workflows are non-linear: all content exists, and any section can be revised at any time. The dependency map must be bidirectional.

### Why It Works

The Medical AI Scientist paper's Manuscript Composer retains "concise summaries of previously generated sections as semantic anchors during subsequent drafting." Adapted to the revision context, this prevents three failure modes:

1. **Silent cascades:** Revising Chapter 5's definition of X breaks Chapter 8, which assumed X. Without the dependency map, the author doesn't know Chapter 8 depends on that definition until AD-020 catches it (or doesn't — if the dependency is implicit, the cascade checker won't see it).
2. **Redundancy:** Chapter 6 re-explains a concept Chapter 3 introduced. Without anchors, the reviser doesn't know what's been covered.
3. **Broken promises:** Chapter 4 says "we will return to this in the context of validation." Chapter 10 never does. The anchor map's forward reference tracking makes undelivered promises visible.

### Dependency Strength Classification

Not all dependencies cascade equally. The `depends_on_me` field classifies each dependency:

- **Strong:** The downstream chapter directly references a specific claim or definition. Revision *will* cascade.
- **Moderate:** The downstream chapter builds on a concept introduced here without explicitly referencing it. Revision *might* cascade — needs review.
- **Weak:** Thematic overlap. Revision is unlikely to cascade but should be checked.

This classification drives the revision workflow: strong dependencies get mandatory cascade checks, moderate get author review, weak get noted.

### How It Integrates

**Generation:** Two-pass process. Pass 1 generates per-section anchors from content (plus AD-020 audit artifacts where available). Pass 2 cross-links the dependency graph by inverting all backward references into `depends_on_me` entries.

**Usage during AD-020 runs:** The anchor map is read as context before each pipeline run. The cascade checker uses it to identify implicit dependencies that aren't visible from explicit cross-references alone.

**Usage during revision:** When a revision CC task modifies Chapter N, the `depends_on_me` list is the blast radius checklist. Strong dependents get cascade checks. The author reviews moderate dependents.

**Maintenance:** After each chapter revision, the affected chapter's anchor is regenerated. If claims or terminology changed, Pass 2 re-runs on affected dependents to update `depends_on_me` entries. This is a small incremental cost — not a full rebuild.

### Anchor Schema

```yaml
semantic_anchor:
  chapter: "chapter-07"
  title: "Checkpoints, Failures, and Recovery"
  date_generated: "2026-04-04"
  generated_from: "AD-020 calibration run 005"
  ad020_completed: true

  core_argument: >
    The same defensive engineering patterns that protect production pipelines
    (config-driven design, progressive testing, checkpoint/recovery) also protect
    the development process from AI coding assistant stochasticity.

  claims_established:
    - Error classification taxonomy: transient, permanent, data-dependent
    - Config-driven architecture eliminates hardcoded parameters as failure source
    - Progressive test infrastructure scales verification with pipeline complexity
    - Transaction-safe checkpoint writes prevent partial-state corruption
    - The recursive stochasticity problem: dev tools are also stochastic

  terminology_introduced:
    - term: "recursive stochasticity"
      definition: "the development tools themselves are non-deterministic"
      in_glossary: true
    - term: "progressive test infrastructure"
      definition: "testing that scales with pipeline complexity"
      in_glossary: false

  forward_references:
    - target: "chapter-09"
      topic: "drift detection and state management"
      type: "explicit"  # promised via thought experiment callback
    - target: "chapter-11"
      topic: "recursive stochasticity argument continues"
      type: "implicit"

  backward_references:
    - source: "chapter-06"
      topic: "parallel batch architecture, exponential backoff, checkpoint requirement"
      type: "explicit"

  depends_on_me:
    - dependent: "chapter-09"
      topic: "thought experiment callback — Ch 9 answers Ch 7's provocation"
      strength: "strong"
    - dependent: "chapter-11"
      topic: "recursive stochasticity framing extends to dev toolchain"
      strength: "moderate"

  open_threads:
    - "Mid-run config changes — acknowledged but deferred"
    - "Runtime estimation — explicitly Ch 6's domain"
    - "Corrupted checkpoint recovery — paragraph added but edge cases remain"
```

### Cost-Benefit

**Cost:** ~200-300 tokens per chapter anchor. For 14 chapters, ~4K tokens of context added to CC tasks. Trivial relative to chapter text. Two-pass generation is a one-time cost; maintenance is incremental.

**Benefit:** Revision blast radius becomes visible before making changes. Implicit dependencies become explicit. Forward reference tracking is structural rather than forensic. The anchor map serves as a book skeleton that any new session can read to understand document structure without reading full chapter text.

---

## 3. Pattern B: Narrative Logic Rewrite Assessment

### What It Is

A post-draft, pre-review assessment pass that evaluates whether the prose *argues* or merely *describes*. Distinct from all existing AD-020 gates:

| Existing Gate | What It Checks | What It Misses |
|---|---|---|
| Correctness (Tier 1) | Facts, citations, terminology | Whether correct facts form a coherent argument |
| Stress Test (Tier 2a) | Practitioner utility | Whether utility is communicated persuasively |
| Depth Check (Tier 2b) | Cognitive scaffolding (Bloom) | Whether scaffolding is expressed through argument or through procedure |
| Secondary Sweep (Tier 3) | Narrative arc, clarity, visuals, motivation | Checks narrative *structure* but not argument *logic* within paragraphs |

### The Specific Problem

LLM-drafted prose (and human prose written under time pressure) exhibits a systematic failure mode: **procedural description masquerading as argument.** Symptoms:

- Paragraphs that walk through steps ("First... Then... Next... Finally...") without stating why each step matters
- Sections that describe *what* a technique does without arguing *why* it's the right choice over alternatives
- Transitions that are temporal ("After establishing X, we turn to Y") rather than logical ("X creates a new problem: Y")
- Claims that are stated but not earned — the evidence is present somewhere in the chapter but the paragraph doesn't connect to it

### What the Pass Would Evaluate

**Per-paragraph assessment:**

1. **Argument type classification:** Is this paragraph (a) making a claim and supporting it, (b) describing a procedure, (c) providing context/background, (d) transitioning between ideas? All four are valid — the problem is when (b) appears where (a) should be.

2. **Causal chain presence:** Does the paragraph contain at least one causal or logical connective that earns the next sentence? ("because," "therefore," "this implies," "which means," "the consequence is") versus purely sequential connectives ("then," "next," "additionally," "also").

3. **"So what?" test:** If the paragraph were deleted, would the chapter's argument lose a load-bearing claim? Or would it just lose a description that could be reconstructed from context? Load-bearing paragraphs must earn their claims. Descriptive paragraphs should be flagged if they occupy positions where argumentative paragraphs are expected.

4. **Evidence-claim coupling:** When a claim is made, is the supporting evidence in the same paragraph or within one paragraph? Or is the evidence three sections away, requiring the reader to hold it in working memory?

**Per-section assessment:**

5. **Section-level argument arc:** Does the section progress from setup → tension → resolution? Or does it read as a list of related facts?

6. **Procedural-to-argumentative ratio:** What fraction of paragraphs are descriptive/procedural vs. argumentative? Engineering chapters will legitimately have higher procedural ratios, but even "how-to" sections should argue *why* each design choice is correct.

### What the Pass Would NOT Do

- **Not edit prose.** Findings only. (Grammarly failure mode, AD-020 §1.)
- **Not replace AD-020 gates.** This is a different dimension. A chapter can pass all AD-020 gates (correct, comprehensive, properly scaffolded, narratively structured) and still fail the narrative logic pass (because it describes rather than argues).
- **Not enforce a single style.** Some sections are legitimately procedural (setup instructions, configuration examples). The pass classifies; the author decides whether the classification reveals a problem.

### Integration Point

**Where in the pipeline:** Between drafting and AD-020 review. The narrative logic pass would run on the draft *before* the full AD-020 pipeline. Rationale: if the prose is fundamentally procedural when it should be argumentative, AD-020's stress test and depth check will flag symptoms (low Bloom depth, practitioner can't use it for judgment) but won't diagnose the root cause. Running narrative logic first gives the author the diagnosis before the symptoms.

**Alternative:** Add as a Tier 2c gate within AD-020. This has the advantage of including findings in the synthesis document's topic clustering. The disadvantage is that it adds another pass to an already multi-pass pipeline.

**Recommendation:** Defer decision until Pattern A is implemented and dogfooded. The experience of revising with semantic anchors may change what Pattern B needs to check — if anchoring reduces procedural drift, Pattern B's scope narrows. Design Pattern B after observing Pattern A's effects.

### Additional Checks to Consider (Parking Lot for Pattern B)

These are candidate assessments that could be bundled into Pattern B or split into separate passes. Not committed — captured for future design:

- **Analogy quality:** Are analogies precise (illuminate the specific mechanism) or decorative (sound good but don't transfer)?
- **Assumption surfacing:** Where does the prose assume knowledge that the stated audience may not have? Different from jargon audit — this is about unstated logical prerequisites.
- **Counterargument anticipation:** Does the prose address obvious objections, or does it only present the positive case? Adversarial reviewer simulation.
- **Specificity gradient:** Does the prose move from general to specific (good) or stay at one level of abstraction throughout (bad)?
- **Example-to-principle ratio:** Are principles always illustrated with concrete examples? Are examples always generalized back to principles?

---

## 4. Implementation Sequence

1. **Pattern A — Semantic Anchoring (implement now)**
   - Generate bidirectional anchors for all 14 chapters (two-pass: anchors then cross-links)
   - Produce anchor map with dependency summary and blast radius analysis
   - Consistency check across full book (terminology conflicts, orphan references, unstated dependencies)
   - Add anchor map as context input to all future CC tasks (AD-020 runs, revisions, drafting)
   - Dogfood on Ch 8 AD-020 run
   - Post-revision anchor maintenance as standard step in revision CC tasks

2. **Pattern B — Narrative Logic Pass (design, defer implementation)**
   - Observe Pattern A's effects on revision quality
   - Refine Pattern B's scope based on what Pattern A doesn't catch
   - Decide integration point (pre-AD-020 vs. Tier 2c within AD-020)
   - Implement after Pattern A has been used on 2-3 chapters

---

## 5. Provenance

The Medical AI Scientist paper (Wu et al., 2026) uses both patterns in its Manuscript Composer:

- **Semantic anchoring:** "concise summaries of previously generated sections are retained and reused as semantic anchors during subsequent drafting" — prevents cross-section drift during generation.
- **Scientific Narrative Enhancer:** "counter[s] the tendency of AI-generated text to overemphasize procedural detail, refining the manuscript to improve clarity and the scientific storyline" — a post-generation rewrite pass targeting the procedural-to-argumentative failure mode.

Their implementation assumes linear drafting and uses both patterns as automated rewrite agents. Seldon's adaptation differs in two ways: (1) anchoring is bidirectional (dependency map, not linear accumulation) to support non-linear revision workflows, and (2) both patterns produce *findings*, not *edits*. The author remains in the loop per AD-020 §1 (Grammarly failure mode constraint). The insight is extracted; the implementation pattern is Seldon-native.

---

*This design note will be registered as a graph artifact with `informs` edges to AD-020 and AD-014.*
