# SEL-002: AD-033 built. One decision register per repository, one write path, baseline DB-1 seeded from the probe, the 45 conflicts resolved as records, the probe re-run clean

**Repos:** seldon (the command, the projection, AD-033), squiddy and arnold (their `docs/decisions/register/`), by
path from one session. Branch `feat/SEL-002` from main in each repo touched. L4: commit, merge, push in each.
**Starts after:** squiddy SQ-008 and SQ-009 are merged to main. Check first (`git --no-optional-locks log main
--oneline | grep -E 'SQ-00[89]'` in squiddy, and AD-032 present in seldon/docs/design). If either is missing, stop and
report; do not start.
**Read first, in full:** `/Users/brock/GitHub/workbench/2026-10-04_decision_layer/AD-033_decision_register_records_lifecycle_consumption.md`
(the design; it governs this task); AD-030 and its two findings files; AD-031; `docs/SEL-001_delivery_report.md`;
AD-032 (filed by SQ-008); the probe as filed by SQ-008 under `squiddy/docs/findings/2026-10-03_operator_audit/probe/`
(`inventory.py`, `units.jsonl`, `conflicts.md`, `conflicts.jsonl`, `NOTEBOOK.md`); squiddy DN-041 and its
`decision_log` code (the hash chain to reuse); `seldon/core/governed.py`; squiddy DN-042 and `squiddy/spend.py` (the
governor Part E runs under). Glob and read sibling `*SEL-002*ADDENDUM*.md`. This file and its addenda are immutable
once read.
**Model spend:** Part E only: one statement call and one validator call per active record, about 450 records.
Estimate from a 10-record pilot under the DN-042 governor before the run; report estimate, actual and ratio. Notional
before the pilot: about 1,000 calls, about 3M tokens. Everything else is zero model calls.
**Network:** the model CLI for Part E; git push.

0. **File the design.** Copy AD-033 from the workbench to `seldon/docs/design/AD-033_decision_register.md`
   byte for byte; record both sha256 values (they must match). Commit it alone, first, before any code: section 6 is
   SEL-003's pre-registration and must be on main before anything is measured. If seldon has a governed graph, run its
   sync and report the count of decision units it parsed.

1. **Part A, the record and the write path (AD-033-R2, R3, R4).**
   - A schema for the record (LinkML if the governed template already uses it, else JSON Schema), required fields as
     R3. Status vocabulary as R4.
   - `seldon decision propose | accept | reject | supersede | amend | deprecate | show | list | check`, CLI and MCP
     (add the MCP tools beside `seldon_task_create`). Writes one YAML file per record event to
     `<repo>/docs/decisions/register/`, named `<seq>_<id-slug>_<event>.yaml`, with `prev_hash` and `record_hash`
     (DN-041's chain form). Refuses every case R2 lists.
   - Projection: `Decision` nodes in the project graph, status derived from the files (R4), relations as edges;
     `docs/decisions/REGISTER.md` rendered from the projection, never hand-edited. Imports via
     `decisions.import:` in `seldon.yaml`; set arnold to import squiddy.
   - `seldon verify` fails: a broken chain or hash mismatch; a labeled decision in a design note committed after
     DB-1 with no record; a record whose `rationale` resolves to no file.
   - `seldon cc register` binds accepted `Decision` records when the repo has a register (R7), across imports, and
     prints "advisory until SEL-003" in its binding block. Positional `Ruling` nodes lose `force: binding` there.
   - Tests, each a planted control shown failing before the code that catches it: hand-edited record; forked
     supersession (refusal names the live head); supersedes a missing id; labeled decision without record; Arnold
     registration resolving `squiddy:R-112`.

2. **Part B, seed DB-1 (AD-033-R5), zero model calls.**
   - Record the three repos' main HEADs as the baseline commit set in `docs/decisions/BASELINE_DB-1.md`
     (seldon).
   - Seed with the probe's `inventory.py` (reuse it; do not write a second parser) over: the 485 units; DN-037
     (ids `squiddy:DN-037-R1` onward, one per decision bullet); AD-032 FC-01 to FC-33 (FC-01 to FC-07 accepted and
     `operator_stated: true`, FC-08 to FC-33 proposed, waiting on "P1 to P6 per AD-032 section 8"); Arnold
     `docs/adr/` (status from each ADR's status line); the unlabeled prose decisions SEL-001 F6 named (Arnold
     intensity-constructs per-set RPE and the five ontology documents), ids `arnold:<doc-slug>-B<n>`, verbatim span
     required to match the file exactly.
   - `source` carries the full body, never the heading alone; for the truncated units the probe lists (DI-170 to
     DI-178 at least), re-read the body from the file.
   - Status at seed per R5. `statement` at seed is the verbatim body (Part E replaces it). DI rows that cite an R
     become `kind: mirror` pointing at it.
   - `operator_stated` is true only with a receipt: the source text names the operator or Brock as decider, or a
     handoff or session notebook quotes him. List the receipts.
   - Every record goes through the command (Part A), so DB-1 is written by the one write path.

3. **Part C, the 45 findings and the 12 drifted mirrors, as records (R5).** For each finding in `conflicts.jsonl`,
   write the transition or superseding record its disposition names, citing the finding id and its quotes. Where the
   disposition offers a choice, apply AD-033 section 5. F11 and F39: already settled by DN-042 (read it); record
   that. No source document is edited. Then the override list: every applied disposition that touches a record with
   `operator_stated: true`, one row each (finding, records, what changed, the receipt). F04 is first. Do not ask the
   operator anything.

4. **Part D, consumers (R6), zero model calls.** For each accepted record, find the conformance items, tests and code
   that cite its id (squiddy `conformance.yaml`, `tests/`, `squiddy/`; seldon and arnold the same) and fill
   `consumer`. The rest get `review_only` with one reason from R6's closed list, chosen by rule: a pre-registration
   section is `pre_registration`; a record in a design note's rationale-only section is `rationale`; FC-labeled and
   dispatch-constraining records are `dispatch`; otherwise `none`. Report coverage (records with a consumer over
   accepted records) per repo, and inherited rows separately.

5. **Part E, statements (R8).** Pilot 10 records, estimate, then the run, under the governor. Statement call and
   validator call are separate calls; the validator sees the verbatim source and the statement only. A failed
   check keeps the verbatim statement and sets `statement_check: failed`. Statements land as `amend` records on the
   statement field (records are never edited). Report pass rate, failures by repo, estimate, actual and ratio.

6. **Part F, exit checks (AD-033 section 7).** Run all seven. The probe re-run on the register must report zero open
   contradictions and zero silent supersessions among active records; if not, list them and stop before merge.
   Also report: records by status and repo; registration of SQ-009's task text against the register (the R-29
   case); the count of `none` consumers.

7. Suite green in each repo, `seldon verify` in each, commit, merge, push, `seldon cc complete`. Delivery report at
   `seldon/docs/SEL-002_delivery_report.md`: lead with the override list, then the exit checks, then counts. End by
   printing this session's own token usage.
