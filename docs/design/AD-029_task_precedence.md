# AD-029: `precedes` — Task Ordering as a First-Class Relationship

**Date:** 2026-09-06
**Status:** Accepted
**Origin:** `cc_tasks/2026-09-06_task_precedes_relationship.md`, closing Seldon ResearchTask `505f4c61`. Defect surfaced by ai-readiness-kg (`6b742c1e` RESULT §5).
**Related:** AD-028 (ResearchTask terminal semantics — this AD reads its terminal states); AD-013 (domain property schemas); AD-022 (CLI default, MCP for external surfaces — why every write path shares one implementation).

## Context

`seldon/domain/research.yaml` had no `ResearchTask → ResearchTask` relationship
except `superseded_by`, which records replacement rather than order. `blocks`
accepts `[Result, PaperSection, Figure]` and `depends_on` accepts
`[Result, DataFile, Script]`; neither accepts a task at the far end.

A multi-task plan therefore could not be stored in the graph at all. It could
not be validated, and `seldon go` could not show it. ai-readiness-kg was
carrying its week chain as a snapshot DataFile plus a prose restatement of the
order in each task's `description` — three copies of one fact, none of them
authoritative, which is precisely the drift the graph exists to prevent. Every
copy had to be edited by hand when a week slipped, and nothing detected it when
one was not.

## Prior art

Task ordering is not a novel problem and this AD does not treat it as one.

- **Kelley & Walker (1959), the critical path method**, and the **precedence
  diagramming method** as standardised in the PMBOK, give the vocabulary. The
  relationship implemented here is the **finish-to-start** dependency, PDM's
  default and by far its most common: the predecessor must finish before the
  successor starts. The three other PDM link types (start-to-start,
  finish-to-finish, start-to-finish) and lead/lag offsets are deliberately not
  implemented — see *Considered and rejected*.
- **Kahn (1962), topological sorting**, is the acyclicity check and the ordering
  used to render a chain. The DAG requirement is not a local preference: a
  precedence network with a cycle has no schedule, so "what is ready?" has no
  answer.
- Within this repo, **AD-028** already settled what a finished task is. This AD
  reads that state machine rather than inventing a second notion of done.

The name `precedes` is taken from PDM rather than coined.

## Decision

### 1. `precedes` is a domain relationship between two ResearchTasks

```yaml
precedes:
  from_types: [ResearchTask]
  to_types: [ResearchTask]
  cardinality: many_to_many
  inverse: preceded_by
  properties:
    reason:
      required: false
```

`A precedes B` means B is not expected to leave `proposed` until A is
terminal-complete. The domain version moves `0.2 → 0.3`.

Stored in **one direction only**. `preceded_by` is a read-name for queries and
rendering and is never written as an edge. It is declared as `inverse` rather
than as a second relationship type, and `DomainConfig` rejects a config in which
an inverse name is also a declared type — two separately-written directions
would silently disagree, and there is no cheap way to notice that later.

`RelationshipConfig` gained `cardinality`, `inverse` and `properties`. Edge
property validation is **opt-in by declaration**: a relationship type declaring
no property schema accepts anything, which is what keeps pre-AD-029 edges valid
(`assumes` carries an undeclared `topic` and `strength`). A type that declares a
schema is validated against it.

### 2. The subgraph is a DAG, enforced at the one write gate

Two invariants, checked before any event is appended, so a rejected write leaves
nothing in the event log or the graph:

- **No self-loop.** A task cannot precede itself.
- **No cycle.** Adding `A → B` is legal exactly when B cannot already reach A,
  which makes the check a single breadth-first reachability query in the
  opposite direction. On rejection the error **names the path that would close
  the cycle**, shortest-first, because "there is a cycle somewhere" is not
  actionable.

The gate lives in `seldon.core.artifacts.create_link`, not in the CLI. Every
write path reaches it — `seldon task precede`, `seldon task chain`, the three
MCP tools, and the generic `seldon link create` — so none of them can author a
cycle. Putting it in the CLI would have left `link create` as an open back door.

`seldon task chain A B C` writes the consecutive pairs in one call and is
**all-or-nothing**: every pair is validated against the graph *plus* the pairs
earlier in the same call before the first write, so a chain that goes wrong at
its third link writes nothing. An edge that already exists is skipped rather
than duplicated, which makes re-running a chain a no-op and therefore safe to
keep in a runbook.

### 3. A predecessor is satisfied when it is finished *or* abandoned

Satisfied: `completed`, `verified` (the work was done); `superseded`,
`withdrawn` (AD-028 — the work was replaced, or its premise was retracted, so
nothing is pending).

**`rejected` is deliberately not satisfied.** A rejected predecessor is work
that was refused, not work that was resolved. A chain hanging off one is a plan
that needs revising, and surfacing it is more useful than silently treating the
successor as startable. Because enforcement is advisory (§4) this costs nothing:
it shows up in `task list` and the briefing and blocks nothing.
`seldon task unprecede` retires the edge once the operator agrees the chain is
dead.

A predecessor whose node is missing also counts as unsatisfied, and
`seldon verify` reports the dangling endpoint separately.

