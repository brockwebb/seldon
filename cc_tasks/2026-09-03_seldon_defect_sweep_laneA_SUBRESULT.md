# Lane A sub-RESULT — Result registry contract (AD-028)

**Task:** `cc_tasks/2026-09-03_seldon_defect_sweep_registry_lifecycle_ontology.md` §2
**Closes (with the integration pass):** Seldon task `0bc41cfc`
**Date:** 2026-09-03
**Lane:** A — Result registry contract, `paper/build.py` resolver path

---

## 1. What shipped

### Files created

| File | Purpose |
|------|---------|
| `seldon/domain/result_units_vocabulary.yaml` | Authoritative machine-readable units vocabulary (packaged) |
| `seldon/domain/units_vocabulary.py` | Loader: `vocabulary_path()`, `load_units_vocabulary()`, `is_real_unit()` |
| `docs/conventions/result_units_vocabulary.md` | Human-readable convention doc; points at the YAML as authoritative |
| `tests/test_result_registry.py` | 47 tests — vocabulary, slug, uniqueness, fail-loud register, migrate-names, backfill |

### Files modified

| File | Change |
|------|--------|
| `seldon/commands/result.py` | A1 `--name`, A2 `migrate-names`, A3 fail-loud register + `backfill-provenance`, `NAME` column in `result list` |
| `seldon/paper/build.py` | A2 transitional units fallback, A4 `allow_proposed`, `summarize_proposed`, `RefError.artifact_name` |
| `seldon/commands/paper.py` | A4 `--allow-proposed` flag wiring on the `build` subcommand only |
| `tests/test_paper_build.py` | +12 tests (24 → 36) |

`seldon/domain/research.yaml` was **not** touched (read-only for this lane, as instructed).

### A1 — `name` property

- `seldon result register --name NAME` is `required=True` at the CLI. The domain schema still
  does not mark `name` required, so pre-AD-028 Results stay valid.
- Slug grammar `^[a-z0-9][a-z0-9_.-]*$`, case-sensitive, ≤128 chars, enforced by
  `validate_result_name()`. Rejection → `Error: ...` on stderr, exit 1, **no event written**
  (validated before the driver is touched).
- Uniqueness enforced by `find_result_by_name()` before any write. A collision prints the
  existing Result's `artifact_id`, value and state, exits 1, writes no event.
- Resolution order in `resolve_references` is unchanged and already correct: `name` first
  (`artifacts["result:<name>"]`), the transitional units fallback only after a `name` miss.
  Test `test_name_wins_over_units_fallback` pins that ordering.

### A2 — transitional units fallback + migration

- `build_units_fallback_index(driver, database, vocabulary=None)` in `seldon/paper/build.py`
  indexes Results that have **no `name`** and whose `units` is **not** in the vocabulary.
- `resolve_references(..., units_fallback=...)` retries a `result` token against that index
  after a `name` miss. One hit → resolves and emits a **non-fatal `SI-09`** warning naming
  the token, the matched `artifact_id`, and the remedy. More than one hit → **fatal `SI-09`**
  naming every candidate; the fallback never guesses.
- Removal is one deletion: `build_units_fallback_index`, its single call site in
  `build_paper`, and the `units_fallback` parameter. Marked `# TRANSITIONAL (AD-028)` with
  the removal condition on its face (§6 of the convention doc repeats it).
- `seldon result migrate-names [--dry-run] [--project-dir PATH] [--show-all]` ships.

### A3 — fail-loud references + backfill

- `seldon result register` now resolves **every** supplied reference before `create_artifact`,
  collects *all* failures, prints each one, and exits 1 with an untouched event log.
  Covers `--data-name`, `--script-name`, `--script-path`, and — see §7 — also `--script-id`,
  `--data-ids`, `--requirement-id`.
- `seldon result backfill-provenance --map FILE [--dry-run] [--project-dir PATH]` ships.
  YAML or JSON (`.json` suffix → JSON, else YAML). Shape-checked by `load_provenance_map()`,
  which rejects a non-mapping file, a non-mapping row, an unknown row key, a malformed
  `computed_from` list, or a blank `generated_by`.
  Row semantics: a row is resolved in full first; any unknown Result / DataFile / Script
  fails **that row as a whole** (no partial links), other rows still run, failures are
  reported at the end, exit code 1 if any row failed. Existing links are detected and
  reported as `already linked` rather than duplicated — `graph.create_link` uses `CREATE`,
  not `MERGE`, so without this check re-running would double every edge.

