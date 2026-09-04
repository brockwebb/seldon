# RESULT — Seldon defect sweep: Result registry contract, task lifecycle, ontology gaps, small defects

**Task:** `cc_tasks/2026-09-03_seldon_defect_sweep_registry_lifecycle_ontology.md`
**Date executed:** 2026-09-03
**Executed by:** CC (integrator) + four lane subagents
**Closes:** `0bc41cfc`, `698d1d86`, `a3ba67a3`, `f951ed84`, `e3f751f6`, `1a23fd00`
**Design decision:** AD-028 — `docs/design/AD-028_result_names_and_task_lifecycle.md`
**Sub-RESULTs:** `cc_tasks/2026-09-03_seldon_defect_sweep_lane{A,B,C,D}_SUBRESULT.md`

---

## 1. Test counts

| | Count |
|---|---|
| Baseline at HEAD (measured before any change, serial, quiet machine) | **697 passed** |
| Final (serial, two consecutive runs) | **934 passed, 0 failed, 0 deselected** |
| Net new tests | **+237** |

New test modules: `test_result_registry.py` (35), `test_task_lifecycle.py` (37), `test_cc_description.py` (20), `test_handoff_picker.py` (15), `test_relationship_types.py` (7 functions / 49 parametrised cases). Plus additions to `test_paper_build.py`, `test_init.py`, `test_cc_utils.py`, `test_state.py`.

The task file said "memory says 341; verify". **Contradicted: the baseline is 697.** Lane A separately reported 676; that measurement was taken while three lanes ran concurrently against the shared test database and is superseded by the serial runs above. Lane D independently confirmed 697 in a pristine worktree.

## 2. Execution model — lane boundary was redrawn before starting

The task file's §1 requires disjoint file ownership and permits redrawing the boundary if the layout differs. **It differed.** Lanes A, B, and C all needed `seldon/domain/research.yaml`:

- A needed `Result.name`
- B needed `relationship_types`
- C needed the `ResearchTask` state machine

Rather than serialise three lanes, the integrator made **all** domain-config edits up front and handed the lanes a settled, read-only config. Lanes then owned only code and tests, and disjointness held. No lane reported a boundary violation, and no two lanes edited the same file.

## 3. Per-lane outcome

### Lane A — Result registry contract (`0bc41cfc`)

**Shipped:** `--name` (required at CLI, slug-validated, unique per graph, collision names the existing `artifact_id`); fail-loud reference resolution with **no event written** on any unknown reference; `migrate-names`; `backfill-provenance`; `--allow-proposed`; transitional units fallback (SI-09) with a per-token warning; packaged units vocabulary.

**A4 render placement:** `<value> (proposed)` as specified, **no collision**. Confirmed against the live rendering path — `resolve_references` ends in a bare `str(value)` with no number formatting, significant figures, or units suffix. That property is now pinned by a test, because the render form depends on it.

**A2 event shape:** one combined `artifact_updated` event, not bespoke event types, because `seldon/core/sync.py` silently skips unknown event types — a bespoke type would make every migration vanish on replay.

**Deviation from the task file's literal wording (integrator-directed):** the machine-readable vocabulary lives at `seldon/domain/result_units_vocabulary.yaml`, inside the package, because `pyproject.toml` does not ship `docs/` and a runtime config load from `docs/conventions/` would fail on any non-editable install. The human-readable doc is at the spec'd path, `docs/conventions/result_units_vocabulary.md`, and points at the YAML.

### Lane B — relationship types (`698d1d86`)

**Shipped:** 49 test cases. **Zero source changes were needed.**

The premise correction below is this lane's substantive finding. `corrects` Result→Result stays **rejected**: an erratum is an authored claim, and the domain models those as `DesignNote`, which carries the rationale; Result→Result supersession already has `validates` and `derived_from`.

