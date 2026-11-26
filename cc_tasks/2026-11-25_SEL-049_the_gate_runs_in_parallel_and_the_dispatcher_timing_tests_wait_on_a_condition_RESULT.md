# RESULT: SEL-049. The gate runs at `-n 6`, and three dispatcher tests wait on a condition instead of a clock

- **The three tests:** `two_disjoint` now overlaps by a rendezvous, not by `sleep: 3`. `exclusive_waits` holds r until
  the test has read the second pass, not for `sleep: 3`. `killed_supervisor` reads the session's own marks after it
  waits for the session to be gone, not `< 30` s on the test's clock. Each test's assertions are kept, and each
  gained one or two (per test below). They passed **10 of 10** alone, all 14 tests of the file each time. Under 20
  busy loops (load about 45), main's `two_disjoint` failed 2 of 3 and this branch's passed 3 of 3.
- **The full `-n 6` run was green except for `union_merge`, the one failure the task allows:** `gate_command` exactly
  as it now reads, **1,573 s (26:13)**, 3,558 passed, 1 failed (`test_union_merge_of_two_event_appends_is_valid`),
  7 skipped. Its cause is now visible: `merge_blocked`, `main_kept_moving` after 3 attempts. It is quoted below and
  not fixed here.
- **This merge's own gate is the last serial one.** The merge round runs main's serial `gate_command` under main's
  7,200 s ceiling once (about 81 to 124 minutes). Every full gate after it runs at `-n 6`: about 26 minutes quiet and
  about 40 loaded.

**Date:** 2026-11-26 (UTC; 2026-11-25/26 EST). **Branch:** `worktree-dazzling-yawning-oasis`, from main `d67f9ef`.
Work commit `98139c4`. Every run used that commit. This session did not merge, push or complete the task.
**Addenda read:** none exist (searched for `..._ADDENDUM*.md` siblings: none).
Recall used: none

The recall hits were read. The SEL-047 RESULT's content reached this task through its evidence README, which the task
names. No hit changed the approach beyond what the task file says. The old-against-new stress comparison follows
SEL-048's RESULT (`stress.sh`), which this task's `**After:**` names.

