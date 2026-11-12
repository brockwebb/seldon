# SEL-038 RESULT: every journal is committed before the fast-forward, a block names git's files, the verdict ledger is union, a held release reads through squiddy.exports

**Task:** `cefcfa29`. **Executed:** Claude Code, dispatched, worktree `calm-riding-melody` (branch
`worktree-calm-riding-melody`), 2026-11-12, on base `2de5bc6`. **Addenda:** none (globbed
`cc_tasks/2026-11-11_SEL-038_*_ADDENDUM*.md` before starting; no file). **Not done, per the launch instructions:**
merge, push, `seldon cc complete`. **Model calls:** none outside this session. **Network:** none.

Recall used: seldon:2026-10-23_ATTR-001_every_governed_repo_merges_its_append_only_logs_by_union_RESULT

(Its Outcome table says each consumer's `.gitattributes` commit is made by that repository's own dispatcher on its
first pass after the branch merges. That is why the hazbrief return below is a check, not a hand edit, and why
ai-readiness-kg gets no return of its own. The other seven hits were not read.)

## In plain terms

- A system-written journal left dirty in main no longer strands a finished branch. Before the fast-forward, under the
  lease, the merge round now commits the prior-art query log and the verdict ledger as well as the event store. HB-155's
  case, reproduced here, failed `ff_refused` before the fix and merges on attempt 1 after it, for both files.
- An `ff_refused` block names the files git named. A `rebase_conflict` with no unmerged-path list does the same.
- `seldon hooks install`, and every dispatcher pass, now declare the verdict ledger `merge=union` beside the query log.
- seldon reads a library release through `squiddy.exports`, so a receipt naming a release squiddy holds as `.gz`
  verifies. squiddy needs no `keep_plain` declaration on seldon's account.

## Premises

| premise | result |
|---|---|
| the first hazbrief filing is on main | holds |
| the second hazbrief filing is on main | holds |
| squiddy's filing is on main | holds |
| `test -f seldon/commands/dispatch_worktree.py` | holds |

## Commits (oldest first, after the prior-art log and verdict records)

| commit | what |
|---|---|
| `03ebbf6` | A: AD-034 ADDENDUM 09 (R19, R20), AD-036 ADDENDUM 13 (R23, R24), four pending register records |
| `ad08063` | B, C: `reconcile.JOURNAL_CLASSES`, `dispatch._record_journals`, the round's call, `worktree.files_named` |
| `ed67feb` | D: `hooks.append_only_paths` lists the verdict ledger |
| `12abd69` | E: `Library._export_exists` and `_digest` through `squiddy.exports` |
| `452b0f4` | tests and evidence |

## A. Rulings

- `seldon prior-art search --internal` with the task's terms, eight queries, each log line committed by the tool. Long
  queries got no hits under BM25 ("merge round fast-forward refused ...": none in seldon). The short terms gave the
  receipts the addenda carry: "union driver", "fast-forward", "reconcile class" and "held compressed".
- `prior-art verify` **PASS** on `docs/design/AD-034_worktree_per_task_dispatch.md` with ADDENDUM 09. The "fast-forward"
  and "reconcile class" receipts pass; "union driver" is a self-citation, since it hits AD-034 ADDENDUM 05. The verdict
  was recorded as `b96da4f0`, after the last edit to the addendum.
- `prior-art verify` **PASS** on `docs/design/AD-036_prior_art_receipts_gate.md` with ADDENDUM 13 (verdict `8676442f`).
- Both verdicts ran before the code commits.
- Register records: `seldon:AD-034-R19`, `R20`, `seldon:AD-036-R23`, `R24`. They are written to `pending/` because this
  is a linked worktree, and the merge numbers them (LOOP-001).
- The commit gate refused the first Part A commit: line 38 had a bold `AD-038-R1`
  (`ruling_label_unparsed`). It was un-bolded, then the AD-034 verdict and all four records were made again.

## B. The merge round

