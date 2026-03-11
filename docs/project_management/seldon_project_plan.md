# Seldon — Project Plan & Task List

**Date:** 2026-02-21
**Status:** Active planning document
**Context:** Derived from seldon_architectural_decisions.md. Organized for someone splitting time between projects and needing to context-switch without losing state.

---

## 0. Current Reality Check

| Item | Status |
|------|--------|
| Seldon repo | Scaffold only — docs, templates, no code |
| ANTS v0.4 | 28 MCP tools, working, deployed on FSCM (481 artifacts) |
| Pragmatics paper | Active — needs result registry and task tracking NOW |
| Wintermute | Broken — bad extractions, isolation problems. Parked. |
| This plan | The thing that prevents "what was I doing?" on every session switch |

**Constraint:** Brock is splitting time between pragmatics paper and infrastructure. The plan must produce value for the paper *while* building Seldon. No "build for 6 weeks then use it" — each tier must be usable immediately.

---

## 1. Tier 0: Schema Design Document (THIS WEEK)

**Why first:** Everything downstream depends on getting the data model right. This is a design task, not a coding task. Can be done in a single focused session.

- [ ] **T0-1: Comprehensive schema design document**
  - All artifact types for research domain config (Result, Figure, PaperSection, Citation, ResearchTask, LabNotebookEntry, Script, DataFile, SRS_Requirement, PipelineRun)
  - All relationship types with cardinality and constraints
  - State machine definitions per artifact type
  - Event schema (what does an event look like in the JSONL?)
  - Carry forward validated patterns from ANTS event schema
  - Document in `seldon/docs/design/schema.md`
  - **CC task:** Can be drafted by CC from ANTS's existing event schema + AD-006/AD-007 specs

- [ ] **T0-2: Update Seldon repo docs to reflect new scope**
  - CLAUDE.md — update to reflect ANTS-folded-in architecture
  - README.md — update scope from "orchestrator" to "core engine"
  - vision.md — already valid, minor updates
  - conops.md — update session workflow for result registry + task tracking
  - Add architectural_decisions.md to repo (the doc we just wrote)
  - **CC task:** Straightforward file updates

- [ ] **T0-3: CLI command design**
  - Map ANTS's 28 tools to Seldon CLI commands
  - Add new commands: `seldon result register`, `seldon task create`, `seldon briefing`, `seldon closeout`
  - Define command groups: `seldon artifact`, `seldon link`, `seldon result`, `seldon task`, `seldon session`
  - Document in `seldon/docs/design/cli_spec.md`
  - **Depends on:** T0-1 (schema must be defined first)

---

## 2. Tier 1: Core Engine MVP (1-2 WEEKS)

**Goal:** Minimum viable Seldon that can be initialized on a project and track artifacts + results + tasks via CLI. No bells and whistles. Must be pip-installable and usable from Claude Code immediately.

### Core Graph Engine
- [ ] **T1-1: Event store (JSONL append-only log)**
  - Event schema implementation from T0-1
  - Append, read, replay functions
  - Port proven patterns from ANTS `events.py`
  - **Clean build** — no copy-paste of ANTS code with tech debt

- [ ] **T1-2: Graph projection (NetworkX)**
  - Build graph from event replay
  - Typed nodes with state machines
  - Typed edges with metadata
  - Port from ANTS `graph.py`, clean up

