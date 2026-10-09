# RESULT: SEL-005, the standing dispatcher runs for seldon and squiddy
**Date:** 2026-10-09. **Task:** `41ef588e`. **Model:** `claude-opus-5-5` (primary). **Addenda:** none existed. Ran after PA-001's RESULT merged (`a9ceaeb`).
**Config blocks.** `seldon/seldon.yaml` and `squiddy/seldon.yaml` `dispatch:`. ai-readiness-kg's values and reasons are copied:
- `branch: main`, `poll_interval_s: 300` (no measured basis), `permission_mode: bypassPermissions`;
- STOP, lease and log paths; the local `osascript` notifier; `stuck_after_passes: 3`; `max_parallel: 1`; `cadence: []`;
- new key `launchd_label`;
- `standing_band_ref` points at squiddy's machine-wide spend configuration by reference: `../squiddy/squiddy/spend.yaml#job_token_cap_default` (squiddy: `squiddy/spend.yaml#...`), 2,000,000. DN-042's config has no daily integer; R-179's `job_token_cap_default` ("a job whose runner has no cap of its own") is what a dispatched session is. A task declaring more waits for a pasted line;
- log caps in a new `jobs.dispatch` block, read by the wrapper.
**Plists.** `scripts/jobs/com.brock.{seldon,squiddy}-dispatch.plist` and `{seldon,squiddy}_dispatch.sh`, tracked in each repo.
- `RunAtLoad` false, `AbandonProcessGroup` true (AD-034 premise 5), StartInterval 300 (the wrapper refuses drift).
- The wrapper reads Neo4j credentials from the repo's `.env`, then `~/.wintermute/.env`, never echoed.
- Installed by symlink in `~/Library/LaunchAgents`, bootstrapped. Launches use the lock's `primary` role and env block through the existing dispatcher (AD-035-R3).
**Dry runs** (step 3, `dispatch status` and `once --dry-run`, enabled in the working copy):
- seldon: 17 open, 0 candidates. 16 have no source file; SEL-003 `e60b17fe` lacks the Spend and Framework headers.
- squiddy: 0 open.
- Nothing would launch, so no task needed its state set.
**First live pass** (`launchctl kickstart`, 2026-10-09T20:38:01Z), both repos: `nothing eligible`, `push: pushed 2 commit(s)`, `=== rc=0`. seldon also logged `record: seldon_events.jsonl NOT committed: written by human`, events from this session's own task updates. No launch.
**`seldon go`.** Always prints `**dispatch: on|off** (<why>)` from `seldon.core.dispatch.dispatch_state`: block loads, `enabled`, no STOP file, `launchd_label` job loaded. JSON gains `dispatch_state`. Tests in `tests/test_go.py` cover on, off with no block, off when the job is not loaded, disabled, and the STOP file. Live: seldon on, squiddy on.
**Suites:** seldon 2286/0/0/0/0. squiddy 1938/0/0/0/1 (pre-existing item 15 harvest_walk_complete).
**Findings.**
- ai-readiness-kg's dispatcher, the only one before this task, reports `dispatch: off (STOP file .seldon/DISPATCH_STOP present)`. Left as found.
- A dispatcher pass pushes `main`; the first passes pushed this task's merges.
- squiddy's `logs/` was not gitignored for dispatch logs; added.
**Tokens:** about 0.1M of this session (budget counter); zero model calls.
