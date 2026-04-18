# CC5: Wintermute Sleep-Function Architecture — 2026-04-18

**Date:** 2026-04-18
**Status:** Design spec. Not yet implemented.
**Scope note:** Wintermute is not currently a Seldon-managed project (no `seldon.yaml` at `/Users/brock/Documents/GitHub/wintermute/` per CC2 findings). This spec lives in seldon's `docs/design/evolution_burst_2026-04/`. When Wintermute is initialized as Seldon-managed, the spec migrates there and this file becomes a pointer.

---

## Architectural Claim

Wintermute's distinctive value is not ingestion-plus-lookup. That's a solved problem — claude-mem (CC1 Q4) handles commodity capture better than anything Wintermute v1 ever did: five lifecycle hooks, CLAIM-CONFIRM queue, hybrid SQLite/Chroma search, production battle-tested. If Wintermute competes on that surface, it loses.

Wintermute's only defensible surface is **offline graph cognition**: the computation that happens between sessions, on the accumulated graph, that no live-session tool can do because it requires whole-graph visibility and time. Sleep functions are that computation. They collapse duplicate entities that arrived through different ingestion paths. They detect entities that should be two. They propose relationships that exist in the source material but weren't explicitly extracted. These operations improve the graph's fidelity to reality over time — without user intervention at ingestion time.

Without sleep functions, the `wintermute-intake` graph (7,660 nodes as of CC2) is a heap of extracted text in a graph database. With them, it becomes a knowledge structure that self-corrects, densifies, and surfaces latent connections. The sleep-function layer is the difference between a search index and a knowledge graph. Building it is the only reason to maintain Wintermute alongside claude-mem rather than replacing it entirely.

---

## Literature Scan

1. **Adler et al. (2021). "Incremental Multi-source Entity Resolution for Knowledge Graph Completion." VLDB-adjacent proceedings.** — Addresses online ER as new sources are integrated, enabling continuous matching against existing entities rather than batch reconciliation. **Applicable:** Wintermute's nightly `knowledge_graph_extract` job produces incremental entity batches; the sleep function must resolve those against the existing graph, not rebuild from scratch.

2. **Li et al. (2024). "Knowledge Graph Large Language Model (KG-LLM) for Link Prediction." arXiv:2403.07311.** — LLM-based link prediction using natural-language prompts; notes that signal-to-noise degrades with graph sparsity. **Applicable:** Directly validates the LLM-proposed-edge approach for Sleep Function C; also explains why embedding-only link prediction fails on heterogeneous sparse graphs like `wintermute-intake`.

3. **Qian et al. (2019). "SystemER: A Human-in-the-Loop System for Explainable Entity Resolution." VLDB 12(12).** — Confidence-based thresholding partitions candidate pairs into auto-accept vs human-review using normalized similarity distance. The architecture is structurally identical to sift-kg. **Applicable:** Provides a principled basis for the 0.90 / 0.50 thresholds in Sleep Function A and validates the two-tier dispatch pattern.

4. **Pershina et al. (2014). "Graph-Based Approaches to Resolve Entity Ambiguity." NYU proceedings.** — Graph-structural methods for detecting polysemous entities (one node, two distinct referents). **Applicable:** Informs Sleep Function B's signal detection: shared-neighbor clustering and edge-type distribution entropy as ambiguity indicators.

5. **Xiang et al. (2025). "SplitE: Enhancing Knowledge Graph Embedding Precision with Entity Split and Contextualization." ACM Trans. Recommender Systems.** — Two-stage embedding approach: cluster multi-meaning entities, contextualize splits, back-merge to preserve connectivity. **Applicable:** Validates the embedding-space bimodality signal used in Sleep Function B; also warns that aggressive splitting loses cross-entity connectivity (hence the back-merge logic).

6. **Ebraheem et al. (2016/2021). "Deep Indexed Active Learning for Matching Heterogeneous Entity Representations." arXiv:2104.03986.** — Active learning framework that minimizes human labeling effort by selecting the most informative candidate pairs for review. **Applicable:** Informs arbitration queue prioritization — don't surface all proposals to the human; rank by expected information gain. High-confidence and low-confidence proposals both need less human attention than the 0.70-0.80 band.

7. **Brock's prior: sift-kg (three-layer entity resolution).** — Deterministic pre-dedup at SemHash/0.95 threshold → LLM-proposed merges with confidence scores → human review via editable YAML. **Applicable:** This IS the reference architecture for Sleep Function A. The three layers map directly. The primary addition here is the "recently-changed neighborhood" scope discipline, which sift-kg didn't need because it was a pipeline tool, not an ongoing daemon.