### A4 — `--allow-proposed`

- `seldon paper build --allow-proposed` → `build_paper(allow_proposed=True)`.
- SI-03 becomes non-fatal; render is `f"{str(value)} (proposed)"` — resolved value, one
  space, the literal `(proposed)`, from the module constant `PROPOSED_MARKER`.
- `verified` / `published` render byte-identically to before.
- Default (flag absent) is unchanged: SI-03 fatal, token left in place, build returns 1.
- Build summary prints `PROPOSED RESULTS RENDERED: <token count>` followed by the sorted
  distinct Result names, via `summarize_proposed()`. The block is printed only under
  `--allow-proposed` (without the flag the build aborts before the report).

---

## 2. A4 collision confirmation

**Confirmed against the actual rendering path.** `resolve_references._replace` ends in a
bare `return str(value)`. There is no number formatting, no significant-figure handling, no
units suffix, and no wrapping anywhere in the resolution path — the only other returns are
the error paths, which return the original token unchanged. `build_paper` writes the
resolved text straight into the assembled `.qmd`; the Tier 0/2/3 QC passes read the resolved
text but do not rewrite it.

So `<value> (proposed)` has **no collision risk**, and the Desktop-stated placement is used
as specified. Pinned by `test_verified_result_renders_bare_value_with_no_suffix`, which
asserts `{{result:m:value}}` on a Result with `value=0.9123456, units='score'` resolves to
exactly `0.9123456` — no `score`, no rounding.

One decision inside the decision, stated rather than asked: the marker is applied to
**whatever field the token requested**, not only `value`. `{{result:m:units}}` on a proposed
Result renders `score (proposed)`. Uniform beats special-cased, and a reader seeing any
field of an unverified Result should see that it is unverified.

---

## 3. Combined-vs-two-event choice for A2

**One combined `artifact_updated` event per promotion**, carrying
`{"name": <units>, "units": None}`, written through
`seldon.core.artifacts.update_artifact`.

**Reason — replay safety, not preference.** `seldon/core/sync.py::_apply_event` projects
events onto the graph by dispatching on `event_type`, and its final branch is
`logger.warning("Unknown event_type '%s' — skipped during sync")`. Emitting bespoke
`result_name_assigned` / `result_units_cleared` types would make every migration **silently
vanish on a full replay** unless that dispatcher learned them first — and `seldon/core/sync.py`
is outside this lane's file set. `artifact_updated` already replays through
`graph.update_artifact`, and Neo4j's `SET a += {units: null}` *removes* the property, so the
clear survives replay identically to the live write. The task file explicitly permits "one
combined event if the event schema prefers"; the event schema does prefer it.

Verified by `test_migrate_names_writes_one_replayable_event_per_promotion`: exactly one event,
type `artifact_updated`, payload `{"name": ..., "units": None}`.

---

## 4. Units vocabulary settled on

**Authoritative list:** `seldon/domain/result_units_vocabulary.yaml` (21 entries).

**Seed (14, from the task file):** `%`, `rate`, `ratio`, `count`, `tokens`, `chars`,
`seconds`, `minutes`, `docs`, `chunks`, `items`, `facts`, `USD`, `kappa`.

**Found in the codebase (7)** — every distinct string the repository already puts in a
`units` slot, from a sweep of all `units=` / `units:` literals across source, tests,
fixtures and domain-config help text:

| Unit | Where it came from |
|------|--------------------|
| `accuracy` | `--units` help text in `seldon/commands/result.py`; test fixtures |
| `acc` | `tests/test_paper_build.py` fixture |
| `ms` | `--units` help text in `seldon/commands/result.py` |
| `score` | the most common `units` literal in the test suite (18 occurrences) |
| `fraction` | `tests/test_verify.py` fixtures |
| `bits` | `tests/test_impact.py` fixture |
| `bits_per_decade` | `tests/test_impact.py` fixture |

