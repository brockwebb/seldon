# DESK-002: a Desktop design note that adds a ruling commits with its register record; registration commits its own event lines; the register takes its source hash from the file

**Repo:** seldon (primary). Cross-repo by absolute path: `/Users/brock/GitHub/squiddy` (Part D, the live control). L4: commit, merge, push in every repo touched.
**Date:** 2026-10-16. **Authored by:** a Desktop session in squiddy (SQ8).
**Resolves:** Issues `5c689098` (desktop_cannot_commit_note_with_new_ruling), `70bf1a21` (registration_leaves_governed_sync_lines_uncommitted), `5bfc2788` (decision_accept_does_not_verify_source_hash).
**Governing:**
- AD-033-R2: a labelled ruling has a register record staged with its note.
- AD-033-R3: a ruling is registered from the note's own bytes.
- AD-036-R4 and R13: the commit gate.
- DESK-001: the tool that writes a governed file commits it.
No new ruling: this task makes the tools meet rulings already in force.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.8M tokens. Basis: DESK-001 was estimated at 1.2M for four Parts of comparable code; this task is narrower.
**Parts:** A 0.35, B 0.20, C 0.25, D 0.20.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: DESK-001's commit path is on main | check: `test -f seldon/core/desktop_commit.py`
- premise: SEL-006's registration commit is on main | check: `test -f seldon/core/governing_commit.py`
- premise: the live control's design note is on disk in squiddy | check: `test -f /Users/brock/GitHub/squiddy/docs/design/2026-10-16_DN-048_export_records_ledger_position_check_before_compares_prefix.md`

Glob and read every sibling `*DESK-002*ADDENDUM*.md`.

## Step 0

If this task is `in_progress`, stop. Otherwise set it `in_progress` now.

## The defects, measured

1. **A Desktop session cannot commit a design note that labels a new ruling (Issue `5c689098`).**
   - The commit gate (AD-033-R2) requires the ruling's register record to be staged with the note.
   - `seldon_commit_governed` refuses `docs/decisions/` as `outside_roots`.
   - `seldon_cc_register` stages the note, the task, `state/prior_art_queries.jsonl` and `governed/ledger/events.jsonl`, but not the register record or `REGISTER.md`. So the gate refuses, and nothing is registered.
   - Reproduced deterministically on 2026-10-16 in squiddy: DN-048 labels R-207 (register seq 985), and registering SQ-017 failed with `governing_note_uncommitted`.
   - The same failure on 2026-10-15 with DN-047 / R-206 needed an operator paste into Claude Code.
2. **Registration's own event-store lines may be left uncommitted (Issue `70bf1a21`).**
   - On 2026-10-16 at 09:42Z, registering squiddy SQ-016R appended `link_created` lines with actor `governed_sync` to `seldon_events.jsonl`. The dispatcher refused to commit them ("written by governed_sync, which is not one of dispatcher, desktop"), then refused the task on c7.
   - That registration ran after the task file had already been committed by `seldon_commit_governed`. The issue's author suspects the order mattered: on 2026-10-15 at 14:45Z, a registration of an uncommitted file was committed by the dispatcher's `register:` step with no c7 on the event store.
   - Establish which it is before fixing: write a test that fails on HEAD, or a measurement showing the defect does not exist.
3. **`seldon_decision_accept` stores `source.sha256` and `source.text` as given, unchecked (Issue `5bfc2788`).**
   - squiddy R-206 (seq 984) carries a 12-hex prefix of a hash over a transcription of DN-047 lines 38-43. The register's convention is the whole-file digest: seq 972 to 975 carry one digest each, for different line spans.
   - The correct digest, measured on 2026-10-15 from the committed note, is `ee543669519804d43a24ebec29e336e9ab0337b809396923d3bbf4f33cf5a025`.
   - `seldon decision amend` refuses every change to `source` ("fixed at creation"), so the wrong value cannot be corrected.

## Part A: the ruling and its record commit together

