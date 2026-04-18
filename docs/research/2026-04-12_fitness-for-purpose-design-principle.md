# Design Principle: Fitness for Purpose, Not Perfection

**Date:** 2026-04-12
**Author:** Brock (captured from voice), Claude (structured)
**Context:** Reaction to proposed drift-measurement experiment (100 ingests through LLM wiki, measure derivation drift vs. Seldon replay). Rejected as yak-shaving. Refined through subsequent discussion about graph superiority for the same function.

---

## The Principle

The value of provenance infrastructure depends on **what the output is used for**, not on whether it achieves theoretical perfection.

Two regimes exist:

| Regime | What matters | Provenance requirement |
|--------|-------------|----------------------|
| **Personal knowledge work** | Does querying the system produce useful results that support my thinking? | Low. If extraction wording differs slightly but conclusions are the same, it doesn't matter. "Close enough" is good enough. |
| **Evidentiary output** | Can I demonstrate the chain from claim → source? Can a reviewer or auditor trace every number? | High. The evidence chain, the provenance, and the ability to demonstrate everything becomes important. Official statistics, federal research, peer-reviewed papers. |

However — and this is the correction to the earlier framing — **the two-regime distinction does not mean Seldon is only for regime 2.** Seldon serves the same long-term memory function as flat wiki systems. It just does it better, with provenance and traceability as structural bonuses that come for free.

---

## The Stronger Argument: Same Function, Better Structure

The earlier framing conceded too much. It positioned Seldon as "different purpose" — provenance for evidentiary work, flat wikis for personal knowledge. The sharper position:

**Seldon provides the same long-term memory function the flat-file systems are trying to provide.** It stores knowledge, retrieves it, maintains it across sessions, and gets richer over time. But it does it on a graph, which is a structurally superior representation for knowledge — and this is not a new claim. It's the entire reason knowledge graphs exist as a field.

Knowledge graphs are known to be better structures for storing knowledge. This is established. They support operations that flat files simply cannot do efficiently:

| Operation | Flat files (Obsidian/wiki) | Knowledge graph (Seldon) |
|-----------|---------------------------|--------------------------|
| "What do I know about X?" | Grep/search across files | Node lookup + neighbor traversal |
| "What depends on X?" | Manual link-following, hope you find everything | Graph query: all downstream edges |
| "If X changes, what breaks?" | Unknown. No structural way to answer. | Blast radius query: transitive closure |
| "Where did this claim come from?" | Scroll through chat history | Provenance chain traversal |
| "What's stale?" | Weekly LLM lint pass (heuristic, unreliable) | State machine transitions propagated via edges |
| "Show me the relationship between X and Y" | Hope they're linked in the same page | Path query between typed nodes |

Provenance and traceability aren't the primary selling point — they're **structural properties that emerge from using the right data structure.** You don't add provenance to a graph. You get provenance because it's a graph.

---

## Why Knowledge Graphs Were "Too Hard" (Until Now)

The historical barrier to knowledge graphs was creation and maintenance cost. Building a graph manually is expensive. Keeping it accurate is expensive. The human effort required made graphs impractical for most personal and small-team use cases.

This is the barrier AI tools remove. The LLM handles:
- Entity and relationship extraction from source material
- Graph updates when new information arrives
- Consistency checking (the "sleep" functions — pruning, tuning, cleaning)
- Query synthesis across graph structure

The mechanical advantage of AI tooling collapses the creation barrier. The graph operations (traversal, blast radius, provenance chains, staleness propagation) were always superior. The only reason flat files won was that graphs were too expensive to build and maintain manually.

