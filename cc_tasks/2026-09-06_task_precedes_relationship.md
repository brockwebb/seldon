# CC Task — `precedes`: task ordering as a first-class relationship

**Date:** 2026-09-06
**Project:** seldon
**Authored by:** Desktop session (ai-readiness-kg `6b742c1e` RESULT §5, seldon ResearchTask `505f4c61`)
**Premise:** `seldon/domain/research.yaml` has no `ResearchTask → ResearchTask` relationship other than `superseded_by`. `blocks` accepts `[Result, PaperSection, Figure]`; `depends_on` accepts `[Result, DataFile, Script]`. A multi-task plan therefore cannot be stored, validated, or shown by `seldon go`; ai-readiness-kg is carrying its week chain as a snapshot DataFile plus prose in each task's description, which is exactly the drift the graph exists to prevent.
**Zero model spend.**

**Immutable once written. Changes require a new task file or an `_ADDENDUM-NN.md` sibling. Glob and read all siblings `2026-09-06_task_precedes_relationship_ADDENDUM*.md` before starting.** Read CLAUDE.md and the ontology/domain conventions used by `superseded_by` (the 2026-06-18 task and its RESULT) before touching the domain file.

---

## 0. Semantics and prior art (record in the AD)
- Relationship: `precedes` — `A precedes B` means B is not expected to leave `proposed` until A is terminal-complete (`completed` or `verified`); `superseded` / `withdrawn` predecessors are treated as satisfied (the work was replaced, not pending). This is **finish-to-start** dependency, the default in scheduling practice (PMBOK precedence diagramming; Kelley & Walker 1959 critical path).
- Invariant: the `precedes` subgraph is a DAG. Reject any write that would create a cycle (Kahn 1962 topological sort as the check). Self-loops rejected.
- `precedes` is advisory for `seldon go` and `task list`, and **enforced only as a warning** on state transitions: moving B to `accepted`/`in_progress` with an unsatisfied predecessor emits a warning and proceeds. Gates bind the machine, not the operator (ai-readiness-kg CLAUDE.md doctrine); the operator may reorder.

## 1. Domain
Add `precedes` to `seldon/domain/research.yaml` with both endpoint types `ResearchTask`, cardinality many-to-many, and a `reason` property (optional, free text). Add the inverse read-name `preceded_by` for queries; store one direction only. Bump the domain version per its convention. AD entry per the ADR format in the repo (next AD number).

## 2. Write paths
- CLI: `seldon task precede <A> <B> [--reason ...]` and `seldon task unprecede <A> <B>`; both accept id prefixes as other task commands do. `seldon task chain <A> <B> <C> ...` writes the consecutive pairs in one call.
- MCP parity: `seldon_task_precede`, `seldon_task_unprecede`, `seldon_task_chain` in `seldon-mcp`, same arguments, same errors. The CLI/MCP parity test that exists for `task close` extends to these.
- Cycle check runs against the event-sourced state before the event is appended; on rejection the error names the path that would close the cycle.

## 3. Read paths
- `seldon task list --open` gains a column: `waits_on` (unsatisfied predecessors, ids) and a marker for **ready** = open with no unsatisfied predecessor.
- `seldon go` / `seldon_go` briefing: after open tasks, render **"Next ready"** (ready tasks, in the order they were created) and **"Chains"**: each connected component of the `precedes` subgraph as `A → B → C` with each node's state. Components of one node are not rendered as chains.
- `seldon verify` gains a check: `precedes` DAG acyclic; every endpoint exists; no edge from a terminal task to itself.

## 4. Tests
Domain load; cycle rejection with the named path; self-loop rejection; satisfied-predecessor rule for all terminal states; `task list` ready marker; briefing rendering on a fixture with two chains and one isolated task; CLI/MCP parity; replay: a log containing `precedes` events rebuilds identical state.

## 5. Not in scope
Migrating ai-readiness-kg's chain — that is one `seldon task chain` invocation in that repo after this ships, and Desktop dispatches it. No changes to `blocks` / `depends_on` semantics.

## 6. Reporting
RESULT: `cc_tasks/2026-09-06_task_precedes_relationship_RESULT.md`. Lead with the exact command that applies a chain, then the briefing rendering on the fixture, then what the domain version became. State every premise this task got wrong. Full test suite, `seldon verify` on the seldon repo itself, `seldon cc complete`, commit, push. Close ResearchTask `505f4c61` as completed with this RESULT as evidence.
