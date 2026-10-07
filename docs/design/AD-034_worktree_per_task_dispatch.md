# AD-034: Parallel dispatch. A task runs in its own git worktree when its declared resources are disjoint from every running task's; independence is declared, never inferred

**Date:** 2026-10-07
**Status:** Accepted. Implemented by SEL-004 (`cc_tasks/2026-10-07_SEL-004_worktree_per_task_dispatch.md`, task aa428cde).
**Implements:** ai-readiness-kg DN-013-R3, as corrected by DN-013 ADDENDUM_01 A2.
**Extends:** ai-readiness-kg DN-006 (the standing dispatcher): decision 2's c6, decision 4's finish, decision 6's lease, decision 9's FIFO.
**Code:** `seldon/core/dispatch.py` (grammar, overlap, planner, config), `seldon/core/worktree.py` (git and lock primitives), `seldon/commands/dispatch_worktree.py` (the parallel pass, the supervisor, the merge).

## 1. The condition

The dispatcher ran one task at a time because every session shared one working tree, and DN-006 §5 set concurrency to one because "the file-ownership model that would license 2 is undesigned and untested". A shared checkout is already unsafe with one dispatched session: on 2026-10-07 ai-readiness-kg's recollection suite died at 35% with no EXIT line at 02:17:51Z when a Desktop session committed in the same checkout (`ai-readiness-kg/cc_tasks/2026-10-06_absence_verdicts_recollection_RESULT.md`).

DN-013-R3 proposed worktrees and said "the precedes graph already says which tasks are independent". It does not. A `precedes` edge records an ordering a Desktop wrote down; its absence says nothing about whether two tasks write the same files, the same database, the same append-only logs or the same spend ledger. ai-readiness-kg tasks with no edge between them share all four.

## 2. Prior art

Named from canonical documentation and the literature; not re-fetched in this session.

- **Declared locks.** GitHub Actions `concurrency` groups: the workflow author names the key; the runner serializes on it. Make and Bazel: a rule declares its outputs and the scheduler runs disjoint rules in parallel. Both put the lock in the author's hand. Nothing here infers one.
- **Worktrees.** `git worktree` (git-worktree(1)): several working trees, each with its own index and HEAD, over one object store and one set of refs. It is the standard way to run parallel agent sessions on one repository.
- **Merge queue.** The "not rocket science rule" (Graydon Hoare, bors for Rust, 2014) and GitHub's merge queue: main only moves to a commit that was tested as it will land. Rebase onto the main it will land on, test, fast-forward only if main has not moved since.
- **Readers and writers.** Courtois, Heymans and Parnas, "Concurrent control with readers and writers" (CACM 14(10), 1971), second problem: writer preference, so a stream of readers cannot starve a writer. An exclusive task is the writer.
- **Leases and liveness.** Kubernetes `coordination.k8s.io/Lease` and Chubby (Burrows, OSDI 2006): a lease has an identified holder. DD-022's orphan rule, already the dispatcher's: a holder is gone when its PID is gone, never because of age.
- **Union merge.** gitattributes(5), `merge=union`: the built-in driver keeps both sides' lines. It cannot see a line that lost its newline or a record appended twice, so its result is checked.
- **One file, one lock.** `flock(2)` on the file itself for read, compute and append: ai-readiness-kg `kg/spend.py` (DD-022), adopted unchanged.

## 3. Decisions

- **AD-034-R1. Independence is declared per task, by resource, and the scheduler never infers it.** A task file may carry `**Exclusive:** yes|no` (absent means yes) and `**Touches:** <item>, ...`, where an item is a resource named under `dispatch.resources` in seldon.yaml or a repository-relative path glob, or `none`. A bare word must be a configured resource name, so a typo refuses instead of silently overlapping nothing. `Exclusive: no` requires `Touches`. A declaration that does not parse fails criterion c10 as `concurrency_undeclared`, with the grammar quoted, in serial mode as well as parallel. A header counts only at the start of a line, so a task that quotes the grammar in prose declares nothing. A task with neither header gets no c10 and behaves exactly as before.

