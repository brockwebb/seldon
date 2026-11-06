# AD-034 ADDENDUM 08: the merge requires the project's declared pass record for the tip, an unrunnable gate is a refusal, and the record never runs under the filing lock

**Date:** 2026-11-06. **Status:** Accepted. Implemented by SEL-024
(`cc_tasks/2026-11-03_SEL-024_the_merge_gate_requires_the_projects_declared_pass_record_for_the_tip_it_merges.md` and
its ADDENDUM 01), from the SQ11 work-order addendum
(`handoffs/2026-10-30_desktop_sq11_work_order_addendum_01_merge_gate_hand_dispatch_register_race.md`, W6).
**Amends:** AD-034's merge round (decision 3) and its callers under the pass (AD-034 ADDENDUM 02's re-merge, ADDENDUM
03's regate). **Applies:** AD-037-R15 (the declared interpreter), AD-038-R20 (the filing lock), squiddy DN-043 R-188 and
DN-052 R-237 (squiddy's own rules; seldon reads them, it does not restate them). Three new rulings, AD-034-R16 to R18.
**Code:** `seldon/core/gate_record.py` (new); `seldon/core/dispatch.py` (`load_dispatch_config` parses
`dispatch.gate_record`); `seldon/commands/dispatch_worktree.py` (`_merge`, `_ensure_record`, `record_pass`,
`record_ready_under_lock`, `record_pending`, the re-merge and regate prechecks, `pass_parallel`);
`seldon/commands/dispatch.py` (`_record_pending` after `_release_filing`; `seldon dispatch regate` runs the record).
**Tests:** `tests/test_sel024_gate_record.py`.

## 1. Evidence

1. **Merges with no pass record.** On squiddy main four tasks merged between the 2026-10-27 kit pass (`bc345c09`) and
   SQ-099's (`d31501c7`) with no line in `kit/ledger/passes.jsonl`, and SQ-101 merged at `67cde2da` with none (W6).
   squiddy's DN-043 R-188 requires a pass per kit commit; DN-052 R-237 makes the ledger main's.
2. **"Environmental" passed.** SQ-101's RESULT classed 17 failures as worktree-environmental and said ruff was not
   installed in the kit venv, so no lint ran. The merge round read the session's exit, its committed RESULT and its
   Stop gate; it had no reading of its own of the project's rule, so a session's classification was the gate.
3. **The filing lock window (SEL-024 ADDENDUM 01 section 1).** Since AD-038-R20 the pass holds the filing lock from
   before its sweep to after candidacy. The re-merge (`remerge_breaker_green`) and the regate both run inside that
   window and both call `_merge`. squiddy's record command is a full kit pass, three runs of about 36 minutes each
   (the 2026-10-30 lines of `kit/ledger/passes.jsonl`: 2201.0 s, 2178.8 s, 2154.7 s), against a filer's 120 s wait.

## 2. Prior art

- **Required status checks on the exact head commit.** GitHub's branch protection ("Require status checks to pass
  before merging") binds a status to a commit SHA, and a push that changes the head discards it; GitLab's "Pipelines
  must succeed" does the same. Adopted: a ledger line names a commit and covers only that commit's content.
- **The Not Rocket Science Rule** (Graydon Hoare, 2014, from the Monotone and Rust practice; bors, Zuul and the merge
  queues that implement it): "automatically maintain a repository of code that always passes all the tests", which
  means testing the tree that will land, not a branch that will be rebased. Adopted: coverage is checked on the tip
  the round is about to fast-forward, after its rebase, and again under the lease after any housekeeping rebase.
- **Reproducible builds** (reproducible-builds.org's definition: given the same source, any party recreates
  bit-for-bit identical artifacts). Adopted at git's own unit, the tree: a recorded commit and the tip that carries
  its ledger line on top are the same source. squiddy's `kitpass.pass_for` already applies it to the `squiddy/` tree
  (check_pin.kit_matches). seldon reads a project's ledger by the project's own scope (`tree_paths`), not a stricter
  one of its own: under the whole-tree default a 108-minute gate is outrun by every task file filed meanwhile.
- **Measurement system analysis: an instrument that gives no reading is not a pass** (AIAG, *MSA* reference manual).
  Applied as the stations already apply it (`seldon.core.stations.run_check`, AD-037 ADDENDUM 02: 126 and 127 and a
  usage error are `unrunnable`, which opens a huddle and never counts as a pass). The gate reuses that classifier and
  adds a project's declared `requires` and `unrunnable_exits`, and python's own `No module named` for its `-m` module.
- **Lock scope: hold a lock for the critical section only.** The lock-holder-preemption and convoy literature (Blasgen,
  Gray, Mitoma and Price, "The Convoy Phenomenon", 1979) is why a long operation is moved out of a lock rather than
  waited out by the lock's other users; AD-038-R20 states the same departure ("a filer never waits on a session").
- **Internal.** squiddy's DN-043 R-188 and DN-052 R-237 (the rules); `seldon.core.pass_ledger` (SQ-096: a project's
  rule lives in the project and seldon only runs it, the pattern followed here); AD-034-R10 (regate in place) and
  AD-034 ADDENDUM 02 (re-merge) are the locked callers; AD-038-R20 the lock.