---

## Sleep Function A: Collapse / Dedup

**Purpose:** Merge duplicate entities in `wintermute-intake` that represent the same real-world concept but arrived through different ingestion paths or surface-form variations.

**Trigger / cadence:**
- **Primary:** Nightly at 03:30 local (30 minutes after `knowledge_graph_extract` ClaudeClaw job).
- **Secondary:** Triggered ad-hoc when new-entity count in the last 24h exceeds 100 nodes (high-ingestion day).
- **Manual:** `wintermute sleep collapse [--dry-run]`
- What triggers a full-graph scan (v2, not v1): explicit `--full-graph` flag only. V1 scope is recent neighborhood exclusively.

**Input:**
- **Recently-changed neighborhood:** all Entity nodes with `created_at` in the last 24h, plus their 1-hop neighbors (entities sharing a Claim or Document node). At current ingestion rate (~50 entities/day), this is approximately 100-300 nodes.
- **Upstream dependency:** `knowledge_graph_extract` job must have completed for the current night. If the job's last-run timestamp is stale (> 6h old at 03:30), sleep skips and logs the skip as a `sleep.skipped` event.

**Process:**

*Layer 1 — Deterministic pre-dedup:*
For each entity pair in the recent neighborhood, compute a SemHash fingerprint: Unicode NFC normalization → lowercase → strip punctuation and stop words → sort tokens → SHA-256 prefix (8 chars). Pairs with identical SemHash are trivially the same. Pairs with Jaccard token overlap ≥ 0.95 are also treated as deterministic matches. Both are merged immediately with `method: deterministic`, no LLM call. Typically handles 50-70% of duplicates from the same ingestion batch (same entity extracted twice from one document).

*Layer 2 — LLM-proposed merges:*
For entity pairs that fail the 0.95 Jaccard threshold but share ≥ 1 common neighbor, generate merge proposals. Batch 10 pairs per LLM call. Prompt shape: entity A name + attributes + 5 connected Claims; entity B name + attributes + 5 connected Claims; shared neighbors. Ask: "Should these be merged? Confidence 0.0-1.0, rationale."

Output: `{"merge": bool, "confidence": float, "rationale": str, "canonical": "A"|"B"}`.

- Confidence ≥ 0.90: auto-accept. Emit `merge_accepted` with `method: llm_auto`.
- Confidence 0.50-0.89: add to arbitration queue. Emit `merge_proposed`.
- Confidence < 0.50: discard. No event (not a merge candidate).

**Starting auto-accept threshold: 0.90. Tunable after 30-day calibration.** If human arbitration rejects > 20% of 0.90-0.95 proposals, raise the auto-accept threshold to 0.93.

*Layer 3 — Human arbitration:*
Items emitted as `merge_proposed` are written to `~/.wintermute/arbitration/<date>_collapse.yaml`. Each entry includes: entity A ID/name/claim-count; entity B ID/name/claim-count; LLM rationale; confidence; suggested canonical direction. User reviews with `wintermute arbitrate` (CLI that opens the YAML and accepts/rejects each entry) or by directly editing the YAML and running `wintermute arbitrate --apply`. Accepted items trigger graph mutations + `merge_accepted` events; rejected trigger `merge_rejected`.

Merge direction rule: always merge lower-degree into higher-degree (the hub is more likely canonical). The LLM's `canonical` field overrides this only if confidence > 0.85.

**Output:**
- Events: `merge_proposed {entity_a, entity_b, confidence, rationale}`, `merge_accepted {entity_a, entity_b, method, canonical}`, `merge_rejected {entity_a, entity_b, reason}`.
- Graph mutations: copy all edges from the absorbed entity to the canonical; set `merged_into: <canonical_id>` on the absorbed entity's node (tombstone — do not delete). Edge deduplication: if both entities had the same edge type to the same neighbor, keep one.
- Arbitration queue: `~/.wintermute/arbitration/<date>_collapse.yaml`.

**Compute budget:**

| Scale | New entities/day | Candidate pairs | LLM batches | Input tokens | Cost/cycle |
|---|---|---|---|---|---|
| 1K nodes | 50 | ~80 (after L1 filters 60%) | 3-4 | ~3,500 | ~$0.0003 |
| 10K nodes | 200 | ~300 | 12-15 | ~15,000 | ~$0.001 |
| 100K nodes | 1,000 | ~1,500 | 60-75 | ~75,000 | ~$0.008 |

Pareto 4-64: Most merges cluster around high-ingestion source domains (the 4% of domains with the highest entity extraction rate drive ~64% of duplicate pairs). Instrument `merge_proposed.source_domain` to identify these; consider domain-specific pre-dedup rules as a v2 optimization.

