# AD-038 ADDENDUM 08: a hand-dispatched task is refused by the dispatcher, a task file is written and registered in one call, and every pass pushes

**Date:** 2026-11-06. **Status:** Accepted. Implemented by SEL-023
(`cc_tasks/2026-11-03_SEL-023_a_consumer_filing_is_a_kind_the_registrar_accepts_and_a_desktop_commit_reaches_origin.md`),
from the squiddy SQ11 work-order addendum
(`handoffs/2026-10-30_desktop_sq11_work_order_addendum_01_merge_gate_hand_dispatch_register_race.md`, W7 and W8) and
squiddy's filing of 2026-11-03 (observations 3 and 6, and its ADDENDUM 01). **Amends:** AD-034 decision 2 (where the
pass pushes); SEL-004 decision 3 (a task that fast-forwards main is now declared, not remembered). Three new rulings.
**Code:** `seldon/core/dispatch.py` (`HEADER_DISPATCH`, `parse_dispatch`, `dispatch_hand` in `static_checks` and
`evaluate`); `seldon/core/filing.py` (`filing_lock`, `file_task`); `seldon/commands/cc.py` (`seldon cc file`);
`seldon/mcp_server.py` (`seldon_cc_file`; `seldon_commit_governed` registers); `seldon/core/desktop_commit.py`
(`register_committed_tasks`); `seldon/core/returns.py` (the return is written under the consumer's lock);
`seldon/commands/dispatch.py` (`_filing_guard`, `_push_unless_tried`, `_pushing`, the lease-held push);
`seldon/commands/dispatch_worktree.py` (`pass_parallel` releases the lock before launching); `seldon/commands/task.py`
(`task update --dispatch`). **Tests:** `tests/test_sel023_filing_kind_hand_dispatch_file_and_push.py`.

## 1. Evidence

1. **"Hand-dispatched" was not a header.** squiddy SQ-050RM (`e1df72ef`) was registered as hand-dispatched (it
   fast-forwards main, SEL-004 decision 3); its `blocked` state was set within two minutes, and the dispatcher
   launched it first. The session replayed onto a branch instead; the protection was luck (W7).
2. **Write-then-register races the pass.** squiddy, 2026-10-30, twice: a Desktop wrote a task file and registered it
   about a minute later, and the 5-minute pass between saw an untracked file and refused every task on c7 (W8). Once
   more on 2026-11-03, between AR-7's write and the squiddy thread's `seldon_commit_governed` (the filing, observation
   3). The lesson "write and register in one step" was in a squiddy handoff only one thread reads.
3. **Where the pass did and did not push.** seldon's own log, 2026-11-03: the Desktop commit `428a4c89` (13:07:54Z)
   left at the next pass, 13:11:50Z (`push: pushed 1 commit(s)`): a pass with nothing eligible already pushed. The
   passes that did not were those that exited on a held lease, those that saw a claim in flight, and those the graph
   outage ended; and launchd starts no pass while a serial holder's job instance runs its session, so a Desktop commit
   made during an hour's session waited the hour. squiddy's addendum measured the effect as "on a schedule set by
   whatever else happens to run" (observation 6). The operator pushes nothing by hand.

## 2. Prior art

- **An atomic publish under mutual exclusion.** A reader that may observe only finished writes is a transaction's
  isolation (Gray and Reuter, *Transaction Processing: Concepts and Techniques*, 1993, the isolation chapter: no
  reader sees another writer's uncommitted state); between cooperating processes on one host the standard primitive
  is `flock(2)` advisory locking. Adopted: one flock, held by the filer over write, commit and register and by the
  pass over the part that reads the tree. Departure: the lock is not held over the pass's launch, so a filer never
  waits on a session (a serial launch holds the dispatch lease for the whole run, which is why the lease itself was
  not reused as this lock).
- **Internal:** the dispatcher's lease (`seldon.core.dispatch.Lease`, DD-019) and `acquire_waiting` are the
  primitive, reused; `write_return` (AD-036-R16) already wrote and registered in one call and now holds the lock too;
  AD-034 decision 2 ("the dispatcher pushes what it commits; a failed push is retried by the next pass") is the push
  rule extended to every pass.

These sources are cited by their published names and were not fetched (Network: none beyond git).

## 3. Rulings

- **AD-038-R19. A task file headed `**Dispatch:** hand` is never launched by the dispatcher.** Registration accepts
  it and records `dispatch_mode: hand` and, from the prose after `hand`, `dispatch_launcher`. The dispatcher lists it
  as not a candidate under its own reason, `dispatch_hand`, read from the graph before the file, with a reason line
  naming who launches it. `**Dispatch:** dispatcher` is the default; any other value is refused
  (`dispatch_unparsable`). `seldon task update --dispatch hand|dispatcher` sets it on a registered task.
- **AD-038-R20. A task file is written, committed and registered in one call, under the project's filing lock, and
  the pass reads the tree only while it holds that lock.** `seldon cc file --project <repo> --content-file <path>`
  and the MCP tool `seldon_cc_file` write the file into the repository's `cc_tasks/`, refuse an existing path, and
  register it through `register_task_file` (which commits it through the hooks, with AD-038-R18's retry), holding
  `filings.lock_file` throughout; a refusal deletes the file. The dispatcher's pass takes the same lock (waiting up
  to `filings.lock_wait_s`) before its sweep, reconcile, cadence and candidacy, and releases it before any launch; a
  pass that cannot take it evaluates nothing and says so. `seldon cc return` writes and registers under the
  consumer's lock. `seldon_commit_governed` and `seldon commit-governed`, given a base task file under `cc_tasks/`
  that no task holds, register it in the same call after the commit; a refused registration leaves the file
  committed (a clean tree) and is reported.
- **AD-038-R21. Every pass ends by pushing what the branch is ahead by.** Whatever the pass found (nothing eligible,
  a claim in flight, the graph down, the filing lock held), it pushes once unless it already tried at the same HEAD;
  a pass that finds the lease held pushes before it exits; and a serial holder pushes on each inspection tick while
  its session runs. The pass prints `push:` as before. A failed push is retried by the next pass, which begins with no
  memory of the last one's attempt. A STOP file, `dispatch.enabled: false`, an inherited API key and a missing commit
  gate still end the pass before anything, the push included: each is the operator's or the gate's stop.

## 4. Details

1. **Why `git push` beside a running session is safe.** It reads refs and objects and updates a remote-tracking ref;
   it touches no working tree and takes no `index.lock`. Since FRICTION-002 every session works in its own worktree.
2. **Why a pass that cannot take the filing lock is not a refusal event.** It is a standing condition lasting
   seconds, which DN-006 decision 7 keeps out of the log; the line is printed to the wrapper's log.
3. **What the race still allows.** A Desktop that writes a file through the Filesystem tools and only then calls
   `seldon_commit_governed` still leaves the file untracked between its two calls; the cure is `seldon_cc_file`, which
   the Desktop section of `seldon go` now names.
