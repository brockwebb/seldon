# RESULT: DESK-002R complete. All four Parts merged before their checks, every milestone passed, squiddy's live control registered SQ-017 with a clean tree

**Tokens** (part-complete, cumulative from launch): A 142,675, B 142,932, C 153,216, D 153,443, against 0.6M (26%). CPI from the station: A 0.63, B 1.05, C 2.74, D 3.91. The A huddle (`072db8c4`) is closed. Its cause is attribution: A's reading included orientation and Part C's design and HEAD tests, all done while A's suite ran.

**Merges, with full suites on the branch:**
- **A+B, run 1:** 2546 passed, 1 failed. `test_the_record_of_a_self_committing_registration_is_committed_by_the_next_pass` asserted that the store is dirty after registration, which is the defect Part B fixes. The test was updated to Part B's contract in `e6e6ca7`; the run is saved as `docs/evidence/desk002/suite_ab_run1.txt`.
- **A+B, run 2:** 2547 passed, 0 skipped, 0 xfailed, 0 deselected, 0 failed. Merged as `0ed91e5` and pushed.
- **C:** 2561 passed, 0 skipped, 0 xfailed, 0 deselected, 0 failed. Merged as `4f35ecc` and pushed. Milestone checks on main: A, B, C and D all pass.

**Part C** (`b81087b`):
- `decisions.create` computes `source.sha256` from the whole file through `checked_source`. A different value is refused, naming both. `source.text` must equal the file's text at `source.lines`, stripped, as registration takes it. This covers accept, propose, and supersede of a new record: one create path.
- `amend` accepts `changes.source` only as a sha256 correction to the file's current digest, while the text still matches. Any other `source.*` change stays fixed at creation. The schema's `Changes` now names `source`.
- Before the change, I measured the convention against the existing registers. In seldon 140 of 140 sources and in arnold 153 of 153 carry the file's current digest. In squiddy 431 of 452 do; the other 21 have files edited since, and their text matches in 451 of 452. Fixture changes: `tests/test_decision_register.py` and `tests/test_hooks.py` planted `"0"*64` and spans that were not the file's. They now carry the note's real span.
- **Tests on HEAD** (`docs/evidence/desk002/partC_tests_on_head.txt`), 10 FAIL and 4 PASS:
  - wrong digest refuses: FAIL (did not raise);
  - no digest computes it: FAIL for both accept and propose (`Source requires sha256`);
  - amend to the true digest: FAIL (`fixed at creation`);
  - amend to another value: FAIL for each of the three values (the refusal does not name sha256);
  - text mismatch and missing file: FAIL;
  - amend after the text drifted: FAIL;
  - the regression guards pass on HEAD as expected: accept with the true digest, and amend of path, lines or text.
- **R-206 correction:** squiddy seq 986 amends the digest to `ee5436…5a025`, with a reason citing 5bfc2788. Committed through the hooks as squiddy `24fd97b` and pushed. `seldon decision check` reports the register clean. Per step 5, it ran after Part D's registration, so 986 did not chain onto an uncommitted 985.

**Part D** (`docs/evidence/desk002/squiddy_live_control.md`): `seldon cc register … --allow-untracked` exited 0.
- squiddy `f91b89c` holds the task, DN-048, record 985 and REGISTER.md together, plus the ledger lines. The gate passed.
- squiddy `5649775` holds the 11 store lines written by registration. `git status` is clean and the branch is pushed. SQ-017 is task `174d0337`; it was not run.

**Premises found wrong:** both premise checks held. The task's file list was stale: squiddy's `state/prior_art_queries.jsonl` and `governed/ledger/events.jsonl` lines had already been committed by squiddy's dispatcher (`6eee7a7`).

**Left open:** Issue `02d52bc4` (the station checks main), which is not this task's. Supersede on the create path also checks source; that is broader than the task named, and a single code path made it the natural choice.
