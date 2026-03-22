# Validity Vocabulary — Canonical Reference

**Maintained in:** `seldon/ontology/validity/`
**Per:** AD-017 (Central Validity Ontology)
**Last updated:** 2026-03-22

---

## Purpose

Single source of truth for validity-related terminology used across all Seldon-tracked projects. Future projects reference this vocabulary. Existing projects used their own definitions at the time and are not retroactively modified. Every definition cites its authoritative source.

---

## Sources

| Short Key | Full Citation | BibTeX Key |
|-----------|---------------|------------|
| [Webb-2026a] | Webb, B. (2026). *AI for Official Statistics.* Chapter 20: State Fidelity Validity. https://brockwebb.github.io/ai4stats/ | `Webb2026ai4stats` |
| [Webb-2026b] | Webb, B. (2026). When AI Enters Federal Statistics: A Crosswalk Between Data Quality and AI Trustworthiness Frameworks. Zenodo. doi:10.5281/zenodo.18766095 | `Webb2026crosswalk` |
| [SCC-2002] | Shadish, W.R., Cook, T.D., & Campbell, D.T. (2002). *Experimental and Quasi-Experimental Designs for Generalized Causal Inference.* Houghton Mifflin. | `ShadishCookCampbell2002` |
| [CM-1955] | Cronbach, L.J. & Meehl, P.E. (1955). Construct validity in psychological tests. *Psychological Bulletin, 52*(4), 281–302. doi:10.1037/h0040957 | `CronbachMeehl1955` |
| [Hirstein-2005] | Hirstein, W. (2005). *Brain Fiction: Self-Deception and the Riddle of Confabulation.* MIT Press. | `Hirstein2005` |
| [Groves-2009] | Groves, R.M., et al. (2009). *Survey Methodology.* 2nd ed. Wiley. | `Groves2009` |
| [NIST-2023] | National Institute of Standards and Technology. (2023). *Artificial Intelligence Risk Management Framework (AI RMF 1.0).* NIST AI 100-1. doi:10.6028/NIST.AI.100-1 | `nist2023airm` |
| [NIST-2024] | National Institute of Standards and Technology. (2024). *AI RMF: Generative AI Profile.* NIST AI 600-1. doi:10.6028/NIST.AI.600-1 | `nist2024genai` |
| [FCSM-2020] | Federal Committee on Statistical Methodology. (2020). *A Framework for Data Quality.* FCSM 20-04. | `fcsm2020` |

All BibTeX entries are maintained in `seldon/docs/references/references.bib`.

---

## State Fidelity Validity (SFV)

**State Fidelity Validity (SFV):** The degree to which an AI-assisted research or analytic pipeline preserves the accuracy and integrity of its accumulated internal state (decisions, terminology, methodology, and intermediate findings) across sequential operations, such that inferences at step N remain warranted by the actual history of steps 1 through N-1, rather than by degraded, distorted, confabulated, or selectively retained versions of that history. [Webb-2026a]

**Abbreviation:** SFV (always capitalized, no periods)

### Sub-dimensions

| Canonical Name | Shorthand | Definition |
|----------------|-----------|------------|
| Terminological Consistency | TC | Vocabulary remains stable and matches externally defined terms across the full execution |
| State Provenance | SP | Outputs are traceable to actual prior steps; no invented history |
| Compression Fidelity | CF | Summarization and compaction do not distort meaning of prior decisions |
| Session Continuity | SC | Information survives thread/session boundaries intact |
| State Coherence | SCoh | Accumulated state is internally consistent at any given point |

[Webb-2026a]

### Threat Taxonomy

| # | Canonical Threat Name | Description |
|---|----------------------|-------------|
| T1 | Semantic Drift | Terminology mutates across turns or sessions without explicit redefinition |
| T2 | False State Injection | System confabulates "memory" of decisions or agreements never established |
| T3 | Compression Distortion | Context window management (compaction, summarization) silently strips nuance or alters meaning |
| T4 | State Supersession Failure | Outdated information persists and influences output despite being explicitly superseded |
| T5 | State Discontinuity | Session boundary loss drops accumulated context; new session operates on partial history |

[Webb-2026a]

### Severity Scale

| Level | Description |
|-------|-------------|
| Fatal | Construct validity failure: pipeline is measuring the wrong thing entirely |
| Potentially fatal | Cumulative uncaught state drift across sessions: corrupted research base |
| Recoverable | Single-session SFV failure caught and corrected before downstream use |
| Cosmetic | Minor terminology inconsistency with no impact on inference |