**Failure modes:**
- *Over-merge (false positive):* Two distinct entities merged incorrectly. Highest risk at the 0.90 boundary. Guard: tombstone pattern enables rollback by replaying events in reverse (emit `merge_undone`). Also: direction rule (lower-degree into higher-degree) limits which entity gets affected.
- *Silent directional error:* B merged into A when B is canonical. Guard: the degree-based direction rule catches the common case; LLM `canonical` field provides a second opinion.
- *Neighborhood scope miss:* Duplicates not in the 24h window are not detected. Accepted limitation for v1; full-graph scan is a v2 operation.

**Measurement:**
- Precision proxy: human arbitration acceptance rate on Layer 2 proposals. Target: ≥ 0.70. Below 0.60 → raise threshold.
- Recall proxy: **no easy recall proxy** — would require known ground-truth duplicate pairs. Honest gap. Future proxy: fraction of Claim nodes shared across merged entities (a good merge should increase claim-per-entity density).
- Outcome proxy: Entity node count trend (should decrease or plateau); Claim-per-entity ratio (should increase after good merges).
- CC4 dashboard metrics: `sleep.collapse.proposals.per_cycle`, `sleep.collapse.accepted.per_cycle`, `sleep.collapse.rejected.per_cycle`, `sleep.collapse.auto_accepted_rate`.

---

## Sleep Function B: Disambiguate

**Purpose:** Detect entity nodes that represent two or more distinct real-world concepts and propose splitting them back into separate entities.

