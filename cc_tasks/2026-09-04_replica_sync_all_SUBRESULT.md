# SUBRESULT — Fleet-wide ontology replica sync (`seldon ontology sync --all`)

**Date:** 2026-09-04
**Graph task:** `c9fdef46` (ResearchTask)
**Lane:** C, worktree `/Users/brock/GitHub/seldon/.claude/worktrees/open-defect-closeout`
**Source defect:** 2026-09-04 defect sweep RESULT §7.3, §7.7

---

## 1. What shipped

### `seldon/commands/ontology.py`

**Refactor — one classifier for plan and apply.**
`_compute_replica_delta(master_terms, project_terms, inheritance)` is a pure
function returning a `ReplicaDelta` (creates / updates / state_changes /
orphan_deprecations / skipped_deprecated). `_do_sync` no longer decides *and*
writes in one loop: it calls the classifier and applies the result. `--all`'s
dry-run calls the same classifier. A dry-run that reasons differently from the
apply is worse than no dry-run, so the two cannot diverge by construction.

Behaviour of `_do_sync` is unchanged — the counts it returns are now derived
from the delta (`deprecated` still sums both causes: a term master retired, and
a term master no longer holds at all).

**New — `seldon ontology sync --all`.** Options:

| Flag | Meaning |
|------|---------|
| `--all` | Operate on every ontology replica in the cluster |
| `--apply` | Perform the writes. Without it, `--all` only reports |
| `--exclude DATABASE` | Skip a database. Repeatable; additive with `$SELDON_SYNC_ALL_EXCLUDE` |
| `--roots DIR` | Directory to scan for projects, for event attribution. Repeatable; defaults to `$SELDON_PROJECT_ROOTS` |
| `--depth N` | Scan depth (default `DEFAULT_SCAN_DEPTH`) |

Guards: `--dry-run` together with `--apply` is refused as contradictory;
`--apply` / `--exclude` / `--roots` without `--all` is refused rather than
silently ignored.

Supporting functions, all in `seldon/commands/ontology.py`:
`_list_online_databases`, `_discover_replica_databases`, `_excluded_databases`,
`_find_projects_including_nested`, `_map_databases_to_projects`,
`_plan_replica`, `_sync_one_replica`, `_render_sync_all_report`,
`_run_sync_all`.

### `tests/test_ontology_sync_all.py` (new, 49 tests)

Classification (pure), harness-pattern exactness, exclusion merging, project
mapping including the nested-project and ambiguous-claim cases, discovery
against a real cluster, failure isolation at both the plan stage and the write
stage, re-run no-op, event attribution, and the CLI flag guards.

Two mutation checks were run against the first draft of the suite. Both
survived, which exposed two real gaps, now closed:

* Removing the `_OntologyMeta` marker guard changed nothing, because the test
  master was also caught by the *name* guard (the fixture monkeypatches
  `ONTOLOGY_MASTER_DB` to it). Added
  `test_a_master_that_is_not_the_configured_one_is_still_refused`, which marks
  the test master with **both** markers and points `ONTOLOGY_MASTER_DB`
  elsewhere, so only the marker check can save it.
* Turning `_sync_one_replica`'s handler into a bare `raise` changed nothing,
  because the only failing-database test failed at the *plan* stage. Added
  `test_a_failure_while_writing_is_recorded_not_raised` (a mapped project whose
  `seldon.yaml` has no `shared_ontology` section).

---

## 2. Discovery scoping — decision and justification

**Decision: discover by marker node, never by name prefix.** A database is a
sync target iff it holds an `_OntologyReplicaMeta` node, after three exclusions.

The task description says "discovers every `seldon-*` DB with an
`_OntologyReplicaMeta` node". The prefix half of that is wrong in both
directions on this machine, and the live cluster proves it:

* **`seldon-` does not imply replica.** `seldon-ai4stats`, `seldon-arnold`,
  `seldon-leibniz-pi`, `seldon-sas2graph` and `seldon-test` carry the prefix and
  hold no `_OntologyReplicaMeta` and no `OntologyTerm` at all. Four of them are
  real projects with a `seldon.yaml`; they have simply never synced.
* **Replica does not imply `seldon-`.** Nothing enforces the prefix. `seldon
  init` derives the database name from the project slug, and a project renamed
  or hand-configured is one YAML edit away from `pragmatics` or `quarry`
  (both of which exist here as non-Seldon databases). Filtering on the prefix
  would silently strand exactly the replica nobody remembers.

