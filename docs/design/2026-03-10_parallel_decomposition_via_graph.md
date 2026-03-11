# Design Insight: Parallel Decomposition via Graph Partitioning

**Date:** 2026-03-10
**Source:** Synthesis of context generation experiment results + discussion
**Builds on:** `2026-03-10_database_as_context_architecture.md`

---

## The Insight

The context window is not the ceiling. It's the size of a single worker's desk. The graph is the warehouse. You never put the warehouse on the desk. You pull one bin at a time.

A 2,000-variable Census pipeline is not one task requiring 2,000 variables of context. It's hundreds of tasks, each requiring 20-50 variables. The graph structure itself defines the decomposition — each DataStep/PROC is a natural work unit with bounded inputs and outputs.

---

## The Pattern: Graph-Partitioned Parallel Execution

### 1. Decompose
Query the graph for all top-level processing steps (DataSteps, PROCs). Each is a self-contained work unit with:
- Input datasets (and their variables)
- Output datasets (and their variables)
- Internal transforms
- A bounded, queryable subgraph

### 2. Slice
For each work unit, extract the minimal context slice:
- The step's input variables (types, states, missing semantics)
- The step's output variables (expected types, states)
- The transforms within the step
- Immediate upstream dependencies (what produced the inputs)
- NOT the entire pipeline. NOT downstream consumers.

Typical slice size: 500-2,000 tokens per work unit, even in a 2,000-variable pipeline.

### 3. Dispatch
Each work unit becomes a CC task or subagent. Each gets a clean context window containing ONLY its slice. Multiple work units dispatch in parallel when they have no data dependencies between them.

The graph defines the parallelism: steps that share no input/output datasets can run simultaneously. Steps in sequence (step_clean → step_merge) must be ordered. This is just topological sort on the DAG.

### 4. Execute
Each agent works in isolation:
- Reads its context slice
- Performs its task (parse SAS, generate Python, compare traces)
- Produces structured output (new graph nodes, results, validation reports)
- Has no knowledge of other agents or the broader pipeline

### 5. Write Back
Agent output goes to the graph as structured records:
- New nodes with provenance (which agent, which slice, which task)
- New edges linking to existing nodes
- Results with verification status
- Schema validation on write prevents malformed data

### 6. Validate
After all agents complete, integrity scripts verify:
- All steps are processed (no orphan work units)
- All edges resolve (no dangling references)
- No duplicate nodes
- State machine constraints hold
- Provenance chains are complete

---

## Why This Works

**The graph is the coordination layer.** Agents don't talk to each other. They talk to the graph. Agent A finishes step_clean, writes nodes back. Agent B queries for the next incomplete step, gets step_merge, pulls its slice. No orchestrator needed — graph state IS the coordination.

**The linking layer does reassembly for free.** The edges between steps are defined by the pipeline structure, not by the agents. When step_merge's agent runs, it doesn't need to know what step_clean did internally. It just queries: "what variables does ds_survey_clean contain?" That's one graph lookup. The linking layer (relationship edges) carries the context that would otherwise require stuffing both steps' details into one window.

**Context windows stay small and precise.** Each agent operates on maybe 1-2% of the total graph. No compression, no summarization, no "losing" context through compaction. The full fidelity lives in the graph. The agent sees exactly what it needs at full resolution.

---

## Scaling Properties

**Horizontal:** Add more variables, more steps, more pipelines — each agent's context slice stays bounded. A 20,000-variable pipeline is 10x more work units but the same size per unit.

**Vertical (depth):** A highly interconnected node (a variable used in 15 transforms) doesn't blow up context — you only follow the edges relevant to the current task. The retrieval profile determines which edges to follow, not the node's total connectivity.

**Parallel throughput:** Limited by API rate limits and CC session limits, not by context window size. With CC subagents or multiple sessions, you can process N independent work units simultaneously.

---

## The Bottlenecks (Real Constraints)

1. **Graph query speed.** Decomposition and slicing require graph traversals. NetworkX is fine for hundreds of nodes. For tens of thousands, Neo4j is the right backend. Already have the infrastructure from Arnold.

2. **Dispatch rate.** How many parallel CC sessions can you run? API rate limits, cost per token, session management overhead. This is an operational constraint, not an architectural one.

3. **Decomposition quality.** If the graph doesn't capture a dependency between two steps, they'll be processed independently and the result will be wrong. Graph completeness is critical — same chokepoint as retrieval quality, different surface.

4. **Write-back conflicts.** If two agents try to create the same node (e.g., a shared variable), you need conflict resolution. Event-sourced architecture helps — both writes are recorded, dedup happens on replay. But the schema must handle this.

5. **Sequential dependencies.** Steps in a data pipeline are partially ordered. step_merge depends on step_clean's output. The topological ordering must be respected — you can't parallelize everything. The graph's DAG structure gives you the dependency order directly.

---

## Relationship to Existing Concepts

| Concept | Connection |
|---------|-----------|
| MapReduce | Decompose = Map, Write-back + Validate = Reduce. The graph is the shuffle layer. |
| Microservices | Each agent is a stateless service. The graph is the shared state store. Service mesh topology = graph topology. |
| Brain / neural activation | Each agent = a localized neural activation pattern. Graph = long-term memory. Context window = working memory. Retrieval = associative recall. |
| Seldon PL-003 (specialist roles) | Different agent types get different retrieval profiles. A "parser" agent gets code-structure slices. A "validator" agent gets trace-comparison slices. Same graph, different views. |
| Wintermute PL-001 (service mesh) | Cross-project version of this same pattern. Each project's graph is a bounded context. Wintermute holds cross-project edges. |

---

## What This Means for the SAS Conversion Project

Phase 0-1 (done): Build the graph, prove CC can build from specs.
Phase 2: Build the decomposer — query the graph for work units, generate slices, dispatch tasks.
Phase 3: Build the write-back — agents commit results to the graph with validation.
Phase 4: Run parallel agents on independent steps of the reference pipeline.

This is the path from "CC builds one thing at a time from hand-written tasks" to "the graph orchestrates parallel agents that build everything from auto-generated slices."

---

*The secret isn't infinite context. It's not needing it.*
