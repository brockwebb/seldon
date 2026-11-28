# RESULT: SEL-064, squiddy SQ-156: the library arm reports whether its release is sealed; a cited passage needs nothing in seldon

**Date:** 2026-11-28. **Task:** 3dffb4f2. **Returns:** squiddy SQ-156 (52a7f4f8), which answered seldon's filings
`c923eb5a` and `45b88039`. **Addenda read:** none exist (`ls cc_tasks | grep SEL-064` lists only the task file).
**Spend:** zero model calls; 96,173 agent tokens at the Part A boundary (`seldon dispatch part-complete`, wall 850 s),
against an estimate of 0.02M. The estimate assumed "nothing to run"; decision 1 added code, red-first tests and a
36-file prior-art test run. **Network:** none.
**Not done, per the dispatcher's launch instructions:** merge, push, `seldon cc complete`.

Recall used: seldon:AD-036-R16, squiddy:R-306, squiddy:R-307

R-306 and R-307 (squiddy keeps a gate-killed release's export on disk and reads its sha256 from it) are why an
unsealed release's receipt stays verifiable, so the arm reports the state and does not refuse it (decision 1).
AD-036-R16 is why this is the return's task and why it answers both filings. The other recall hits (SQ-150, SQ-151,
R-295, R-110, DI-169) describe the cited-sources and passage machinery the return names, and changed nothing here.

## Step 0: SQ-156 is on squiddy main

The return names `6c9c75d3` on squiddy's worktree branch. The dispatcher rebased it before merging, so that sha is not
an ancestor of squiddy main. The code is on main: `squiddy/index.py` `Index.release_sealed` (line 1622) and its
`"release_sealed"` key in `Index.search`'s `index` (line 1650), and SQ-156's RESULT commits `b7dc3bd6`, `50a586f0` and
`2583c20a`. I read the SQ-156 RESULT in full.

## Decisions, and their grounding

1. **`c923eb5a`: the library arm reports `release_sealed` and does not refuse a receipt on it.** The return leaves
   this to seldon. A refusal would buy nothing that verification does not already give, and it would cost something:
   - Integrity does not depend on the seal. A receipt names its export by sha256, and `verify` rebuilds that export
     and compares it hash for hash (AD-036-R2, R3, ADDENDUM 06). squiddy R-306 and R-307 keep a gate-killed release's
     export in `exports/`, so the rebuild has its bytes. When the export is gone, AD-036-R19 (SEL-029) passes the
     receipt as `pass (superseded)` only if a carried release holds every row it lists. That ruling was made for
     exactly c923eb5a's release `7b72aaa89fe005d3`.
   - A refusal would stop library search between stage 15 and the seal. For factory-kg that window is hours (SQ-156:
     a 7.31 h dense pass).
   - What the seal adds is that the release's gates passed. The person writing the receipt should know when that is
     missing, so it is shown loudly (CLAUDE.md section 4: never silently). The arm now:
     - carries `release_sealed` on `Library.search`'s result, on each graph in `run_search` (CLI and MCP
       `seldon_prior_art_search`) and on the first graph's top-level fields, and in the `prior_art` log line;
     - prints `, NOT SEALED` on the graph line and a stderr warning when the value is `false`;
     - stays quiet for `true` and for `null`. squiddy uses `null` for a ledger that seals nothing. A squiddy from
       before SQ-156 reports nothing, which also reads as `null`: the arm says nothing it was not told.
   The receipt line's grammar is unchanged, so every note's receipts parse as before.
   Prior art: this is TUF's rule (clients act only on signed metadata) and Maven's staging repository (staged artifacts
   are not a release). Those apply when the unsigned bytes could be tampered with. Here the receipt pins the bytes by
   content hash, so the remaining gap is a quality attestation, not integrity. Surfacing it rather than gating on it is
   a deliberate departure, and the reason is above. If a later case shows an unsealed citation doing harm, refusing is
   a one-line change at the `is False` check in `seldon/commands/prior_art.py`.
2. **`c923eb5a`'s stronger form** (build beside the served index and swap at the seal) is squiddy's to build. SQ-156
   names it and does not build it. Nothing in seldon waits on it.
3. **`45b88039`, both questions: nothing to apply in seldon.** The kit now builds a cited-sources graph (catalog,
   OpenAlex and Crossref resolution, robots.txt, archive root, SQ-150's union catalog, SQ-151's coarse tier).
   `squiddy passage promote --pages A-B` promotes a passage from its cited pages only (R-319). SEL-056 already put
   seldon-biblio on the coarse tier with `Passage` and `PassageOf` declared. A promotion is made when a citation asks
   for one, and no ruling asks yet. When one does, the command, from seldon's root, is:
   `/Users/brock/GitHub/squiddy/.venv/bin/squiddy passage promote --graph graphs/seldon-biblio --id <entry> --pages A-B --exact "<quote>" --for "<the citation>" --by <who>`.

## What was applied

| What | Where |
|---|---|
| `release_sealed` read from squiddy's `index` and carried on the result | `seldon/core/prior_art.py` `Library.search` |
| carried per graph, at the top level, and in the `prior_art` log line; `NOT SEALED` on the graph line and a stderr warning when `false` | `seldon/commands/prior_art.py` `run_search`, `search_command` |
| red-first tests (5 of 7 failed before the change) | `tests/test_sel064_release_sealed.py` |

## Verification

- `tests/test_sel064_release_sealed.py`: 7 passed. Before the code change, 5 failed: the three `release_sealed`
  values, the pre-SQ-156 `None` case, and the CLI flag. The two quiet-CLI cases passed both before and after.
- Every test file that names prior-art (36 files, `-n 6`): **494 passed, 1 skipped**, 480 s.
- Live, read-only (`/tmp/sel064_live.py`, `Library.search` on the primary's `graphs/seldon-biblio` through the
  installed squiddy, with no log line written): release `seldon_biblio_graph_20261111_sel037_2026-11-11.json`,
  sha256 `076422bb8382…`, **`release_sealed: True`**, 35 rows.
- The full suite was not run here (it takes about 61 to 82 minutes). The dispatcher's gate runs it before the merge.

## What was not applied

- No refusal on `release_sealed: false` (decision 1).
- No passage promoted, and no release cut (decision 3).
- Filings `c923eb5a` and `45b88039` are already `completed` in squiddy's graph, according to the SQ-156 RESULT's
  "Returns filed". This task closes nothing more.
