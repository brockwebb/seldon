# SUBRESULT — Lane 1: AD-028 Amendment 01 grammar + predictive, atomic `migrate-names`

**Task:** `cc_tasks/2026-09-04_ad028_grammar_amendment_migrate_atomic.md`
**Lane:** 1 of 3 (worktree `.claude/worktrees/defect-fixes-ad028`)
**Date:** 2026-09-04
**Scope executed:** §1.1, §1.2, §1.3, §3. §0 (the amendment docs) was already
done by the integrator and was not touched. §2's close / commit / push and
`seldon verify` belong to the integrator and were not run.

---

## 1. Files changed

| File | Change |
|------|--------|
| `seldon/commands/result.py` | Grammar constant widened and made the single definition point; `refused`, `name_set_units_pending` and `already_named` classes; `build_migration_plan`; `write_migration_report`; `migrate-names` rewritten as validate-all-then-write with `--partial` and `--report`. |
| `seldon/domain/research.yaml` | `Result.name` description only — the regex removed, replaced by a pointer to the constant. Nothing else in the file. |
| `docs/conventions/result_units_vocabulary.md` | §1 grammar paragraph — regex replaced by prose plus a pointer to the constant. |
| `tests/test_result_registry.py` | Grammar parametrize sets updated for the amendment; 32 new test nodes for the migration plan. |
| `tests/test_result_grammar.py` | **New.** 6 tests, including the grep test. |

No file outside the lane's ownership list was edited. `seldon/commands/ontology.py`,
`verify.py`, `cc.py`, `seldon/core/**`, `seldon/paper/**`, `tests/conftest.py`,
`tests/testdb.py` and `docs/design/**` are untouched by this lane.

---

## 2. Test counts

| Run | Result |
|-----|--------|
| Baseline in this worktree, before any Lane 1 edit | **1001 passed, 0 failed** |
| Lane 1's own files after the change (`tests/test_result_registry.py` + `tests/test_result_grammar.py`) | **85 passed, 0 failed** |
| New test nodes added by Lane 1 | **+38** (32 in `test_result_registry.py`, 6 in `test_result_grammar.py`) |
| Expected full-suite total attributable to Lane 1 | **1039** |

**Full-suite state at the time of writing: 1029 passed, 10 failed.** Every one of
the 10 failures is in `tests/test_ontology.py` (`TestIngest`, `TestSync`), raised
from `seldon/commands/ontology.py` with
`TypeError("'NoneType' object is not subscriptable")` inside `_do_ingest`. That
file is Lane 2's and was mid-edit during this run; it passed at the 1001 baseline.
A confirming run with `--ignore=tests/test_ontology.py` gave **1036 passed, 1
failed**, the single failure being `tests/test_ontology_ingest_lifecycle.py::
TestNoOpIngest::test_empty_parse_is_refused` — a test file Lane 2 added during the
run. Nothing in either failure set touches Result, the name grammar, or the
migration. **Lane 1 is green; the integrator should see 1039 once Lane 2 lands.**

Test command used throughout, per the ground rules:
`python -m dotenv -f .env run -- python -m pytest tests/ -q`.

---

## 3. The regex constant location

**`seldon/commands/result.py:37`**

```python
RESULT_NAME_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
```

That is the only place the pattern string is written. The four former copies now
derive from it or describe it in words:

| Former copy | Now |
|-------------|-----|
| `validate_result_name` docstring | names the constant; does not restate the pattern |
| `validate_result_name` error message | interpolates `RESULT_NAME_PATTERN.pattern` plus `RESULT_NAME_GRAMMAR_PROSE` |
| `register --name` help text | f-string interpolating `RESULT_NAME_PATTERN.pattern` and `RESULT_NAME_MAX_LENGTH` |
| `seldon/domain/research.yaml` `Result.name` description | prose; points at `seldon.commands.result.RESULT_NAME_PATTERN` |
| `docs/conventions/result_units_vocabulary.md` | prose; points at the constant, and says why it does not reproduce it |

### The grep test

`tests/test_result_grammar.py::test_result_name_pattern_appears_in_exactly_one_file`
walks every authored text file in the repo, counts occurrences of
`RESULT_NAME_PATTERN.pattern`, and asserts the hit set is exactly
`{"seldon/commands/result.py": 1}`.

Two design points worth stating, because both are places where a grep test can
quietly become worthless:

1. **The needle comes from the constant, never from a literal.** The test file
   itself therefore cannot become the copy it exists to prevent, and the test
   automatically tracks any future amendment to the grammar.
2. **A companion test guards the guard.**
   `test_scan_actually_reaches_the_files_it_claims_to` asserts the scan reaches
   `research.yaml`, the conventions doc and `README.md`, and covers >100 files.
   Without it, a bad exclusion rule would make the grep test pass by scanning
   nothing — the same failure mode as the defect this task fixes.

**Exemptions, and why.** The scan skips `docs/design/`, `docs/plans/`,
`docs/superpowers/`, `cc_tasks/`, `handoffs/`, `issues/` and `output/`. Those are
immutable records of what was decided or done at a past moment, not statements of
what the grammar is now. AD-028 Amendment 01 necessarily quotes *both* the
original and the amended pattern — that is what an amendment is — and this task
file quotes both as well. Editing history to satisfy a lint would destroy the
audit trail the amendment exists to create. The exemption list is a named
constant in the test with that rationale attached, so it is a decision on the
record rather than a silent hole.

