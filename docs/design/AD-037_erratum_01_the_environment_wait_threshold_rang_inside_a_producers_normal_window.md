# AD-037 erratum 01: the environment wait's threshold rang inside a producer's normal window

**Date:** 2026-11-28. **Corrects:** AD-037-R23's default
(`docs/design/AD-037_ADDENDUM_06_a_parts_own_check_line_is_read_and_a_wait_on_a_producer_rings.md`), and the basis
in `seldon/core/dispatch.py` (`ENVIRONMENT_WAIT_PASSES_DEFAULT`). The addendum is not edited. This erratum and its
register record (`seldon decision amend seldon:AD-037-R23`) carry the change.
**Found by:** REVIEW-001 F-20. **Fixed by:** SEL-062 Part B
(`cc_tasks/2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say.md`).

## What was wrong

R23 rings when a consumer's wait on a producer's lease has refused 12 reviewed passes, one hour at a 300 s poll.
Its stated basis was "seldon's full gate took 2,408 s at `-n 6` (SEL-055's baseline), the longest window a producer
holds in normal running". That was one figure, not a distribution, and the record contradicts it.

Measured on 2026-11-28 by `/tmp/sel062/windows.py`, read-only over each repository's event store:

| Source | n | p50 | p90 | max |
|---|---|---|---|---|
| seldon `gate_run`, call site `merge_gate`, tier full (2026-11-25 to 27) | 5 | 4,854 s | 5,788 s | 5,788 s |
| seldon `gate_run`, call site `cli`, tier full | 2 | 2,449 s | 3,600 s | 3,600 s |
| seldon `gate_run`, call site `stop_gate`, tier scoped | 4 | 430 s | 638 s | 638 s |
| hazbrief-mcp `environment_in_flight` refusals: window age at first sighting | 35 | 1,840 s | 8,158 s | 13,958 s |
| squiddy, the same | 11 | 153 s | 3,192 s | 3,228 s |
| factory, the same | 5 | 74 s | 6,896 s | 6,896 s |

A producer holds its lease through a full gate. seldon's full merge gates ran past one hour every time recorded, so
twelve passes rang inside normal windows. seldon and hazbrief-mcp both declare `gate_timeout_s: 7200`. A gate past
that is killed, so 7,200 s bounds a normal window. No scheduled run (SEL-055's `scheduled` call site) is on record
yet, so the schedule's own distribution is not measured.

## The correction

The default becomes the first pass past the bound: `ENVIRONMENT_WAIT_PASSES_DEFAULT = 25`, which is 7,500 s at
300 s. The bound is `PRODUCER_WINDOW_BOUND_S = 7200`, the producers' declared `gate_timeout_s`. That follows WHO TRS
1033 Annex 4: alert levels "should be established based on historically reported data". A project that names
`environment_in_flight` keeps its own value. `seldon dispatch status` now prints the effective threshold of every
criterion, so the number a consumer runs on is visible, not inferred from code.

The observed windows past 7,200 s (hazbrief's 8,158 s and 13,958 s first sightings) are the abnormal holds R23
exists to ring for. At 25 passes they would have rung at about 2 h 5 min.

The default is re-read when the scheduled call site has a distribution of its own, by the next task that changes
R23's threshold.
