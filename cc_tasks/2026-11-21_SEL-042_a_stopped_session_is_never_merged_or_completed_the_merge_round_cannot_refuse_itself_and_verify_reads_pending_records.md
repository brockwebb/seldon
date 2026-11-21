# SEL-042: a session the dispatcher stopped is never merged or completed, the merge round cannot refuse its own fast-forward, `seldon verify` reads pending records, and a file name too long is a refusal

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-21, the Saturday batch the operator ordered on 2026-11-19. Answers four filings: hazbrief-mcp `de40f402` (two tasks stopped by the disk ceiling were merged and completed with no gate), hazbrief-mcp `6a9c00fa` (the round's own dedupe line makes its fast-forward refuse), squiddy `5b76278b` (`seldon verify` KeyError `record_hash` on pending records, 2026-11-06), hazbrief-mcp `1639fa20` (an addendum file name over 255 characters crashes with a traceback).
**Repo:** seldon (primary). hazbrief-mcp and squiddy are read, never written; Part F files their returns. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-034 (the merge round; R5 merge on green; R16 to R18 the pass record; R19 journals before the fast-forward; R24 the merge projects what it numbers); AD-037-R6 (stations and hard stops); FRICTION-002 (the Stop gate); AD-038 (R1 reconcile; R16, R17 the OODA between chained tasks; R20, R26 filing in one call; R25 kept events); AD-033 (R2, R12 pending records numbered at merge). Number new rulings under AD-034, AD-033 and AD-038.
**Model:** primary
**Spend:** est. 1.2M tokens. Basis: four defects, each located by its filing to a function, each with a reproduction first; two addenda; two returns. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon/commands/dispatch_worktree.py`, `seldon/commands/dispatch.py`, `seldon/core/stations.py`, `seldon/core/decisions.py`, `seldon/commands/verify.py`, `seldon/core/filing.py`)
**Parts:** A 0.10, B 0.35, C 0.20, D 0.15, E 0.10, F 0.10.
**Premises:**
- premise: the disk-ceiling filing is on main | check: test -f cc_tasks/2026-11-18_filing_from_hazbrief_two_tasks_stopped_by_the_disk_ceiling_were_merged_and_completed_with_no_gate_and_their_successors_launched.md
- premise: the dedupe filing is on main | check: test -f cc_tasks/2026-11-16_the_merge_round_s_own_dedupe_line_makes_its_fast_forward_refuse_a_kept.md
- premise: the verify filing is on main | check: test -f cc_tasks/2026-11-06_consumer_filing_from_squiddy_seldon_verify_keyerror_record_hash_on_pending_register_records.md
- premise: the file-name filing is on main | check: test -f cc_tasks/2026-11-19_filing_from_hazbrief_an_addendum_file_name_over_255_characters_crashes_with_a_traceback.md

Read the four filings first. Their evidence is the measurement.

## The condition

1. **Ungated work reached main and was marked done** (hazbrief, 2026-11-18). HB-197's session was stopped in its gate by the dispatcher's own hard stop (`disk_ceiling`); it committed a RESULT saying the gate "is not established"; two minutes later the task was completed and merged (`regated: false`, `gate: null`). HB-198 was stopped the same way, its RESULT ends "the task is in progress and is not complete", and it was completed three minutes later. Its successor launched. Two tasks were filed to redo the work. This is the most serious of the four: the dispatcher's stop removed the only gate and the round merged anyway.
2. **The ceiling counted the gate's own disk.** HB-198 launched with 10.46 GB free, twice its footprint, and was stopped at 4.56 GB by temporary files its own gate wrote.
3. **The merge round refused itself** (hazbrief, 2026-11-16). Under the lease the round commits main's journals, rebases, and `dedupe()` appends `kept_events_deduped` to main's store after that store was committed and before the fast-forward, so git refuses; the next attempt commits the line, main moves, the rebase restores the duplicates, three times, then `ff_refused`. A finished green branch was landed by hand.
4. **`seldon verify` crashes on pending register records** (`KeyError: 'record_hash'`, `decisions.py:772`): squiddy 2026-11-06, hazbrief 2026-11-16, and seldon's own SEL-040 session, which skipped verify for it. Pending records in a worktree are the documented path (AD-033-R12). Every other check's result is lost when it raises. Sessions work around it by moving the pending directory aside.
5. **A file name over 255 bytes is a traceback** (`OSError: File name too long`, `filing.py` line 292). A long task stem leaves an addendum about 50 characters of slug or none.

## Prior art

- Seldon's own: AD-034-R5 ("merge on green"), SEL-024 (the merge requires the project's declared pass record for the tip, which a project with `gate_record: none` does not have), SEL-034 (a terminal task stops its session). The defect in item 1 is a hole between those three, so the rule exists and the round does not ask for its evidence.
- Fail-safe defaults (Saltzer and Schroeder 1975, "The Protection of Information in Computer Systems": base the decision on permission, so that an absent check denies). Named from memory and not fetched; cite it from seldon-biblio or the squiddy library if either holds it, otherwise as unfetched.
- Kubernetes node-pressure eviction (soft and hard thresholds on available disk, and a pod's own ephemeral-storage limit counted against the pod and not the node). Named from memory and not fetched; same rule.

Run `seldon prior-art search` (internal and library arms) before the addenda.

## What to build

**A. Rulings** (AD-034 addendum for items 1 to 3, a short AD-033 addendum for item 4, AD-038 for item 5; `prior-art verify` passing before the code).
- A branch is merged only on recorded evidence that a gate passed for the tip being merged: the session's Stop-gate pass, the round's re-gate, or the project's declared pass record. With none of the three, the task is blocked `ungated`, its worktree kept. Absence of a gate never merges.
- A session that ended on a dispatcher hard stop is never completed by the round: the task is blocked with the stop's reason, whatever its RESULT says, and no successor is released from it.
- The disk station: measure first what it reads and when (Part B). Then rule so that a task is not stopped by disk its own run is using inside what it declared or was measured to need; a run that exceeds that is stopped as now.
- The round writes nothing to main's tracked files between its journal commit and its fast-forward.
- `seldon verify` reports pending register records (count and ids, "numbered at merge") and runs every other check.
- A name over the file system's limit is refused before anything is written, stating the limit and the characters left for the slug.

**B. The stop that merged.** Reproduce first from hazbrief's events between 15:30Z and 16:15Z on 2026-11-18 (a fixture cut from them): the current code completes and merges. Then the two rules and their tests: a hard-stopped session's task is blocked and unmerged; a branch with no gate evidence is `ungated`; a normal green finish merges as now; a project with `gate_record` behaves as SEL-024 left it. Then the disk station: record what `need_bytes` and `free_bytes` meant in HB-197 and HB-198, measure a gate's temporary growth on seldon's own suite, and build the ruling. Say what happens to the two hazbrief tasks' state (they are completed in hazbrief's graph; seldon does not rewrite it; the return says so).

**C. The round that refused itself.** Reproduce from hazbrief's `docs/evidence/hb193/` counts (a branch whose rebase restores three event lines main already holds): three attempts, `ff_refused`. Then the fix and its test: one attempt, merged, each id once on main. Find which replayed commit restores the lines (the filing could not isolate it) and report it.

**D. Verify and pending records.** Reproduce with squiddy's three pending files' shape (two accepts, one amend of a numbered record). Then the report line and the test that every other check still prints. Remove the "move the pending directory aside" workaround from any seldon doc or CLAUDE.md that teaches it.

**E. The name limit.** `seldon cc file` (task and addendum paths) and `seldon cc return` refuse `name_too_long` with the byte count; registration warns when a task's stem leaves fewer than 60 bytes for an addendum slug (the number is a first value; say so). Tests at the limit and one byte over, with a non-ASCII name.

**F. Returns.** One to hazbrief-mcp answering `de40f402`, `6a9c00fa` and `1639fa20`: what changed; that HB-197 and HB-198 stay as hazbrief recorded them; that the OODA between chained tasks is the dispatcher's knowledge source by design (AD-038-R16) and a successor that needs a person's turn says so with `Dispatch: hand` or an `at: launch` premise. squiddy's `5b76278b` is closed with the answer (verify is meant to run with pending records and now reports them); a task in squiddy only if squiddy has something to do.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 1.45M.

## Deliverables

A to F with tests; the addenda and their rulings; the four filings answered; `cc_tasks/2026-11-21_SEL-042_a_stopped_session_is_never_merged_or_completed_the_merge_round_cannot_refuse_itself_and_verify_reads_pending_records_RESULT.md`.