That cost equation has flipped. If the LLM is already doing the maintenance work (and it is — that's what the Obsidian/wiki pattern celebrates), then the question isn't "can you afford a graph?" but "why would you store the result of that maintenance work in a flat file instead of a graph?"

---

## The Sleep Functions: Graph Hygiene as Long-Term Memory Maintenance

The Rosebud taxonomy describes async "dream" processes — nightly consolidation, drift correction, periodic summarization. Seldon implements these as graph maintenance operations:

- **Pruning:** Remove redundant or superseded edges
- **Tuning:** Adjust confidence/staleness scores based on new evidence
- **Cleaning:** Resolve entity ambiguity, merge duplicates, fix broken references
- **Staleness propagation:** When upstream artifacts change, flag downstream dependents

These operations exist precisely to avoid making a mess of the graph over time. They're the graph equivalent of the "lint" pass in the wiki pattern — but they're structural operations on typed edges, not an LLM re-reading hundreds of markdown files and hoping it catches contradictions.

---

## The Anti-Yak-Shaving Position

Running 100 ingests through an LLM wiki, measuring drift, comparing against Seldon's replay — this sounds like rigorous science. In practice it becomes:

- Which model did you use? (Results change with model)
- Which prompt? (Results change with prompt)
- How many times did you run it? (Non-deterministic outputs)
- What's your ground truth? (The evaluation paradox again)

You end up evaluating model performance and prompt engineering, not the architectural question. The architectural question — "can you rebuild derived state from raw events?" — is a **structural property**, not an empirical one. Seldon can. Flat wikis can't. That's provable by construction, not by experiment.

Spending time and money on experiments that measure the wrong thing is exactly the failure mode the book rails against. If someone else wants to run that experiment, they're welcome to. It's not where the value is for this work.

---

## The 4-64 Rule and the `git init` Analogy

The 80/20 rule (Pareto) applied to its own top 20% yields the **4-64 rule**: 4% of events control 64% of consequential outcomes. Applied to knowledge artifacts:

- 4% of your knowledge artifacts will drive 64% of your consequential decisions
- You cannot identify which 4% at creation time
- Seldon's provenance cost applies uniformly across all artifacts
- Seldon's provenance *value* concentrates in the tail — the small fraction of artifacts that end up cited in a paper, supporting a policy decision, or surviving peer review

This is the same logic as `git init`. You don't initialize version control because you know you'll need to rollback. You do it because:

1. The cost is near zero
2. It's trivially automated — once it's part of the routine, you don't think about it
3. The one time you need it, you *really* need it
4. By the time you know you need it, it's too late to add retroactively

Seldon is `git init` for research provenance. The argument isn't "you will need this." The argument is "the cost of having it is lower than the cost of not having it the one time it matters, and you can't predict when that is."

**For the paper:** This reframes the adoption argument entirely. Don't argue that everyone needs provenance. Argue that provenance is cheap enough to be the default, and that the 4% of artifacts where it matters will justify the uniform cost retroactively. The alternative — deciding per-artifact whether provenance is needed — requires predicting the future, which is more expensive than just tracking everything.

---

## Implications for the Paper

The Seldon paper should NOT:
- Claim that flat wiki systems are "wrong" or "broken"
- Run benchmark experiments comparing derivation drift (yak-shaving)
- Position Seldon as only for "high-stakes" evidentiary work

The Seldon paper SHOULD:
- Position Seldon as serving the same long-term memory function, implemented on a structurally superior data structure
- Note that knowledge graphs are established as better representations for knowledge — the barrier was always creation cost, not representational quality
- Argue that AI tooling collapses the creation barrier, making the graph's operational advantages accessible at near-zero marginal cost
- Show that provenance, traceability, blast radius queries, and staleness propagation are structural properties of the graph — not add-on features
- Frame via the 4-64 rule: value concentrates in the tail, cost is uniform, prediction is harder than default-on
- Use the `git init` analogy: cheap enough to be the default, invaluable the one time it matters

---

## Related Notes
- `2026-04-12_obsidian-llm-wiki-pattern-as-foil.md` — the pattern this responds to
- `2026-04-12_cross-source-synthesis-memory-landscape.md` — "projectable state" as the structural differentiator