`accuracy`, `acc`, `score` and `fraction` are metric names, not dimensional units. They are
in the vocabulary because the codebase already uses them as units, and omitting them would
make `migrate-names` promote them to names and rewrite existing Results. The vocabulary
records what the system treats as a unit, not what a metrologist would.

### Deviation from the task file's literal wording (packaging)

The task file says "put the final vocabulary in `docs/conventions/`". Split, on the
integrator's instruction and for a real reason:

- `pyproject.toml` ships `include = ["seldon*"]` and package-data
  `"seldon.domain" = ["*.yaml"]`. `docs/` is **not** in the installed distribution. A loader
  reading `docs/conventions/` would work in this editable checkout and fail with a
  config-not-found on any non-editable install.
- So: machine-readable YAML at `seldon/domain/result_units_vocabulary.yaml` (covered by the
  existing glob — **no `pyproject.toml` change was needed**, and none was made), human-readable
  doc at the spec'd `docs/conventions/result_units_vocabulary.md` pointing at the YAML.
- The loader resolves the path from its own `__file__`, never from cwd or a repo-root guess.
  Pinned by `test_units_vocabulary_loads_from_packaged_location` (asserts the path is under
  the installed `seldon/domain/`) and `test_units_vocabulary_is_cwd_independent` (chdirs to an
  unrelated tmp dir and loads successfully).

---

## 5. A2 dry-run against `ai-readiness-kg` — counts and full ambiguous list

Command (run from the seldon repo, **`--dry-run` only, no live run**):

```
seldon result migrate-names --dry-run --project-dir /Users/brock/GitHub/ai-readiness-kg
```

Database `seldon-ai-readiness-kg`. **Results with no `name`: 3592.**

| Class | Count |
|-------|-------|
| `migrated` | **3529** |
| `units_is_real_unit` | **23** |
| `ambiguous` | **40** |
| `no_units` | **0** |

`units_is_real_unit` (23) breaks down as `count` ×18, `kappa` ×3, `accuracy` ×2.

### Full ambiguous list (40 Results, 11 contested strings)

Every one is ambiguous for the same reason: **the units string is shared by more than one
unnamed Result, so `name := units` cannot be unique.** Grouped by contested string.

**`proportion` — 9 Results**
```
cab6927b-25e1-41c0-99e3-3b75504caa46  value=0.0792
6432b9f3-6bf8-4a74-a022-bc7d18803c8f  value=0.429
9ba07610-0602-459b-ad8d-05cc4104ad9a  value=0.167
ba24460d-f47d-45e6-894e-a894b98959e9  value=0.129
645f0bf3-af15-40f4-88cc-dd3e4c329e4a  value=0.121
02052ff6-3fd9-47a5-a9e1-25dea292a017  value=0.081
d40dccd3-8be2-4faf-8828-e1cf281d32ab  value=0.073
6cc5680a-2090-4b5c-baa3-49341b1cd54a  value=0.126
f425fcce-3474-4a6a-b0d5-9ffe8a8dfbc8  value=0.331
```

**`precision` — 5 Results**
```
def5744f-ad6c-477f-b682-a02fb1c1b75f  value=0.535
d2d23ae2-cdbe-4a19-940e-6d47a25bcb5e  value=0.831
8b42e4bd-5809-4c06-90b5-4c68466edeed  value=1.0
b547469b-40f1-4a2c-83c1-00c9d69821ff  value=0.921
cfeac3ca-dd83-4dc4-b7eb-069d9d46c24d  value=0.78
```

**`fabrication_share` — 3** · **`fabrication_share_upper95` — 3** · **`item_faithful_rate` — 3**
· **`atomic_facts` — 3** · **`admitted_items_per_chunk` — 3** · **`admitted_yield_ratio` — 3**
· **`quarantine_rate` — 3** · **`usd_per_admitted_item` — 3** · **`instrument_containment_recall` — 2**

The full per-artifact listing (every `artifact_id`, with its reason line) is reproducible in
under a second and is printed in full by the command itself — `ambiguous` is never truncated,
by design. Re-run the command above to regenerate it verbatim.

**These 40 Results need a human to assign distinct names before the ai-readiness-kg live run.**
The live run will migrate 3529 and leave these 40 untouched.

---

## 6. Premises in the task file that live state contradicted

Reported, not silently reconciled.

