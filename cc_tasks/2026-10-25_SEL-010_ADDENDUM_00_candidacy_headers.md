# SEL-010 ADDENDUM 00: the candidacy headers the base file omitted

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-25
**Repo:** seldon (primary). L4: commit, merge, push in seldon. hazbrief is read by path for the adoption check, never written.
**Governing:** AD-034 (worktree dispatch) and AD-038 (the criteria vector and redrive); DN-006 §4 (the OODA the standing dispatcher did not automate); DN-005 §5 rule 1 (the framework-layer header). If c18 belongs under a new ruling, number it under AD-038 and say so in the RESULT.
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: one new criterion with a fixture test, one new command that writes a config block and a plist, one convention document. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** no
**Parts:** A 0.45, B 0.35, C 0.20.
**Premises:**
- premise: the standing dispatcher note leaves the between-task OODA to a person | check: grep -q "Desktop OODA" docs/design/2026-09-15_standing_dispatcher.md
- premise: SEL-008 Part C's cross-project wait (c17) is on main | check: grep -q cross_waits seldon/core/dispatch.py
- premise: the candidacy headers are a kit-wide constant, not a per-project list | check: grep -q "REQUIRED_HEADERS = (HEADER_SPEND, HEADER_NETWORK, HEADER_LAYER)" seldon/core/dispatch.py

Checks are single commands with no shell.

## Why this addendum exists

The base file was committed 2026-10-25 08:42 by the hazbrief Desktop session and never registered. `seldon cc register` refuses it at `parts_undeclared`, and the dispatcher would refuse it next on `no_header:Spend,Framework layer served` (its `**Spend:** none.` is not a token count, and it names no layer). The task file is immutable once committed, so the headers live here. Parts A, B, C map to the base file's "What to build" items 1, 2, 3.

That the file was refused by the very header its item 2 proposes to make per-project is the first observation for the RESULT, not a reason to skip the header.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.

## Deliverables

Unchanged from the base file.