Practitioner framing: "Dead / mostly dead / mostly alive with caveats." [Webb-2026a]

### Operationalization: The State Fidelity Tax

State degradation is a continuous, measurable cost rather than a binary pass/fail. This framing maps to how federal statisticians already think: Total Survey Error, acceptable variance, SQC tolerance intervals, coefficients of variation. [Webb-2026a]

**Tolerable Variance Tiers:**

| Level | Tax Rate | Description | Tolerability |
|-------|----------|-------------|--------------|
| Nominal | Low | Minor stylistic shifts without changing inclusion criteria | Acceptable for all phases |
| Operational | Moderate | Semantic drift or soft confabulation (e.g., model assumes 95% CI when 90% was specified) | Tolerable for exploratory analysis; requires re-validation for official statistics |
| Structural | High | Loss of core constraints or hard terminology drift | Unacceptable — pipeline must be reset or re-anchored |

Note: These map loosely to the severity scale above but use language suited to practitioner audiences. The "tax" framing is better for presentations; the severity scale is better for governance documentation. [Webb-2026a]

### Key Arguments

1. **Validity, not reliability.** State degradation alters what is being measured and how. A pipeline can reliably produce the same corrupted provenance. That is validity failure, not reliability failure. [Webb-2026a]

2. **The instrument is (fixed weights + mutable context buffer).** The context window IS the instrument. Its content determines what the pipeline "knows" and how it operates. State fidelity is whether that instrument maintained integrity. [Webb-2026a]

3. **Latent threat.** Unlike a bad survey question (visible in the instrument), state degradation is invisible until it biases output. Structurally easy to miss. [Webb-2026a]

4. **Not LLM-specific.** Any stateful research process has this vulnerability. Human teams experience it (institutional memory loss, terminology drift across personnel changes). LLMs make it acute and frequent. Frame as general with LLM instantiation. [Webb-2026a]

5. **Precondition for other validity types.** If the operative history is corrupted, neither construct, internal, external, nor statistical conclusion validity claims are defensible. [Webb-2026a]

### Engineering Countermeasures

| Countermeasure | Addresses Threat(s) | Implementation in Seldon |
|----------------|---------------------|--------------------------|
| Config-driven vocabulary | T1 (Semantic Drift) | Terms defined in config files, not context window |
| Graph-backed ontology | T1, T2 | Concepts exist in Neo4j; pipeline queries graph, does not rely on memory |
| TEVV validation loops | T2, T3 | Outputs validated against source of truth before entering research base |
| Handoff documents | T5 (State Discontinuity) | Explicit state serialization at session boundaries |
| Documentation-as-traceability | T3, T4 | Architectural decision records (AD-013) capture rationale |
| Multi-model triangulation | T2 | Convergent evidence across independently prompted models |
| Periodic state reconciliation | T1, T2, T3, T4 | Ask system to restate commitments; diff against canonical log |

[Webb-2026a]

### Operationalization Metrics

| Metric | What It Measures | Maps to Threat(s) |
|--------|-----------------|-------------------|
| Terminology consistency rate | Fraction of terms used correctly across turns/sessions | T1 |
| Reference resolution accuracy | Does step N correctly bind to entities from prior steps? | T2 |
| Post-compaction state divergence | Diff between canonical log and model's paraphrase after compaction | T3 |
| Cross-session reconstruction error | How accurately can a new session reconstruct prior state from handoff? | T5 |
| False provenance rate | Fraction of outputs referencing decisions/states that never occurred | T2 |
| State reconciliation pass rate | Periodic test: system restates commitments, scored against canonical record | T1, T2, T3, T4 |

[Webb-2026a]

### Limitations Boilerplate (for papers using LLM pipelines)

> The findings in this report were generated through a multi-stage, AI-mediated research pipeline. While large language models enable complex analytical synthesis, they are subject to State Fidelity degradation over extended operational sequences. This manifests as a State Fidelity Tax, where the system may confabulate prior internal decisions, drift from established terminology, or lose methodological nuance during context window compaction. To maintain State Fidelity Validity, this study implemented a tolerable variance threshold of [X%]; any divergence in core construct definitions across session boundaries triggered a state-reset and re-injection of the foundational research parameters. Despite these mitigations, the dynamic nature of the instrument's internal state introduces a degree of non-deterministic variance that distinguishes this pipeline from static statistical software.

