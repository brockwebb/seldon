# DESK-002R: DESK-002 resumed. Merge its Parts A and B from the branch, then do Part C (the register's source hash) and Part D (the squiddy live control); each Part merges before its check

**Repo:** seldon (primary). Cross-repo by absolute path: `/Users/brock/GitHub/squiddy` (Part D). L4: commit, merge, push in every repo touched.
**Date:** 2026-10-17. **Authored by:** a Desktop session in squiddy (SQ8).
**Supersedes:** `cc_tasks/2026-10-16_DESK-002_desktop_rulings_commit_with_their_register_records.md` (task 4f7e5409).
- That task halted at Part B on a false line stop: Issue `02d52bc4`. The Part A milestone check ran in the main checkout, while the work and its test file were on branch `fix/desk002-ruling-commits-with-record` (worktree `../seldon-desk002`).
- The dispatcher moved the task to `blocked`, which has no transition back to a launchable state (`research.yaml:1141`). So the work is re-issued here.
- Read the DESK-002 base task and its RESULT first. The measured defects, the governing rulings and Part B's measurement are all there, and they stand.
- `..._ADDENDUM_01_resume_merge_before_part_checks.md` was written for the old stem. Its content is folded in below.

**Resolves:** Issues `5c689098`, `70bf1a21`, `5bfc2788`.
**Governing:** AD-033-R2, AD-033-R3, AD-036-R4 and R13, DESK-001. No new ruling.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.6M tokens. Basis: DESK-002 used 0.19M through Part B against 0.8M; what remains is Part C's code and tests, Part D, and two full suites.
**Parts:** A 0.15, B 0.10, C 0.45, D 0.30.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: DESK-002's Parts A and B exist on their branch | check: `git rev-parse --verify fix/desk002-ruling-commits-with-record`
- premise: the live control's design note is on disk in squiddy | check: `test -f /Users/brock/GitHub/squiddy/docs/design/2026-10-16_DN-048_export_records_ledger_position_check_before_compares_prefix.md`

Glob and read every sibling `*DESK-002R*ADDENDUM*.md`.

## The rule for every Part: merge before `part-complete`

The milestone station runs each Part's `check:` in the main checkout. Code changes go on a branch in a worktree, because main is read live by every launcher. So for each Part:
1. build it on the branch;
2. run the full suite on the branch;
3. merge to main and push;
4. then call `seldon dispatch part-complete`.

If the full suite fails on the branch, do not merge. Record the failures and stop. The station's design is Issue `02d52bc4`, which is not this task's to fix.

## Part A: merge DESK-002 Part A

1. Do not rebuild it: commit `01835ba` on the branch is the work.
2. Run the full suite on the branch. The first run did not.
3. Merge to main and push.

Acceptance:
- `check: pytest tests/test_desk002_ruling_commits_with_record.py -q`

## Part B: merge DESK-002 Part B

1. Commit `68f4c92` and the measurement `docs/evidence/desk002/registration_event_lines.md` are already on the branch. If Part A's merge carried them, call `part-complete` for B straight after A's.

Acceptance:
- `check: test -f docs/evidence/desk002/registration_event_lines.md`

## Part C: the register's source hash

1. `decision accept` and `decision propose` compute `source.sha256` from the bytes of the whole file at `source.path`, the register's convention (seq 972 to 975).
   - A caller-supplied value that differs is refused, naming both values.
   - `source.text` must equal the file's text at `source.lines`, or the record is refused.
2. `decision amend` may change `source.sha256` only to the digest of the file's current bytes, and only when the record's `source.text` still matches the file at its lines. Every other change to `source` still refuses.
3. Correct squiddy R-206 (seq 984) with that amend, to `ee543669519804d43a24ebec29e336e9ab0337b809396923d3bbf4f33cf5a025`, with a reason citing `5bfc2788`. Commit squiddy's register through the hooks.
4. Write tests, each of which fails on HEAD:
   - accept with a wrong digest refuses;
   - accept with no digest computes it;
   - amend to the file's true digest succeeds;
   - amend to any other value refuses.

Acceptance:
- `check: pytest tests/test_desk002_register_source_hash.py -q`

## Part D: the live control in squiddy

squiddy holds the exact case, uncommitted on disk:
- `docs/design/2026-10-16_DN-048_export_records_ledger_position_check_before_compares_prefix.md`
- `docs/decisions/register/00985_squiddy-r-207_accept.yaml` and `docs/decisions/REGISTER.md`
- `cc_tasks/2026-10-16_SQ-017_dn048_export_ledger_position_arnold_closed.md`
- `state/prior_art_queries.jsonl` and `governed/ledger/events.jsonl`, from DN-048's prior-art verdict (event 89705eb8)

Steps:
1. With Part A on main, run this in squiddy: `seldon cc register cc_tasks/2026-10-16_SQ-017_dn048_export_ledger_position_arnold_closed.md --allow-untracked`. Use the merged code path, not a hand `git add`.
2. Record the commit or commits it made and `git status` in `docs/evidence/desk002/squiddy_live_control.md`. squiddy's tree must be clean, including `seldon_events.jsonl`, which is Part B's fix.
3. Do not run SQ-017. squiddy's own dispatcher launches it.
4. If registration still refuses, record its output verbatim and stop.
5. Do Part C's R-206 correction before this registration, or after it, but not as part of it.

Acceptance:
- `check: test -f docs/evidence/desk002/squiddy_live_control.md`

## Report

Write the RESULT in under 30 lines at `cc_tasks/2026-10-17_DESK-002R_..._RESULT.md`. Include:
- tokens per Part, against 0.6M and the dispatcher's CPI;
- the Part C tests and their failures on HEAD;
- full-suite counts for each merge: passed, skipped, xfailed, deselected, failed;
- the squiddy live control: the commits, a clean `git status`, SQ-017's task id;
- premises found wrong.

Then run `seldon verify` and `seldon cc complete`, resolve the three Issues with their commits, merge and push.
