# SEL-056: squiddy SQ-151: the coarse tier for reference documents, with a cited passage promoted word for word

**Status:** proposed
**Author:** `seldon cc return`, 2026-11-27, for squiddy SQ-151 (8052015c), which answered squiddy:750348cb (AD-036-R16).
**Returns:** squiddy:8052015c-1317-4201-9ab4-a853c4592128 (SQ-151)
**After:** 2026-11-27_SEL-055_the_gate_runs_what_a_change_can_break_and_no_queue_waits_an_hour_for_a_one_line_change
**Spend:** est. 0.05M agent tokens. Basis: reading one design note and deciding whether the governed graph declares the tier; zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Parts:** A 1.00.

squiddy:750348cb (750348cb) was filed into squiddy; squiddy task SQ-151 (8052015c) answered it. This task is that answer's return, filed by the answering task rather than pasted by hand (AD-036-R16).

## What landed, and where

- The answering task: `squiddy/cc_tasks/2026-11-26_SQ-151_a_graph_can_carry_design_patterns_work_to_work_edges_and_status_flags_and_a_coarse_tier_for_reference_documents.md`.
- Its RESULT: `squiddy/cc_tasks/2026-11-26_SQ-151_a_graph_can_carry_design_patterns_work_to_work_edges_and_status_flags_and_a_coarse_tier_for_reference_documents_RESULT.md`. Read it in full before starting.
- The commit: squiddy@348d4497569e7c51ed336398ece154984e1ed166 (on branch worktree-tingly-twirling-lantern, which the dispatcher merges to main).

## What seldon does with it

Answers seldon's filing `750348cb` (the operator's statement of 2026-11-12). A graph may declare
`tiers: {coarse: [reference]}`: an entry with that disposition is admitted, held, parsed and indexed (the index's
paragraph units with located receipts, as `squiddy-library` search already returns them) and is never extracted
whole. A passage someone cites is promoted on demand, word for word: `squiddy passage promote --graph G --id <entry>
--exact "<quote>" [--prefix ..] [--suffix ..] [--locator "p. 8"] --for "<the citation>" --by <who>` locates it by the
W3C TextQuoteSelector exactly once in the parsed text, cuts it from there, and writes a `Passage` node (its span,
hashes, `promoted_for`, `promoted_by`) and a `PassageOf` edge; the ledger event is the promotion's record
(DN-050 ADDENDUM 02 R-295). Not built: a model's claims extracted from a promoted passage (R-296), and `45b88039`'s
narrower ask, locating a passage without parsing and indexing the whole document, which stays open.

In a shell, any directory, to read what was decided:

```
1.  sed -n '/^### R-295/,/^### R-296/p' /Users/brock/GitHub/squiddy/docs/design/2026-11-27_DN-050_ADDENDUM_02_patterns_work_to_work_edges_status_flags_and_a_coarse_tier.md
```

A graph that adopts it adds `tiers: {coarse: [reference]}`, `- Passage: Node` and `- PassageOf: Edge` to its spec,
then `squiddy init <graph> --render --allow-schema-change` and `squiddy schema declare --graph <graph>`.

## Part A: apply it

Acceptance:
- `check: test -f cc_tasks/2026-11-27_SEL-056_squiddy_sq_151_the_coarse_tier_for_reference_documents_with_a_cited_pa_RESULT.md` (the RESULT says what was applied, and what was not)
