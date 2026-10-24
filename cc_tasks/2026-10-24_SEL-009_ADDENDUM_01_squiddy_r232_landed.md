# SEL-009 ADDENDUM-01: squiddy R-232 landed; the run-holds-its-binary half is done on Squiddy's side

**Author:** Desktop session (hazbrief), 2026-10-24 09:45 local.
**Applies to:** `cc_tasks/2026-10-24_SEL-009_models_refresh_does_not_bump_the_lock_under_a_held_lease.md`, Parts A and B.

squiddy SQ-038R landed on main at 7322bc7 with **R-232**: a run holds the CLI binary it was piloted on, and a lock bump during the run warns instead of stopping. Consumers pass the graph to `pin_cli(client, t, graph)` and seed pilot records with `squiddy pilot record`. hazbrief adopts it in HB-30.

What this changes here:

- **Part A** stands as ADDENDUM-00 reads it: AD-035-R7 is Seldon's rule for the in-flight lock entry, and the task finds why `models refresh` did not honour it on 2026-10-24. R-232 is the consumer's defence; it does not make the refresh correct, and a bump that R-232 only warns about still changes the measured system for the next run.
- **Part B**'s "pilot sized to what it detects" is unchanged and is Seldon's to declare on the lock (`pilot: {cost_calls, content_sample, full_on}`); R-232 does not touch pilot size. The squiddy stub Part B files should cite R-232 and SQ-038R so the reader of `pin_cli` is the one that reads the declaration.
- Do not duplicate R-232 in Seldon.
