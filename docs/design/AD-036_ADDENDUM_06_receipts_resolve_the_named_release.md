# AD-036 ADDENDUM 06: a library receipt is re-run against the release it names

**Date:** 2026-10-20. **Task:** PA-002 (`cc_tasks/2026-10-19_PA-002_receipts_verify_against_the_release_they_name.md`).
**Amends:** nothing. This restores what AD-036-R2 and R3 already say: a receipt is re-run against the corpus identity it
names, and only an identity that can no longer be loaded fails as `release_unavailable`. No new ruling. The mechanism
is `seldon/core/prior_art.py` (`Library.search_release`, `rebuild_release`, `open_rebuilt`, `release_commit`,
`corpus_anchor`, `_verify_library`). Tests: `tests/test_pa002_release_resolve.py`.

## 1. The defect, measured

On 2026-10-19 `seldon prior-art verify docs/design/AD-036_prior_art_receipts_gate.md` returned FAIL with seven
`release_unavailable` findings (verdict `3ab498a4`, governed ledger). Each library receipt named
`library_graph_20260930_m002` or `library_graph_20261012_sq013_01`. Both exports were still in
`squiddy/graphs/library/exports/`. The verifier compared each receipt only with the release the index served,
`library_graph_20261017_sq018_02`, which SQ-018R cut on 2026-10-17. So every design note with a library receipt
written before that release failed, and AD-036 ADDENDUM 05's gate held every task those notes govern (STD-001 on
2026-10-19).

A second defect hid the first from a dispatched session. Relative corpus paths (`../squiddy`, the library graph)
resolved against the checkout, and a dispatched session's checkout is a worktree under
`<primary>/.claude/worktrees/<name>`. There, `../squiddy` names `.claude/worktrees/squiddy`, which does not exist. MCP-001's RESULT
recorded the symptom on 2026-10-17: `prior-art verify` failed from any worktree on every sibling receipt.

## 2. The resolver rule

1. **The served release keeps today's path.** A receipt whose sha256 is the served index's is judged on the served
   search, exactly as before.
2. **Any other release is looked up on disk.** The receipt names an export file and its sha256. The verifier looks for
   `<library exports_dir>/<release>`. A release name that carries a path is refused. If the file is absent, or its bytes
   do not hash to the named sha256, the receipt is `release_unavailable` and the finding names the path it looked for.
   This is the only way a receipt still gets that status.
3. **A release on disk is rebuilt, not approximated.** The served index is rebuilt in place at every release, so an
   older release's index survives only as its inputs. The kit keeps every one of those inputs:
   - the **corpus manifest** is read from the first commit of the library's repository whose `EXPORT_VERSIONS.md` row
     carries the release's digest (`release_commit`);
   - the **rows** come from the index's corpus checkpoint, which never drops a (unit, content sha256, rule) line
     (`squiddy.index.iter_rows`; a unit it lacks is a refusal);
   - the **database** is built by the kit's own `build_db` in a temporary directory;
   - the **vectors** come from the dense shard log, which never deletes a shard. For each entry, the verifier takes
     the shard keyed under the key the kit computes from that entry's rows at that release, whether live or retired.
     Its bytes and row ids are checked as the kit checks them.

   The rebuilt index is queried through the kit's own `Index`, so it runs the same query path as the served one. The
   query-time `index:` block must equal the block at the release's commit; if it does not, the rebuild refuses rather
   than rank under parameters the receipt never ran with. Nothing is encoded, so no model call is made.
4. **The rule is top-k membership, as before.** A rebuilt release passes a receipt only when every cited row is in its
   top `library.k` (20). That is R2's rule and R5's "top 20". The task's cheaper alternative was to check membership in
   the release's whole row set. That would pass any row the release holds, whatever the query, so it does not honour
   the top-20 rule. It was rejected.
5. **The query log names the release each verification ran against.** Each line carries `release`, `sha256`, `index`
   (`served` or `rebuilt`), and for a rebuild the `export_path` and the `commit` the manifest came from.
6. **Corpus paths anchor at the primary checkout.** When the file defining the `prior_art:` block lies in a linked
   worktree, relative corpus paths resolve against the same directory in the primary checkout (`corpus_anchor`). The
   project's own state (the query log, the verdict ledger) stays in the worktree. A worktree shares the primary's object
   store, so every commit a receipt names is readable from either.

**Evidence that the rebuild reproduces the instrument.** Run on the release the index serves, the older-release path
produces the served index's `row_fingerprint` and dense `shard_set_sha256` exactly (`7a774aec…`, 416,365 rows;
`test_rebuilding_the_served_release_reproduces_the_served_index`). The manifest that `release_commit` finds for
`20261017_sq018_02` (commit `edd5d5d6`) hashes to the `manifest.sha256` the served index manifest records (`9eba9c8a…`).
The `index:` block is identical at all four release commits named in section 4.

## 3. Why not the alternatives

- **Accept a receipt on its recorded verdict and never re-run it.** R2 says "verified by re-running them, not by
  trusting a log". The verdict recorded at commit stays the record (R4). The gate re-verifies because a note's bytes
  or addenda change.