---

## 4. Four-class (in fact seven-class) dry-run output against the fixture

`MIGRATION_CLASSES` now has seven members, and every Result in the graph lands in
exactly one, so the summary table reconciles against the total row count:

| Class | Meaning | Planned action |
|-------|---------|----------------|
| `migrated` | no name; units is a promotable token key | `set_name_and_clear_units` |
| `name_set_units_pending` | name set, units still holds the same string | `clear_units` |
| `already_named` | name set, nothing to do | `none` |
| `units_is_real_unit` | no name; units is a genuine unit | `none` |
| `ambiguous` | no name; the string is contested | `none` |
| `no_units` | no name and no units | `none` |
| `refused` | would be migrated, but the name fails validation | `none` |

The test fixture `_mixed_fixture` builds ten Results covering all seven. Its
dry-run summary, asserted in
`test_migrate_names_dry_run_reports_all_seven_classes`:

```
Result name migration — database '<per-process test db>' (DRY RUN)
  Results in graph: 10
    migrated                 2
    name_set_units_pending   1
    already_named            1
    units_is_real_unit       1
    ambiguous                2
    no_units                 1
    refused                  2
```

A note on the fixture: `units` is a *required* property on `Result`, so the
`no_units` row cannot be created with an empty one. It is produced the way the
graph really produces it — created, then cleared by the same `artifact_updated`
event the migration itself emits.

---

## 5. Dry run and live run agree — proven by test

`test_migrate_names_dry_run_and_live_run_agree_row_for_row` is the test that
carries the contract. On the ten-row fixture it:

1. runs `--dry-run --partial`, asserts `refused == 2`, and asserts the event
   store did **not** grow;
2. runs the live `--partial`, asserts the live summary table is *identical* to
   the dry run's, and that both exit with the same code (1);
3. asserts the number of new events equals exactly
   `migrated + name_set_units_pending` (3), and that the set of touched
   `artifact_id`s is exactly the three rows the plan said it would touch;
4. reads the graph back and asserts both refused rows still carry no `name`, and
   both migrated rows carry the names the dry run predicted.

Step 3 is the part that matters. **Agreement is asserted against the event store
and the graph, never against the dry run's own arithmetic.** The originating
defect passed a "class counts sum to the row total" check while validating
nothing: the counts were internally consistent and still wrong. No test in this
lane accepts a reconciled total as evidence that a row was validated.

Exit-code parity is part of the prediction, not just the counts.
`test_migrate_names_dry_run_predicts_the_live_exit_code_when_blocked` runs both
paths without `--partial` on the same fixture and asserts both exit 1 —
the dry run prints `Predicted live exit code: 1` rather than exiting 0 and
letting the caller discover the refusal from the live run.

The structural reason they cannot disagree: `--dry-run` and the live path consume
**one** plan from **one** `build_migration_plan` call. The grammar check that used
to live only on the write loop now lives inside `classify_unnamed_results`, on the
shared path. There is no second code path left to drift.

---

## 6. `--partial` and no-`--partial` behaviours

| Condition | Without `--partial` | With `--partial` |
|-----------|--------------------|------------------|
| Plan has zero refusals | writes everything, exit 0 | identical, exit 0 |
| Plan has any refusal | **nothing written at all**, refusals printed to stderr, exit 1 | valid rows written, refused rows untouched, exit 1 |

Tests:

- `test_migrate_names_without_partial_writes_absolutely_nothing_on_refusal` —
  asserts `event_count()` is unchanged (the event store did not grow), exit 1,
  and that the *valid* row is still unmigrated and the pending row still holds
  its stale `units`. One bad row aborts the whole run.
- `test_migrate_names_partial_writes_the_valid_rows_and_still_exits_nonzero` —
  asserts exactly 3 new events, the promoted names in the graph, `units`
  cleared, and exit **1**.
- `test_migrate_names_clean_graph_needs_no_partial_flag` — `--partial` changes
  nothing when there is nothing to refuse.

**Design decision worth flagging to the integrator:** a `--partial` run that
refused anything still exits **non-zero**. `--partial` changes *whether the valid
rows are written*, not *whether the run succeeded*. A run that left rows behind
did not complete, and returning 0 would let a caller's `&&` chain treat an
incomplete migration as a finished one. This is stated in the `--partial` help
text and in the command docstring.

---

## 7. Resumability

- `test_migrate_names_skips_rows_that_already_carry_a_name` pins the
  pre-existing behaviour: a named Result is never renamed, and no event is
  written for it.
- `test_migrate_names_clears_pending_units_without_reassigning_the_name` covers
  the ai-readiness-kg half-applied state. It asserts the run emits **one** event
  whose properties contain `units: None` and **no `name` key** — the clear alone.
  Re-asserting a name that is already correct would be a second write of a
  correct value and would hide whether the clear was the missing half.
