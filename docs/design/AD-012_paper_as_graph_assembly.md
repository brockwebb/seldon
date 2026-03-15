# AD-012: Paper-as-Graph Assembly with Claim-Level Tracking and Tiered QC

**Date:** 2026-03-15
**Status:** Design — Extends AD-011, supersedes paper_authoring_convention.md
**Depends on:** AD-011 (reference resolution), AD-006 (Result registry), AD-009 (database-as-context)
**Context:** Three iterations of manual paper-writing (pragmatics v1/v2/v3) characterized five failure modes. AD-011 solved number drift via reference resolution. This AD addresses the remaining four: context starvation, confabulation, priority inversion, and non-convergence.

---

## 1. Design Principle

**Human-in-the-loop at decision points, not approval gates.**

The system maximizes the proportion of human attention spent on judgment tasks (argument design, validity assessment, voice) versus mechanical tasks (fact-checking, convention compliance, contradiction detection).

Testable requirement: After deploying this system, measure what percentage of editing time is spent on argument/voice vs. janitorial corrections. Target: flip from ~20/80 to ~80/20.

---

## 2. The Three-Layer Representation

A paper exists at three simultaneous granularities in the graph. Agents operate at the layer appropriate to their task.

### Layer 0: Argument Skeleton (human-authored)

The thesis and its supporting logical structure. This is the paper's blueprint — what is being claimed and why, in what order.

```
Argument
  ├── Thesis: "Entropy-based fitness avoids wrong-limit attractors in symbolic regression"
  ├── Supporting Claim 1: "Standard GP fitness is exploitable at finite evaluation horizons"
  │     └── Evidence needed: wrong-limit attractor density results
  ├── Supporting Claim 2: "Information-theoretic fitness measures convergence quality"
  │     └── Evidence needed: entropy fitness results, bits-per-decade metric
  ├── Supporting Claim 3: "The evaluation horizon creates a fundamental trade-off"
  │     └── Evidence needed: scaling analysis, T-sensitivity results
  └── Implication: "Fitness function design is underexplored in SR literature"
        └── Evidence needed: literature gap analysis
```

This is authored by the scientist. It is the one artifact no agent produces. The argument skeleton IS the paper — everything else is machinery to render it as prose with evidence.

Node type: `ArgumentClaim`
Properties: `statement`, `role` (thesis | supporting | implication | methodological), `evidence_needed`, `sequence`
State machine: `proposed → accepted → supported → published`
  - `supported` = all required evidence links exist and are verified

### Layer 1: Claim Inventory (materialized view)

Every paragraph distilled to its core assertion(s) plus the evidence it cites. This is the compressed, machine-readable representation that agents use for cross-section awareness.

Each claim is a node:
```
Claim {
    claim_id, statement,        # "The entropy fitness discovered Leibniz in 1.0/5 seeds"
    claim_type,                 # finding | methodology | background | limitation | future_work
    paragraph_id,               # which paragraph contains this claim
    section_id,                 # which section (denormalized for fast lookup)
    supports_argument,          # link to ArgumentClaim this serves
    evidence_ids[]              # Result, Citation, or LabNotebookEntry IDs
}
```

The claim inventory is a **materialized view** — pre-computed from the prose, updated when prose changes, queryable without touching the full text. An agent writing Section 5 receives the claim inventory for Sections 1-4 (maybe 50-100 tokens per paragraph), not the full prose (500+ tokens per paragraph).

### Layer 2: Full Prose

The actual written text of each paragraph. Pulled only when:
- An agent is drafting or editing that specific paragraph
- A QC agent is checking sentence-level quality (conventions, banned words)
- A human is reviewing voice and style

The prose is a **projection** of the claim inventory + evidence + conventions. It is generated from structure, not the other way around.

---

## 3. Intra-Paper Edge Types

These are typed, directed relationships between claims/paragraphs that encode the paper's logical structure.

