# RESULT — AD-028 amendment + the 2026-09-04 defect sweep

**Task:** `cc_tasks/2026-09-04_ad028_grammar_amendment_migrate_atomic.md`
**Date executed:** 2026-09-04
**Executed by:** CC (integrator) + five lane subagents, in worktree `defect-fixes-ad028`
**Closes:** `a79bf520` (the task file), plus `0d2ce3d1`, `9ae4b245`, `a9e7ed28`, `868d6bb0`
**Design record:** AD-028 Amendment 01 — `docs/design/AD-028_result_names_and_task_lifecycle.md`
**Sub-RESULTs:** `cc_tasks/2026-09-04_{test_db_isolation, ad028_grammar_amendment_migrate_atomic, ontology_ingest_defects, reltype_case_and_source_provenance, related_terms_parser_regression}_SUBRESULT.md`

---

## 1. Test counts

| | Count |
|---|---|
| Baseline at worktree branch point (serial, quiet) | **934 passed** |
| Final (serial, two consecutive runs) | **1180 passed, 0 failed** |
| Net new | **+246** |

New modules: `test_verify_reltype_case.py` (35), `test_ontology_ingest_lifecycle.py` (25), `test_testdb.py` (20), `test_parser_sections.py` (20), `test_cc_git_guard.py` (20), `test_verify_reltype_migration.py` (16), `test_cc_orphan_supersede_migration.py` (13), `test_mcp_cc_git_guard.py` (9), `test_result_grammar.py` (6), plus additions to `test_result_registry.py`, `test_ontology.py`, `test_mcp_tools.py`.

`seldon verify` exits 0 with both new checks green:
```
✓ Relationship types  All canonical (uppercase)
✓ Task source files   No open task is missing its spec (13 of 50 resolve on disk); 37 settled
✓ Ontology            Up to date (epoch 4)
```

## 2. §3 reporting for the task file

**Regex constant location:** `seldon/commands/result.py::RESULT_NAME_PATTERN`, the single definition point. `register --name` and `migrate-names` both import it. A grep test asserts the pattern string appears nowhere else in source or config; a companion test asserts the scan actually reaches `research.yaml`, the conventions doc and `README.md` across 100+ files, so a careless exclusion cannot make the grep test vacuously pass. `docs/design/`, `cc_tasks/` and `handoffs/` are exempt by a named constant carrying its rationale: an amendment must quote both the old and the new pattern, and rewriting history to satisfy a lint would destroy the audit trail.

**Four-class dry run on a fixture, and dry-run/live agreement:** proven by `test_migrate_names_dry_run_and_live_run_agree_row_for_row`, which asserts against the **event store and the graph**, never against the dry run's own arithmetic. Dry run reports `refused: 2` and grows the event store by zero; live `--partial` produces an identical summary, the same exit code, exactly `migrated + name_set_units_pending` events, and a touched-`artifact_id` set equal to the rows the plan named — with both refused rows read back from the graph still carrying no `name`. Structurally they cannot diverge: both paths consume one plan from one `build_migration_plan` call, and the grammar check moved onto that shared path.

**`--partial` semantics:** without it, any refusal aborts with nothing written and a non-zero exit. With it, valid rows are written **and the run still exits non-zero.** The task file specified the exit code only for the no-`--partial` case; treating `--partial` as "write the valid rows" rather than "call this a success" prevents a downstream script reading exit 0 as "everything migrated."

**ai-readiness-kg dry run (DRY RUN ONLY — no live run; that project has its own task):**

| Class | Count |
|---|---|
| `migrated` | 953 |
| `name_set_units_pending` | 2576 |
| `already_named` | 0 |
| `units_is_real_unit` | 23 |
| `ambiguous` | 40 |
| `no_units` | 0 |
| **`refused`** | **0** — exit 0 |

Sums to 3592. **`refused: 0` is the proof the amendment clears the damage:** those 953 uppercase names are exactly the rows the old live run refused after having already written 2576. Independently re-run by the integrator. Residual for the downstream task: 40 `ambiguous` rows across 11 contested strings, a uniqueness question for a human, not a grammar problem.

## 3. The other four defect tasks

### `0d2ce3d1` — test database isolation
Per-process databases via `tests/testdb.py`. Resolution order: `SELDON_TEST_DATABASE` verbatim → `seldon-test-p<pid>-<worker>` under xdist → `seldon-test-p<pid>`. Created at session start, dropped at teardown, with a self-healing sweeper for interrupted runs.