[Webb-2026a]

---

## Classical Validity Types

SFV extends and depends on the classical validity typology from experimental methodology. [SCC-2002]

**Construct Validity:** The degree to which a test, instrument, or measurement procedure measures the theoretical construct it claims to measure. Requires that the construct be precisely defined and that the instrument is appropriate to that definition. [SCC-2002; CM-1955]

**Internal Validity:** The degree to which a causal inference is warranted — that observed covariation between treatment and outcome reflects a genuine causal relationship rather than a confound. Assumes the measurement instrument does not change during data collection. [SCC-2002]

**External Validity:** The degree to which causal inferences generalize beyond the specific conditions (sample, setting, treatment variation, outcomes) of the study. [SCC-2002]

**Statistical Conclusion Validity:** The degree to which statistical inferences about the covariation between variables are warranted. Requires adequate statistical power, appropriate tests, and consistent measurement. [SCC-2002]

### Positioning of SFV Relative to Classical Types

| Type | What It Addresses | Assumption About Instrument |
|------|-------------------|-----------------------------|
| Construct Validity | Are you measuring what you think you are measuring? | Instrument is defined and stable |
| Internal Validity | Are causal inferences warranted? | Instrument does not change during measurement |
| External Validity | Do findings generalize beyond study conditions? | Instrument behaves the same across contexts |
| Statistical Conclusion Validity | Are statistical inferences warranted? | Instrument produces consistent measurements |
| **State Fidelity Validity** | Does the instrument's accumulated state faithfully represent its actual operational history? | *Does not assume stability; directly tests for it* |

SFV is a **precondition** for all four classical validity types in stateful AI-assisted research pipelines. If the operative history is corrupted, no downstream validity claim is defensible. [Webb-2026a; SCC-2002]

---

## Key Terminology Decisions

### Confabulation (not fabrication, not hallucination)

**Confabulation:** The generation of plausible but unfounded outputs without awareness of error. The system constructs false knowledge and presents it as real, without intent to deceive — the system does not "know" it is wrong. [Hirstein-2005; Webb-2026b]

Distinguished from:
- **Hallucination:** Implies perception of something not present — a perceptual metaphor. Imprecise for AI systems, which do not perceive. Widespread in colloquial AI discourse but discouraged in formal contexts. The correct term per NIST AI 600-1 is confabulation. [NIST-2024]
- **Fabrication:** Implies intent to deceive. Inaccurate for AI systems, which are not intentional agents. Use "confabulation" when the failure mode is generation of false outputs without awareness.
- **False State Injection (T2):** The SFV-specific instantiation of confabulation — the pipeline confabulates "memory" of decisions or agreements that were never established. Confabulation is the general term; T2 is the specific SFV threat. [Webb-2026a]

**Terminology decision rationale:** "Confabulation" was established as the standard term per the neuropsychological literature [Hirstein-2005] and adopted by NIST AI 600-1 [NIST-2024]. The crosswalk article originally used "fabrication" and "confident fabrication"; these were systematically replaced with "confabulation" for terminological precision. [Webb-2026b]

### Reliability vs. Validity Distinction

**Reliability:** Consistency of measurement under repetition or across conditions. A reliable instrument produces the same result when applied to the same object under the same conditions. Reliability is a necessary but not sufficient condition for validity. [CM-1955; SCC-2002]

**Validity:** Whether an instrument measures what it claims to measure. An instrument can be reliably wrong. [CM-1955]

**Application to SFV:** State degradation is a validity failure, not a reliability failure. The argument for this classification:

> Traditional methodologists will argue that an instrument changing its own rules mid-flight is a reliability failure (lack of stability), which subsequently destroys validity. The counter: because the LLM is actively making methodological choices, a loss of state fidelity does not just introduce random noise (which would be reliability). It structurally alters the foundation of the research mid-execution — the definitions and parameters drift, so the system is no longer measuring or analyzing the original construct. That makes it a validity failure, not a reliability failure. A pipeline can reliably produce the same corrupted provenance. That is validity failure.

[Webb-2026a]

### Terms Considered and Rejected

| Rejected Term | Reason for Rejection |
|---------------|---------------------|
| Context Validity | Collision with psychometrics (external conditions around a fixed instrument) |
| Processual Validity | Collision with Hayashi et al. 2019 |
| Processual Integrity Validity (PIV) | Derives from collision; unnecessarily complex |
| Pipeline Integrity Validity | Sounds like data security / infosec |
| Execution Fidelity Validity | "Execution" reads as procedural, not epistemic |
| Temporal State Validity | Collision risk with longitudinal validity concepts |
| Operational Context Validity | "Context" creates confusion with psychometric context validity |

