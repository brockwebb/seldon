# AD-034 ADDENDUM 11: a session the dispatcher stopped is never merged, nothing merges without gate evidence, the disk station reads a run against its allowance, and the merge round cannot refuse its own fast-forward

**Date:** 2026-11-21. **Status:** Accepted. Implemented by SEL-042 Parts B and C
(`cc_tasks/2026-11-21_SEL-042_a_stopped_session_is_never_merged_or_completed_the_merge_round_cannot_refuse_itself_and_verify_reads_pending_records.md`),
from hazbrief-mcp's filings `de40f402` (2026-11-18) and `6a9c00fa` (2026-11-16). **Amends:** AD-034's decision 4 and
AD-034-R5 (merge on green) by naming what "green" must be on the record; AD-037-R6's disk station for a running
session. **Extends:** AD-034-R19 (every journal is committed before the fast-forward) to the round's own lines. Four
new rulings, AD-034-R25 to R28.
**Code:** `seldon/commands/dispatch_worktree.py` (`finish_session`, `launch_hard_stops`, `gate_evidence`, `_merge`,
`_finish_unmerged`); `seldon/commands/dispatch.py` (`_gate_reading`: `checks_run`); `seldon/core/dispatch.py`
(`disk_in_run`); `seldon/commands/dispatch_stations.py` (the station's disk reading).
**Tests:** `tests/test_sel042_stopped_session_never_merges.py`; `tests/dispatch_scaffold.py` (the scaffold's project
declares `gate_command: true`).

## 1. Evidence

1. **Two hard-stopped sessions were merged and completed.** hazbrief HB-197 (`f6a8bca3`) was stopped by the
   dispatcher's `disk_ceiling` at 15:29:25Z on 2026-11-18 (event `c3163e6c`), the stop was delivered at a tool boundary
   (`0406da34`), and its Stop gate then recorded `pass` over three Parts whose `checks` were all empty (`37465e8c`). The
   round merged it at 15:37:12Z with `regated: false`, `gate: null` (`e214e7d7`) and completed it. HB-198 (`7989e01b`)
   went the same way: stop `5d755186` at 16:02:46Z, Stop gate `pass` with no Part (`b33be2ca`), merged and completed at
   16:07:09Z (`b650f591`), and its successor HB-199 launched. The finish never read the stop, and it read a gate that
   ran nothing as a pass. The fixture is cut from hazbrief's store (`tests/fixtures/sel042/hb197_hb198_events.jsonl`,
   `docs/evidence/sel042/cut_fixture.py`); on the code before this addendum the reproduction merges
   (`docs/evidence/sel042/reproduction_old_code.txt`).
2. **What the disk station read.** At launch c12 measured HB-197 at 16,870,010,880 bytes free against a need of
   4,982,362,106 (twice a 2,491,181,053-byte tree) and HB-198 at 14,122,819,584 against 4,993,090,550. During each run the
   station read the same `free >= need` test on the project's volume, and stopped HB-197 at 4,073,521,152 and HB-198 at
   4,563,726,336 free. The volume had lost 12.80 GB and 9.56 GB since launch: 2.57 and 1.91 times each run's need. HB-198's
   own record (`hazbrief docs/evidence/hb198/disk.txt`) shows where: its worktree (made before its first reading), a
   clean clone in `/tmp` of 3.78 GB with its install, and that clone's gate, which ran the volume from 7.85 GB to 4.56 GB
   free before the stop and gave 3.7 GB back when the clone was deleted. The filing's "twice its footprint" (10.46 GB)
   was read after the worktree was made.
