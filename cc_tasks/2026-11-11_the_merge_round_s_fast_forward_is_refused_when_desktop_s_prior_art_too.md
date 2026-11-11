# The merge round's fast-forward is refused when Desktop's prior-art tool has appended to state/prior_art_queries.jsonl in main during a run, and the Issue names no file

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-11
**Reporter:** hazbrief-mcp HB-166 (`937b6132`), landing HB-155 (`49768b52`) after its merge was refused.

## What was experienced

HB-155 ran for six hours in a worktree, finished green (6,773 passed; ruff clean), committed its RESULT and exited 0.
The standing dispatcher's merge round, at 2026-11-11 12:25 EST, recorded `MERGE BLOCKED 49768b52 (ff_refused): -`
after three attempts, kept the worktree, set the task blocked and opened Issue `1e7d1faf`, whose text says
"Files: none named". Six hours of finished work stayed off main until a second task (HB-166) landed it by hand.

## What the evidence shows

- The branch was strictly ahead of main at the fast-forward: `git merge-base main <branch>` is `83779f86`, the
  round's own record commit at 12:25:29; the branch's 20 commits are dated 12:25:33 to 12:25:49 (rebased onto it).
- The `dispatch_finished` event (`8d7403aa`, 17:25:55Z) carries git's stderr in `payload.merge.stderr`:

  ```
  error: Your local changes to the following files would be overwritten by merge:
  	state/prior_art_queries.jsonl
  Please commit your changes or stash them before you merge.
  Aborting
  ```

- The local changes were six lines appended by Desktop's `prior-art/1` tool at 11:40Z (06:40 EST), while HB-155's
  lease was held. The next pass committed them at 12:31:04 EST as
  `reconcile: 6 prior-art line(s) written by prior-art/1; committed by the standing dispatcher (prior_art, AD-038-R1)`.
- HB-155 itself changed `state/prior_art_queries.jsonl` (its AD-036 receipts for DN-023), so git refused. HB-164,
  which did not change that file, fast-forwarded at 15:20:14 EST over 31 uncommitted prior-art lines (committed
  afterwards at 15:25:27). The refusal therefore needs both: Desktop writes to the prior-art journal during a run,
  and the run writes prior-art receipts of its own. Any task that authors a design note under AD-036 does the latter.
- In the round (`seldon/commands/dispatch_worktree.py` lines 978-983) the lease-held step before the fast-forward
  runs `_record_own_lines` (which reconciles `classes=("event_store",)`, `dispatch.py` line 417) and
  `_commit_shared` (the configured `shared_paths`). The `prior_art` reconcile class is committed only by the full
  `R.reconcile` at the start of a pass (`dispatch.py` line 307). The comment at lines 979-981 describes this exact
  failure for the event store.
- On `ff_refused` the round records `files: []` (lines 1014-1018) although git's stderr names the file, so the Issue
  says "Files: none named".
- This repository's dispatch log (`logs/seldon_dispatch.log`, read 2026-11-11 15:4x EST) holds 85 merges, every one
  `attempt 1, regated=False`, and five `MERGE BLOCKED` lines: three `spec_modified`, one `uncommitted_changes`, and
  this one, the only `ff_refused`.

Full evidence: hazbrief-mcp `docs/evidence/hb166/divergence.txt` (merge base, both sides' commits, main's reflog, the
files both sides changed).

## What is asked

That the dispatcher not leave a finished, green, strictly-ahead branch unmerged because a system-written append-only
journal in main was dirty, and that an `ff_refused` Issue name the file git named. The fix is seldon's to design.
