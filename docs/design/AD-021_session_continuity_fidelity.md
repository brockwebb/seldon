# AD-021: Session Continuity Fidelity

**Date:** 2026-04-03
**Status:** Proposed
**Context:** Two related continuity failures. (1) Handoff documents routinely report CC tasks as incomplete when they have already been executed. (2) Long-lived project tasks get tracked in prose (CLAUDE.md "Open Items," handoff bullet lists) instead of as graph artifacts, causing drift and CC sessions treating stale prose as authoritative state. Both are symptoms of the same root cause: tracking mutable state in static files instead of querying the graph.
**Extends:** AD-014 (Agent Roles as Graph Artifacts), AD-007 (Task Completion Tracking)

---

## Problem

The session continuity mechanism has two fidelity gaps.

### Gap 1: CC Task Completion Status

Three components interact:

1. **`seldon closeout`** — runs at session end, creates a LabNotebookEntry with session event counts, prompts for a summary string.
2. **Handoff files** — written by the AI as narrative prose in `handoffs/`. Describe what happened, what's open, what's next.
3. **`seldon go`** — reads the latest handoff file from disk and presents it alongside live graph state.

The failure mode: a Desktop session writes a CC task and notes it as "not yet executed" in the handoff. CC executes the task in a separate session. The handoff file is never updated. The next Desktop session reads the stale handoff via `seldon go` and sees a phantom incomplete task.

This isn't an edge case — it's the normal workflow. Desktop writes CC tasks; CC executes them asynchronously. The handoff is always a snapshot of Desktop's knowledge at closeout time, which is structurally unable to reflect CC's subsequent execution.

### Gap 2: Long-Lived Project Tasks in Prose

Project tasks — deferred design decisions, open research questions, blocked items, hotwash findings — get tracked as prose bullet lists in:
- CLAUDE.md "Open Items" sections
- Handoff "Open Items" / "Not addressed this session" sections  
- Planning documents with checkbox lists

This is wrong for three reasons:

1. **CLAUDE.md is a bootloader, not a database.** It gets loaded into every session's context window. Mutable task state in a static file means every session reads stale state. CC sessions have been observed treating these stale lists as authoritative work assignments.

2. **Prose lists don't have state machines.** A bullet point that says "deferred — design decision needed" has no queryable state, no transition history, no blocking relationships. It can't appear in `seldon briefing` output. It's invisible to the graph.

3. **Duplication and drift.** The same task appears in CLAUDE.md, in the handoff, and maybe in a planning doc. Three copies, none authoritative, all drifting independently. Classic "which one is current?" failure.

The graph already has `ResearchTask` with a full state machine (proposed → accepted → in_progress → completed → verified) and blocking relationships. That's where project tasks belong. If a task needs to survive across sessions, it's a graph artifact or it doesn't exist.

### Gap 3: Desktop Cannot Mutate Graph State

Desktop sessions (Claude Desktop, claude.ai threads) can orient via `seldon go` but cannot create tasks, close stale artifacts, mark CC tasks complete, or query the graph directly. The only MCP tool exposed is `seldon_go`. This creates a round-trip problem:

1. Desktop identifies 9 stale `proposed` tasks that were already addressed.
2. Desktop cannot close them — it would need to write a CC task to do housekeeping.
3. CC task overhead is disproportionate to the operation (updating a `state` field).
4. The stale tasks persist until someone bothers to write the CC task, which often never happens.

The same problem applies to task creation. When Desktop identifies a deferred work item during planning, it should create the graph artifact immediately — not note it in prose and hope someone formalizes it later. But without MCP tools for graph mutation, Desktop is limited to writing prose (the exact anti-pattern Gap 2 describes).

Additionally, the `neo4j-mcp` tool cannot handle Seldon's per-project database isolation. It connects to one database. Seldon projects each have their own Neo4j database (per AD-004). Desktop threads working on ai-workflow-design can't query that project's graph through `neo4j-mcp` if it's configured for the seldon-seldon-self database.

### Why This Matters

- **Wasted context window:** New sessions spend tokens investigating work that's already done or tasks that were resolved sessions ago.
- **Re-execution risk:** A task described as incomplete might get re-executed, creating duplicate artifacts.
- **Trust erosion:** If the orientation context is routinely wrong about task status, operators learn to distrust it, defeating its purpose.
- **CC misuse:** CC sessions executing stale task lists from CLAUDE.md because they look like authoritative instructions.
- **Housekeeping debt:** Trivial graph mutations accumulate because Desktop can't do them inline, and writing CC tasks for each one is disproportionate overhead.

