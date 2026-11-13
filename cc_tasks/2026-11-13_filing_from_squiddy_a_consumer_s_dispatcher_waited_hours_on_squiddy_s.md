# Filing from squiddy: a consumer's dispatcher waited hours on squiddy's lease after squiddy's task session had ended, and nothing showed whether the holder was working

**Kind:** filing
**Filed by:** squiddy
**Date:** 2026-11-13. **Authored by:** a Desktop session in squiddy (SQ-14), at the operator's question the same day ("Is that a good design or a bad design?").

## What was experienced

- squiddy's dispatcher launched SQ-133R (76d0cde1) at 14:12Z on 2026-11-13. The task's session wrote `EXIT=0` to its log at 17:37:59Z. Its work touched only squiddy's repository and squiddy's `graphs/library`.
- After the session ended the dispatcher went on holding its lease while the merge round's `gate_record` ran (`python -m squiddy.kitpass record-pass`, 2,847 tests on each of three seeds). The same command took 2h25m on 2026-11-09 and 2h05m earlier on 2026-11-13. At 20:17Z, 2h39m after the session ended, no pass line had been written and the lease was still held.
- hazbrief's dispatcher refused HB-177 as `environment_in_flight` from 18:05Z, as reported by the hazbrief thread: another project's dispatcher held a lease on a repository hazbrief depends on. HB-177 was the only hazbrief task queued and the operator's weekly allowance reset was about six hours away.
- The operator did not expect the two projects to conflict. He read the refusal as squiddy working on hazbrief's tree, which it was not; nothing he could see said what the lease covered or why it was held.
- From the squiddy thread, a running gate and a hung one could not be told apart: `logs/squiddy_dispatch.log` had no line after `=== 2026-11-13T14:12:21Z | squiddy-dispatch fire`, and the worktree's `kit/ledger/passes.jsonl` is written only when the round ends.
- A consumer filing from hazbrief was committed to squiddy's main at 18:02Z, during the round. Whether that moves the round to a second full pass was not visible either.
- While the lease was held, `seldon_task_create` in squiddy answered `event store NOT committed (lease_held)`.

## What squiddy is doing on its side

The length of squiddy's own record-pass is squiddy's: idea SQ-138 (a44ac624) in squiddy's graph.

## What is asked

Seldon's reading of this: what the cross-project lease is meant to protect, over what part of a dispatch, and what a waiting consumer and its operator are shown.
