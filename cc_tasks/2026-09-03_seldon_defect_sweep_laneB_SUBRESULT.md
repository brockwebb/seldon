# Lane B sub-RESULT — Ontology gaps (`698d1d86` + item 4 of `0bc41cfc`)

**Date:** 2026-09-03
**Task:** `cc_tasks/2026-09-03_seldon_defect_sweep_registry_lifecycle_ontology.md` §3
**Lane:** B
**Status:** complete

---

## 1. What shipped

| File | Change |
|------|--------|
| `tests/test_relationship_types.py` | **New.** 49 tests. Endpoint-type contract for `generated_by`, `computed_from`, `corrects`, `annotates`, `disputes` — validator matrix plus end-to-end through `create_link`. |

Nothing else. No source change was required in this lane, because the change the
task asked for had already been made in a file this lane does not own — see §2.

`seldon/domain/research.yaml` was edited by the integrator (three lanes needed
the same file). Lane B treated it as read-only and verified it rather than
editing it.

### Test structure

Two layers, deliberately:

1. **Validator in isolation** — `seldon.domain.loader.validate_relationship`
   over the full accept/reject matrix (10 accepted triples, 21 rejected triples,
   parametrized). Cheap, no Neo4j.
2. **End to end through `seldon.core.artifacts.create_link`** — one accepted and
   one rejected case per edge type. The rejected cases additionally assert that
   **no `link_created` event is written and no Neo4j edge exists** after the
   raise. A validator that passes in isolation is not evidence that the
   caller-facing path enforces it; the `create_link` layer is where a caller
   actually meets the rule.

Plus a config-surface test asserting the declared `from_types`/`to_types` sets
per edge type, so a silent widening of an endpoint set fails a test rather than
passing unnoticed.

### Coverage of the spec's named cases

| Spec requirement | Test |
|---|---|
| `generated_by` accepts `DataFile→Script` (previously rejected) | `test_endpoint_pair_accepted`, `test_create_link_accepts_endpoint_pair` |
| `generated_by` rejects `Script→Script` | `test_endpoint_pair_rejected`, `test_create_link_rejects_endpoint_pair` |
| `computed_from` accepts `DataFile→DataFile` | both layers |
| `computed_from` rejects `DataFile→Script` | both layers |
| `corrects` accepts `DesignNote→{DesignNote, Result}` | both layers |
| `corrects` rejects `Result→Result` | `test_corrects_result_to_result_is_rejected` (dedicated, with the rationale in its docstring) |
| `annotates`/`disputes` reject non-`Issue` origins | 6 parametrized cases (`Result`, `DesignNote`, `PaperSection` origins) |
| `annotates`/`disputes` reject non-`Result` targets | 6 parametrized cases (`Script`, `DataFile`, `PaperSection` targets) |

---

## 2. Premise in the task file that live state contradicted — REQUIRED ITEM

### The claim

Task file §3, first bullet:

> Add relationship types to the master `seldon-ontology`

### The claim is false. Relationship types do not live in `seldon-ontology`.

Verified against live state, not inferred:

**a. The master DB holds a controlled research vocabulary, not a schema registry.**
Live query against `seldon-ontology`:

```
node ['Artifact', 'OntologyTerm']   105
node ['_OntologyMeta']                1
rel  ADDRESSES_THREAT                13
rel  MEASURES_THREAT                  9
rel  DEFINES_SUB_DIMENSION            5
rel  DEFINES_THREAT                   5
rel  PRECONDITION_FOR                 4
```

There is no node type in that database that represents a relationship *type*.
The only node label besides bookkeeping is `OntologyTerm`.

**b. Its edges are between vocabulary terms and come from a closed set of five.**
`seldon/ontology/parser.py::ParsedRelationship.rel_type` documents the set as
`defines_sub_dimension, defines_threat, addresses_threat, measures_threat,
precondition_for`, and `_build_relationships` (parser.py:784) only ever emits
those. Both `ingest` (ontology.py:515) and `_do_sync` (ontology.py:300) match
`(:Artifact:OntologyTerm)-[r]->(:Artifact:OntologyTerm)` exclusively. Nothing in
the ontology path can express an endpoint constraint on an artifact-level edge.