---

## Decision

Two principles, three mechanisms.

**Principle 1: Verifiable claims in orientation context must be projections of graph state, not pass-through of narrative prose.** The handoff file remains for narrative context (design rationale, open questions, strategic direction). But task completion status, artifact registration status, and other verifiable claims are derived from the graph at query time.

**Principle 2: If a task must survive across sessions, it's a graph artifact.** No exceptions. Prose lists of open items in CLAUDE.md or handoffs are informational summaries of graph state, not the source of truth. When a Desktop session identifies a deferred task, it creates the artifact immediately via MCP — not in prose.

### Mechanism 1: CC Task Completion Tracking

CC tasks become trackable. A new convenience command records execution:

```bash
seldon cc complete <filepath> [--note "..."]
```

Behavior:
1. Validates `<filepath>` exists
2. Creates a `ResearchTask` artifact with `source_file` property pointing to the CC task file, state `completed`, timestamp
3. The CC task file itself is NOT modified (immutability preserved)

When `seldon go` presents the latest handoff, it cross-references CC task paths mentioned in the handoff against completed `ResearchTask` artifacts with matching `source_file` values. Completed tasks get annotated:

```
### One CC Task Remains
cc_tasks/2026-04-03_register_glossary_ontology_design_note.md — register the 
architecture gap design note...

  ✓ [COMPLETED 2026-04-03T15:32:00Z] — artifact registered in graph
```

### Mechanism 2: Project Task Hygiene

**Rule:** When a Desktop session identifies work that must survive across sessions (deferred decisions, blocked items, hotwash findings), it creates the graph artifact in-session via MCP tools (see Mechanism 3). The handoff may reference these tasks narratively, but the canonical state lives in the graph.

**Migration:** Existing prose task lists in CLAUDE.md and handoffs should be triaged:
- Still relevant → create graph artifact, remove from CLAUDE.md
- No longer relevant → just remove from CLAUDE.md
- Genuinely static context (not a task) → leave as prose

### Mechanism 3: Seldon MCP Tool Surface for Desktop

Extend `mcp_server.py` with a small set of tools that let Desktop sessions do graph housekeeping without round-tripping through CC tasks. All tools are project-scoped — they resolve the project database from `seldon.yaml` at the given `project_dir`, eliminating the neo4j-mcp single-database limitation.

#### Tool Inventory

**`seldon_task_create`** — Create a ResearchTask in the project graph.
- Parameters: `project_dir`, `description`, `state` (default: `proposed`), `blocks` (optional artifact ID)
- Returns: artifact ID of created task
- Use case: Desktop identifies deferred work during planning; creates it immediately instead of writing prose.

**`seldon_task_update`** — Update a ResearchTask's state.
- Parameters: `project_dir`, `task_id`, `state`, `note` (optional)
- Returns: confirmation with old → new state
- Use case: Desktop closes stale tasks, marks tasks in_progress, etc.

**`seldon_task_list`** — List tasks filtered by state.
- Parameters: `project_dir`, `state_filter` (optional, e.g. `open`, `proposed`, `completed`), `brief` (optional, default true)
- Returns: formatted list of matching tasks
- Use case: Desktop checks what's actually open without burning the full `seldon go` output.

**`seldon_issue_create`** — Create an Issue in the project graph.
- Parameters: `project_dir`, `name`, `description`, `importance`, `urgency`
- Returns: artifact ID
- Use case: Desktop captures a problem with Eisenhower dimensions during review.

**`seldon_issue_update`** — Update an Issue's state or priority.
- Parameters: `project_dir`, `issue_id`, `state` (optional), `importance` (optional), `urgency` (optional)
- Returns: confirmation

**`seldon_cc_complete`** — Mark a CC task file as completed in the graph.
- Parameters: `project_dir`, `filepath`, `note` (optional)
- Returns: artifact ID of completion record
- Use case: Desktop (or CC) records that a CC task has been executed.

