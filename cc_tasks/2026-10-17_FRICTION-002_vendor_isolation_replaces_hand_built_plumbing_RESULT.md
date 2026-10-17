# FRICTION-002 RESULT: worktree-only dispatch, Stop-hook completion gate, auto mode with the breaker

**Outcome.** All four Parts are done on `feat/friction-002` (576be40, ccb1ef9, 2b5cb17) and merged to main. The ruling text is in `docs/design/AD-034_ADDENDUM_01_worktree_is_the_only_mode.md`.
**Tokens:** 346,549 of the 1.0M estimate at the last measurement (input plus cache writes plus output, from `logs/dispatch/<stem>.log`). Part A used 61,747 at its `part-complete`. Parts B to D were built as one change in shared files (`_launch_inplace`, `finish_session`, `stop_gate`), so their split between `part-complete` records is not a measurement. Cache reads were 30.2M.
**Suite:** a full run on the branch gave 2623 passed, 4 failed, 1 skipped. The 4 were the serial transcript (×2) and `test_cadence_pass.py` (×2). Their fixes changed tests only (a fixture missing `.claude/` in its ignore, and a transcript re-recorded twice, byte-identical, with an erratum). Those two files then passed (14 passed). I did not run the full suite a second time.
**Tests on HEAD** (`docs/evidence/friction002/new_tests_on_head.txt`): 18 of 19 new tests fail on c756ec4. The one that passes is `test_a_write_to_the_primary_from_inside_the_session_is_refused_recorded_probe`, which reads the recorded vendor probes, so it holds the CLI's behaviour rather than ours. `test_live_cli_refuses_a_write_to_the_primary` is opt-in (`SELDON_LIVE_CLI_TESTS=1`, one model call).
**Isolation refusal text** (CLI 2.1.302, `--worktree`, under `bypassPermissions`):
- Write to the primary: "This session is isolated in the worktree …/.claude/worktrees/f002probe. Edit the worktree copy of this file instead of the shared-checkout path."
- `git -C <primary> commit`: "this command redirects git to the shared checkout via -C. Refusing to run it — a worktree-isolated session's git operations must target its own worktree."
**First classifier block count:** none measured. This run was launched under `bypassPermissions`, because it started before the switch, so it records no `classifier_block`. The three-task measurement and its kill rule are ResearchTask 65037d58.
**Live Stop-hook probe** (`docs/evidence/friction002/stop_gate_live_probe.jsonl`): the CLI honoured the block decision 13 times, then its default cap ("9 consecutive times — overriding and ending turn") ended the session with the check still failing.

## Premises found wrong
1. "The session merges to main on green, as AD-034-R5 says." AD-034-R5 has the supervisor merge, not the session, and the CLI's isolation now refuses a session's `git -C <primary>`. The dispatcher merges and completes every task (R5, R6). This task's own "merge before each part-complete" cannot be followed by a task dispatched after it.
2. "Hard isolation blocks a session's write to the primary" is only partly true. Edit/Write and git are refused. A plain shell redirect into the primary (`echo y > <primary>/file`) was written (`isolation_probe_bash.jsonl`). This is recorded in ADDENDUM 01 §4, and c7 plus the reconciler remain the catch. No new control was added (AD-038-R6).
3. "The Stop hook refuses to end the session while a check fails and the ceiling is not reached." The CLI overrides a Stop hook after its block cap. The live probe found a model that could not pass its check re-asserting that on every refusal. Fixes: the cap is set per launch (`stations.stop_hook_block_cap: 20`, no measured basis beyond that one probe), and a session the CLI lets go with its gate unpassed is never merged (`stop_gate_unpassed`, `worktree_kept`).
4. A worktree carries no gitignored `.env`, and every served repository keeps its Neo4j credentials there. `dispatch.worktree_links` now defaults to `[".env"]`.

## Changes other repositories inherit (shared code)
- squiddy, ai-readiness-kg and arnold now run every task in a worktree with the Stop and PermissionDenied hooks. Each already ignores `.claude/`.
- Their `permission_mode` stays `bypassPermissions` until their own `seldon.yaml` changes.
- `SELDON_NOTIFY_OUTCOME` now says `merged` / `session_failed` / … where it said `ok` / `blocked`.
- `dispatch.worktree_dir` and `branch_prefix` are refused at load. No repository sets either.