| Edge Type | From → To | Semantics | QC Implication |
|-----------|-----------|-----------|----------------|
| `ASSUMES` | Claim → Claim | This claim takes as given what the target establishes | Target must exist and be supported. Broken ASSUMES = structural defect. |
| `EXTENDS` | Claim → Claim | Builds on, deepens, or elaborates the target claim | Weaker dependency — removing target weakens but doesn't break. |
| `SUPPORTS` | Claim → ArgumentClaim | This claim provides evidence for an argument-level assertion | Every ArgumentClaim should have ≥1 SUPPORTS edge. Unsupported = gap. |
| `CONTRADICTS` | Claim → Claim | Asserts something incompatible with the target | Should NEVER exist in a valid paper. QC hard-fail if detected. |
| `REFINES` | Claim → Claim | Narrows, qualifies, or adds conditions to the target | Informational — helps QC check that refinements don't contradict. |
| `SEQUENCED_AFTER` | Paragraph → Paragraph | Reading order within a section | Structural — used for assembly, not validation. |
| `SERVES` | Section → ArgumentClaim | This section's role in the argument | Every section must serve at least one ArgumentClaim. Orphan sections = structural problem. |

### Human-Defined vs. Agent-Inferred Edges

- `ASSUMES` and `SUPPORTS`: **Human-defined preferred, agent-proposed acceptable.** These are the load-bearing logical connections. The human (scientist) knows what assumes what. An agent can propose them, but they should be reviewed.
- `EXTENDS`, `REFINES`: **Agent-inferred is fine.** Lower stakes — extraction from prose.
- `CONTRADICTS`: **Agent-detected, human-reviewed.** This is a QC finding, not an authoring action. If the agent finds one, it's flagged, not auto-fixed.
- `SEQUENCED_AFTER`, `SERVES`: **Structural, defined at scaffolding time.** Part of the outline.

---

## 4. Tiered QC System

Three tiers of constraint enforcement. Each tier has a different enforcement mode.

### Tier 1: Structural Integrity (Hard Constraints — Build Fails)

These are referential integrity checks. The paper does not build if any are violated.

| Check | Description | Enforcement |
|-------|-------------|-------------|
| SI-01: Unresolved references | `{{result:NAME:value}}` points to nonexistent artifact | Build aborts |
| SI-02: Stale references | Referenced Result/Figure in `stale` state | Build aborts |
| SI-03: Unverified references | Referenced Result in `proposed` state (not yet verified) | Build aborts |
| SI-04: Broken ASSUMES | Claim ASSUMES a target claim that doesn't exist or was deleted | Build aborts |
| SI-05: Missing evidence | ArgumentClaim in `accepted` state has zero SUPPORTS edges | Build warning → abort at `publish` |
| SI-06: Orphan section | Section has no SERVES edge to any ArgumentClaim | Build warning |
| SI-07: Missing BibTeX | `{{cite:NAME:key}}` has no matching entry in references.bib | Build aborts |
| SI-08: Missing figure file | `{{figure:NAME:path}}` points to nonexistent file | Build aborts |

### Tier 2: Prose Quality Rules (Soft Constraints — Flagged for Review)

Machine-checkable, codified in a YAML config file. Violations are reported; human decides to fix, override, or annotate as intentional exception.

```yaml
# paper_qc_config.yaml

prose_rules:
  max_sentence_words: 35
  min_paragraph_sentences: 2
  max_paragraph_sentences: 8
  no_inline_bold: true
  no_em_dashes: true
  no_semicolons_over_words: 20
  active_voice_preferred: true
  first_person: "we"
  tense_results: past
  tense_claims: present
  max_hedge_per_claim: 1
```

| Check | Description | Enforcement |
|-------|-------------|-------------|
| PQ-01: Sentence length | Sentence exceeds `max_sentence_words` | Flag with location |
| PQ-02: Paragraph length | Paragraph below `min` or above `max` sentences | Flag with location |
| PQ-03: Inline bold | Bold used outside headings/labels | Flag with location |
| PQ-04: Em dashes | Em dash (—) found in prose | Flag with location |
| PQ-05: Run-on joins | Semicolons in sentences over N words | Flag with location |
| PQ-06: Hedge stacking | Multiple hedging words in one claim | Flag with location |
| PQ-07: Pronoun ambiguity | "This" or "It" opening a sentence without clear antecedent | Flag (heuristic, may have false positives) |
| PQ-08: Tense inconsistency | Past/present tense mismatch within paragraph | Flag (heuristic) |