- **Reproduced first** (`docs/evidence/sel038/red_merge_round_before_fix.txt`, run on the base code). Setup:
  - one merge attempt;
  - the branch appends a line to the journal and commits it;
  - `primary_append` adds a `prior-art/1` line to main's copy during the run.

  Result for the query log and for the verdict ledger alike: `{'attempts': 1, 'files': [], 'reason': 'ff_refused',
  'stderr': 'error: Your local changes to the following files would be overwritten by merge: ...'}`.
- **Fix:**
  - `reconcile.JOURNAL_CLASSES = ("event_store", "prior_art")`.
  - `dispatch._record_journals` commits the event store through `_record_own_lines`, then each other journal class
    with the subject a pass gives it.
  - The round calls it under the lease in place of `_record_own_lines`.
  - Every file in those classes is `merge=union`, so the housekeeping test lets the round rebase over the commit
    without a re-gate.
- **After the fix:** both cases merge on attempt 1. main holds the base line and both appends, once each, and the tree
  is clean. The Desktop line went in as `reconcile: ... (prior_art, AD-038-R1)`.
- **Other reconcile classes, and why they are not committed before the fast-forward** (in AD-034-R19):
  - `decision_register`: its writer commits records with their rendering (DESK-002R), and a rendering is regenerated,
    never union-merged.
  - `cadence`: edits one seldon.yaml line in place.
  - `task_files`, `filing`, `hooks`: whole files a branch does not share with main's dirt.

  Committing any of these would turn a fast-forward into `main_kept_moving` and fix nothing.

## C. The Issue names the files

- `worktree.files_named` reads the tab-indented list under git's "following ... files would be ... by ...:" headings
  and the `CONFLICT (...): Merge conflict in <path>` lines.
- On HB-155's exact stderr it gives `["state/prior_art_queries.jsonl"]`.
- `ff_refused` records those paths. A `rebase_conflict` whose unmerged list is empty falls back to them, in the round
  and in `regate`.
- End to end: an untracked file in main at a path the branch adds gives `ff_refused` with `files: ["out/a/x.txt"]`, and
  the Issue reads "Files: out/a/x.txt.".

## D. The verdict ledger is union

- `append_only_paths` now lists `gate.verdict_ledger_without_governed`, read from config and resolved against the
  project, whenever verdicts do not go to the governed ledger. `seldon hooks install` and the pass's `_declare_union`
  write it.
- Two-branch test: the `.gitattributes` hazbrief had, then the `seldon hooks install` CLI (it adds and commits the one
  line), then main and a branch each append a verdict. The rebase completes with every line once, and the union check
  passes.
- **The governed-ledger case** (`docs/evidence/sel038/verdict_ledger_survey.txt`, read 2026-11-12):
  - seldon, squiddy and arnold record verdicts in `governed/ledger/events.jsonl`. ATTR-001 already declares that file,
    so there is nothing missing and no exposure.
  - hazbrief-mcp and ai-readiness-kg record them in `state/prior_art_verdicts.jsonl`, undeclared. Both are exposed,
    and both are declared by their own dispatcher's first pass after this merges.
  - A test pins that, with a governed graph, the fallback path is not declared and the governed ledger is listed once.

## E. Held releases

- `Library._export_exists` and `Library._digest` go through `squiddy.exports`: `exists`, `sha256`, and `size` with
  `mtime` for the digest cache key. seldon only hashes a release, so it never calls `read_bytes`. `search_release` and
  `release_rows` use them.
- `HeldExportError` is a `SystemExit`. It is caught and becomes `release_unavailable`.
- If the installed squiddy has no accessor, a held release is refused **as held**, naming the `.gz`. It is never
  reported as "not on disk".
- **What is actually installed (2026-11-12):** `squiddy/exports.py` exists only on squiddy's SQ-134 branch
  (`9a54c9e5`, worktree `twinkling-meandering-nova`). It is not on squiddy main, which is what this interpreter
  imports. The held `.gz` files are already in squiddy's primary.
