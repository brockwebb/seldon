# AD-034 ADDENDUM 03: kept work blocked by its Stop gate is re-gated in place and merged

**Date:** 2026-10-20. **Written by:** DISP-003R Part C (`cc_tasks/2026-10-20_DISP-003R_gate_runs_the_branch_code.md`).
**Amends:** AD-034-R5 and R6 (a worktree task merges on green; an unmerged one keeps its tree). One new ruling,
numbered from the register, and one repair to the union set of SEL-004 decision 4.

## Evidence: PA-002 (`314a3942`)

PA-002 finished `stop_gate_unpassed` with exit 0, its RESULT committed on `worktree-delegated-floating-coral` and its
tests green. The only failing check was the one AD-037-R14 now repairs. A blocked task had one way back,
`seldon dispatch redrive`, which puts it on the queue for a fresh launch that redoes finished work in a new tree.
ADDENDUM 02's `remerge_breaker_green` re-merges a `classifier_breaker` finish whose gate passed. A finish whose gate
did not pass had nothing like it.

**Rehearsal, 2026-10-20** (`/tmp/disp003r/sim.py`, a throwaway clone): main at `1ee592f`, then this branch merged
(`d0895c6`), then PA-002's kept branch rebased onto that (41 commits). PA-002's three `check:` lines ran in that tree
through `run_task_checks`, with the tree first on `PYTHONPATH`. All three passed:
`pytest tests/test_pa002_release_resolve.py -q` (36 s), `seldon prior-art verify
docs/design/AD-036_prior_art_receipts_gate.md` (115 s; AD-036 PASS, which needs both PA-002's release fix and
AD-036-R14) and `test -f docs/design/AD-036_ADDENDUM_06_...` (0 s). This is the state the dispatcher's first pass
after this branch merges will regate. The first rehearsal, without the repair below, stopped at the rebase:
`state/prior_art_queries.jsonl` conflicted.

## The rule

- **AD-034-R10. A task blocked `stop_gate_unpassed` whose kept worktree holds its committed RESULT is re-gated in place: its branch is rebased onto main, every `check:` line of the task runs in the worktree with the tree's own code, and on pass the branch goes to the merge path; on fail it stays blocked with the failing checks quoted.**
  `seldon dispatch regate <task>` does this for one task under the pass lease. Every pass with no session in flight
  does it for every such task (`_breaker_and_stale`, beside the remerge). Each attempt writes `dispatch_regated`:
  `regate_id`, checks with interpreter and path, outcome, failing commands, the branch-diff key and main's sha. A pass
  does not repeat a failed reading. It skips the task while the branch's diff is unchanged and main has moved only by
  housekeeping files (union files and `shared_paths`, the set `_merge` already uses). An explicit `regate` always
  runs. The checks are all Parts' checks, since a committed RESULT says every Part is done. A check that is not `pass`
  fails the regate, `unrunnable` included, because nothing unverified merges. A dirty tree or a rebase conflict fails
  the regate and names the files. On pass the task walks `blocked -> in_progress`, and `_merge` re-gates when main
  changed a file the task changed, then fast-forwards, completes, sweeps and records the merged finish with
  `regate.regate_id`. Code: `seldon/commands/dispatch_worktree.py` `regate`, `regate_candidates`, `task_checks`,
  `run_task_checks`; `seldon/commands/dispatch.py` `dispatch_regate`.

**Repair, no new rule.** `state/prior_art_queries.jsonl` merges by union (`.gitattributes`). AD-038-R1 already
counts it as append-only, machine-written state. Without union, any two branches that ran prior-art searches
conflict on rebase, which is the PA-002 case. The merged file is still checked by decision 4: every line must be
JSON, and `event_id` must be unique among lines that carry one.

## Prior art

### External

- library receipt: query "merge queue retest rebased branch before merge" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-03-17_arXiv_2303_18223#p137:2370:4242-4428

  The library's top row is a survey paragraph unrelated to merging. The prior art is engineering practice.
- **The merge queue re-tests the rebased change.** bors (Graydon Hoare's "not rocket science rule": keep a
  repository whose main always passes its tests) and GitHub's merge queue test each change on top of the current
  main before it lands. R10 runs the check against the rebased branch, not the branch as the session left it.
- **Re-run, not rebuild.** CI systems re-run a failed job on the same commit (GitHub Actions "Re-run failed jobs")
  rather than asking for a new commit. Message queues move a dead letter back with its payload (Amazon SQS dead-letter
  queue redrive). R10 is the re-run for a kept branch. `redrive`, which relaunches, stays the path for work that is
  not finished.

### Internal

- internal receipt: query "redrive blocked task dead-letter" | repo seldon@72d57e86f2b496bb8c4c9d52eee8a66c1d90270f | hits docs/design/AD-038_the_machine_reconciles_its_own_state.md:64

AD-038-R1 (line 64) lists the prior-art query log among the append-only, machine-written state the dispatcher
commits. The union repair applies that classification at merge time.

## Negative control (AD-038-R6)

`tests/test_disp003_regate.py`. While the check still fails, `regate` exits 1, the task stays `blocked`, no
finish is written, and a pass with nothing changed does not run it again. A task that is not a candidate is refused
with no record. The test fails on HEAD before this change (`regate` is no such command).
