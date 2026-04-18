# Design Note: Graph-Backed Session Continuity

**Date:** 2026-04-08  
**Status:** Proposed  
**Context:** Current session transitions require manual copy-paste of handoff markdown between threads. This burns tokens, introduces staleness, and makes the human the transport layer for state that the graph already tracks. AD-021 solved the Desktop→CC reconciliation problem and added MCP tools. This design note addresses the next gap: making `seldon go` the complete session bootstrap, eliminating manual handoff transport.  
**Extends:** AD-021 (Session Continuity Fidelity), AD-007 (Task Completion Tracking), AD-004 (Per-Project Database)  
**Informed by:** Claude Code's compaction hierarchy pattern (cheapest context first, expensive last), MemPalace's "wake-up" concept (~170 tokens to orient), Karpathy's "wiki from raw sources" pattern.

---

## 1. Problem Statement

### The Current Workflow (What Actually Happens)

1. Session starts → `seldon go` → loads orientation + latest handoff + graph state
2. Work happens → context grows → tokens burn
3. Session ends → AI writes handoff prose → saves to `handoffs/`
4. **Human copies handoff text from old thread**
5. **Human pastes handoff into new thread**
6. **Human types `seldon go`** → loads orientation again (redundant with pasted handoff)
7. New session re-establishes context from pasted prose + graph query

