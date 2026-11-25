# ADDENDUM 01 to 2026-11-21_SEL-044_one_brief_and_one_handoff_read_every_registered_repository_from_the_portfolio_project: SEL-043 already gives the running task's phase, its gate's progress and the wall clock

**Author:** OODA knowledge source on bf0b7a06 (AD-038-R16)
**Date:** 2026-11-25
**Predecessor:** SEL-043 (`bf0b7a06`), merged to main (`448fcfa`, `37f02d5`). RESULT:
`cc_tasks/2026-11-21_SEL-043_a_consumer_waits_on_a_producer_only_for_what_can_hurt_it_and_a_running_gate_shows_its_progress_and_its_wall_time_RESULT.md`.

Both premises are unchanged (the dispatcher ran them true). Parts A, B, D and E are unchanged. This addendum amends
two items of Part C's brief, because SEL-043 built what they read and ruled how one of them is shown.

## 1. "The running task and its phase" reads the pass lease's phase (AD-037-R17, R19)

SEL-043 made the pass lease record `phase` (`pass`, `session`, `gate`, `merge`; `seldon/core/dispatch.py`
`LEASE_PHASES`, `mark_phase`) and `phase_since`, and `seldon dispatch status` already reports it with the holder, the
task and, while a gate runs, `lease_gate` from `seldon/core/stations.py` `gate_progress` (wall seconds, lines
written, last line, how long since the log last grew, whether `EXIT=` is written).

- The portfolio row's phase is that lease phase, read from each repository the way `seldon dispatch status` reads its
  own (reuse its reader; do not derive a phase from events or task state). A repository whose lease records no phase
  (a holder on older code) shows `phase unknown`. Do not guess it.
- When a repository's lease is in `gate`, its detail shows `gate_progress` as `dispatch status` does. Output that has
  stopped growing is how a hung gate shows itself (AD-037-R19), so it counts as one of Part C's alarms ("something
  wrong" → detail). The threshold for "stopped growing" comes from config, not from a literal.
- Reading a lease and a gate log is read-only. Part B's "writes nothing to any of them" still holds. `mark_phase`
  rewrites a lease only when the caller holds it, and the portfolio reader holds none, but do not call it anyway.

## 2. "The median gate seconds" is wall time (AD-037-R21)

R21 says time shown to a person is wall time. Monotonic `seconds` leave out sleep: a pass recorded as 7,734 s took
10,834 s.

- The brief's median is over `wall_seconds` on `gate_recorded` and `gate_run` records (`seldon/core/gate_record.py`
  `summary`). Records written before SEL-043 have no `wall_seconds`. Leave them out, and print the median's n
  beside it. Do not fill those records in from monotonic `seconds`; that would mix two clocks in one number.
- A repository with no record that carries wall time shows `no wall-clock gate records`, not a number.
- Part D's thirty-second budget stays on the brief's own runtime. It does not touch this median.

## 3. Tests (added to Part C's fixture of three repositories)

- One fixture repository's lease is in `gate`, with a gate log, and the brief shows its phase and its gate's last line.
  A second has a lease with no phase, and the brief shows `phase unknown`.
- One repository has gate records with and without `wall_seconds`. The median uses only those with it, and its n is
  printed.

## 4. What NOT to do

- Do not add a second phase field, a second gate-progress reader or a second clock. SEL-043's are the ones to use.
- Do not change station (a)'s holding rule or the lease format. They belong to AD-037-R17 and R18.
