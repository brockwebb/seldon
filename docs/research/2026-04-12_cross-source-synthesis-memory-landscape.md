# Cross-Source Synthesis: Agent Memory Landscape — Seldon Paper Positioning

**Date:** 2026-04-12
**Author:** Claude (Desktop session, research review)
**Sources reviewed:**
- `llm-memory-unsolved-seldon-notes.md` — LangChain/Rosebud problem statement
- `llm-memory-taxonomy-rosebud-seldon-notes.md` — Rosebud 9-axis taxonomy + comparison table
- `lestat-20260412-170403-544de5-notes.md` — (S)AGE consensus-validated memory
- `lestat-20260412-115837-2e887a-notes.md` — Claude Code internal architecture

---

## 1. What the Existing Notes Get Right

The CC notes correctly identify:
- The 9 axes as validity audit points (not just design choices)
- Derivation drift as a T1 reliability threat
- Confidence without provenance as a T3 construct validity threat
- Memory-induced bias as a T2 internal validity threat
- (S)AGE's consensus mechanism as one answer to the write-authority problem

This framing is solid and should carry forward into the Seldon paper.

---

## 2. What the Notes Miss

### 2.1 The Raw/Derived Spectrum Is Too Binary

The Rosebud piece frames raw vs. derived as a spectrum. The existing notes accept this framing uncritically. But the interesting systems — including Seldon — aren't picking a position on a line. They maintain **multiple representations simultaneously with explicit provenance between layers**.

Seldon's architecture is: event-sourced JSONL (raw) → graph projection (derived), where the derived layer is always rebuildable from the raw layer. This isn't a tradeoff — it's a structural relationship that eliminates derivation drift by design. The graph is a view, not a copy. If the view drifts, replay the events.

**For the paper:** Position this as a third option beyond raw and derived: **projectable state**. The derived representation is not an independent artifact that can drift — it's a deterministic function of the raw log. This is the event-sourcing pattern from distributed systems applied to agent memory, and it structurally eliminates the "photocopy of a photocopy" degradation the Rosebud piece identifies as fundamental.

### 2.2 The Evaluation Paradox Has a Partial Solution the Notes Don't Name

The Rosebud piece says ground truth for memory evaluation exceeds any context window. The notes map this to Seldon's meta-evaluation problem but don't offer a solution.

SFV (State Fidelity Validity) IS the partial solution. You don't need to evaluate the entire memory corpus at once. You need to evaluate whether the **current derived state** faithfully represents the **accumulated raw events**. That's a local property — you can check it incrementally, at each derivation step, without holding the entire history in context.

SFV asks: "has the state drifted from the events that produced it?" This is checkable by replaying a subset of events and comparing the resulting state against the current state. It's statistical sampling applied to provenance verification.

**For the paper:** The evaluation paradox is real for systems that lose their raw source. It's solvable for systems that preserve it. Seldon preserves it. SFV is the measurement framework.

### 2.3 (S)AGE Solves a Problem Seldon Doesn't Have (and Vice Versa)

The (S)AGE note correctly identifies the consensus mechanism but doesn't sharpen the contrast enough.

The threat models are fundamentally different:

| Dimension | (S)AGE | Seldon |
|-----------|--------|--------|
| **Threat model** | Adversarial agents (Byzantine faults) | Information loss and drift (entropy) |
| **Trust boundary** | Between agents (multi-party) | Between sessions (temporal) |
| **Write authority** | Consensus quorum (social proof) | Risk-stratified single-operator (provenance proof) |
| **Integrity mechanism** | BFT consensus + hash-linked ledger | Event sourcing + graph projection |
| **What "valid" means** | "Multiple agents agree this is true" | "This claim traces to verifiable source through an unbroken chain" |

(S)AGE's validity is **social** — truth is what the quorum agrees on. Seldon's validity is **evidentiary** — truth is what the provenance chain supports. These are complementary, not competing. A multi-agent research system might want both: Seldon for per-agent provenance, (S)AGE for cross-agent consensus.

**For the paper:** Position these as addressing orthogonal validity threats. (S)AGE handles T4 (external validity in multi-agent settings — can you trust claims from agents you don't control?). Seldon handles T1-T3 (statistical conclusion, internal, and construct validity within a single operator's research pipeline).

### 2.4 Claude Code's Architecture Reveals the Production Reality

The Claude Code internals note is treated as a standalone curiosity. It's actually evidence for Seldon's design thesis.

Key observations:
- **Compaction at ~13K tokens** confirms the context pressure problem is real and current, not theoretical
- **KAIROS_DREAM (orient → gather → consolidate → prune)** is exactly the async derivation pattern the Rosebud piece describes, implemented at production scale inside Anthropic's own tooling
- **Adversarial verification (independent sub-agent, no self-PASS)** is a production implementation of the "curator conflict" the notes identify — Anthropic solved it by splitting the curator role
- **MEMORY.md at 200 lines / 25KB** is a hard constraint that forces lossy compression — this IS the derivation drift problem, built into the product

