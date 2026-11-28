# Filing from factory: a task renumbered at filing keeps its old number inside its own acceptance check

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-27
**Reporter:** factory Desktop session FCT-7.

## What was experienced

At 19:25 EST on 2026-11-27 the coordinator filed a task into seldon with `seldon_cc_file` as `2026-11-27_SEL-059_recall_is_measured_...md`. SEL-059 had been taken minutes earlier by a return from squiddy SQ-155, so filing retried under AD-038-R18 and registered it as SEL-060, reporting two changes: the file name and the title line. The body was left as written. Its Part C acceptance check still reads `grep -q '^## For the consumer' cc_tasks/2026-11-27_SEL-059_recall_is_measured_..._RESULT.md`, a path that will never exist, and its addendum glob still says `*SEL-059*ADDENDUM*`. The dispatcher launched SEL-060 at 2026-11-28T00:06:33Z, before the coordinator saw it. The check cannot pass as registered; the session will finish its work and be held at its gate or blocked at merge.

The coordinator did not edit the registered file (a changed task file is refused at merge as `spec_modified`) and did not stop the running session.

## What the evidence shows

seldon `cc_tasks/2026-11-27_SEL-060_recall_is_measured_and_a_session_starts_with_what_the_record_says_about_the_files_it_will_touch.md` lines 21 and 42; the `seldon_cc_file` result text ("Retried under AD-038-R18 (next_number) after number_taken ... Changes: ...") in the factory thread; `cc_tasks/2026-11-27_SEL-059_squiddy_sq_155_init_check_counts_passage_passageof_and_a_declared_rows.md`, the task that holds the number.

## What factory wants to know

Whether a renumbered task's own references to its number (its RESULT path in a check, its addendum glob) are meant to follow the number, and how SEL-060's finished work is to land.
