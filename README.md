# Seldon

**The queen of the colony.**

Seldon is a research operating system that guarantees reproducibility, traceability, and continuity for AI-assisted scientific and engineering work — regardless of domain, scale, or which agents do the work.

## What Seldon Is

Seldon is the persistent graph intelligence that decomposes research work into bounded tasks, provides each agent with exactly the context it needs, validates what comes back, and maintains the collective state across sessions, agents, and projects.

Individual agents — Claude Code sessions, subagents, automated scripts — are stateless, disposable workers. They are spawned, receive a precisely-scoped graph slice, do their work, write structured output back to the graph, and terminate. No agent holds state that isn't in the graph. Any agent can be replaced by any other agent given the same context slice.

**The graph is the mind. The agents are the hands.**

## What Seldon Guarantees

These are the architectural properties — the -ilities — that Seldon enforces for any project it manages. Features change. These don't.

| Property | Guarantee |
|----------|-----------|
| **Recoverability** | Any agent can crash at any point. Graph state is always consistent. Work units are re-dispatchable from the last valid state. |
| **Scalability** | Horizontal: more artifacts = more work units, same context size per unit. A 20,000-variable pipeline is 10x more work units but the same size per unit. |
| **Composability** | Agents are interchangeable. Context slices are combinable. Any agent can do any task given the right slice. |
| **Auditability** | Event-sourced append-only log is a complete history. Every mutation is traceable — who wrote it, when, from what input, with what authority. |
| **Reproducibility** | Same input slice produces same output. Deterministic. Re-runnable. Verifiable. |
| **Resilience** | No single agent failure corrupts the collective. No single session loss destroys project state. The graph persists across all discontinuities. |
| **Evolvability** | Schema changes are events. Old data remains valid. New patterns layer on without breaking existing structure. |

## How It Works

**The database is the context window.** Not a supplement to the LLM context window — the replacement. The graph stores millions of tokens of project state, queryable at sub-second latency with precise retrieval. Each agent gets a slice of hundreds or thousands of tokens — exactly what it needs, nothing more. No compression, no summarization, no drift.

**The graph decomposes work.** A large pipeline with 2,000 variables isn't one task. It's hundreds of tasks, each operating on a small subgraph. The graph structure itself defines the decomposition — each processing step has bounded inputs and outputs. Topological sort on the DAG determines sequencing.

**Agents are stateless drones.** Spawned, given a context slice, do work, write back, terminate. The graph is the coordination layer. Agents don't talk to each other. They talk to the graph. Agent A finishes a task, writes nodes back. Agent B queries for the next incomplete task, gets its slice, works on it.

**Validation enforces integrity.** Every write-back passes through schema validation and referential integrity checks before committing to the event log. Malformed outputs are rejected. The graph never enters an inconsistent state.

## Architecture

```
You (Product Manager) ──→ Specifications
                              │
                              ▼
                    ┌─────────────────┐
                    │     Seldon      │
                    │   (The Queen)   │
                    │                 │
                    │  Graph Store    │  ← Persistent state
                    │  Event Log     │  ← Complete history
                    │  Domain Config │  ← Schema + rules
                    │  Query Engine  │  ← Context slicing
                    │  Validator     │  ← Integrity enforcement
                    └────────┬────────┘
                             │
                    Decompose + Slice + Dispatch
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         ┌─────────┐   ┌─────────┐   ┌─────────┐
         │ Agent A  │   │ Agent B  │   │ Agent C  │
         │ (Drone)  │   │ (Drone)  │   │ (Drone)  │
         │          │   │          │   │          │
         │ Context  │   │ Context  │   │ Context  │
         │ Slice: X │   │ Slice: Y │   │ Slice: Z │
         └────┬─────┘   └────┬─────┘   └────┬─────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    Write back + Validate
                             │
                             ▼
                    ┌─────────────────┐
                    │  Graph Store    │  ← Updated state
                    └─────────────────┘
```

## Current State

**Phase A (active):** Skills and conventions. The Seldon workflow is encoded as Claude Code skills (`briefing`, `closeout`, `result-register`, `task-track`). The "database" is structured markdown files. This works for small projects.

**Phase B (next):** CLI engine. NetworkX + JSONL replaces markdown files. Skills call the CLI instead of reading/writing files directly. Graph queries replace grep.

**Phase C (target):** Graph-driven context generation. `seldon context generate` auto-produces CC task files from graph state. Agents receive context slices, not hand-written tasks. The graph orchestrates.

**Phase D (future):** Neo4j for production scale. Parallel agent dispatch. Cross-project queries via Wintermute.

**Proof of concept:** The [SAS Graph Code Conversion](https://github.com/brockwebb/sas_graph_code_conversion) project. Phase 0 complete — 49 tests passing, reference pipeline graph (65 nodes, 91 edges), context generation experiment validated.

## Relationship to Other Systems

| System | Role |
|--------|------|
| **Seldon** | The queen. Holds the graph, decomposes work, slices context, validates output. |
| **Wintermute** | The collective memory. Cross-domain knowledge graph. Seldon manages per-project state; Wintermute holds cross-project connections. |
| **LeStat** | The forager. Autonomous knowledge intake that feeds Wintermute. |
| **ANTS** | Historical. The proto-Seldon. Core patterns (NetworkX, event sourcing, authority model) carry forward. |
| **Agents (CC sessions)** | The drones. Stateless workers that receive context slices and write back results. |

## Key Architectural Decisions

See [`docs/design/seldon_architectural_decisions.md`](docs/design/seldon_architectural_decisions.md) for the full AD registry.

- AD-001: Clean build from ANTS patterns
- AD-002: Domain-agnostic core + swappable domain config
- AD-003: CLI commands, not MCP servers
- AD-004: Per-project database, no shared infrastructure
- AD-005: Standard update/retrieve interface
- AD-006: Result Registry as first-class artifact
- AD-007: Task tracking as first-class artifact
- AD-009: Database as context architecture
- AD-010: Collective architecture — stateless agents, persistent graph

## License

MIT