**For the paper:** Claude Code's own architecture is a case study in the tradeoffs the Rosebud taxonomy describes. The compaction-to-dream pipeline is a concrete instance of the raw→derived→forgetting chain. Seldon's event sourcing avoids the compaction information loss by never discarding the raw log.

### 2.5 The Forgetting Problem Maps to Seldon's State Machines

The notes correctly identify forgetting as provenance-threatening but don't connect it to Seldon's existing solution.

Seldon doesn't "forget" — it transitions state. An artifact moves from `verified` to `stale` to `deprecated`. The artifact still exists in the graph with full history. Its state communicates "don't rely on this" without destroying the evidence chain. Staleness propagates via graph edges: if an upstream result changes, all downstream citations get flagged.

This is structurally different from every system in the Rosebud comparison table. None of them have state machines on their memory artifacts. They either append forever, overwrite, or decay. Seldon's state transitions are a fourth pattern: **supervised deprecation with preserved provenance**.

**For the paper:** Introduce "supervised deprecation" as a forgetting strategy distinct from the three the Rosebud piece identifies (append-only, overwrite, decay). The key property: the system communicates that knowledge has been superseded without destroying the evidence that it once existed.

---

## 3. Seldon's Position on the 9-Axis Map

For the paper, Seldon should be mappable onto the Rosebud taxonomy:

| Axis | Seldon's Position |
|------|-------------------|
| **What gets stored** | Raw (event-sourced JSONL) + derived (typed graph artifacts). Explicit provenance links between layers. |
| **When derivation happens** | On-demand graph projection from event replay. No async "dreams" — the graph IS the derivation, rebuilt deterministically. |
| **Write trigger** | Explicit CLI commands (not LLM-as-curator). Every write is a deliberate act, not an inference. |
| **Storage backend** | JSONL (event log, source of truth) + NetworkX (graph projection) + Neo4j (optional, for complex queries). |
| **Retrieval** | Graph traversal (provenance chains, dependency queries, blast radius). NOT semantic similarity. |
| **Post-retrieval** | State-machine filtering (only surface artifacts in valid states). Risk scoring. |
| **Retrieval timing** | Session briefing (hook-driven at session start) + CLI-driven (tool-driven during session). |
| **Curator** | Human operator (write authority) + risk-stratified AI (propose authority). Never self-curating. |
| **Forgetting** | State-machine deprecation with preserved provenance. Staleness propagation via graph edges. Never hard-delete. |

**Key differentiator:** Seldon is the only system on this map where the derived representation is a deterministic function of the raw log. Every other system's derived state can drift independently. Seldon's can't — by construction.

---

## 4. Papers to Track Down

From this research sweep, additional sources worth acquiring:

1. **Hindsight (arXiv 2512.12818)** — "Building Agent Memory that Retains, Recalls, and Reflects." Four logical networks distinguishing world facts, agent experiences, entity summaries, evolving beliefs. Closest to Seldon's typed-artifact model in the academic literature.

2. **"From Storage to Experience" survey (Preprints.org 202601.0618)** — Evolutionary framework for LLM agent memory: Storage → Reflection → Experience. The three-stage model may map to Seldon's event → artifact → validity pipeline.

3. **A-Mem (arXiv 2502.12110)** — "Agentic Memory for LLM Agents." Self-organizing memory that the agent actively manages. Contrast with Seldon's externally-governed model.

4. **ACM TOIS survey on LLM agent memory mechanisms (10.1145/3748302)** — Comprehensive survey. Check for coverage of provenance-preserving approaches.

5. **(S)AGE Paper 1-4** — The four papers in the `papers/` directory of the l33tdawg/sage repo. Paper 2 (controlled empirical study, 50-vs-50) and Paper 4 (longitudinal learning) are most relevant for Seldon's empirical validation design.

---

## 5. Seldon Paper Outline Implications

This research sweep suggests the related work section should organize around:

1. **Consumer memory systems** (ChatGPT, Claude, Rosebud) — the raw/derived tradeoff and why it's insufficient for research
2. **Consensus-validated memory** ((S)AGE, BlockAgents) — social validity, orthogonal to evidentiary validity
3. **Structured agent memory** (Hindsight, A-Mem, MemPalace) — typed representations, closest to Seldon but without event sourcing
4. **The evaluation gap** — SFV as the missing measurement framework that none of these systems provide

The thesis: existing agent memory systems optimize for retrieval quality (finding the right memory at the right time). Seldon optimizes for **validity preservation** (ensuring that whatever is found is trustworthy, traceable, and falsifiable). These are different problems, and the research literature has focused almost exclusively on the first while ignoring the second.
