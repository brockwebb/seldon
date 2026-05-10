# AD-023 — Wintermute Sleep Functions as Architectural Center

**Status:** Proposed, 2026-04-18. Promoted from CC5 deliverable (evolution burst 2026-04) with one edit — claude-mem Option A commitment surfaced in Decision section per operator call 2026-04-18.
**Related:** AD-017 (ontology), AD-019/020 (AI-proposes / human-arbitrates authority model), AD-022 (CLI-default).
**Full specification:** `docs/design/evolution_burst_2026-04/cc5_sleep_function_architecture.md` — this AD is the decision; the spec is the implementation detail.

---

## Context

The CC1 literature survey (evolution burst 2026-04, Q4) established that claude-mem solves commodity capture — five-hook lifecycle, CLAIM-CONFIRM queue, hybrid search, production-grade AGPL code — better than Wintermute v1 ever did. The CC2 infrastructure audit found Wintermute's `wintermute-intake` graph has 7,660 nodes with no quality measurement, no entity resolution, and no relationship inference. ClaudeClaw runs 16 autonomous jobs feeding this graph.

The critical question: **what does Wintermute offer that commodity capture doesn't?**

This AD answers that question and commits to the answer.

## Decision

**Wintermute's architectural center is the sleep-function layer: offline graph cognition that runs asynchronously, operates on the accumulated graph with whole-graph visibility, and improves graph fidelity over time without user intervention at ingestion time.**

Three sleep functions define this layer (full specs in CC5 deliverable):

- **A. Collapse / Dedup** — nightly. Three-layer entity resolution: deterministic SemHash pre-dedup → LLM-proposed merges (auto-accept ≥ 0.90, arbitration 0.50–0.89) → human YAML review.
- **B. Disambiguate** — weekly. Detects entities that should be split based on claim embedding bimodality, attribute contradictions, edge-type entropy. All splits go to human arbitration.
- **C. LLM-Proposed Edge Inference** — weekly, after A and B. Proposes new edges between entities with shared neighbors + embedding cosine ≥ 0.60. Same three-tier authority model as A.

**Every Wintermute engineering investment must serve these functions or the infrastructure that makes them possible.** Ingestion pipelines that generate raw entity/claim/document nodes are in-scope because sleep functions need them. Retrieval endpoints are second-class unless they serve sleep-function quality (e.g., surfacing arbitration queues).

**Commodity capture is explicitly OUT of Wintermute's core.** Per operator decision 2026-04-18, **claude-mem is adopted (Option A)** as the capture layer. Wintermute consumes claude-mem observations via bridge and owns the sleep layer above them. This is a deliberate narrowing: Wintermute does not re-solve a problem claude-mem has already solved.

**AGPL acceptance:** The claude-mem Option A commitment inherits AGPL. Acceptable for personal infrastructure (operator's context). If Seldon/Wintermute ever enters a distribution or service context where AGPL becomes restrictive, Option B (extract patterns) remains reversible at the cost of rebuilding reliability work. Flagged here so future consumers of this AD can find the assumption.

## Consequences

**Positive:**
- Clarifies the build roadmap: every engineering decision is evaluated against "does this help sleep functions run better?"
- Positions Wintermute uniquely in the ecosystem — no other tool in the CC1 survey performs offline graph cognition at this level.
- Makes the kill/keep decision crisp: if sleep functions aren't implemented within a bounded timeframe, Wintermute's independent existence lacks justification and it should be reduced to a thin layer over claude-mem.
- Provides a measurement criterion: sleep-function precision, recall proxies, and arbitration acceptance rates tell us whether Wintermute is improving the graph.

**Negative / cost:**
- Narrows Wintermute's scope deliberately. Features outside the sleep-function center (search API, retrieval endpoint, chat interface) become second-class unless they serve sleep-function quality.
- Sleep functions require a running, high-quality entity/claim/document graph. If ingestion quality is poor (noisy entities, garbage claims), sleep functions amplify noise rather than resolving it. Garbage-in / garbage-out applies.
- Human arbitration is a UX burden. The self-regulating valve (raise threshold when queue > 100) is a mitigation, not a solution.

**Reversibility:** High on the architectural claim; medium on the implementation.
- **Architectural claim:** If three months of sleep-function operation shows no graph-quality improvement (precision proxies stay low, rejection rates stay high — e.g., > 50% rejection on Sleep C per roadmap bet 10.1), this AD is amended to deprioritize or defer sleep functions. Wintermute may then reduce to a thin layer over claude-mem.
- **Implementation:** Event-sourced graph means any sleep-function mutation can be rolled back. Tombstone pattern (absorbed entities marked, not deleted) is essential to this and is non-negotiable.

## Measurement Discipline

Sleep functions are a claim about what produces value. The only way to validate the claim is to measure. AD-023 is therefore **load-bearing on CC4 observability** (see AD-024). Key metrics (full table in CC5 deliverable):

- `sleep.*.proposals.per_cycle` — is the function finding anything?
- `sleep.*.auto_accepted_rate` — is the threshold calibrated? (Expected range: 0.20–0.60.)
- `sleep.*.rejected.per_cycle` — is the LLM's signal trustworthy? (Expected: < 40% rejection on Sleep A merges; < 50% on Sleep C edges.)
- `sleep.arbitration_queue.size` — is the workflow sustainable?
- `sleep.compute.cost_usd.per_cycle` — is it affordable? (Budget: < $0.05/cycle at current graph scale.)

If after 30 days any sleep function's metrics are outside expected ranges and the cause cannot be identified, that function is re-evaluated against the decision above.

## Relation to Prior ADs

- **AD-001 (ANTS → Seldon):** Extends event-sourced append-only pattern into Wintermute. Sleep functions emit events to a Wintermute event log with the same schema.
- **AD-017 (Central Validity Ontology):** Sleep functions operate on ontology-aligned entities. Edge-type vocabulary for Sleep C is constrained to the Wintermute entity relationship ontology, not invented per proposal.
- **AD-019/AD-020 (Agentic audit, multi-lens review):** Same authority model — AI proposes, human arbitrates. Sleep-function arbitration is structurally identical to AD-019's Issue routing at the graph-curation layer.
- **AD-022 (CLI-default):** `wintermute arbitrate` is CLI. AD-023 is the primary consumer of AD-022's governing principle.
- **AD-024 (Observability as substrate):** AD-023 is the hardest test of AD-024. If the dashboard cannot surface sleep-function signal, AD-024 has a gap.

## Open Questions

- **ClaudeClaw `knowledge_graph_extract` output quality.** Sleep A has nothing to merge if the input entities aren't coherent. A 20-node sample from `wintermute-intake` is a prerequisite for Sleep A implementation (scheduled as part of roadmap 15.2).
- **Wintermute edge-type ontology completeness.** Sleep C constrains proposals to defined relationship types. The current vocabulary may be incomplete. A schema audit precedes Sleep C work.
- **Sleep cadences.** Nightly Collapse, weekly Disambiguate and Edge Inference are starting values. Calibrate after 30 days of data.
- **Full-graph sleep runs.** V1 scopes to recent neighborhood (24h + 1-hop). Full-graph is a v2 question, not addressed here.
- **Multi-provider ensemble for sleep LLM calls.** Current spec is single-provider (Gemini Flash via LiteLLM). V2 requirement, deferred.

---

*Short AD by design. The decision is the contribution; CC5 has the implementation detail. Reversibility is load-bearing — this AD claims sleep functions justify Wintermute's existence. If sleep functions don't deliver, the claim amends.*
