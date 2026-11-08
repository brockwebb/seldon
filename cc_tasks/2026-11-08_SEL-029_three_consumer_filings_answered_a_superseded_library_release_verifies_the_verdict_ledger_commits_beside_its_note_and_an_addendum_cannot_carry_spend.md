# SEL-029: three consumer filings answered: a receipt against a superseded library release verifies instead of failing `release_unavailable`; the verdict ledger commits beside the note whose verdict it carries; an addendum that carries a `**Spend:**` line is refused at commit with the re-filing rule

**Status:** proposed
**Author:** Desktop session (seldon, acting for the operator), 2026-11-08. Answers SEL-026 (`9f0c7e1b`), SEL-027 (`6e5d0d94`) and SEL-028 (`771032cd`), all filed by hazbrief-mcp in the last 30 hours. Each cost the consumer a re-filing or a failed commit; SEL-028 fails every design note older than the current library release.
**Repo:** seldon (primary). L4: commit, merge, push in seldon. The three filings are closed by this task's `seldon cc return`.
**After:** none
**Governing:** AD-036 (prior art: receipts, verify, R4 the commit gate, R10 the ledger, R17 consumer filings); AD-038 (the dispatcher: R11 candidacy headers read from the file only; R20 the Desktop commit tool registers what it commits); DESK-001 and DESK-002 (the Desktop commit tool's roots and the ruling-record exception). Number new rulings under AD-036 for Parts A and B and AD-038 for Part C.
**Model:** primary
**Spend:** est. 0.6M tokens. Basis: one resolution path in `prior_art.py` with a fixture of a superseded release, one root exception in `desktop_commit.py` mirroring DESK-002's, one header check at commit and registration, tests for each, three returns. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon/core/prior_art.py`, `seldon/core/desktop_commit.py`, the registration path in `seldon/core/dispatch.py` or `filing.py`)
**Parts:** A 0.45, B 0.25, C 0.30.
**Premises:**
- premise: verify names the failure | check: grep -q 'RELEASE_UNAVAILABLE = "release_unavailable"' seldon/core/prior_art.py
- premise: the export register is read by name | check: grep -q 'EXPORT_REGISTER = "EXPORT_VERSIONS.md"' seldon/core/prior_art.py
- premise: the Desktop tool refuses outside its roots | check: grep -q 'OUTSIDE_ROOTS = "outside_roots"' seldon/core/desktop_commit.py
- premise: the three filings are registered | check: test -f cc_tasks/2026-11-08_SEL-028_a_library_receipt_fails_verify_once_the_library_graph_is_re_released_every_note_older_than_the_current_release_now_fails.md

Checks are single commands with no shell.

## The condition

1. **SEL-028.** hazbrief-mcp's DN-019 (2026-11-04) carries a library receipt against release sha256 `7b72aaa89fe005d3...`. HB-125 produced a new library release on 2026-11-07/08 and the squiddy export register at HEAD no longer carries that sha, so `prior-art verify` on DN-019 with a new addendum returned FAIL, `release_unavailable`, while every other receipt passed (verdict `ea01ac75ed6043c8b8a2324d66d0f413` in hazbrief-mcp). Every note written before the current release will fail the same way when touched. First measure in Part A whether the register dropped the row (a squiddy or consumer release-step defect) or never kept superseded releases (a design gap here); the RESULT states which with the register's git history.
2. **SEL-026.** The commit gate (AD-036-R4) requires `state/prior_art_verdicts.jsonl` staged beside a verified note; `seldon_commit_governed` and `seldon commit-governed` refuse that path as `outside_roots`. A verified note is uncommittable through the tool addressed by the gate's own message. hazbrief-mcp committed DN-022 by hand with git.
3. **SEL-027.** HB-115's ADDENDUM-01 raised the task's Spend from 600k to 1.2M; the dispatcher's ceiling read the base line (720k at factor 1.2) and the andon halted the run at 942k. AD-038-R11 already says headers are read from the task file only; nothing enforced it on the addendum, so the consumer learned it from a halted task.

## What to build

### Part A: a superseded release verifies

1. Read the squiddy export register's history (`git log -p -- graphs/library/exports/EXPORT_VERSIONS.md` in the squiddy checkout `seldon.yaml` points at) and record whether `7b72aaa89fe005d3` was ever a row. If it was and was removed, the row-dropping step is named in the RESULT and SEL-028's return says the fix is in that step (file the squiddy filing from here if that is where it lives); this part still proceeds, because a register that keeps every row is not something verify may assume.
2. In `prior_art.py`, when a receipt's release cannot be rebuilt, resolve it before failing: a receipt verifies as `pass (superseded)` when the current release (or any release the register still carries) contains every row id the receipt lists, matched on the row id up to the release-specific suffix the index rule defines, and the verdict line names the release it was verified against. It fails `release_unavailable` only when no carried release contains the rows, and the message then says which rows are missing from the current release.
3. A receipt verified as superseded is not rewritten in the note; the ledger carries the resolution.
4. Tests: a fixture register with two releases where the older is removed; a receipt against the removed one passes superseded when its rows are in the newer one and fails with the missing rows named when one is absent; the existing `release_unavailable` cases (unreadable root, unreadable commit) are unchanged.

### Part B: the ledger commits beside its note

5. In `desktop_commit.py`, `state/prior_art_verdicts.jsonl` is accepted when it is named beside a design note (or addendum) whose current bytes have a verdict in that ledger, mirroring DESK-002's register exception: alone, or beside a note with no verdict for its bytes, it still refuses `outside_roots`. The commit message stays `desktop: design: <basename>`.
6. Decide, and record under AD-036, whether the gate should also read a verdict from the ledger on disk when the ledger is not staged. The recommended ruling is no: the staged ledger is the proof, and the Desktop tool now has a way to stage it. The RESULT says what was ruled.
7. Tests: the DESK-002 test file gains the ledger cases; the CLI `seldon commit-governed` and the MCP tool share the path and both are tested.

### Part C: an addendum cannot carry Spend

8. At `seldon_commit_governed` and `seldon_cc_register` of an addendum file (the `_ADDENDUM_` name pattern DN-006 defines), refuse when the file carries any candidacy header (`**Spend:**`, `**Network:**`, `**Framework layer served:**`, `**Exclusive:**`): `addendum_carries_header: <header>; headers are read from the task file only (AD-038-R11); to change one, re-file the task with an R suffix`. The refusal text is what the consumer sees, so it says the rule and the remedy in one line.
9. The wait form SEL-027 asks for (a Part that waits on an operator input without spending the ceiling) is a design question, not this task's: write it as an Issue on seldon with SEL-027's text and leave it open for a design note. The return to SEL-027 says so.
10. Tests: an addendum with a Spend line is refused at both entry points with the text above; an addendum without one is accepted as before; the existing addendum marker test is unchanged.

### Returns

11. `seldon cc return` to SEL-026, SEL-027 and SEL-028, each naming the Part that answers it and the tests.
12. Full gate; `seldon verify`; RESULT with the register finding from step 1 stated plainly.

## Not in this task

- The wait form (step 9's Issue); any change to the receipt format; the premise checker (single command, no shell) stays as it is, since it is documented.
