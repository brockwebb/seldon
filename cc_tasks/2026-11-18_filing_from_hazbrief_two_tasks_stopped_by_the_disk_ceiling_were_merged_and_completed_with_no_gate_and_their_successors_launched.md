# Filing from hazbrief-mcp: two tasks stopped by the dispatcher's disk ceiling were merged and completed with no gate, and their successors launched

**Kind:** filing
**Filed by:** hazbrief-mcp
**Author:** Desktop session hz-19, 2026-11-18. This reports what hazbrief-mcp experienced. It proposes nothing.

## What happened

All times are 2026-11-18, UTC. The ids are hazbrief-mcp's.

1. **HB-197 (`f6a8bca3`).** Launched 14:09:40. At about 15:34 its session was in its gate (the first pytest step at 96 percent, no failure printed) when the dispatcher wrote a hard stop, `disk_ceiling`: 4.07 GB free against 4.98 GB needed "for an in-place launch". The session ended its gate and committed a RESULT whose title says the gate "is not established". At 15:37:09 the task was completed and its branch was on main (`163d6adf`). HB-198's RESULT reads the event store for that merge as `regated: false`, `gate: null` (events `c3163e6c`, `0406da34`, `e214e7d7`).
2. **HB-198 (`7989e01b`).** Launched 15:45:43. Stopped by `disk_ceiling` at about 16:04 (`free_bytes` 4,563,726,336 against `need_bytes` 4,993,114,036, factor 2 times a footprint of 2,496,557,018), with the hook recording `andon_halted`. Its RESULT's last line is "The task is in progress and is not complete", and it lists most of its items as not done. At 16:07:09 the task was completed.
3. **The successor.** The OODA knowledge source read HB-198's RESULT, wrote an addendum about disk for HB-199 (`3161ca30`), and released it. HB-199 launched at 16:14:43.
4. **Where the ceiling met the gate.** hazbrief's gate writes several GB of temporary files while it runs. HB-198's own record (`docs/evidence/hb198/disk.txt`) shows 10.46 GB free before its work and 4.56 GB when it was stopped. So a task that launched with twice its footprint free was stopped by the disk its own gate was using.

## What it cost hazbrief

- Main holds HB-197's changes, and HB-198's partial ones, with no whole-suite pass over them.
- A checkpoint task is completed in the graph with its checkpoint, its Issues, its manifest and its gate not done. Desktop filed two new tasks to redo the work (HB-202, HB-203).
- The Desktop OODA had no turn between these tasks. Each successor was released at its predecessor's completion, so an addendum written from a finished RESULT arrives after the successor has started. Twice today the only way to steer a successor was to read the predecessor's draft RESULT in its worktree while its gate was still running.

## Where the records are

hazbrief-mcp: `cc_tasks/2026-11-17_HB-197_*_RESULT.md` ("Stopped by"; "Gate and verify"); `cc_tasks/2026-11-17_HB-198_*_RESULT.md` (title; "Stopped by"; "Not done"; "Closure state"); `docs/evidence/hb198/disk.txt`; `seldon_events.jsonl` between 15:30 and 16:15.