These sources are cited by their published names and were not fetched (Network: none beyond git).

## 3. Rulings

- **AD-034-R16. When a project declares `dispatch.gate_record`, the merge round merges a tip only when the ledger the
  tip carries holds a pass covering the tip's tree.** The declaration names the command that records a pass, the
  tracked JSONL ledger it appends to, the field of a line naming the commit (`commit_field`) and the field that is
  `true` on a pass (`pass_field`), the command's `timeout_s`, and optionally `requires`, `unrunnable_exits` and
  `tree_paths`; `gate_record: none` declares no ledger, and an absent key keeps today's round. A line covers the tip
  when the commit it names differs from the tip, under `tree_paths` (absent: the whole tree), only in the ledger and
  in the round's housekeeping (`merge=union` files and `shared_paths`); the newest covering line decides. With no
  covering pass the round runs the command in the worktree, under the declared interpreter (AD-037-R15), outside the
  pass lease, commits the line it appended on the branch (`gate_record: ...`), and checks again; still uncovered, it
  blocks the task `merge_blocked` with reason `pass_unrecorded`, naming the ledger, and the redrive that answers any
  merge block applies. The check is repeated under the lease after any housekeeping rebase. The merge record carries
  `gate_record` (the coverage, whether the command ran, its reading and the ledger commit), and every run writes
  `gate_recorded`.
- **AD-034-R17. A gate that could not run is `gate_unrunnable`: a block, a huddle naming what it lacked, and no
  record.** A declared `requires` tool not on the gate's PATH, the shell's 126 or 127, a usage error, python's `No
  module named` for the command's module, or a declared `unrunnable_exits` code is no reading. The round blocks the
  task `merge_blocked` with reason `gate_unrunnable`, opens a `huddle` (`reason: gate_unrunnable`, `tools`, `command`,
  `tip`) that stays open until one names its gate, restores the ledger as the branch had it and commits nothing. A
  session's classification of its own failures as environmental is never read.
- **AD-034-R18. The gate command never runs while the pass holds the project's filing lock.** The re-merge and the
  regate, which a pass runs under the lock, read the ledger only (a file read). An uncovered tip is not handed to the
  round: the task is left as it was and `gate_record_pending` is written. After `_release_filing`, before any launch,
  the pass's record step runs the command for each pending task still blocked with its worktree on disk (rebased onto
  main), unless that tree is covered or already recorded, and commits its `gate_recorded` lines; the next pass merges
  on the record. A tree whose record already ran and did not pass is handed to the round, which blocks it
  `pass_unrecorded` or `gate_unrunnable`, naming the record. The post-session round and `seldon dispatch regate`,
  which hold no filing lock, run the command themselves. **Choice and reason (ADDENDUM 01 section 1 offered three):**
  the third, "the locked paths leave the record to a path outside the lock", because the other two move work the lock
  protects. Running the gate before the merge round on the post-session path does not reach the re-merge and regate,
  whose sessions never reached the round. Releasing the lock around the gate would mean re-acquiring it before the
  fast-forward and the reconcile, and a re-acquire that times out leaves a task walked to `in_progress` with no finish
  and a pass that no longer holds the lock its reconcile and candidacy assume. The cost of the choice is one pass of
  latency on a deferred task (five minutes at seldon's and squiddy's `poll_interval_s`) against a gate of up to two
  hours.

## 4. What a project declares

seldon keeps no pass ledger; its seldon.yaml declares `gate_record: none`. squiddy's declaration is the return filed by
SEL-024 into squiddy's `cc_tasks/` (its RESULT names it): squiddy writes it, since the ledger, the command, its exits
and the tree a pass covers are squiddy's rules (DN-043 R-188, DN-052 R-237, `kitpass.pass_for`).
