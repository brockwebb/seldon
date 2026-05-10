# Design Note: Authoring Workflow Evolution — Direct Creation, Task Immutability, Session Continuity, and Editing Friction

**Date:** 2026-04-20
**Author:** Desktop session (Opus 4.6, claude.ai)
**Status:** Draft — captures four related workflow problems and candidate solutions
**Context:** Synthesized from operator observations during SFV paper revision cycle (April 2026). Multiple friction points converged into a clear pattern: the system optimized for auditability at the cost of authoring velocity.

---

## 1. Problem Statement

Four related problems have emerged from production use of the Seldon-managed authoring workflow:

**P1: Wasteful creation pattern.** Desktop sessions compose content (lab notes, document sections, design notes), then write a CC task containing that content verbatim, then CC reads the task and writes the content to disk. The content traverses three representations (desktop context → task file → target file) when one would suffice. This doubles the token cost and adds a round-trip for zero value.

**P2: CC task immutability is unenforced.** The behavioral contract says tasks are immutable once written. Agents violate this because it's a prose rule, not a structural constraint. As the system evolves toward less visible task execution, undetected task mutations become a data integrity risk.

**P3: Session continuity friction.** Briefings and closeouts are hand-authored markdown documents. The graph knows what's open, what changed, what's blocked, but the operator reads a prose document instead of querying that state. `seldon go` should produce the briefing from graph state. `seldon closeout` should capture session state back to the graph. Handoff documents should be generated projections, not primary artifacts.

**P4: Editing friction tax.** A one-word fix (e.g., "Recoverable" → "Potentially fatal") currently requires: notice problem → write CC task spec → CC reads task → CC makes edit → CC runs glossary/sync/build → review PDF. This is 5-10 minutes and hundreds of thousands of tokens for a single-word change. The ceremony exists to prevent untracked mutations, but the cure is worse than the disease for small edits. Worse, tasks for prose edits introduce unintended drift: CC rewrites the operator's intent through its own voice.

These four problems share a root cause: the system was designed around a strict desktop-delegates/CC-executes separation that treats all file mutations as equally risky. In practice, *creating* a new file and *editing* an existing tracked file are fundamentally different operations with different risk profiles. Similarly, a one-word mechanical fix and a multi-paragraph prose addition are fundamentally different operations that should not require the same ceremony.

---

## 2. P1 Resolution: Desktop Direct Creation

### Current pattern (wasteful)

```
Desktop composes content
  → Desktop writes CC task containing content verbatim
    → CC reads task, writes content to file
      → CC registers artifact in graph
```

### Proposed pattern

```
Desktop composes content
  → Desktop writes file directly (Filesystem MCP)
  → Desktop registers artifact (seldon_cc_register or seldon artifact create)
  → Desktop writes CC task ONLY for post-creation QC
    (glossary check, ontology sync, em-dash sweep, graph edge wiring)
```

### Behavioral contract amendment

The current rule in `go.py` `_ROLE_SECTION`:

> Desktop sessions must not directly edit tracked source files or run compliance audits.

Amended to:

> Desktop sessions may CREATE new files and register them as artifacts. Desktop sessions must not EDIT existing tracked source files or run compliance audits. Creation ≠ mutation. The distinction: a new file has no prior state to corrupt; an edit to an existing file can introduce untracked drift.

The carve-out is narrow and principled:
- Desktop CAN: create new files, register new artifacts, write CC tasks for QC follow-up
- Desktop CANNOT: edit existing tracked files, run glossary/audit/build cycles, modify graph state beyond artifact registration

### What this saves

For a typical lab note or design note: eliminates one CC task file, one CC session, and the token cost of CC reading the task and writing the content. The content goes from desktop context to disk in one step.

---

## 3. P2 Resolution: CC Tasks as First-Class Graph Artifacts

### Current state

CC tasks are markdown files in `cc_tasks/`. Immutability is a prose rule in the behavioral contract and userMemories. Agents sometimes violate it. There is no structural enforcement.

### Proposed design

CC tasks become first-class artifacts in the Seldon graph with a state machine:

```
draft → registered → executing → completed
                  ↘ superseded (if a new task replaces it)
```

**State transitions and immutability rules:**

| Transition | Who | What happens |
|---|---|---|
| draft → registered | `seldon cc register` | File hash captured. File becomes immutable. |
| registered → executing | CC agent (implicit on task start) | Graph records execution start timestamp. |
| executing → completed | `seldon cc complete` | Graph records completion. File hash verified against registration hash. |
| registered → superseded | Desktop (explicit) | New task created with `supersedes` edge to original. Original file untouched. |

**Immutability enforcement:**

When `seldon cc complete` runs, it computes the current file hash and compares to the hash stored at registration. If they differ, the completion fails with an error:

```
ERROR: Task file has been modified since registration.
  Registered hash: abc123...
  Current hash:    def456...
  Task immutability violated. File must not be edited after registration.
  If changes are needed, create an addendum or superseding task.
```

This is structural enforcement, not a prose rule. The graph catches violations that agents can't be trusted to prevent.

**Addendum pattern:**

When a registered task needs modification:

1. Create a new file: `cc_tasks/YYYY-MM-DD_<original_name>_addendum.md`
2. Register it with an `amends` edge to the original task
3. CC reads both the original task and the addendum
4. Original file is never touched

**Superseding pattern:**

When a registered task is replaced entirely:

1. Create a new task file
2. Register it with a `supersedes` edge to the original
3. Transition original to `superseded` state
4. CC executes only the new task

### Schema additions

New artifact type: `CCTask` (or reuse `ResearchTask` with a `task_type: cc_task` property — author judgment on whether the distinction warrants a new type).

New edge types:
- `amends` — addendum → original task
- `supersedes` — new task → old task

New system property on CCTask:
- `file_hash` — SHA-256 of file content at registration time

### Handoffs as first-class artifacts

Handoff documents follow the same pattern. Type: `Handoff` (or `SessionHandoff`). State machine: `draft → active → archived`. The `active` handoff is the one `seldon go` reads. When a new handoff is written, the previous one transitions to `archived`.

Edge types:
- `closes_session` — handoff → session (if sessions become trackable)
- `opens_session` — handoff → next session
- `references` — handoff → any artifact mentioned in the handoff

---

## 4. P3 Resolution: Graph-Driven Session Continuity

### `seldon go` evolution

Currently: reads `_ROLE_SECTION` from `go.py`, prints it, tells the agent what project it's in.

Proposed: `seldon go` becomes the briefing engine. It queries the graph and produces a structured briefing:

```
$ seldon go --project-dir /path/to/project

PROJECT: sfv-paper
ROLE: Desktop (planning, design, writing)
LAST SESSION: 2026-04-19 (handoff: 2026-04-19_session_close.md)

OPEN TASKS (3):
  - [e90ce07b] Glossary violation fixes — registered, not started
  - [fef02b71] Bib corrections — registered, not started
  - [027e1a43] Batch2 citations — executing

STALE ARTIFACTS (1):
  - PaperSection:09_demonstration — content_hash changed since last sync

OPEN ISSUES (2):
  - ISS-004: INC-002 header severity mismatch (low)
  - ISS-007: fcsm2025aiready uncited in S08 (low)

RECENT CHANGES (last 48h):
  - 6 section files edited (run-003 must/should-fix revisions)
  - Run-005 audit completed (gemini-3-flash-preview)
  - 4 new findings surfaced

CONTEXT SOURCES:
  - claudemem: cross-thread memory available
  - wintermute: knowledge base MCP available
  - graph: 223 artifacts, 187 edges
```

The briefing is a graph query, not a document read. The handoff document supplements it with narrative context that the graph can't capture (operator intent, strategic decisions, emotional state of the work).

### `seldon closeout` evolution

Currently: doesn't exist as a command. The operator writes a handoff markdown file manually.

Proposed: `seldon closeout` captures session state:

1. Queries the graph for what changed since `seldon go` was last run
2. Generates a structured closeout:
   - Tasks completed this session
   - Tasks created this session
   - Artifacts created/modified
   - Issues opened/closed
   - Files changed (from git diff if available)
