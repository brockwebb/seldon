# RESULT: SEL-022, the DD-007 refusal rings the stuck alarm once and stops dirtying the event log

**Task:** `110feeac`, `cc_tasks/2026-11-01_SEL-022_the_dd007_refusal_rings_the_stuck_alarm_once_and_stops_dirtying_the_log.md`.
No addenda were filed.
**Branch:** `worktree-swirling-fluttering-clover`. Code, tests and the design-note sentence are in `d2987dc`; the closing
commit carries this file. No merge, push or `cc complete`: the dispatcher does those.
**Parts:** A recorded with `seldon dispatch part-complete` at 140,956 tokens, 1,456 s. B recorded after this commit.
**Premises:** both held. `api_key_present` was emitted at its own site in `dispatch_once` before the lease;
`EVENT_STUCK` and `_run_notifier` exist.
**Stop condition:** not reached. The DD-007 check is still the first thing `dispatch_once` does after loading config,
before the STOP file, the hook check, the lease and any claim. No pass under a planted key takes the lease (the test
asserts `.seldon/dispatch.lock` never appears). No other refusal changes behaviour (see "Decisions" 3).

Recall used: AD-038-R1

AD-038-R1 (lines written outside the lease get committed by the next pass that holds it) is why I looked for a way to
commit without the lease. An API-key outage has no pass under the lease for as long as it lasts. Following R1 alone
would leave the alarm's own lines dirty in the tree for the whole outage, so `git status --porcelain` would not be
empty. `commit_journal_append` is the existing writer-outside-the-lease commit that MCP tools and `dispatch redrive`
use. It probes the lease and never takes it, and that is what this change uses.

## Part A: standing pre-lease refusals join the streak

- **`api_key_present` is a standing condition** (`_api_key_present` in `seldon/commands/dispatch.py`). It follows
  AD-038-R6's `_database_unavailable` pattern. A state file `dispatch_api_key.json` (`D.API_KEY_STATE_FILE`) sits
  beside the lease and holds `{first_seen, passes, variable}`.
  - The first pass of an outage writes one `dispatch_refused` that names the variable. Its value is never read into
    any file, event or notification.
  - The streak uses the key `dispatcher:api_key_present` (`D.standing_key`) in the same `dispatch_stuck.json`, and
    is advanced by the same `advance_stuck`. When it reaches the threshold it writes one `dispatch_stuck` (criterion,
    variable, passes, threshold, first_seen, remedy) and runs `notify` once.
  - Later passes print `refused: ... pass N since ...` and write nothing.
  - Lines that were written are committed by `commit_journal_append`. A live lease holder defers the commit to its
    next pass (AD-038-R1).
  - The first pass without the key deletes the state file and the streak entry, and prints
    `api_key_present cleared after N refused pass(es)`.
  - A dry run prints and writes nothing.
- **Default threshold `api_key_present: 1`** (`STUCK_AFTER_PASSES_BY_CRITERION_DEFAULT`).
- **`lease_held`**: a live holder PID is unchanged (one refusal per acquisition, no alarm). A dead holder PID whose
  flock is still held (for example, an orphan inherited it) counts in the streak `dispatcher:lease_held`, once per
  acquisition (keyed on holder and `acquired_at`). At `stuck_after_passes` (3) it writes one `dispatch_stuck` whose
  `remedy` names `seldon dispatch lease reap`, and runs `notify` once. Nothing reaps automatically. A pass that takes
  the lease, or sees a live holder, clears that streak.

### Decisions (grounded, logged here)

1. **Commit via `commit_journal_append`, not by taking the lease.** Taking the lease after the refusal would still
   keep the check before the lease. But the existing test `test_an_api_key_refuses_before_any_claim` asserts that no
   lease file appears, and the stop condition's intent is that a key-present pass never touches the lease. Probing
   the lease is the precedent already used by every writer outside the lease.
2. **The new default also applies under a project map that does not name it.** I checked the consumers.
   `dispatch adopt` copies the kit's `stuck_after_passes_by_criterion: {dirty_tree: 1}` into each one: hazbrief-mcp,
   factory and aacps-ai-policy all carry it. Under the old replace semantics, the code default would never reach
   hazbrief, which is the case that motivated this task. So `load_dispatch_config` now merges
   `STUCK_AFTER_PASSES_BY_CRITERION_UNLESS_NAMED = {"api_key_present": 1}` under the project's map.
3. **Only that key is merged.** Several tests (and possibly operators) write `{}` to give `dirty_tree` the 3-pass
   threshold. A full merge of the defaults would change `dirty_tree`'s behaviour under such a map, which the stop
   condition forbids. An explicit project value for `api_key_present` still wins.
4. **Task streaks are untouched by a pre-lease pass.** It has not observed the queue (the same rule as a pass whose
   tree read failed).

### Tests