- [ ] **T1-3: Artifact CRUD**
  - Create, read, update state, delete (soft — event-sourced)
  - Domain-agnostic: artifact type comes from config, not hardcoded
  - State machine enforcement (can't go from proposed → published without verified)

- [ ] **T1-4: Relationship CRUD**
  - Create, read, remove links between artifacts
  - Relationship type validation against domain config
  - Cascading staleness propagation (upstream change flags downstream)

### Domain Configuration
- [ ] **T1-5: Domain config loader**
  - YAML or TOML file defining artifact types, relationship types, state machines
  - Research config as first implementation
  - Validation: refuse to create artifact types not in config

### CLI
- [ ] **T1-6: CLI skeleton (Click or Typer)**
  - `seldon init` — initialize project with domain config
  - `seldon status` — show graph stats, open tasks, stale results
  - `seldon artifact create/list/show/update`
  - `seldon link create/list/show`
  - pip-installable, `seldon` command available after install

### Authority Model
- [ ] **T1-7: Authority model (refined)**
  - Default: auto-accept (AI writes, it's authoritative)
  - Override: human can flag items for review
  - Decisions traced — who accepted, when, why
  - Per AD discussion: reduce friction, human intervenes at decision points only

---

## 3. Tier 2: Research Domain Features (1-2 WEEKS, overlaps with paper work)

**Goal:** The things the pragmatics paper needs RIGHT NOW. Built on top of Tier 1 engine.

### Result Registry
- [ ] **T2-1: `seldon result register` command**
  - Creates Result artifact with: value, units, description, generating script, input data hash, run timestamp
  - Links to Script artifact, DataFile artifacts, SRS_Requirement
  - State: proposed → verified → published

- [ ] **T2-2: `seldon result verify` command**
  - Re-runs generating script, compares output to registered value
  - If match: state → verified, records verification event
  - If mismatch: flags as stale, shows diff, propagates to downstream citations

- [ ] **T2-3: Result provenance query**
  - Given a result ID, show full chain: Result → Script → Data → SRS
  - Given a paper section, show all cited results and their provenance completeness score
  - `seldon result trace <id>` and `seldon result coverage <section>`

### Task Tracking
- [ ] **T2-4: `seldon task create/list/update` commands**
  - Creates ResearchTask artifact with state machine
  - Links: depends_on, blocks relationships
  - `seldon task list --open` shows all non-completed tasks

- [ ] **T2-5: Session briefing integration**
  - `seldon briefing` at session start shows: open tasks, stale results, incomplete provenance, recently changed artifacts
  - This is the `general_retrieve()` for the session start context

- [ ] **T2-6: Session closeout**
  - `seldon closeout` captures: what was done, new tasks created, results registered
  - This is the `general_update()` for session end
  - Replaces handoff prose with structured state

### Migration
- [ ] **T2-7: ANTS → Seldon migration for FSCM**
  - Read existing ANTS events from federal-survey-concept-mapper
  - Transform to Seldon event format
  - Validate 481 artifacts survive migration
  - One-time script, not ongoing feature

---

## 4. Tier 3: Pragmatics Paper Deployment (CONCURRENT with paper writing)

**Goal:** Actually use Seldon on the paper. Validate it works. Discover what's missing.

- [ ] **T3-1: Initialize Seldon on federal-survey-concept-mapper**
  - `seldon init --domain research`
  - Migrate ANTS data (T2-7)

- [ ] **T3-2: Register all verified numbers from existing analysis**
  - Port from numbers_registry.md into Seldon Result artifacts
  - Link each to generating script and SRS requirement
  - Identify gaps: numbers with no traceable script

- [ ] **T3-3: Formalize open tasks**
  - The 3 Anthropic parse failures that were never backfilled → ResearchTask
  - Any other dropped items from conversation archaeology → ResearchTask
  - Link each to what it blocks

- [ ] **T3-4: Write paper sections using Seldon briefings**
  - Start each writing session with `seldon briefing`
  - End each with `seldon closeout`
  - Track whether this actually prevents the failure modes

- [ ] **T3-5: Retrospective**
  - What worked? What's missing? What's friction?
  - Feed findings back into Seldon roadmap
  - This becomes the requirements for Tier 4+

---

## 5. Tier 4+: Future (NOT SCHEDULED — triggers noted)

| Feature | Trigger |
|---------|---------|
| Engineering domain config | When a non-research project needs Seldon |
| Automated run provenance (PL-004) | After manual result registration proves the pattern |
| Drift detection (PL-005) | After result registry has enough data to test |
| Specialist retrieval profiles (PL-003) | After session briefings prove useful and need specialization |
| Wintermute cross-project layer | After 2-3 Seldon instances running |
| ALMA-inspired meta-learning (PL-006) | After basic system produces data about retrieval effectiveness |

---

## 6. Task Dependencies (Critical Path)

```
T0-1 (schema) ──→ T0-3 (CLI spec) ──→ T1-6 (CLI skeleton)
    │                                        │
    ├──→ T1-1 (event store) ──→ T1-2 (graph) ──→ T1-3 (artifact CRUD) ──→ T1-4 (link CRUD)
    │                                                     │
    │                                                     ├──→ T2-1 (result register)
    │                                                     ├──→ T2-4 (task tracking)
    │                                                     └──→ T2-7 (ANTS migration)
    │
    └──→ T1-5 (domain config)

T0-2 (doc updates) ── independent, do anytime

T2-1 + T2-4 ──→ T2-5 (briefing) ──→ T3-4 (paper use)
T2-7 ──→ T3-1 (init on FSCM) ──→ T3-2 (register numbers) ──→ T3-3 (formalize tasks)
```

**Critical path to paper value:** T0-1 → T1-1 → T1-2 → T1-3 → T1-5 → T1-6 → T2-1 → T2-4 → T2-5 → T3-1

---

## 7. What Can Be CC Tasks vs. Desktop Sessions

| Task | Mode | Why |
|------|------|-----|
| T0-1 Schema design | Desktop brainstorm → CC draft | Needs your domain judgment, then CC writes it up |
| T0-2 Doc updates | CC | Pure grunt work |
| T0-3 CLI spec | Desktop brainstorm → CC draft | Design decisions, then CC documents |
| T1-1 through T1-7 | CC | Implementation from spec. Review at checkpoints. |
| T2-1 through T2-6 | CC with review | Implementation, but domain logic needs your eye |
| T2-7 Migration | CC | Mechanical transformation |
| T3-1 through T3-4 | Desktop | Active use, real-time feedback |
| T3-5 Retrospective | Desktop | Judgment call |

---

## 8. Session Protocol (Use This Now, Even Before Seldon Exists)

Until `seldon briefing` and `seldon closeout` are built:

**Session start:** Read this document. Read the latest handoff in `seldon/handoffs/`. Check the task list above — what's next on the critical path?

**Session end:** Update the checkboxes in this document. Write a handoff if anything non-obvious happened. Commit.

**Context switching between projects:** This document IS the briefing. If you can read it in 2 minutes and know what to do next, it's working.

---

*Last updated: 2026-02-21. Update checkboxes and dates as work progresses.*
