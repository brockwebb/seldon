# RESULT: NUM-001R, task numbers are allocated and headers are read from the header block only

**Task:** `bacacc4c`, `cc_tasks/2026-10-27_NUM-001R_task_numbers_allocated_and_headers_read_from_the_header_block.md`.
No addenda.
**Date:** 2026-10-27. **Branch:** `worktree-dynamic-imagining-rossum`.
**Commits:**
- `7a7d75e`: Part A.
- `1340cfb`: Part B.
- `a98226e`: AD-038 ADDENDUM 05 and its two register records.
- `efd081c`: a fix the full suite found.
- The closing commit: this RESULT and the two supersessions.

**Rulings:** AD-038-R13 and AD-038-R14 are new and numbered under AD-038, as the task asked. They are in
`docs/design/AD-038_ADDENDUM_05_task_numbers_allocated_and_headers_read_from_the_header_block.md`, accepted
`--decided-by cc:bacacc4c`, and pending under `docs/decisions/register/pending/`. The merge step numbers them on main.
**Spend:** 222,644 tokens at Part B's boundary (`part_complete`), against an estimate of 0.4M and a stop at 0.5M.
Part A's boundary was at 172,793. There were no model calls and no network use (no push; the dispatcher merges).

Recall used: seldon:2026-10-26_SEL-011_registration_refuses_what_dispatch_would_refuse_and_every_non_candidate_gets_a_reason_RESULT

(SEL-011's RESULT set the shape of this one: new refusals go in `register_task_file` before creation, the ruling
goes in an AD-038 addendum with `--decided-by cc:<id>` records, and the resolved file-less tasks are superseded in
the closing commit. It also recorded the `test_pa002` drift and the "uncommitted" banner false failure, both met
again here. The other hits were background.)

## Part A: an allocator, and `number_taken` at registration

- **`seldon/core/numbering.py`.**
  - **The token.** A task number is `<PREFIX>-<digits><suffix>` with an optional `R`/`R<n>` re-filing marker. It is
    read from the file name, or, for a task with no file, from a description that leads with `<TOKEN>:` or
    `<TOKEN> —`. Seldon's graph has 72 file-less tasks; NUM-001 itself (`ef0c9db0`) was one.
  - **Identity.** A letter suffix is its own task. hazbrief's HB-01b to HB-01e and squiddy's SQ-021M/SQ-021M2 are
    siblings filed on purpose.
- **`seldon task number <PREFIX>` and the MCP tool `seldon_task_number`.**
  - They print the next unused number: one more than the highest holder under the prefix, at that prefix's widest
    width (three digits for a new prefix; HB stays two).
  - Holders come from the graph and from `cc_tasks/` in the primary checkout and every `git worktree list` entry, so
    a number on an unmerged branch is taken.
  - Live on seldon: `SEL-012` (after SEL-011, `bd5f26fb`) and `NUM-002` (after `ef0c9db0`), read across 4
    checkouts.
- **`register_task_file`** refuses, before anything is created, a numbered file whose number another file holds in
  the graph: `number_taken: <token> is already registered to another file ... (<token> by <id8> (<state>,
  <file>))`, with the allocator to ask.
- **The R suffix, and one amendment to the task's wording.** The task allows an R re-filing "when the holder is
  withdrawn or superseded".
  - All five R re-filings over an open holder in seldon's event log (DESK-002R, SEC-001R, DISP-001R, STD-001R,
    DISP-003R) were registered 4 to 34 seconds BEFORE their holder was superseded. `task supersede --superseded-by`
    needs the new task's id, so the re-filing has to come first.
  - A literal rule would refuse every one of them, and would refuse this task's own filing (`ef0c9db0` was still
    proposed).
  - R13 therefore also allows a holder that is still open and not running (proposed, accepted, blocked).
    Registration then prints the exact `seldon task supersede <holder> --superseded-by <new id> --reason ...` line.
  - It refuses over a holder that is in progress, completed or verified, and refuses a second file with the same R
    token.
  - The grounding is in the addendum §1 item 2.
- **A bare number is refused even when its holder was withdrawn.** MODEL-002 and SEL-006 were each filed twice under
  the bare number; the R suffix is how a re-filing is named now.
- **No reservation.** Two threads that ask at once get the same number, and the second registration refuses. This
  is optimistic concurrency with the unique check at insert (addendum §5), the same move as AD-033-R12.

**Tests** (`tests/test_num001r_task_numbers_allocated.py`, 26, real git and Neo4j):
- The task's required test: two SQ-019 files, the second refused with the holder named and nothing created.
- Re-registering the same file.
- A lettered sibling.
- R over an open holder (the supersede line is named), over a withdrawn one, and over a completed one (refused).
- A duplicate R.
- A bare reuse after withdrawal.
- A file-less holder.
- The allocator across the graph, an unregistered file on main's disk and a RESULT on an unmerged worktree branch
  (CLI and MCP both answer `SEL-014`).
- A bad prefix, and the name grammar.

## Part B: headers from the header block only