Evidence is a **negative control**, not just a green suite: forcing two processes onto the shared `seldon-test` reproduces the original defect (15 and 19 failures, same signatures as 2026-09-03), while the fix passes 2 concurrent runs, **4 concurrent runs** (the original four-lane scenario), and 2 concurrent *full* suites. Cost is +6.3s fixed per session, not per test. The sweeper's match is anchored to `seldon-test-p<pid>`, verified live against a server holding 25 real project databases: planted orphan dropped, live-PID database and decoy untouched.

**The task's own prescription was wrong** and was corrected: it said suffix with `PYTEST_XDIST_WORKER`, but `gw0` exists in *every* concurrent xdist run, so two agents running `pytest -n 4` would have collided exactly as before. PID is what guarantees uniqueness; the worker id is kept only for readability.

### `9ae4b245` — ontology ingest
Defect (1) fixed: `ingest` now builds a plan and compares content first, bumping the epoch only on real change. Proven on the **live master**: a real ingest reported `No changes: 100 terms already current. Master epoch stays 3; no event written.` The post-run snapshot diffed byte-identical and the event log md5 was unchanged. Under the old code that same run would have burned epoch 3→4 and staled every replica.

Defect (2) shipped as `--deprecate-missing`, default off, `--dry-run --deprecate-missing` as the rehearsal, orphans reported by default and never counted toward the epoch unless the flag is set. Sync propagates a master deprecation to replicas that already carry the term and will not introduce a deprecated term into a replica that never had it.

**Two tests encoded the defect** and were rewritten: `test_ingest_increments_epoch` asserted epoch 2 after two *identical* ingests — the suite was green on behaviour that was wrong.

### `a9e7ed28` — relationship type case
Audit across **all 30 databases** — including `wintermute-intake` at 3,016 rel types and 3.7M relationships — found **only `seldon-seldon-self`** affected (`INFORMS` 8 + `informs` 4). Migrated 9 rel types/61 rels → 8/61, `informs` 0; edge count preserved, re-run is a clean no-op. Nothing written outside `seldon-seldon-self`. `seldon verify` gained Check 8.

The 4 lowercase edges had no `created_at` and no `link_created` events: raw-Cypher drift, unproducible by replay and unremovable through the sanctioned API, since `artifacts.remove_link` uppercases its argument.

Graded `fail` but **not Tier A**: a lowercase twin is invisible to every type-filtered query, so the failure mode is a confidently wrong answer — but `--strict` is the CC-task machine gate, and this reports history rather than the change in hand, so Tier A would block every commit for a future adopter with a legacy graph. Not wired into `--fix`: a rename deletes and recreates edges, so it gets its own dry-run-by-default migration script.

### `868d6bb0` — task source-file provenance
`seldon verify` Check 9; git-tracking guard on `cc register` / `cc complete` with `--allow-untracked`; dry-run-by-default supersede migration.

**37 orphans confirmed exactly — but the task's prescribed action was wrong.** Of 50 tasks carrying a `source_file` (not 49), 33 are `completed` and 1 `rejected`, and `superseded` is deliberately unreachable from those states because relabelling a finished task would corrupt the honest completion record. **Superseding all 37 would have destroyed the very provenance the task set out to protect.** Only the 3 open orphans were superseded, reason `source_file lost pre-c53b3c9`, no descriptions invented: `e911fc13`, `7120e000`, `676c0e39` — including both ids the 2026-09-03 sweep recorded as unrecoverable. The remaining 34 are counted in the verify summary as settled.

## 4. A defect found mid-flight and fixed: the related-terms parser regression

Task `9ae4b245` could not be honestly closed, because its premise was false in an instructive way. The 5 "orphan" terms were **not absent from the markdown** — they are defined today under `## Related Terms (Defined Elsewhere)`. `_parse_related_terms` had an unbounded forward scan that walked past its own section and read the *next* table positionally, so `row[1]` (Origin Project) became `definition`. That is the source of two junk terms whose definition is the literal string `leibniz-pi`.

**Lane 2 stopped rather than deprecate.** Deprecating those five would have frozen a silent parser regression into a terminal state across every replica. That refusal is the single most valuable thing in this sweep.

Corrections to the integrator's brief, from Lane 4:
- The regression is commit **`b6714f3` (2026-03-28)**, not `62d6bdf`. Exposure was **5 months**, not 4.
- The 5 terms were never missing from the graph — they exist at epoch 1 from the *pre-regression table*, so the live plan was **0 creates, 5 updates**, not 5 adds.
- **Seven parsers shared the same unbounded idiom**, not one. Only Related Terms had leaked, because only its section stopped containing a table. All are now bounded.

