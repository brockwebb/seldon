# AD-036 ADDENDUM 11: a receipt against a release the library no longer carries verifies against one it does, and the verdict ledger commits beside the note whose verdict it carries

**Date:** 2026-11-08. **Status:** Accepted. Implemented by SEL-029
(`cc_tasks/2026-11-08_SEL-029_three_consumer_filings_answered_a_superseded_library_release_verifies_the_verdict_ledger_commits_beside_its_note_and_an_addendum_cannot_carry_spend.md`),
answering hazbrief-mcp's filings SEL-028 (`771032cd`) and SEL-026 (`9f0c7e1b`). **Amends:** AD-036 ADDENDUM 06 (a
receipt naming a release that cannot be rebuilt no longer fails on that alone); DESK-002's register exception gains a
sibling for the verdict ledger. AD-036-R4 is unchanged: the gate reads the staged ledger only. Two new rulings.
**Code:** `seldon/core/prior_art.py` (`SUPERSEDED`, `Library.served_rows`, `register_releases`, `release_rows`,
`resolve_superseded`, `release_row_ids`, `register_rows`, `_resolve_superseded`; `rebuild_release` now shares its
steps 1 and 2 with `release_row_ids` through `_release_rows`); `seldon/core/desktop_commit.py` (`_ledger_rel`,
`_ledger_refusal`). **Tests:** `tests/test_sel029_superseded_release.py`,
`tests/test_sel029_ledger_and_addendum_commit.py`.

## 1. Evidence

1. **SEL-028.** hazbrief-mcp's DN-019 (2026-11-04) carries a library receipt against
   `library_graph_20261105_sq114_a_2026-11-05.json`, sha256 `7b72aaa89fe005d3...`. On 2026-11-08 verify returned FAIL
   for it, `release_unavailable: ... no commit of .../EXPORT_VERSIONS.md carries 7b72aaa89fe005d3` (hazbrief-mcp
   verdict `ea01ac75ed6043c8b8a2324d66d0f413`), and every note older than the current release fails the same way when
   touched.
2. **The register never carried that release; it did not drop it.** `git log -S'7b72aaa89fe005d3' --all --
   graphs/library/exports/EXPORT_VERSIONS.md` in squiddy finds no commit, and `-G'sq114_a'` finds only `a8f2266c`
   (2026-11-06 21:14, the `20261105_sq114_a.r1` row, sha `79e52df405ff4536`). The export `7b72...` is on disk under
   both `..._2026-11-05.json` and `..._2026-11-06.json`. SQ-114 (2026-11-05) wrote that export and halted at stage 15
   `conformance`; SQ-114R rebuilt the served index over it (stage 15 `index`: pass) and halted at `index-parity`, so
   stages 16 to 18 (`registers`, `seal`) never ran: "No line was appended to `EXPORT_VERSIONS.md`" (squiddy
   `cc_tasks/2026-11-05_SQ-114R_..._RESULT.md`). The served index carried release `7b72...` from then until
   `20261106_sq125_c` was sealed, and DN-019's search ran against it. The defect is squiddy's: its index stage serves a
   release before the seal registers it. That is filed into squiddy; this addendum does not depend on it, because a
   register that keeps every release is not something verify may assume.
3. **Every row DN-019's receipt lists is in the current release.** All 45 row ids are rows of the served index's
   database (`graphs/library/work/index/corpus.db`, release `20261106_sq125_c`, sha256 `bbd841d3...`), measured
   2026-11-08. With this addendum's code, `verify_note` on DN-019 and its ADDENDUM-01 returns PASS, the base receipt
   `pass (superseded)` against `library_graph_20261106_sq125_c_2026-11-06.json` (nothing recorded; the measurement
   script `/tmp/sel029/live_dn019.py` turns the query log off).
