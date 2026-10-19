# AD-037 ADDENDUM 01: the spend ceiling has a measured floor, a hard stop is delivered at a tool boundary, and the reap reads liveness

**Date:** 2026-10-19. **Written by:** DISP-001R Part B (`cc_tasks/2026-10-19_DISP-001R_worktree_name_and_spend_floor.md`).
**Amends:** the dispatcher's hard stops (station d of AD-037's sixth ruling) and the seventh ruling's reading of the
spend estimate. No new ruling beyond the three below (R11 to R13, numbered from the register); the task file
states them and this records them with their evidence.

## Evidence: DISP-001 (`98d14c80`), 2026-10-19

- `session_stop` **04926773** at 12:22:33Z: kind `hard`, reason `spend_ceiling`, reading `{"tokens": 134746,
  "estimate": 80000, "factor": 1.2}`. The first inspection, five minutes after launch, read more than the 96,000
  ceiling before the session had done its work, because no estimate below the cost of loading a session (its system
  prompt, CLAUDE.md files, tools and first reads) can be met.
- `andon_reaped` **d787bf17** at 12:27:34Z: SIGTERM after `waited_s` 300.6 against `reap_after_s` 300. The session
  was inside a five-minute pytest call. A session reads a stop only at `part-complete` or `boundary`, and neither
  runs during a tool call, so it had nowhere to read the stop. The reap killed it mid-call and its tree was kept with
  an uncommitted test file.

## The rules

**AD-037-R11. The floor (amends R6 d).** The spend ceiling is `max(estimate, floor) x spend_ceiling_factor`. `floor` is measured,
never configured: the median token reading at the first inspection (`poll_interval_s` after launch) over the
repository's last `dispatch.stations.floor_launches` (10) finished launches, read from `dispatch_launched` and each
session's own log (assistant records carry a `timestamp`). A launch that never reached the model is not a data point.
When the floor is the binding term the `session_stop` reading records it, with the launches it came from.
`seldon qc chart` prints the floor as it stood each week. Code: `seldon/core/stations.py` `tokens_at`,
`spend_floor`, `spend_ceiling`, `floor_by_week`.

*Departure from the task's wording, with reason:* the task wrote `max(estimate x factor, floor)`. A ceiling equal to
the median first-inspection reading stops about half of the low-estimate sessions at their first inspection, which
is DISP-001's defect again. So the factor's margin applies to whichever term binds. The floor is still a lower bound.

*Measured on 2026-10-19:* floor **131,243** tokens (n 10, DESK-001 through DISP-001; DISP-001's own reading,
reproduced from its log by `tokens_at`, is 134,746).

**AD-037-R12. The boundary (amends R6 d).** A hard stop is delivered to the session, not only written to the ledger. Every dispatched
session is launched with a `PreToolUse` hook, `seldon dispatch tool-gate`. It reads the ledger for an unanswered
hard `session_stop` on this session's task. If it finds one, it refuses the next tool call with the stop's reason
(`permissionDecision: deny`) and records `andon_halted` (`at: tool boundary`) itself. So the session halts at its
next boundary, between tool calls, and is never killed inside one. Only a hard stop is delivered there; a line or
andon stop is still read at a Part or loop boundary. Code: `seldon/commands/dispatch_stations.py`
`tool_gate_command`.

**AD-037-R13. Liveness (amends R6 d).** The reap stays as the backstop. It fires only when the unanswered hard stop has aged past
`reap_after_intervals x poll_interval_s` and the session's log has not grown for that same interval. A session that
is writing to its log is alive and gets its boundary (`reap_deferred` in the inspection). `andon_reaped` records
`last_log_growth_s`. Code: `seldon/core/stations.py` `inspect`, `log_growth_s`.

*Known limit, recorded rather than fixed:* stream-json writes nothing while a tool call runs. So a session inside a
single call longer than the reap interval still has a quiet log and is reaped, as DISP-001 was. R12 shrinks the
problem to that case (R12): the stop is delivered at the first tool boundary after it is written. The interval
(`reap_after_intervals`, default 1) is the control.

## Prior art

- **Graceful shutdown before kill.** POSIX SIGTERM-then-SIGKILL, and Kubernetes' `terminationGracePeriodSeconds`
  with `preStop` hooks, deliver termination at a point the workload chooses. R12 is the agent-session form,
  where the tool boundary is the safe point.
- **Liveness by heartbeat, not by deadline alone.** Kubernetes liveness probes, and lease and heartbeat failure
  detectors (Chandra and Toueg, "Unreliable failure detectors for reliable distributed systems", JACM 43(2), 1996):
  a process is presumed dead only after it has been silent for the timeout. R13 uses the log's growth as
  the heartbeat.
- **A budget's floor is its fixed cost.** Earned-value practice separates fixed (level-of-effort) cost from
  discrete work (PMI, *Practice Standard for Earned Value Management*, 2nd ed., 2011). The floor is the session's
  fixed cost, measured, so the estimate covers the work.
- **Claude Code's hooks.** A `PreToolUse` hook may deny a tool call and give the model its reason
  (code.claude.com/docs/en/hooks). The same hook family already carries FRICTION-002's Stop gate.

## Negative controls (AD-038's sixth ruling)

`tests/test_disp001r_stations.py`. With no finished launch to measure, DISP-001's reading is still stopped against
the estimate alone. An andon stop is not delivered at a tool call. A session the dispatcher did not launch is
untouched. The tests fail on HEAD before this change (`docs/evidence/disp001r/plants_fail_on_head.txt`).
