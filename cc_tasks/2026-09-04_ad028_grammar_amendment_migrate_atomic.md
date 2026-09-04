# CC Task — AD-028 amendment: admit uppercase in Result names; make `migrate-names` predictive and atomic

**Date:** 2026-09-04
**Project:** seldon
**Authored by:** Desktop session
**Closes Seldon task:** `a79bf520`
**Spend:** zero model spend.
**SEQUENCING:** Runs BEFORE `ai-readiness-kg/cc_tasks/2026-09-04_result_migration_completion.md`.

**Immutable once written. Changes require a new task file or an `_ADDENDUM-NN.md` sibling.**

---

## 0. Decision (Desktop, grounded, not for ratification)

AD-028's slug grammar `^[a-z0-9][a-z0-9_.-]*$` is amended to `^[A-Za-z0-9][A-Za-z0-9_.-]*$`. Rationale: (1) AD-028 already declares names case-sensitive, so a lowercase-only grammar buys no collision safety it does not already have; (2) the downstream convention it collides with (ai-readiness-kg DD-035/DD-037: `_L0`…`_L4`, `MOE`, `CI`, `SE`, `CV`, `DP_NOISE`, `RELIABILITY_FLAG`, `VINTAGE` segments) is established, carries meaning, and is cited by 66 live tokens; (3) renaming 953 Results plus rewriting tokens to satisfy a cosmetic constraint is cost with no measured benefit. Uniqueness remains exact-match, case-sensitive. Append the amendment to `docs/design/AD-028_result_names_and_task_lifecycle.md` and a dated line to `docs/design/seldon_architectural_decisions.md`. Do not rewrite the original text.

## 1. Changes

### 1.1 Grammar
- Single definition point for the name regex (a constant in the result module); `register --name`, `migrate-names`, and any other name-accepting path import it. Test: the constant is the only place the pattern string appears (grep test).
- Update the error message to describe the new grammar.

### 1.2 `migrate-names --dry-run` must predict the live run
- Dry-run applies the identical validation the live path applies (grammar, uniqueness against both existing names and the names it would assign in this run) and reports a fourth class `refused` with the reason per row. Test: a fixture graph where dry-run reports `refused: N`, live run writes exactly `migrated` count and zero of the refused.
- Live run is validate-all-then-write: build the full plan, validate every row, write events only if the plan has zero refusals **or** `--partial` is passed. Without `--partial`, any refusal → exit non-zero, nothing written, refusals printed. Test both paths.
- Live run is resumable: rows that already carry `name` are skipped (already the behaviour; pin it with a test). Rows that carry `name` AND still carry a `units` value equal to `name` (the ai-readiness-kg compensating-event state: 2576 rows) are reported as `name_set_units_pending` and, on live run, get the `units` clear event only. Test with such a fixture.

### 1.3 Report shape
- Both dry-run and live print a summary table of all classes plus a `--report PATH` option writing the per-row plan as JSONL (artifact_id, current name, current units, class, planned action, reason). The downstream task consumes this.

## 2. Integration

- Full suite green, count ≥ 934 + new tests.
- `seldon verify` clean on seldon.
- `seldon task close a79bf520` with note. `seldon cc complete` this file. Commit and push, including this task file and the RESULT (both must be tracked at push).

## 3. RESULT must report

Test counts; the regex constant location; the four-class dry-run output against a fixture; confirmation that dry-run and live agree on the fixture; the `--partial` and no-partial behaviours; any premise here contradicted by live state.