3. Prompts for operator narrative (optional freeform notes)
4. Writes the handoff document as a generated artifact
5. Registers it in the graph with edges to all referenced artifacts

The handoff document becomes a *generated projection* with an optional narrative addendum, not a hand-authored primary artifact.

### Context sources at session start

`seldon go` should also indicate what context sources are available:

- **claudemem**: Cross-thread memory from Claude's memory system. Provides context that survives across conversations but is not authoritative (the graph is).
- **Wintermute MCP**: Knowledge base search for cross-project context. Available when the MCP server is running.
- **Graph**: The source of truth. Task states, artifact states, edges, provenance.

The briefing engine doesn't replace any of these. It synthesizes the graph state into a human-readable summary that the operator (and the agent) can consume in seconds.

---

## 5. P4 Resolution: Editing Friction Reduction

This is the most complex problem because it sits at the intersection of auditability (need to track changes) and velocity (need to make changes fast).

### 5.1 Quick-fix CLI: `seldon paper fix`

For mechanical edits (find/replace, delete sentence, add citation markup):

```bash
seldon paper fix <file> --find "Recoverable" --replace "Potentially fatal"
seldon paper fix <file> --find "(T1, Recoverable)" --replace "(T1, Potentially fatal)"
```

What it does:
1. Makes the edit
2. Captures a before/after diff as an event in the JSONL log
3. Runs the mandatory build cycle (glossary check → sync → build --no-render)
4. Reports success/failure

No CC task. No CC session. The edit is tracked through the event log, not through task ceremony. The event includes: timestamp, file, diff, actor (human/desktop), and a one-line description.

For safety: `seldon paper fix` requires `--confirm` for edits that change more than N characters (configurable threshold). Small mechanical fixes auto-apply. Large changes prompt for confirmation.

### 5.2 Lightweight edit mode: `seldon paper edit`

For edits that are too complex for find/replace but too small for a full CC task:

```bash
seldon paper edit <file>
```

Opens the file in the configured editor ($EDITOR). On save:
1. Computes diff against the registered content hash
2. Captures the diff as an event
3. Runs the mandatory build cycle
4. Updates the content hash in the graph

This is the "desktop can edit existing files" exception to the behavioral contract. It's allowed because the event log captures exactly what changed, providing the same auditability as a CC task but without the ceremony.

The behavioral contract amendment for this:

> Desktop sessions may use `seldon paper edit` to make tracked edits to existing files. The edit is captured as an event in the JSONL log with full diff. This is the ONLY mechanism for desktop edits to tracked files. Direct file modification outside `seldon paper edit` remains prohibited.

### 5.3 Visual editing interface (longer-term)

The raw markdown editing problem — noise that disrupts concentration, inability to quickly scan and fix issues — points toward a visual interface. Several open-source options exist:

**Candidate A: SilverBullet** (silverbullet.md)
- Markdown files on disk, Lua-scriptable, offline-first PWA
- Live preview, WYSIWYG-ish editing, bi-directional links
- Self-hosted, single Go binary (now Deno-based)
- Could point directly at `paper/sections/` directory
- Lua scripting could integrate with Seldon CLI (run glossary check on save, etc.)
- Risk: another tool to maintain. But it reads/writes plain markdown files, so it's additive, not replacing.

**Candidate B: Gollum** (github.com/gollum/gollum)
- Git-backed wiki, every save is a commit
- Markdown rendering with live preview
- Ruby-based, runs locally, lightweight
- Natural git integration means changes are versioned automatically
- Simpler than SilverBullet but less programmable

**Candidate C: Wiki.js**
- Full-featured wiki with WYSIWYG, markdown, and visual editors
- Version control built in
- Heavier infrastructure (Node.js + database)
- Probably overkill for a single-author research workflow

**Candidate D: Custom Seldon paper server**
- A lightweight Flask/FastAPI app that:
  - Renders paper sections as HTML with live preview
  - Provides inline editing (click to edit, save triggers `seldon paper fix` or event capture)
  - Runs the build cycle on save
  - Shows QC violations inline (like a linter in an IDE)
  - Integrates with the graph to show cross-references, citation status, etc.