1. Make `seldon_cc_register` stage, in the same commit as the note and the task:
   - the register record files for every ruling the governing note labels that has no committed record yet;
   - `docs/decisions/REGISTER.md`.
2. Make `seldon_commit_governed` accept a `docs/decisions/register/*.yaml` path and `REGISTER.md` in the same call as a design note whose labels those records answer, and nowhere else. A register path given alone still refuses as `outside_roots`.
3. Write tests, each of which fails on HEAD:
   - Registration of a task whose note labels a new ruling commits the note, the record and REGISTER.md together, and the gate passes.
   - `commit_governed` with a note plus its record commits both.
   - `commit_governed` with a record alone refuses.
   - The gate still refuses a note whose label has no record anywhere.

Acceptance:
- `check: pytest tests/test_desk002_ruling_commits_with_record.py -q`

## Part B: registration's event lines

1. Measure, in a temp repo, whether `seldon_cc_register` on an already-committed task file leaves `governed_sync` lines uncommitted in `seldon_events.jsonl`. Record the measurement in `docs/evidence/desk002/registration_event_lines.md`.
2. If the defect exists, registration commits every event line it wrote in the same commit as the task, through the hooks, and a test pins it. If it does not exist, close `70bf1a21` as not reproduced, with the measurement as the reason.

Acceptance:
- `check: test -f docs/evidence/desk002/registration_event_lines.md`

## Part C: the register's source hash

1. `decision accept` and `decision propose` compute `source.sha256` from the file's bytes at `source.path`. A caller-supplied value that differs is refused with both values. `source.text` must equal the file's text at `source.lines`, or the record is refused.
2. `decision amend` may change `source.sha256` only to the digest of the file's current bytes, and only when the record's `source.text` still matches the file at its lines. Every other change to `source` still refuses. This is a verifiable correction, not a rewrite.
3. Correct squiddy R-206 with that amend: `ee543669519804d43a24ebec29e336e9ab0337b809396923d3bbf4f33cf5a025`, reason citing `5bfc2788`. Commit the squiddy register through the hooks.
4. Write tests, each of which fails on HEAD:
   - accept with a wrong digest refuses;
   - accept with no digest computes it;
   - amend to the file's true digest succeeds;
   - amend to any other value refuses.

Acceptance:
- `check: pytest tests/test_desk002_register_source_hash.py -q`

## Part D: the live control in squiddy

squiddy holds the exact case from defect 1, uncommitted on disk:
- `docs/design/2026-10-16_DN-048_export_records_ledger_position_check_before_compares_prefix.md`
- `docs/decisions/register/00985_squiddy-r-207_accept.yaml` and `docs/decisions/REGISTER.md`
- `cc_tasks/2026-10-16_SQ-017_dn048_export_ledger_position_arnold_closed.md`
- `state/prior_art_queries.jsonl` and `governed/ledger/events.jsonl`, from DN-048's prior-art verdict (event 89705eb8)

Steps:
1. After Part A merges, run `seldon cc register cc_tasks/2026-10-16_SQ-017_dn048_export_ledger_position_arnold_closed.md --allow-untracked` in squiddy with the fixed code. Use the fixed code path, not a hand `git add`.
2. Record the commit it made and `git status`. The tree must be clean.
3. Do not run SQ-017. squiddy's own dispatcher launches it.
4. If registration still refuses, record its output verbatim and stop.

Acceptance:
- `check: test -f docs/evidence/desk002/squiddy_live_control.md`

## Report

Write the RESULT in under 30 lines at `cc_tasks/2026-10-16_DESK-002_..._RESULT.md`. Include:
- tokens per Part, against 0.8M and the dispatcher's CPI;
- each test and its failure on HEAD;
- Part B's measurement and the decision it led to;
- the squiddy live control: the commit, a clean `git status`, SQ-017's task id;
- suite counts: passed, skipped, xfailed, deselected, failed;
- premises found wrong.

Then run `seldon verify` and `seldon cc complete`, resolve the three Issues with their commits, merge and push.
