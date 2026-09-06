# RESULT — `precedes`: task ordering as a first-class relationship

**Date:** 2026-09-06
**Task:** `cc_tasks/2026-09-06_task_precedes_relationship.md`
**Addenda:** none found. Globbed `cc_tasks/2026-09-06_task_precedes_relationship_ADDENDUM*.md` before starting; no siblings exist.
**AD:** `docs/design/AD-029_task_precedence.md`
**Domain version:** `research.yaml` `0.2 → 0.3`
**Tests:** 1516 passed, 0 failed (72 of them new, in `tests/test_precedence.py`).
**`seldon verify`:** all 12 checks pass, exit 0.

---

## 1. The command that applies a chain

```
$ seldon task chain d3405105 4d5cb106 4b6d8506 --reason 'week-1 order'
Chained: d3405105 → 4d5cb106 → 4b6d8506
  + d3405105 → 4d5cb106
  + 4d5cb106 → 4b6d8506
  reason: week-1 order
```

Ids may be prefixes, as with every other task command. Re-running the same chain
writes nothing and reports `= a → b (already recorded)`, so a chain is safe to
keep in a runbook. `seldon task precede A B` is the two-task case;
`seldon task unprecede A B` removes one edge.

The MCP equivalents are `seldon_task_chain(task_ids=[...])`,
`seldon_task_precede(before_id, after_id)` and
`seldon_task_unprecede(before_id, after_id)` — same arguments, same errors,
because all six entry points call one implementation in
`seldon/core/precedence.py`.

A cycle is refused and the error names the closing path:

```
$ seldon task precede 4b6d8506 d3405105
Error: 'precedes' must stay acyclic: 4b6d8506 → d3405105 would close the cycle
       4b6d8506 → d3405105 → 4d5cb106 → 4b6d8506.
```

Starting a task ahead of its predecessor warns and proceeds:

```
$ seldon task update 4d5cb106 --state accepted
Warning: 4d5cb106 → accepted with 1 unsatisfied predecessor: d3405105 [proposed].
         'precedes' is advisory — proceeding.
Updated Task: 4d5cb106...
  state: proposed → accepted
```

`seldon task list --open`, same graph:

```
  ID         STATE          BLOCKS  DEPS  WAITS_ON      CLAIM   DESCRIPTION
--------------------------------------------------------------------------------
▸ d3405105   proposed       0       0     -                     Ingest the week-1 corpus
  4d5cb106   proposed       0       0     d3405105              Extract entities
  4b6d8506   proposed       0       0     4d5cb106              Score bridges

▸ = ready: open, with no unsatisfied predecessor.
```

## 2. Briefing rendering on the fixture

The fixture the task file specifies — two chains and one isolated task, with the
first chain's head completed. This is `seldon go`'s Project State section,
rendered by the same `_format_project_state` the test asserts on:

```
## Project State

**Open Tasks:** 5
- [proposed] Extract entities
- [proposed] Score bridges
- [proposed] Freeze the calibration set
- [proposed] Run the G1 gate
- [proposed] Rewrite the ontology README

**Next ready:** 3
- cf5d6240 [proposed] Extract entities
- 1ff67693 [proposed] Freeze the calibration set
- 3f06f503 [proposed] Rewrite the ontology README

**Chains:** 2
- 10bfdc32 [completed] → cf5d6240 [proposed] → 17699011 [proposed]
    - 10bfdc32  Ingest the week-1 corpus
    - cf5d6240  Extract entities
    - 17699011  Score bridges
- 1ff67693 [proposed] → 4a972460 [proposed]
    - 1ff67693  Freeze the calibration set
    - 4a972460  Run the G1 gate
```

The isolated task appears in **Next ready** and in **Open Tasks** but not under
**Chains**: a component of one node is not a chain. `seldon briefing` renders the
same two sections as `NEXT READY` and `CHAINS`.

## 3. Domain version

`research.yaml` is now `version: "0.3"`, up from `0.2`.

## 4. Premises the task file got wrong

**One, and it is small.** §1 said to "bump the domain version per its
convention." There is no convention: `research.yaml` has carried `0.2`
unchanged since the file was created (`b3aee86`), through every additive schema
change since including AD-028's, and no code path has ever read the string.
`0.3` therefore *establishes* the convention rather than applying one —
**additive schema change bumps the minor version** — and AD-029 §"Notes on the
originating task file" records that so the next AD has something to follow.
`tests/test_domain.py` pins the value so a future change is deliberate.

Everything else in the premise checked out against the file: `superseded_by` was
indeed the only `ResearchTask → ResearchTask` edge, `blocks` accepted exactly
`[Result, PaperSection, Figure]`, and `depends_on` exactly
`[Result, DataFile, Script]`.

## 5. Decisions the task file left open

Three points the spec did not settle, decided on the grounding and recorded in
the AD rather than escalated:

**`rejected` is not a satisfied predecessor.** §0 enumerated `completed` /
`verified` as terminal-complete and added `superseded` / `withdrawn` as
satisfied. `rejected` is the one terminal state it did not mention, and §4 asked
for a test across all terminal states, so the gap had to be closed one way or
the other. It is treated as **unsatisfied**: rejected work was refused, not
resolved, and a chain hanging off one is a plan that needs revising. Because
enforcement is advisory this blocks nothing — it shows up in `waits_on` and in
the briefing, and `seldon task unprecede` retires the edge. AD-029 §3.

**The cycle check reads the graph, not the log.** §2 said "against the
event-sourced state". The Neo4j graph *is* the projection of that state, every
other command reads it, and `seldon verify --replay` is the existing instrument
for the case where the two have diverged. Replaying the log per edge write would
be a second, slower source of truth for one reachability query. AD-029 §7.

**A branching component is not rendered as a line.** §3 asked for each component
as `A → B → C`. That is faithful only when the component is a simple path;
rendering a fan-out that way asserts an ordering the graph does not contain. A
branching component is labelled and its edges listed one per line instead.
AD-029 §5.

## 6. Two things built slightly wider than the letter of the spec

Both disclosed rather than buried:

**The DAG gate sits in `core.artifacts.create_link`, not in the CLI.** §2 put the
cycle check on the write paths it named. Placing it at the shared writer instead
means `seldon link create` reaches it too — otherwise that command would have
remained an open back door for authoring a cycle, and `seldon verify` would have
been the only thing standing between the graph and an unanswerable readiness
query. Test: `test_the_guard_also_covers_the_generic_link_command`.

**`seldon_task_list` and `seldon briefing` render readiness too.** §3 named
`seldon task list` and `seldon go` / `seldon_go`. A Desktop thread picking work
calls `seldon_task_list`, and a terminal session runs `seldon briefing`; leaving
either blind to readiness would reintroduce, at those two surfaces, exactly the
"the plan lives somewhere other than the graph" defect this task exists to
close. Both read the same `precedence_view()` as the two named surfaces — there
is one computation of *ready*, not four.

## 7. What was built

| Area | Change |
|---|---|
| `seldon/domain/research.yaml` | `precedes` relationship; version `0.3` |
| `seldon/domain/loader.py` | `RelationshipConfig.cardinality` / `.inverse` / `.properties`; inverse-collision validator; `validate_relationship_properties` (opt-in by declaration) |
| `seldon/core/precedence.py` | **new** — invariants, cycle detection (Kahn + DFS extraction), readiness, chains, write paths, renderers |
| `seldon/core/artifacts.py` | `create_link` runs the DAG gate and edge-property validation; `transition_task` returns advisory warnings; `walk_to_completed` gains an `on_warning` sink |
| `seldon/commands/task.py` | `task precede` / `chain` / `unprecede`; `WAITS_ON` column and `▸` ready marker; warnings to stderr |
| `seldon/mcp_server.py` | `seldon_task_precede` / `_chain` / `_unprecede`; readiness in `seldon_task_list`; warnings in `_update` and `_close` |
| `seldon/commands/session.py` | `precedence` block in briefing data; `NEXT READY` and `CHAINS` in `seldon briefing` |
| `seldon/commands/go.py` | **Next ready** and **Chains** after open tasks |
| `seldon/commands/verify.py` | check 9, **Precedence** — cycles, self-loops, illegal endpoints |
| `tests/test_precedence.py` | **new** — 72 tests |
| `docs/design/AD-029_task_precedence.md` | **new** |
| `CLAUDE.md` | AD-029, the three CLI commands, the three MCP tools, the multi-task-plan rule |

Test coverage maps to §4 of the task file: domain load; cycle rejection with the
named path; self-loop rejection; the satisfied-predecessor rule parameterised
over **all nine** ResearchTask states; the `task list` ready marker; briefing
rendering on the two-chains-plus-isolated-task fixture; CLI/MCP parity (same
edges, byte-identical error text, distinct recorded actors); and replay — a log
containing `precedes` events rebuilds a graph that is identical *and* answers
readiness identically.

`seldon/core/sync.py` needed no change: `link_created` / `link_removed` already
project generically, so these edges replay for free. That was verified, not
assumed.

## 8. One defect observed in passing, not fixed

`seldon task show <prefix>` does not resolve id prefixes — it passes the
argument straight to `get_artifact`, so `seldon task show 505f4c61` reports
"Task '505f4c61' not found" for a task that exists. Every other task command
(`update`, `close`, `precede`, `unprecede`, `withdraw`, `supersede`) resolves
prefixes through `resolve_artifact_id`. Out of scope for this task and left
alone; worth its own one-line fix.

## 9. Graph state

- CC task `012a1a36` (this task file): `proposed → completed` via
  `seldon cc complete`.
- ResearchTask `505f4c61` (the originating domain-model defect):
  `proposed → accepted → in_progress → completed`, with the RESULT named as
  evidence in the close note.

## 10. Not done, per §5

ai-readiness-kg's week chain was not migrated. That is one `seldon task chain`
invocation in that repo now that this has shipped, and Desktop dispatches it.
No changes were made to `blocks` or `depends_on` semantics.
