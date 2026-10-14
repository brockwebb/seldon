# QC-002 RESULT: AD-037-R6's four stations in the dispatcher

**Date:** 2026-10-14. **Task:** 22730567, dispatched (launch 13:38:57Z), Claude Opus 5.5. No addenda existed. Commits 671f422 to e2e92d1 (feat/qc-002-four-stations, ff to main), governed 9c8ea77; squiddy 742100a.

**Tokens** (input + cache writes + output, from the dispatch log's stream-json; cache reads not counted, 27.3M): Part A 226,435; B 250,480; C 261,679; D 297,451; about 0.31M at this RESULT, against 1.5M (stop line 1.8M, not reached). **This task's CPI, as the dispatcher computed it:** A none, B 3.59, C 4.87, D 5.04. Part A had no CPI because `spend_tokens` read this task's Spend header as 0 (see premises). The records came from `seldon dispatch once` run by hand: launchd starts no pass while its own job (the holder running this session, pid 6243, old code) is running.

**Stations, their records, where the dispatcher reads them** (`seldon/core/stations.py`, `seldon/commands/dispatch_stations.py`, protocol in `docs/conventions/dispatched_session_protocol.md`):
- (a) premise review, in `_pass` before the claim: `dispatch_refused` `premise_false` (with an Issue; c13 then holds the task while the Issue is open) and `environment_in_flight`, recorded once per sibling-lease acquisition. Every `dispatch_launched` carries `premises` and `inspection_reserve`. `status --json` shows `last_premise_review`.
- (b) first article: `first_article` (session), then `first_article_pass` or `session_stop`.
- (c) milestone: `part_complete` (session, tokens from the log), then `milestone` with checks, CPI and judgment plan.
- (d) andon: `session_stop` (`line`, `andon` or `hard`), `andon_halted` (session), `andon_reaped` (holder only), `huddle` and `huddle_closed`.
- Who inspects: the lease holder runs `_run` as Popen, inspecting every `poll_interval_s`. A pass that finds a holder with no `stations` field in its lease inspects in its place and reaps nothing. `seldon dispatch inspect` does the same by hand.

**Plants** (each fails on HEAD 9344954: `docs/evidence/qc002/plants_fail_on_head.txt`):
- milestone: failing check stops (HEAD: no `part-complete` command); CPI 0.625 opens a huddle without a stop (same); no `**Parts:**` refused at registration (HEAD: no refusal, reached the graph).
- premises: a false `check:` premise refuses and files an Issue, and a held lease in sibling `sib` refuses (HEAD launched both).
- first article: a pass continues and a fail stops (HEAD: no station).
- andon: an operator stop halts at the next boundary (HEAD: no `stop`); a hard stop is reaped at 300 s and not at 299 s (same); `go` lists an open huddle, then none (HEAD: no `huddle`).
- Plus `_run` reaping a real process group (SIGTERM, exit -15).
- Live: `seldon go` listed huddle 2d69be52, then none after `huddle --id` closed it.

**Chart, first reading** (`seldon qc chart`; seed `docs/evidence/qc002/cpi_first_reading.yaml`):
- act/est and CPI: SQ-010 2.20 and 0.455; SQ-012 0.16 and 6.383; SQ-013 0.58 and 1.714; SQ-014 0.60 and 1.667 (actual a lower bound); SQ-015 0.64 and 1.569; QC-002 0.20 and 5.043.
- Milestone defect rate 0/4; premise-false and first-article rates 0/0; huddles 1.
- The individuals chart is not drawn: 6 tasks of the 10 FC-15 requires.
- The table's "ratio" is actual/estimate, which is 1/CPI; both are printed.

**Suite** (passed, skipped, xfailed, deselected, failed): worktree at Part D, 2444/0/0/0/0; final main (9c8ea77 plus this RESULT), 2445/0/0/0/0. `seldon verify`: all checks passed after the repin.

**Constraints and basis.**
- CPI huddle line 0.8: external (AD-037-R6 c, no measured basis).
- 10% inspection reserve: external (R7). The measured inspection share is 0.0 model tokens (zero judge calls) and 2.7 to 31 s of checks per milestone.
- One-interval reap: external (task). Three-poll first-article huddle: external (task).
- Spend ceiling 1.2 x estimate: inherited (QC/SQ stop conditions). Check timeout 1800 s: assumption.
- Judgment sample rate 0.25: assumption, inert until QC-003. Usage-error exits (2 or 4 with `usage:`, 126, 127) read as `unrunnable`: external (POSIX, argparse and click conventions; pytest exit 4).

**Premises found wrong.**
1. "The dispatcher's next pass" does not exist during a serial session: launchd runs one job instance, and that instance is the holder. So the holder inspects in-process.
2. QC-001's criteria reader found 0 criteria in this file (`Acceptance:` with a same-indent list), so `criterion_unmarked` passed it vacuously. Fixed.
3. `spend_tokens` put `zero` ahead of a count, so this task, PA-001 and SEL-005 read as 0 tokens at c4. Fixed: an explicit count wins.
4. Part A's `check: seldon cc register` is not runnable as written (exit 2). It was recorded `unrunnable`, huddled and closed; the plant test carries the criterion.
5. `seldon verify` failed on main before this task: 8 governed docs were uncataloged because squiddy was 13 commits past pin 21f4004. Repinned to 57e220f with `squiddy governed repin` (121 unchanged, 18 re-admitted, 0 failed), then swept (9 cataloged). The Makefile's `--tests=` flag no longer exists.
6. The worktree supervisor does not inspect (its session writes the worktree's event store). `stations_live()["worktree"]` is False, so R9's opt-in stays closed.
7. No FC-32 toxic classifier exists: a hard stop for that tier is `seldon dispatch stop --hard`.
8. Premises are optional until a task carries them; this task declares none, so station (a) evaluated only the environment premise, and not for this launch (old code).
9. The `parts_undeclared` gate applies once a project names `qc.parts_baseline`. Seldon does; squiddy, arnold and ai-readiness-kg have not.

Issues e8142dcc (premise 6) and f6c69653 (premise 9) track the two open follow-ups.