### Tier 3: Style Preferences (Blacklist / Repetition Detection — Informational)

No build impact. Reported for human awareness.

```yaml
# paper_style_config.yaml

banned_words:
  always:
    - "novel"
    - "utilize"
    - "leverage"
    - "robust"
    - "notably"
    - "remarkably"
    - "strikingly"
    - "importantly"

banned_phrases:
  always:
    - "it is important to note"
    - "it is worth noting"
    - "it should be noted"
    - "in order to"
    - "the fact that"
    - "provides an explanation of"
    - "exhibits a difference from"

  paper_specific: []  # Added per-project

repetition_detection:
  window_paragraphs: 3
  flag_repeated_non_trivial_words: true
  min_word_length: 6  # Don't flag "the", "and"
  exclude: []  # Technical terms that repeat legitimately

cliche_patterns:
  - "\\bpaves the way\\b"
  - "\\bsheds light on\\b"
  - "\\btip of the iceberg\\b"
  - "\\bgame.?changer\\b"
  - "\\bparadigm shift\\b"
  - "\\bsynergy\\b"
  - "\\bholistic\\b"
  - "\\bseamless\\b"
```

| Check | Description | Enforcement |
|-------|-------------|-------------|
| SP-01: Banned word | Word from `banned_words.always` found | Report with location and count |
| SP-02: Banned phrase | Phrase from `banned_phrases` found | Report with location |
| SP-03: Repetition | Same non-trivial word appears in N consecutive paragraphs | Report |
| SP-04: Cliché | Pattern from `cliche_patterns` matches | Report with location |
| SP-05: Self-congratulation | Superlative/emphasis adverbs ("very", "extremely", "highly") | Report |
| SP-06: Nominalization | Noun-form where verb exists ("utilization" → "use") | Report (heuristic) |

---

## 5. The Perturbation and Healing Model

When a paragraph is deleted, rewritten, or moved, the system identifies what broke and surfaces it.

### Change Classification

| Action | Graph Impact | Healing Required |
|--------|-------------|-----------------|
| Paragraph deleted | Incoming ASSUMES edges now dangle; SUPPORTS edges lost | Must resolve: re-anchor ASSUMES or accept structural weakening |
| Paragraph rewritten | Claim inventory stale; outgoing edges may be invalid | Refresh claim inventory; re-validate edges |
| Paragraph moved (reorder) | SEQUENCED_AFTER edges stale | Auto-heal: recompute sequence from file order |
| Result updated | Staleness propagates to all CITES edges | Existing mechanism (AD-006 staleness propagation) |
| Section deleted | All contained paragraphs, claims, edges lost | Cascade: surface all broken incoming edges from other sections |
| New paragraph added | No breakage; may need new edges | Agent proposes edges; human reviews |

### Healing Workflow

1. **Detection:** Change triggers graph traversal to identify broken/stale edges.
2. **Report:** System produces a perturbation report:
   ```
   PARAGRAPH DELETED: section_3_para_4 ("Standard GP fitness is exploitable...")
   
   BROKEN EDGES:
     - section_5_para_2 ASSUMES section_3_para_4  [STRUCTURAL — must fix]
     - section_5_para_2 claim: "Building on the exploitability shown in Section 3..."
   
   WEAKENED EDGES:
     - argument_claim_1 SUPPORTS lost (was 3 supports, now 2)  [REVIEW — still adequate?]
   
   NO IMPACT:
     - section_2_para_1 EXTENDS section_3_para_4  [section_2 comes before section_3, EXTENDS was informational]
   ```
3. **Decision:** Human decides how to heal. Options: rewrite the dependent paragraph, move the deleted claim elsewhere, update edges, or accept the weakening.
4. **The system does not auto-heal.** It surfaces what broke. The scientist decides what to do about it.

---

## 6. Cross-Section Awareness via Claim Inventory

The key architectural insight: **agents don't need full prose to maintain cross-section coherence. They need the claim inventory.**

### Context Slice for Writing Agent

When an agent is drafting Section 5, paragraph 3:

```
ARGUMENT SKELETON (full — ~200 tokens):
  Thesis: "Entropy-based fitness avoids wrong-limit attractors..."
  This section serves: Supporting Claim 3 (evaluation horizon trade-off)

SECTION ROLE: "Demonstrate that extending evaluation horizon T shifts but
does not eliminate wrong-limit attractors"

CLAIM INVENTORY — PRIOR SECTIONS (~100 tokens per section):
  Section 1 (Intro): Establishes SR fitness landscape problem. Cites [schmidt2009].
  Section 2 (Background): Defines wrong-limit attractors. Cites [cranmer2023, hillar2012].
  Section 3 (Methods): Entropy fitness defined. Bits-per-decade metric.
    - Para 3.4 ESTABLISHES: "Standard GP fitness exploitable at finite T"
      [YOUR SECTION ASSUMES THIS — section_3_para_4]
  Section 4 (Results - entropy): Entropy fitness finds Leibniz in 1.0/5 seeds.
    - Para 4.2: {{result:entropy_minimal_5_5:value}} = 1.0

CLAIM INVENTORY — THIS SECTION SO FAR:
  Para 5.1: Scaling behavior across terminal set sizes
  Para 5.2: T-sensitivity analysis setup

VERIFIED RESULTS AVAILABLE FOR THIS PARAGRAPH:
  {{result:scaling_T_sensitivity:value}} = ... [verified]
  {{result:attractor_density_T1000:value}} = ... [verified]

CONVENTIONS: [pointer to paper_qc_config.yaml — agent loads if needed]

WRITE: Section 5, Paragraph 3. Role: Present T-sensitivity results showing
attractor shift behavior.
```

Total context: ~800-1200 tokens for cross-section awareness. Not 15,000 tokens of full prose. The agent has:
- The argument it's serving
- Compressed awareness of what every other section established
- The specific claims it ASSUMES (with explicit pointers)
- The verified results it can cite
- The conventions to follow

### Claim Inventory Maintenance

Two modes:

**Top-down (new paper):** Human writes argument skeleton → defines section roles → outlines what each paragraph should claim → agents draft prose from claims.

**Bottom-up (existing prose):** Agent reads existing paragraphs → extracts claim inventory → proposes edges (ASSUMES, EXTENDS, SUPPORTS) → human reviews and corrects.

The leibniz-pi paper needs bottom-up bootstrapping for existing sections, then top-down for new sections.

---

## 7. Schema Extensions to research.yaml

### New Artifact Types

```yaml
artifact_types:
  # ... existing types ...
  - ArgumentClaim     # Argument skeleton node
  - Paragraph         # Paragraph-level tracking
  - Claim             # Assertion within a paragraph
```

### New Relationship Types

```yaml
relationship_types:
  # ... existing types ...
  
  # Intra-paper structural
  contains_paragraph:
    from_types: [PaperSection]
    to_types: [Paragraph]
  contains_claim:
    from_types: [Paragraph]
    to_types: [Claim]
  sequenced_after:
    from_types: [Paragraph, PaperSection]
    to_types: [Paragraph, PaperSection]
  
  # Intra-paper logical
  assumes:
    from_types: [Claim]
    to_types: [Claim]
  extends:
    from_types: [Claim]
    to_types: [Claim]
  supports:
    from_types: [Claim]
    to_types: [ArgumentClaim]
  contradicts:
    from_types: [Claim]
    to_types: [Claim]
  refines:
    from_types: [Claim]
    to_types: [Claim]
  serves:
    from_types: [PaperSection]
    to_types: [ArgumentClaim]
  
  # Evidence links (extending existing)
  cites_result:
    from_types: [Claim]
    to_types: [Result]
  cites_literature:
    from_types: [Claim]
    to_types: [Citation]
  references_figure:
    from_types: [Paragraph]
    to_types: [Figure]
```

### New State Machines

```yaml
state_machines:
  ArgumentClaim:
    proposed: [accepted]
    accepted: [supported, stale]
    supported: [published, stale]
    published: [stale]
    stale: [accepted]

  Paragraph:
    proposed: [draft]
    draft: [review, stale]
    review: [final, draft]
    final: [stale]
    stale: [draft]

  Claim:
    proposed: [active]
    active: [stale]
    stale: [active]
```

