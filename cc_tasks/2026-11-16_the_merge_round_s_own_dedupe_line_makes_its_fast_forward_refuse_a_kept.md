# The merge round's own dedupe line makes its fast-forward refuse: a kept branch whose reconciled events reappear on every rebase is ff_refused three times

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-16
**Reporter:** hazbrief-mcp HB-193 (`4d98aefe`), landing HB-189 (`f61999a7`) after its merge was refused.

## What was experienced

HB-189 ran in two sessions (the first was kept on a network failure; its branch was merged into the second's). The
second finished green (7,980 passed; ruff clean), committed its RESULT and exited 0 at 13:35 EST on 2026-11-16. The
standing dispatcher's merge round then logged `MERGE BLOCKED f61999a7 (ff_refused): seldon_events.jsonl` after three
attempts, kept the worktree, set the task blocked and opened Issue `8e8e1ecf`. A second task (HB-193) landed the work
by hand. No content conflicted: the only file both sides changed was `seldon_events.jsonl` (`merge=union`).

## What the evidence shows

- `dispatch_finished` `93965f23` (18:38:26Z), `payload.merge.stderr`: "error: Your local changes to the following
  files would be overwritten by merge: seldon_events.jsonl ... Aborting". `attempts: 3`.
- Main's log during the round (EST): `9d8c7b2e` 13:35:54 (record: ... stop_gate, 17 lines), `1573cbc2` 13:36:43
  (record: kept_events_deduped f61999a7, 1 line), `1240b17b` 13:37:32 (record: kept_events_deduped f61999a7, 1 line),
  then `e3904bc2` 13:38:29 (record: kept_events_deduped, dispatch_finished, ... 24 lines).
- Three `kept_events_deduped` events, each dropping the same three ids (`30730309`, `b1ab2033`, `dfa7ae1e`), each with
  a different branch commit: `cffcdf74` 18:36:39Z (`e9598be1`), `569e07ce` 18:37:25Z (`3891cff2`), `7175298e`
  18:38:19Z (`fa8fd4d2`).
- The branch's reflog shows a rebase before each drop: onto `9d8c7b2e`, `1573cbc2`, `1240b17b`. The three ids are held
  once at the session's tip and twice right after each rebase (counts per revision below).
- Reading `_merge` in `seldon/commands/dispatch_worktree.py`: under the lease the round calls `_record_journals`
  (which committed `9d8c7b2e`, `1573cbc2`, `1240b17b`), sees main moved by housekeeping only, rebases, and calls
  `dedupe()`. `dedupe()` calls `S._emit(project_dir, ...)`, which appends `kept_events_deduped` to main's store after
  that store was committed and before `git merge --ff-only`. The branch also changes the store, so git refuses. The
  next attempt commits the line, which moves main, which forces the next rebase, which restores the duplicates again.
- The third dedupe line was committed only with `dispatch_finished`, after the round gave up.

### docs/evidence/hb193/divergence.txt (excerpt)

```
git merge-base main worktree-witty-finding-whisper = 1240b17b (the round's own record commit)
main since the base: 5 commits; branch: 31 (HB-189's 30, then the dispatcher's drop commit fa8fd4d2)
files changed: main 2, branch 445, both 1 -- seldon_events.jsonl (merge=union)

  rev        30730309 b1ab2033 dfa7ae1e
  9e977247^  2 2 2     HB-189's own tree before its hand edit
  9e977247   1 1 1     HB-189's hand edit (Part D item 15) removed the later copy of each
  f7fefe89   1 1 1     HB-189's session tip
  885e3704   1 1 1     rebased onto 8eb45a75
  864cf918   2 2 2     after the round's rebase onto 9d8c7b2e
  e9598be1   1 1 1     dedupe
  8f5d7ab3   2 2 2     after the rebase onto 1573cbc2
  3891cff2   1 1 1     dedupe
  c10a7ecd   2 2 2     after the rebase onto 1240b17b
  fa8fd4d2   1 1 1     dedupe (branch tip)
  main       1 1 1
```

### docs/evidence/hb193/events_diff.tsv (summary)

```
main f10255db: 11,969 lines, 11,969 ids, 0 malformed
branch worktree-witty-finding-whisper: 11,946 lines, 11,946 ids, 0 malformed
main_only 23 (the round's own lines from 18:38:19Z on, and HB-193's registration); branch_only 0
main_duplicate 0; branch_duplicate 0
removed by HB-189's hand edit: 30730309, b1ab2033, dfa7ae1e (each x1); each is on main once now
```

## Observations, reported with this filing

1. A session that removes duplicated events by hand so that `seldon verify` passes in its worktree (HB-189 Part D
   item 15: "three events the kept-branch merge duplicated removed (main had reconciled them already)") is the branch
   whose later rebases restored those lines, every round. Which replayed commit restores them was not isolated.
2. `seldon verify` in a worktree whose `docs/decisions/register/pending/` holds pending records raises
   `KeyError: 'record_hash'` at `seldon/core/decisions.py:772` (`Record.last_hash`), from `check_decisions`
   (`seldon/commands/verify.py:248`). Reproduced first-hand by HB-193 on 2026-11-16 with HB-189's 21 pending
   records present (13 accepts, HBD-442..454, and 8 amendments) (hazbrief `logs/hb193/verify1.txt`); with the pending directory moved aside for
   one run, verify reports 0 issues. HB-189's own session hit it before its hash refresh and worked around it the same way.

No fix is proposed here.
