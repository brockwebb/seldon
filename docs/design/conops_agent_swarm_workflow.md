# ConOps: Seldon Agent Swarm Workflow

**Date:** 2026-03-16
**Status:** Concept of Operations — How the system works end-to-end
**Context:** Defines the operational workflow for using Claude Desktop, Seldon's graph, and Claude Code agent swarms to produce research deliverables. This document is the reference so we don't reinvent this every session.

---

## 1. The Actors

| Actor | What It Is | Role |
|-------|-----------|------|
| **Human** | Brock | Chief scientist. Owns the argument. Makes judgment calls. Approves. |
| **Desktop** | Claude Desktop with Seldon MCP | Design partner. Calls `seldon go` for orientation. Produces CC task specs. Does NOT write code. |
| **CC Leader** | Claude Code with agent swarm enabled | Orchestrator inside CC. Reads the CC task spec. Decomposes into worker assignments. Synthesizes results. |
| **CC Workers** | Claude Code agent swarm workers | Specialists. Each gets a scoped role, bounded context, and specific deliverable. Interact with the graph via `seldon` CLI. |
| **Seldon Graph** | Neo4j + JSONL event store | Source of truth. Holds artifacts, provenance, role definitions, argument skeleton, project state. All state changes go through the graph. |

---

## 2. The Workflow

### Phase 0: Orientation (Desktop)

Human opens Desktop. Says something like "let's work on leibniz-pi" or asks a question about the project.

1. Desktop calls `seldon go` MCP tool with the project directory
2. MCP returns: engineering standards, project CLAUDE.md, latest handoff, graph state (open tasks, stale results, documentation health, role definitions)
3. Desktop is now oriented — knows the project state, the argument skeleton, the available roles, what's open

**Desktop's job from here:** Think. Design. Produce CC task specs. Never write code.

### Phase 1: Directive (Human → Desktop)

Human gives a high-level directive:
- "Write the Methods section"
- "Verify all results have provenance"
- "Audit documentation completeness across the whole project"
- "Red team the Discussion section"

### Phase 2: Decomposition (Desktop)

Desktop decomposes the directive against the graph state. This is design work — understanding what the directive requires, what artifacts are involved, what roles are needed, and what the work units are.

Desktop produces a **CC task spec** — a markdown file that goes in `cc_tasks/`. The task spec includes:

1. **Objective** — what "done" looks like
2. **Swarm configuration** — which roles to activate, what each worker does
3. **Role instructions** — system prompt per worker, pulled from the graph's AgentRole artifacts
4. **Graph context** — specific artifacts, provenance chains, argument claims each worker needs (retrieved by `seldon go` or specified as `seldon` CLI queries for workers to run)
5. **Coordination** — what the leader synthesizes, what conflicts to flag, what goes back into the graph
6. **Success criteria** — how to verify the swarm's output
7. **What NOT to do** — boundaries

### Phase 3: Handoff (Human)

Human reviews the CC task spec. Approves, modifies, or rejects. Then hands it to CC (opens CC session, points it at the task file).

This is the human approval gate. The task spec is the artifact that captures intent.

### Phase 4: Execution (CC Agent Swarm)

CC reads the task spec. Leader agent:

1. Reads the full task spec
2. Creates the shared task board per CC swarm protocol
3. Spawns workers with role-specific instructions from the task spec
4. Workers execute in parallel:
   - Each worker calls `seldon` CLI to get its context slice from the graph
   - Each worker produces its deliverable (prose, verification report, gap analysis, etc.)
   - Each worker writes results back via `seldon` CLI (register results, update artifacts, create tasks for gaps found)
5. Leader collects worker outputs, flags conflicts, synthesizes

### Phase 5: Results (CC → Graph → Desktop)

Worker outputs land in the graph:
- New artifacts registered (draft sections, verification records)
- Existing artifacts updated (documentation properties filled, states transitioned)
- Tasks created for issues found (gaps, contradictions, missing provenance)

CC commits code/prose changes. Writes a handoff.

### Phase 6: Review (Human + Desktop)

Human opens Desktop for next session. `seldon go` shows:
- What the swarm produced
- What tasks were created (gaps, conflicts)
- What needs human judgment (argument decisions, interpretation, voice)

Desktop helps review, critique, plan next iteration.

---

## 3. The Roles

Stored in the Seldon graph as `AgentRole` artifacts. Retrieved by `seldon go` and included in CC task specs.

### Lead / Chief Scientist (Seldon)
**Responsibility:** Decompose directives. Assign work. Synthesize outputs. Maintain argument coherence.
**Retrieval profile:** Argument skeleton (Layer 0), claim inventory (Layer 1), open tasks, cross-section dependencies.
**Does NOT:** Write prose. Verify numbers. Check citations. That's what workers are for.

### Methods & Analysis
**Responsibility:** Write methodology prose. Document parameters. Verify scripts produce claimed results. Check statistical validity.
**Retrieval profile:** Script artifacts + documentation properties, Result artifacts + provenance chains, DataFile schemas, PipelineRun reproduction commands.
**CLI tools used:** `seldon result trace`, `seldon docs check --type Script`, graph queries for GENERATED_BY and COMPUTED_FROM chains.

