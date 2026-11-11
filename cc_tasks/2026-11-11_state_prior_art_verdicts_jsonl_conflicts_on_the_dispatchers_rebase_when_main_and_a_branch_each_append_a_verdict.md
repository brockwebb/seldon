# state/prior_art_verdicts.jsonl conflicts on the dispatcher's rebase when main and a branch each append a verdict

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-11
**Reporter:** hazbrief-mcp Desktop session hz-16, from the OODA on HB-166 (`937b6132`). Continues the filing of the same day, seldon task `a7795a22` (commit `7f8acb92`), which names `state/prior_art_queries.jsonl` only.

## What was experienced

HB-166 landed HB-155's kept branch by hand. Replaying HB-155's commits onto main conflicted in one file, `state/prior_art_verdicts.jsonl`, in two commits (`888c26c5` and `915d2ab9`, both `record: prior-art verify DN-023 (pass) (AD-036-R11)`). main had appended one verdict to that file in the meantime (HB-164's). The session resolved it by keeping every line from both sides in `ts` order; the file ended at 60 valid JSONL lines with no duplicate ids.

The session reports that a merge commit carrying the same content would have been refused by the dispatcher as `rebase_conflict`, because `WT.rebase` runs a plain `git rebase -q <main>`, which drops the merge commit and replays the branch's commits. It did not let the dispatcher try; this is its reading of `seldon/commands/dispatch_worktree.py` and of `git merge-tree`.

## What the evidence shows

- hazbrief-mcp `.gitattributes` (written by `seldon hooks install`, per its own header) carries two lines: `seldon_events.jsonl merge=union` and `state/prior_art_queries.jsonl merge=union`. `state/prior_art_verdicts.jsonl` is not listed.
- The file is append-only in use: every writer found is a `prior-art verify` record.
- hazbrief-mcp `docs/evidence/hb166/divergence.txt` lists it among the nine files both sides changed, marked "append-only by use; not merge=union in .gitattributes".
- hazbrief-mcp `cc_tasks/2026-11-11_HB-166_..._RESULT.md`, sections "In plain terms", Part B item 3 and "Deviations", gives the conflict, the resolution and the tool used (`docs/evidence/hb166/tools/union_resolve.py`).
- The condition is ordinary: any two tasks that each verify a design note under AD-036, where the first merges while the second runs, put a verdict on both sides.

## What is asked

Whether the omission of `state/prior_art_verdicts.jsonl` from the union-merged set is intended. If it is, what a consumer's task should do when its rebase conflicts there. If it is not, hazbrief-mcp will re-run `seldon hooks install` when told to.

Until answered, hazbrief-mcp's Desktop sessions run no `seldon prior-art` search or verify in the primary checkout while a dispatched task is in flight.
