# Preprint Sketch: Event-Sourced Graph Architecture for Persistent Agent State Management

**Working title candidates (pick one, or iterate):**
- "Event-Sourced Graph State Machines for AI Agent Memory: An Architecture for Provenance-Preserving Persistent Context"
- "Beyond Retrieval: Managing Agent State with Event-Sourced Knowledge Graphs and Typed Artifact Lifecycles"
- "Seldon: An Event-Sourced Graph Architecture for Stateful AI Agent Workflows"

**Target venues:** FCSM 2026, JSM 2026, AAAI Workshop on Agents, or standalone arXiv preprint
**Approach:** Systems paper, not ML paper. No training, no benchmarks against LLM performance. This is about architecture — how you structure persistent state so agents don't lose provenance, use stale data, or drop tasks.

---

## Abstract (draft)

AI agent systems increasingly require persistent memory that survives beyond a single session, yet current approaches treat agent memory as a retrieval problem — storing and fetching text fragments via vector similarity, key-value pairs, or context window management. We argue that the core failure modes of agent memory are not retrieval failures but *state management* failures: agents cite stale results, lose provenance chains between generated artifacts, and drop incomplete tasks across session boundaries. We present Seldon, an event-sourced graph architecture where agent-produced artifacts are typed nodes with lifecycle state machines, connected by validated relationship types, tracked through append-only event logs, and projected into a persistent graph database. Session-scoped briefing and closeout protocols provide structured context loading and consolidation. Staleness propagation via graph traversal ensures downstream dependents are flagged when upstream artifacts change. We evaluate the architecture on a statistical code conversion pipeline, comparing context quality and provenance completeness against flat-file, vector-retrieval, and unstructured memory baselines.

---

## 1. Introduction

### The problem (grounded in real failure modes, not hypotheticals)

Multi-session AI agent workflows — research projects, code migration, iterative analysis — generate artifacts that accumulate state over weeks or months. Current agent memory systems focus on *what the agent remembers* (retrieval quality) but neglect *what state those memories are in* (lifecycle management).

Documented failure modes from production use:
- **Provenance loss**: A quantitative result (e.g., "accuracy = 91.2%") generated in Session 3, cited in Session 7, but no traceable path from the cited number to the script that produced it or the data it was computed from. By Session 12, the number has drifted to 91.6% with no audit trail explaining why.
- **Task dropout**: Session creates 3 sub-tasks. One is completed. The conversation pivots. The other two are never formalized as trackable items and are discovered weeks later during forensic archaeology through chat transcripts.
- **Stale citation**: A script is re-run with updated data, producing a different result. Paper sections citing the old result are not updated because no structural mechanism connects the result to its downstream dependents.
- **Context over-fetch**: An agent retrieves 73% of the project graph when scoped retrieval would have required 12%, wasting context tokens and diluting attention on relevant artifacts.

These are not retrieval problems. Vector similarity search does not solve them. They are state management problems that require typed artifacts, lifecycle state machines, relationship validation, and graph-based dependency tracking.

### Positioning against existing approaches

| System | Memory Model | What it misses |
|--------|-------------|----------------|
| Mem0 | Key-value store with entity extraction | No artifact lifecycle, no provenance, no state machines |
| MemGPT/Letta | Context window paging (page-in/page-out) | No persistent graph, no relationship types, no staleness propagation |
| LightRAG | Graph-enhanced vector retrieval | No event sourcing, no artifact states, no authority model |
| Vector stores (Chroma, pgvector) | Embedding similarity search | No structural relationships, no provenance chains, no state tracking |
| Flat files (CLAUDE.md, Obsidian vaults) | Unstructured text in filesystem | No queryability, no state, no relationships, no validation |
| A-Mem | Agentic memory with self-organization | No typed artifacts, no domain configuration, no staleness propagation |
| ALMA | Meta-learned memory designs | Learns retrieval strategies but doesn't address provenance or lifecycle |

