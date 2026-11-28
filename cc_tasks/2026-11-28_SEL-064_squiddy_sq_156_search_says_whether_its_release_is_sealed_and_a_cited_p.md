# SEL-064: squiddy SQ-156: search says whether its release is sealed, and a cited passage is promoted from its cited pages alone

**Status:** proposed
**Author:** `seldon cc return`, 2026-11-28, for squiddy SQ-156 (52a7f4f8), which answered squiddy:c923eb5a (AD-036-R16).
**Returns:** squiddy:52a7f4f8-5169-41f0-b705-c1051035f7d6 (SQ-156)
**After:** 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings
**Spend:** est. 0.02M agent tokens. Basis: reading this section; nothing to run.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Parts:** A 1.00.

squiddy:c923eb5a (c923eb5a) was filed into squiddy; squiddy task SQ-156 (52a7f4f8) answered it. This task is that answer's return, filed by the answering task rather than pasted by hand (AD-036-R16).

## What landed, and where

- The answering task: `squiddy/cc_tasks/2026-11-27_SQ-156_a_graphs_index_is_built_in_minutes_not_most_of_a_day_and_the_oldest_open_filings_are_answered.md`.
- Its RESULT: `squiddy/cc_tasks/2026-11-27_SQ-156_a_graphs_index_is_built_in_minutes_not_most_of_a_day_and_the_oldest_open_filings_are_answered_RESULT.md`. Read it in full before starting.
- The commit: squiddy@6c9c75d39083ac904d481537c22eca2aede73d90 (on branch worktree-snappy-squishing-lemur, which the dispatcher merges to main).

## What seldon does with it

Answers seldon's filings `c923eb5a` (the library's served index carried an unsealed release) and `45b88039` (a
project's cited-sources graph was built by hand, and whole-document parse was most of the cost).

What changed for you:

- **`c923eb5a`** (DN-063 ADDENDUM 02 R-318): the index is built at stage 15, before the gates that read it and before
  the seal, because those gates must pass first; what is served in that window now says so. Every `search` answer's
  `index` carries `release_sealed`: `true` when squiddy's ledger holds a seal of the export the index is bound to,
  `false` when it does not (between stage 15 and the seal, or a release a later gate killed: a receipt taken then names
  a release no register holds), `null` for a graph whose ledger seals nothing. A gate-killed release's export stays in
  `exports/` (R-306 and R-307 need it); whether it is sealed is the same question. Refusing a receipt when
  `release_sealed` is false is your library arm's to decide. The stronger form, building beside the served index and
  swapping at the seal, is named and not built.
- **`45b88039`**, first question: the kit now builds a graph of the works a project's notes cite. Catalog from your
  candidates; acquire resolves (OpenAlex, Crossref), honours robots.txt and holds bytes under an archive root; SQ-150's
  union catalog links a work another graph holds; SQ-151's coarse tier holds and indexes a reference document and never
  extracts it whole. No resolver or fetcher is needed in seldon.
- **`45b88039`**, second question (DN-050 ADDENDUM 04 R-319): `squiddy passage promote --graph G --id <entry> --pages
  A-B --exact "<quote>" --for "<the citation>" --by <who>` checks the held file's bytes, reads only pages A to B and
  promotes the passage word for word, with no whole-document parse; SP 800-53's one control costs its pages, not a
  492-page docling parse. The passage is a `Passage` node with its `PassageOf` edge (R-295); item 42 checks it.

Nothing to run.

## Part A: apply it

Acceptance:
- `check: test -f cc_tasks/2026-11-28_SEL-064_squiddy_sq_156_search_says_whether_its_release_is_sealed_and_a_cited_p_RESULT.md` (the RESULT says what was applied, and what was not)
