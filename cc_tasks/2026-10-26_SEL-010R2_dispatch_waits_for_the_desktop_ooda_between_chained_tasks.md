# SEL-010R2: `seldon dispatch` waits for the Desktop OODA between chained tasks, and a project adopts it in one step

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-26. Re-filing of SEL-010R (refused c10 `concurrency_undeclared`: `Exclusive: no` with no `Touches`) and of SEL-010 (hazbrief Desktop session, 2026-10-25), whose base file carries no candidacy headers and cannot be registered.
**Repo:** seldon (primary). L4: commit, merge, push in seldon. hazbrief is read by path for the adoption check, never written.
**Governing:** AD-034 (worktree dispatch) and AD-038 (the criteria vector and redrive); DN-006 §4 (the OODA the standing dispatcher did not automate); DN-005 §5 rule 1 (the framework-layer header). If c18 belongs under a new ruling, number it under AD-038 and say so in the RESULT.
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: one new criterion with a fixture test, one new command that writes a config block and a plist, one convention document. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits seldon/core/dispatch.py, which every dispatcher task touches)
**Parts:** A 0.45, B 0.35, C 0.20.
**Premises:**
- premise: the standing dispatcher note leaves the between-task OODA to a person | check: grep -q "Desktop OODA" docs/design/2026-09-15_standing_dispatcher.md
- premise: SEL-008 Part C's cross-project wait (c17) is on main | check: grep -q cross_waits seldon/core/dispatch.py
- premise: the candidacy headers are a kit-wide constant, not a per-project list | check: grep -q "REQUIRED_HEADERS = (HEADER_SPEND, HEADER_NETWORK, HEADER_LAYER)" seldon/core/dispatch.py

Checks are single commands with no shell.

Glob and read every sibling `*SEL-010*ADDENDUM*.md`.

## Scope

The condition, what to build and the deliverables are in `cc_tasks/2026-10-25_SEL-010_dispatch_waits_for_the_desktop_ooda_between_chained_tasks.md`, which stays as the statement of record. Parts A, B, C are that file's "What to build" items 1, 2, 3. Deliver the RESULT as `cc_tasks/2026-10-26_SEL-010R2_..._RESULT.md` and leave the SEL-010 base file untouched.

## One finding to record in the RESULT, found before launch

`seldon cc register` reads candidacy headers from the base file only. SEL-010's ADDENDUM-00 (committed 9f4caa6) carries every header and registration still refused `parts_undeclared`. So an addendum cannot repair a committed base file's headers, and the only route is a new file, which is this one. Part B's `dispatch adopt` and the per-project header list should either make the registrar read addendum headers or state that it will not and why; TRIAGE-001's note that SEL-003 "needs those headers added in an addendum" is wrong on the current code and should be corrected the same way.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.