- **Keep one built index per release.** That means about 1.4 GB of database and vectors per release (230 MB
  `corpus.db` plus 1.2 GB of shards today), kept against a reader who may never come. The checkpoints already hold
  every input. The rebuild reuses the vectors and builds only the database. Each 2026-10-20 run above (section 4) took 1.4 to
  4.5 minutes per note, with one outlier at 20 minutes (DN-043). The machine load average was near 44, and the times
  include loading the served index and the encoder.
- **Re-cite every old note against the newest release.** That is an edit of the note, or an addendum per note, for
  every release, and it would rewrite what the author actually searched.

## 4. Notes re-verified on 2026-10-20

Every design note in seldon and squiddy that carries a `library receipt:` line was re-verified. An addendum is verified
with its base note. The verdicts are recorded in each repository's governed ledger.

| Repository | Note (with its addenda) | Library receipts, by release | Verdict |
|---|---|---|---|
| seldon | AD-035 | m002 (2), sq013_01 (1) | PASS, event `b087610c` |
| seldon | AD-036 (ADDENDA 01 to 05) | m002 (6), sq013_01 (1) | PASS, event `9e516a51` |
| seldon | AD-037 | m002 (8) | PASS, event `b6718fc1` |
| seldon | AD-038 | sq013_01 (2) | PASS, event `a11e3d5e` |
| squiddy | DN-043 (ADDENDUM 02) | m002 (4) | PASS, event `fe1af92d` |
| squiddy | DN-044 | m002 (8) | PASS, event `ea2c3bd4` |
| squiddy | DN-045 (ADDENDUM 01) | sq011_11 (5) | PASS, event `9487ac69` |
| squiddy | DN-046 | sq013_01 (2) | PASS, event `ec836541` |
| squiddy | DN-047 | sq013_01 (1) | PASS, event `25251791` |
| squiddy | DN-048 | sq013_01 (1) | PASS, event `c729ab4d` |

No receipt named the served release, so every receipt ran on a rebuilt index. The rebuilds used these library commits:
`20260930_m002` from `c40f79cc`, `20261012_sq011_11` from `12bd2fda`, and `20261012_sq013_01` from `a34b25cf`. The query logs
(`state/prior_art_queries.jsonl` in each repository) record each run's release, index and commit. No note still fails.
The verifications ran from this task's worktree, which also exercises section 2 rule 6.

## 5. Prior art

### External

- The rule is R2's own prior art, reproducible builds: a second party re-derives an artifact from its declared inputs.
  Here the artifact is a release's index and the inputs are the manifest at the recording commit plus the kit's
  content-keyed checkpoints. The library returned no source on reproducible builds as such. Its nearest rows are
  OpenHands' runtime images (arXiv 2407.16741): the image is looked up by an exact hash of its inputs, and when no
  image matches, "the system will try to rebuild using the latest generic image". That is the same shape as this rule: an index keyed by inputs, and a
  rebuild that reuses keyed parts. Network was out of scope for PA-002, so no web source was fetched.
- library receipt: query "reproducible build rebuild an artifact from recorded inputs and checksums" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-22_arXiv_2407_16741#p21:370:2688-2892, lesson:2026-02-22_arXiv_2407_16741#p22:374:224-608

### Internal

- AD-036-R2 is the rule this restores: re-run "against the named release", `release_unavailable` only for a release
  that is "no longer loadable". The decision register holds R2's acceptance (`00223`). Searches in squiddy,
  ai-readiness-kg, arnold, icsp_notebook, wintermute and the workbench audit found no rebuild rule and no other
  treatment of an unavailable release.
- internal receipt: query "release_unavailable rebuild" | repo seldon@0849d1b05da2391c686f303b76426f7c7cef563d | hits docs/design/AD-036_prior_art_receipts_gate.md:80, docs/decisions/register/00223_seldon-ad-036-r2_accept.yaml:1
- internal receipt: query "release_unavailable rebuild" | repo squiddy@15a1a1e9bfe93d0edcb99d5ff5bfc39ebe7d9e8e | hits none
- internal receipt: query "release_unavailable rebuild" | repo ai-readiness-kg@788400fd7046eafb6e7855e7867e389f2c4bf45b | hits none
- internal receipt: query "release_unavailable rebuild" | repo arnold@f089fc8c79403a5371c823c6c3f2aec30fa90e57 | hits none
- internal receipt: query "release_unavailable rebuild" | repo icsp_notebook@ccfb76201f842fb968e7abc1a513d5d1aefdb405 | hits none
- internal receipt: query "release_unavailable rebuild" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "release_unavailable rebuild" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "reproducible builds second party re-derives" | repo seldon@0849d1b05da2391c686f303b76426f7c7cef563d | hits docs/design/AD-036_prior_art_receipts_gate.md:80
- The worktree half (rule 6) was first recorded in `cc_tasks/2026-10-17_MCP-001_every_mcp_tool_runs_the_checkout_in_a_fresh_process_RESULT.md`,
  line 8. `seldon/core/worktree.py` (`primary_checkout`) resolves the primary checkout the same way for the spend
  ledger (AD-034 decision 5).
