# SEL-009 ADDENDUM-00: AD-035-R7 already rules the in-flight case; Part A is a conformance defect, not a feature

**Author:** Desktop session (hazbrief), 2026-10-24, minutes after registration.
**Applies to:** `cc_tasks/2026-10-24_SEL-009_models_refresh_does_not_bump_the_lock_under_a_held_lease.md`, Part A.

Registration's recall returned **AD-035-R7** (accepted 2026-10-09): while a run is in flight, the system shall keep the run's lock entry until the run ends, and a version bump is handled accordingly. The task as written asks for that rule as if it did not exist. It does. So Part A is read as:

1. Quote AD-035-R7 in full in the RESULT.
2. Find why it was not honoured on 2026-10-24: whether `models refresh` keeps no per-run entry, whether hazbrief's run never registered itself against the lock (the consumer's defect, to be filed back to hazbrief as a task), or whether squiddy's `pin_cli` reads only the lock head and never the kept entry (squiddy's defect, filed as a stub there). Quote the code path for each.
3. Fix what is Seldon's; file the rest where it belongs. The deferral record and the printed refresh time in the task's Part A steps 1 and 2 stand only where R7 does not already provide them.

Part B is unchanged. Also seen at registration and not this task's: the served recall arm is unavailable for seldon, squiddy and arnold because each `governed/work/index/index_manifest.json` was written under index rule `k003-index/2` and the reader wants `sq028r-index/3`; the indexes need a rebuild.
