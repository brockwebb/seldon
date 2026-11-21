# AD-033 ADDENDUM 02: `seldon verify` reads a branch's pending register records and reports them

**Date:** 2026-11-21. **Status:** Accepted. Implemented by SEL-042 Part D
(`cc_tasks/2026-11-21_SEL-042_a_stopped_session_is_never_merged_or_completed_the_merge_round_cannot_refuse_itself_and_verify_reads_pending_records.md`),
from squiddy's filing `5b76278b` (2026-11-06) and hazbrief's report in `6a9c00fa` (2026-11-16). **Extends:**
AD-033-R12 (a branch's records are written pending and numbered at merge) to the verifier. One new ruling, AD-033-R14.
**Code:** `seldon/commands/verify.py` (`check_decisions`, `_pending_line`).
**Tests:** `tests/test_sel042_verify_pending_and_name_limit.py`.

## 1. Evidence

squiddy SQ-124 (worktree `cosmic-launching-cray`, 2026-11-06) committed three pending records (two `accept`, one
`amend` of the numbered `squiddy:R-237`) as AD-033-R12 directs; `seldon verify` then raised `KeyError: 'record_hash'`
at `seldon/core/decisions.py:772` (`Record.last_hash`) from `check_decisions`, and printed no check at all. hazbrief
HB-193 met it with HB-189's 21 pending records (2026-11-16), seldon's own SEL-040 session skipped verify for it, and
each of them worked around it by moving the pending directory aside. Reproduced here with SQ-124's shape; on the code
before this addendum the test fails with the same `KeyError` at the same line
(`docs/evidence/sel042/reproduction_old_code.txt`).

The cause: the projection check folded the register WITH its pending records and compared each record's
`last_hash` with the graph. A record whose last event is pending has no `record_hash` until the merge numbers it, and
the graph is projected from numbered records only (AD-033-R12, AD-034-R24), so the comparison could never hold.

## 2. Prior art

### Internal

- internal receipt: query "pending records" | repo seldon@6a74a6a82c5c73c7f40fc91952bfc9f0d46b477f | hits docs/design/evolution_burst_2026-04/cc1_pattern_extraction.md:316, docs/design/AD-033_ADDENDUM_01_register_numbers_at_merge.md:20, docs/design/AD-033_ADDENDUM_01_register_numbers_at_merge.md:30, docs/decisions/register/00301_seldon-ad-033-r12_accept.yaml:1
- internal receipt: query "pending records" | repo squiddy@0a00d72d79c1799fc095f5b2cd25904318aecad6 | hits docs/H-006_delivery_report.md:149, docs/design/2026-09-25_daemon_livelock_at_size_deferral.md:27, docs/Q-002_delivery_report.md:168, docs/EXTRACTION_DESIGN_SPEC.md:3

### External

- **A staged write is not a committed write** (a write-ahead log's records before their commit point; a database
  sequence drawn inside the committing transaction): a reader compares the committed state with the committed state
  and reports what is staged separately, rather than treating the stage as committed. AD-033 ADDENDUM 01 cites the
  same model (Kafka's broker-assigned offset) for numbering at merge; this addendum applies it to the reader. Named,
  not fetched.

## 3. Rulings

- **AD-033-R14. `seldon verify` runs with a branch's pending register records present: it compares the graph with the numbered chain alone, reports the pending records as `N pending record(s), numbered at merge: <id> <event>, ...`, and runs every other check.**
  The pending records' own checks (name, canonical bytes, provisional id, shape, no duplicate create) still run in
  `Register.verify`, as AD-033-R12 made them. Verify is meant to run on a branch; moving `pending/` aside to make it
  run is never needed and hides the records the merge will number.

## 4. What this does not change

The numbering at merge, the projection after it (AD-034-R24) and the pending records' format are unchanged.
`seldon decision project` is not changed here; it is the merge's step, run on the primary after numbering.