The marker is the thing that *makes* a database a replica, so the marker is what
is tested. Three exclusions precede it:

1. **The configured master** (`seldon.config.ONTOLOGY_MASTER_DB`) — structural.
   Syncing the master into itself is at best a no-op and at worst a corruption
   of the authoritative copy.
2. **Any database holding `_OntologyMeta {key: 'master'}`** — the same rule
   again, but by marker rather than by name, so a renamed master or a second
   master (a test master, say) is also protected. Tested directly.
3. **This repository's pytest-harness databases**, matched by
   `_TEST_HARNESS_DB_RE = ^seldon-test(?:-project|-p\d+(?:-[A-Za-z0-9]+)*)?$` —
   an exact reproduction of `tests/testdb.py`'s own naming, not a `seldon-test`
   prefix match. A fleet sync that pushed the real master's 111 terms into a
   database an in-flight `pytest` run is asserting against would turn a hygiene
   command into a source of flaky failures. The exclusion fails closed (the
   database is left alone) and every skip is printed with its reason, so an
   over-exclusion is visible rather than silent. Overridable in the other
   direction only by this repo's own tests, via
   `_discover_replica_databases(..., skip_test_harness=False)`; the CLI always
   leaves it on. A real project database would have to be named literally
   `seldon-test`, `seldon-test-project` or `seldon-test-p<digits>` to collide.

Offline databases are excluded by the `SHOW DATABASES` filter, and a database
that cannot be inspected is reported as a skip carrying the error text rather
than aborting discovery.

**Event attribution is a separate, best-effort concern.** `_do_sync` appends an
`ontology_synced` event to a project's log. `--all` maps each replica database
back to the directory whose `seldon.yaml` claims it, using
`seldon.core.projects` over `--roots`:

* **Exactly one claimant** → sync through that project's own config; the event
  lands in that project's log.
* **No claimant** → sync graph-only, no event, row labelled
  `unmapped — graph-only, no event`. A replica no directory claims has no event
  log to be inconsistent with and no `seldon rebuild` that will ever run for it;
  leaving it carrying junk terms that `seldon ontology list` and `seldon verify`
  read is the worse outcome. `shared_ontology.inheritance` defaults to
  `read-only`, which is the only mode AD-017 defines.
* **More than one claimant** → sync graph-only, no event, row labelled
  `AMBIGUOUS (N dirs)` with the paths. Writing the event into one of two logs
  would be recording a fact we do not have.

`_find_projects_including_nested` exists because `find_projects` deliberately
stops at the first `seldon.yaml` it meets. That rule is right for auditing event
logs and wrong for mapping databases: `brock_projects/nsf_aiday2026` is a
project nested inside a project and owns `seldon-nsf-aiday2026`. Without the
rescan its sync event would have gone nowhere. `seldon/core/projects.py` was
off-limits to this lane, so the composition lives in the command module.

---

## 3. Live state — the task description's premises, re-measured

Every epoch figure in the task description is stale, and one count is wrong
independently of staleness.

| Premise in the description | Live state at 2026-09-04 ~18:55Z | Verdict |
|---|---|---|
| Master at epoch 3 | Master at **epoch 6**, 111 terms, 2 deprecated | Contradicted (task `0977c79a` landed epochs 4→6 in between) |
| "13 project replicas at epoch 3" | **10** replicas at epoch 3 | Contradicted — a miscount, not drift |
| — | 2 further replicas (`seldon-ai-readiness-kg`, `seldon-seldon-self`) at epoch 4, junk already deprecated | Not in the description |
| `seldon-sfv-paper` at epoch 2 | Confirmed (53 terms) | Holds |
| `seldon-test-project` at epoch 1 | Confirmed (48 terms) | Holds |
| Sync carries "the 2 junk-term deprecations" | Sync carries **6 new terms + 103 rewritten content hashes + 2 deprecations** per replica | Understated |
| "every `seldon-*` DB with an `_OntologyReplicaMeta` node" | 5 `seldon-*` databases have no replica marker at all | Contradicted — see §2 |
| "Drop `seldon-test-project` after confirming no project dir references it" | No `seldon.yaml` names it, but `tests/testdb.py` derives it and `scripts/observability_collect.py` names it | Not dropped — see §5 |