`ontology ingest` was **deliberately not run**. Lane B changed no vocabulary markdown, and `ingest_command` bumps the master epoch *unconditionally* before comparing content — a ceremonial run would have burned epoch 3→4, staled every replica including ai-readiness-kg, and written a false `ontology_ingested` event. `sync` ran against `seldon-seldon-self` only: already up to date at epoch 3, 105 terms, no change.

### Lane C — ResearchTask lifecycle (`a3ba67a3`, `1a23fd00`)

**Shipped:** `withdrawn` terminal state; `seldon task close` / `withdraw` / `supersede`; MCP `seldon_task_withdraw` / `seldon_task_supersede`; claim marker on `accepted → in_progress`; `--stale-claims HOURS` report; `resolve_artifact_id` / `transition_task` extracted so CLI and MCP share **one** walker (the duplicate MCP walker was deleted). Fixed a latent `TypeError` in `seldon_task_create(blocks=...)` found en route.

**MCP shape choice:** two new verb tools, matching `seldon_task_close`'s existing precedent, rather than extending `seldon_task_update`. `seldon_task_update` now *refuses* `withdrawn`/`superseded`, because its `note` argument is echoed and never stored — that route could silently drop a required reason.

**Behavior change:** `seldon task list` default flipped from "everything" to "open work only". `--all` restores the old behavior. This breaks anything parsing the full listing.

### Lane D — small defects (`f951ed84`, `e3f751f6`, registrar description)

**Shipped:** date-prefix-then-mtime handoff picker; `seldon/paths.py` as the single derivation point for all default paths; stale-path fixes; corrected description parser; `seldon cc rederive-description`.

**D1 root cause (measured, not asserted):** the picker sorted the *whole filename* descending, so on a same-date tie the trailing slug — which carries no recency information — decided. Verified on the real files: `2026-09-02_sensor_layer…` (13:42) beat `2026-09-02_post_burn_reconciliation…` (17:46) purely because `s` > `p`.

**Beyond spec, accepted:** the spec's own phrasing ("package root + `ontology`") walks into a trap — `seldon/ontology/` is the parser *code* package, so that derivation resolves to the wrong directory on every install. Resolution now requires a marker vocabulary file. A fourth stale path the task never named was also fixed: `go.py::_read_system_standards` hardcoded `~/Documents/GitHub/CLAUDE.md`.

## 4. C1 finding — where the superseded rows came from

**The task file's premise is stale, and this is the answer to §7's C1 question.**

`superseded` has been a first-class terminal state in the `ResearchTask` state machine since commit `9612b3b` (2026-06-18), with an in-file comment citing `cc_tasks/2026-06-18_cc_task_researchtask_superseded_terminal.md`. It was already reachable from the active states and already unreachable from `completed`/`verified`. `seldon_task_update`'s MCP docstring already documented it. So `a3ba67a3`'s claim that "no such state exists" was false when written.

**The rows were not written by a bypass path.** Evidence: 31 `artifact_state_changed` events, all `proposed → superseded`, 8 by `desktop` and 23 by `human`, and zero artifacts created directly into the state. They went through the legitimate state machine.

**Count is 31, not 30** — one more landed 2026-09-02, after the premise was written.

**The real defect was discoverability**, not the state machine: there was no `seldon task supersede` command, so the state was reachable only by hand-driving `task update`. That is what shipped.

**All 31 rows lack a `terminal_reason`.** Counted and reported, **not backfilled** — a reason invented after the fact is not a reason.

## 5. A2 dry-run against `seldon-ai-readiness-kg`

Dry-run only. **No live run, no events written to that project.** Independently re-run by the integrator; numbers reconcile to 3592.

| Class | Count |
|---|---|
| `migrated` | 3529 |
| `units_is_real_unit` | 23 |
| `ambiguous` | 40 |
| `no_units` | 0 |

