# AD-036 ADDENDUM 04: the query log is the calling repository's evidence, and automatic writers commit what they write

**Date:** 2026-10-14. **Task:** DISP-c7 (`cc_tasks/2026-10-14_DISP-c7_prior_art_log_lives_in_calling_repo.md`,
task `defca7cc`). **Resolves:** Issue `7e70aeb0`. **Amends:** AD-036-R3 ("a logged, deterministic tool") by saying
where the log is and who commits it. It adds R10 to R12. The dispatcher's c7 (clean tree) is DN-006's criterion
(ai-readiness-kg `docs/design/2026-09-15_DN-006_standing_dispatcher.md`, decision 2). DN-006 owns the criterion and
AD-036 owns the writer that kept breaking it, so the rulings are recorded here. The mechanism is
`seldon/core/prior_art.py` (`calling_project`, `commit_appends`), `seldon/commands/prior_art.py` (`--project`),
`seldon/models.py` (`refresh`) and `seldon/commands/cc.py` (`register --project`).

## 1. The condition, measured

Issue `7e70aeb0` records more than 300 dispatcher passes refused on c7. The task they blocked never touched
`state/prior_art_queries.jsonl`. The operator committed that file twice on 2026-10-13 (`13cb697`, `3535216`), and it
was dirty again within hours.

The task's premises, checked against the code and the history:

1. **"Every query, from any repo on the machine, goes to seldon's log": wrong as to mechanism.** Since ADDENDUM 03
   (2026-10-11), `settings()` resolves `log` against the project that uses the block. A search run with squiddy as
   its working directory already writes `squiddy/state/prior_art_queries.jsonl`. Foreign lines reached seldon's log
   by two other routes:
   - a search run with seldon as the working directory for another repository's note;
   - the MCP tools, whose `project_dir="."` resolves to `SELDON_DEFAULT_PROJECT`, which is seldon in the Desktop
     config. MODEL-002's RESULT names "Desktop sessions' queries".

   The defect common to every repository was a different one: **nothing committed the log**.
2. **"The verifier reads receipts from the calling repo's log": wrong.** `verify_note` reads receipts from the note
   and its addenda and re-runs them (R2: "verified by re-running them, not by trusting a log"). It only appends to
   the log. Moving the log cannot change a verdict, and the before/after table (section 3) measures that.
3. **"The lock refresh wrote evidence without committing it": true; the cause was the branch.** `refresh()` already
   commits the lock and the evidence in one path-scoped commit. On 2026-10-11 between 12:55 and 23:44 local time the
   main checkout was on `feat/SQ-010-repin` (reflog). The 02:41Z refresh wrote the lock and
   `refresh_2026-10-12.json`, refused to commit off `main`, and left both dirty. The 2026-10-13 refresh then
   overwrote the lock. No lock commit for 2026-10-12 exists.
4. **"The cross-repo filings are left untracked": no longer true.** Both are tracked since `3535216`, and neither is
   registered. Seldon also has no filing helper (`seldon cc --help`: complete, constrain, rederive-description,
   register).

## 2. Rulings

- **AD-036-R10. The prior-art query log lives in the repository that ran the search, beside the document the receipt supports.**
  - The calling repository is resolved in this order:
    1. `--project <dir>` (MCP: `project_dir`);
    2. the repository holding the note, for `verify` and for `search --note`;
    3. the nearest directory at or above the working directory that holds a `seldon.yaml`.
  - Seldon's own log holds only seldon's searches. Every line names its calling project (`project`).
  - Prior art: a test's fixtures and a build's lockfile live with the project that uses them. ADDENDUM 03 already
    resolves "the project's own state" against the referencing project.
- **AD-036-R11. An automatic writer commits what it writes, in the repository it writes to, with a path-scoped commit that runs the hooks.**
  - An automatic process that leaves a tracked file dirty is a defect.
  - The query log, and the verdict ledger `verify` appends to, are committed by the run that appended to them. The
    commit is `git commit -- <paths>` with no `--no-verify`, and only when the file's change is append-only against
    HEAD.
  - DN-006 ADDENDUM 04 says "a pass never commits without the lease". So while another session holds a dispatcher
    lease on the repository, the commit is deferred. The next pass that takes the lease commits the leftover lines
    before it reads the tree, as it already does for its own records.
  - The lock refresh checks, before any probe, that it can commit: a work tree on the configured branch. If it
    cannot, it writes nothing and the current lock stands. Where it does write, the lock and its evidence go in one
    commit.
- **AD-036-R12. A filing into another repository's `cc_tasks/` registers the file there, and the registration commits it.**
  - Use `seldon cc register --project <that repo> --allow-untracked <file>`. Registration commits an untracked task
    file by path (`_commit_registered_file`); without the flag the CLI refuses the untracked file before it gets there.
  - No filing helper exists to refuse an unregistered write, so the rule is written into the filing instructions in
    seldon's `CLAUDE.md`.

## 3. Evidence

`docs/evidence/disp_c7/`:

- `migration.json`: seldon's log split by the receipt each line supports.
- `verdicts_before.tsv`, `verdicts_after.tsv`: verdicts per document in every repository with a query log. Their
  sha256 values are in the RESULT.

## 4. Departures, stated

- **`TOOL_VERSION` stays `prior-art/1`.** It is "bumped when the matching, ranking, grammar or verdict rules change",
  and the fix to hit paths with spaces (the task's step 4) touches the grammar. The change is percent-encoding (RFC
  3986 section 2.1) of `%`, `,` and whitespace in a hit path, which the old grammar could not express at all.
  Decoding is the identity on every path that contains no `%`. No receipt in any gated repository contains one
  (`migration.json`, `percent_in_receipts`). So every receipt that parsed before parses to the same value now, and
  matching and ranking, which R5's recall control measures, are unchanged. A bump would require a new
  pre-registration for an instrument whose behaviour on every existing input is unchanged.
