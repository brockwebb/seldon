# RESULT — Precedence check must read Artifact edges only

**Date:** 2026-09-07
**Task:** `cc_tasks/2026-09-07_precedence_artifact_labels.md`
**Addenda:** none found. Globbed `cc_tasks/2026-09-07_precedence_artifact_labels_ADDENDUM*.md` before starting; no siblings exist.
**Closes:** Seldon ResearchTask `1ad92c2b`
**AD:** `docs/design/AD-029_task_precedence.md` — Addendum 029-A
**Tests:** 1542 passed, 0 failed (26 new: 14 in `tests/test_precedence_cotenancy.py`, 8 in `tests/test_cypher_unlabelled_lint.py`, 3 in `tests/test_precedence.py`, 1 rewritten + 1 added in `tests/test_verify_reltype_migration.py`).
**`seldon verify`:** 12 of 12 checks pass, exit 0. `--replay` fails on pre-existing drift — see §7.
**Model spend:** zero, as specified.

---

## 1. The rule, and why the premise was right

The task file's premise checked out exactly. `precedence.read_edges()` ran

```cypher
MATCH (a)-[r:PRECEDES]->(b)
```

with no endpoint label. In a database that co-tenants a domain KG under disjoint
labels — the documented arrangement, and the reason `create_artifact` writes the
double label `:Artifact:<type>` — that pattern binds the co-tenant's nodes as
readily as Seldon's. ai-readiness-kg's `kg/schema.yaml` whitelists `precedes:
Concept → Concept` (BFO_0000063), so `seldon verify` reported 117
`illegal endpoint: ? [missing] → ? [missing]` rows and readiness went
unanswerable.

The rule now recorded in Addendum 029-A: **Seldon never reads a relationship by
name alone.** Every node pattern names a label; every relationship traversal
binds `:Artifact` on both endpoints; destructive scope is enumerated rather than
universal.

I confirmed the double-label invariant against the live graph before relying on
it — every one of the 160 artifact nodes in `seldon-seldon-self` carries
`:Artifact` plus its type, and only `_SeldonMeta` and `_OntologyReplicaMeta` do
not.

## 2. §1 — the queries that were bound

The audit the task asked for (grep for unlabelled `MATCH (` across `seldon/`)
found **19 offending queries**, not the one. All 19 are fixed:

| File | Query | Relationship |
|---|---|---|
| `core/precedence.py` | `read_edges` | `PRECEDES` |
| `core/precedence.py` | `edge_exists` | `PRECEDES` |
| `core/precedence.py` | `read_task_states`, `precedence_view` | (node match, now `:Artifact:ResearchTask`) |
| `core/graph.py` | `find_noncanonical_rel_types` | any |
| `core/graph.py` | `get_relationships_of_type` | any |
| `core/replay_check.py` | `fingerprint_graph` × 2 | any |
| `core/sync.py` | `full_replay` wipe | — (see §5) |
| `commands/artifact.py` | outbound + inbound link listing | any |
| `commands/issue.py` | ×4 | `AFFECTS`, `BLOCKED_BY`, `RELATED_ISSUE`, `RESOLVED_BY` |
| `commands/session.py` | briefing blockers, provenance gap | `BLOCKS`, `GENERATED_BY`, `DERIVED_FROM` |
| `commands/task.py` | ×4 | `BLOCKS`, `DEPENDS_ON` |

`SUPERSEDED_BY` was checked and had no unlabelled read.

The dangling-endpoint detection is kept, as the task required. `read_edges`
binds `:Artifact` but still *returns* each endpoint's `artifact_id` and
`artifact_type` rather than filtering on them, so an `:Artifact` with no id, or
one that is not a ResearchTask, still reaches `check_precedence` and still fails
it. Both cases are pinned by test.

**One thing the bind would have cost, and a fix for it.** Binding `:Artifact` on
both ends makes an edge with *one* end in each graph invisible rather than
illegal — a class of defect the old query did catch, however noisily.
`precedence.read_half_artifact_edges()` reads exactly that case, and
`check_precedence` reports it as `straddling endpoint: <id> [ResearchTask] → ?
[Concept] — one end is not a Seldon artifact`. An edge with *neither* end in the
Seldon graph is not read at all; it is the co-tenant's. This was not in the task
file; it is there because shipping the bind without it would have traded a noisy
false positive for a silent false negative.

## 3. §2 — the fixture test

`tests/test_precedence_cotenancy.py`, 14 tests. `_plant_domain_kg()` builds a
`(:Concept)-[:PRECEDES]->(:Concept)` chain carrying `key` and `bfo:
'BFO_0000063'` — no `artifact_id`, no `:Artifact` — beside a real task chain in
one database.

Asserted: `read_edges`, `read_task_states`, `precedence_view` (ready set, pairs
and chains all byte-identical before and after planting 20 co-tenant edges),
`seldon verify`, and `seldon task list` each read exactly the Seldon half; a
co-tenant `precedes` *cycle* is not reported as a Seldon DAG violation; the
write gate still refuses a cycle with the co-tenant graph present.

Held down as the things the bind must not cost: an illegal `:Artifact` endpoint
of the wrong type still reports, an `:Artifact` with no `artifact_id` still
reports, a straddling edge reports, a purely co-tenant edge does not.

**Mutation-checked.** Reverting `read_edges` to the unlabelled form and
re-running fails three of these tests with the exact reported symptom:

```
AssertionError: ['illegal endpoint: ? [missing] → ? [missing] — both ends must be a ResearchTask', ...]
assert 'fail' == 'pass'
```

## 4. §3 — the lint

