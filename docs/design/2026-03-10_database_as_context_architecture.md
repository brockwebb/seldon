# Design Insight: Database as Context Architecture

**Date:** 2026-03-10
**Source:** Voice note during driving + synthesis session
**Status:** Active insight — shapes Seldon Phase B/C architecture

---

## The Core Insight

The database is not a supplement to the LLM context window. It is the replacement.

LLM context windows are:
- Ephemeral (gone when the session ends)
- Lossy (compression/compaction discards information)
- Fixed-size (200k tokens, maybe 1M — still finite)
- Undifferentiated (everything in the window competes for attention)
- Expensive to fill (every token of context costs inference time)

A graph database is:
- Persistent (survives sessions, survives model changes, survives everything)
- Lossless (structured records don't degrade)
- Unbounded (millions of nodes, limited only by storage)
- Precisely queryable (retrieve exactly the subgraph you need)
- Cheap to store, cheap to query (milliseconds, not token costs)

**The architectural principle:** Agents are stateless functions that operate on graph slices. The graph is the state. The context window is working memory, not storage.

---

## Memory Surface Model

The context window is not a flat buffer. With graph-backed retrieval, it becomes a structured memory surface:

**Horizontal scaling:** Add more nodes and relationships to the graph without affecting any individual agent's context window. A project with 10,000 artifacts is no harder to work with than one with 100 — each agent still gets only its relevant slice.

**Vertical depth:** The richness of interconnectedness at a node. A variable with 15 relationships (derived_from, consumed_by, validated_by, cited_in, etc.) provides:
- 15 associative paths to find it during retrieval
- 15 dimensions of context when it's retrieved
- Precise scope: follow only the relationships relevant to the current task

**The linking layer does work within the context window.** When you retrieve a subgraph, the relationships between nodes ARE context. You don't need to explain "variable X feeds into transform Y which produces variable Z" — the graph edges encode that directly. The linking structure substitutes for prose explanation, saving tokens and eliminating ambiguity.

**Brain analogy (structural, not metaphorical):**
- Working memory (context window): small, expensive, temporary, loses fidelity under load
- Long-term memory (graph database): large, cheap, persistent, structured
- Retrieval (graph query): associative, follows links, returns precise activations
- Consolidation (closeout/result-register): structured write-back from working memory to long-term store
- The brain doesn't load all memories into consciousness. It activates the specific network relevant to the current task. That's what graph-scoped retrieval does.

---

## What This Means for Seldon

### Phase A (current): Skills simulate the pattern
- Briefing skill reads handoff files (flat retrieval from filesystem)
- Closeout skill writes handoff files (flat write-back)
- This works for small projects but doesn't scale — grep is not a graph query

### Phase B (next): CLI + graph engine replaces flat files
- `seldon briefing` becomes a graph query: open tasks, stale results, incomplete provenance relevant to current scope
- `seldon closeout` becomes a graph write: structured records committed to the event log
- Results, tasks, artifacts are graph nodes, not YAML files
- NetworkX + JSONL is sufficient at this scale

### Phase C (target): Graph generates agent context automatically
- `seldon context generate --scope <task>` produces a CC task file with exactly the right subgraph context
- Each CC session gets a precisely-scoped slice of the project graph
- Multiple CC sessions can run in parallel on different subgraph slices
- The graph query IS the prompt engineering — retrieval quality determines output quality

### Phase D (future): Neo4j for production scale
- When NetworkX + JSONL hits performance limits (thousands of nodes, complex traversals)
- Neo4j provides: Cypher queries, relationship-first storage, graph algorithms, persistence
- Already have Neo4j infrastructure from Arnold — migration path exists
- Cross-project queries (Wintermute territory) require a real graph database

---

## The Chokepoint: Retrieval Quality

The voice note identified this correctly: **retrieval quality is the single point of failure.**

If the graph query that produces a context slice is wrong or incomplete:
- Agent operates on a malformed view of the project
- Produces confidently wrong outputs
- Those outputs write back to the graph, compounding the error
- No human in the loop to catch it (Level 4 = human reviews outcomes, not process)

**Retrieval quality depends on:**

1. **Schema quality** — are the right node types and relationship types defined? Missing a relationship type = missing an associative path = missing context during retrieval.

2. **Query design** — does the query follow the right relationships to the right depth? Too shallow = missing dependencies. Too deep = including irrelevant context. This is the equivalent of prompt engineering, but for graph traversal.

3. **Graph completeness** — are all artifacts actually registered? An unregistered result is invisible to retrieval. This is why `result-register` and `task-track` must be enforced, not advisory.

4. **Relationship integrity** — are edges correct? A wrong `derived_from` edge produces wrong lineage queries. Validation scripts must check referential integrity.

**Mitigation strategies:**
- Schema validation on every write (already in the domain config pattern)
- Integrity check scripts that run on commit hooks (deterministic, not advisory)
- Retrieval tests: for known scenarios, verify the query returns the expected subgraph
- Agent output validation: before writing back to graph, validate against schema constraints

---

## The Problem to Solve

The experiment (`experiments/001_context_generation.md`) tests whether this architecture works at small scale (65 nodes). The real problems emerge at scale:

1. **Query design language.** How does a human (or Seldon) express "give me the context for implementing FR-001"? This maps to a graph traversal pattern: find the FR node, follow its relationships to relevant artifact nodes, include those artifacts' immediate dependencies. Need a DSL or at least a library of named query patterns.

2. **Scope boundaries.** When traversing the graph for context, where do you stop? One hop gives too little. Unlimited hops gives the whole graph. The right answer depends on the task type. This is the "retrieval profile" from PL-003 — different specialist roles need different traversal depths and directions.

3. **Context budgeting.** The retrieved subgraph must fit in the context window with room for the agent to work. Need to estimate token cost of a subgraph before retrieving it. If the slice is too large, need strategies: summarize leaf nodes, prune low-relevance edges, retrieve in stages.

4. **Write-back validation.** When an agent produces output, how do you validate it before committing to the graph? Schema validation catches structural errors. But semantic errors (wrong value in a result, incorrect relationship) require either automated testing or human review. The risk scoring from the authority model (DD-AUTO-ACCEPT-001) applies here.

5. **Graph evolution.** The schema will change as the project evolves. New node types, new relationship types, deprecated types. Event-sourced architecture handles this (old events still valid, new events use new schema), but queries need to handle schema heterogeneity.

---

## Relationship to Existing Architecture Decisions

| AD | Relevance |
|----|-----------|
| AD-002 (domain-agnostic core) | The context generation mechanism is domain-agnostic. Query patterns are domain-specific. |
| AD-003 (CLI, not MCP) | Context generation is a CLI command. The graph slice is a file, not a streaming API. |
| AD-004 (per-project database) | Each project's graph is self-contained. Context slices come from one graph. |
| AD-005 (update/retrieve interface) | `retrieve()` IS the context generation query. `update()` IS the write-back. This AD was more right than we knew. |
| AD-006 (result registry) | Results must be in the graph to be retrievable. Unregistered results are invisible. |
| AD-007 (task tracking) | Tasks must be in the graph to appear in briefings. This closes the loop. |
| DD-AUTO-ACCEPT-001 (risk-stratified authority) | Write-back validation uses risk scoring. Low-risk writes auto-accept. High-risk writes require review. |

---

*This insight reshapes the implementation priority. The graph engine (Tier 1 of the project plan) isn't just infrastructure — it's the context architecture. Getting the query patterns right is more important than getting the CLI pretty.*