### 6.1 The "14 ambiguous cases" are name collisions, not vocabulary/token-key overlaps

The task file (§2 A2, third bullet) defines `ambiguous` as "`units` that both matches the
vocabulary AND is used as a token key somewhere (the 14 ambiguous ai-readiness-kg cases per
handoff)".

Implemented literally, that rule yields **zero** ambiguous cases in `seldon-ai-readiness-kg`
— because **that project has no `paper/` directory at all**, so there are no
`{{result:NAME:field}}` token keys on disk to overlap with. Verified: `/Users/brock/GitHub/ai-readiness-kg/paper`
does not exist, and a recursive grep for `{{result:` across the repo returns nothing.

The real ambiguity is a **name-uniqueness collision**, and it reproduces the handoff's "14"
exactly: **14 distinct `units` strings are carried by more than one unnamed Result**
(`count` 18, `proportion` 9, `precision` 5, `kappa` 3, `fabrication_share` 3,
`fabrication_share_upper95` 3, `item_faithful_rate` 3, `atomic_facts` 3,
`admitted_items_per_chunk` 3, `admitted_yield_ratio` 3, `quarantine_rate` 3,
`usd_per_admitted_item` 3, `accuracy` 2, `instrument_containment_recall` 2). Of those 14,
three (`count`, `kappa`, `accuracy`) are real units and are never promoted, so they are not
collisions; the other 11 cover the 40 ambiguous Results above.

