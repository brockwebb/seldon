# SEL-004: the dispatcher runs independent tasks in parallel, each in its own git worktree, with independence declared by resource and never inferred from the precedes graph

**Repo:** seldon. Branch `feat/SEL-004` from main. L4: commit, merge, push.
**Date:** 2026-10-07. **Authored by:** a Desktop session in ai-readiness-kg.
**Governing:** ai-readiness-kg `docs/design/2026-10-06_DN-013_parallelism_known_endpoints_and_prose.md` R3; ai-readiness-kg DN-006 (the dispatcher's one-lease design and decision 10). Read both, `seldon/core/dispatch.py` and `seldon/commands/dispatch.py` in full. Glob and read sibling `*SEL-004*ADDENDUM*.md`.
**Framework layer served (DN-005 §5 rule 1):** none (Seldon infrastructure).
**Spend:** est. 3M tokens (Opus). No harness model call.
**Network:** none beyond git push.

## A premise in DN-013-R3 is wrong, and this task is built around the correction
R3 says "the precedes graph already says which tasks are independent". It does not. A `precedes` edge records an ordering a Desktop session wrote down, often by hand; its absence says nothing about whether two tasks write the same files or the same database. In ai-readiness-kg, tasks with no edge between them routinely share:
- the Neo4j database `seldon-ai-readiness-kg` (the KG projection resets its labels; scan publication owns `Observation`/`Finding`/`Rule`; Seldon's artifact graph lives there too);
- append-only JSONL tracked in git: `events/batch-*.jsonl`, `seldon_events.jsonl`, the spend ledger `state/spend_ledger.jsonl`;
- gitignored state and logs, and the `.seldon/` lease, STOP and stuck files;
- generated views that many tasks regenerate (matrices, report, site, evidence map).
Evidence that a shared checkout is already unsafe: on 2026-10-07 the operator-launched recollection's first full-suite run died at 35% with no EXIT line at 02:17:51Z, when a Desktop session committed in the same checkout (ai-readiness-kg `cc_tasks/2026-10-06_absence_verdicts_recollection_RESULT.md`, gate paragraph).

## Decisions

1. **Independence is declared, by resource.** Two optional task headers, machine-read beside the three required ones:
   - `**Exclusive:** yes|no`, default `yes`. An exclusive task runs alone, as every task does today.
   - `**Touches:** <resource>, ...`: path globs plus named resources (`neo4j`, `framework_record`, `views`, `spend_ledger`).
   A non-exclusive task launches only when its `Touches` is disjoint from every running task's. The model is GitHub Actions' `concurrency` groups and declared outputs in Make and Bazel: the author names the lock; the scheduler never guesses one. Unparseable headers refuse with the grammar quoted, as `network_undeclared` does. A task with neither header behaves exactly as now.

2. **Worktree per task.** The dispatcher launches each task in `git worktree add <repo>/.worktrees/<task stem> -b task/<task stem> <main HEAD>`, with the child's cwd there. `.worktrees/` is gitignored. The lease becomes one per worktree under `.seldon/leases/`, plus the existing global lease taken by exclusive tasks. `dispatch.max_parallel` in `seldon.yaml`, default `1`, which reproduces today's behaviour.

3. **Merge on green, never auto-resolve.** When the child exits with its RESULT committed on its branch: rebase onto main; if main moved and the rebase changed any file in the task's write set, rerun the task's gate in the worktree; then fast-forward main, push, and remove the worktree. A rebase conflict or a red re-gate sets the task `merge_blocked`, writes an Issue naming the files, leaves the worktree in place and notifies the operator. Nothing is resolved by the dispatcher.

4. **Append-only files merge by union.** `.gitattributes` marks the append-only JSONL files `merge=union` (git's built-in union driver). A post-merge check asserts each is valid JSONL with unique `event_id`s; a duplicate or a malformed line fails the merge as `merge_blocked`.

5. **One spend ledger across worktrees.** Every worktree resolves the ledger to the primary checkout's path and appends under an exclusive `flock`, so parallel runs share one daily cap. Test it with two processes reserving against one cap.

6. **Seldon's own graph writes.** Two worktrees calling `seldon cc complete` and `seldon cc register` concurrently must leave a consistent graph and, after merge, both events in `seldon_events.jsonl`. Test it against a scratch database.

7. **Recovery.** A killed child leaves its worktree and lease; the next poll finds a lease whose process is gone, marks the task as the existing stale-lease path does, and keeps the worktree for inspection.

## Tests (each against a scratch repository and database)
Two disjoint non-exclusive tasks run concurrently and both merge; two overlapping ones serialize; two `neo4j` tasks serialize; an exclusive task waits for running ones and blocks new ones; union merge of two event appends is valid; a conflicting rebase ends `merge_blocked` with an Issue; `max_parallel: 1` reproduces the current dispatch log byte for byte on a recorded fixture; the ledger lock holds under two processes.

## Rollout
Default `max_parallel: 1`; nothing changes in any project until it opts in. The RESULT names the exact lines an ai-readiness-kg task would change to opt in (`seldon.yaml`, its CLAUDE.md dispatch protocol, and the headers), and does not change that repository.

## Report
Suite (with passed, skipped, xfailed, deselected), the tests above by name, the RESULT under 50 lines at `cc_tasks/2026-10-07_SEL-004_worktree_per_task_dispatch_RESULT.md`: what was built, the header grammar as implemented, premises wrong, tokens and model. `seldon cc complete`, merge, push.