**`seldon_cc_register`** — Register an already-written CC task file as a graph artifact.
- Parameters: `project_dir`, `filepath`
- Returns: artifact ID
- Use case: Desktop writes a CC task file via Filesystem MCP, then registers it in the graph with one tool call. Creates a ResearchTask with `source_file` property and state `proposed`.

**`seldon_query`** — Read-only Cypher query against the project's graph database.
- Parameters: `project_dir`, `cypher` (the query string)
- Returns: formatted query results
- Constraint: **Read-only.** The tool must reject any query containing write operations (CREATE, MERGE, SET, DELETE, REMOVE, DETACH). Graph mutations go through the typed tools above, which enforce event sourcing and state machine rules. Raw Cypher bypasses those constraints.
- Use case: Desktop explores graph state, checks relationships, runs ad-hoc queries that the typed tools don't cover.

#### Design Principles for the MCP Surface

1. **Project-scoped.** Every tool takes `project_dir` and resolves the database from `seldon.yaml`. No hardcoded database names. This is how Desktop talks to any project's graph regardless of which database neo4j-mcp is configured for.

2. **Thin wrappers.** The MCP tools delegate to the same internal functions the CLI uses (`create_artifact`, `update_artifact_state`, etc.). No duplicated logic. The MCP tool handles parameter parsing and project resolution; the core functions do the work.

3. **Event-sourced.** All mutations go through the event log, same as CLI operations. The MCP surface is an interface, not a bypass.

4. **Read-heavy, write-light.** `seldon_query` and `seldon_task_list` are the high-frequency tools. The mutation tools (`_create`, `_update`) are used less often but eliminate the CC-task-for-housekeeping overhead.

5. **No artifact creation for tracked content.** Desktop still cannot create PaperSection, Figure, Result, or other content artifacts via MCP. Those go through CC tasks with `seldon verify` gates. The MCP surface is for project management artifacts (tasks, issues) and graph queries — not content.

---

## What This Does NOT Do

- Does NOT eliminate handoff files. Narrative context (design rationale, strategic direction, session story) can't be captured in structured graph data. Handoffs remain valuable for that.
- Does NOT require handoffs to be machine-parseable. CC task reconciliation operates on file paths, not prose parsing.
- Does NOT add mandatory steps to Desktop closeout workflow. Creating graph tasks during the session is the discipline change; closeout is unchanged.
- Does NOT auto-generate handoffs from graph state. The graph provides facts; the handoff provides story.
- Does NOT create a new artifact type for CC tasks. `ResearchTask` with a `source_file` property is sufficient. If the pattern proves unwieldy, a dedicated `CCTask` type can be added later.
- Does NOT expose content artifact creation via MCP. PaperSections, Figures, Results go through CC tasks. MCP is for project management and queries.
- Does NOT allow raw Cypher writes via MCP. All mutations go through typed tools that enforce event sourcing and state machines.

---

## Scope & Sequencing

**Phase 1:**
- `seldon cc complete` CLI command
- `seldon go` handoff reconciliation for CC task paths
- Triage existing CLAUDE.md prose task lists → graph artifacts or deletion

**Phase 2:**
- MCP tools: `seldon_task_create`, `seldon_task_update`, `seldon_task_list`, `seldon_issue_create`, `seldon_issue_update`, `seldon_cc_complete`, `seldon_cc_register`, `seldon_query`
- All project-scoped via `project_dir` parameter

**Phase 3 (if warranted):**
- Richer `seldon go` reconciliation — cross-referencing artifact mentions in handoff prose against graph state
- Auto-detection of prose task patterns in handoffs that should be graph artifacts (lint rule)

---

## Related

- AD-003: CLI Commands, Not MCP Servers — This AD intentionally extends the MCP surface for Desktop housekeeping while preserving CLI-first for project-internal operations. The MCP tools are thin wrappers around CLI internals, not a parallel interface.
- AD-004: Per-Project Database — The `project_dir` parameter on every MCP tool is how Desktop reaches any project's graph without neo4j-mcp's single-database limitation.
- AD-007: Task Completion Tracking — ResearchTask as first-class artifact. This AD extends the pattern to CC tasks and enforces the discipline that all persistent tasks belong in the graph.
- AD-014: Agent Roles as Graph Artifacts — session protocol definitions.
- The April 3 handoff that triggered this: reported a CC task as incomplete when it had been executed, and carried forward deferred items from a March 25 hotwash as prose bullets that were never formalized as graph artifacts.
