# LLM Memory Taxonomy & Design Space — Seldon Implications

**Source:** https://rosebudjournal.notion.site/Everything-you-need-to-know-about-LLM-memory-33b328e8e3f780858d3df3acb06d23b9
**Author:** Rosebud Journal
**Cross-reference:** `llm-memory-unsolved-seldon-notes.md` (same author, earlier version without comparison table)

---

## Why This Matters for Seldon

This is the most complete taxonomy of LLM memory system design currently published. The 9-axis framework + 8-system comparison table gives Seldon a concrete evaluation instrument for assessing any agent-with-memory system's validity properties.

The earlier article (already in Seldon research) laid out the problem. This one lays out the **full design space and maps real systems onto it**.

---

## The 9 Axes as Seldon Validity Audit Points

Each axis is a point where validity can be preserved or destroyed:

### 1. What Gets Stored — Provenance Depth

| Storage choice | Validity implication |
|----------------|---------------------|
| Raw only | Maximum provenance, minimum interpretation. Claims are traceable but unstructured. |
| Derived only | Compact, actionable — but every derivation is a lossy transformation. Provenance degrades with each step. |
| Hybrid (raw + derived) | Best of both IF the link from derived → raw is maintained. Without that link, derived artifacts become unfalsifiable. |

**Seldon rule:** Any memory assertion used as evidence must be traceable to raw source within N derivation steps. N should be tracked as a validity metadata field.

### 2. When Derivation Happens — Error Injection Timing

Synchronous derivation means errors enter the record in real-time and may influence the same conversation. Async derivation (nightly "dreams") means errors accumulate offline and appear as surprises in the next session.

**Seldon rule:** Derivation timing should be logged. If an agent's conclusion depends on a memory that was derived asynchronously, the derivation timestamp and inputs should be auditable.

### 3. Write Triggers — Selection Bias in the Record

"LLM-as-curator" is the most common trigger and the most validity-threatening. The model decides what's worth remembering — which means the model's biases shape the historical record. This is a **T2 (internal validity) threat**: the measurement instrument is contaminating the data.

**Seldon rule:** Write trigger mechanism should be declared. Self-curated memory should carry lower validity weight than user-triggered or write-everything systems.

### 4. Storage Backend — Audit Capability

Graph DBs support provenance queries natively (traverse from claim → source). Vector DBs do not — similarity search finds related things, not source things. Filesystem preserves full content but requires external indexing for provenance chains.

**Seldon rule:** The storage backend determines what kinds of validity audits are possible. If the backend can't answer "where did this fact come from?", validity claims based on that memory are weak.

### 5. Retrieval — Systematic Evidence Exclusion

The **selective retrieval bias** failure mode is the most dangerous for validity: relevant evidence stored under a different topic or framing is invisible to the retrieval system. This is a form of **sampling bias** — the agent's reasoning is based on a non-representative subset of its own knowledge.

**Seldon rule:** For high-stakes conclusions, retrieval should be tested for completeness, not just relevance. Run the query multiple ways. Check what was NOT retrieved.

### 6. Post-Retrieval Processing — Confirmation Bias Risk

Re-ranking and LLM-based narrowing can systematically prefer evidence that confirms the current framing. "Which of these are relevant to the current turn?" is a leading question.

**Seldon rule:** Post-retrieval narrowing criteria should be logged and auditable.

### 7. Retrieval Timing — Evidence Availability Bias

| Mode | Validity risk |
|------|--------------|
| Always injected | Context pollution — irrelevant history biases reasoning (T2) |
| Hook-driven | Harness decides what evidence is available — opaque selection (T2) |
| Tool-driven | Model doesn't know what it doesn't know — evidence gaps are invisible (T3) |

No mode is clean. Each introduces a different kind of evidence availability bias.

### 8. Curator Identity — Conflict of Interest

When the main model curates its own memory, it has a structural conflict of interest: it's both the analyst and the archivist. Self-curated memory tends toward self-consistency, not accuracy. The model remembers what fits its current understanding, not what challenges it.

**Seldon rule:** Self-curated memory should be flagged. External curation (user, separate model, harness) provides higher validity guarantees.

### 9. Forgetting — Irrecoverable Evidence Destruction

The article's key insight on forgetting: **deleting raw turns doesn't delete derived summaries**. The graph facts, the inferences, the self-directed prompts — all persist as orphaned assertions with no backing evidence.

**Seldon rule:** Forgetting must be provenance-aware. If raw source is deleted, all derived artifacts that cite it must be flagged as "source deleted — validity unverifiable."

---

## The Comparison Table as Evaluation Instrument

The 8-system comparison maps real products onto the 9 axes. For Seldon, this is actionable:

**Highest validity potential:** Lossless Claw (raw never deleted, compacted summaries expand back to source) and MemPalace (temporal validity windows on knowledge graph facts — facts have start/end dates).

**Lowest validity potential:** ChatGPT Memory (derived only, cheap model extraction, no provenance chain, append-only forgetting with user deletion but no cascade).

**Wintermute's current position:** Closest to QMD/OpenClaw hybrid — raw markdown files with frontmatter, LLM-as-curator writes, MCP-driven retrieval. The knowledge graph extraction is a derivation step. The staging pipeline preserves raw source.

**What Wintermute should adopt from MemPalace:** Temporal validity windows on knowledge graph facts. Facts should have `valid_from` and `valid_until` dates so Seldon can assess temporal relevance.

---

## Key Patterns for Seldon's Validity Vocabulary

New terms this article motivates:

| Term | Definition |
|------|-----------|
| **Derivation depth** | Number of transformation steps between a memory assertion and its raw source |
| **Provenance chain** | Traceable link from derived artifact → derivation step → raw source |
| **Curator conflict** | When the entity making memory decisions is the same entity whose reasoning depends on that memory |
| **Orphaned assertion** | A derived fact whose raw source has been deleted or is no longer verifiable |
| **Selective retrieval bias** | Systematic exclusion of relevant evidence due to framing-dependent retrieval |
| **Temporal validity window** | Time range during which a memory fact is considered valid (MemPalace pattern) |
| **Forgetting cascade** | Propagation of deletion from raw source through all derived artifacts that cite it |

---

## Related Notes
- `llm-memory-unsolved-seldon-notes.md` — same author's earlier framing (problem statement + 9 axes + failure modes, no comparison table)
- `lestat-20260412-170403-544de5-notes.md` — SAGE consensus-validated memory (one answer to the provenance problem)