Steps 4-6 are manual compaction with the human as transport layer. The handoff file is a flat-file registry for session state — the exact anti-pattern Seldon was built to replace (see AD-006's rationale: "Flat-file registries are manual, unenforced, and drift-prone").

### What's Wrong

**Token waste.** The pasted handoff often contains 1,000-3,000 tokens of narrative that partially overlaps with what `seldon go` already provides (open tasks, project state, latest handoff). The new session pays for both.

**Staleness.** Between writing a handoff and starting the next session, CC tasks may execute, artifacts may change state, new issues may be created. The pasted handoff is a snapshot that doesn't reflect intervening work. AD-021 partially addressed this with CC task reconciliation, but the handoff prose itself (narrative, strategic direction, next steps) still goes stale.

**Cross-project blindness.** Each handoff is project-scoped. When hopping between ai-workflow-design, seldon, leibniz-pi, and sfv-paper, the human carries cross-project context in their head. There's no mechanism for `seldon go` on project A to surface "you left project B mid-task" or "project C has a stale artifact that's relevant here."

**Context window pressure.** Long sessions accumulate stale context. There's no principled "rotate now" signal. The human rides the thread until Claude starts degrading, then manually rotates. Proactive rotation (short focused sessions, clean state transitions) would be better, but only if the rotation cost is near zero.

**CC tasks as loose files.** CC task specs get written to `cc_tasks/` and registered in the graph, but they could *be loaded from* the graph when a CC session starts. Right now CC gets its task by the human pasting a file path or content. `seldon go` could surface "you have 2 ready CC tasks" and the CC session could load the spec directly.

### The Failure Mode Ladder

1. **Today:** Human is the transport layer. Works but burns tokens, introduces lag, drops cross-project context.
2. **Without fixing this:** As project count grows, the manual handoff hop becomes the bottleneck. More projects = more silos = more context the human carries mentally = more things dropped between threads.
3. **What Karpathy/MemPalace users will hit:** Their "dump everything, search it" approach has no session state management at all. They'll hit this wall when they try to maintain multi-session, multi-project coherence. Seldon solving this cleanly is a differentiator.

---

## 2. Proposed Design

### Core Principle

**`seldon go` becomes the complete session bootstrap.** One command. No copy-paste. The graph provides everything a new session needs to resume work, across any project.

### What `seldon go` Should Load (Layered Context)

Borrowing the compaction hierarchy concept: cheapest/smallest context first, expensive/detailed on demand.

#### L0: Identity + Role (always loaded, ~100 tokens)
- Session type (Desktop planning vs. CC execution)
- Behavioral contract (what this session type can/cannot do)
- Project name and one-line description

#### L1: Current State (always loaded, ~200-400 tokens)  
- Graph stats (node count, relationship count)
- Open tasks (count + one-line summaries)
- Stale artifacts (count)
- Open issues (count + DO NOW quadrant items)
- CC tasks ready for execution (count + file paths)
- Documentation completeness percentage

#### L2: Session Context (always loaded, ~300-800 tokens)
- **Compressed handoff:** Not the full narrative. A structured summary: what was decided, what was deferred, what's next. Extracted from the latest handoff at write time (or computed from graph state changes since last closeout).
- **Cross-project alerts:** If other Seldon-managed projects have urgent items (DO NOW issues, stale artifacts blocking this project), surface them. Requires cross-project query capability (see Section 4).
- **Resolved gates:** Items explicitly marked "do not re-flag" (DG-2, DG-5, etc.) — prevents the re-investigation loop.

#### L3: Deep Context (on demand, loaded by request)
- Full handoff narrative (if the compressed version isn't sufficient)
- CC task specs (loaded when a CC session is about to execute one)
- Artifact provenance chains (loaded when working on specific results)
- Agent role definitions (loaded when invoking specialist workflows)

**Total bootstrap cost: ~600-1,300 tokens for L0-L2.** Compare to current: 3,000-5,000 tokens for pasted handoff + `seldon go` output.

### `seldon close` (Replaces Manual Handoff Writing)

The counterpart to `seldon go`. Runs at session end.

**What it does:**
1. **Structured state capture** → graph artifacts:
   - New decisions → DesignNote or ArchitecturalDecision artifacts
   - New tasks identified → ResearchTask artifacts (already possible via MCP)
   - CC tasks written → registered via `seldon cc register`
   - Items explicitly resolved → marked in graph with "do not re-flag" metadata

2. **Narrative summary** → handoff artifact in graph:
   - The narrative part of current handoffs (design rationale, strategic thinking, session story) becomes a `SessionHandoff` artifact type — or a `LabNotebookEntry` with enhanced properties.
   - Stored in the graph with timestamp, session scope, project(s) touched.
   - Compressed version auto-generated for L2 loading in next session.
   - Full version available at L3 on request.

3. **Thread rotation signal:**
   - Estimate remaining useful context window capacity.
   - If below threshold: "Recommend rotating to a new thread. State is captured. `seldon go` will resume cleanly."
   - This makes proactive rotation practical — you rotate when it's *optimal*, not when it's *forced*.

### CC Task Loading

When a CC session starts and runs `seldon go`:
- If there are ready CC tasks, they're listed with file paths.
- `seldon cc load <task-id-or-filepath>` loads the full spec into the session.
- No human copy-paste of task content. The graph knows what's ready; the session loads it.

---

## 3. Handoff Artifact Design

The handoff transitions from a loose markdown file to a graph-backed artifact.

### Option A: New `SessionHandoff` Artifact Type

```yaml
SessionHandoff:
  properties:
    session_date: datetime (required)
    projects_touched: list[string] (required)
    prior_handoff: artifact_id (optional)
    narrative: text (the full story)
    compressed: text (L2-loadable summary, auto-generated)
    decisions_made: list[string] (references to DesignNote/AD artifacts)
    tasks_created: list[artifact_id]
    tasks_completed: list[artifact_id]
    cc_tasks_written: list[artifact_id]
    do_not_reflag: list[string] (resolved items that should not be revisited)
    next_steps: list[string] (ordered priority)
  state_machine:
    current → superseded (when next handoff is created)
```

### Option B: Enhanced `LabNotebookEntry`

`seldon closeout` already creates a LabNotebookEntry. Add the structured fields above as properties. The LabNotebookEntry becomes the handoff *and* the session record.

**Recommendation:** Option A. LabNotebookEntry serves a different purpose (session audit log). SessionHandoff is about continuity — what the *next* session needs. Conflating them overloads the artifact type.

---

## 4. Cross-Project Visibility (The Wintermute Lite Question)

This is the AD-008 trigger. Three Seldon instances are running. Cross-project context is needed now.

### Minimal Viable Cross-Project

`seldon go --project X` queries project X's graph. But it could *also* query other known projects for:

- **Urgent items:** DO NOW issues in any project.
- **Blocking relationships:** If project A has a task that `blocks` something in project B (currently not possible — cross-project edges don't exist), surface it.
- **Recent activity:** "Project B was last touched 3 days ago, has 2 stale artifacts."
- **Shared terminology drift:** If a term in the shared ontology was updated, projects with stale replicas get flagged.

### Implementation Path

1. **`seldon.yaml` gets a `known_projects` list** — paths to other Seldon-managed repos.
2. **`seldon go` queries known projects at L2** — lightweight: just counts and urgent items. No full graph traversal.
3. **Cross-project edges deferred** — that's Wintermute territory. For now, the alert is "project B exists and has state X," not "project B's artifact Y relates to your artifact Z."

This is not Wintermute. This is Seldon acknowledging that projects don't exist in isolation and providing minimal cross-project awareness. Wintermute is the deep cross-project graph with entity resolution, semantic linking, and knowledge synthesis. This is just "hey, your other projects have stuff going on."

---

## 5. What This Changes

| Before | After |
|--------|-------|
| Human copies handoff between threads | `seldon go` loads everything from graph |
| Handoff is a loose markdown file | Handoff is a graph artifact with structured + narrative components |
| Session bootstrap: 3,000-5,000 tokens | Session bootstrap: 600-1,300 tokens (L0-L2) |
| No cross-project visibility | Basic cross-project alerts in L2 |
| Thread rotation is forced by degradation | Thread rotation is proactive, recommended by the system |
| CC tasks loaded by human copy-paste | CC tasks loaded from graph by reference |
| Resolved decisions get re-flagged | `do_not_reflag` list prevents re-investigation |

---

## 6. What This Does NOT Do

- Does NOT eliminate narrative handoffs. Strategic thinking and design rationale need prose. The narrative moves into the graph artifact but remains human-written prose.
- Does NOT build Wintermute. Cross-project alerts are shallow queries, not deep entity resolution or semantic linking.
- Does NOT auto-generate session plans. `seldon go` provides state; the human (with AI) decides what to do.
- Does NOT require changes to CC task file format. CC tasks remain immutable markdown files. The graph tracks their state alongside them.
- Does NOT change the Desktop/CC session split. Desktop still plans; CC still executes. The transport between them gets automated.

---

## 7. Sequencing

### Phase 1: Structured Closeout
- `seldon close` command that captures structured state to graph
- `SessionHandoff` artifact type in domain config
- Compressed summary auto-generation from structured fields
- `seldon go` loads L0-L2 from graph state + latest SessionHandoff

### Phase 2: Cross-Project Awareness
- `known_projects` in `seldon.yaml`
- `seldon go` L2 includes cross-project alerts
- Ontology staleness detection across projects

### Phase 3: CC Task Loading
- `seldon cc load` command
- `seldon go` in CC mode surfaces ready tasks
- CC session bootstraps from graph without human transport

### Phase 4: Thread Rotation Signal
- Context window estimation in `seldon close`
- Proactive rotation recommendation
- Rotation cost tracking (was the rotation worth it?)

---

## 8. Relationship to External Patterns

**MemPalace "wake-up":** ~170 tokens of identity + critical facts. Our L0 + L1 is the same concept but graph-backed and project-scoped instead of flat-file.

**Karpathy "wiki from folders":** The `seldon go` output *is* the wiki — but it's generated from graph state, not maintained by an AI scanning raw files. The provenance chain is the difference.

**Claude Code compaction hierarchy:** Cheapest context first (L0-L2 are cheap graph queries), expensive context on demand (L3 requires loading full artifacts). Same principle, applied to session bootstrapping instead of in-session context management.

**Claude Code CLAUDE.md hierarchy:** Enterprise → project → user → local. Our hierarchy is similar: Seldon system contract → project domain config → session state → ad-hoc context. `seldon go` assembles these layers; the human doesn't manually compose them.

---

## 9. Open Questions

1. **SessionHandoff vs. enhanced LabNotebookEntry:** Leaning toward separate artifact type. Worth discussion.
2. **Compressed summary format:** YAML? Prose with structure? AAAK-style compression (probably not, but worth considering for token density)?
3. **Cross-project query performance:** Querying N Neo4j databases on every `seldon go` adds latency. Cache? Background refresh?
4. **Thread rotation threshold:** What's the right context window utilization percentage to recommend rotation? Needs empirical data.
5. **Handoff file migration:** Existing `handoffs/` directory has valuable narrative history. Migrate to graph artifacts or leave as historical record?

---

*This design note captures the vision for graph-backed session continuity. It's the natural extension of AD-021 and the missing piece that makes `seldon go` a true session bootstrap rather than a read-only orientation tool.*
