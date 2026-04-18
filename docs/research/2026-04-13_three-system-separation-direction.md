# Architectural Direction: Three-System Separation

**Date:** 2026-04-13
**Type:** Design note — captures emerging architectural understanding from dogfooding
**Context:** Conversation following the AD-022 T5 incident (audit pipeline state discontinuity) and the Arnold coaching system experience

---

## The Current Problem

Seldon is currently doing three jobs:

1. **State management** — graph-backed state machines, event-sourced transitions, authority model, drift detection, reconciliation. The core SFV countermeasure layer.
2. **Authoring pipeline** — AD-019/AD-020 audit gates, citation conventions, chapter patterns, sweep synthesis, run manifests. A domain-specific research writing workflow.
3. **Cross-project knowledge custodian** — shared ontology (AD-017), central validity vocabulary, practitioner vocabulary, data dictionary, bibliography catalog. Master/replica sync patterns, read-only inheritance.

These are three distinct concerns with different consumers, different evolution paths, and different operational characteristics. They're joined together because they grew together, not because they belong together.

## Evidence That They're Distinct

### Wintermute concern misplaced in Seldon
The `seldon ontology sync` command, the master/replica pattern, the read-only inheritance in `seldon.yaml` — all of this is Seldon acting as a cross-project knowledge store. That's Wintermute's job. The implementation creates friction: filesystem path dependencies, sync commands that can drift, replica files that are copies (and copies drift — proven at 363B in <24hrs). The natural interface is a live query via MCP, not a replicated file.

### Authoring concern irrelevant to non-writing projects
When Seldon was deployed on the Arnold coaching system, the state management was immediately valuable — tracking training decisions, preventing programming drift, maintaining coherence across sessions. The authoring pipeline (audit gates, citation conventions, chapter patterns) was irrelevant. The coaching thread's initial reaction that Seldon was overkill was a reaction to the authoring layer, not the state layer. They couldn't distinguish the two because the code doesn't distinguish them.

### State management is the kernel
Without state management, the authoring pipeline can't function — it depends on the graph for cross-section impact tracking, ontology enforcement, artifact state machines. But state management functions perfectly without the authoring pipeline. The dependency is one-directional. State is the kernel; authoring is a module.

## Target Architecture

Three systems, clean interfaces:

| System | Concern | Interface |
|--------|---------|-----------|
| **Wintermute** | Cross-project knowledge: ontology, taxonomy, data dictionary, bibliography, knowledge graph, curation, synthesis, connection discovery | MCP server (in development). Projects query live, no replicas. |
| **Seldon Core** | Per-project state management: graph-backed state machines, event-sourced transitions, authority model, drift detection, artifact CRUD, session briefing/closeout | CLI + MCP. Domain-agnostic. Works for papers, coaching systems, data pipelines, anything with stateful decisions. |
| **Authoring Module** | Research writing workflow: audit gates (AD-019/AD-020), citation conventions, chapter patterns, sweep synthesis, run manifests | Built on top of Seldon Core. Loaded when a project needs it (`domain: research` + `review:` config in seldon.yaml). Not loaded for non-writing projects. |

The relationship: Wintermute and Seldon are peers — two organisms in the same ecosystem, symbiotic but independent. The authoring module is a layer on Seldon, not a peer. Wintermute provides shared knowledge; Seldon enforces project-level state; the authoring module orchestrates research writing workflows using both.

## Migration Sequence

### Phase 1: Wintermute MCP → migrate centralized knowledge out of Seldon
- Wintermute MCP server comes online (currently in development)
- Ontology, vocabulary, data dictionary, bibliography served via MCP
- `seldon.yaml` points to Wintermute MCP endpoint instead of filesystem paths
- Retire `seldon ontology sync`, master/replica patterns, read-only filesystem copies
- Seldon becomes a pure consumer of shared knowledge

### Phase 2: Exercise the Wintermute-Seldon boundary on real projects
- Verify the MCP interface works for project initialization, glossary checks, bibliography lookups
- Multiple projects (Arnold, SFV paper, ai-workflow-design, future work) stress different parts of the boundary
- Identify any coupling that the clean split missed

### Phase 3: Split Seldon's authoring module from state core
- Wait for enough project diversity to prove where the cut belongs
- Arnold (no authoring), SFV paper (heavy authoring), ai-workflow-design (heavy authoring), future projects each stress different boundaries
- When the seam is clear, refactor — not before
- The authoring module becomes loadable infrastructure, not baked-in

## Design Principles Governing the Split

- **Modules, not monoliths.** Each system has one concern. Overlap is purposeful and explicit.
- **Compose, don't marry.** Systems interact through interfaces (MCP, CLI), not shared internals.
- **Build from understanding, not speculation.** Split when the evidence demands it, not when the architecture diagram suggests it. The Arnold experience and the T5 incident are evidence. More will come.
- **Symbiosis, not hierarchy.** Wintermute doesn't own Seldon. Seldon doesn't own Wintermute. They're peers with different specializations in the same ecosystem.
- **The fractal pattern holds.** The same graph-backed, event-sourced, authority-modeled architecture at every scale — per-project (Seldon), cross-project (Wintermute), per-workflow (authoring module). Same engine, different scope, different vocabulary.

## What This Is Not

This is not a refactoring plan. No code changes are implied. This is a record of where the architecture is heading based on observed pain points, so that incremental decisions align with the direction rather than fighting it. The next concrete step is Phase 1: get the Wintermute MCP server working and migrate the first centralized concern (ontology) out of Seldon.

---

*Captured from a Desktop session following the AD-022 work. The T5 incident, the Arnold deployment, and the cross-project task misrouting incident all pointed to the same conclusion: Seldon is currently three systems pretending to be one, and the pretense creates friction at every boundary.*