### 4. Enforcement is advisory, and stops at a warning

`precedes` is advisory for `seldon go` and `task list`, and **warning-only** on
state transitions: moving a successor to `accepted` or `in_progress` with an
unsatisfied predecessor emits one warning line and proceeds. Gates bind the
machine, not the operator. An operator may reorder work, and a hard block would
teach them to delete edges — losing the plan to preserve the gate.

The warning is computed in `transition_task` from the graph as it stood *before*
the write (the question is whether starting was legitimate, which is a fact
about the prior state) and returned to the caller. The CLI prints it to stderr;
the MCP tools append it to their returned text. `walk_to_completed` takes an
`on_warning` callback rather than a second return value, so the walk's return
contract — the thing both surfaces render and the AD-028 parity test compares —
is unchanged.

### 5. One computation of "ready", read by every surface

`precedence_view()` assembles the pairs, states, `waits_on` map, ready list and
chains in a single pass. `seldon task list`, `seldon_task_list`,
`seldon briefing` and `seldon go` all read it. Three surfaces each deriving
readiness from their own queries is how they would come to disagree.

- **`task list`** gains a `WAITS_ON` column and a `▸` marker for **ready** =
  open with no unsatisfied predecessor.
- **`seldon go` / `seldon_go`** render **Next ready** (in creation order) and
  **Chains** immediately after open tasks, because that is the question an
  orienting agent asks next: of these open tasks, which may I start?
- A chain is a *weakly connected component* of the subgraph. A component of one
  node is not rendered — a task with no ordering relation to anything is not a
  chain, and rendering it as one would bury the real chains. A component that is
  a simple path renders as `A → B → C`; a **branching** component does not,
  because rendering a fan-out as a line asserts an ordering the graph does not
  contain, so its edges are listed one per line instead.

### 6. `seldon verify` checks the invariant it cannot enforce retroactively

A twelfth check, **Precedence**, fails on a cycle, a self-loop, or an edge whose
endpoint is missing or is not a ResearchTask. Each of those means a write
bypassed the gate — raw Cypher, or a log predating this AD.

It is **not Tier A**, on the same reasoning as "Relationship types": it reports a
property of accumulated graph state rather than of the change in hand, and an
executing CC task cannot make it clean by doing its own task correctly. Default
`seldon verify` still fails on it (exit 2).

### 7. Cycle detection reads the projection, not the log

The check runs against the Neo4j graph. The graph is the projection of the
event-sourced state, every other command reads it, and `seldon verify --replay`
is the existing instrument for the case where the two have diverged. Replaying
the log on every edge write to answer a reachability question would be a second,
slower, separately-maintained source of truth for one query.

## Consequences

- A multi-task plan is now a graph artifact. ai-readiness-kg's week chain
  becomes one `seldon task chain` invocation and its snapshot DataFile plus
  per-task prose ordering can be retired.
- `transition_task` returns `list[str]` instead of `None`. Existing callers that
  ignore the return keep working; the two CLI and two MCP call sites surface it.
- `research.yaml` is at version `0.3`. This is the first bump since the file was
  created, despite many additive schema changes in between — see *Notes on the
  originating task file*.
- `precedes` events replay like any other link event; `seldon.core.sync` needed
  no change, and the recoverability test confirms a log containing them rebuilds
  an identical graph that answers readiness identically.

## Considered and rejected

**The other three PDM link types, and lead/lag.** Start-to-start,
finish-to-finish, start-to-finish and numeric offsets are real parts of the
prior art and were deliberately left out. They earn their complexity when
durations are being scheduled against a calendar; Seldon orders discrete
research tasks with no duration model, so all three would be unexercised
machinery whose semantics no code could check. Finish-to-start is the default in
the field for the same reason.

**Hard enforcement on state transitions.** Rejected under the operator/machine
distinction: the operator may override any gate, and a machine that refuses to
let them would be routed around by deleting edges, which destroys the record
that this AD exists to create.

**Storing both directions.** Rejected: two writes that can disagree, with no
cheap detector. `inverse` is a read-name, and the loader refuses a config that
would turn it into a second stored type.

**Deduplicating in `graph.create_link`.** Not attempted. `create_link` uses
`CREATE` and can therefore write parallel edges; `precedes` avoids duplicates by
checking at its own gate rather than by changing a shared writer's semantics for
every other edge type in the domain.

## Notes on the originating task file

The task file asked to "bump the domain version per its convention." There was
no convention to follow: `research.yaml` had carried `version: "0.2"` unchanged
since the file was created (`b3aee86`), through every additive change since,
AD-028's included. The version string has never been read by any code path.

`0.3` is therefore the *establishment* of a convention rather than an
application of one: **additive schema change bumps the minor version.** It is
recorded here so the next AD has something to follow. Nothing depends on the
value except `tests/test_domain.py`, which pins it so that a change is
deliberate.

The task file's premise was otherwise accurate on every point that was checked:
`superseded_by` was indeed the only `ResearchTask → ResearchTask` edge, and
`blocks` / `depends_on` accept exactly the endpoint types it named.