**The task file's `ambiguous` definition yields zero.** It defined ambiguous as "units matches the vocabulary AND is used as a token key somewhere" — but ai-readiness-kg has **no `paper/` directory**, so there are no token keys to overlap with. The operative hazard is a **name collision**, which would violate A1's own uniqueness contract. The class now covers both conditions and each row prints which applies.

The 14 `units` strings shared by 2+ unnamed Results — matching the handoff's original "14" exactly — are:

| units | Results | classified |
|---|---|---|
| `count` | 18 | `units_is_real_unit` |
| `proportion` | 9 | ambiguous |
| `precision` | 5 | ambiguous |
| `kappa` | 3 | `units_is_real_unit` |
| `fabrication_share` | 3 | ambiguous |
| `fabrication_share_upper95` | 3 | ambiguous |
| `item_faithful_rate` | 3 | ambiguous |
| `atomic_facts` | 3 | ambiguous |
| `admitted_items_per_chunk` | 3 | ambiguous |
| `admitted_yield_ratio` | 3 | ambiguous |
| `quarantine_rate` | 3 | ambiguous |
| `usd_per_admitted_item` | 3 | ambiguous |
| `accuracy` | 2 | `units_is_real_unit` |
| `instrument_containment_recall` | 2 | ambiguous |

63 Results sit in those groups: 23 classify as `units_is_real_unit`, the other 40 as `ambiguous`.

**For the downstream ai-readiness-kg task:** the 40 ambiguous Results need human-assigned distinct names **before** its live run. The 23 `units_is_real_unit` Results also stay unreferenceable by token until a human names them — the machine correctly declines to guess which of three Results named `kappa` a citation meant.

## 6. Premises in the task file contradicted by live state

Recorded, never silently reconciled. The task file is immutable.

1. **Baseline is 697, not 341.**
2. **Relationship types do not live in the ontology.** §3 directed adding edge types to the master `seldon-ontology`. That database holds `OntologyTerm` vocabulary artifacts parsed from markdown, with five term-to-term edge types closed in `parser.py`; both `ingest` and `_do_sync` match only term-to-term edges. The validator that actually rejected `DataFile-[:GENERATED_BY]->Script` is `seldon/domain/loader.py::validate_relationship`, reading `relationship_types` from `research.yaml`. **Executed literally, the task would have left the defect in place and added five pseudo-terms to the validity vocabulary.**
3. **`superseded` already existed** (§4 above). Only `withdrawn` was genuinely missing.
4. **`seldon init`'s ontology default was already derived** from the package location, not hardcoded — but the derivation was still wrong for a wheel install, and stale `Documents/GitHub` strings survived in four other places.
5. **Lane ownership was not disjoint as drawn** (§2 above).
6. **The `ambiguous` definition yields zero** (§5 above).
7. **The repo is at `/Users/brock/GitHub/seldon`**, not `/Users/brock/Documents/GitHub/seldon` as `CLAUDE.md` states. The latter is a symlink to the former.

## 7. Scope not completed

**D3's live re-derivation of `7120e000` and `676c0e39` is BLOCKED and was not performed.** Both source files — `cc_tasks/2026-04-16_file_issues_and_convention.md` and `cc_tasks/2026-05-07_ontology_tracer_bullet.md` — are absent from disk **and from all git history** (`cc_tasks/` was only tracked from commit `c53b3c9`). Independently confirmed by the integrator with `git log --all --diff-filter=A`. `rederive-description` exits 1 with a clear diagnostic rather than guessing; their descriptions are unchanged. **Resolving this requires the files, which no longer exist.**

Lane D did survey all 49 registered CC tasks: 37 have missing source files, 9 were fixable and were re-derived live via `artifact_updated` events — including this sweep's own artifact `bc2354f2` (`**Immutable once written…**` → `Seldon defect sweep: Result registry contract, task lifecycle, ontology gaps, small defects`).