4. **SEL-026.** The commit gate's refusal of DN-022 ended "then stage the verdict ledger state/prior_art_verdicts.jsonl
   with the note"; `seldon_commit_governed(paths=[note, "state/prior_art_verdicts.jsonl"])` returned `REFUSED
   outside_roots`. hazbrief-mcp committed DN-022 by hand.

## 2. Prior art

- **Memento (RFC 7089, Van de Sompel, Nelson and Sanderson, 2013).** A request for a resource as it was at a time the
  server no longer holds exactly is answered by a TimeGate with the nearest version it does hold, and the response
  names that version (`Memento-Datetime`). Adopted: a receipt whose release cannot be rebuilt is checked against a
  release the library carries, and the verdict line names the release it was checked against
  (`verified_against`). Departure: Memento negotiates on time; this resolves on content, because the claim a receipt
  makes is "these rows exist", and a row id is content-derived.
- **Version navigation link relations (RFC 5829, 2010):** `predecessor-version`, `successor-version`,
  `latest-version`. Adopted as the order of resolution: the served (latest) release first, then the register's
  releases newest first. The receipt is not rewritten to point at its successor (RFC 5829 relations are carried by the
  link, not by editing the older resource); the ledger carries the resolution.
- **Content-derived identifiers.** squiddy's index rule `sq028r-index/3` builds a row id as
  `<doc id>#<pointer into the document's text>` (`squiddy/index.py`: `f"{doc_id}#{pdftext.pointer(...)}"`, and
  `#meta` for a metadata row). Nothing in it names a release, so ids are compared whole: an equal id in another release
  names the same passage, and a moved passage is a different id (the SEL-029 task's "release-specific suffix" does not
  exist in the rule; this is recorded rather than invented).
- **Attestation travels with its artifact (in-toto, Sigstore bundles).** A signature or provenance statement is
  shipped beside the artifact it attests, and a verifier reads the bundle, not a side store. Adopted for R20: the
  staged ledger is the proof the gate reads, so the tool that commits the note commits the proof with it.
- **Internal:** AD-036 ADDENDUM 06 (a receipt names the release it ran against; rebuild from the kit's checkpoints);
  DESK-002 (a register record commits only beside the note whose label it answers); HOOK-001 (the gate judges the
  STAGED ledger); `prior_art.addenda_of` (a note's addenda are verified with it).

The external sources are cited by their published names and were not fetched: the task's Network header allows
nothing beyond git. The internal search was this repository's record (the recall hits DESK-001, SEL-006, HOOK-002,
SEL-023 and AD-036-R13) and squiddy's register history and SQ-114 RESULTs, read directly.

## 3. Rulings

- **AD-036-R19. A library receipt whose named release cannot be rebuilt passes as `pass (superseded)` when a release the library still carries holds every row it lists, and the verdict names that release.**
  Resolution runs only after `search_release` fails, against the served release first and then up to
  `prior_art.library.superseded_releases` register releases (default 3), newest first; row ids are compared whole.
  The receipt in the note is not rewritten; the verdict's receipt carries `verified_against: {release, sha256}`. When
  no carried release holds the rows it stays `release_unavailable`, and the detail names the rows the current release
  lacks. A receipt that found nothing (`rows none`) is never resolved this way.
- **AD-036-R20. The verdict ledger commits through the Desktop commit tool beside a design note or addendum whose current bytes have a verdict in it, and the gate does not read a verdict from an unstaged ledger.**
  `seldon_commit_governed` and `seldon commit-governed` accept `prior_art.verdict_ledger` (the governed ledger, or
  `gate.verdict_ledger_without_governed`) in such a call; alone, or beside files it holds no verdict for, it refuses
  `outside_roots`. The message stays `desktop: design: <basename>`. AD-036-R4's gate keeps reading the staged ledger
  only: a verdict read from disk would admit a commit that does not hold its own proof, and the tool now stages it.

## 4. Details

1. **Why the bound on register releases.** Each register release besides the served one costs a pass over the
   library's corpus checkpoint (0.6 GB on 2026-11-08) to list its rows. Three covers more than the releases cut in one
   working day (two on 2026-11-06); `0` restricts resolution to the served release. A release whose export is gone or does
   not hash to its register row is skipped and named under "not checked".
2. **SEL-028's other two questions.** A FAIL on a base note's receipt does fail a verification that includes a new
   addendum, because `verify_note` judges a note and its addenda together (`prior_art.addenda_of`); R19 removes the
   cause rather than splitting the judgment. The commit gate admitted the addendum after the FAIL because addenda are exempt from the gate
   (`prior_art.gate.exempt_globs` in seldon.yaml: "addenda and errata complete or correct a note and are verified WITH
   it, so they are not gated alone"): an addendum commit never consults a verdict.
3. **`TOOL_VERSION` stays `prior-art/1`.** The served-search path, its ranking and its matching are unchanged; R19
   adds a resolution for receipts that previously could not be judged at all, as ADDENDUM 06 and R14 did without a
   bump.