3. **The round refused its own fast-forward.** hazbrief HB-189's merge (`f61999a7`, 2026-11-16) was blocked
   `ff_refused` after three attempts over `seldon_events.jsonl`. Under the lease `_merge` committed main's journals,
   rebased over that commit, dropped the branch's copies of three reconciled lines (`dedupe`), and appended
   `kept_events_deduped` to main's store before `git merge --ff-only`; the branch also changed the store, so git
   refused to overwrite it. Replaying the branch here (`docs/evidence/sel042/hb189_replay.txt`) shows which commit
   restores the lines: HB-189's own `docs(HB-189 Part C item 9)` commit (`8dbe12c4` and `f9f168f6` before the rounds'
   rebases, `34984e36` on the final branch) appended the session's three `artifact_updated` lines (07:39:30Z to
   07:39:32Z) that the kept-events reconcile later put on main; every rebase replays that append onto a main already
   holding them. The later removals (the session's hand edit `9e977247`, each round's drop commit) do not survive the
   replay: `merge=union` resolves the conflicting hunk at the store's end by keeping both sides.

## 2. Prior art

### External

- **Fail-safe defaults** (J. H. Saltzer and M. D. Schroeder, "The Protection of Information in Computer Systems",
  Proceedings of the IEEE 63(9), 1975, design principle (b)): "Base access decisions on permission rather than
  exclusion", so that a missing check denies rather than allows. Adopted for the merge: absent evidence of a pass is not
  a pass. Cited from memory and not fetched (Network: none). The library arm was searched for it
  (`seldon prior-art search --library "fail-safe defaults protection of information"`, 2026-11-21): neither
  seldon-biblio nor the squiddy library holds it; the nearest row, NASA SWE-072's "initialized ... to a known safe
  state", is a different principle.
- **Kubernetes node-pressure eviction and ephemeral-storage limits** (kubernetes.io, "Node-pressure Eviction" and
  "Local ephemeral storage"): a pod's own ephemeral-storage use is counted against the pod's declared limit, and the
  node's free-space thresholds are a separate signal. Adopted: the disk station separates the run's allowance (what it
  was admitted with) from the volume's state. Departed from in one respect, said in R28: the station has no per-run
  accounting, so the volume's loss since launch stands in for the run's own use. Cited from memory and not fetched;
  the library arm (`"node-pressure eviction ephemeral storage"`) holds neither page.
- **git's union merge driver** (gitattributes(5), "Built-in merge drivers": `union` "will take lines from both versions
  ... the order is undefined"): a deletion on one side that overlaps an append on the other is kept from neither, so
  both copies survive. This is the mechanism behind evidence 3.

### Internal

- internal receipt: query "merge on green" | repo seldon@6a74a6a82c5c73c7f40fc91952bfc9f0d46b477f | hits docs/design/AD-034_ADDENDUM_03_kept_work_is_regated_in_place.md:3, handoffs/2026-10-30_desktop_sq11_work_order_addendum_01_merge_gate_hand_dispatch_register_race.md:11, docs/decisions/register/00209_seldon-ad-034-r5_accept.yaml:1, handoffs/2026-10-30_desktop_sq11_work_order_addendum_01_merge_gate_hand_dispatch_register_race.md:7
- internal receipt: query "hard stop" | repo seldon@6a74a6a82c5c73c7f40fc91952bfc9f0d46b477f | hits docs/design/AD-037_ADDENDUM_01_spend_floor_tool_boundary_liveness.md:36, docs/design/AD-037_ADDENDUM_01_spend_floor_tool_boundary_liveness.md:1, docs/decisions/register/00293_seldon-ad-037-r12_accept.yaml:1, docs/design/AD-037_ADDENDUM_04_a_terminal_task_stops_its_session.md:3
- internal receipt: query "gate_record" | repo squiddy@0a00d72d79c1799fc095f5b2cd25904318aecad6 | hits docs/design/2026-11-06_DN-057_the_merge_requires_a_kit_pass_record_and_the_rounds_line_reaches_main.md:73, docs/decisions/register/01041_squiddy-r-251_accept.yaml:1, docs/design/2026-11-06_DN-057_the_merge_requires_a_kit_pass_record_and_the_rounds_line_reaches_main.md:3, docs/design/2026-11-15_DN-062_ADDENDUM_01_the_escaping_test_errors_by_name_and_the_keys_are_set_before_the_pass.md:28

