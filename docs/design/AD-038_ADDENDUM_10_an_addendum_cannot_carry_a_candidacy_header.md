# AD-038 ADDENDUM 10: a task addendum that carries a candidacy header is refused where it enters the machine

**Date:** 2026-11-08. **Status:** Accepted. Implemented by SEL-029 Part C
(`cc_tasks/2026-11-08_SEL-029_three_consumer_filings_answered_a_superseded_library_release_verifies_the_verdict_ledger_commits_beside_its_note_and_an_addendum_cannot_carry_spend.md`),
answering hazbrief-mcp's filing SEL-027 (`6e5d0d94`). **Enforces:** AD-038-R11 ("the headers ... are read from the
task's base file and never from an addendum"), which until now was enforced nowhere. One new ruling.
**Code:** `seldon/core/dispatch.py` (`ADDENDUM_FORBIDDEN_HEADERS`, `ADDENDUM_CARRIES_HEADER`, `is_addendum_name`,
`addendum_header_refusal`); `seldon/core/desktop_commit.py` (`_addendum_refusal`); `seldon/commands/cc.py`
(`register_task_file`, and the CLI's fix line); `seldon/mcp_server.py` (`seldon_cc_register`'s fix line).
**Tests:** `tests/test_sel029_ledger_and_addendum_commit.py` (Part C).

## 1. Evidence

1. **HB-115.** Its base file carries `**Spend:** ... 600,000 ...`; its ADDENDUM-01 section 4 raised the spend to
   1,200,000. The dispatcher's ceiling read the base line (720,000 at factor 1.2) and the andon halted the run at
   942,515 tokens (hazbrief-mcp HB-115 RESULT, Outcome; SEL-027 observation 1). The consumer learned R11 from a halted
   task.
2. **The raise was prose.** The addendum's line is "Spend rises to 1200000 for the Part 0 work." (hazbrief-mcp
   `cc_tasks/2026-11-04_HB-115_..._ADDENDUM_01_...md:33`), not a `**Spend:**` header. A header check would not have
   caught that file; it catches the form an author reaches for once told the base line is a header, and the refusal
   states the rule so the prose form is not the next attempt.

## 2. Prior art

- **Immutable fields refused with the remedy (Kubernetes API conventions).** An update that changes an immutable field
  (a Deployment's `spec.selector`, a Job's `spec.template`) is rejected by validation with a message naming the field,
  and the documented remedy is to delete and recreate the object. Adopted: an addendum that would change a candidacy
  header is refused naming the header, and the remedy (re-file the task with an R suffix) is in the same line.
- **RFC 5322 §2.1, the header section.** A message's headers are its preamble, and a header-shaped line in the body
  is body. AD-038-R14 already reads candidacy headers from the base file's block only; this ruling closes the other
  side, so a header-shaped line in an addendum cannot look like a change the machine will act on.
- **Internal:** AD-038-R11 (headers from the base file only; a missing header is a re-filing); AD-038-R12 (registration
  runs the dispatcher's static checks); DESK-002 (the Desktop commit tool refuses with the rule and the remedy).

The external sources are cited by their published names and were not fetched: the task's Network header allows
nothing beyond git.

## 3. Ruling

- **AD-038-R24. A task addendum that carries a candidacy header is refused at `seldon_commit_governed` and at `seldon_cc_register`, the rule and the remedy in one line.**
  A `cc_tasks/` file named `*_ADDENDUM*.md` carrying `**Spend:**`, `**Network:**`, `**Framework layer served:**` or
  `**Exclusive:**` anywhere outside fenced code and code spans refuses
  `addendum_carries_header: **<header>:**; headers are read from the task file only (AD-038-R11); to change one,
  re-file the task with an R suffix`. Nothing is staged or registered. An addendum without one commits and registers
  as before; a header quoted in backticks is prose.

## 4. Details

1. **The wait form is not designed here.** SEL-027's second question (a Part that waits on an operator input without
   spending the session's ceiling) is Issue `0555aa72`, open for a design note.
2. **Why anywhere in the file, not the header block.** An addendum has no candidacy block of its own; a raise written
   under a section heading is the case that misled the consumer.