Format decision: definition-list only, no table branch. `PRACTITIONER_VOCABULARY.md` has zero `|` lines and its own parser; the table form exists only in history; and "accept whichever shape turns up" *is* the bug. A revert now raises instead of being silently absorbed.

Detectability, so this class of bug cannot recur silently: structural bounds make leaking impossible; a runtime `VocabularyParseError` fires when a claimed section yields **zero** rows (floor is 1, not N, so a legitimate row deletion does not break every project's ingest); and CI asserts the exact heading set with per-section counts.

**Live master: epoch 3 → 4**, snapshotted before and after, 105 terms both sides, 36 relationships byte-identical, **exactly 7 nodes touched** — 5 related terms updated, 2 junk terms `active → deprecated`. `seldon-seldon-self` synced to epoch 4 (`0 new, 5 updated, 2 deprecated`). No other project written to.

## 5. Also fixed: the MCP side door

Lane 3's guard closed `seldon cc register` / `cc complete`, but MCP `seldon_cc_register` / `seldon_cc_complete` duplicate that logic and bypassed it — a Desktop session could still register an unrecoverable task file after the CLI stopped allowing it. A guard with an open side door is not a guard. Both tools now take `allow_untracked` and reuse `cc.py`'s status predicate and reason/remedy tables, so the two front ends can diverge in wording but not in rules. 9 tests, including end-to-end refusal through the tools themselves, since wiring is the part that regresses.

Two `test_mcp_tools.py` tests began failing on the new guard because they build temp project dirs with no git work tree. They were made explicit with `allow_untracked=True` and a comment naming where the guard *is* covered — the failures were correct behaviour, not a regression.

## 6. Premises contradicted by live state

1. **`PYTEST_XDIST_WORKER` alone is not unique** (§3, `0d2ce3d1`).
2. **The 5 ontology orphans were not orphans** (§4) — the deprecation premise of `9ae4b245` was false.
3. **The regression commit and duration were wrong** in the integrator's brief (§4).
4. **`superseded` is unreachable from `completed`/`rejected`**, so 34 of the 37 could not take the prescribed action (§3, `868d6bb0`).
5. **50 tasks carry a `source_file`, not 49.**
6. The integrator's own first verification of the ai-readiness-kg dry run **ran stale code** — the `seldon` console script resolves to the main checkout, not the worktree. Corrected by forcing the module path; the numbers then matched Lane 1 exactly. Recorded because it is a live trap for anyone verifying CLI behaviour from a worktree.

## 7. Findings recorded, not fixed

1. **`seldon-seldon-self`'s event log has 9 legacy lines with no `event_id`, so `read_events` raises and full replay is currently impossible.** Recoverability is a declared guaranteed property of Seldon and does not hold for its own graph. This is the most serious open item.
2. `## Core Instrument Terms`, `## Framework Terms (Cross-Cutting)` and `### Core Construct: Context Window` are parsed by **nobody** — 6 real terms that have never been in the graph. Declared explicitly in `SECTION_COVERAGE` and left unfixed so the live dry run matched expectation.
3. **13 project replicas still carry both junk terms as `active` at epoch 3**, plus `seldon-sfv-paper` (epoch 2) and `seldon-test-project` (epoch 1). Each needs only `seldon ontology sync` from its own directory. Not run, per scope.
4. `_term_content_hash` ignores `name` / `citations` / `extra`; widening it would force a mass live update and was deliberately not done mid-fix.
5. `python -m seldon` is broken (no `__main__.py`), degrading `verify --fix`.
6. `seldon.yaml:16` hardcodes the ontology source at the main checkout, so a worktree cannot test a vocabulary edit — a "Never Hardcode" violation.
7. `seldon-test-project` (48 terms, epoch 1) looks like a droppable stale artifact.

## 8. Scope deliberately not taken

The 12 April/May design and feature backlog items (`7e862893`, `84c880a8`, `59d67aeb`, `6dad25b9`, `63e151d5`, `369fc223`, `69494d5c`, `3454bf69`, `30746b6b`) remain open. The 2026-09-03 sweep excluded them by name as "feature/design backlog, not defects", and several — bold-usage conventions, source-tier framing — are value judgements that the operator is the sensor for, not defects a lane can settle.
