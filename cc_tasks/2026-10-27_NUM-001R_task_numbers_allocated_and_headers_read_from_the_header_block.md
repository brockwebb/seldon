# NUM-001R: task numbers are allocated, not hand-minted, and headers are read from the header block only

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-27. Re-filing, with candidacy headers, of NUM-001 (ef0c9db0) and of the open half of 02bf065d (item 1, header anchoring); both had no source file and could never dispatch.
**Repo:** seldon (primary). L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-033-R12 (seq assigned at merge, the precedent for allocation); AD-038-R11 and R12 (candidacy headers, registration runs the dispatcher's static checks). Number new rulings under AD-038.
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: one allocator command, one registration refusal, one regex change, fixture tests. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits seldon/commands/cc.py and seldon/core/dispatch.py)
**Parts:** A 0.60, B 0.40.
**Premises:**
- premise: registration lives in register_task_file | check: grep -q "def register_task_file" seldon/commands/cc.py
- premise: the header regex is still unanchored | check: grep -q "_header_re" seldon/core/dispatch.py

Checks are single commands with no shell.

## The condition

A. Measured 2026-10-21: two Desktop threads both wrote squiddy SQ-019 within three hours (a0e43099, 6b38bc3f); both files told the session to glob every sibling `*SQ-019*ADDENDUM*`, so each would have read the other's addenda. Fixed by hand (re-issued as SQ-023). Same week: duplicate SEL-007s. There is no allocator.

B. `_header_re` in seldon/core/dispatch.py has no line anchor and the first match anywhere wins, so a `**Network:**` or `**After:**` quoted in prose is read as the header (2f5d4492 recorded network_kind=cadence from a Supersedes sentence; registration refused twice on 2026-09-22 for a prose `**After:**`).

## What to build

**A.** `seldon task number <PREFIX>` prints the next unused number for a prefix, reading the graph and `cc_tasks/` across main and every open worktree. `seldon cc register` refuses a file whose number is already registered to a different file in that repository (`number_taken`, naming the holder). An R suffix (SEL-010R, SEL-010R2) is the same number re-filed and is allowed when the holder is withdrawn or superseded. MCP: expose the allocator as a tool so a Desktop session calls it before writing a file. Test: two files with one number, the second refused.

**B.** Headers are read from the header block (the contiguous `**Name:**` lines after the title, line-anchored); a second match of the same header in the block refuses; prose matches are ignored. Control fixture: a file quoting `**After:**` in its body registers with its real After.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.

## Deliverables

A and B with tests; ef0c9db0 and 02bf065d superseded by this task in the closing commit; `cc_tasks/2026-10-27_NUM-001R_task_numbers_allocated_and_headers_read_from_the_header_block_RESULT.md`.
