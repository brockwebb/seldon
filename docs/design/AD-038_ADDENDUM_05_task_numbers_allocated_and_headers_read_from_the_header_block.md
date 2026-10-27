# AD-038 ADDENDUM 05: task numbers are allocated, and headers are read from the header block only

**Date:** 2026-10-27. **Status:** Accepted. Implemented by NUM-001R
(`cc_tasks/2026-10-27_NUM-001R_task_numbers_allocated_and_headers_read_from_the_header_block.md`, task `bacacc4c`).
**Amends:** AD-038-R12 (registration runs the dispatcher's static checks), which gains `number_taken` and
`header_repeated`; DN-006 decision 2's header reading.
**Resolves:** ResearchTasks `ef0c9db0` (NUM-001) and `02bf065d` (header anchoring, its open item 1).
**Code:** `seldon/core/numbering.py`; `seldon/commands/task.py` (`seldon task number`); `seldon/mcp_server.py`
(`seldon_task_number`); `seldon/commands/cc.py` (`register_task_file`); `seldon/core/dispatch.py` (`header_block`,
`header_hits`, `repeated_headers`, `_header_value`, `parse_concurrency_headers`, `static_checks`).
**Tests:** `tests/test_num001r_task_numbers_allocated.py`; `tests/test_num001r_headers_read_from_the_header_block.py`.

## 1. Evidence

1. 2026-10-21: two Desktop threads both wrote squiddy SQ-019 within three hours (`a0e43099`, `6b38bc3f`). Each file
   told its session to glob every sibling `*SQ-019*ADDENDUM*`, so each would have read the other's addenda. It was
   fixed by hand (re-issued as SQ-023). The same week had two SEL-007s. seldon's graph also holds MODEL-002, SEL-006
   and HOOK-001 twice each under the bare number. Nothing allocated a number.
2. All five of seldon's R re-filings over an open holder in the event log (DESK-002R, SEC-001R, DISP-001R, STD-001R,
   DISP-003R) were registered 4 to 34 seconds before their holder was superseded. The supersession needs the new id
   (`--superseded-by`), so the re-filing comes first. SEL-010R2 was registered after SEL-010R was withdrawn.
3. `_header_re` had no line anchor and the first match anywhere won. 2f5d4492 recorded `network_kind=cadence` from a
   Supersedes sentence. Registration refused twice on 2026-09-22 for a prose `**After:**`.
4. Measured 2026-10-27 over the 1,623 base task files in `~/GitHub`:
   - "The contiguous header lines after the title" would have dropped 106 real Network headers and 29 Spend headers.
     Authors separate header groups with blank lines and sentences, and write `**Spend:** ... **Network:** ...` on
     one line.
   - The preamble rule below changes 6 parsed outcomes, each a prose misread corrected: four After values, the
     2f5d4492 file's Network, and one Spend read as `1` from "1.3 ×" in a later section.
   - No file carries a header twice in its block.

## 2. Rulings

- **AD-038-R13. Task numbers are allocated by a command and unique per repository at registration.**
  - `seldon task number <PREFIX>` and the `seldon_task_number` MCP tool print the next unused number: one more than
    the highest number any holder carries under the prefix, at the widest width the prefix has used (three digits
    for a new prefix).
  - Holders are read from the graph and from `cc_tasks/` in the primary checkout and every open worktree. A graph
    holder is a ResearchTask whose file name carries the number or, with no file, whose description leads with
    `<TOKEN>:` or `<TOKEN> —`.
  - A token is `<PREFIX>-<digits><suffix>` with an optional trailing `R` or `R<n>`. A letter suffix is a distinct
    task (HB-01b, SQ-021M2). The `R` suffix is a re-filing of the same number (SEL-010R, SEL-010R2).
  - `seldon cc register` refuses, before anything is created, a file whose number another file holds in that
    repository's graph (`number_taken`, naming each holder).
  - An R re-filing is allowed when every other holder of its number is withdrawn, superseded or rejected, or still
    open and not running (proposed, accepted, blocked). Registration then names each open holder and the exact
    `seldon task supersede <holder> --superseded-by <new id>` line. It is refused over a holder that is in progress,
    completed or verified, and over a second file with the same R token.
  - The allocator reserves nothing. Two threads that ask at once get the same answer; the second registration is
    refused, and its author asks again.