- **AD-034-R2. The planner launches a non-exclusive task only when its Touches is disjoint from everything running or waiting ahead of it.** Candidates are taken in FIFO order by `created_at`. Two declarations overlap when they share a resource name or when any two of their path globs, including each resource's configured paths, may match one path. The glob test is sound and deliberately not exact: globs are normalised (`//` and `.` segments collapsed, lower-cased because the default macOS file system is case-insensitive), two globs are disjoint only when their literal prefixes, or their literal suffixes, are unrelated, and a literal path against a glob is decided by `fnmatch`. A task deferred for any reason reserves what it declared, so a later overlapping task cannot overtake it. An exclusive task launches only when nothing runs, and while it waits it holds everything (writer preference). `dispatch.max_parallel` caps the running set.

- **AD-034-R3. A non-exclusive task runs in its own worktree; an exclusive task runs in place, alone, as before.** Under `max_parallel > 1` a non-exclusive task is claimed, its claim committed to main, and `git worktree add <worktree_dir>/<stem> -b <branch_prefix><stem> <main HEAD>` cut, with a detached supervisor running the session there. An exclusive task runs in the primary checkout with the pass lease held for its whole run, through the same code a serial pass uses. `max_parallel` defaults to 1, and at 1 the pass is the pre-SEL-004 pass, held byte for byte against a recorded transcript.

- **AD-034-R4. Every write to main in the primary checkout happens under the pass lease; each worktree has its own lease, held by its supervisor.** The pass lease (`dispatch.lock`) is taken by a pass, which never waits for it, or by a finishing supervisor, which waits up to `merge_lock_timeout_s`. A per-worktree lease (`<lease_dir>/<stem>.lock`) names the supervisor's PID from the moment the pass starts it, so the next pass never sees a gap; its release record keeps the task, worktree and branch. A worktree session works only in its worktree, so the gates that ask whether a session is working in the primary checkout ask it of the in-place claim alone.

- **AD-034-R5. A worktree task merges on green and is never resolved by the dispatcher.** When the session exits 0 with its RESULT committed on its branch, the supervisor requires a clean worktree, rebases onto main, reruns `dispatch.gate_command` in the worktree when main changed a file in the task's write set (`merge=union` files excepted), checks every `merge=union` file the task wrote, checks the task's spec against its registered hash, then under the pass lease commits any pending record and shared-file lines and fast-forwards main only if main has not moved. A move made only of `merge=union` and `shared_paths` commits is rebased over inside the lease, since it cannot conflict and never triggers a re-gate; any other move, a refused fast-forward or a primary off its branch ends the round, up to `merge_attempts`. A rebase conflict, a red re-gate, an invalid union file, a modified spec, a refused fast-forward or a main that kept moving is `merge_blocked`: the task moves to `blocked`, `dispatch_merge: merge_blocked` is set, an Issue of type `merge_blocked` names the files and links `remediated_by` to the task, the operator is notified, and the worktree and branch stay as the session left them.

- **AD-034-R6. The dispatcher, not the session, completes a worktree task, and only after main carries its work.** The worktree prompt tells the session not to run `seldon cc complete`, merge, push or switch branches. After the fast-forward the supervisor walks the task to `completed` with `dispatch_merge: merged`, writes `dispatch_finished` with `outcome: merged`, pushes and removes the worktree. The graph never says `completed` for work that is not on main, so a successor's c2 cannot open on an unmerged predecessor.

