# RESULT: PRUNE-001 weekly prune of open artifacts (2026-10-17)

**Task:** `becc7081`. **Code:** `seldon/core/prune.py`, `seldon/commands/prune.py` (`seldon prune run|redate`), `seldon.yaml prune:`, lane `scripts/jobs/{seldon_prune.sh,com.brock.seldon-prune.plist}` (Sunday 03:30, installed by symlink, loaded). Zero model calls. Nothing deleted.

| repo | open Issues before → after | stale FUTURE (60 d) before → after | actions |
|---|---|---|---|
| seldon | 9 → 8 | 7 → 0 | 7 re-dated by hand (triggers plausible: paper projects moved 10-11/10-14); `25da4d06` (stale pin) resolved by hand, outside the rules, reason `02de85f` |
| squiddy | 56 → 29 | 0 → 0 | 27 resolved by `fixed_marker`, each with the main head at filing as its commit |
| arnold | 0 → 0 | 0 → 0 | none |
| ai-readiness-kg | 12 → 12 | 0 → 0 | none (its 25 FUTURE proposals are all under 60 days) |

Evidence: `docs/evidence/prune001/<repo>_issues.md`, `before_dry_run.json`, `part_a_run.json`.

**Exit rows (R-186, kit 627da34, appended in squiddy `5eff895`):** seldon 22 admissions, 0 failed, 0 open, cold 30.23 s, warm p95 30.97 s; squiddy 22, 0, 0, 27.16 s, 29.23 s; arnold 11 (no new admission: every key was already done at this kit commit), 0, 0, 26.73 s, 26.97 s. Uncataloged 0 in all three. ai-readiness-kg has no R-186 measurement.

**Lane's first pass** (`launchctl kickstart`, 2026-10-17T16:33:57Z): rc 0, 0 actions, one `prune_pass` record, no notification (`docs/evidence/prune001/lane_first_pass.txt`). Spend: token cap 0 with DN-042's ×1.2 stop, so any charged token stops the lane.

**Premises found wrong or loose.**
1. "Tasks named FUTURE": FUTURE is a description prefix (TRIAGE-001 rule 4), not a name. The rule reads `moving.is_future`. All 7 stale ones had been rewritten by TRIAGE-001 two days earlier. Their age ran from `created_at`. The clock now runs from `redated_at`.
2. "Whose named commit is on main": taken literally, this closes Issues that name the commit where the defect was *seen* (`25da4d06` names 4ac50a5). I narrowed the rule to a fix phrase ("fixed in <sha>"). A named fix that main does not hold keeps the Issue open (a test caught this).
3. The dry run found one false positive: squiddy `dc636a65`, whose lead reads "NOT FIXED ... a RESOLVED CANDIDATE". Now the first marker in the lead decides.
4. Rule 2 has no model call, so the lane cannot judge plausibility. Re-dating is a hand step (`seldon prune redate`). Without a hand re-date or an edge from an open task, each of the 7 is withdrawn at the Sunday pass of 2026-12-20.

**Checks.** `tests/test_prune001.py` 16 passed. Full suite on d79c016 (worktree, detached): 2606 passed, 0 failed in 26:03 (`docs/evidence/prune001/full_suite.txt`).