The 105→111 term jump and the 103 content-hash rewrites are the tail of
`0977c79a`: six new instrument/crosscutting terms at epoch 5, and the
`_term_content_hash` widening (version prefix `v2`, covering `name`,
`citations`, `extra`) at epoch 6, which invalidated every stored hash by design.

**Concurrent activity note.** `seldon-ai-readiness-kg` measured at epoch 4 at
~18:55Z and at epoch 6 twenty minutes later, before this lane wrote anything —
another lane synced it in between. State words were verified against the
machine at each step rather than carried forward.

### Before (measured directly, before any write by this lane)

| Database | Epoch | Terms | Junk terms |
|---|---:|---:|---|
| seldon-ai-readiness-kg | 4 | 105 | deprecated |
| seldon-ai-workflow-design | 3 | 105 | **active** |
| seldon-blank | 3 | 105 | **active** |
| seldon-book-responsible-ai | 3 | 105 | **active** |
| seldon-brock-projects | 3 | 105 | **active** |
| seldon-census-web-concept-inventory | 3 | 105 | **active** |
| seldon-federal-survey-concept-mapper | 3 | 105 | **active** |
| seldon-icsp-notebook | 3 | 105 | **active** |
| seldon-nsf-aiday2026 | 3 | 105 | **active** |
| seldon-seldon-self | 4 | 105 | deprecated |
| seldon-sfv-paper | 2 | 53 | **active** |
| seldon-tickbiterisk | 3 | 105 | **active** |
| seldon-usai-harness | 3 | 105 | **active** |
| seldon-test-project | 1 | 48 | **active** (excluded — see §5) |

`seldon-ontology` holds 111 terms and no `_OntologyReplicaMeta`, as a master
should.

### After (`--apply`, then verified by direct query)

Every one of the 13 real replicas: **epoch 6, 111 terms, 109 active, 2
deprecated**, with `ontology:validity:related:log_precision_fitness` and
`ontology:validity:related:precision_gain_rate` both `deprecated`. The junk
terms are cleared in every replica that carried them.

`seldon-test-project` is unchanged at epoch 1 / 48 terms, deliberately.

**Re-run proof.** A second `--all --apply` reported
`Synced 0 replica(s); 13 already current.`, wrote nothing, and exited 0.

**Event attribution.** Ten mapped projects each received exactly one new
`ontology_synced` event at `master_epoch: 6`. `seldon-blank` and
`seldon-sfv-paper` were synced graph-only with no event, as reported in their
rows. `seldon-seldon-self` was excluded from the fleet run and synced separately
from this worktree, so its event landed in the worktree's
`seldon_events.jsonl` rather than in the main checkout — the main checkout at
`/Users/brock/GitHub/seldon` was not written to by this lane (its log's last
ontology event is still the 15:47Z, epoch-4 one).

---

## 4. Commands run

```bash
# plan
python -m dotenv -f .env run -- python -m seldon ontology sync --all \
    --roots /Users/brock/GitHub

# live (seldon-self excluded so its event stays in this worktree's log)
python -m dotenv -f .env run -- python -m seldon ontology sync --all --apply \
    --roots /Users/brock/GitHub --exclude seldon-seldon-self

# seldon-self, from the worktree
python -m dotenv -f .env run -- python -m seldon ontology sync

# no-op proof
python -m dotenv -f .env run -- python -m seldon ontology sync --all --apply \
    --roots /Users/brock/GitHub     # -> "Synced 0 replica(s); 13 already current."
```

Roots were scoped to `/Users/brock/GitHub`. Adding
`/Users/brock/Documents/GitHub` makes `seldon-ai-workflow-design` ambiguous:
`Documents/GitHub/ai-workflow-design.PRE-MOVE-QUARANTINE` is a dead pre-move
copy whose `seldon.yaml` still claims the same database. Excluding that root
lets the event land in the live project. No replica is reachable only from the
Documents tree, so nothing was lost.

---

## 5. `seldon-test-project` — NOT dropped

**Decision: do not drop. Excluded from `--all` instead.**

The task authorised the drop "after confirming no project dir references it".
Read literally that condition is met — no `seldon.yaml` on this machine names
`seldon-test-project` as its `neo4j.database`. Read as intended (nothing depends
on it), it is not met.

**What was checked**

