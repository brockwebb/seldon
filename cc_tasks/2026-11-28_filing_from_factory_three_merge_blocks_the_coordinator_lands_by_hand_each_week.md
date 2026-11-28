# Filing from factory: three merge blocks the coordinator lands by hand each week

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-28
**Reporter:** factory FAC-61 (DN-006), a dispatched Claude Code session; counted by `scripts/lessons.py` at zero tokens.

## What was experienced

FAC-61 counted every registered repository's record since 2026-10-29 by the reason codes the dispatcher writes
(`dispatch_finished.merge.reason`), one event per task and kind. Three merge blocks recur, and every one was landed
by a person or an OODA task (a redrive, a supersede and an R task, or a completion by hand), never by code:

1. **`uncommitted_changes`: 7 events in 30 days, in 4 repositories.** A session ends with a file in its worktree it
   neither committed nor ignored, and the merge blocks after the session has exited, when it can no longer fix it.
   - 2026-10-29T23:38Z hazbrief-mcp HB-72 (`corpus/raw`, `graphs/hazbrief-corpus/...`), completed by desktop
   - 2026-11-05T15:42Z squiddy SQ-114, 22:59Z SQ-114R, 2026-11-07T20:31Z SQ-131 (each
     `graphs/library/evidence/20260923_q002/verb_parity_biblio_neo4j`), superseded by desktop; SQ-114R replayed
   - 2026-11-14T05:43Z factory FAC-06 (`logs/`)
   - 2026-11-18T22:47Z hazbrief-mcp HB-203 (`seldon_events.jsonl`), completed by cc
   - 2026-11-26T22:55Z critical-thinking-ai CTAI-006R (`graphs/critical-thinking-evidence/archive:inbox/`), redriven by
     desktop
2. **`spec_modified`: 5 events, in 2 repositories.** A session edits its own task file; the merge refuses the change.
   - 2026-10-29T22:54Z hazbrief-mcp HB-64, 2026-11-05T02:15Z HB-106, 2026-11-06T16:47Z HB-107, 2026-11-27T08:48Z
     HB-232 (OODA-004 redrove it)
   - 2026-11-28T01:33Z factory FAC-55 (superseded; replayed as FAC-55R by OODA-023)
3. **`regate_red`: 7 events, in 2 repositories.** The re-gate at merge is red; five of the seven were redriven by hand
   and passed on a later launch (HB-217, HB-223, SEL-043, SEL-051 twice), one was replayed (SEL-045), and SEL-041's
   gate was killed at its time limit (`exit_code -9, timed_out`).

The record lines are in `factory/state/lessons.json` (`kinds`) and on `factory/site/lessons.html`; each event names
its `seldon_events.jsonl` line.

## What factory asks, one per block

1. **Strays found while the session can still act.** Could the stop gate (or `seldon dispatch part-complete` for the
   last Part) run the merge's own `uncommitted_changes` test in the worktree and refuse to pass while it fails, naming
   the paths, so the session commits or ignores them before it ends?
2. **The session's own task file, refused at the tool.** `dispatch.guard.deny_paths` takes static absolute paths
   (seldon/core/controls.py). Could the tool gate also deny an Edit or Write on the dispatched task's own
   `source_file` (and its addenda), the poka-yoke at the source rather than the refusal at merge?
3. **A red re-gate that is main's, not the task's.** Five of seven passed on a redrive with no change to the branch.
   Could the re-gate record whether main itself was red at the commit it rebased onto (the cadence's last full gate),
   and the pass redrive by code once main is green again, keeping F-027 item 2 (a task red twice on its own change is
   parked)?

## What factory does meanwhile

These three kinds carry the disposition `filing` in `factory/scripts/lessons.yaml`, citing this file. The tick
recounts them (DN-006 decision 3); each later event is on the lessons page with what was done about it.