`tests/test_cypher_unlabelled_lint.py`, adapted from ai-readiness-kg's
`230b282f` §1.2. Scope: `seldon/core/`, `seldon/commands/`, and `seldon/paper/`
— the third added because a co-tenanted database is no less co-tenanted when the
manuscript pipeline reads it.

Two deliberate departures from the prior art:

**Queries come from the Python AST, not a regex.** The prior art splits on
`session.run(` and re-joins string literals by regex, which needs its own
`{{` → `{` un-doubling step for f-strings. Parsing instead handles f-strings,
implicit concatenation and `+`-joins uniformly, picks up `cypher = ...`
assignments (`ontology.py` builds its queries that way, and `sess.run(` is not
`session.run(`), and — because `_IS_QUERY` anchors on a leading Cypher clause —
keeps `rebuild.py`'s docstring, which quotes the wipe it performs, out of the
lint. An interpolated slot becomes `INTERP`, which is right: `f"(t:{TYPE})"`
reads as `(t:INTERP)` and is correctly labelled.

**No blanket `labels(...)` escape.** The prior art passes any query mentioning
`labels(`. That would pass a query where the mention guards a *different* node
than the unlabelled one. The allowlist is instead a `dict[str, str]` of pattern
→ reason, and holds **one** entry: `read_half_artifact_edges`, whose whole job
is to compare labels across the boundary and which cannot bind both ends without
returning nothing.

Five self-tests keep the lint from becoming decoration: it must fail on the
exact query that shipped, pass its fixed form, not flag `count(r)`/`labels(n)`
as node patterns, treat a variable labelled once as bound for the whole query,
and find more than 50 queries (a typo in `LINTED_ROOTS` would otherwise make it
vacuously pass).

## 5. Beyond the task file: the unscoped rebuild wipe

The §1 audit's most dangerous find is not a read. `sync.full_replay` issued

```cypher
MATCH (n) DETACH DELETE n
```

In a co-tenanted project database — the arrangement this task exists to support
— `seldon rebuild` destroys the domain KG. Data Seldon never owned and its event
log cannot replay.

It is now scoped to `sync.SELDON_OWNED_LABELS`: `:Artifact` plus `_SeldonMeta`,
`_OntologyReplicaMeta` and `_OntologyMeta`. A test greps every `CREATE (`/`MERGE
(` in `seldon/core/` and `seldon/commands/` and asserts the labels they create
are a subset of that set, so a new creation path cannot quietly leave orphans
behind a rebuild. A second test plants a co-tenant graph, runs `full_replay`,
and asserts the co-tenant is still standing and the task chain is rebuilt.

I fixed this rather than filing it: leaving a data-destroying defect in place
while adding a lint that flags it is the shortcut §1 of the engineering
standards forbids.

**One test changed meaning as a result**, and it is worth stating plainly.
`test_null_endpoint_is_refused_rather_than_silently_dropped` in
`tests/test_verify_reltype_migration.py` used `(:Thing)-[:informs]->(:Thing)` to
exercise the rel-type migration's null-endpoint guard. With
`get_relationships_of_type` bound, a co-tenant's relationship is no longer
visible to the plan at all — which is correct, and means that migration can no
longer rewrite a graph Seldon does not own. The guard itself still matters and
is still reachable, so the test now uses an `:Artifact` with no `artifact_id`
and still asserts the `ValueError`. A new test pins the co-tenancy behaviour:
the plan is empty and the co-tenant's lowercase edge survives.

## 6. §4 — `seldon task show <prefix>`

`task show` called `get_artifact(session, task_id)` with the raw argument, so it
was the one task command that demanded a full UUID — and therefore the one that
could not consume the 8-character short ids that `task list` and the chain
renderer print. It now routes through the existing `_load_task()` helper, so it
resolves prefixes and inherits the shared resolver's unknown/ambiguous
diagnostics. Live:

```
$ seldon task show 1ad92c2b
Task: 1ad92c2b-374a-4760-8efe-e784eae7ef7b
  description: verify's Precedence check uses an UNLABELLED node pattern ...
  state:       proposed
```

Three tests in `tests/test_precedence.py` cover the prefix, the unknown prefix
and the empty argument.

## 7. Verification

```
$ python -m dotenv -f .env run -- python -m pytest tests/ -v
1542 passed in 112.05s

$ python -m dotenv -f .env run -- seldon verify
  ✓ File hashes / Ontology / Glossary / References / Stale artifacts /
    Blocking tasks / Unregistered files / Relationship types / Precedence /
    Task source files / Event log
  All checks passed.
```

`seldon verify --replay` fails, and it fails identically on `HEAD` without any
of this work — I stashed and re-ran to confirm:

| | this branch | HEAD |
|---|---|---|
| artifacts live/replayed | 160 / 158 | 160 / 156 |
| relationships live/replayed | 61 / 56 | 61 / 56 |
| state mismatches | 18 | 18 |
| relationships outside the event path | 5 | 5 |

Pre-existing drift in `seldon-seldon-self` — graph state written outside the
event path — not caused by and not addressed by this task. The two-artifact
difference between the columns is this session's own task-creation events being
in the log on one side and not the other. Worth its own task; not this one's
scope, and not silently folded into it.

## 8. What was deliberately not done

**Node-only matches keep their single artifact-type label.** `MATCH
(t:ResearchTask)` is already label-bound and, under the disjoint-label
arrangement, a co-tenant does not use Seldon's artifact-type labels. Upgrading
~25 more sites to `:Artifact:<Type>` would have broadened the diff without
serving the defect. The rule as written and linted — a label on every node
pattern, `:Artifact` on both ends of every traversal — is what is enforced. The
`precedes` read path binds both anyway, being the surface under repair.

**The pre-existing replay drift** (§7). Named, measured, left alone.
