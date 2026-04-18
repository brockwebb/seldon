# AD-020: Iterative Content Review Pipeline — Multi-Lens Comprehensiveness Gates

**Date:** 2026-04-02
**Status:** Design
**Depends on:** AD-019 (content audit pipeline), AD-014 (agent roles)
**Motivated by:** Chapter 3 LI post test revealed that correctness auditing (AD-019) misses framing gaps. The audit verified all 52 assertions but could not detect that the System Owner perspective — supportability, maintainability, opportunity cost, replaceability, predictability-as-feature — was entirely absent. The gap was only visible when a practitioner asked "can I answer a real question from this material?"

---

## 1. Problem Statement

AD-019 answers: "Is what's here correct and properly supported?"

It does not answer:
- "What should be here that isn't?" (comprehensiveness)
- "Does the reader walk away with engineering judgment, or just a technical routing table?" (cognitive depth)
- "Can a practitioner answer real questions using only this material?" (utility)
- "Is the argument structure effective, or does it bury insights where 90% of readers won't connect the dots?" (communication effectiveness)

These are different evaluation dimensions that require different lenses. Each lens produces findings. The author resolves them. No lens auto-edits.

### The Grammarly Failure Mode

Iterative LLM editing loops converge on mush. Each individual suggestion is locally "correct" — smoother phrasing, clearer sentence, better transition. The aggregate effect destroys voice, flattens argument structure, and produces homogenized prose. This is the greedy algorithm problem: locally optimal moves, globally terrible outcomes.

**Design constraint:** Every gate in this pipeline REPORTS findings. None of them EDITS. The author decides what to change. The stop condition is author satisfaction, not gate silence. Gates will never be silent — there's always another suggestion. The pipeline must make this boundary structural, not aspirational.

---

## 2. Pipeline Architecture

### 2.1 Three Tiers

The pipeline has three tiers, each producing structured findings. Tiers run sequentially because later tiers benefit from earlier findings (Tier 2 is more useful after Tier 1 has confirmed the facts are right).

**Tier 1: Correctness Audit (AD-019)**
Already built. Checks claims, citations, terminology, cross-section consistency. Mechanical verification. Produces Issues and ResearchTasks.

**Tier 2: Primary Reader Gates**
High-value evaluation lenses that each assess a distinct dimension of content quality. These run as separate passes, each producing structured findings. Two primary gates:

| Gate | What It Checks | Based On |
|------|---------------|----------|
| **Practitioner Stress Test** | Can a working practitioner answer real questions using only this material? What's missing that should be here? | Feynman: if you can't use it, you don't understand it. Keller ARCS: relevance is the motivational component most often missing in technical writing. |
| **Cognitive Depth Check** | Does the chapter scaffold from comprehension → application → evaluation → judgment? Or does it stop at "understand" and never ask the reader to judge tradeoffs? | Bloom's taxonomy. Sweller's cognitive load theory. Kahneman System 1/2 (engineering heuristics need to become intuitive, not just explained). |

**Tier 3: Secondary Lens Sweep**
A consolidated pass that applies multiple secondary perspectives and synthesizes them into a single findings report. Not separate agents — one blended pass that names which lens surfaced each finding. Secondary lenses include:

| Lens | Focus |
|------|-------|
| **Narrative structure** | Does the chapter have a story arc? Does each section earn its place? Is there a hook, tension, resolution? (Gladwell's method: concrete story → surprising insight → reframe) |
| **Clarity / jargon audit** | Where does the prose require unstated domain knowledge? Where would a motivated non-expert get lost? |
| **Visual/spatial gaps** | Where would a diagram, table, or figure communicate faster than prose? (Mayer's multimedia learning, Paivio's dual coding) |
| **Motivational framing** | Does the reader understand why they should care about each section? (Keller ARCS: Attention, Relevance, Confidence, Satisfaction) |

The secondary sweep is one agent, one pass, blended output. Not four separate loops. This prevents the "15 scattered items from 4 different reviewers" problem.

### 2.2 Output: The Synthesis Document

This is the key design decision. All findings from all tiers converge into a single synthesis document that:

1. **Groups findings by topic cluster, not by gate.** If the Practitioner Stress Test, the Cognitive Depth Check, and the Narrative Structure lens all flag the same gap (e.g., "System Owner perspective is absent"), they appear together under one cluster heading, not scattered across three reports.

2. **Names which lens surfaced each finding.** Within a cluster, each finding is tagged with its source: `[practitioner]`, `[bloom]`, `[narrative]`, `[clarity]`, `[visual]`, `[motivation]`. This lets the author see convergence — if three lenses flag the same gap, it's more important than something only one lens noticed.

3. **Pre-synthesizes related findings into actionable items.** Instead of "here are 15 things," the synthesis produces 4-6 clusters, each with a heading, the converging evidence, and a suggested action scope (not a suggested edit — a scope like "add a section on X" or "reframe paragraph Y as a tradeoff").

4. **Orders clusters by impact.** Clusters where multiple lenses converge rank higher. Single-lens findings rank lower. Author works top-down.

5. **Is designed for serial processing.** Each cluster is self-contained. The author can address cluster 1, then cluster 2, without needing to hold the whole document in working memory. No scrolling back to find the next item.

### 2.3 Output Format

```yaml
review_synthesis:
  file: "[path to reviewed chapter]"
  date: "[ISO date]"
  document_type: "[academic_paper | book_chapter | blog_post | ...]"
  tier_1_reference: "[path to AD-019 audit YAML, if exists]"

  clusters:
    - id: 1
      title: "[descriptive heading — e.g., 'System Owner Perspective Missing']"
      convergence: 3  # number of lenses that flagged this
      lenses: ["practitioner", "bloom", "narrative"]
      
      findings:
        - lens: "practitioner"
          finding: "Practitioner cannot answer 'can my team support this in 2 years?' from the material. Supportability, maintainability, opportunity cost are absent as named tradeoffs."
        - lens: "bloom"
          finding: "Chapter stays at Bloom's 'apply' level. No scaffolding to 'evaluate' — reader learns routing rules but is never asked to judge organizational tradeoffs."
        - lens: "narrative"
          finding: "The chapter has a Pipeline Builder arc but no System Owner arc. The reader who builds the pipeline has no framework for the reader who inherits it."
      
      suggested_scope: "Add a section (~300-400 words) between Fine-Tuning Cost Trap and Schema Inference that names the System Owner perspective as a group: supportability, maintainability, opportunity cost, replaceability, predictability-as-feature."
      
      affected_sections:
        - "[## The Fine-Tuning Cost Trap — contains fragments]"
        - "[## Where Traditional Methods Still Win — contains predictability argument but not framed as design virtue]"

    - id: 2
      title: "[next cluster]"
      convergence: 2
      # ...

  unclustered:
    # Single-lens findings that didn't group with anything else
    - lens: "visual"
      finding: "The tradeoff space has no visual representation. A 2x2 or routing diagram would reduce cognitive load."
      suggested_scope: "Consider a figure mapping tool selection tradeoffs."
```

---

## 3. Gate Specifications

### 3.1 Practitioner Stress Test

**Input:** Chapter file + chapter's stated scope/topic.

**Process:**
1. Given the chapter topic, generate 8-10 questions a working practitioner would ask. These should be "such as" questions — "I'm designing a system, what tradeoffs should I consider such as...?" Not trivia. Not comprehension checks. Design decision questions.
2. For each question, attempt to answer it using ONLY the chapter material.
3. Score each: fully answerable (the chapter directly addresses this) / partially answerable (fragments exist but aren't synthesized) / not answerable (the chapter doesn't cover this).
4. For partially and not answerable: describe the gap.

**Critical constraint:** The quality of this gate depends on the quality of the generated questions. The prompt must steer toward engineering judgment questions, not factual recall. Bad example: "What is NAICS code 238220?" Good example: "If my team can't support a fine-tuned model long-term, what are my alternatives?"

**Enhancement — third-party model:** This gate benefits from using a model that did NOT participate in drafting the chapter. A fresh model has no memory of what was intended — only what's on the page. Use Gemini or GPT for this gate if possible. The drafting model's blind spots are the chapter's blind spots.

### 3.2 Cognitive Depth Check (Bloom)

**Input:** Chapter file.

**Process:**
1. For each major section (## level), classify the highest Bloom level the reader is asked to reach:
   - **Remember:** Can recall facts presented
   - **Understand:** Can explain concepts in own words
   - **Apply:** Can use patterns in new situations (routing table, template application)
   - **Analyze:** Can distinguish components, identify relationships
   - **Evaluate:** Can judge, compare, recommend based on criteria
   - **Create:** Can design new solutions using the principles

2. Flag sections that stop at Apply or below when the content naturally supports Evaluate or Create.
3. Specifically check: does the chapter include opportunities for the reader to practice judgment? (Reflection prompts, thought experiments, design tradeoff questions)
4. Check scaffolding: does the chapter build from lower to higher cognitive levels, or does it jump unpredictably?

### 3.3 Secondary Lens Sweep (Blended)

**Input:** Chapter file + Tier 2 findings (so it doesn't repeat what's already been flagged).

**Process:** Single pass through the chapter applying all secondary lenses simultaneously. For each finding, tag with the lens that surfaced it. If a finding is relevant to multiple lenses, tag all.

The blended approach prevents the "four separate reports with overlapping findings" problem. One agent, one pass, one report.

---

## 4. Synthesis Engine

The synthesis step is not optional — it's the core value of the pipeline. Raw findings from multiple gates are unusable at volume. The synthesis:

1. **Clusters by topic.** Uses the actual content of findings to group them, not the lens that produced them. Two findings about "missing visual representation" from different lenses go in the same cluster.

2. **Counts convergence.** More lenses → higher priority. This is a natural quality signal: if only the narrative lens flags something, it might be stylistic. If the practitioner test, Bloom check, AND narrative lens all flag the same gap, it's structural.

3. **Writes actionable scope, not edits.** "Add a section on X" not "Change paragraph 3 to say Y." The author writes the prose. The pipeline identifies the gaps.

4. **Orders for serial processing.** Highest convergence first. Each cluster is self-contained. The author can close one, open the next, without context-switching.

### 4.1 The "Working One Piece at a Time" Requirement

The synthesis document must be designed so the author can:
- Read cluster 1, address it, mark it done
- Read cluster 2, address it, mark it done
- Stop at any point and resume later without losing state
- Never need to scroll back up to find the next item

This means each cluster must contain everything needed to act on it: the findings, which sections are affected, the suggested scope, and the convergence evidence. No cross-references to other clusters unless they have a genuine dependency (rare — most content gaps are independent).

If clusters DO have dependencies (e.g., "add System Owner section" must happen before "add reflection prompts to System Owner section"), the dependency is stated explicitly and the dependent cluster references the upstream cluster by ID.

---

## 5. Relationship to AD-019

AD-019 (correctness audit) is Tier 1 of this pipeline. AD-020 adds Tiers 2 and 3.

The pipelines share:
- Output format philosophy (structured YAML, not prose reports)
- Agent team pattern (lead + ephemeral teammates for cascade/parallel work)
- Findings-not-edits principle
- Synthesis into actionable clusters

AD-019's cascade checking pattern (spawn lightweight teammates to verify cross-section impacts) applies here too: if the Practitioner Stress Test identifies a gap that likely affects other chapters, spawn cascade checkers for those chapters.

---

## 6. Implementation Approach

### Phase 1: Manual with synthesis template (immediate)

Run the gates as separate prompts in a CC session or third-party model. Use the synthesis YAML format to manually combine findings. Validate that the clustering and convergence scoring actually helps the author work serially.

The LI post test that surfaced Chapter 3's gaps was already an informal Phase 1 run.

### Phase 2: Subagent definitions + CC task template

Write subagent definitions for each gate (practitioner-stress-test, bloom-check, secondary-sweep). Write a CC task template that runs all three and produces the synthesis document. Similar to the AD-019 agent team pattern.

### Phase 3: `seldon review` CLI command

`seldon review <chapter>` runs the full pipeline: Tier 1 (AD-019 audit) → Tier 2 (primary gates) → Tier 3 (secondary sweep) → synthesis. Outputs the synthesis document to `audits/<chapter>_review_synthesis.yaml`.

### Phase 4: Third-party model integration

Route the Practitioner Stress Test to a different model (Gemini, GPT) for fresh-eyes evaluation. Requires API key configuration but adds genuine value by removing the drafting model's blind spots.

---

## 7. Document Type Configuration

The pipeline is structurally identical across document types. What changes is which gates fire, at what intensity, and how the stress test is framed. Document type is declared in the project config and drives gate calibration.

### 7.1 Document Type Taxonomy

| Type | Key | Description |
|------|-----|-------------|
| Academic paper | `academic_paper` | Peer-reviewed or preprint. Formal argument structure. Citations mandatory. |
| Book chapter | `book_chapter` | Part of a longer work. Pedagogical structure. Reader needs to walk away with usable knowledge. |
| Blog post | `blog_post` | Standalone. Engagement-driven. Lower citation bar, higher narrative bar. |
| Medium article | `medium_article` | Long-form online. Blend of practitioner and general audience. |
| Course handout | `course_handout` | Instructional. Reader must be able to do the exercise after reading. |
| Policy brief | `policy_brief` | Decision-maker audience. Actionable conclusions. Clarity dominant. |

### 7.2 Gate Calibration by Document Type

| Gate | `academic_paper` | `book_chapter` | `blog_post` | `course_handout` | `policy_brief` |
|------|-----------------|----------------|-------------|-------------------|----------------|
| **Tier 1: Correctness** | Full — citations mandatory for every factual claim | Full | Light — higher common knowledge threshold | Moderate | Light citations, heavy accuracy |
| **Tier 2: Stress Test** | Reviewer: "What would Reviewer 2 ask?" | Practitioner: "Can I use this?" | Reader: "Does this change how I think?" | Student: "Can I do the exercise?" | Decision-maker: "Can I act on this?" |
| **Tier 2: Depth Check** | Argument completeness: claim→evidence chains, logical gaps, unstated assumptions | Bloom taxonomy: does reader reach evaluate/create? | Skip | Bloom is primary — scaffolding IS the point | Skip |
| **Tier 3: Narrative** | Argument arc (not story arc) | Story arc, hook, tension | Dominant concern | Light | Light |
| **Tier 3: Clarity** | Jargon audit against stated audience | Yes | Yes | Dominant concern | Dominant concern |
| **Tier 3: Visual gaps** | Figures, tables, diagrams | Yes | Moderate | Critical | Light |
| **Tier 3: Motivational framing** | Light — motivation is implicit in research contribution | Yes — Keller ARCS | Engagement dominant | Yes — relevance to learning objectives | Yes — relevance to decision |

### 7.3 Stress Test Reframing by Document Type

The stress test persona changes with document type. The core mechanism is identical — "generate questions, try to answer from material only, report gaps" — but the question framing determines what gets caught.

| Document Type | Stress Test Persona | Example Question |
|---|---|---|
| `academic_paper` | Reviewer 2 at the target venue | "What alternative explanations weren't considered?" |
| `book_chapter` | Working practitioner | "Can I use this to make a design decision tomorrow?" |
| `blog_post` | Interested generalist | "Did I learn something I can explain to someone else?" |
| `course_handout` | Student doing the homework | "Can I complete the exercise with only this handout?" |
| `policy_brief` | Decision-maker with 10 minutes | "Is there enough here to approve or reject the proposal?" |

### 7.4 Depth Check Adaptation by Document Type

The Bloom taxonomy check applies differently — or not at all — depending on document type:

- **`academic_paper`**: Replace Bloom with **argument completeness check**. Every claim needs evidence. Every evidence item needs to support a claim. Logical gaps between sections are flagged. Unstated assumptions are flagged. The reader isn't being scaffolded through cognitive levels — they're evaluating an argument.
- **`book_chapter`**: Full Bloom. The chapter IS scaffolding. Does the reader reach Evaluate/Create, or does the chapter stop at Apply?
- **`blog_post`**: Skip. Blog posts don't scaffold.
- **`course_handout`**: Bloom is primary. The entire document's purpose is to move the student up the taxonomy.
- **`policy_brief`**: Skip. The reader isn't learning — they're deciding.

### 7.5 Configuration

In `paper_qc_config.yaml` or `seldon.yaml`:

```yaml
review:
  document_type: academic_paper  # drives gate calibration
  audience: "GP/evolutionary computation researchers, AI safety researchers"
  # Optional overrides:
  # skip_gates: [bloom]
  # stress_test_persona: "Reviewer 2 at GECCO"
```

The document type selects a default gate profile. The author can override individual gates (skip, intensify, or reframe) without changing the pipeline structure.

---

## 8. What This Does NOT Do

- **Does not edit prose.** Findings only. The author writes.
- **Does not replace the author's judgment on argument structure.** It surfaces gaps. The author decides which gaps matter and how to fill them.
- **Does not guarantee the "right" practitioner questions.** Question quality depends on the model's domain understanding. The gate catches more gaps than no gate, but fewer than a real domain expert (the author).
- **Does not run indefinitely.** The stop condition is author satisfaction. Gates will always find more to flag. The pipeline does not chase perfection.
- **Does not replace human beta readers.** A real practitioner reading a draft catches things no LLM gate will. This pipeline is a complement, not a replacement.

---

## 9. Open Questions

1. **Synthesis agent: same model or coordinator pattern?** The synthesis step could be a standalone agent that reads all gate outputs and clusters them. Or the lead session could do it. Standalone is cleaner (fresh context, no accumulated gate noise). Coordinator pattern is simpler (one session).

2. **Third-party model routing.** Calling Gemini/GPT from within a CC session is possible via API but adds complexity. Alternative: export the chapter + gate prompt as a self-contained document, paste into the other model manually, paste results back. Phase 1 pragmatism.

3. **How many clusters is too many?** If the synthesis produces 12 clusters, that's still overwhelming. Should there be a cap (e.g., top 6 by convergence) with the rest filed as "additional findings" appendix?

4. **Interaction with the book's pedagogical pattern.** The ai-workflow-design book has a defined chapter pattern (opening hook, core content, distributed reflection prompts, thought experiment, chapter bridge). Should the Bloom check be calibrated against this pattern specifically? Probably yes — the pattern implies specific cognitive levels at specific structural positions.

5. **Calibration data.** The Chapter 3 LI post test is the first calibration point. The leibniz-pi paper is the first `academic_paper` calibration target. Running the pipeline on both document types and comparing gate output to author-identified gaps will reveal whether the gates are useful or just noisy, and whether document type calibration makes a meaningful difference.

6. **Document type extensibility.** The taxonomy in §7.1 is not exhaustive. Conference poster, grant proposal, technical report, API documentation, README — each has a different gate profile. Add types as needed. The structure supports arbitrary extension; the calibration tables in §7.2 just need new columns.

---

## 10. References

- AD-019: Agentic Content Audit Pipeline
- AD-014: Agent Roles as Graph Artifacts
- Bloom, B.S. (1956). Taxonomy of Educational Objectives
- Sweller, J. (1988). Cognitive load during problem solving
- Mayer, R.E. (2009). Multimedia Learning
- Keller, J.M. (1987). ARCS Model of Motivational Design
- Kahneman, D. (2011). Thinking, Fast and Slow
- Chapter 3 LI post test: Claude Desktop session 2026-04-02 (this conversation)
- Grammarly convergence failure: Author's direct experience with iterative acceptance

---

*The pipeline catches what's wrong with what's there (AD-019) and what's missing from what should be there (AD-020). Neither replaces the author. Both make the author's judgment more efficient by doing the diagnostic work that humans are bad at (exhaustive checking) so the human can focus on what humans are good at (deciding what matters).*
