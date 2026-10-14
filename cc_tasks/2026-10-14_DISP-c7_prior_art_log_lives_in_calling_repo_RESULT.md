# DISP-c7 RESULT: the prior-art query log is the calling repo's, and every automatic writer commits what it writes

**Date:** 2026-10-14. **Task:** defca7cc, dispatched; Claude Opus 5.5. No addenda. Branch `fix/disp-c7` (f7d4b1d, d98e8d6, 488a9bb) was merged as 9641887; registrations are 4dd6cb9. Rulings: `docs/design/AD-036_ADDENDUM_04_query_log_in_the_calling_repo.md`, R10 to R12, with register records 00281 to 00283 accepted. Resolves Issue 7e70aeb0.

**Premises found wrong (ADDENDUM 04 §1).**
1. The log already resolved to the calling repo, since ADDENDUM 03. Foreign lines came from two places: searches run with seldon as the working directory, and the MCP tools, whose `"."` means `SELDON_DEFAULT_PROJECT` (seldon). The defect everywhere was that nothing committed the log.
2. The verifier never reads the log. It re-runs the note's receipts.
3. The refresh already put the lock and its evidence in one commit. On 2026-10-12 it refused to commit because the checkout was on `feat/SQ-010-repin` (reflog), which left both files dirty.
4. The two filings were already tracked (3535216); they were only unregistered. No filing helper exists, so the rule went into CLAUDE.md.

**Built.**
- Calling-project resolution, in order: `--project`, else the note's repo, else the project at or above the working directory. It applies to the CLI and MCP search and verify. Every log line now carries `project`.
- `commit_appends`: a path-scoped commit through the hooks, made only for files that were clean before the run and only for append-only lines. It defers while another session holds the lease; the dispatcher's pass then sweeps the leftovers.
- The refresh checks the branch before any probe. Off the branch it returns `skipped`: nothing is written and nothing is spent.
- Hit paths are percent-encoded for `%`, `,` and whitespace.
- `cc register --project`.
- New tests: `tests/test_prior_art_caller.py` (16) and two refresh tests in `tests/test_models.py` (fake runner).

**Migration of seldon's log (step 1).** The log had 413 lines: 410, plus 3 of this task's own searches. Each line was attributed by the receipt it supports (`docs/evidence/disp_c7/migration.json`):
- 325 are seldon's and stay.
- 46 moved to squiddy (44bcf75) and 1 to ai-readiness-kg (078e6f0d).
- 41 are unattributable (no pasted receipt anywhere, e.g. SQ-013's `LinkML` check) and stay.
- None was ambiguous.

No receipt in 15 repos contains `%`, so the encoding leaves every existing receipt unchanged.

**Verdicts (step 2).** `scripts/disp_c7/verdict_table.py` covered 42 notes with receipts in seldon, squiddy, ai-readiness-kg, arnold and icsp_notebook. Its log went to a temp file. The table was run before the change on old code and after the merge and migration on new code. Before and after are identical: sha256 `afc65f512c92d5d82fefc3f41c458ad5121b60b35d1bac5df814c8198fb788a8` for both. 40 of the 42 notes fail in both runs, for reasons that predate this task: 33 library receipts name releases the index no longer serves, 1 is `id_not_returned`, and some notes have empty subsections.

**Refresh (step 3).** On the branch, a refresh makes one commit holding the lock and its evidence (and the event when the lock bumps). Off the branch it returns `skipped`, makes 0 CLI or npm calls and leaves the tree clean. An "evidence alone" case never arises: a recheck on a later day rewrites `resolved_on`, so the lock always changes along with its evidence.

**Hit path with spaces (step 4).** A receipt for `AI Readiness  A Comprehensive Review.md` now round-trips through search and verify and passes. The unencoded form is still `malformed`, and that is the control test.

**Registered (step 5).** Both filings are now `proposed` and were not run:
- ef334553: the DesignNote-cites filing.
- 6174165c: its slosh-pipe addendum, registered as its own task. Its date prefix keeps the dispatcher's addendum glob from reading it as the parent's addendum.

They are ordered ef334553 → 6174165c. To pass registration (`criterion_unmarked`, `parts_undeclared`), each file got header lines and marked criteria, labelled in the file. Nothing else in them changed.

**Gate.**
- check suite (main, detached): 2463 passed, 0 skipped, 0 xfailed, 0 deselected, 0 failed (902 s). The worktree run before the merge gave the same 2463.
- check porcelain after one search from each repo (`/tmp/dispc7/gate_porcelain.txt`):
  - seldon `` → `` (2bd2666); squiddy `` → `` (9f5321e); icsp_notebook unchanged, commit ccfb762.
  - ai-readiness-kg was dirty before and after on paths this task did not touch (` M seldon_events.jsonl`, two `??` files from another session). Its search committed as 2f7dab2b.
  - arnold was ` M cc_tasks/2026-10-08_per-exercise-measurement-schema.md` before and after. It ignores `*.jsonl` (`.gitignore:188`), so its log is untracked by its own rule.
  - icsp_notebook has two `??` cc_tasks that were there before.
- check `seldon dispatch status`: `dirty=False` on all three passes, with a squiddy library search committed between each (8bd154f, b1929ff, 4bbbf40).
- check `seldon verify`: all checks passed. This came after two governed re-admissions, releases 20261014_dispc7, dispc7b and dispc7c, and `governed sync` (2 documents updated).

**Open (Issue 6bb0904e, high/high).** The ledger, the served export and the graph agreed. Even so, squiddy's drift gate reported both re-admissions as abandoned, and every `--resume-abandoned` failed at 05: the resumed admission excludes its own events from the replay, while a separate release had already exported them.

- **KLUDGE:** I moved the two admission leases aside to `docs/evidence/disp_c7/moved_leases/`, with copies of their admission logs. Each entry is now `in_graph` with no lease, so squiddy judges it by ledger evidence (DN-046 R-202). That is the state the merge left AD-036 ADDENDUM 04 in, and drift is CLEAN.
- The Issue stays open for squiddy to decide how a release that exports an admission's write should close that admission.
- Also noted: each search or verify is now one commit in its repo's history.