### Evidence / Verifier
**Responsibility:** Trust nothing. Verify every provenance chain. Check every `{{result:NAME:value}}` reference. Flag stale, unverified, or missing evidence.
**Retrieval profile:** All Result artifacts, all provenance chains, CITES edges from PaperSections, staleness state.
**CLI tools used:** `seldon result list --state stale`, `seldon result trace`, `seldon paper audit`, `seldon docs check --strict`.

### Prose / Writer
**Responsibility:** Draft section text from claim inventory + evidence. Follow `conventions.md`. Maintain consistent voice and argument flow.
**Retrieval profile:** Argument skeleton, claim inventory for target section, verified Results and their interpretations, conventions and style config.
**CLI tools used:** `seldon paper build --no-render` (to resolve references), `seldon paper audit` (on own output).

### Literature / Acquisitioner
**Responsibility:** Check citation coverage. For each claim, verify supporting literature exists. Flag unsupported claims. Identify missing references.
**Retrieval profile:** Citation artifacts, claim inventory, CITES edges, references.bib.
**CLI tools used:** `seldon artifact list --type Citation`, graph queries for claims without Citation links.

### Contrarian / Red Team
**Responsibility:** Read all outputs. Find contradictions between sections. Identify logical gaps. Challenge assumptions. Surface blind spots.
**Retrieval profile:** Full claim inventory across all sections, cross-section ASSUMES/CONTRADICTS/EXTENDS edges (AD-012 typed edges).
**CLI tools used:** `seldon paper audit`, graph traversal for contradicting claims, cross-section edge analysis.

---

## 4. Example: "Write the Methods Section"

### Desktop produces this CC task spec:

```
# CC Task: Write Methods Section — Agent Swarm

## Objective
Produce a draft Methods section for the leibniz-pi paper, fully connected to 
the Seldon graph with {{result:NAME:value}} references.

## Swarm Configuration
Leader: Seldon role. Decomposes against argument skeleton claims tagged 
"methods" or "methodology".

Workers:
1. Methods agent — write prose for each subsection, documenting parameters 
   and linking to Script artifacts
2. Evidence agent — verify every Result cited in Methods has a complete 
   provenance chain (Script → DataFile → PipelineRun)
3. Writer agent — polish prose, enforce conventions.md, run paper audit
4. Red Team agent — read the draft, flag assumptions that aren't stated, 
   find logical gaps in the methodology argument

## Role Instructions
[Retrieved from graph by seldon go — full system prompts per role]

## Graph Context
- Argument skeleton claims for Methods: [claim IDs from graph]
- Script artifacts: [list from seldon artifact list --type Script]
- Result artifacts tagged methods: [list]
- Current Methods section draft (if exists): paper/sections/03_methods.md

## Coordination
Leader synthesizes worker outputs into a single draft.
Conflicts between Methods prose and Evidence verification → create ResearchTask.
Red Team findings → create ResearchTask with blocks → PaperSection.

## Success Criteria
- Methods section draft exists with all {{result}} references resolving
- seldon paper audit passes Tier 2 on the section
- All Results cited have verified provenance (Evidence agent confirms)
- Zero unresolved conflicts between workers
```

### CC executes with native agent swarm.

---

## 5. What This ConOps Does NOT Cover

- **How CC agent swarms work internally** — that's CC's implementation. We produce the task spec; CC handles worker lifecycle.
- **ClaudeClaw integration** — ClaudeClaw remains Wintermute's daemon. If we need scheduled/autonomous Seldon jobs, that's a separate design.
- **Real-time collaboration between Desktop and CC** — Desktop produces specs, CC executes them. Not concurrent.
- **Argument skeleton authoring** — that's human work. The skeleton is Layer 0 (AD-012). No agent writes it.

---

## 6. Prerequisites To Make This Work

| Prerequisite | Status | What's Needed |
|-------------|--------|---------------|
| `seldon go` MCP returning context | Built (AD-013 session) | Extend to include role definitions |
| CC agent swarms enabled | Available (v2.1.32+) | Enable in CC settings |
| Role definitions in graph | NOT BUILT | New `AgentRole` artifact type + register roles |
| Workflow templates | NOT BUILT | Optional — can start with manual CC task specs |
| Argument skeleton in graph | Per-project | Exists for leibniz-pi (AD-012 Layer 0) |
| `seldon` CLI callable by CC workers | Working | Already works — CLI is on PATH |

---

## 7. The Key Principle

**The graph is the coordination layer.** Workers don't pass messages to each other — they read from and write to the graph. The shared task board (CC's native feature) handles worker coordination. The Seldon graph handles research state coordination. These are complementary, not competing.

**Desktop designs. CC executes. The graph persists.** Each actor does what it's good at. No actor tries to do another's job.

---

*This document defines how we work. Reference it. Don't reinvent it.*
