# Filing from hazbrief-mcp: the dispatcher's gate is one command per repository; hazbrief's grew from 12 minutes to 76 to 89 minutes in ten days and ran in full for a one-slide change

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-21
**Reporter:** hazbrief Desktop thread, relayed by the operator to the seldon Desktop session SLD-2 at 07:53 EST and written here by that session in hazbrief's words.

## What hazbrief experienced

`dispatch.gate_command` is one command per repository, with no notion of what a change touched. hazbrief's grew from 12 minutes to 76 to 89 minutes over ten days and ran in full for one-slide changes.

- 2026-11-11: 12 to 14 minutes (HB-164).
- 2026-11-16: 59 to 72 minutes.
- Since then: 76 to 89 minutes by HB-194's measurement, at 8,321 tests.

Three things are stacked: the gate exists as one command for the whole repository (seldon's dispatcher); what that command runs is the entire suite and then lint (hazbrief's own `seldon.yaml`, HB-105, HB-164, HB-194); and "before the RESULT, one full gate" on every task is hazbrief's own `CLAUDE.md`, repeated in every task file. `max_parallel: 1` makes tasks queue end to end. The "run everything" choice was made when the suite took minutes and was not revisited as it grew. The operator's finding of 2026-11-12 (hazbrief Issue `9db4906c`) asked for slices with the whole suite at critical points; it got parallel workers, and the suite grew past the gain.

hazbrief's suite holds 29 recorded briefs replayed, headless Chrome tests and two dispersion engines, and every task adds tests.

## What the evidence shows

- hazbrief-mcp `docs/evidence/hb164/` (the 12 to 14 minute measurement and the parallel change), `docs/evidence/hb193/gate_history.tsv`, `docs/evidence/hb194/three_gates.tsv`.
- hazbrief-mcp `seldon.yaml` `dispatch.gate_command`; hazbrief-mcp `CLAUDE.md`.
- hazbrief has not read the other projects' gate lines and cannot say how long theirs take.

## What hazbrief wants to know

Does the dispatcher intend a gate chosen by what a task changed, and should adoption warn when a gate passes a time threshold?