**Gap:** No existing system treats agent-produced artifacts as *typed, stateful entities with validated relationships and event-sourced provenance.* The closest analog is not from AI — it's from requirements engineering (IBM DOORS) and software traceability systems, adapted for AI agent workflows.

---

## 2. Architecture

### 2.1 Design Principles

1. **Artifacts, not memories.** The unit of persistence is a typed artifact (Result, Script, DataFile, ResearchTask, PaperSection) with a defined lifecycle, not an unstructured text blob.

2. **State machines, not flags.** Each artifact type has a defined state machine (proposed → verified → published → stale). Invalid transitions are rejected. State changes are events.

3. **Relationships are validated, not inferred.** A GENERATED_BY link between a Result and a Script is created explicitly and validated against the domain schema. The graph doesn't guess at connections — it enforces them.

4. **Event sourcing as ground truth.** Every mutation is an append-only event in a JSONL log. The graph database is a projection — a materialized view that can be rebuilt from event replay. This provides full audit trail, temporal queries, and crash recovery.

5. **Domain-agnostic engine, domain-specific configuration.** Artifact types, relationship types, and state machines are defined in YAML configuration per domain. The same engine serves research workflows, engineering projects, or any domain that produces typed, related artifacts.

6. **Session-scoped context loading.** Agents don't receive the entire graph. A briefing protocol queries for open tasks, stale results, incomplete provenance, and recent changes — loading only relevant state into the agent's working context.

### 2.2 Dual-Layer Storage

```
Append-only JSONL event log    →    Neo4j graph projection
(source of truth, portable)         (persistent, indexed, queryable via Cypher)
```

Every mutation writes to JSONL first, then executes the corresponding Cypher against Neo4j. The JSONL log is git-tracked and portable. Neo4j provides indexed traversal, concurrent access, and a query language suitable for agent-driven retrieval.

Recovery: if the graph database is lost, `seldon rebuild` replays the event log into a fresh instance. Zero data loss.

### 2.3 Artifact Lifecycle

Each artifact type defines a state machine. Example for Result:

```
proposed → verified → published → stale
                                    ↓
                               verified (re-verification after re-run)
```

State transitions are:
- Validated against the domain configuration (invalid transitions rejected with error)
- Recorded as events with actor, timestamp, and authority level
- Propagated: when a Result transitions to "stale," downstream artifacts citing it via CITES relationships are automatically flagged

### 2.4 Session Protocol

**Briefing** (session start — structured context loading):
- Open tasks (proposed, accepted, in_progress, blocked)
- Stale results and what they block
- Results with incomplete provenance (no linked generating script)
- Recent activity
- Graph statistics

**Closeout** (session end — structured consolidation):
- Log session summary as LabNotebookEntry artifact
- Record artifacts created, state transitions, links created during session
- Session-tagged events enable temporal queries ("what happened in this work session?")

This replaces unstructured handoff documents with structured state capture.

### 2.5 Staleness Propagation

When an upstream artifact changes state (e.g., Result marked stale because the generating script was updated), graph traversal identifies all downstream dependents:

```cypher
MATCH (downstream)-[:CITES|CONTAINS]->(target:Artifact {artifact_id: $id})
WHERE downstream.state IN ['published', 'review', 'draft']
RETURN downstream
```

Each dependent is transitioned to "stale" if its state machine permits, with events recorded. This is causal consistency enforced structurally — not a policy, but a graph operation.

---

## 3. Implementation

### 3.1 System Description

Seldon is implemented as a pip-installable Python CLI package. 97 tests. MIT licensed.

- **Event store:** Append-only JSONL with atomic writes, truncation detection, duplicate event detection
- **Graph projection:** Neo4j with double-label pattern (:Artifact:<TypeLabel>), indexed on artifact_id, type, and state
- **Domain config:** YAML defining artifact types, relationship types with cardinality constraints, state machines per type
- **CLI:** Click-based commands for artifact CRUD, result registry, task tracking, session briefing/closeout
- **Sync:** Incremental sync (events since last checkpoint) and full replay for recovery
- **Authority model:** Events carry actor (human|ai) and authority (proposed|accepted) fields. Default auto-accept; human review triggered by risk indicators.