**c. The component that actually rejected `DataFile-[:GENERATED_BY]->Script` is
elsewhere.** `seldon/domain/loader.py::validate_relationship` (line 103) reads
`domain_config.relationship_types`, which is loaded from
`seldon/domain/research.yaml`. It is the only validator on the path; the single
caller is `seldon/core/artifacts.py::create_link` (line 243). The ontology
module is never consulted.

### Consequence

Had the task been executed literally — adding relationship-type entries to
`ontology/validity/VALIDITY_VOCABULARY.md` and running `seldon ontology ingest`
— the defect would not have been fixed. `DataFile→Script` would still raise, and
the master vocabulary would have been polluted with five pseudo-terms that are
not validity concepts. The ingest parser would most likely not have produced
them at all, since it parses category-structured vocabulary sections rather than
arbitrary entries.

### What was actually done

The integrator applied the fix to `seldon/domain/research.yaml` before this lane
started, because three lanes needed edits to that one file and lane-ownership
could not be kept disjoint otherwise. Lane B independently verified the
diagnosis above and then verified the config, rather than editing it.

**Verified live and correct** (each asserted by
`test_domain_config_declares_endpoints`):

| Edge type | `from_types` | `to_types` | Status |
|---|---|---|---|
| `generated_by` | Result, Figure, Table, **DataFile** | Script | extended |
| `computed_from` | Result, **DataFile** | DataFile | extended |
| `corrects` | DesignNote | DesignNote, Result | new |
| `annotates` | Issue | Result | new |
| `disputes` | Issue | Result | new |