- **AD-034-R7. Append-only files merge by union, and the merged content is checked before main moves.** `.gitattributes` marks them `merge=union`, and that attribute is the only list: the files git merges by union are the files the check reads. Each line the merge added (lines already on main are not the task's) must parse as a JSON object, and its `dispatch.union_unique_key` (default `event_id`) must not repeat a key already in the file; a failure is `merge_blocked` with reason `union_invalid`.

- **AD-034-R8. A file that must be one file across worktrees resolves to the primary checkout and is appended under its own flock.** A worktree session resolves such a file (a spend ledger) with `seldon.core.worktree.primary_checkout`, or `$SELDON_PRIMARY_CHECKOUT`, and appends under `seldon.core.worktree.locked`, the flock discipline `kg/spend.py` already uses, so parallel runs share one daily cap. A file listed in `dispatch.shared_paths` is committed by the pass under that flock when it is append-only against HEAD, and its appends are not dirt that c7 waits on.

- **AD-034-R9. A worktree task whose supervisor is gone is blocked by the next pass, and its worktree and lease are kept.** The pass reads each per-worktree lease. Once the supervisor has taken its flock, liveness is the flock, which the kernel drops at death and which is immune to PID reuse; before that it is the PID the pass recorded. A dead holder, or a lease released while its task is still `in_progress`, moves the task to `blocked` with `dispatch_finished.outcome` `holder_gone` or `released_unfinished`, terminates the process group the supervisor recorded so an orphaned session stops writing and spending, and notifies. The lease file stays for `seldon dispatch lease reap --task <stem>`, which refuses a live holder; nothing is reaped by age.

## 4. Premises corrected

1. **DN-013-R3's independence premise** (corrected by R1 and R2; DN-013 ADDENDUM_01 A2 already records it).
2. **DN-006 decision 9's FIFO never held.** `evaluate` dropped `created_at`, so `fifo` sorted on `("", task_id)`, a random uuid order. Found when SEL-004's recorded transcript flipped between runs; fixed, with a test over evaluated rows (`tests/test_dispatch.py::test_fifo_orders_evaluated_rows_by_created_at_not_by_task_id`). The recorded transcript is a run in which uuid order happened to agree with `created_at`.
3. **"Merge on green" left the completion unassigned.** A session that ran `seldon cc complete` before its merge would leave the graph `completed` for work that may never land, and `completed` has no edge back to `blocked`. R6 assigns the completion to the dispatcher.
4. **"Resolve the ledger to the primary" is half the fix.** ai-readiness-kg tracks `state/spend_ledger.jsonl` in git, so appends in the primary leave its tree dirty and would hold c7 false for every launch. R8 adds the committer.
5. **launchd and detached children.** A LaunchAgent's leftover processes in the job's process group are killed when the job exits. The supervisor is started with `setsid` (`start_new_session`), outside that group; a project that opts in should also set `AbandonProcessGroup` true in its plist.

## 5. Parameters and their basis

| parameter | default | basis |
|---|---|---|
| `max_parallel` | 1 | today's behaviour; a project opts in |
| `gate_command` | required above 1 | the re-gate has nothing to run otherwise |
| `merge_attempts` | 3 | **no measured basis** |
| `merge_lock_timeout_s` | 600 | **no measured basis**; a pass is seconds |
| `gate_timeout_s` | 3600 | **no measured basis**; ai-readiness-kg's full suite took 42 minutes (DN-013 §2) |
| `worktree_dir`, `branch_prefix`, `lease_dir` | `.worktrees`, `task/`, `.seldon/leases` | DN-013 and the SEL-004 task |
| `union_unique_key` | `event_id` | the event store's id field |

## 6. What this does not solve

- **Semantic conflicts outside the write set.** A task whose files main did not touch is not re-gated, even if main changed code it depends on. The rule is the SEL-004 task's; DN-013-R4's daily `gate-full` on main is the backstop.
- **Touches is declarative.** Nothing enforces it at write time, as nothing enforces the Network allowlist at the socket (DN-006 ADDENDUM_05 §2). The finish records `undeclared_writes`, the files the task changed that its Touches did not cover; the rebase and the union check catch the textual consequences.
- **Hand-dispatch.** DN-006 decision 10 stands: the primary checkout is the exclusive task's and the dispatcher's, and an operator session there is invisible to the planner.
