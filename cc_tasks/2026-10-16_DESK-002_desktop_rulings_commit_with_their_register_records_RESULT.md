# RESULT: DESK-002 HALTED at Part B by a line stop; Parts A and B are built on an unmerged branch, C and D not started

**Halt.** At Part B, `seldon dispatch part-complete --part B` exited 3. The cause was the Part A milestone check, `session_stop` `check_failed`. The station ran `pytest tests/test_desk002_ruling_commits_with_record.py -q` in the main checkout and got exit 4 (file not found). That file exists only on branch `fix/desk002-ruling-commits-with-record` (worktree `../seldon-desk002`), because seldon code changes go in a worktree: main is read live by every launcher. On the branch, that command passes (5 tests). The stop is false, but it binds this session, so `andon_halted` was recorded and work stopped. Issue `02d52bc4` records the station defect.

**Tokens** (from part-complete): Part A not read (None); A+B 192,863 at Part B, against 0.8M (A+B planned 0.44 = 352k). The dispatcher computed no CPI for A (no token reading).

**What stands on the branch (not merged, not pushed):**
- `01835ba` Part A. Root cause: `governing_commit.plan_records` skipped any label whose record already existed on disk. So a record written by Desktop (`seldon_decision_accept`) and not yet committed was never staged, and the hook refused the commit. Registration now stages those records, the uncommitted chain links before them, and the re-rendered REGISTER.md (`uncommitted_record_paths`). `commit_governed` accepts a register path only in the same call as a note that labels its id.
- `68f4c92` Part B. Measured in `docs/evidence/desk002/registration_event_lines.md`. **The defect exists in both orders**, so order is not the cause. Order only decides whether the dispatcher's `source_commit`-keyed sweep rescues the lines later. Registration now commits its own lines in a `register: record` commit right after the task's commit. They cannot go in the same commit, because `source_commit` names that commit. It does this only when the store was clean at the start and every appended line is its own actor's or `governed_sync`'s.

**Tests and their result on HEAD** (`docs/evidence/desk002/partA_tests_on_head.txt`):
- registration with a Desktop-written record: FAIL on HEAD (`governing_note_uncommitted ... has no record in the staged register`), the squiddy SQ-017 case.
- commit_governed, note plus record: FAIL on HEAD (`outside_roots`).
- record alone refuses: HEAD already refused; the test pins the new reason, so it FAILs on HEAD only on wording.
- record whose note does not label it: FAIL on HEAD (wrong reason).
- gate refuses a label with no record anywhere: PASSES on HEAD. It is a regression guard and cannot fail on HEAD.
- Part B, both orders: FAIL on HEAD (`[('artifact_created','desktop'),('link_created','governed_sync')]`).
- On the branch: those 7 tests plus the registration/commit suites pass (23 passed in five files; DESK-001 and SEL-006 suites 26 passed). **The full suite was not run.**

**Not done:**
- Part C (source hash on accept/propose/amend; squiddy R-206 correction).
- Part D (squiddy live control). squiddy is untouched; its DN-048/R-207/SQ-017 files are still uncommitted, as found.
- No merge, no push, no `cc complete`. Issues 5c689098, 70bf1a21 and 5bfc2788 stay open.

**To resume:** clear the stop for 4f7e5409. Then merge the branch, so the Part A/B checks resolve on main. Then do Part C (I planned to compute `source.sha256` in `dr.create` for accept/propose, check `source.text` against `source.lines`, and add a `source`-only path to amend that changes `sha256` alone) and Part D.

**Premises found wrong:** none of the three task premises. One unstated premise was wrong: that a Part check sees the session's work before merge.