[Webb-2026a]

---

## Framework Terms

### TEVV (Test, Evaluation, Verification, and Validation)

**TEVV:** The NIST AI RMF 1.0 framework for assessing AI systems. Encompasses activities for testing system behavior, evaluating performance against requirements, verifying that systems meet specifications, and validating that systems accomplish intended purposes in their operational context. SFV operationalization fits within TEVV frameworks — state fidelity metrics are a form of validation. [NIST-2023]

### Total Survey Error (TSE)

**Total Survey Error:** The framework for conceptualizing all sources of error that contribute to the difference between an observed survey statistic and the true population value it is intended to estimate. TSE encompasses errors of representation (coverage, sampling, nonresponse, adjustment) and errors of measurement (validity, measurement, processing). SFV is the analogue of TSE for AI-assisted research pipelines: a framework for the full set of state degradation threats that accumulate across execution. [Groves-2009]

### FCSM Data Quality Dimensions

The Federal Committee on Statistical Methodology [FCSM-2020] defines 11 data quality dimensions for official statistics. These are the quality vocabulary on the statistical side of the FCSM/NIST crosswalk.

| Dimension | Brief Definition |
|-----------|-----------------|
| Relevance | Data serve the needs for which they are produced and used |
| Accuracy & Reliability | Data correctly describe the phenomena they measure |
| Timeliness/Punctuality | Data are produced and disseminated within required timeframes |
| Accessibility | Data are available and findable to intended users |
| Coherence | Data are consistent across series, over time, and with related sources |
| Interpretability | Data are accompanied by sufficient metadata for users to understand and use them correctly |
| Granularity | Data are available at the level of detail required by users |
| Scientific Integrity/Credibility | Data production follows sound methods and is transparent about its limitations |
| Transparency | Data production methods are documented and disclosed |
| Confidentiality | Data protect the identity of respondents and sensitive information |
| Computer & Physical Security | Data and infrastructure are protected from unauthorized access and physical threats |

[FCSM-2020]

### Construct Validity Audit Methodology (Crosswalk Application)

When auditing a crosswalk between frameworks (e.g., FCSM/NIST), construct validity checks whether the mapped concepts are genuinely equivalent in scope, not merely sharing vocabulary. Key distinctions identified in the FCSM/NIST crosswalk audit:

- **Substantive equivalence:** Both frameworks address the same output quality concern (e.g., FCSM Accuracy & Reliability ↔ NIST Valid & Reliable)
- **Procedural correspondence only:** Frameworks share vocabulary but address different levels — one addresses output quality, the other addresses process governance (e.g., FCSM Relevance ↔ NIST MAP function: same word, different construct)
- **Distributed mapping:** A concept in one framework is addressed by multiple scattered elements in the other (e.g., NIST Safety is addressed by FCSM Confidentiality + C&PS + A&R combined)

Presenting procedural correspondences without qualification as construct equivalences is a validity threat in crosswalk documentation. [Webb-2026b]

---

## Related Terms (Defined Elsewhere)

| Term | Brief Meaning | Canonical Source |
|------|---------------|-----------------|
| Context window | The token buffer containing the system's current operative state — the literal instrument in LLM pipelines | Not a metaphor in SFV; it is the physical substrate of state |
| Compaction | Automated summarization/truncation of context to fit window limits | Distinct from intentional summarization by a researcher |
| Handoff document | Explicit serialization of accumulated state for session continuity | Engineering countermeasure to T5; see Seldon session protocol |
| State | The accumulated working context: decisions made, terms defined, methods chosen, intermediate findings recorded | Use precisely; do not conflate with database state or application state |
| Fidelity | Faithfulness of the operative state to the actual history of decisions | Use precisely; do not conflate with audio/signal fidelity |

---

## Terms That May Be Promoted from Projects

*Placeholder. As project-specific terms prove cross-project utility, they get added here with citations.*

| Candidate Term | Origin Project | Status |
|----------------|----------------|--------|
| Log-precision fitness | leibniz-pi | Project-specific; candidate for promotion if used in future GP/SR work |
| Precision gain rate | leibniz-pi | Project-specific; candidate for promotion if used in future GP/SR work |
