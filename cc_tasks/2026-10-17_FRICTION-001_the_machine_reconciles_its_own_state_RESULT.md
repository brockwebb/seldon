# RESULT: FRICTION-001, AD-038 R1-R6 (seldon) — done; merged 356b67b (+ fix 0fb7930), pushed

**No addenda.** Both premises held. Built in worktrees: `seldon/core/reconcile.py` (A), `redrive.py` (B), `commands/mcp_call.py` (C), stations cwd/branch (D), registration premises, outage refusal, `core/toil.py` (E).
**Tokens** (`part_complete`, dispatch-log stream-json; a lower bound, the log lagged the session): A 364,337; B-E 365,118 cumulative, against 1.5M. Milestones A-E all `pass`, CPI 1.24 / 1.85 / 2.67 / 3.49 / 4.11, no stop, no huddle.
**All five Parts merged at once, then part-complete A-E from main.** The Part D fix makes per-Part merging unnecessary; CPI per Part is cumulative.

**Each new test's failure on HEAD** (main 92f491b, detached checkout):
- A 4/4 fail: `NOT committed: written by governed_sync|cc, which is not one of dispatcher, desktop`; no `unreconciled:` line. The 4 unit tests import the new module.
- B: the 3 task tests + the auto-redrive test fail (`No such command 'redrive'`, `blocked -> accepted` illegal). The negative control (other stops wait) passes, as it should.
- C 4/4 fail: `server_stale ... Restart`; no `_run_in_head`.
- D 5/5 fail: the record lands in the worktree store; the check runs in main.
- E 5 fail + 1 positive control passes: registration ignores premises; the outage test hits the old `DatabaseUnavailable` path; no toil module.

**Full suite per merge:** branch 4a75674: 2581 passed, 8 failed (tests that monkeypatch MCP internals; `--help` hides `mcp-call`). Fixed, then faa4544: **2589 passed, 0 failed** before merge 356b67b. Fix 0fb7930 (stale-log isolation): **2590 passed, 0 failed**, fast-forwarded.
**Rewritten tests (R1/R3 reverse what they pinned):** own_record and stuck_and_journal `cc` line now committed; dispatch_launch per-class commits; mcp_server_stale; the serial transcript was re-recorded with an erratum (12 reworded subjects + 1 `unreconciled:` line).

**First `qc chart` toil reading** (2026-W42): 153 passes refused on machine dirt, 266 on other dirt, 4 re-issues, 0 redrives, 0 restarts.
- The W42 restart came from my own test (Part C's station check wrote the real stale log). Fixed in 0fb7930; the line was removed.
- The "other" dirt is mostly `models/models.lock.yaml` and its refresh receipt (machine-written, rewritten in place, outside R1's classes): Issue `models_lock_refresh_left_dirty_outside_r1`.
- Also in it: an unregistered filing, correctly left to c7.

**Premises found wrong:** none. **Judgment calls:**
- R5 runs premises at registration even for a task whose premise names a predecessor's output; such a task will now refuse until that output exists.
- `seldon_audit`'s mock did not reach the child in the 4a75674 run, so up to 5 real `claude --print` calls may have run (unverified).

**Issues:** resolved 02d52bc4, c5e0f12c, 59b2db84 (70bf1a21 was already resolved by DESK-002). Opened: the models-lock gap, and `commit_governed_scan_error_reported_as_secret_found`. The latter's scanner fails to import `squiddy` and reports it as a secret, so the SQ8 handoff `handoffs/2026-10-17_desktop_sq8_friction_class_ad038_work_order.md` stays untracked. c7 will name it; it needs its writer, or the fixed scanner.
**`seldon verify --fix`:** every check green except governed docs, where 13 files (this RESULT, AD-038 and today's Desktop task files among them) are uncataloged. `make -C governed catalog` refuses on squiddy pin drift (pinned a1e991c); the repin needs squiddy's ~75-min kit pass, which is outside this task. `seldon decision project` projected AD-038-R1..R6. `seldon cc complete`: c48b3fd6 completed.