Also noted by Lane D: only the **em-dash-H1 shape** is a live parser bug. The other two named failure shapes no longer reproduce — they are frozen output of already-fixed parsers, which is precisely why `rederive-description`, not the parser fix, is the real deliverable for existing rows.

## 8. Defects found and fixed that the task did not name

**Test-suite auth lockout (blocking, found by Lane C, fixed by the integrator).** `tests/test_init.py` set `NEO4J_PASSWORD="wrong-on-purpose-for-this-test"` and ran `seldon init` against the **live** server six times. That trips Neo4j's `AuthenticationRateLimit`, after which **every connection from every process** is refused for the lockout window. The file itself passed and left the server locked, poisoning unrelated test files. This produced every unstable count observed during this run (18 → 24 → 41 → 51 → 409 errors). Fixed by making the server unreachable (`bolt://127.0.0.1:1`) instead of unauthenticated — no credential is ever presented. `test_init.py` now runs in 1.0s instead of 6.7s because it no longer contacts a real server.

**`seldon init` hardcoded its Neo4j URI (integrator).** Found while fixing the above: `init.py` hardcoded `bolt://localhost:7687` in two places — the value written into `seldon.yaml` and the URI it connected to — and ignored `NEO4J_URI` entirely. A "Never Hardcode" violation that also meant `seldon init` could not target a non-default server. Now resolved once via `_resolve_neo4j_uri()` and used for both, so a project can never be configured for one server and initialised against another.

**Property-category defaults (integrator).** `PropertyDef.category` defaults to `"documentation"`, so a property declared with neither `required` nor `category` silently counts as a documentation gap. Both new properties were affected: `Result.name` (an identifier) and `terminal_reason` (absent for every task that ended another way — one false gap per completed task). Both set to `category: system`, matching AD-027's `snapshot` precedent.

**Three stray probe databases** (`seldon-derived-default-probe`, `seldon-env-override-probe`, `seldon-no-ontology-probe`) left on the real Neo4j server by earlier runs of the offending test were dropped. The URI fix prevents recurrence.

## 9. Findings recorded, not fixed (out of scope)

1. **Shared test database is a concurrency hazard.** All Neo4j tests share one `seldon-test` database that `clean_test_db` wipes wholesale, so parallel pytest processes corrupt each other. Real and directly observed during this run, though secondary to the auth lockout. Fix would be to parameterise `TEST_DATABASE` per worker.
2. **`ontology ingest` has no deprecation pass.** Master carries 5 orphan `active` terms from epoch 1 that no longer exist in the markdown, and `sync` replicates them into every project.
3. **`seldon-seldon-self` holds both `INFORMS` (8) and legacy lowercase `informs` (4) edges.** Type-filtered queries silently miss the latter.
4. **37 of 49 registered CC tasks have missing source files** — a provenance gap predating this task.

## 10. Install / refresh mechanism (§6 step 4)

**No reinstall was required.** `seldon` is already installed **editable** into `/opt/anaconda3/lib/python3.12/site-packages`, with the project location recorded as `/Users/brock/Documents/GitHub/seldon`, which is a **symlink** to `/Users/brock/GitHub/seldon`. New subcommands therefore appear on PATH immediately. Verified by invoking them: `seldon task --help` lists `close`, `withdraw`, `supersede`; `seldon result --help` lists `migrate-names`, `backfill-provenance`.

## 11. Design decisions recorded (§7 requirement)

`docs/design/AD-028_result_names_and_task_lifecycle.md` (full spec) plus an **appended, dated** summary entry in `docs/design/seldon_architectural_decisions.md`. Append only; nothing existing was rewritten. Covers all four required items: name-as-token-key with the transitional units fallback; the `(proposed)` render form; terminal-state semantics; claim-marker semantics.

## 12. Verification

- `python -m dotenv -f .env run -- python -m pytest tests/ -q` → **934 passed**, twice consecutively.
- `seldon verify` → all checks passed, exit 0.
- New CLI commands confirmed live on PATH.
