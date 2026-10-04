# Baseline DB-1: the decision register's first configuration baseline

**Date:** 2026-10-04. **Established by:** SEL-002 (Seldon task 0636b04a), under AD-033-R5.
**Prior art:** EIA-649C configuration identification and change control: a baseline is an identified,
approved state from which changes are controlled. The register is a configuration baseline of decisions.

## The baseline commit set

The three repositories' `main` HEADs at SEL-002's start. Every DB-1 seed record's `source.sha256` is the
sha256 of its source file at this commit (Seldon's AD-033, filed by SEL-002 step 0 at `419c30e`, is the one
document added after it; its labeled decisions are registered, as AD-033-R2 requires of a note added after the
baseline).

| Repository | Commit | Subject |
|---|---|---|
| seldon | `a6422a0e7cfa3184ab870557c46d99d8962f9669` | Merge chore/SQ-008: handoffs tracked (FC-02), AD-032 factory control design filed and ingested |
| squiddy | `c3de5552b54fa26951c163d3f0ea158c8b92ac19` | close: SQ-009 completed in Seldon (squiddy 7076eae) |
| arnold | `f31a4c3531e1cc167bda922a36a8887e0858d10d` | Merge feat/KG-008-finish: the 120-question demand test |

Each repository's `seldon.yaml` carries its own commit under `decisions.baseline`, which is what `seldon verify`
reads: a labeled decision in a design note absent from that commit's tree must have a record.

## What DB-1 holds

Seeded by `scripts/sel002/seed_db1.py` through `seldon.core.decisions` (the one write path; the CLI and the MCP
tools call the same functions). Per-record provenance: `evidence/sel002/seed_manifest.json`.

- The decision probe's 485 units (`squiddy/docs/findings/2026-10-03_operator_audit/probe/units.jsonl`), parsed
  again at the baseline by the probe's own `inventory.py` (byte-identical copy,
  `evidence/sel002/inventory/inventory.py`, sha256 `91a71f13...17e69`) with its two truncation caps lifted, so
  every `source` carries the full body (`scripts/sel002/inventory_uncapped.py`). The re-run also found 20 units
  added since the probe: Squiddy R-174 to R-181, Seldon AD-032 (resolved to its FC records) and AD-033-R1 to R11.
- Squiddy DN-037: `squiddy:DN-037-R1` to `R7`, one per decision bullet (R1 to R5 its Decision section, R6 and
  R7 its Deferred section).
- Seldon AD-032: `seldon:AD-032-FC-01` to `FC-33`. FC-01 to FC-07 accepted and operator-stated; FC-08 to FC-33
  proposed, waiting on "P1 to P6 per AD-032 section 8".
- Arnold `docs/adr/`: `arnold:ADR-001` to `ADR-017` and `arnold:ADR-013-A01`, status from each status line.
- The unlabeled prose decisions SEL-001 F6 named: every decision in Arnold's five ontology documents
  (canonical-exercise-creation, progression-policy, training-domain-vocabulary, week-template,
  workout-structure) and intensity-constructs' per-set RPE decisions, ids `arnold:<doc-slug>-B<n>` (or the
  document's own label where it writes one), each span checked against the file
  (`evidence/sel002/arnold_ontology_decisions.json`). The 2026-06-27 reversal record's labeled rulings join them.
- Beyond AD-033-R5's list, Arnold DN-001 and DN-002's labeled decisions: AD-033-R7 stops positional rulings
  binding, and DN-001-R2 (per-set RPE exists nowhere) would otherwise have stopped binding Arnold's tasks.

Status at seed (AD-033-R5): the source's stated status where it has one; a Draft or Proposed note that a
dispatched task executed under is accepted with that task as the receipt; otherwise accepted. Then ADDENDUM 01
item 3 (`seldon:AD-033-R10` supersedes `seldon:AD-030-R14`) and ADDENDUM 02 item 1 (`seldon:AD-033-R11`
supersedes `squiddy:R-04` and amends R-08, DI-070, DI-163, DI-242 and AD-030-R5), each through the command.

The 45 probe findings and the 12 drifted mirrors are applied after the seed as transition, superseding and
amending records (SEL-002 Part C), each citing its finding id and quotes; the delivery report
(`docs/SEL-002_delivery_report.md`) carries the override list and the counts.