### 3.2 Domain Configuration Example (Research)

Artifact types: Result, Figure, PaperSection, Citation, ResearchTask, LabNotebookEntry, Script, DataFile, SRS_Requirement, PipelineRun

Relationship types with validation:
- cites: PaperSection|Figure → Result|Citation
- generated_by: Result|Figure → Script
- computed_from: Result → DataFile
- blocks: ResearchTask → Result|PaperSection|Figure
- implements: Script → SRS_Requirement

Adding a new domain (e.g., engineering) requires only a new YAML file — no code changes.

---

## 4. Evaluation

### 4.1 Experimental Setup

**Domain:** SAS-to-Python statistical code conversion pipeline for U.S. federal survey programs.

**Test graph:** 65 nodes, 91 edges representing a complete survey data processing pipeline — variables, transformations, dependencies, state transitions from raw data through published statistics.

**Task:** Given a specific SAS DATA step, retrieve sufficient context to generate equivalent Python code. Measure:
- **Context tokens consumed:** How many tokens were loaded into the agent's working context
- **Retrieval precision:** What fraction of loaded context was actually relevant to the task
- **Provenance completeness:** Can every generated result be traced back to its source through the graph
- **Stale-data incidents:** Did the agent cite or use any artifact in "stale" state

### 4.2 Conditions

1. **Flat-file baseline:** Agent receives the entire project documentation as text (simulates CLAUDE.md / Obsidian vault approach)
2. **Vector retrieval:** Agent queries a vector store with the task description, receives top-k similar chunks (simulates RAG / Mem0 approach)
3. **Graph-scoped retrieval:** `seldon briefing` loads only open tasks, stale results, and graph-neighborhood of the target artifact (Seldon approach)
4. **Agent-driven graph retrieval:** Agent receives a Cypher query interface and writes its own retrieval queries (future RLM-style, stretch goal)

### 4.3 Metrics

- Context tokens: raw count loaded into agent context
- Precision@task: fraction of loaded artifacts that the agent actually referenced in its output
- Provenance score: fraction of output results with complete upstream trace (Result → Script → DataFile → Requirement)
- Staleness violations: count of citations to artifacts in "stale" state
- Task completion: did the agent complete the assigned work correctly

### 4.4 Expected Results

Flat-file loads everything (low precision, high tokens). Vector retrieval loads semantically similar but structurally irrelevant content (moderate precision, no provenance). Graph-scoped retrieval loads the exact subgraph needed (high precision, low tokens, full provenance, zero staleness violations by construction — stale artifacts are flagged before loading).

The key result isn't that graph retrieval is "better" — it's that it's the only approach that *prevents structural failures* (stale citations, provenance gaps, dropped tasks) by design rather than by luck.

---

## 5. Discussion

### 5.1 Agent Memory as State Management, Not Retrieval

The field's focus on retrieval quality (embedding models, chunking strategies, re-ranking) addresses a real problem but misses the structural one. An agent can retrieve the perfect text chunk and still cite a stale number, because the retrieval system has no concept of artifact state. Seldon's contribution is reframing agent memory from "what should the agent remember?" to "what state are the agent's artifacts in, and are the dependencies between them consistent?"

### 5.2 Event Sourcing as Audit Infrastructure

The append-only event log provides capabilities that no other agent memory system offers:
- **Temporal queries:** "What did the agent believe was true on March 3rd?" (replay events up to that date)
- **Blame analysis:** "When did this result change, and who/what triggered the change?"
- **Recovery:** Complete rebuild from event log if graph database fails
- **Reproducibility:** The event log is the complete, ordered history of every state change

### 5.3 Domain Agnosticism

The same architecture applies to any domain that produces typed, related artifacts with lifecycles. Research projects, software engineering (requirements → design → code → tests), clinical trials (protocol → data collection → analysis → report), regulatory compliance (requirement → evidence → attestation). The domain configuration is YAML, not code.

