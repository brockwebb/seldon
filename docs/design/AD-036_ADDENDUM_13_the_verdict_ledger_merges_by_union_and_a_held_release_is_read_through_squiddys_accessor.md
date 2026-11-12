# AD-036 ADDENDUM 13: the verdict ledger merges by union wherever the query log does, and a held library release is read through squiddy's accessor

**Date:** 2026-11-12. **Status:** Accepted. Implemented by SEL-038
(`cc_tasks/2026-11-11_SEL-038_a_system_written_journal_never_blocks_a_merge_and_a_held_library_release_is_read_through_squiddys_accessor.md`,
Parts D and E), answering hazbrief-mcp's filing
`cc_tasks/2026-11-11_state_prior_art_verdicts_jsonl_conflicts_on_the_dispatchers_rebase_when_main_and_a_branch_each_append_a_verdict.md`
(task `6d607cb9`) and squiddy's filing
`cc_tasks/2026-11-10_consumer_filing_from_squiddy_library_sealed_releases_held_compressed_and_prior_art_verify_opens_dated_exports.md`.
**Amends:** AD-036-R4 (the verdict ledger) as AD-034 ADDENDUM 05 declared the query log; AD-036-R2, R19 and ADDENDUM
06 (how the library arm opens a release a receipt names). **Applies:** squiddy DN-059 R-253 (squiddy's rule; seldon
reads it, it does not restate it). Two new rulings, AD-036-R23 and R24.
**Code:** `seldon/core/hooks.py` (`append_only_paths`); `seldon/core/prior_art.py` (`_exports_accessor`,
`Library._export_exists`, `Library._digest`, `search_release`, `release_rows`).
**Tests:** `tests/test_sel038_journals_and_held_releases.py`.

## 1. Evidence

1. **The verdict ledger conflicted on a rebase.** hazbrief HB-166, landing HB-155's branch by hand, conflicted twice in
   `state/prior_art_verdicts.jsonl`: main had appended one verdict (HB-164's) and the branch two. hazbrief's
   `.gitattributes`, written by `seldon hooks install`, declared `seldon_events.jsonl` and
   `state/prior_art_queries.jsonl` `merge=union` and not the verdict ledger. Every writer of the ledger appends one
   `prior-art verify` record; the ledger is append-only by use. hazbrief has stopped running prior-art searches in its
   primary while a task is in flight until this is answered.
2. **Which projects carry the exposure** (`docs/evidence/sel038/verdict_ledger_survey.txt`, read 2026-11-12). A project
   with a governed graph records verdicts in its governed ledger (`prior_art.verdict_ledger`), which ATTR-001 (AD-034
   ADDENDUM 05) already declares: seldon, squiddy and arnold, none exposed. A project without one records them at
   `gate.verdict_ledger_without_governed`: hazbrief-mcp and ai-readiness-kg, both at `state/prior_art_verdicts.jsonl`,
   both undeclared.
3. **squiddy now holds sealed releases compressed.** squiddy DN-059 R-253 (SQ-134) holds 33 sealed releases older than
   the diff base as `<name>.gz` beside where they were, with the original's sha256 and size in `compressed.jsonl`.
   `Library.search_release` and `Library.release_rows` opened a release by its plain name (`path.is_file()`), so a
   receipt naming a held release would read `release_unavailable`. No current receipt is affected (squiddy keeps every
   receipt-named release plain); the next old one would be. On 2026-11-12 the held files are on disk in squiddy's
   primary while `squiddy/exports.py` is on SQ-134's branch only (commit `9a54c9e5`), not on squiddy main.

## 2. Prior art

### External

- **git's union merge driver** (`gitattributes(5)`), as AD-034 ADDENDUM 09 cites it: the merge for an append-only
  JSONL journal. The verdict ledger is that kind of file, so it gets what the query log already has. Cited by its
  published name; not fetched (Network: none).
- **squiddy DN-059 R-253 item 3** (squiddy's filing, quoted): "`squiddy.exports` reads a dated export by its PLAIN path
  whether it is plain or held: `read_bytes`, `read_text`, `sha256` (of the original bytes), `size` (original),
  `exists`, `mtime` ... A held read decompresses and verifies the recorded sha256 and size; a mismatch raises
  `HeldExportError` (a `SystemExit`)." Adopted: the kit's one reader of its exports is the reader, so seldon carries no
  second copy of the hold's format. Its own prior art (logrotate's `compress`, git's identity of an object as the hash
  of its uncompressed content) is why a held release is the same release: its sha256 is the original's.

### Internal

- internal receipt: query "union driver" | repo seldon@2de5bc6dc0ff37fa5d47f75749a0db41305c6989 | hits docs/design/AD-034_ADDENDUM_05_union_attribute_in_every_governed_repo.md:47, docs/design/AD-034_ADDENDUM_05_union_attribute_in_every_governed_repo.md:42, docs/design/AD-034_ADDENDUM_05_union_attribute_in_every_governed_repo.md:31
- internal receipt: query "held compressed" | repo squiddy@cbe87f388c2f72dde3f708f7b4f55738aec94216 | hits docs/H-009_delivery_report.md:165, docs/EXTRACTION_DESIGN_SPEC.md:344

## 3. Rulings

- **AD-036-R23. The prior-art verdict ledger merges by union wherever the query log does.**
  `seldon hooks install`, and the dispatcher's own declaration at every pass, declare the verdict ledger `merge=union`
  beside the query log: `gate.verdict_ledger_without_governed`, resolved against the project as the log is, read from
  the configuration and never a literal. A project with a governed graph records its verdicts in the governed ledger,
  which AD-034 ADDENDUM 05 already declares, so it has nothing further to declare. A block without the fallback key has
  no verdict ledger to declare. A rebase where main and a branch each appended a verdict completes with every line once,
  and the round's union check (AD-034-R7) reads the result.
- **AD-036-R24. The library arm opens a release a receipt names through `squiddy.exports`, plain or held.**
  Existence, the sha256 of the original bytes, and the size and modification time the digest cache keys on are read
  through the accessor, so a receipt naming a release squiddy holds compressed verifies exactly as a plain one does. A
  held file that does not decompress to its recorded bytes is `release_unavailable`, never a process exit. Where the
  squiddy installed in the interpreter predates the accessor, a held release is refused as held, naming the `.gz` and
  the missing accessor, never as "not on disk". seldon needs no `keep_plain` declaration from squiddy on its account.

## 4. What this does not change

Receipt grammar, verification outcomes and the superseded-release window (AD-036-R19) are unchanged: only how the
bytes of a named release are found and hashed. seldon does not read a release's bytes beyond its hash; a rebuild uses
the library's checkpoints, as ADDENDUM 06 rules.