**Decision (grounded, taken, not escalated):** `ambiguous` covers both conditions —
(a) units is a real unit AND is in use as a token key (the task file's rule, kept), and
(b) promoting units would produce a duplicate `name`, because several unnamed Results share
it or a named Result already holds it. `name` is declared unique per graph by A1; a
classifier that proposes a duplicate would be proposing a state its own contract forbids.
Each ambiguous row prints which of the two reasons applies.

Classification order matters and is deliberate: **vocabulary is checked first.** Several
Results measured in `count` is normal and is not a collision, because nothing is promoted for
them. Only the promote branch can collide. Getting this backwards moves all 23
`units_is_real_unit` rows into `ambiguous` — an intermediate version did exactly that, which
is how the ordering got pinned by `test_classify_duplicate_real_unit_is_not_a_collision`.

### 6.2 Baseline is **not** 697 passing

The ground rules state "Baseline is 697 passing". Measured at HEAD before any Lane A edit,
with the mandated command: **697 tests collected, 676 passed, 21 failed.** The 697 is the
*collected* count, not the passing count.

Of those 21, two are reproducible in isolation and attributable to the integrator's
`research.yaml` edit (see §8). The remainder are Neo4j contention from the four lanes sharing
one `seldon-test` database (§7.3) — every one of them passes when its file is run alone.

### 6.3 Confirmed premises (verified live, not assumed)

- `load_named_artifacts` already keys `"result:<name>"` and `resolve_references` already looks
  up `f"{reftype}:{name}"`. Confirmed by reading; resolve-by-name works the moment a Result
  carries a `name`. The defect was solely that nothing ever set one.
- `resolve_references` renders a bare `str(value)`. Confirmed — see §2.
- SI-03 was at `seldon/paper/build.py:217` (now moved by the additions above). Confirmed.
- **`seldon-seldon-self` contains 0 Result nodes.** Confirmed live by running
  `seldon result migrate-names --dry-run` in the repo: `Results with no name: 0`, all four
  classes 0. The A2 live run against seldon's own graph is a genuine no-op — no work invented.
- `seldon-ai-readiness-kg` holds 3592 Results, 0 with a `name`. Confirmed; see §5.

---

## 7. Deviations, scope extensions, and deferrals

### 7.1 Scope extension: `--script-id`, `--data-ids`, `--requirement-id` also fail loud

The task file names `--data-name` and `--script-name`. A bogus UUID passed to `--script-id`,
`--data-ids` or `--requirement-id` was the *same defect with a worse failure mode*: the code
wrote a `link_created` event and then ran a Cypher `MATCH ... CREATE` that matched nothing,
so the event log claimed a link the graph never had — a provenance lie that survives replay.
All three are now validated before `create_artifact`, and every unresolved reference in one
invocation is reported together rather than one per run.

### 7.2 Scope extension: `NAME` column in `seldon result list`

AD-028 makes `name` the identity of a Result; a listing that only showed a truncated UUID
would send every reader back to the graph. Pre-AD-028 Results show `-`.

### 7.3 New source file inside `seldon/domain/`

`seldon/domain/units_vocabulary.py` and `result_units_vocabulary.yaml` are **new files** in a
directory the ground rules mark "do not edit". No existing file in `seldon/domain/` was
modified; the coordinator's mid-task instruction directed the YAML there for packaging
reasons and the loader belongs beside its data. No other lane touches either file.

### 7.4 Deferred (not done, deliberately)

- **Removing the units fallback.** Explicitly out of scope for this task. Marked with its
  removal condition.
- **The ai-readiness-kg live migration.** `--dry-run` only, per the task file. That project's
  own task runs it — and must resolve the 40 ambiguous rows first.
- **`docs/design_decisions.md` append (task file §7, last bullet).** That file is the
  integrator's; this lane did not touch it. The AD-028 material it needs — name-as-token-key,
  the transitional fallback, and the `(proposed)` render form — is written up in
  `docs/conventions/result_units_vocabulary.md` and in §2–§4 above, ready to be appended.

---

## 8. Cross-lane file needs

### 8.1 `seldon/domain/research.yaml` — `name` on `Result` needs `category: system`

**Blocking two pre-existing test failures.** The integrator's `Result.name` property has no
`category:` key, so `seldon docs check` counts it as a *documentation* property. Two tests
assert the Result documentation-property total is 2 (`interpretation`, `methodology_note`):

```
tests/test_docs_check.py::test_docs_check_required_vs_doc_stats   assert 3 == 2
tests/test_docs_check.py::test_docs_check_mixed_completeness
```

Both reproduce in isolation, both were already failing at the pre-Lane-A baseline, and
neither `research.yaml` nor `tests/test_docs_check.py` is in this lane's file set.

**Recommended fix (integrator's call):** add `category: system` to the `name` property on
`Result` — `name` is a system identity key, not prose documentation, and the sibling `snapshot`
and `table_number` properties already use `category: system`. That restores `doc_total == 2`
and needs no test change. The alternative — updating the two test expectations to 3 — records
`name` as something an author is expected to *write about*, which it is not.

### 8.2 Nothing else

No other lane's file was needed. `seldon/core/artifacts.py`, `events.py`, `graph.py`,
`sync.py`, `task.py`, `mcp_server.py`, `go.py`, `init.py`, `cc.py` were read but not modified.
`update_artifact`, `create_artifact`, `create_link`, `get_artifact` and
`find_artifact_by_property` were sufficient as they stand.

---

## 9. Test results

**Lane A scope — green, repeatedly and in isolation:**

```
python -m dotenv -f .env run -- python -m pytest \
    tests/test_result_registry.py tests/test_result.py tests/test_paper_build.py -q
92 passed
```

- `tests/test_result_registry.py` — **47 tests, all new**
- `tests/test_paper_build.py` — **36 tests (24 pre-existing + 12 new)**
- `tests/test_result.py` — 9 pre-existing, unchanged and still passing

Widened to every neighbouring suite that touches Results, provenance, paper build, sync or
events:

```
python -m dotenv -f .env run -- python -m pytest \
    tests/test_result_registry.py tests/test_result.py tests/test_paper_build.py \
    tests/test_paper_sync.py tests/test_paper_context.py tests/test_paper_qc.py \
    tests/test_verify.py tests/test_name_resolution.py tests/test_impact.py \
    tests/test_artifacts.py tests/test_sync.py tests/test_events.py -q
320 passed
```

### A5 coverage map

| A5 requirement | Test |
|----------------|------|
| name uniqueness collision | `test_register_name_collision_names_existing_artifact_id` (asserts the existing `artifact_id` is in the message and the event log did not grow) |
| slug rejection | `test_validate_result_name_rejects_invalid_slugs` (8 cases), `test_validate_result_name_rejects_overlong`, `test_register_rejects_bad_slug_and_writes_no_event` |
| resolve-by-name | `test_register_accepts_a_free_name`, `test_name_wins_over_units_fallback`, plus the pre-existing `test_resolve_references_substitutes_value` |
| fallback-by-units + warning | `test_units_fallback_resolves_and_emits_warning`, `test_units_fallback_ambiguity_is_fatal_and_names_candidates`, `test_units_fallback_absent_falls_through_to_si01`, `test_build_units_fallback_index_excludes_real_units_and_named` |
| migrate-names, all three classes | `test_classify_all_three_classes`, `test_classify_marks_duplicate_units_ambiguous_not_migrated`, `test_classify_duplicate_real_unit_is_not_a_collision`, `test_classify_respects_already_claimed_names`, `test_classify_no_units_bucket`, `test_migrate_names_live_promotes_units_to_name`, `test_migrate_names_dry_run_writes_no_event`, `test_migrate_names_leaves_duplicates_alone` |
| unknown `--data-name` → error, **no event** | `test_register_unknown_data_name_errors_and_writes_no_event` (asserts `event_count` unchanged AND no node created), `test_register_unknown_script_name_errors_and_writes_no_event`, `test_register_reports_every_unresolved_reference_at_once` |
| backfill-provenance dry-run + live + partial failure | `test_backfill_provenance_dry_run_writes_nothing`, `test_backfill_provenance_live_creates_links`, `test_backfill_provenance_is_idempotent`, `test_backfill_provenance_partial_failure_continues_and_exits_nonzero` |
| `--allow-proposed` render form | `test_allow_proposed_renders_value_space_marker`, `test_allow_proposed_leaves_verified_render_unchanged`, `test_build_paper_allow_proposed_renders_and_summarises` |
| default-fatal preserved | `test_default_keeps_proposed_fatal_and_leaves_token`, `test_build_paper_without_allow_proposed_still_fails`, plus the untouched pre-existing `test_resolve_references_si03_proposed` |
| vocabulary loads from the packaged location | `test_units_vocabulary_loads_from_packaged_location`, `test_units_vocabulary_is_cwd_independent` |

### Full-suite count — and why it is not a clean number right now

The full suite was run repeatedly during this lane. **It is not stable while four lanes run
in parallel, because every lane's test run shares one `seldon-test` Neo4j database and
`conftest.py::clean_test_db` issues `MATCH (n) DETACH DELETE n` before each test.** One lane's
wipe lands inside another lane's test. Observed across runs in a ~30-minute window: 676/697,
886/934, 885/934, and once `525 passed, 409 errors` when the Neo4j instance was saturated and
the reachability probe itself started failing.

Evidence this is contention and not breakage: `tests/test_sync.py` failed 2 of 15 inside a
full run, then passed 15/15 three times consecutively when run alone; the 12-file
Result/paper/sync/events selection above failed 10 during a concurrent lane run and then
passed **320/320** minutes later.

**Reproducible non-contention failures, none of them Lane A's:**

| Failure | Owner |
|---------|-------|
| `test_docs_check.py::test_docs_check_required_vs_doc_stats`, `::test_docs_check_mixed_completeness` | integrator's `research.yaml` — see §8.1 |
| `tests/test_task_lifecycle.py::*` (many) | Lane C, mid-edit at the time of measurement |
| `tests/test_ontology.py::*` (12) | Lane B, mid-edit at the time of measurement |

**The integrator should take the authoritative full-suite count after all four lanes have
landed and are quiescent**, ideally with the lanes' test runs serialised. Lane A contributes
**+59 tests** (47 new + 12 added to `test_paper_build.py`).

---

## 10. Instructions honoured

- No commit, no push. No `seldon verify`. No Seldon task closed.
- No live migration run anywhere. Only `--dry-run`.
- `seldon/domain/research.yaml` untouched. `pyproject.toml` untouched.
- Every graph write goes through `create_artifact` / `update_artifact` / `create_link` in
  `seldon/core/artifacts.py`. No direct Cypher `SET`. History is append-only.
- No tunable is hardcoded in source: the units vocabulary is data
  (`seldon/domain/result_units_vocabulary.yaml`); the slug grammar, length limit, proposed
  marker, check id, migration classes and report preview size are named module constants
  with comments.
- Every new public function carries an Args/Returns/Raises docstring. No bare
  `except Exception: pass`; the one broad-ish catch (`load_provenance_map` parse errors)
  names the exception types, prints the diagnostic and exits non-zero.