What the record already held: AD-034-R5 (merge on green), SEL-024's declared pass record (AD-034-R16 to R18), the
regate of kept work (AD-034-R10), SEL-034's terminal stop (AD-037-R16) and AD-037-R12's hard stop at the tool boundary.
Each was right alone. The hole was between them: the finish asked whether the Stop gate said `pass`, not whether
anything had been checked, and it never asked whether the dispatcher had stopped the session. squiddy's DN-057 is the
same principle for squiddy (no kit pass record, no merge); this addendum makes it every project's.

## 3. Rulings

- **AD-034-R25. A session that ended after a dispatcher hard stop of its launch is never merged or completed: the task is blocked `hard_stopped: <reason>` whatever its RESULT or its Stop gate says, its worktree is kept, and no successor is released from it.**
  The stops read are the launch's `session_stop` records of kind `hard` (the spend and disk ceilings). A terminal task
  is answered first by SEL-034's rule, as before. Nothing redrives a hard stop automatically: it is not one of
  `AUTO_REDRIVE_REASONS`, so a person or Desktop redrives it (AD-038-R2).
- **AD-034-R26. A branch merges only on recorded evidence that a gate passed for the tip being merged: the project's declared pass record, the round's re-gate, a kept branch's regate of its declared checks, or a Stop gate that passed after running at least one check. With none of these the round runs the project's `dispatch.gate_command` in the worktree and merges only if it passes; a project with no gate command blocks the task `ungated` and keeps its worktree.**
  A Stop gate that passed with no check to run verified nothing and is not evidence (Saltzer and Schroeder's fail-safe
  default). The merge record carries `gate_evidence` naming which evidence it merged on; a red gate run for want of
  other evidence is `regate_red` with `evidence_gate: true`. `regated` keeps its meaning (re-gated because main changed
  a file the branch changed).
- **AD-034-R27. The merge round writes nothing to main's tracked files between its journal commit and its fast-forward.**
  The `kept_events_deduped` records a round owes are held in memory and written after the fast-forward, or in the
  unmerged finish when the round gives up; both are followed by the finish's own journal commit.
- **AD-034-R28. During a run the disk station stops a session only when the volume has lost more than the run's allowance since launch (the `need_bytes` its launch was admitted with) and free space is below that need; inside its allowance a run is never stopped for disk it is using itself.**
  The allowance is c12's measured need at launch (factor times the tree), and the loss is read on the volume
  (`consumed_bytes`), an upper bound on the run's own use: anything else writing to the volume counts against it too.
  A launch recorded without a c12 reading is read as before (`free >= need`). The reading carries
  `launch_free_bytes`, `allowance_bytes`, `consumed_bytes` and `within_allowance`.

## 4. What the rulings change for each project

- **hazbrief-mcp** declares a gate command and no pass record. A task whose Parts declare no check is now merged on the
  round's own run of that command, so its gate runs twice (the session's and the round's). Both HB-197 and HB-198 used
  more than their allowance, so R28 would have stopped both, and R25 would then have blocked both, unmerged.
- **seldon** declares a gate command (the full suite) and no pass record: the same, at the suite's wall time per merge.
- **squiddy** declares a pass record: unchanged (SEL-024's record is the evidence).
- **factory** declares neither: a factory task whose Parts declare no check is blocked `ungated` until factory declares
  a gate command or its tasks declare checks. That is the rule working, and the RESULT says so to its operator.

## 5. What this does not change

HB-197 and HB-198 stay completed in hazbrief's graph as hazbrief recorded them: seldon does not rewrite another
project's graph, and `completed` has no edge back. The OODA between chained tasks (AD-038-R16) still reads a completed
task's RESULT and releases its successor; R25 means a hard-stopped task is never completed, so it never reaches that
step. What counts as dirt, the stations' other stops and the launch's c12 admission are unchanged.
