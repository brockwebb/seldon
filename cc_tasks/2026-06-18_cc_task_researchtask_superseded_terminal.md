# CC Task — Add `superseded` terminal state to ResearchTask state machine

**Date:** 2026-06-18
**Type:** CC task (Seldon engine change)
**Author:** Brock (via Desktop design session)
**Status:** ready
**Repo:** `/Users/brock/Documents/GitHub/seldon/` (the Seldon engine — NOT fss-policy-kg)

---

## Problem

`ResearchTask` has no honest terminal state for a task that is overtaken/obsoleted
*before* it completes. When work pivots and a task is no longer relevant, the only
options today are to mislabel it `completed` (false — it was never done) or leave it
stuck in `in_progress`/`accepted` forever (dishonest task graph). This has now bitten
twice: tasks `fe5ba7f7` (closed SUPERSEDED with no real terminal) and `6d9cfb9a` (stuck).

`ArchitecturalDecision` already has exactly this pattern (`superseded: []` terminal,
reachable from `accepted`). This task applies the same pattern to `ResearchTask`.

## Scope / design (decided — do not redesign)

Add `superseded` as a **terminal** state (`superseded: []`) reachable from the
**active, non-finished** states only:

- `proposed → superseded` ✅
- `accepted → superseded` ✅
- `in_progress → superseded` ✅
- `blocked → superseded` ✅
- `completed → superseded` ❌ (do NOT add — a genuinely completed task must keep its
  completion record; supersession is for tasks overtaken mid-flight)
- `verified → superseded` ❌ (terminal already; do not touch)
- `rejected → superseded` ❌ (terminal already; do not touch)

Rationale for the asymmetry: supersession means "this was overtaken before it finished."
Relabeling a `completed` or `verified` task as superseded would corrupt the honest
completion history, which is the whole point of the state machine.

## Files to change

### 1. `seldon/domain/research.yaml` — the state machine
Locate the `ResearchTask` block under `state_machines:`. Current:

```yaml
  ResearchTask:
    proposed: [accepted, rejected]
    accepted: [in_progress]
    in_progress: [completed, blocked]
    completed: [verified]
    blocked: [in_progress]
    verified: []
    rejected: []
```

Change to:

```yaml
  ResearchTask:
    proposed: [accepted, rejected, superseded]
    accepted: [in_progress, superseded]
    in_progress: [completed, blocked, superseded]
    completed: [verified]
    blocked: [in_progress, superseded]
    verified: []
    rejected: []
    superseded: []
```

**Check for other domain configs** that define a `ResearchTask` state machine
(`seldon/templates/paper.yaml`, `blank.yaml`, any project-level `seldon.yaml` that
overrides it). If `ResearchTask` is redefined there, apply the same change for
consistency. If it inherits from research.yaml, no change needed. Report what you found.

### 2. MCP docstring — `seldon/mcp_server.py`
Find the `seldon_task_update` tool definition. Its docstring enumerates valid states:
`(accepted, in_progress, completed, verified, blocked)`. Add `superseded` to that list.
The transport already passes `state` straight through to `validate_transition`, so no
logic change is needed — only the docstring, so the enumerated list isn't lying.

Also check `seldon_task_close` — its docstring says it walks "proposed→accepted→
in_progress→completed". It should NOT auto-route through superseded (close = completed
path is correct). Leave its behavior alone; just confirm it doesn't break. Note: a
superseded transition is a deliberate `seldon_task_update --state superseded`, never an
auto-close.

### 3. Tests — `tests/test_state.py` and/or `tests/test_task.py`
Add coverage:
- `proposed/accepted/in_progress/blocked → superseded` each SUCCEED.
- `completed → superseded` and `verified → superseded` each raise
  `InvalidStateTransition`.
- `superseded` is terminal: any transition out of `superseded` raises
  `InvalidStateTransition` (terminal-state branch — empty valid_transitions).

Mirror the existing `ArchitecturalDecision` superseded tests if present; reuse the same
assertion style already in the file. Do not invent a new test harness.

### 4. `seldon task list --open` semantics — VERIFY, do not assume
In `seldon/commands/task.py`, `OPEN_STATES = ["proposed", "accepted", "in_progress",
"blocked"]`. `superseded` is terminal and correctly NOT in that list, so superseded tasks
drop out of `--open` automatically. Confirm this is the case; no change expected. If there
is any other place that enumerates "closed/terminal" task states explicitly, make sure
`superseded` is treated as terminal there too.

## Migration — the two stuck tasks

These live in the **fss-policy-kg** project graph, not the Seldon engine repo. Do this
step from that project (`/Users/brock/Documents/GitHub/icsp_notebook`), AFTER the engine
change above is installed (`pip install -e .` in the seldon repo so the new transition is
valid).

1. Inspect current state of each — do NOT assume:
   - `fe5ba7f7` (handoff says "closed SUPERSEDED — force-fix root cause, not the flatten
     hypothesis"; may currently be mislabeled `completed` or stuck).
   - `6d9cfb9a` (handoff says stuck/overtaken).
   Use `seldon_query` (MUST pass `project_dir`) or `seldon task show <id>` to read actual
   current state for each.
2. For each task, if it is in an active non-terminal state (`proposed`/`accepted`/
   `in_progress`/`blocked`), transition it to `superseded` via
   `seldon_task_update --state superseded --project_dir <fss-policy-kg>`.
3. **Edge case — if either is already `completed`:** it CANNOT go to `superseded` under
   the new rules (by design). Do NOT force it. Stop and report to operator: the task was
   mislabeled `completed` and needs a manual decision (the honest fix may require an
   event-log correction, which is operator territory, not an auto-migration). Flag it;
   don't paper over it.
4. Report final state of both tasks.

## Acceptance criteria

- [ ] `research.yaml` ResearchTask SM updated exactly as specified (4 active states gain
      `superseded`; `completed`/`verified`/`rejected` unchanged; `superseded: []` added).
- [ ] Other domain configs checked; ResearchTask SM consistent across them (report findings).
- [ ] `seldon_task_update` docstring lists `superseded`.
- [ ] Tests added and passing: 4 valid transitions, 2 forbidden (`completed`/`verified`),
      terminal-out forbidden. Full suite still green (was 341 tests; no regressions).
- [ ] `pip install -e .` re-run so the engine change is live.
- [ ] fss-policy-kg: both stuck tasks inspected, migrated to `superseded` if eligible, or
      flagged if already `completed`. Final states reported.
- [ ] Commit on main with message referencing this task. Do NOT push (operator pushes).

## Out of scope
- No change to `seldon_task_close` behavior (close = completed path stays).
- No retroactive supersession of any task already `completed`/`verified`.
- No new CLI command (`seldon task supersede` sugar is NOT wanted — `update --state
  superseded` is sufficient; adding sugar is scope creep).