1. Every `seldon.yaml` under `/Users/brock` to depth 6 (18 files) with its
   `neo4j.database` extracted. **Complete.** None names `seldon-test-project`.
2. `grep -rn "seldon-test-project"` over `/Users/brock/GitHub` excluding
   `.git`, `node_modules`, `.venv`, `__pycache__`. **Complete** — 21 hits, all
   listed below or in documentation.
3. This repo's own test harness, specifically. **Complete.**
4. A full-text grep of `/Users/brock/Documents/GitHub` was started and had
   returned no hits when this was written, but did **not** finish — that tree is
   large and slow to walk. It does not change the decision: the blocking
   references are inside this repository, and check 1 (which does cover the
   Documents tree) proves no project config there claims the database. Noted
   rather than glossed over.

**What was found — the blocking references**

* **`tests/testdb.py:208`** —
  `TEST_PROJECT_DATABASE = f"{TEST_DATABASE}-project"`. Under the documented
  serial-run override `SELDON_TEST_DATABASE=seldon-test` (`tests/testdb.py`
  lines 45-46), `TEST_DATABASE` is `seldon-test` and `TEST_PROJECT_DATABASE` is
  exactly `seldon-test-project`. The suite **creates and writes** this database
  in a supported configuration. This is not hypothetical: the database was last
  written at **2026-09-04T15:06:13Z**, hours before this task, and its contents
  (epoch 1, 48 terms — a small test master, not the real 111-term one) are
  exactly what an ontology sync test under that override produces.
* **`scripts/observability_collect.py:43`** — names it literally in
  `EXCLUDED_DBS`.
* **`tests/test_testdb.py:121,199`** — listed in `PROTECTED_NAMES` and in the
  realistic-listing test, i.e. the suite explicitly asserts that the sweeper
  must **never** drop this database. These two are string assertions rather than
  live usage, but they encode a standing decision that this name is protected.
* Documentation references in `docs/design/evolution_burst_2026-04/`
  (`phase_c_retirement_list.md` R5 proposes retiring it; the retirement was
  never executed).

`tests/testdb.py`'s `drop_database` refuses any name that is not an ephemeral
per-process database, which is why this one has survived: it is a leftover from
a serial-override run that the suite is forbidden to clean up.

**Why not drop it anyway.** Dropping a database is irreversible; the standing
instruction for this lane was "if anything references it, do not drop it —
report and stop"; and the cost of keeping it is one idle database, while the
cost of being wrong is a destroyed test fixture in the middle of a multi-lane
session.

**What was done instead.** `_TEST_HARNESS_DB_RE` excludes it from `--all`, with
the reason printed on every run:

```
skip seldon-test-project: pytest harness database (tests/testdb.py)
```

Syncing it would have been actively harmful: it would have replaced a 48-term
test replica with the real master's 111 terms, breaking any subsequent
serial-override run that asserts on replica contents.

**Recommendation (not executed).** The clean retirement is: remove the
`SELDON_TEST_DATABASE=seldon-test` serial-override path or make it use an
ephemeral name too, then drop `seldon-test` and `seldon-test-project` together,
then delete the `EXCLUDED_DBS` entry and the `PROTECTED_NAMES` entries that only
exist to guard them. That is a change to `tests/testdb.py` and
`tests/test_testdb.py`, which belong to another lane's surface.

---

## 6. Verification

* `python -m dotenv -f .env run -- python -m pytest tests/ -q` →
  **1444 passed, 0 failed** (baseline at the start of this lane: 1389 passed;
  49 of the increase are this lane's, the rest landed from other lanes during
  the session).
* `tests/test_ontology_sync_all.py`: 49 tests, all passing.
* Regression check on the shared classifier:
  `tests/test_ontology.py`, `tests/test_ontology_ingest_lifecycle.py`,
  `tests/test_projects_discovery.py` all pass unchanged.
* One self-inflicted failure was found and fixed during the run:
  `test_no_hardcoded_database_literal_in_test_modules` caught a literal
  `"seldon-test"` in the new test file's parametrize list. The parameters are
  now built from `BASE_DATABASE`, which also ties `_TEST_HARNESS_DB_RE` to the
  harness's own constant so the two cannot drift apart silently.

## 7. Files changed

* `seldon/commands/ontology.py` — classifier extraction + `sync --all`
* `tests/test_ontology_sync_all.py` — new

No other files were modified. Nothing was committed; no graph task was closed.
