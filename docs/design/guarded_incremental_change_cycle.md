# Methodology — The Guarded Incremental-Change Cycle

**Date:** 2026-06-22
**Status:** Active methodology (validated 2026-06-22 on fss-policy-kg)
**Scope:** Cross-project. Applies to any system where state is reconstructable from a log (event-
sourced graphs, append-only stores) or where a change must be provably exact and isolated.
**Owner:** Seldon (canonical). Project-specific mechanics live in each project; this is the pattern.

---

## What this is

A discipline for making a change to a live, verified, reconstructable system and PROVING the change
was exactly what you intended and nothing else moved. It exists because the dangerous failure mode in
these systems is not a loud crash — it is SILENT divergence: a write that lands in the live state but
not the log (vanishes on rebuild), or a change that touches more than intended (orphan nodes, drifted
counts) and accretes invisibly over time.

Validated first on fss-policy-kg (2026-06-22): an incremental 4-document ingest into a live KG. The
cycle caught a real non-additive artifact (an orphan authority node) on the same run and corrected it
before it landed. Evidence: `icsp_notebook/kg/incremental_ingest_tevv_report.md` and
`icsp_notebook/docs/2026-06-22_lab_notes_incremental_growth_tevv_passed.md`.

## When to use it

Any time you are about to change a reconstructable/event-sourced system and need the change to be
provably exact:
- ingesting new material into a knowledge graph (Wintermute, fss-policy-kg)
- backfilling or correcting fields in an event-sourced store
- any mutation where "did this touch only what I meant" is a real question

Not needed for: throwaway scratch work, read-only operations, or systems with no reconstruction
guarantee to protect.

## The cycle

1. **Drift-gate BEFORE (hard gate).** Verify the live state is a faithful projection of the log
   (replay into a scratch instance, diff against live). If NOT clean, STOP — never change a system
   that has already diverged; you would build the change on a corrupt base and lose the ability to
   attribute later drift.

2. **Snapshot.** Back up the log (timestamped, before any write). Append-only systems make this
   cheap and it is the thing that makes the correction step in (5) safe.

3. **Additive change.** Apply the change through the log (never direct state mutation that bypasses
   the log — that is the exact silent-divergence hazard). Never invoke a destructive
   truncate/regenerate path that would discard expensive state. Touch only new material; leave
   existing state untouched.

4. **Canary diff.** Compute the invariants before and after — counts by type, key histograms, and a
   per-entity property fingerprint. The delta must be EXACTLY "the intended new material and nothing
   else." Any unexplained delta is the signal the canary exists to catch.

5. **Catch and correct (if the canary shows an unintended delta).** This is not a failure — it is the
   cycle working. Identify the spurious change, drop/fix exactly it (snapshot already taken in (2);
   preserve all expensive/stochastic state), reload, and re-run the canary + drift check. Log the
   root cause so the defect does not recur.

6. **Drift-gate AFTER (hard gate).** Re-verify live == log replay. Must be clean. This proves the
   change went through the log (reconstructable) and nothing diverged.

7. **TEVV scorecard.** Produce a PASS/FAIL record of each safeguard with the before/after canary and
   the drift evidence. This is the deliverable that makes the change auditable and reusable — not the
   changed data alone.

## The principles under it

- **A caught failure is a SUCCESS; a forced change is the failure.** The point is not "the change
  completed" — it is "the change completed AND every safeguard fired." Stopping on a tripped gate is
  the system working. Steamrolling a gate to finish is the only real failure.
- **Detection by system, not by luck.** The whole reason this cycle exists is to convert "we caught
  it because someone happened to read the code" into "the gate caught it automatically." If a class
  of error was ever caught by luck, that class needs a gate.
- **Log is truth; live state is a projection.** Every change goes through the log so replay
  reconstructs it. A write that lands only in live state is invisible to replay and is the canonical
  silent-divergence bug.
- **Currency/provenance set at admission, not bolted on later.** If incoming material supersedes or is
  superseded by existing state, set the staleness/currency flags AT the change, not in a later
  cleanup. Stale-status-as-afterthought is its own drift.

## Project-specific mechanics (NOT here — by design)

The drift-check implementation, the log format, the extraction/projection pipeline, and the scratch-
replay mechanism are project-specific and live in each project (e.g. fss-policy-kg:
`kg/drift_check.py`, `kg/loader.py`, `kg/events.jsonl`). This doc is the PATTERN; do not copy project
code into it — read the project's own tooling for the mechanics, apply this cycle as the discipline.