(`superseded_by` also present; Lane C's.)

### Recommendation for the RESULT

The task-file section header "Lane B — Ontology gaps" is a misnomer for what the
work turned out to be. These are **domain schema gaps**. The word "ontology" is
overloaded in this repo: `seldon-ontology` is a *vocabulary* service (validity
concepts, threat taxonomy), while the *schema* (artifact types, edge endpoint
constraints, state machines) lives in the domain config. Any future task that
says "add a type to the ontology" should be read as ambiguous and resolved
against `seldon/domain/research.yaml` first.

---

## 3. The `corrects` Result→Result decision

**Decision: keep it rejected.** Test `test_corrects_result_to_result_is_rejected`
asserts the rejection.

Reasons:

1. **An erratum is an authored claim, and the domain models authored claims as
   `DesignNote`.** `corrects` was introduced (per the config comment) for
   ai-readiness-kg's `ERRATUM-01`, which is a note. A note carries the
   rationale; a bare `Result→Result` edge carries none, so admitting it would
   let a correction exist in the graph with no written justification anywhere.
2. **`Result→Result` supersession already has two edge types.** `validates`
   (Result→Result) and `derived_from` (Result→…, Result). A third path for
   approximately the same relation makes provenance queries ambiguous —
   "what replaced this Result?" would need to union three edge types, and
   authors would pick inconsistently between them.
3. **Nothing in the observed defect needs it.** The reported failure was
   `DataFile→Script` on `generated_by`; no live artifact wanted
   `corrects` from a `Result`.

If a future case genuinely needs Result→Result correction, the right move is a
new edge type with its own semantics (e.g. `corrected_by`), not widening
`corrects` — because the widening would silently make the DesignNote-authored
form optional.

No config change is requested for this. If the integrator disagrees, the change
is one line in `research.yaml` plus flipping one parametrized case in
`tests/test_relationship_types.py::REJECTED` to `ACCEPTED`.

---

## 4. Ingest / sync outcome

### `seldon ontology ingest` — deliberately NOT run. This is not a skipped step.

Lane B changed no vocabulary markdown. `ontology/validity/VALIDITY_VOCABULARY.md`
and `ontology/practitioner/PRACTITIONER_VOCABULARY.md` are untouched
(`git diff --stat -- ontology/` empty; last commit touching `ontology/` is
`7dd54ce`, 2026-04-18). A `--dry-run` confirms the parse is identical to what
master already holds:

```
[DRY RUN] Would write to master database:
  ... 17 categories, 100 terms total ...
  Relationships: 36
No changes written.
```

Master already holds those 36 relationships exactly (13 + 9 + 5 + 5 + 4).

**A ceremonial live run would not be a no-op — it would do harm.**
`ingest_command` (ontology.py:473) calls `_increment_epoch` **unconditionally**,
before comparing any content hash, and then appends an `ontology_ingested` event
to `seldon_events.jsonl` regardless of outcome. Running it would have:

- bumped the master epoch from 3 to 4 with zero content change;
- marked every project replica stale against master, forcing a pointless sync
  in every downstream project including `ai-readiness-kg` (which this task
  explicitly says not to touch);
- written a provenance event claiming an ingest happened when nothing was
  ingested.

That is the opposite of the traceability property the epoch exists to provide,
so the run was not performed.

**Why the task file expected one:** the task file's own premise (§2 above) was
that the fix lands in the master vocabulary. Under that premise an ingest is
mandatory — it is how a vocabulary edit reaches master. Once the premise is
corrected and the fix lands in `seldon/domain/research.yaml`, the ingest step
has nothing to carry: the domain config is a packaged file read from disk at
load time, not graph state, so it needs no propagation mechanism at all.

### `seldon ontology sync` — run live against `seldon-seldon-self` only.

```
$ seldon ontology sync
Already up to date at epoch 3.
```

- Master epoch before: **3**. After: **3** (unchanged — no ingest).
- Replica `seldon-seldon-self` epoch before: **3**. After: **3**.
- Term count master: **105**. Replica: **105**. Unchanged.
- `ai-readiness-kg` was **not** synced, per the task instruction.

`sync` is safe to run unconditionally (unlike `ingest`): when epochs match it
short-circuits at `_do_sync` with `up_to_date` and writes nothing.

---

## 5. Additional findings (not in scope; reported, not fixed)

### 5a. `seldon ontology ingest` never deprecates terms dropped from the markdown

Master holds **105** `OntologyTerm` nodes but the current vocabulary markdown
parses to **100** unique `term_id`s. Five orphans, all `state: active`, all
`epoch: 1`:

```
ontology:validity:related:context_window
ontology:validity:related:compaction
ontology:validity:related:handoff_document
ontology:validity:related:state
ontology:validity:related:fidelity
```

`_do_sync` deprecates project-replica terms missing from master
(ontology.py:337-341), but `ingest_command` has no corresponding pass for master
terms missing from the source markdown — it only creates and updates. So master
accumulates terms that were removed from the vocabulary, and `sync` faithfully
replicates them into every project. `seldon-seldon-self` holds all 105,
including the five orphans.

This is a real gap in the master/replica inheritance model (AD-017) and deserves
its own task: an ingest-side deprecation pass, symmetric with the sync-side one.
Not fixed here — fixing it requires a live `ingest`, which §4 explains should not
be run casually, and it is out of this task's scope.

### 5b. Mixed-case relationship types in `seldon-seldon-self`

The self graph holds both `INFORMS` (8 edges) and `informs` (4 edges).
`create_link` upper-cases (`artifacts.py:264`) and `core/sync.py:96,105` does the
same on replay, and `graph.create_link` has exactly one caller — so nothing in
the current code path can produce the lowercase form. The 4 lowercase edges are
legacy, most likely written by direct Cypher (a Desktop/MCP session) before the
normalization existed. Any query filtering by `[r:INFORMS]` silently misses
them. Cosmetic-looking, but it is a correctness hole in graph queries. Not
Lane B's file set.

---

## 6. Cross-lane needs

Nothing needed **from** Lane B. Two items **for** the integrator:

### 6a. `docs/design/AD-028_*.md` does not exist

`seldon/domain/research.yaml` now cites "AD-028" in eight comments and two
property descriptions, but there is no `docs/design/AD-028_*.md` and no `AD-028`
string anywhere under `docs/`. The highest AD on disk is AD-027. The config is
citing a decision document that has not been written. The integrator owns
`docs/design/` — this needs to be written before commit, or the citations are
dangling.

Lane B's content for it, if useful: the five edge types in §2's table, their
rationale (the comments in `research.yaml` are already written and accurate),
and the `corrects` Result→Result rejection rationale from §3.

### 6b. No stale relationship-type registry doc found

Checked `docs/` for a document enumerating relationship types.
`docs/data_dictionary.md:10` mentions `relationship_types` only generically
("Defines artifact_types …, relationship_types …, state_machines …") — no
enumeration, so nothing goes stale. `docs/architecture/schema-design.md` uses
`computed_from`/`generated_by` as *Postgres column names* in a different
(pre-Neo4j) design, unrelated to the graph edge types. **No doc staleness to
fix.** Only 6a is outstanding.

---

## 7. Test results

Command (mandatory form):

```
python -m dotenv -f .env run -- python -m pytest tests/ -v
```

| | Count |
|---|---|
| Baseline (task file) | 697 passing |
| Lane B new tests | +49 |
| Expected total | 746 |
| **Observed** | **743 passed, 3 failed** |

743 + 3 = 746, so the arithmetic reconciles: no test was lost.

**All 49 Lane B tests pass.** `tests/test_relationship_types.py` alone:
`49 passed in 2.63s`.

### The 3 failures are not Lane B's, and both causes are in `research.yaml`

Deterministic (reproduce in isolation, not order-dependent):

1. `tests/test_state.py::test_invalid_state_transition_carries_valid_options`
   — asserts `["accepted", "rejected", "superseded"]`; the integrator's config
   adds `withdrawn` to `ResearchTask.proposed`. **Lane C** owns the state
   machine and this test's expectation.
2. `tests/test_docs_check.py::test_docs_check_required_vs_doc_stats`
   — asserts `doc_total == 2` for `Result`; the integrator's config adds
   `name` as a `documentation`-category property, making it 3.
3. `tests/test_docs_check.py::test_docs_check_mixed_completeness`
   — same cause: `fully_documented` is now 0 because neither fixture Result
   sets the new `name` property.

(2) and (3) are consequences of **Lane A**'s `Result.name` work. Both files are
outside Lane B's ownership; neither was touched.

### Cross-lane hazard: the suite is not safe to run concurrently

Every Neo4j test shares one database, `seldon-test` (`tests/conftest.py:31`),
and `clean_test_db` wipes it with `MATCH (n) DETACH DELETE n`. When two lanes
run the suite at the same time, one lane's wipe lands inside the other lane's
test. Observed: `tests/test_sync.py` produced 5 failures
(`assert 10 == 4` — six extra nodes from a concurrent lane) on one run and
`15 passed` on an immediate re-run with no code change.

**These failures are indistinguishable from real ones at a glance**, and they
will waste integration time if lanes run the suite in parallel. Either serialize
the integration test run, or parameterize `TEST_DATABASE` per worker
(e.g. `seldon-test-$PYTEST_XDIST_WORKER` or a PID suffix). Recommend the latter
as a follow-up task; it is a `tests/conftest.py` change, which no lane owns.

---

## 8. Compliance

- Did **not** edit `seldon/domain/research.yaml` or any file outside the Lane B set.
- Did **not** commit, did **not** run `seldon verify`, did **not** close any Seldon task.
- Did **not** sync into `ai-readiness-kg`.
- No model spend. No `claude -p` calls.
