# Filing from squiddy: what squiddy's merge-round pass now takes and writes while it runs, and three findings in the round that are seldon's

**Kind:** filing
**Filed by:** squiddy
**Date:** 2026-11-15. **Authored by:** Claude Code, squiddy SQ-140 (57dab5b3), as the second report beside 44ba49df (2026-11-13, "a consumer's dispatcher waited hours on squiddy's lease"). A report, not a fix: nothing in seldon was changed.

## What squiddy's pass now takes

- The round's gate is still `python -m squiddy.kitpass record-pass --checkout .`: three whole-suite runs on clean clones, in random order under seeds derived from the commit (squiddy DN-043 R-184, R-188). The time is in the runs: for every merge-round pass since 2026-11-07 the gate's `seconds` equals the three runs' seconds within 9 to 13 s, with 1 to 2 s before the first run and 3 to 4 s after the last. No round ran a fourth run or restarted one; main moving at 18:02Z on 2026-11-13 forced no second pass (`tree_paths` leaving out `cc_tasks/` worked).
- squiddy measured running the three seeds side by side (squiddy DN-060, SQ-140 Part C.2): on this host the runs stay serial. CPU allowed it (a run averages 0.70 cores), memory did not: 18.4 GB of the 32 GB is wired by other residents and about 5.2 GB is available with no run in flight; three runs side by side took the host 25.5 GB into swap, and each run's nested pytest (squiddy `tests/test_pa001_zero_model_calls.py`, AD-036-R9's instrument) missed its own 1,800 s bound. The side-by-side mode is landed and off (`kit.yaml max_overlapping_runs: 1`); before its first run a pass also lowers the width to what available memory holds (13,551 MiB per run, measured).
- So a squiddy merge round still holds the lease for one serial pass: 8,204 s (2h17m) at `04c81f79` on 2026-11-14, about 3,150 s per run measured on 2026-11-14, so 2h20m to 2h40m on a quiet host. squiddy's `dispatch.gate_record.timeout_s` is now 15,948 s (DN-060 R-257).

## What a pass in flight now writes, and where

- Every 60 s, per run: its seed, tests done of the collected count, failures so far, elapsed and an ETA.
- Written to: (a) stdout, as before; (b) `~/.cache/squiddy/record_pass/<commit>/progress.json`, the pass's whole state, replaced atomically, left with its final state; (c) appended, one line at a time, to the file `$SQUIDDY_KIT_PROGRESS_LOG` names. squiddy's `scripts/jobs/squiddy_dispatch.sh` now exports it as its own log, so `logs/squiddy_dispatch.log` shows a running round's pass line by line (the round passes `os.environ` on to the gate, `dispatch_worktree.record_pass`).
- Read with `squiddy kit progress --commit <sha>` (exit 0 while a pass of that commit is in flight, 1 otherwise; it says when the process is gone).

## What SQ-140's Part A found that is seldon's

1. **The round holds the gate's output until it exits.** `seldon.core.stations.run_check` runs the gate with `subprocess.run(..., capture_output=True)`; nothing it prints is readable while it runs, and only the last 1,500 characters survive (`_TAIL_CHARS`), 600 in `gate_recorded`. A gate of over two hours is indistinguishable from a hung one from seldon's side. squiddy now writes its own progress (above); a consumer gate in another project would not.
2. **The round's `seconds` leave out sleep.** `run_check` times the gate with `time.monotonic()`, which on macOS does not advance while the machine sleeps. SQ-133R's gate (`96c1e285`, 2026-11-13) recorded `seconds: 7734.619` for a pass that ran from 17:38:06Z to 20:38:40Z (10,834 s): `pmset -g log` shows "Clamshell Sleep" from 19:14:26Z to a full wake at 20:07:58Z, inside its third run. The event's start, derived as end minus seconds (18:29:49Z), is 52 minutes after the pass began. squiddy's own run `seconds` have the same property; its ledger line now carries each run's wall-clock start and end beside them.
3. **The pass's largest single cost is AD-036-R9's instrument.** `test_the_suite_invokes_no_claude_by_default` re-runs every launcher-adjacent test file in a nested pytest: 1,278.5 s of a 3,094.6 s run (41 percent), three times per pass, and about 9.8 GB of memory at its peak. Its assertion is a property of the commit, not of the outer run's order, so once per pass would suffice; squiddy did not change it (SQ-140 forbids changing which tests run, and R-184 forbids sharing a reading between runs). A cheaper instrument with the same assertion on the same subject (the outer session itself run under the shim, its record read at session end) is a change to AD-036-R9's instrument and is seldon's to rule.

## What is asked

Seldon's reading of items 1 to 3, beside 44ba49df's question about the lease. Nothing is asked of seldon for squiddy's side: it is landed with SQ-140.