- Most work to build. Most integrated with the existing system. Highest long-term value.
- Could start as a read-only viewer (renders markdown, shows QC status) and add editing later.

**Assessment:**

| Option | Effort | Integration | Editing quality | Maintenance |
|---|---|---|---|---|
| SilverBullet | Low (adopt) | Medium (Lua hooks) | Good WYSIWYG | Low |
| Gollum | Low (adopt) | Low (git-native) | Basic | Low |
| Wiki.js | Medium (deploy) | Low | Best WYSIWYG | Medium |
| Custom server | High (build) | Best | Custom | Depends on scope |

**Recommendation:** Start with the quick-fix CLI (5.1) and lightweight edit mode (5.2) — they're small, immediate, and eliminate the worst friction. Evaluate SilverBullet as the visual layer — it reads plain markdown from disk, is scriptable, and doesn't require changing any file structure. If SilverBullet proves insufficient, the custom server becomes a future engineering investment with a clearer requirements picture from having used a visual tool.

---

## 6. Implementation Sequence

### Phase 1: Behavioral contract + quick fixes (immediate)

1. Amend `go.py` `_ROLE_SECTION` for desktop direct creation
2. Implement `seldon paper fix` CLI command (find/replace with event capture)
3. Update CC task registration to capture file hash
4. Add hash verification to `seldon cc complete`

### Phase 2: Task and handoff artifact types (near-term)

5. Add `CCTask` (or extend `ResearchTask`) with file_hash and state machine
6. Add `amends` and `supersedes` edge types to domain config
7. Add `Handoff` artifact type
8. Implement addendum pattern

### Phase 3: Session continuity (near-term)

9. Evolve `seldon go` to query graph state for briefing
10. Implement `seldon closeout` command
11. Generate handoff documents from graph state + operator narrative

### Phase 4: Visual editing (when the itch gets bad enough)

12. Evaluate SilverBullet pointed at `paper/sections/`
13. Configure Lua hooks for glossary check / sync on save
14. If insufficient, scope the custom paper server

---

## 7. Decisions Required

**D1:** Should `CCTask` be a new artifact type or a `task_type` property on `ResearchTask`? New type is cleaner separation. Property reuse avoids schema proliferation. Leaning toward new type because the state machine and immutability semantics are fundamentally different from ResearchTask.

**D2:** Should `seldon paper fix` auto-run the full build cycle, or just the edit + event capture? Full cycle is safer (catches downstream breakage immediately) but slower. Edit-only is faster but defers breakage detection. Leaning toward full cycle with a `--no-build` escape hatch.

**D3:** Should `seldon paper edit` be available from desktop sessions, or CC-only? The whole point is reducing friction for the operator. If it's CC-only, it doesn't solve P4. Leaning toward desktop-allowed with the event capture as the auditability mechanism.

**D4:** How does the hash verification interact with git? If the file is committed between registration and completion, the hash changes are tracked by git. Should `seldon cc complete` check git status as well as file hash? Or is file hash sufficient?

**D5:** Visual editor evaluation — should this be a Seldon research note (evaluate SilverBullet) or a time-boxed spike (install it, point it at the SFV paper, use it for a week)?

---

## 8. Relationship to Existing ADs

| AD | Relationship |
|---|---|
| AD-019/020 (Audit pipeline) | Unaffected. Agent-based audits remain as-is. The copy-editor gate (CE-01 through CE-08) slots in as Tier 0 below the agent layer. |
| AD-022 (CLI-default, MCP-exception) | Reinforced. New commands (`paper fix`, `paper edit`, `closeout`) are CLI. |
| AD-023 (Sleep functions) | Unaffected. |
| AD-024 (Observability) | Extended. Event capture for `paper fix` and `paper edit` feeds the observability substrate. |

---

*This design note captures the operator's workflow friction as of April 2026. The solutions are ordered by effort and impact. Phase 1 is actionable now. Phases 2-4 depend on Phase 1 validation.*
