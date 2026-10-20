# AD-036 ADDENDUM 07: a receipt that cites its own note is a self-citation, and a task's governing notes are its Governing header

**Date:** 2026-10-20. **Written by:** DISP-003R Part B (`cc_tasks/2026-10-20_DISP-003R_gate_runs_the_branch_code.md`).
**Amends:** AD-036-R2 (how a receipt is judged) and AD-036-R4 as amended by ADDENDUM 05 (which notes hold a task).
Two new rulings, numbered from the register.

## Evidence

**Self-citation.** AD-036 ADDENDUM 03 line 106 is an internal receipt whose only hit is
`docs/design/AD-036_prior_art_receipts_gate.md:95`, the base note's own line. Since SQ-012 the internal arm leaves the
note under verification, base and addenda, out of its own search (QC-001 premise 3: a note is not prior art for itself).
So that receipt can never be returned. It read `id_not_returned` and failed AD-036 on every verification. Addenda are
immutable (AD-036-R7), so no edit could remove it. Verified on this branch at `dd781db`, the receipt now reads
`self_citation  docs/design/AD-036_ADDENDUM_03_prior_art_by_reference.md:106`. AD-036's remaining failures are its
`release_unavailable` library receipts, which PA-002 (ADDENDUM 06) answers.

**Governing.** `prior_art.governing_notes` took every `docs/design/*.md` path anywhere in a task's body, so a task that
named the note it repairs was held `governing_unverified` on it. STD-001 (`ac82552e`, 2026-10-19) was held for naming
the AD-036 self-test addendum as a file to correct. DISP-003 (`7f5de59e`, 2026-10-20) was held for a premise naming
ADDENDUM 03. Each was re-issued (STD-001R, DISP-003R) at the cost of a supersede and a registration.
`governing_commit.governing_notes`, the function that commits notes at registration, already read the header blocks
only. The two readers disagreed.

## The rules

- **AD-036-R14. An internal receipt whose every cited location lies inside the note under verification (its base or any addendum) is a self-citation: reported `self_citation`, and it neither passes nor fails the note.**
  In a receipt that also cites other locations, those are checked as before and the self-citations are named in its
  detail. A subsection whose receipts are all self-citations carries no prior art and fails as empty. The verdict
  payload lists `self_citations`. A self-citation is not re-run, so it writes no query-log line. Code:
  `seldon/core/prior_art.py` `SELF_CITATION`, `_verify_internal`, `verify_note`.
- **AD-036-R15. A task's governing notes are the notes its `**Governing:**` header names, by path or by AD-/DN- identifier, and nothing else.**
  A `docs/design/` path elsewhere in the task, in a premise, a step or the note it repairs, is text. It is not a
  governing note and holds nothing. Registration's holds and the dispatcher's c14 both read
  `prior_art.governing_notes`, so both change. Code: `seldon/core/prior_art.py` `governing_notes`.

*Not changed:* `governing_commit.governing_notes` still reads the `Implements`, `Amended by` and `Resolves` headers
as well. Those decide which uncommitted notes a registration commits with its task, not which notes hold it. A task
whose note is committed but unverified is held only when the note is in `**Governing:**`.

## Prior art

### External

- library receipt: query "self-citation excluded from citation counts" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-22_arXiv_2410_23968#p7:101:3427-3698
- library receipt: query "closing keywords issue reference mention" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-11_arXiv_2504_14765#p64:578:55-222

  Neither query found a row on its subject. The rows cited are the tops returned: a retrieval paper's token-count
  footnote and a forecasting prompt. The prior art is in the sources below.
- **Self-citation is its own class in bibliometrics.** Clarivate's Journal Citation Reports publishes impact
  factors with and without self-citations, and suppresses titles whose self-citation inflates the count. A citation
  of oneself is not counted as evidence from elsewhere. It is not treated as an error either. R14 takes the same
  view: neither a pass nor a failure, and never enough alone.
- **A mention is not a link.** GitHub links a pull request to an issue it closes only through a closing keyword
  (`Fixes #12`), while a bare `#12` in the text is only a cross-reference. git's `interpret-trailers` parses
  `Key: value` only from the trailer block at the end of a message, not from the body. PEP 1's header preamble
  (`Requires:`, `Replaces:`) is where a PEP's relationships live. R15 makes `**Governing:**` that header.

### Internal

- internal receipt: query "self-citation" | repo seldon@49f0e138d8397a8e7e37003fde1f331aa68c43ad | hits docs/design/2026-04-05_ad020_calibration_consolidated.md:154

AD-020's calibration (line 154) already reads a high self-citation rate as a framework not yet placed in its
literature. That is the reason R14 refuses a subsection made only of self-citations.

## Negative controls (AD-038-R6)

`tests/test_disp003_self_citation.py::test_negative_control_a_missing_hit_outside_the_note_still_fails`: a receipt
citing a self location and a missing file is still `id_not_returned`. `tests/test_disp003_governing_header.py::
test_negative_control_the_same_note_in_the_governing_header_is_held`: the same unverified note named in the header
is held. The positive tests fail on HEAD before this change. `tests/test_prior_art.py::
test_a_receipt_citing_the_note_itself_fails_and_says_why` encoded the old status. It now asserts `self_citation` for
the receipt and a failing note, because that receipt is its only Internal one.