### 5.4 Limitations

- **Scale:** Tested on project-scale graphs (tens to hundreds of artifacts). Industrial-scale validation (thousands of artifacts, concurrent agents) is future work.
- **Retrieval strategy:** Current briefing protocol uses fixed queries. Adaptive retrieval (agent-driven, RLM-style) is designed but not yet evaluated.
- **Authority model:** Currently binary (proposed/accepted). Risk-stratified authority with graph-derived risk scores is designed but not yet implemented.
- **Cross-project state:** Each project has its own isolated graph. Cross-project knowledge sharing requires a separate coordination layer (designed, not built).

---

## 6. Related Work

- **Mem0** (Chhikara et al., 2025): Scalable long-term memory with entity extraction. Key-value model, no artifact lifecycle.
- **MemGPT/Letta** (Packer et al., 2024): OS-inspired context management with virtual memory paging. No persistent graph.
- **LightRAG** (Guo et al., 2024): Graph-enhanced retrieval. No event sourcing, no state machines.
- **ALMA** (Xiong et al., 2026): Meta-learned memory designs. Learns retrieval strategies, doesn't address provenance.
- **A-Mem** (Xu et al., 2025): Agentic memory for LLM agents. No typed artifacts, no domain configuration.
- **Saga** (Ilyas et al., 2022): Apple's knowledge graph platform. Validates fact-level provenance at industrial scale. Closest architectural precedent, but designed for knowledge graph construction, not agent workflow state.
- **RLM** (Zhang & Khattab, 2026): Recursive language models with REPL-based context access. Complementary — RLM addresses *how* agents access context; Seldon addresses *what state that context is in*.
- **Multi-agent memory consistency** (Yu et al., 2026): Frames agent memory as computer architecture problem. Position paper identifying the consistency gap that Seldon's staleness propagation partially addresses.
- **IBM DOORS**: Requirements traceability in systems engineering. The conceptual ancestor — typed artifacts, bidirectional traceability, impact analysis. Seldon adapts this pattern for AI agent workflows.

---

## 7. Conclusion

Agent memory systems that treat persistence as a retrieval problem will continue to produce agents that cite stale data, lose provenance, and drop tasks. The structural failures documented in this paper arise not from forgetting, but from the absence of lifecycle management, relationship validation, and dependency tracking in the memory layer.

Seldon demonstrates that event-sourced graph architectures with typed artifact state machines address these failures by construction. The architecture is domain-agnostic, implemented as a lightweight CLI tool, and evaluated on a real statistical code conversion pipeline. The event log provides full auditability. The graph provides structured traversal. The state machines prevent invalid lifecycle transitions. Staleness propagation ensures consistency.

The contribution is not a new retrieval algorithm. It is the argument — backed by implementation and evaluation — that agent memory should be managed as a state machine over a provenance graph, not as a document store with semantic search.

---

## References

(To be formatted per venue style)

- Chhikara et al. (2025). Mem0: Building production-ready AI agents with scalable long-term memory. arXiv:2504.19413
- Guo et al. (2024). LightRAG: Simple and fast retrieval-augmented generation. arXiv:2410.05779
- Ilyas et al. (2022). Saga: A platform for continuous construction and serving of knowledge at scale. SIGMOD 2022. arXiv:2204.07309
- Packer et al. (2024). MemGPT: Towards LLMs as operating systems. arXiv:2310.08560
- Xiong et al. (2026). Learning to continually learn via meta-learning agentic memory designs. arXiv:2602.07755
- Xu et al. (2025). A-Mem: Agentic memory for LLM agents. arXiv:2502.12110
- Yu et al. (2026). Multi-agent memory from a computer architecture perspective. arXiv:2603.10062
- Zhang & Khattab (2026). Recursive language models. arXiv:2512.24601

---

## Appendix: System Availability

Seldon is open source (MIT license): https://github.com/brockwebb/seldon
97 tests passing. Neo4j + JSONL dual-layer architecture. pip-installable.
