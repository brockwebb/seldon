# SEL-038: a system-written append-only journal never blocks a finished branch's merge, an ff_refused Issue names the file git named, and a held library release is read through squiddy's accessor

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-11. Answers three consumer filings: hazbrief-mcp `a7795a22` (the fast-forward refused over `state/prior_art_queries.jsonl`), hazbrief-mcp `6d607cb9` (`state/prior_art_verdicts.jsonl` conflicts on rebase), squiddy `2ce35aa9` (library releases held compressed).
**Repo:** seldon (primary). L4: commit, merge, push in seldon. Consumers are told by `seldon cc return`; their repositories are not written otherwise.
**After:** 0e49ea54
**Governing:** AD-034 (the merge round) and its addenda; AD-038-R1 (reconcile: the dispatcher commits system-written lines); AD-036-R11 (verdict records), R19 (superseded releases), R12 and R16 (consumer filings and the return path); squiddy DN-059 R-253 (held releases and the `squiddy.exports` accessor). Number new rulings under AD-034 and AD-036.
**Model:** primary
**Spend:** est. 0.6M tokens. Basis: three narrow changes with tests in code the filings already located by line, one addendum per governing note, three returns. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon/commands/dispatch_worktree.py`, `seldon/commands/dispatch.py`, `seldon/core/prior_art.py`, the hooks installer)
**Parts:** A 0.15, B 0.35, C 0.15, D 0.20, E 0.15.
**Premises:**
- premise: the first hazbrief filing is on main | check: test -f cc_tasks/2026-11-11_the_merge_round_s_fast_forward_is_refused_when_desktop_s_prior_art_too.md
- premise: the second hazbrief filing is on main | check: test -f cc_tasks/2026-11-11_state_prior_art_verdicts_jsonl_conflicts_on_the_dispatchers_rebase_when_main_and_a_branch_each_append_a_verdict.md
- premise: squiddy's filing is on main | check: test -f cc_tasks/2026-11-10_consumer_filing_from_squiddy_library_sealed_releases_held_compressed_and_prior_art_verify_opens_dated_exports.md
- premise: the merge round is where the filings say | check: test -f seldon/commands/dispatch_worktree.py

Read the three filings first. Their evidence is the measurement; re-measure only what a fix depends on.

## The condition

1. hazbrief HB-155 ran six hours, finished green and strictly ahead of main, and was left unmerged (`ff_refused`) because a Desktop prior-art search had appended six lines to `state/prior_art_queries.jsonl` in main during the run and the branch had receipts of its own in that file. The lease-held step before the fast-forward reconciles the `event_store` class only; the `prior_art` class is committed only at the start of a pass. The Issue it opened said "Files: none named" while git's stderr named the file. A second task landed the work by hand.
2. Landing it by hand then conflicted twice in `state/prior_art_verdicts.jsonl`: `seldon hooks install` writes `merge=union` for `seldon_events.jsonl` and `state/prior_art_queries.jsonl` and not for the verdict ledger, which is append-only by every writer found. hazbrief has stopped running prior-art searches in its primary while a task is in flight until this is answered.
3. squiddy now holds library releases older than its keep set as `.gz`; `Library.search_release`, `Library.export_path` and `Library.release_rows` open a release by plain file name, so a receipt naming a held release reads `release_unavailable`. No current receipt is affected; the next old one will be.

## Prior art (cite in the addenda; the mechanism is git's own and squiddy's own)

- `gitattributes(5)`, built-in merge driver `union`: keeps lines from both sides of a conflict, for files where line order across sides carries no meaning. An append-only JSONL journal whose lines carry their own timestamp and id is that case; Seldon already ruled so for the event log and the query log.
- AD-038-R1 already rules that the dispatcher commits system-written lines; the comment at `dispatch_worktree.py` lines 979 to 981 describes this failure for the event store. The fix extends an existing ruling to a class it missed; it is not a new mechanism.
- squiddy DN-059 R-253 item 3: `squiddy.exports` reads a dated export by its plain path whether plain or held, verifying sha256 and size.

Run `seldon prior-art search` for the internal receipts (merge round, reconcile, union) before the addenda.

## What to build

**A. Rulings.** An AD-034 addendum: before the fast-forward, under the lease, every reconcile class whose files are system-written append-only journals is committed, not the event store alone; an `ff_refused` record carries the files git's stderr names. An AD-036 addendum: the verdict ledger is union-merged wherever the query log is; a library release is read through `squiddy.exports`. `prior-art verify` passing before the code.

**B. The merge round.** Tests first, reproducing the filing: a branch that changed `state/prior_art_queries.jsonl`, main dirty in the same file from a `prior-art/1` append made during the run; the round must merge on attempt 1. Then the same for the verdict ledger. Then the fix. If any other system-written file can be dirty in main during a run (list them from the reconcile classes), it gets the same treatment or a stated reason why not.

**C. The Issue.** `ff_refused` (and any other merge block that has git's stderr) records the named files; test on the filing's stderr text.

**D. Union for the verdict ledger.** `seldon hooks install` writes `state/prior_art_verdicts.jsonl merge=union` (or the project's `verdict_ledger_without_governed` path, read from config, never a literal); a rebase where both sides appended a verdict completes with every line once. Test with two branches. Check the governed-ledger case (a project that records verdicts in its governed ledger instead): say whether it has the same exposure, with evidence.

**E. Held releases, and the returns.** `Library` opens a release through `squiddy.exports` (`exists`, `sha256`, `read_bytes`); a receipt naming a held release verifies; test with a gzip-held fixture. Then the returns: to hazbrief-mcp (re-run `seldon hooks install`; Desktop prior-art searches during a run are safe again; what to do if a rebase still conflicts), and to squiddy only if squiddy has something to do (R16), otherwise close the filing with the answer: seldon reads through the accessor, no `keep_plain` declaration is needed on its account.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.72M.

## Deliverables

A to E with tests; the two addenda and their rulings; the three filings answered; `cc_tasks/2026-11-11_SEL-038_a_system_written_journal_never_blocks_a_merge_and_a_held_library_release_is_read_through_squiddys_accessor_RESULT.md`.