- `test_migrate_names_is_idempotent` runs the live migration twice and asserts
  the second run writes zero events and reports `already_named: 2`.

---

## 8. The `--report PATH` JSONL

One JSON object per line, in plan order, **one line per Result in the graph** —
including rows the run will not touch, so a consumer can reconcile the file
against the graph's row count. Written on both the dry run and the live run.
Parent directories are created. Field set (`MIGRATION_REPORT_FIELDS`):

| Field | Value |
|-------|-------|
| `artifact_id` | the Result's id |
| `current_name` | `name` as it stands now, or `null` |
| `current_units` | `units` as it stands now, or `null` |
| `class` | one of the seven `MIGRATION_CLASSES` |
| `planned_action` | `set_name_and_clear_units`, `clear_units`, or `none` |
| `reason` | the human-readable justification for the class |

This is a consumed contract —
`ai-readiness-kg/cc_tasks/2026-09-04_result_migration_completion.md` reads it —
so the field names are pinned by
`test_migrate_names_report_writes_one_row_per_result_with_the_agreed_fields`
(exact `set(row) == set(MIGRATION_REPORT_FIELDS)`), and
`test_migrate_names_report_row_classes_match_the_summary_table` asserts the file
and the printed table are two views of one plan and cannot differ.

Adding a field later is safe; renaming or removing one is a breaking change, and
the constant carries that note.

---

## 9. `--dry-run` against `seldon-ai-readiness-kg`

**DRY RUN ONLY. No live run was made against that project — it has its own task.**
The report was written to the session scratchpad, not into the ai-readiness-kg
repo.

```
Result name migration — database 'seldon-ai-readiness-kg' (DRY RUN)
  Results in graph: 3592
    migrated                 953
    name_set_units_pending   2576
    already_named            0
    units_is_real_unit       23
    ambiguous                40
    no_units                 0
    refused                  0

Dry run — no events written.
The live run would write 3529 event(s): 953 promotion(s) and 2576 units clear(s).
Exit code: 0
```

Reconciliation against the live state the integrator confirmed:

| Integrator's figure | This run |
|---------------------|----------|
| 3592 Results total | 3592 ✓ |
| 2576 with `name` set and `units` still equal to `name` | `name_set_units_pending` = 2576 ✓ |
| 1016 with no `name`, still carrying `units` | 953 + 23 + 40 = **1016** ✓ |
| 953 prospective names contain uppercase | `migrated` = 953 ✓ — all now valid under Amendment 01 |
| 0 rows with `name` set and `units` null or differing | `already_named` = 0 ✓ |

**`refused: 0`** is the proof the amendment resolves the defect: before it, those
953 uppercase names were exactly the rows the live run refused after writing
2576. The run now exits 0 and would write all 3529 events in one validated pass.

Residual, for the downstream task: **40 `ambiguous`** rows across 11 units
strings (`precision`, `proportion`, `admitted_yield_ratio`,
`admitted_items_per_chunk`, `atomic_facts`, `fabrication_share`,
`fabrication_share_upper95`, `instrument_containment_recall`,
`item_faithful_rate`, `quarantine_rate`, `usd_per_admitted_item`) — each shared
by 2, 3, 5 or 9 unnamed Results, so promoting any of them would break name
uniqueness. These need a human to decide who gets the name; they are not a
grammar problem and the amendment does not touch them. **23 `units_is_real_unit`**
rows carry `accuracy`, `count` or `kappa` and are correctly left alone.

---

## 10. Premises in the task file checked against live state

Every premise in §0 and §1 held. Specifically:

- 3592 Results, 2576 in the `name_set_units_pending` state, 953 uppercase names —
  all confirmed exactly by the dry run above.
- The `^[a-z0-9][a-z0-9_.-]*$` pattern was duplicated in five places, as stated
  (constant, docstring, `--name` help, `research.yaml`, conventions doc).
- §1.2's description of the ai-readiness-kg compensating-event state as "rows
  that carry `name` AND still carry a `units` value equal to `name`" matched the
  graph precisely: 2576 rows, and **zero** rows with `name` set and `units` null
  or differing.

**One clarification rather than a contradiction.** §1.2 calls `refused` "a fourth
class". Implemented, it is the seventh: `name_set_units_pending` is required by
the same paragraph, and `already_named` is required to make the summary table
reconcile against the graph's total row count and to make resumability visible
in the report. §1.3 asks for "a summary table of all classes", which the seven
satisfy. Nothing in §1 was dropped.

**One judgement call recorded, not escalated.** The exit code of a `--partial`
run that refused rows is non-zero (see §6). The task file specifies the exit code
only for the no-`--partial` case. Grounding: a partial run that left rows behind
did not complete, and a zero exit would let a caller treat it as finished.

---

## 11. Cross-lane needs

**None.** Lane 1 required no change to any file owned by another lane.

For the integrator's awareness only, not a request: the 10 `tests/test_ontology.py`
failures and the 1 `tests/test_ontology_ingest_lifecycle.py` failure observed
during Lane 1's runs come from Lane 2's in-flight edits to
`seldon/commands/ontology.py`. They passed at the 1001 baseline and are unrelated
to this lane's changes.
