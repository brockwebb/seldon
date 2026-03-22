# SFV Development Notes: Gemini Discovery Conversation
**Date:** 2026-03-22 (conversation date approximate)
**Purpose:** Reference document capturing the intellectual provenance of SFV naming and key framing insights from an exploratory conversation with Google Gemini. The canonical definitions are in `SFV_TERMINOLOGY_BASELINE.md` — this document preserves the discovery process and supplementary framing that may be useful for the SSRN preprint and presentations.

---

## Provenance

SFV was arrived at through iterative dialogue. The initial prompt described the problem space (terminology drift, confabulation as memory, compaction loss, stale context, session boundary loss) and asked whether an existing term covered it. Gemini confirmed no existing term does and evaluated candidate names.

### Candidates Evaluated

| Candidate | Gemini Assessment |
|-----------|-------------------|
| Operational Context Validity | "Context" creates confusion with psychometric context validity |
| Execution Fidelity Validity | Accurate but clunky |
| Pipeline Integrity Validity | Drifts toward data security / CIA triad |
| Temporal State Validity | Over-emphasizes time; failure is logical and structural |
| State Coherence Validity | Strong — bridges CS and methodology |
| **State Fidelity Validity** | Selected — punchy, precise, implies measurable gradient |

---

## Key Framing: The "Tax" Metaphor for Operationalization

The "State Fidelity Tax" framing positions state degradation as a continuous, measurable cost rather than a binary pass/fail. This maps directly to how federal statisticians already think: Total Survey Error, acceptable variance, SQC tolerance intervals, coefficients of variation.

### Tolerable Variance Tiers (from Gemini conversation)

| Level | Tax Rate | Description | Tolerability |
|-------|----------|-------------|--------------|
| Nominal | Low | Minor stylistic shifts without changing inclusion criteria | Acceptable for all phases |
| Operational | Moderate | Semantic drift or soft confabulation (e.g., model assumes 95% CI when 90% was specified) | Tolerable for exploratory analysis; requires re-validation for official statistics |
| Structural | High | Loss of core constraints or hard terminology drift | Unacceptable — pipeline must be reset or re-anchored |

**Note:** These map loosely to the severity scale in the terminology baseline (Cosmetic / Recoverable / Potentially Fatal / Fatal) but use different language suited to different audiences. The "tax" framing is better for practitioners and presentations; the severity scale is better for governance documentation.

**Connection to foreword:** The stochastic tax concept introduced in the book's foreword provides the philosophical foundation; the State Fidelity Tax is its operationalization for pipeline validity.

---

## Key Framing: SFV as Umbrella (Supertype) with Sub-Validities

The OO/inheritance framing positions SFV as a class containing specialized instances. This is valuable because:

1. It shows SFV is interconnected with established validity concepts, not isolated
2. It allows agencies to set different tolerance thresholds for different sub-types
3. It maps naturally to the sub-dimensions already defined in the terminology baseline

### Mapping: Gemini Sub-types → Canonical Sub-dimensions

| Gemini Framing | Canonical Sub-dimension (from TERMINOLOGY_BASELINE) |
|----------------|-----------------------------------------------------|
| Epistemic State Validity | State Provenance (SP) + State Coherence (SCoh) |
| Lexical State Validity | Terminological Consistency (TC) |
| Functional Context Validity | Compression Fidelity (CF) |
| Methodological Continuity Validity | Session Continuity (SC) |

The canonical sub-dimensions are more granular and precise. The Gemini framing is useful for high-level presentations where the audience needs the concept before the taxonomy.

---

## Reliability vs. Validity Defense

This argument will come up at FCSM. The defense:

> Traditional methodologists will argue that an instrument changing its own rules mid-flight is a reliability failure (lack of stability), which subsequently destroys validity. The counter: because the LLM is actively making methodological choices, a loss of state fidelity does not just introduce random noise (which would be reliability). It structurally alters the foundation of the research mid-execution — the definitions and parameters drift, so the system is no longer measuring or analyzing the original construct. That makes it a validity failure, not a reliability failure. A pipeline can *reliably* produce the same corrupted provenance. That is validity failure.

---

## Boilerplate: Limitations Paragraph (for papers using LLM pipelines)

> The findings in this report were generated through a multi-stage, AI-mediated research pipeline. While large language models enable complex analytical synthesis, they are subject to State Fidelity degradation over extended operational sequences. This manifests as a State Fidelity Tax, where the system may confabulate prior internal decisions, drift from established terminology, or lose methodological nuance during context window compaction. To maintain State Fidelity Validity, this study implemented a tolerable variance threshold of [X%]; any divergence in core construct definitions across session boundaries triggered a state-reset and re-injection of the foundational research parameters. Despite these mitigations, the dynamic nature of the instrument's internal state introduces a degree of non-deterministic variance that distinguishes this pipeline from static statistical software.

---

## Mitigation Strategies (from Gemini, aligned with canonical countermeasures)

| Strategy | Description | Maps to Canonical Countermeasure |
|----------|-------------|----------------------------------|
| Deterministic Semantic Anchoring | External source of truth (MCP server, glossary) queried every turn | Config-driven vocabulary; Graph-backed ontology |
| Checkpoint Re-Injection | Re-inject core constraints every N turns | Periodic state reconciliation |
| State-Aware Summarization | Prioritize methodological invariants over narrative during compaction | Documentation-as-traceability |
| Validation Probes ("Audit Turn") | Periodic "restate definition of X" queries; diff against canonical | Periodic state reconciliation |

---

*This is a reference document. Canonical definitions remain in SFV_TERMINOLOGY_BASELINE.md.*