- **The block** (`seldon.core.dispatch.header_block`) is the preamble: after the `# ` title, up to the first `##`
  heading or thematic break, with fences skipped.
  - The task's wording was "the contiguous `**Name:**` lines after the title". That was measured first, over all
    1,623 base task files in `~/GitHub`. It would have dropped 106 real Network headers and 29 Spend headers.
    Authors separate header groups with blank lines and a sentence (seldon's own SEL-006 does), and 79 files write
    `**Spend:** ... **Network:** ...` on one line.
  - The preamble rule is RFC 5322 §2.1's header section in Markdown form (addendum §5).
- **`header_hits`.** A header line starts with a bold label carrying a colon.
  - Later fields on that line are read, except inside a backtick code span. That exception is exactly the 2f5d4492
    shape: `` its `**Network:**` header opened with ... ``.
  - An empty value takes the list under it (squiddy SQ-012/013/015's `**Spend:**`).
  - A colon-less `**Spend**` alone on its line is kept, because arnold KG-006 uses it and the old reader read it.
  - `_header_value`, `parse_headers` and `parse_concurrency_headers` all read through it. `_CONC_HEADER_RE`
    (SEL-004's local anchor) is gone.
- **`header_repeated:<name>`.** `static_checks` refuses any header it reads (the candidacy headers, After, Exclusive,
  Touches) that appears twice in the block, naming the lines. Registration and the dispatcher refuse on the same
  code.
- **Measured impact** (old reader at `7a7d75e` against the new one, compared as parsed outcomes: Spend tokens,
  Network kind, layer named, After kind, Exclusive, Touches). 6 of the 1,623 files change, and each is a prose
  misread corrected:
  - ai-readiness-kg `2026-10-02_evidence_map_prior_art_v2`: Network `cadence` → `none`. This is the 2f5d4492 defect
    itself.
  - Four files whose After was read from prose (ai-readiness-kg `2026-09-19_seldon_hygiene_superseded_cadence_after`,
    arnold `2026-05-15_fix-injury-...`, brock_projects `2026-05-09_sfv_intro_restructure`, squiddy SQ-076):
    unparseable → absent.
  - ai-readiness-kg `2026-08-30_bulk_extraction_v038`: Spend `1`, read from "1.3 ×" in a later section → absent.
  - No file in any repository carries a repeated header, so no task becomes refused by `header_repeated`.
- **Found by the measurement, fixed before commit.** My first cut blanked code spans before matching and lost a value
  that opens with one: 13 ai-readiness-kg `**After:** \`<stem>\`` and 3 arnold Touches values.
  `test_a_value_that_opens_with_a_code_span_is_read_whole` covers it.

**Tests** (`tests/test_num001r_headers_read_from_the_header_block.py`, 13):
- **The required control fixture.** A file with a prose `**After:** the scan, then the report` ABOVE its real
  `**After:** none`, and again in the body, registers, and the dispatcher reads `none`. Run against `7a7d75e`'s
  `dispatch.py` (`/tmp/num001r/oldcheck.py`), the old reader returns `after_unresolved` on this text, and Network
  `cadence` on the Supersedes-sentence fixture.
- Repeats refused at both gates, for After, Network and Exclusive.
- A body-only repeat is not refused.
- Fences, the section end, multi-field lines, list continuation, code-span values, the bare label, and a file with no
  title.

**Changed test:** `tests/test_dispatch.py::test_a_serial_task_carrying_a_malformed_concurrency_header_is_refused`.
It appended `**Exclusive:** perhaps` below the first `##` section, which is prose under R14. The fixture now puts it
in the block, where the refusal it tests still holds.

## Supersessions

`ef0c9db0` (NUM-001) and `02bf065d` (header anchoring) are superseded `--superseded-by bacacc4c`. The event lines are
in the closing commit. `02bf065d`'s item 3 (candidacy at registration) had already been built by SEL-011 (AD-038-R12),
and its item 2 by QC-002; the supersession reason says so.

## Verification

- **First full run, on `1340cfb`** (`python -m dotenv -f .env run -- python -m pytest tests/ -q -n 8`):
  **2 failed, 2962 passed, 7 skipped in 814s.**
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` is the known squiddy
    library-index drift. It fails on main and is not a regression.
  - `test_prior_art::test_cc_register_holds_rather_than_refuses` was mine. It registers an unnumbered file with
    `driver=None`, and the number check read the graph first. Fixed in `efd081c`: an unnumbered file reads no graph.
    That file, `test_dispatch_stuck_and_journal`, `test_cadence_pass` and `test_cc_register_commits` then passed
    (68).
- **Second full run, on `efd081c`: 2 failed, 2962 passed, 7 skipped in 750s.**
  - `test_pa002_release_resolve` is the same known drift.
  - `test_dispatch_parallel::test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` is the wall-clock
    overlap flake under 8-way xdist load that SEL-011 recorded. Re-run alone, `tests/test_dispatch_parallel.py`
    passed (14 passed in 304s). Nothing here touches launch timing.
  - The fix's own failure (`test_prior_art`) passes.

## Not done / for the next session

- **Older readers keep their own anchors:** `**Model:**` (`models.MODEL_HEADER_RE`), `**Parts:**`, `**Premises:**`,
  `**First article:**` (stations) and `**Governing:**` (prior_art). They are already line-anchored. Moving them onto
  `header_block` is a separate change; this task did not need it.
- **Doubled numbers already in seldon's graph** (MODEL-002, SEL-006, HOOK-001, SEL-007, SEL-008) stay as they are.
  R13 governs new registrations.
- **Desktop has to use the allocator.** The allocator only helps if Desktop calls `seldon_task_number` before writing
  a file. Registration's `number_taken` is the backstop either way.
