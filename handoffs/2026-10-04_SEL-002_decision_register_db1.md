# Handoff: SEL-002, the decision register and baseline DB-1 (CC, 2026-10-04)

**Read first:** `docs/SEL-002_delivery_report.md` (override list, exit checks, counts, findings G1 to G11).

## What exists now

- Every repository that registers tasks (squiddy, seldon, arnold) has `docs/decisions/register/`: one YAML file per
  record event, hash-chained, written only by `seldon decision` (CLI) or `seldon_decision_*` (MCP). REGISTER.md is
  rendered; never edit either by hand. `seldon verify` fails a hand edit.
- `seldon cc register` in these repositories binds accepted `Decision` records (own plus imports; Arnold imports
  Squiddy), labelled "advisory until SEL-003". Positional Rulings are `force: searchable` and bind nothing.
- `seldon decision check --probe` re-runs the conflicts probe on the register (AD-033-R9). Clean at merge: 45/45
  findings resolved, zero open contradictions or silent supersessions among 657 active records.
- A design note written from now on: register its labeled decisions in the same session (`seldon_decision_accept`
  with the record YAML), or `seldon verify` fails on the label.

## Open, in order of consequence

1. **SEL-003 (AD-033 section 6) is unblocked.** Its pre-registration is frozen in `docs/design/AD-033_decision_register.md`
   (committed alone at `419c30e`). Its units are the active accepted records; 128 of them still carry the verbatim
   source as their statement (`statement_check: failed`).
2. **Two spend-governor stops, left stopped.** Run 2 of the statement pass paused at touchpoint 1 (writer token cap,
   validator +20% band). 9 records have no complete check (2 Arnold exercise-identity rulings unwritten; 7 without a
   verdict, among them plan-builder addendum-02 R2). To finish: write `spend_approval.yaml` (operator, date, job, new
   ceiling, words) in `seldon/evidence/sel002/statements/`, run `statements.py run` from Squiddy's venv, then
   `statements_apply.py`. Roughly 40k weighted tokens.
3. **Seldon's governed graph will not admit AD-033** under the pinned kit (G2: read stage writes `cataloged`, reconcile
   refuses). Squiddy's governed graph is nine documents behind and its pin is stale (G3). Both need a governed-graph
   task that re-pins and re-sweeps; not urgent now that the register is the binding source.
4. **DN-042 estimator issue** (G5): cold-start calls priced as warm. Worth a Squiddy Issue.
5. **Arnold `docs/requirements/FR-*`** headings were positional Rulings and now bind nothing (G8); if those
   requirements matter at registration, register them.

## Surprises worth knowing

- SQ-008 left Seldon's governed export stale; every admission since was refused (G1, repaired here).
- Arnold ignored `seldon.yaml`; it is tracked now (G4).
- The CLI's default effort spends thousands of output tokens on thinking for a JSON reply; `--effort low` halves the
  cost of a strict check (G6).
- The first DB-1 seed under-read operator receipts and was redone on the unmerged branch before anything consumed it (G7).