---

## 8. New CLI Commands

### Paper Subcommand Group

```
seldon paper init <name>              # Scaffold paper directory + register sections
seldon paper build                    # Reference resolution + assembly + QC
seldon paper audit                    # Run all QC checks without building
seldon paper audit --tier 1           # Structural integrity only
seldon paper audit --tier 2           # Prose rules only  
seldon paper audit --tier 3           # Style preferences only
seldon paper numbers-registry         # Export graph → markdown table (human-readable view)
seldon paper figure-map               # Export figure artifacts → YAML
seldon paper citation-check           # Verify BibTeX ↔ graph consistency
seldon paper claim-inventory          # Export claim inventory as markdown
seldon paper perturbation-report      # Show broken/weakened edges from recent changes
```

### Claim Management

```
seldon claim create --section <name> --paragraph <n> --statement "..." --type finding
seldon claim link --from <claim_id> --rel assumes --to <claim_id>
seldon claim inventory --section <name>    # Show claims for a section
seldon claim inventory --all               # Full paper claim inventory
```

### Argument Skeleton

```
seldon argument create --statement "..." --role thesis
seldon argument create --statement "..." --role supporting --parent <id>
seldon argument show                       # Display full argument tree
seldon argument coverage                   # Which claims are supported vs. gaps
```

---

## 9. Build Pipeline (Extended from AD-011)

AD-011 defined reference resolution (`{{result:NAME:value}}`). This AD extends the build to include the full QC pipeline.

```
seldon paper build [--strict] [--skip-qc] [--output paper.qmd]

Pipeline:
  1. Load argument skeleton from graph
  2. Load all section files from paper/sections/ in sort order
  3. Reference resolution (AD-011) — substitute {{result:...}}, {{figure:...}}, {{cite:...}}
  4. Tier 1 QC: Structural integrity checks (SI-01 through SI-08)
     - --strict: abort on any warning (default: abort on errors only)
  5. Tier 2 QC: Prose quality checks (PQ-01 through PQ-08)
     - Load paper_qc_config.yaml
     - Report violations with file:line locations
  6. Tier 3 QC: Style checks (SP-01 through SP-06)
     - Load paper_style_config.yaml
     - Report for awareness (never blocks build)
  7. Assembly: frontmatter + abstract + resolved sections → .qmd
  8. Render: quarto render → PDF/HTML
  9. Post-build report: summary of all QC findings by tier
```

`--skip-qc` bypasses tiers 2-3 for rapid iteration. Tier 1 always runs (structural integrity is non-negotiable).

---

## 10. Implementation Plan

### Phase 1: QC Config Files (Now — No Code Required)

Write the YAML config files for the leibniz-pi paper. These are immediately useful even without automation — they codify decisions.

- [ ] `paper_qc_config.yaml` — prose rules (sentence length, paragraph length, etc.)
- [ ] `paper_style_config.yaml` — banned words, clichés, repetition rules
- [ ] General `conventions.md` — human-readable writing rules (extends pragmatics template)

### Phase 2: Style/Prose QC Agent (1-2 sessions)

A standalone Python script that reads markdown files and applies Tier 2 + Tier 3 checks. No graph dependency. Pure text analysis.

- [ ] Sentence length checker
- [ ] Paragraph length checker
- [ ] Banned word/phrase scanner
- [ ] Cliché pattern matcher
- [ ] Repetition detector (sliding window)
- [ ] Em dash / inline bold detector
- [ ] CLI: `seldon paper audit --tier 2 --tier 3` or standalone `paper_qc.py`

This is high-value/low-effort. Regex + counting. Usable on any markdown file, not just Seldon-managed papers.

### Phase 3: Build Pipeline with Reference Resolution (1-2 sessions)

Implement AD-011's `seldon paper build` with Tier 1 structural checks.

- [ ] Reference resolution parser (`{{result:NAME:value}}` → graph lookup)
- [ ] Stale/missing/unverified detection
- [ ] BibTeX cross-reference check
- [ ] Figure file existence check
- [ ] Assembly into .qmd
- [ ] Quarto render integration