- **AD-038-R14. Headers are read from the header block only, and a header the block carries twice refuses.**
  - The header block is the task file's preamble: the lines after the `# ` title up to the first `##` heading or
    thematic break, with fenced code excluded (the whole file's start when there is no title).
  - A header line starts, after optional indentation and a list bullet, with a bold label carrying a colon. A later
    `**<Name>:**` field on such a line is read too, except inside a backtick code span. A header line with no value
    takes the list or indented lines under it. A colon-less `**<Name>**` alone on its line is read the same way.
  - Nothing outside the block, and no line that does not start with a label, is read as a header.
  - The candidacy headers, After, Exclusive and Touches are all read this way (`_header_value`, `parse_headers`,
    `parse_concurrency_headers`).
  - `static_checks` refuses `header_repeated:<name>` for any header it reads that appears twice in the block,
    naming the lines. Registration and the dispatcher refuse on the same code.

## 3. Negative control

- `test_two_files_with_one_number_the_second_is_refused_and_names_the_holder`: the SQ-019 case. The first file
  registers; the second is refused and nothing is created.
- `test_registering_the_same_file_again_is_not_a_collision_with_itself` and
  `test_a_lettered_sibling_is_its_own_number`: what was legal stays legal.
- `test_control_a_file_quoting_after_in_its_body_registers_with_its_real_after`: a prose `**After:** the scan, then
  the report` above the real `**After:** none` and again in the body. The reader before R14 refuses this file
  `after_unresolved` (checked against `dispatch.py` at `7a7d75e`). It now registers, and the dispatcher reads
  `none`.
- `test_a_header_repeated_only_in_the_body_is_not_a_repeat`: prose repeats are not a refusal.

## 4. What this does not change

- Addenda are still never read for headers (AD-038-R11).
- `**Model:**` (`seldon.models.MODEL_HEADER_RE`), `**Parts:**`, `**Premises:**` and `**First article:**`
  (`seldon.core.stations`) keep their own line-anchored readers. `**Governing:**` keeps
  `prior_art._GOVERNING_BLOCK_RE`.
- Numbers already held twice in a graph (MODEL-002, SEL-006, HOOK-001 in seldon) stay as they are. R13 governs new
  registrations.

## 5. Prior art

### External

- **Sequential human-readable keys allocated by the system.**
  - An issue tracker's `PROJ-123` keys are minted by the tracker at create time, never by the author.
  - PEP 1: "the PEP editors will assign a PEP number".
  - The RFC Editor assigns RFC numbers at publication.
  *Adopted:* the number comes from one allocator that reads every holder, not from the author's view.
- **Optimistic concurrency with a unique constraint at insert.** A read-then-insert under a unique index (PostgreSQL
  documentation, "Unique Indexes" and `INSERT ... ON CONFLICT`) proposes freely and lets the constraint refuse the
  loser, who retries. *Adopted* in place of a reservation ledger: registration is the insert, `number_taken` is the
  constraint.
- **The header section ends where the body begins.**
  - RFC 5322 §2.1: a message is header fields, then an empty line, then the body. §3.6 limits fields such as
    `Subject:` to at most one occurrence.
  - Pandoc's title block and MultiMarkdown's metadata are the Markdown form: a block at the top of the file, read
    as metadata only there.
  *Adopted:* headers are read only from the preamble, and a repeated field is malformed rather than resolved by order.
  *Departed from:* the end marker. Blank lines may separate header groups (§1 item 4), so the block ends at the first
  section heading or thematic break.

### Internal

- AD-033-R12: a decision record's `seq` is assigned at merge, not at authoring. This is the same move, numbering at
  the point of commit.
- AD-038-R12 (SEL-011): registration refuses what the dispatcher would. Both new refusals are made there, with the
  dispatcher's own function for R14.
- `_CONC_HEADER_RE` (SEL-004) had already anchored Exclusive and Touches to line start after a prose quote was read
  as a declaration. R14 generalizes it to every header and replaces it.
