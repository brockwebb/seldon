# AD-034 ADDENDUM 04: the Stop gate lets a session go on no progress, not at a count

**Date:** 2026-10-20. **Written by:** LOOP-001 Part A (`cc_tasks/2026-10-20_LOOP-001_stop_hook_no_progress_rule.md`).
**Amends:** AD-034 ADDENDUM 01 (FRICTION-002: the Stop hook is the completion gate). Withdraws its block cap,
`dispatch.stations.stop_hook_block_cap: 20`, which was set with no measured basis. One new ruling.

## Evidence

FRICTION-002's live probe (`docs/evidence/friction002/stop_gate_live_probe.jsonl`, 2026-10-17) recorded the failure
mode. A model that could not make its check pass re-asserted the same state 13 times, until the CLI's refusal cap
ended the session. Raising the cap to 20 bought seven more rounds of the same output. A count cannot tell a session
that is fixing from one that is repeating itself. What the session's checks print can.

## Prior art

- The vendor's loop pattern (code.claude.com/docs/en/workflows): "keep fixing until a check passes ... or two rounds
  in a row make no progress". This addendum adopts it as written.
- Reflexion (Shinn et al. 2023): a retry must carry new information or stop. Identical check output means the last
  round added nothing.

## The rule

- **AD-034-R11. Each Stop the gate refuses is a round, and the gate records a fingerprint of the round's check outputs (exit code, stdout and stderr, hashed after the configured volatile spans are masked); when a round's fingerprint equals the previous refused round's, the gate lets the session end with verdict `no_progress` and the finish treats it as `stop_gate_unpassed`, so the branch is not merged; rounds whose outputs differ continue with no count and no cap of the dispatcher's own.**
  The record carries `round`, `fingerprint` and `no_progress: {rounds: [n-1, n]}`. The CLI's own refusal cap is
  still there as the backstop. The launch no longer sets `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`, so the CLI's default
  applies, and it fires only on a session whose output keeps changing. `dispatch.stations.no_progress_volatile` is
  a list of regular expressions for spans that differ on every run (durations, timestamps, addresses, temporary
  paths). Without the duration mask, pytest's "1 failed in 0.42s" would make every round look new. The loader
  refuses `stop_hook_block_cap` and names this addendum. Code: `seldon/core/stations.py` `stop_gate`,
  `round_fingerprint`, `output_fingerprint`, `WITHDRAWN_KEYS`; tests `tests/test_loop001_no_progress.py`.

**Repair, no new rule.** The refusal text quoted `output_tail`, a key no check row carries, so the model never saw
the failing output it was told to fix. It now quotes the row's `tail`.
