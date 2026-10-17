# DESK-002 ADDENDUM 01: resume from the branch; merge before each Part check

**Date:** 2026-10-17. **Authored by:** a Desktop session in squiddy (SQ8), after reading the DESK-002 RESULT and Issue `02d52bc4`.

## Why

The first run halted on a false line stop. The Part A milestone check ran in the main checkout, while the work and its test file were on branch `fix/desk002-ruling-commits-with-record` (worktree `../seldon-desk002`).

The station is behaving as built: it checks main. The session was right to keep the work off main until it was tested. The two are only compatible if each Part merges before its `part-complete`. That is how this run proceeds.

The station's design is Issue `02d52bc4` and is not this task's to fix.

## What changes

1. **Do not redo Parts A and B.** Resume from `01835ba` and `68f4c92` on the branch.
2. **Before calling `part-complete` for a Part:**
   - run the full suite on the branch;
   - merge to main and push;
   - then call `part-complete`, so the station's check runs against code that is on main.
3. **Parts A and B go first.** Run the full suite, which the first run did not, then merge and push. Then call `part-complete` for A and B in this new launch. Their checks must pass on main.
4. **Then Part C, then Part D,** each on the same pattern: build on a branch, run the full suite, merge, then `part-complete`.
5. **If the full suite fails on the branch, do not merge.** Record the failures and stop.

Everything else in the base task stands, including the Report.