`tests/test_sel022_standing_pre_lease_refusals.py` uses a scratch repo with a tracked store, a stub `claude` and zero
model calls:

- `test_the_default_thresholds_ring_api_key_present_on_its_first_pass`
- `test_a_copied_project_map_still_rings_api_key_present_on_its_first_pass`: `{dirty_tree: 1}` gives
  `api_key_present: 1`, `{}` keeps `dirty_tree` absent, and an explicit value wins.
- `test_a_planted_key_rings_once_writes_nothing_more_and_clears_when_removed`. A planted `ANTHROPIC_API_KEY` in
  `.env` gives:
  - exactly one `dispatch_stuck` and one `dispatch_refused`, and one `notify` line;
  - the value appears in neither the log nor the notification;
  - porcelain is empty and HEAD is the record commit.
  Ten more passes leave the log bytes, HEAD and porcelain unchanged, with `passes == 11` and no lease file. Removing
  the key: the next pass proceeds, prints the cleared line, and the state file and streak entry are gone. A new
  outage rings again.
- `test_a_dry_run_under_a_planted_key_writes_nothing`
- `test_a_dead_holder_lease_rings_once_naming_lease_reap`: one stuck event at pass 3 of 7, naming
  `seldon dispatch lease reap`, one notify, and still one `lease_held` refusal.
- `test_a_live_holder_lease_raises_no_stuck_event`

Unchanged and passing: `test_a_second_pass_under_a_standing_condition_leaves_the_event_log_byte_identical` (all five
parametrizations) and `test_an_api_key_refuses_before_any_claim`. The DD-007 child-environment strip
(`_run` in `seldon/commands/dispatch.py`: `k not in D.API_KEY_VARS`) is not in the diff.

**Full suite** (`python -m dotenv -f .env run -- python -m pytest tests/ -n 6`): 3136 passed, 7 skipped, 1 failed in
25:58. The failure is `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`,
which raises `release_unavailable` because squiddy's live `graphs/library/extract/control.yaml` `index:` block
differs from the release commit `edd5d5d66bf2`. It reads a sibling repository's state, fails on main for the same
drift (recorded 2026-10-24), and neither `seldon/core/prior_art.py` nor that test is in this branch's diff.

## Part B: the record

The event lines a planted-key run writes, verbatim. The run used the scratch project from `tests/dispatch_scaffold`,
`ANTHROPIC_API_KEY=sk-ant-planted-not-real` in `.env`, and three passes:

```
{"event_id": "1b2b2451-d6a0-4a30-81ce-c9b305640ef5", "event_type": "dispatch_refused", "timestamp": "2026-11-01T12:48:21.153927Z", "session_id": "e257b501-4d44-47de-ae96-5a6921bbfa84", "actor": "dispatcher", "authority": "accepted", "payload": {"task_id": null, "reason": "api_key_present", "variable": "ANTHROPIC_API_KEY", "first_seen": "2026-11-01T12:48:21.153181Z"}}
{"event_id": "b17c2a4d-6cf2-4a16-b3f7-f1995668088d", "event_type": "dispatch_stuck", "timestamp": "2026-11-01T12:48:21.189701Z", "session_id": "e257b501-4d44-47de-ae96-5a6921bbfa84", "actor": "dispatcher", "authority": "accepted", "payload": {"task_id": null, "name": "dispatcher", "criterion": "api_key_present", "passes": 1, "threshold": 1, "first_seen": "2026-11-01T12:48:21.153181Z", "variable": "ANTHROPIC_API_KEY", "remedy": "remove ANTHROPIC_API_KEY from the dispatcher's environment and the project's .env (DD-007)", "poll_interval_s": 300}}
```

Passes 2 and 3 wrote nothing. The notifier received `stuck: api_key_present for 1 pass(es) since
2026-11-01T12:48:21.153181Z; remove ANTHROPIC_API_KEY from the dispatcher's environment and the project's .env
(DD-007)`. After the run, `git status --porcelain` was `''` and HEAD was `dispatcher: dispatch_refused, dispatch_stuck
- — 2 line(s) written by seldon dispatch once (api_key_present)`.

**Design note.** `docs/design/2026-09-15_standing_dispatcher.md` (SEL-005's note), under "Events", now has a paragraph
"Standing refusals ring once (SEL-022)". It names the standing refusals and how often each writes: the per-task
streak criteria, `database_unavailable`, `api_key_present`, `lease_held` with a dead holder, and the STOP file. It
also says that a live-holder `lease_held` raises no alarm.

## Open

- seldon's own `seldon.yaml` (the kit `adopt` copies from) still lists only `dirty_tree: 1`. The loader merge makes
  that harmless. Adding `api_key_present: 1` there would only be documentation, and `seldon.yaml` is outside this
  task's `Touches`, so it is left alone.
- A dead-holder lease's lines are deferred, as `lease_held`'s always were. They are committed by the first pass that
  holds the lease after `lease reap`.
