# Filing from factory: a coordinator task launches beside an exclusive build task, and goes first among eligible tasks

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-27
**Reporter:** factory FAC-35 (`cc_tasks/2026-11-27_FAC-35_an_ooda_task_does_not_wait_behind_a_build_task_and_the_coordinator_resizes_the_grants_it_set.md`),
under factory F-044 as amended by FAC-35, decision 1 (`decisions.md`, "F-044 amended 2026-11-27 by FAC-35"), and
factory DN-003 (the coordinator's check-in is a zero-token tick; judgment is a dispatched OODA task).

## What happened

At about 22:40 EST on 2026-11-26 factory's tick filed OODA-001 for critical-thinking-ai CTAI-008's
`merge_blocked: ungated`. It sat in factory's queue behind FAC-31, an exclusive 1.8M build task, for the length of
that task, while twelve more changes waited behind "an OODA is open". The block it was filed for held the book's
whole chain for ninety minutes, until a Desktop thread landed it by hand (CTAI-008R). A check-in that queues behind
the work it watches is CTAI-006's three-hour stall again.

## What seldon does today (read at seldon main, 2026-11-27)

- `seldon/core/dispatch.py` `plan_launches`: while any held task is exclusive, every candidate waits, exclusive
  (`exclusive_waits`) or not (`exclusive`). So no `Exclusive: no` / `Touches` declaration on the OODA lets it run
  beside an exclusive build, at any `max_parallel`.
- `fifo`: eligible candidates are ordered by `created_at` and nothing else (DN-006 decision 9: "a priority field
  would be a value nobody measured"). A just-filed OODA is the newest candidate, so even when the build finishes, the
  oldest waiting build launches first.
- factory runs at `dispatch.max_parallel: 1` (AD-037-R9).

## What factory does until this lands

The tick orders every open OODA it filed ahead of every factory task not yet launched with `seldon task precede`
(a task with an open predecessor is not eligible, c2), and takes the edges off with `seldon task unprecede` when the
OODA is blocked or rejected. That gets the OODA the next free slot. It cannot get it a slot while a build runs.

## What is asked

A declared lane for coordination work: tasks matching a configured name pattern (factory's would be `^OODA-\d+`,
the same pattern as factory's `scripts/bank.yaml` `grants.coordinator_tasks`) get one reserved slot that an
exclusive task does not hold, and go first among eligible candidates. For example, in `seldon.yaml`:

```yaml
dispatch:
  coordination_lane: {name_pattern: '^OODA-\d+', slots: 1}
```

- A lane task is still a task in every other way: its own worktree and branch, the band, the Spend ceiling, the
  stop gate, the merge lock and the re-gate. Two lane tasks do not run at once (`slots: 1`).
- It is not a priority field set per task by an author (the value DN-006 decision 9 declines): it is a class named
  once in configuration, as GitHub Actions concurrency groups and Kubernetes' `system-cluster-critical` priority
  class name a class of work, and as Slurm's QOS reserves capacity for one. What makes it safe beside an exclusive
  build in factory is what an OODA writes: task files in other repositories through `seldon cc file`, its own RESULT,
  and `for_operator` items, never the files a build task touches. A project that turns the lane on declares that.
- When it lands, factory removes its precede fallback (the tick's `order_oodas_first: false` in
  `scripts/coordinator_tick.yaml`).

What factory will test against it: an OODA filed while an exclusive build task is in flight is launched at the
dispatcher's next pass, and a second OODA filed meanwhile waits for the first.