Changed: `tests/dispatch_scaffold.py` (the stub's rendezvous only), `tests/test_dispatch_parallel.py`, `seldon.yaml`
(`gate_command` and comments), `docs/evidence/sel049/**`, and this RESULT. Nothing under `seldon/`. Zero model calls,
no network. Nothing was filed into any repository and nothing was registered.

## Part A: overlap by rendezvous, budgets as ceilings on a waited condition

**Scaffold.** A stub spec may carry `"rendezvous": {"peers": [...], "ceiling_s": N}` (needs `mark`). After writing its
`start` mark, the stub polls the mark file until every peer has a `start` line, or gives up at `ceiling_s`. It then
writes `rendezvous_met` or `rendezvous_missed` and goes on, so a missed ceiling never hangs a test. A peer can be the
test itself, writing `<name> start <t>`. A spec without `mark`, `peers` or `ceiling_s` exits 2 and says so on stderr.
`sleep` and every other key are unchanged. The test file names the ceilings as constants: `RENDEZVOUS_CEILING_S = 60`,
under `_wait_settled`'s 90 s, and `SESSION_GONE_CEILING_S = 20`.

Per test, what is asserted before and after:

- **`test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge`.**
  - Before: both stubs `sleep: 3`. It asserted 2 launches in one pass, then the overlap
    `a.start < b.end and b.start < a.end`, then both completed, both files and both RESULTs on main, the worktrees
    removed, the branches kept, main pushed, the primary clean, both finishes `merged`, and c10/c11 ok.
  - After: each stub waits at a rendezvous for the other (ceiling 60 s). Every assertion above is unchanged, and
    `rendezvous_met` is asserted for both before the overlap.
  - The overlap now holds whenever both launch in one pass, however long b's launch takes. If the dispatcher held b
    until a ended, a would miss the rendezvous, and both the new assertion and the overlap fail. So the test still
    detects serialization; it no longer detects a slow machine.
- **`test_an_exclusive_task_waits_for_running_ones_and_blocks_new_ones`.**
  - Before: r `sleep: 3` had to outlast registering x and b plus the second pass. SEL-047's one failure saw r's merge
    under way (`dirty_tree`) instead of `exclusive_waits`. It asserted: pass 1 launches 1; pass 2 launches none and
    prints `waits (exclusive_waits) on r` and `waits (exclusive) on x`; x runs in place in a worktree and completes
    while b stays proposed; then b runs; the mark order is `r.end <= x.start` and `x.end <= b.start`; all complete.
  - After: r rendezvouses with the peer `checked`, which the test writes after the second pass returns. It writes it
    in a `finally`, so a raised pass still releases r. Every assertion is unchanged, and `rendezvous_met` is asserted
    for r. So r is running at the second pass by construction. The `< 30` s budget the task names is not in this test
    (that phrase fits `killed_supervisor`); its implicit budget was the `sleep: 3`.
- **`test_a_killed_supervisor_is_marked_by_the_next_pass_and_its_worktree_kept`.**
  - Before: `time.monotonic() - started < 30`, measured from before the first pass, standing for "killed
    mid-session, not after it" (the session sleeps 60 s). SEL-047: 31.0 s under load.
  - After: the stub writes marks and a pidfile. After the kill the test waits for the session's process to be gone
    (`D.pid_alive`, ceiling 20 s), then asserts the session wrote `start` and never wrote `end`.
  - Kept unchanged: STALE once, `blocked`, `holder_gone`, the kept worktree's partial file, the lease held and dead,
    no `EXIT=` in the log, and the reap.
  - This is stronger than before. The old budget passed if the session was still alive (unkilled) at 29 s. The new
    form requires the session to be dead and to have stopped before its end.

**Runs** (rows on `docs/evidence/sel049/runs.jsonl`, table in its README). `alone_dispatch_parallel_01..10`: the
file alone, gate form, random order on. **10 of 10 passed, 14 of 14 tests each**, 431 to 435 s, 1-minute load 4.5
to 13.2. `union_merge` passed all ten.

Added, because quiet passes prove little (SEL-048's reasoning): the three tests under 20 busy loops, main's copy
against this branch's (`stress20_{old,new}_{1,2,3}`).
- Main's `two_disjoint` **failed 2 of 3**, both once the load had reached about 44. a ran 11.2 s and 10.9 s, and b
  started 0.26 s and 0.07 s after a ended, SEL-047's form.
- This branch's passed **3 of 3**.
- The two budget tests passed in both versions at this load, so this comparison does not distinguish them. Their fix
  rests on construction.

Acceptance check (Part A), run after the sequence: **passed**.

## Part B: the full tier runs at -n 6

- `seldon.yaml`: `gate_command` gains `-n 6`, and the pa002 `--deselect` stays. The comment above it gives the
  measured basis (SEL-047: serial 7,463 s against 2,193 to 2,508 s under the same load; 25:40 and 25:51 quiet,
  SEL-042). It also says pytest-randomly reorders every gate run. `gate_timeout_s` stays 7,200, and a new comment says
  why: about three times the worst `-n 6` run, and a timeout is a red gate that costs a second full run.
- **Tests that pin the command's text: none.** Grep of `tests/` for `gate_command`, `no:cacheprovider`, `--deselect`
  and reads of the real `seldon.yaml`: every gate test builds its own scratch config. `seldon gate plan --base main`
  loads the new config: `full: requested: **Gate:** full`, also `gate_config_changed: seldon.yaml`,
  `unmatched: tests/dispatch_scaffold.py`.
- `full_n6_1`: `gate_command` read from this tree's `seldon.yaml`, run verbatim by `/bin/sh -c` from the tree's root
  with `SELDON_PRIMARY_CHECKOUT` set, as `gate_plan.run` does. **1,572.8 s; 1 failed, 3,558 passed, 7 skipped.**
  1-minute load 6.9 before, about 21 mid-run. The one failure is `union_merge`. Its message, as SEL-048 made it
  (the `finished` list is cut at b's record; the full text is `docs/evidence/sel049/logs/full_n6_1.log` lines 83
  to 107):

```
E       AssertionError: states {'a': 'blocked', 'b': 'completed'}
E         finished [{... 'source_file': 'cc_tasks/b.md', ... 'outcome': 'merged', 'merge': {... 'attempts': 1 ...}},
E                   {... 'source_file': 'cc_tasks/a.md', ... 'wall_clock_s': 7.975, ... 'ok': False,
E                    'outcome': 'merge_blocked', 'merge': {'reason': 'main_kept_moving', 'files': [], 'attempts': 3}}]
E         --- a
E         session exit=0 result_committed=True graph=in_progress model=claude-opus-5-5 (requested claude-opus-5-5) classifier_blocks=0
E         record: record: dispatch_worktree_named, gate_run 95de4e87 — 2 line(s) written by dispatcher; reconciled by the standing dispatcher (event_store, AD-038-R1) -> cd07c6d
E         record: record: dispatch_worktree_named 956d8d2c — 1 line(s) written by dispatcher; reconciled by the standing dispatcher (event_store, AD-038-R1) -> 4d75f25
E         reconcile: 1 event line(s) of kept .claude/worktrees/a union-merged into seldon_events.jsonl (merge_blocked; task blocked)
E         MERGE BLOCKED 95de4e87 (main_kept_moving): -; worktree .claude/worktrees/a kept; issue 409b0b8d
E         ...
E         --- b
E         session exit=0 result_committed=True graph=in_progress ...
E         record: record: gate_run 956d8d2c — 1 line(s) written by dispatcher; ... -> b6ffc9d
E         merged 956d8d2c worktree-b at 438b507c (attempt 1, regated=False)
E         sweep: removed .claude/worktrees/b (branch worktree-b kept)
E         record: record: artifact_updated, artifact_state_changed, dispatch_finished, worktree_removed 956d8d2c — 4 line(s) ... -> 17045df
E         push: pushed 5 commit(s)
```

  So SEL-047's "cause not determined" now has a reading. While b merged, b's merge and the dispatcher's record commits
  for both tasks moved main. a's merge saw main move on each of its 3 attempts (the dispatcher's default
  `merge_attempts: 3`) and blocked with `main_kept_moving`. Whether the record commits should count as "main moving"
  for a peer's merge is a question for the dispatcher. The review finding behind
  `test_a_busy_shared_ledger_does_not_cost_a_merge_attempt` treats housekeeping moves as free. That is a code
  question under `seldon/`, and this task does not answer it.

Acceptance checks (Part B): both **passed**.

## Part C: the record, and what the next gate will cost

`docs/evidence/sel049/README.md` has the ten alone runs, the full run, the stress comparison, and the lease table:

| gate | lease hold (≈ full tier wall time) |
|---|---|
| serial, main until this merges | 81 to 96 min quiet; 124 min (7,463 s) loaded, over the 7,200 s ceiling |
| `-n 6`, SEL-047 loaded | 37 to 42 min |
| `-n 6`, SEL-042 quiet | 25:40, 25:51 |
| `-n 6`, this task | **26:13** |

- A seldon full gate should now hold the lease for about a third as long as before.
- **This task's own merge is the last serial gate:** main's command, about 81 to 124 minutes, once.
- If that serial gate is red, the likely ids are `union_merge` or the `lock_wait` test SEL-048 fixed. The merge log
  will name them (factory F-027 item 2: a second red parks the task).

For factory (read here; nothing filed):
1. Once this lands, the one known intermittent in the full tier is `union_merge`. It failed 1 of 1 `-n 6` runs here,
   0 of 10 alone, and 2 of 20 alone in SEL-047. Its cause is `main_kept_moving` from record commits during a peer's
   merge (above). A fix is under `seldon/` and gates full.
2. SEL-050 still owns the pa002 `--deselect`.

Acceptance checks (Part C): `grep -q "lease" docs/evidence/sel049/README.md` **passed**. The diff-path check passes
on the committed branch (run after the RESULT commit).
