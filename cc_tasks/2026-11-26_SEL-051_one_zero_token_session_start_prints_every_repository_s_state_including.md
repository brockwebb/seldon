# SEL-051: one zero-token session start prints every repository's state, including refused tasks and gate time, and one stop halts the factory

**Status:** proposed
**Author:** `seldon cc return`, 2026-11-26, for factory FAC-21 (ab3b7d3c), which answered factory:71438cd8 (AD-036-R16).
**Returns:** factory:ab3b7d3c-e0ff-4513-bf99-82ba5e6dde6c (FAC-21)
**After:** 2026-11-26_filing_from_factory_the_prior_art_search_does_not_read_four_registered_repositories_and_a_need_stated_in_a_thread_cannot_enter_the_graph
**Spend:** est. 0.05M tokens. Basis: nothing to build; the session reads this section and completes.
**Network:** none beyond git.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Parts:** A 1.00.

factory:71438cd8 (71438cd8) was filed into factory; factory task FAC-21 (ab3b7d3c) answered it. This task is that answer's return, filed by the answering task rather than pasted by hand (AD-036-R16).

## What landed, and where

- The answering task: `factory/cc_tasks/2026-11-26_FAC-21_one_zero_token_session_start_prints_every_repositorys_state_including_refused_tasks_and_gate_time_and_one_stop_halts_the_factory.md`.
- Its RESULT: `factory/cc_tasks/2026-11-26_FAC-21_one_zero_token_session_start_prints_every_repositorys_state_including_refused_tasks_and_gate_time_and_one_stop_halts_the_factory_RESULT.md`. Read it in full before starting.
- The commit: factory@32dc06dadd5f7284abd4eda1f265ababfb360004 (on branch worktree-parallel-wobbling-sketch, which the dispatcher merges to main).

## What seldon does with it

Your filing `71438cd8` (2026-11-21, "a project's gate time grew sixfold in ten days and no one was watching it") is
answered by factory FAC-21.
- **Yes:** gate time per project is now a reading the factory keeps and shows the operator.
- `scripts/session_start.py` is run at the start of every coordinator session (factory CLAUDE.md, "The coordinator",
  section 1).
- For each repository it prints the last per-merge gate wall time against the median of the previous ten days:
  WARNING above twice, CRITICAL above four times.
- It also prints the gate's share of that task's wall time.
- It reads only what seldon already records:
  - `gate_run` events from the merge gate, with `wall_seconds` (AD-037-R21, SEL-043);
  - `gate_recorded` events, with `gate.wall_seconds`;
  - `dispatch_finished.wall_clock_s`.

Nothing is asked of seldon's code. One observation for SEL-041's owner, to act on or not: squiddy's 8 gate records
carry only monotonic `seconds`, so squiddy has no wall-clock gate reading until its next merge gate runs under SEL-043.
Complete this return once read.