### Phase 4: Argument Skeleton + Claim Inventory (2-3 sessions)

The new schema work. Requires research.yaml updates and new CLI commands.

- [ ] Add ArgumentClaim, Paragraph, Claim to research.yaml
- [ ] Add intra-paper edge types (ASSUMES, EXTENDS, SUPPORTS, etc.)
- [ ] `seldon argument` CLI commands
- [ ] `seldon claim` CLI commands
- [ ] Claim inventory export (materialized view as markdown)
- [ ] ASSUMES edge validation (Tier 1 check SI-04)
- [ ] Argument coverage check (SI-05)

### Phase 5: Perturbation Detection + Healing Reports (1-2 sessions)

- [ ] Change detection (paragraph added/deleted/modified via content hash)
- [ ] Edge impact analysis (which edges broke, weakened, or are unaffected)
- [ ] Perturbation report generation
- [ ] Integration into `seldon paper build` (report shown before assembly)

### Phase 6: Context Slice Generation for Writing Agents (2-3 sessions)

- [ ] Claim inventory compression (paragraph → 1-sentence summary)
- [ ] Per-section context slice generator
- [ ] Argument skeleton + section roles + compressed claims + available results
- [ ] Token budget estimation per slice
- [ ] Integration with agent workflow (briefing for writing vs. briefing for research)

---

## 11. What This Does NOT Do

- **Does not generate the argument.** The scientist writes the argument skeleton. The system validates it's structurally complete and renders it as prose.
- **Does not auto-fix prose.** QC reports violations. The human fixes them or annotates as intentional. The system is not a grammar corrector.
- **Does not auto-heal perturbations.** It surfaces what broke. The scientist decides how to fix it.
- **Does not replace human judgment on validity.** An agent can verify that claim X cites result Y. It cannot determine whether result Y actually supports claim X in a scientifically meaningful way.
- **Does not enforce rigidity.** Every soft constraint can be overridden. Every style preference is informational. Only structural integrity is mandatory — and even that has an escape hatch (`--skip-qc` for rapid iteration).

---

## 12. Relationship to Existing Documents

| Document | Status After AD-012 |
|----------|-------------------|
| AD-011 (database-driven paper assembly) | **Incorporated.** Reference resolution syntax and build pipeline carry forward as the foundation. AD-012 extends with claim tracking and tiered QC. |
| paper_authoring_convention.md | **Superseded.** The flat-file convention spec is replaced by the graph-native approach. The scaffold structure and conventions template remain useful as starting points. |
| 2026-03-10_fractal_document_graph.md | **Incorporated.** The node hierarchy (Paper → Section → Paragraph → Claim) and edge types are formalized here with state machines and QC semantics. |
| WRITING_CONVENTIONS_PAPER.md (pragmatics) | **Template source.** The general rules become the seed for `conventions.md` and `paper_style_config.yaml`. Paper-specific rules stay paper-specific. |

---

## 13. Vector Embeddings: Role and Limits

Embedding similarity has a specific, bounded role in this system: **redundancy detection in Tier 3 QC.**

Use embeddings to flag: "These two paragraphs in different sections are saying suspiciously similar things." Surface for human review. This catches unintentional repetition that word-level repetition detection misses (same idea, different words).

Do NOT use embeddings for:
- Inferring logical dependencies (ASSUMES, EXTENDS). These are argumentative relationships, not semantic similarity. Two paragraphs can discuss the same topic and contradict each other. Two paragraphs on different topics can have critical logical dependencies.
- Generating the claim inventory. Claims are extracted by reading comprehension, not by embedding proximity.
- Replacing explicit edge types. Embeddings are fuzzy; the paper's logical structure must be precise.

If/when embedding-based redundancy detection is implemented, it's a Tier 3 check (informational, never blocks build).

---

*This is the most architecturally significant addition to Seldon since the core engine. But it's tractable: the foundation (Neo4j graph, staleness propagation, CLI, reference resolution) exists. The new pieces are schema additions, QC scripts, and claim-level tracking — all extensions of proven patterns.*