- Tests use a gzip-held fixture, run through a stand-in that follows R-253 item 3's contract. The real accessor variant
  is skipped where squiddy lacks it. Run against SQ-134's branch on PYTHONPATH, all four real variants pass
  (`docs/evidence/sel038/held_release_tests_with_real_squiddy_exports.txt`).

## Tests

- `tests/test_sel038_journals_and_held_releases.py`: 14 pass, 4 skip (the real-accessor variants, as above).
- **Full suite on the branch:** 3386 passed, 2 failed, 11 skipped in 72 min (`docs/evidence/sel038/full_suite.txt`).
  - `test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index` is pre-existing. It
    fails the same way on main's own code (run from the primary checkout). `rebuild_release` is untouched.
  - `test_friction002_auto_mode.py::test_a_classifier_breaker_becomes_a_line_stop_with_the_classifiers_reason` got
    `completed` for `blocked` under the suite's load. It passes alone, and its file passes whole (6 passed). This is a
    timing race of the detached supervisor; the code it covers was not touched.

## The filings

- hazbrief `a7795a22` and `6d607cb9`: answered by the return below (`seldon cc return --answers`), which closes both.
- squiddy `2ce35aa9`: squiddy has nothing to do on seldon's account, so per R16 there is no return task. The filing is
  closed with this answer: seldon reads a held release through `squiddy.exports` (AD-036-R24), and no `keep_plain`
  declaration is needed for seldon. Until SQ-134's branch is on squiddy main, a receipt naming a held release is
  refused as held and names the missing accessor. No current receipt names one.

## For hazbrief-mcp

**Title:** seldon SEL-038 landed: the verdict ledger merges by union and Desktop prior-art runs during a task are safe again

Answers both filings: `a7795a22` (`ff_refused` over `state/prior_art_queries.jsonl`, Issue "Files: none named") and
`6d607cb9` (`state/prior_art_verdicts.jsonl` not `merge=union`).

The omission was not intended; seldon has fixed it. Since SEL-038 (AD-034-R19, R20; AD-036-R23):

- Before its fast-forward, under the lease, the merge round commits every system-written journal: the event store,
  the prior-art query log and the verdict ledger. A Desktop `seldon prior-art search` or `verify` in your primary
  while a task is in flight no longer strands that task's branch, so you can run them again.
- `seldon hooks install`, and your dispatcher at every pass, declare `state/prior_art_verdicts.jsonl merge=union`
  beside the query log.
- An `ff_refused` (or a `rebase_conflict` with no unmerged list) names the files git named.

Steps:

1. Confirm seldon main carries SEL-038: `grep -n JOURNAL_CLASSES /Users/brock/GitHub/seldon/seldon/core/reconcile.py`
   prints a line. If it prints nothing, stop. Say so in your RESULT; your dispatcher's first pass after seldon merges
   writes the attribute without you.
2. Check the attribute where you are working: `git check-attr merge -- state/prior_art_verdicts.jsonl
   state/prior_art_queries.jsonl` prints `union` for both. Your dispatcher's pass usually commits it to main before
   this task launches, as a `chore: declare append-only logs merge=union` commit.
3. If the verdict ledger is not `union`, run `seldon hooks install` where you are working (a dispatched session's
   worktree is fine). It writes and commits `.gitattributes` alone with `state/prior_art_verdicts.jsonl merge=union`.
   The commit merges with this task. Then repeat step 2.
4. Lift the hold on Desktop prior-art searches and verifies during a run. Say in your RESULT that it is lifted.

If a later rebase still conflicts in either file, the attribute was not in the tree the rebase read. Check it on
main with `git show main:.gitattributes`. Once it is there, put the blocked task back with `seldon dispatch redrive
<task id>`. Do not resolve by hand. If it conflicts with the attribute present, file it to seldon with git's stderr:
that would be a new defect.
