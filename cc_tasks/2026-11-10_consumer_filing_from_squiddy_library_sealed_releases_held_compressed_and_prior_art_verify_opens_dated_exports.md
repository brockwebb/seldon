# Consumer filing from squiddy: library's sealed releases older than the diff base are now held compressed, and prior-art verify opens dated exports directly

**Repo:** seldon. **Date:** 2026-11-10. **Authored by:** squiddy SQ-134's dispatched session (worktree `twinkling-meandering-nova`), filed under AD-036-R12 as a report of what changed in a directory seldon reads. No candidacy headers, not a dispatcher candidate. This filing proposes no fix; the seldon thread decides what, if anything, changes.
**Evidence:** squiddy `docs/design/2026-11-10_DN-059_sealed_releases_older_than_the_diff_base_are_held_compressed.md` (ruling squiddy:R-253), `squiddy/exports.py`, `graphs/library/config.yaml` `engine.export.hold`; the hold record `graphs/library/exports/compressed.jsonl` (gitignored, primary checkout), summarised in squiddy `docs/evidence/sq134/hold_counts.json`.
**Kind:** filing
**Filed by:** squiddy

## What changed in `squiddy/graphs/library/exports/`

1. **The layout.** 33 sealed releases (99 files, 12.01 GB) are now held as `<name>.gz` beside where they were: `library_graph_<v>_<date>.json.gz`, `_nodes.jsonl.gz`, `_edges.jsonl.gz`. The plain file is gone; the `.gz` carries the original's modification time. Each file has one `held` line in `exports/compressed.jsonl`: `file`, `gz`, `release`, `sha256` and `bytes` of the ORIGINAL, `register_sha16` for the `.json`, written only after the gzip round trip was verified against that sha256 (and the `.json` against its register row). Nothing was deleted whose bytes are not recoverable.
2. **What stays plain** (DN-059 R-253 item 2, and these nine releases on this host): the served `library_graph.json`; the newest register row `20261106_sq125_c` (also the next diff's base) and the previous row `20261105_sq114_a.r1`; the newest five register rows (`keep_newest_sealed: 5`, chosen to cover prior-art verify's window: the served release plus `superseded_releases: 3`, plus the receipt's own release it excludes); every release a seldon library receipt names, counted over every repository's `cc_tasks/`, `docs/` and `handoffs/` on 2026-11-10 (`20260930_m002`, `20261012_sq011_11`, `20261012_sq013_01`, `20261017_sq018_02`, plus the ones above); and every dated export with no register row, untouched (`20261012_sq011_01`, and the `20261105_sq114_a` pair your filing of 2026-11-08 asks about).
3. **The accessor's contract.** `squiddy.exports` reads a dated export by its PLAIN path whether it is plain or held: `read_bytes`, `read_text`, `sha256` (of the original bytes), `size` (original), `exists`, `mtime`, `dated(dir, glob)` (plain names of plain or held files). A held read decompresses and verifies the recorded sha256 and size; a mismatch raises `HeldExportError` (a `SystemExit`). `squiddy exports restore <version> --graph G` writes a release's plain files back, each verified before its `.gz` is removed. `squiddy.export.load_exported` goes through it.
4. **Going forward.** `squiddy release` runs stage 18 `hold` after `seal`, so each new release can move one more older release out of the plain set.

## Where seldon reads these files directly (read-only, 2026-11-10)

- `seldon/core/prior_art.py` `Library.search_release` and `Library.export_path`: a receipt's `release` is a file NAME opened with `path.is_file()` and hashed with `_sha_file`. A receipt naming a held release now reads `release_unavailable: ... is not on disk`. Every release a receipt names today is plain, so no current receipt changes outcome.
- `Library.release_rows` (AD-036-R19, `resolve_superseded`): the newest `superseded_releases` register releases besides the served one, opened the same way. All five newest rows are plain.
- A receipt written later against a release that later leaves the plain set would hit the first case. `graphs/library/config.yaml` `engine.export.hold.keep_plain` is where squiddy declares a release a reader outside the kit opens by name.

## What the consumer wants to know back

Whether seldon wants to read a held release through `squiddy.exports` (it already imports squiddy in-process for the library arm) or wants squiddy to keep every receipt-named release plain by declaration, as now. Return path per AD-036-R16: a task file in `/Users/brock/GitHub/squiddy/cc_tasks/` only if squiddy has something to do.