**Trigger / cadence:**
- **Primary:** Weekly, on Sunday at 04:00 local (after the current week's collapse cycles have settled).
- **Event-triggered:** Immediately after any `merge_accepted` event where the post-merge entity's intra-cluster variance exceeds 0.4. This catches false merges quickly rather than waiting for Sunday.
- **Manual:** `wintermute sleep disambiguate [--dry-run]`

**Input:**
- All Entity nodes with degree ≥ 5 (enough claims to compute variance meaningfully).
- Filter to those where ≥ 1 of these signals is present:
  1. `intra_claim_variance` > 0.4 — contradictory or highly divergent attribute values across connected Claims.
  2. `merged_at` flag is present AND the entity has acquired contradictory claims since the merge.
  3. Edge-type entropy: the entity's edges split > 60/40 between two entirely disjoint relationship-type clusters.
- **Upstream dependency:** Collapse must have run for this week before disambiguate runs (graph should be in a post-merge stable state).

**Process:**

*Signal computation:*
For each candidate entity, compute:
1. Claim embedding variance: embed all connected Claim text, run k-means with k=2, compute silhouette score. Score > 0.50 → bimodal candidate.
2. Attribute contradiction check: look for Claims with contradictory properties (e.g., two different `date` values that are > 1 year apart, two different `type` classifications, contradictory polarity).
3. Edge-type entropy: compute Shannon entropy of edge-type distribution. High entropy from a bimodal type distribution (not from a genuinely multi-relational hub) is a signal.

Entities not flagged by any signal are skipped. Only flagged entities proceed to LLM step.

*LLM disambiguation:*
For each flagged entity, build a prompt: entity name, all attributes, 10-15 connected Claims grouped by their k-means cluster membership. Ask: "Should this entity be split? If yes: proposed Entity A and Entity B names/descriptions, which claims belong to each, confidence."

Output: `{"split": bool, "confidence": float, "entity_a": {name, description}, "entity_b": {name, description}, "claim_routing": {"a": [claim_ids], "b": [claim_ids]}, "rationale": str}`.

**All split proposals go to human arbitration regardless of confidence.** Splitting is more destructive than merging — it severs accumulated edges and redistributes claims — and the failure mode (splitting a correctly merged entity) is harder to detect than a wrong merge. Starting threshold for even proposing a split to arbitration: confidence ≥ 0.65 (below that, discard).

*Human arbitration:*
Proposals written to `~/.wintermute/arbitration/<date>_disambiguate.yaml`. Each entry includes: entity name, split rationale, proposed A/B names, claim routing preview, confidence. On acceptance: create Entity B node, redistribute Claims per routing, add `split_from: <original_id>` property, emit `split_accepted`. On rejection: emit `split_rejected`.

**Output:**
- Events: `split_proposed {entity_id, confidence, rationale, proposed_a, proposed_b}`, `split_accepted {entity_id, new_entity_id, method: human}`, `split_rejected {entity_id, reason}`.
- Graph mutations: create new Entity node B; redistribute Claims; add `split_from` property.
- Arbitration queue: `~/.wintermute/arbitration/<date>_disambiguate.yaml`.

**Compute budget:**

| Scale | Candidate entities | LLM calls | Input tokens | Cost/cycle |
|---|---|---|---|---|
| 1K nodes | 5-10 | 5-10 | ~8,000 | ~$0.0006 |
| 10K nodes | 30-50 | 30-50 | ~40,000 | ~$0.003 |
| 100K nodes | 150-200 | 150-200 | ~180,000 | ~$0.016 |

Pareto 4-64: High-degree, high-variance entities dominate — typically generic concepts absorbed too many claims during extraction ("machine learning," "federal survey"). Instrument `split_proposed.entity_degree` to verify.

**Failure modes:**
- *False split (most dangerous):* Correctly merged entity split incorrectly, fragmenting valid cross-document connections. Guard: all splits are human-reviewed; the claim routing preview in the YAML makes the consequence visible before acceptance.
- *Silhouette threshold miscalibration:* 0.50 silhouette threshold may produce too many or too few candidates. Needs calibration after first 30 days. Instrument `disambiguate.candidates.flagged_count` vs `disambiguate.proposals.count` to detect threshold drift.
- *Routing error:* LLM routes a Claim to the wrong entity in the split. Guard: human review of the YAML should scan the routing; misrouted high-degree Claims will be obvious.
- *Rollback:* A wrongly accepted split is rolled back by deleting Entity B, re-routing its Claims to the original entity, and emitting a `split_undone` event.

**Measurement:**
- Precision proxy: human acceptance rate on split proposals. Target: ≥ 0.60. Lower than merges because splits are noisier.
- Recall proxy: **no easy recall proxy**. Ground truth would require knowing which merged entities were false merges. Honest gap.
- Outcome proxy: post-split entity claim coherence (within-entity Claim similarity should be higher after a good split than before).
- CC4 metrics: `sleep.split.proposals.per_cycle`, `sleep.split.accepted.per_cycle`, `sleep.split.rejected.per_cycle`.

---

## Sleep Function C: LLM-Proposed Edge Inference

**Naming discipline:** The original spec used "Bayesian-edge inference." That name is rejected.

Belief propagation and Markov logic networks require numeric parameters fit to a probabilistic graphical model — parameters that don't exist in a heterogeneous entity-claim graph of Wintermute's sparsity. "Bayesian" implies a formal posterior update; what we're doing is LLM-generated proposals with confidence scores that approximate a posterior without computing one. Calling it Bayesian would be misleading to anyone who reads the architecture and tries to implement it. The correct name is **LLM-proposed edge inference with human arbitration.** This spec uses that name consistently.

**Purpose:** Propose direct relationships between entity pairs that are meaningfully connected (via shared evidence, shared neighbors, or embedding proximity) but don't yet have an explicit edge.

**Trigger / cadence:**
- **Primary:** Weekly, on Sunday at 05:00 local — AFTER collapse and disambiguate for that cycle have completed. This is a hard dependency: proposing edges on about-to-be-merged or about-to-be-split entities generates proposals against invalid entity configurations.
- **Manual:** `wintermute sleep infer-edges [--dry-run]`

**Input:**
- **Candidate pair generation** — entity pairs meeting ALL of:
  1. No existing direct edge between them.
  2. Shared-neighbor count ≥ 2 (both connect to ≥ 2 of the same Claim or Document nodes).
  3. Embedding cosine similarity ≥ 0.60 (permissive; LLM filters).
  4. OR: both entities appeared in the same source Document with no extracted relationship between them.
- **Scope cap:** Top-K candidate pairs by shared-neighbor count. K scales logarithmically: K=200 at 1K-node scale, K=500 at 10K-node scale, K=1,000 at 100K-node scale. Prevents runaway compute on dense graph regions.
- **Upstream dependency:** Collapse and disambiguate events for this week must be in `completed` or `skipped` state.

**Process:**

*Candidate pair generation:*
Graph query: `MATCH (a:Entity)-[:APPEARS_IN|SUPPORTS]->(shared)<-[:APPEARS_IN|SUPPORTS]-(b:Entity) WHERE id(a) < id(b) AND NOT EXISTS {(a)-[]-(b)} WITH a, b, count(shared) AS shared_count WHERE shared_count >= 2 RETURN a, b, shared_count ORDER BY shared_count DESC LIMIT K`

*LLM edge proposal:*
Batch 10 pairs per call. Prompt: entity A name/description + 5 key claims; entity B name/description + 5 key claims; shared neighbors; any existing indirect path between them (up to 3 hops). Ask: "Should there be a direct relationship? If yes: edge type from {RELATES_TO, EXTENDS, CONTRADICTS, SUPPORTS, IS_INSTANCE_OF, PART_OF, PRECEDES, FOLLOWS}, direction, confidence, rationale."

Output: `{"has_edge": bool, "edge_type": str, "direction": "A_to_B|B_to_A|bidirectional", "confidence": float, "rationale": str}`.

- Confidence ≥ 0.90: auto-accept. Emit `edge_accepted` with `method: llm_auto`. Create edge in graph.
- Confidence 0.60-0.89: add to arbitration queue. Emit `edge_proposed`.
- Confidence < 0.60: discard. No event.

**Auto-accept threshold: 0.90. Starting point. Tunable after 30-day calibration.** Edge types are constrained to Wintermute's ontology vocabulary in the prompt; the LLM cannot invent edge types.

*Human arbitration:*
Items written to `~/.wintermute/arbitration/<date>_edges.yaml`. Each entry: entity pair names; proposed edge type and direction; rationale; confidence; shared-neighbor context. User reviews with `wintermute arbitrate` or direct YAML edit.

**Output:**
- Events: `edge_proposed {entity_a, entity_b, edge_type, direction, confidence, rationale}`, `edge_accepted {entity_a, entity_b, edge_type, direction, method}`, `edge_rejected {entity_a, entity_b, reason}`.
- Graph mutations: CREATE edge of type and direction specified.
- Arbitration queue: `~/.wintermute/arbitration/<date>_edges.yaml`.

**Compute budget:**

| Scale | Candidate pairs (K) | LLM batches | Input tokens | Output tokens | Cost/cycle |
|---|---|---|---|---|---|
| 1K nodes | 200 | 20 | ~22,000 | ~4,000 | ~$0.003 |
| 10K nodes | 500 | 50 | ~55,000 | ~10,000 | ~$0.007 |
| 100K nodes | 1,000 | 100 | ~110,000 | ~20,000 | ~$0.014 |

Pareto 4-64: Hub entities (the 4% with degree ≥ 20) generate ~64% of candidate pairs. Edge inference for hubs is high-value (they're the well-documented entities); edge inference for low-degree entities is high-noise. Consider filtering to pairs where at least one entity has degree ≥ 3 as a noise reduction.

**Failure modes:**
- *Confabulated edges:* LLM proposes a relationship with no real-world basis. Guard: constrained edge type vocabulary; auto-accept threshold of 0.90 limits the blast radius; human review of the 0.60-0.89 band catches systematic errors.
- *Directional errors:* Edge proposed A→B when B→A is correct. Guard: human arbitration YAML previews include direction; the `direction` field is explicit.
- *Edge type hallucination:* Prompt constrains types to the ontology vocabulary. If LLM returns an out-of-vocabulary type, the collector rejects the proposal and emits a warning event.
- *Stale candidates:* A candidate pair was generated before a concurrent merge resolved one of the entities. Guard: filter candidate pairs against the current tombstone list before LLM calls.

**Measurement:**
- Precision proxy: human acceptance rate on edge proposals. Target: ≥ 0.65.
- Recall proxy: **no recall proxy without ground truth.** Honest gap. Future proxy: query retrieval improvement (do relevant entities now have shorter graph paths between them?).
- Outcome proxy: average shortest path length between semantically related entity clusters (should decrease as correct edges are added).
- CC4 metrics: `sleep.edge.proposals.per_cycle`, `sleep.edge.accepted.per_cycle`, `sleep.edge.rejected.per_cycle`, `sleep.edge.auto_accepted_rate`.

---

## Cross-Cutting Concerns

### Ordering and interaction

**Required execution order:** Collapse → Disambiguate → LLM-Proposed Edge Inference.

Rationale: collapse must run first to reduce entity count and remove noise (proposing edges on duplicate entities wastes calls and produces duplicate edges). Disambiguate should run after collapse to catch any false merges from the collapse cycle. Edge inference must run last because it operates on the entity space that collapse and disambiguate have finalized — any entity pair that edge inference touches should be stable.

**Interaction risk:** If collapse merges entities A+B at 03:30, and the edge inference queue from a prior cycle contains a proposal for A↔C and B↔C separately, those proposals are stale. Guard: the edge inference step filters its candidate list against the current tombstone index before submitting LLM calls. Any candidate referencing a tombstoned entity is dropped.

**Schedule discipline:** Collapse runs nightly (M/W/F minimum); Disambiguate and Edge Inference run weekly (Sunday). Do not run Disambiguate or Edge Inference on the same night as a fresh Collapse cycle. The entity space needs at least 12 hours to stabilize after a collapse cycle before split detection is meaningful.

### Event sourcing discipline

Every sleep-function mutation is an event in the Wintermute event log (JSONL append-only, matching Seldon's pattern). No graph mutation occurs without a corresponding event.

**Event types:**
- `merge_proposed`, `merge_accepted`, `merge_rejected`, `merge_undone`
- `split_proposed`, `split_accepted`, `split_rejected`, `split_undone`
- `edge_proposed`, `edge_accepted`, `edge_rejected`, `edge_undone`
- `sleep.skipped {function, reason}` — when a sleep function skips due to dependency not met
- `sleep.cycle_complete {function, duration_s, proposals, accepted, rejected, cost_usd}`

**Full replay contract:** Given the event log and the original ingested document set, the graph state at any point in time should be fully reconstructible by replaying events in timestamp order. The tombstone pattern (absorbed entities are marked, not deleted) is essential to this — deletion would break replay.

**Audit trail:** Each event records: `function` (collapse/disambiguate/edge), `method` (deterministic/llm_auto/human), `confidence`, `model_used`, `cycle_id` (ISO timestamp of the sleep cycle that generated the proposal).

### Human arbitration workflow

**Queue location:** `~/.wintermute/arbitration/` with files named `<YYYY-MM-DD>_<function>.yaml`. One file per sleep function per night. Files accumulate; the user can work through them asynchronously.

**Review interface:** `wintermute arbitrate` — CLI command that opens each pending file, renders it in a human-readable format (entity names, rationale, confidence), and accepts Y/N/skip per item. Alternatively, the user can edit the YAML file directly (each proposal has an `action: null | accept | reject` field) and run `wintermute arbitrate --apply` to process the YAML into graph mutations.

**SLA assumption:** The queue is unbounded. The system does not auto-accept aged items (that would defeat the purpose of the arbitration queue). However: items in the queue that are older than 30 days AND have confidence ≥ 0.85 will be escalated in `seldon briefing` output ("N proposals older than 30 days with confidence ≥ 0.85 — consider accepting or explicitly rejecting"). No forced auto-accept.

**Queue size pressure:** If the arbitration queue exceeds 100 items, the next sleep cycle lowers its Layer 2 confidence band to reduce new proposals (raise the threshold for queuing from 0.50 to 0.70). This is a self-regulating valve to prevent queue overflow from overwhelming the user.

### Single-point-of-failure resistance

**V1 (this spec):** All sleep-function LLM calls route through Gemini Flash via the k-dense-byok pattern (LiteLLM proxy, `gemini-flash` alias). Single-model dependency. This is a known SPOF.

**Where the SPOF matters most:** Auto-accept decisions (confidence ≥ 0.90) are made by one model. If Gemini Flash has a systematic bias (over-confidence on certain entity types, underconfidence on others), v1 will silently miscalibrate the auto-accept threshold. Guard: monitor `sleep.*.auto_accepted_rate` in the CC4 dashboard. Rate outside 0.20-0.60 range suggests threshold miscalibration.

**V2 requirement (explicitly deferred):** Route LLM proposals through an ensemble of ≥ 2 providers (Gemini Flash + a second provider via LiteLLM; Claude Haiku is the obvious second). A proposal auto-accepts only if both models agree with confidence ≥ 0.85. Cost roughly doubles; false-positive rate drops substantially. The k-dense-byok LiteLLM config pattern (CC1 Q3) is the reference implementation for this.

---

## Dashboard Integration

The CC4 Q-a curation-rate panel is currently a stub. The following metrics unblock it once sleep functions are implemented. The CC4 collector (`scripts/observability_collect.py`) should read the Wintermute event log to compute these.

| Metric name | Type | Definition | Threshold for attention |
|---|---|---|---|
| `sleep.collapse.proposals.per_cycle` | Counter | Layer 2 merge proposals generated per collapse run | < 5 for 3 consecutive nights → possible ingestion stall |
| `sleep.collapse.accepted.per_cycle` | Counter | Merges accepted (llm_auto + human) per collapse run | — |
| `sleep.collapse.rejected.per_cycle` | Counter | Merges rejected (human) per collapse run | > 40% of proposals rejected → lower confidence threshold |
| `sleep.collapse.auto_accepted_rate` | Fraction | `llm_auto` accepts / total accepted | Outside 0.20–0.60 → threshold miscalibration |
| `sleep.split.proposals.per_cycle` | Counter | Split proposals generated per disambiguate run | > 20 per week → aggressive merge threshold, review |
| `sleep.split.accepted.per_cycle` | Counter | Splits accepted (human) per disambiguate run | — |
| `sleep.split.rejected.per_cycle` | Counter | Splits rejected (human) per disambiguate run | > 60% rejected → signal threshold too low |
| `sleep.edge.proposals.per_cycle` | Counter | Edge proposals generated per inference run | — |
| `sleep.edge.accepted.per_cycle` | Counter | Edges accepted (llm_auto + human) per inference run | — |
| `sleep.edge.rejected.per_cycle` | Counter | Edges rejected (human) per inference run | > 35% rejected → lower confidence band |
| `sleep.edge.auto_accepted_rate` | Fraction | `llm_auto` accepts / total accepted | Outside 0.20–0.60 → threshold miscalibration |
| `sleep.arbitration_queue.size` | Gauge | Total pending proposals across all functions | > 100 → queue pressure valve activates |
| `sleep.arbitration_queue.oldest_pending_days` | Gauge | Age of oldest unreviewed proposal | > 30 → surface in `seldon briefing` |
| `sleep.compute.llm_calls.per_cycle` | Counter | Total LLM API calls per sleep run (all functions) | > 200 at 10K-node scale → scope leak |
| `sleep.compute.cost_usd.per_cycle` | Gauge | Estimated cost at Gemini Flash pricing | > $0.05 per cycle → abnormal, investigate |

These metrics feed directly into the CC4 Q-a curation panel that currently shows a stub. Once sleep functions emit events to the Wintermute event log, the CC4 collector can read them and the dashboard's curation rate panel comes alive.

---

## AD-023 Draft

### AD-023 Draft: Wintermute Sleep Functions as Architectural Center

**Status:** Proposed, 2026-04-18.

**Context:** The CC1 literature survey (Q4) established that claude-mem solves commodity capture (five lifecycle hooks, CLAIM-CONFIRM queue, hybrid search, AGPL production grade) better than Wintermute v1 ever did. The CC2 infrastructure audit found Wintermute's `wintermute-intake` graph has 7,660 nodes but no quality measurement, no entity resolution, and no relationship inference. ClaudeClaw runs 16 autonomous jobs producing content into this graph with no verification that any of it is useful. The critical question for Phase C is: what does Wintermute offer that commodity capture doesn't? This AD answers that question and commits to the answer.

**Decision:** Wintermute's architectural center is the sleep-function layer: offline graph cognition that runs asynchronously, operates on the accumulated graph with whole-graph visibility, and improves graph fidelity over time without user intervention at ingestion time. Three sleep functions define this layer: Collapse/Dedup (entity resolution), Disambiguate (entity split detection), and LLM-Proposed Edge Inference. Every Wintermute engineering investment should serve these functions or the infrastructure that makes them possible (ingestion pipeline that generates raw entity/claim/document nodes for sleep functions to work on; observability that reveals when sleep functions are producing useful signal).

Commodity capture (the hook layer that records tool calls, session observations, and cross-session context) is deliberately NOT in Wintermute's core unless the claude-mem adopt option (CC1 Q4 Option A) is selected. If adopted, claude-mem handles capture; Wintermute owns the sleep layer above it. If extracted (Option B), Wintermute also owns capture; but the sleep layer remains the primary source of value. Either way, sleep functions are the thing that justifies maintaining Wintermute as a separate system.

**Consequences:**

Positive:
- Clarifies the build roadmap: every engineering decision is evaluated against "does this help sleep functions run better?" 
- Positions Wintermute uniquely in the ecosystem — no other tool in the CC1 survey does offline graph cognition at this level.
- Makes the kill/keep decision crisp: if sleep functions aren't implemented, Wintermute should be deprecated in favor of claude-mem.
- Provides a measurement criterion: sleep function precision and recall (even imperfect proxies) tell us whether Wintermute is improving the graph.

Negative / cost:
- Narrows Wintermute's scope deliberately. Features outside the sleep-function center (a search API, a retrieval endpoint, a chat interface) become second-class unless they serve sleep function quality.
- Sleep functions require a running, high-quality entity/claim/document graph to operate on — if ingestion quality is poor (noisy entities, garbage claims), sleep functions amplify the noise rather than resolving it. Garbage-in / garbage-out applies.
- Human arbitration is a UX burden. If the queue grows faster than Brock can review it, the sleep functions stall. The self-regulating valve (raise threshold when queue > 100) is a mitigation, not a solution.

Reversibility: High. The decision commits to a prioritization, not to an implementation. If three months of sleep-function operation shows no quality improvement (precision proxies stay low, rejection rates stay high), the AD can be amended to deprioritize sleep functions or defer them indefinitely. The event-sourced graph means any sleep-function mutations can be rolled back.

**Relation to prior ADs:**
- **AD-001 (ANTS → Seldon):** Extends the event-sourced append-only pattern (established for Seldon) into Wintermute. Sleep functions emit events to a Wintermute event log with the same schema.
- **AD-017 (Central Ontology):** Sleep functions operate on ontology-aligned entities. The edge type vocabulary for LLM-proposed edge inference is constrained to the Wintermute entity relationship ontology, not invented per-proposal.
- **AD-019/020 (Audit pipeline):** Same authority model — AI proposes, human arbitrates. The sleep-function arbitration queue is structurally identical to AD-019's Issue routing. The CC5 spec is a second implementation of the same pattern at the graph-curation layer.
- **AD-022 (CLI-default, if drafted):** Arbitration is CLI-driven (`wintermute arbitrate`). If AD-022 formalizes the CLI-first principle, sleep-function arbitration is its primary implementation.
- **AD-024 (Observability, if drafted):** Sleep functions are the highest-signal thing Wintermute does. The 15-metric table in CC5 §Dashboard Integration is the seed for AD-024's observability requirements.

**Open questions explicitly deferred:**
- Whether to adopt claude-mem (Option A) or extract hook patterns into Wintermute (Option B). This AD is agnostic; it describes where sleep functions sit relative to capture without committing to the capture architecture.
- Ensemble multi-provider LLM dispatch for sleep functions. Named as a v2 requirement; this AD does not specify when v2 begins.
- Whether the weekly Disambiguate and Edge Inference cadences are correct. Starting values; calibrate after 30 days of operation.
- Full-graph sleep-function runs (v1 scopes to recent neighborhood only). This AD does not commit to full-graph scans.
- The specific embedding model used for signal computation in Disambiguate (silhouette scoring). Operational detail left to implementation.

---

## Honest Unknowns

1. **Embedding quality for signal computation.** Sleep Function B's bimodality signal depends on Claim embeddings. The quality of entity-level signals (silhouette score, cluster separation) depends entirely on how well the embedding model represents the claim text. We don't know which embedding model ClaudeClaw uses for the Wintermute graph, or whether it's consistent. This needs to be resolved before Disambiguate can be implemented.

2. **Ingestion entity quality.** Sleep functions operate on entities produced by `knowledge_graph_extract`. The quality of those entities (are they coherent concepts? or arbitrary noun phrases?) determines whether collapse has anything meaningful to merge. The CC2 audit found no timestamps on `wintermute-intake` nodes, so the quality of recent extractions vs. older ones is unknown.

3. **Correct arbitration UX.** The YAML-based review workflow (inherited from sift-kg) is a design assumption. It may be too friction-heavy for daily operation, or it may be fine. This needs one real cycle of operation to evaluate.

4. **Self-regulation valve calibration.** The "raise threshold when queue > 100" valve is a heuristic. The right threshold depends on how fast proposals arrive vs. how fast Brock can review. Unknown without operational data.

5. **Edge type ontology completeness.** The LLM-proposed edge inference step constrains proposals to Wintermute's defined relationship types. The spec lists example types (RELATES_TO, EXTENDS, CONTRADICTS, etc.) but the actual Wintermute entity ontology hasn't been audited for completeness. A constrained vocabulary with missing types will cause the LLM to force-fit proposals into wrong categories.

---

## Questions for Brock

1. **Wintermute edge type ontology:** What relationship types are currently defined for entity-to-entity edges in the Wintermute schema? The LLM-proposed edge inference vocabulary needs to be constrained to these. If no formal ontology exists, defining it is a prerequisite for Sleep Function C.

2. **ClaudeClaw `knowledge_graph_extract` output quality:** Are the entities extracted by ClaudeClaw coherent named concepts, or noun-phrase fragments? A quick sample of 20 Entity nodes from `wintermute-intake` would tell us whether Sleep Function A has real duplicates to merge or whether the signal is noise.

3. **Cadence preferences:** The spec proposes nightly Collapse + weekly Disambiguate/Edge. Is nightly Collapse too aggressive for the current ingestion rate (~50 entities/day), or does it need to be nightly to keep the graph fresh? Would a Mon/Wed/Fri cadence be better?

4. **AGPL and claude-mem decision:** This spec is written to work under either adopt (Option A) or extract (Option B). But the arbitration workflow and hook architecture differ depending on the answer. When does Phase C make the call?

5. **Arbitration queue tolerance:** How many pending proposals per week is tolerable before it becomes a burden? If the answer is "more than 10 feels like homework," the auto-accept thresholds need to be higher (0.92+) and the proposal generation needs tighter candidate filtering.
