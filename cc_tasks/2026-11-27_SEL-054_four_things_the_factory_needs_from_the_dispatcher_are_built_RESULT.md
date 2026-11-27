# RESULT: SEL-054, four things the factory needs from the dispatcher are built

**Task:** `cc_tasks/2026-11-27_SEL-054_four_things_the_factory_needs_from_the_dispatcher_are_built.md` (`5ef8838d`).
**Branch:** `worktree-twinkling-noodling-meadow`. Not merged or completed here; the dispatcher merges on green.
**Addenda:** none existed (`*SEL-054*ADDENDUM*.md` matched nothing).
**Decisions:** AD-038 ADDENDUM 16
(`docs/design/AD-038_ADDENDUM_16_a_coordination_lane_project_premises_a_minted_session_identity_and_tried_limits.md`),
rulings AD-038-R40 to R45, six pending register records. `seldon prior-art verify` passed on the note before the code
commit.

Recall used: none. I did not open the eight recall hits. The approach came from the code and from the session memory
on worktree guards and returns (`addendum-receipts-and-returns-traps`).

## Part A: the launch path

1. **A coordination task launches beside an exclusive build (R40, R41).** Configuration:
   `dispatch.coordination_lane: {name_pattern, slots, writes, merge_wait_s}`.
   - **What I found.** The planner was not the only thing in the way. An exclusive task runs in place with the pass
     lease held for its whole session, so every later pass exits on `lease_held`. Nothing could launch anything
     during a build, at any `max_parallel`.
   - **The holder launches the lane task.** The one process awake during a build is that build's holder, which
     inspects its session every `poll_interval_s` and holds the lease. Each inspection tick now looks for a lane
     task and launches it. It uses the same claim, record, push and supervisor as any worktree launch
     (`dispatch_lane.launch_beside`). The lease is marked `pass` while the tick writes main and `session` after.
     A failed look is recorded as `dispatch_lane_error` and never reaches the build.
   - **Ordering and slots.** A lane task goes first among eligible candidates (`fifo(rows, lane)`). It always runs in
     its own worktree under its own supervisor, and it takes a reserved lane slot, not a `max_parallel` slot.
     `plan_launches` does not hold a lane task behind an exclusive task, running or waiting, and a lane task does not
     hold one back. A full lane defers the next lane task as `lane_slots`.
   - **The slot follows the supervisor, not the graph.** A lane slot stays held while its supervisor's worktree lease
     is live, whatever the graph says. The first scenario test caught this: the stub session completed its own task
     in the graph, and a second OODA launched under the first one's pending merge.
   - **The merge wait.** A lane supervisor waits up to `merge_wait_s` for the pass lease at its finish (default
     14,400 s; no measured basis, chosen to exceed FAC-31's ninety minutes). A build's holder keeps the lease until
     the build finishes, and the old 600 s wait would have left the lane task `released_unfinished`.
   - **What a lane task may write (R41).** The lane's `writes` list is required. The merge round refuses a lane
     branch that changes anything else, as `merge_blocked` with reason `lane_wrote_outside`, and names the paths.
     Exempt: the task's own RESULT, `merge=union` files and the gate record ledger.
2. **Project premises (R42).** Configuration: `dispatch.premises: [{statement, check}]`. Each check is an opaque
   command, run before every launch: serial, parallel and lane.
   - A false premise refuses the launch. stderr carries the statement, the exit code and the check's output (the
     grant id).
   - It is a standing condition: one `dispatch_refused` with reason `project_premise_false` per episode, the stuck
     streak, and no Issue. It clears on the first pass where every premise holds.
   - Merges, redrives and the stuck alarm run earlier in the pass and are not affected.

Acceptance: `git log --oneline main..HEAD -- tests` lists `9016be0` (the red tests) and later commits.

## Part B: identity and tried limits

3. **One board identity per session, minted at launch (R43).** Configuration:
   `dispatch.hive: {mint_command, notices_hook, secrets_dir, mint_timeout_s}`.
   - **Where it is minted.** The pass mints for in-place sessions and the supervisor mints for worktree sessions.
     Both run `mint_command` outside the session, with `HIVE_PROJECT`, `HIVE_TASK`, `HIVE_TASK_NAME` and
     `SELDON_SESSION_ID` set. The command prints the token, alone or as `{"token","identity"}`.
   - **Where the token goes.** Only into the session's environment, as `HIVE_TOKEN` with `HIVE_PROJECT` and
     `HIVE_TASK`.
   - **What is recorded.** `session_identity` records the identity's name and a 12-character sha256 prefix of the
     token. A test checks that the token appears in no event and not on the launch line.
   - **Failure handling.** An inherited `HIVE_TOKEN` is stripped from every session. A failed mint is recorded, and
     the session launches without a token: a post is context and never a gate (DN-005 decision 3).
   - **The notices hook.** `notices_hook` goes on the launch line as a PostToolUse hook, for every project that
     declares the block.
4. **The session guard (R44).** The PreToolUse tool gate now refuses any call that names a path under
   `dispatch.guard.deny_paths` or `dispatch.hive.secrets_dir`.
   - It checks a file tool's path argument (resolved) and the text of a Bash command or search (the resolved form
     and the `~`, `$HOME` and `/private` spellings).
   - It runs before the event store is read. The paths travel on the hook's own command line (`--deny-path`).
   - It is a guard, not a wall: sessions run as the operator's Unix user.
5. **Every limit tried by a plant (R45).**
   - **When the controls run.** Before any launch, whenever the fingerprint of the limits changes, and on demand with
     `seldon dispatch controls`, which exits 2 if a limit fails.
   - **The guard control.** A planted `Read` and a planted `Bash cat` for each guarded path are fed to the hook
     command the launch line installs.
   - **The spend-ceiling control.** The inspector runs over a planted session at twice its ceiling and must write
     the `spend_ceiling` hard stop.
   - **Recording and refusal.** One `limits_tried` record per fingerprint. A limit that lets its plant through
     refuses every launch as `limit_control_failed` (a standing condition, in the stuck streak) until the limits
     change and hold. A test removes `--deny-path` from the launch line and checks that the guard control fails and
     launches stop.
   - **The Network line is untried, with the reason recorded.** seldon only passes `SELDON_NETWORK_ALLOWLIST`; it
     enforces no host rule of its own.
   - **FAC-31's syntax failure cannot occur here.** The single-slash rule cannot be written by seldon's launch line,
     because `dispatch.allow` refuses anything but `Bash(<pattern>)` at load. A test holds that. So the guard is the
     launch line's one path limit, and it is tested by plants, not by reading its syntax.

Live readings on 2026-11-27:
- `seldon dispatch controls` on seldon's own config: spend ceiling held (2,400,000 against a 1,200,000 ceiling);
  network untried; fingerprint `dabb4665359ae3c7`; exit 0.
- The guard, set to factory's real `~/.factory/hive/secrets` and tried through the installed hook command: both
  plants refused (`/tmp/sel054/trial_guard.py`). Nothing under that path was read.

## Tests

- Red first: commit `9016be0`, before any wiring: 28 failed and 10 passed. The 10 that passed exercised only the new
  pure modules, which existed at that point.
- Green: `tests/test_sel054_launch_path.py` (17) and `tests/test_sel054_identity_and_controls.py` (21) all pass
  against the scratch Neo4j database. Three of them run real passes with the stub CLI:
  - an OODA filed during an exclusive build launches during the build (by rendezvous) and merges after it, while a
    second OODA waits;
  - a lane branch that writes outside its lane is blocked `lane_wrote_outside`, naming `src/build.txt`;
  - a false project premise refuses two passes with one record and no Issue, and the task completes once the
    premise clears.
- `tests/fixtures/dispatch_serial_transcript.txt` was re-recorded for one intended change: `limits_tried` joins the
  first launch's record commit (5 lines instead of 4), and the UUID placeholders renumber after it. The test passes
  unrecorded.
- Related suites (every `test_dispatch*`, `test_disp0*`, `test_friction002*`, `test_sel0*`, `test_station*`,
  `test_stations*`, `test_qc00*`, `test_desk*` and `test_hook*` file), `-n 6`: 1,239 passed, 1 skipped, 1 failed
  in 41 min 31 s. The failure was `test_dispatch_parallel.py::test_union_merge_of_two_event_appends_is_valid`,
  blocked `main_kept_moving` under load. That is the known union-merge flake (Issue `88c9f4d8`), and it passed three
  times out of three run alone on this branch. The full gate is left to the dispatcher's merge round (see below).

## Not done, and why

- `seldon dispatch status` under `max_parallel > 1` (`dispatch_worktree.survey`) does not show the lane's ordering
  or c6; the pass applies both. No project runs a lane in parallel mode today.
- I read the four filings in full and factory's DN-005 decision 2 and `scripts/hive.py` `session_token`. I did not
  read FAC-29, FAC-30, FAC-31 and FAC-35's RESULTs or DN-003 and DN-004 in full. The filings quote what this task
  needed from them.

## For the consumer

One return goes to factory and answers all four filings. It is written from the next section and filed with
`seldon cc return` once for each filing.
The return is factory FAC-48 (`afc7586b`,
`factory/cc_tasks/2026-11-27_FAC-48_what_seldon_built_for_the_four_dispatcher_filings_of_2026_11_26_and_27.md`), and
its registration committed it in factory. All four filings are completed in seldon's graph (AD-036-R17): `82f9d4f1`
(lane), `81e09bae` (project premise), `654bdd98` (Hive identity) and `925f4577` (planted controls). Filing `3619898e`
(seldon main's full gate red on two tests) arrived beside this task and is not answered here.

## For factory

**Title:** what seldon built for the four dispatcher filings of 2026-11-26 and 27

This return covers seldon SEL-054's answers to four factory filings: the coordinator lane, the project premise, the
minted Hive identity and the planted controls. The changes are on seldon's branch `worktree-twinkling-noodling-meadow`
and reach factory when seldon's dispatcher merges it, since factory runs seldon's editable code. Decisions:
AD-038-R40 to R45 (`seldon/docs/design/AD-038_ADDENDUM_16_...md`).

### What factory does

1. **Turn the lane on (coordinator filing).** In factory's `seldon.yaml`, under `dispatch:`, add:

       coordination_lane:
         name_pattern: '^OODA-\d+'
         slots: 1
         writes: ['cc_tasks/**', 'for_operator/**']

   Correct `writes` to the paths an OODA really changes in factory. A lane branch that changes anything else is not
   merged (`lane_wrote_outside`). Then set `order_oodas_first: false` in `scripts/coordinator_tick.yaml`.
2. **Declare the grant premise in each project with a dispatcher (premise filing).** Under `dispatch:`, add:

       premises:
         - statement: "<project>'s seldon_sessions grant has room"
           check: "<cost_manager.py premise --project <project> --unit seldon_sessions, as that command prints it>"

   A spent grant then refuses new launches with `project_premise_false`. stderr carries the check's output (the
   grant id). There is one record per episode and no Issue, and launches resume when the check passes. Merges and
   redrives continue.
3. **Give the dispatcher a mint command (Hive filing).** `scripts/hive.py` needs a command that mints one identity
   and prints it as `{"token": ..., "identity": "<project>.<session8>"}`. seldon runs it with `SELDON_SESSION_ID`,
   `HIVE_PROJECT`, `HIVE_TASK` and `HIVE_TASK_NAME` set. It should not write `sessions/<id>.json`: the session gets
   the token from `HIVE_TOKEN`. `session_token` should then return `HIVE_TOKEN` when it is set, as the filing said.
   In each project that should get identities and notices, add under `dispatch:`:

       hive:
         mint_command: /opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/hive.py <the mint command>
         notices_hook: /opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/hive.py notices --hook
         secrets_dir: ~/.factory/hive/secrets

   A failed mint does not stop a launch. It is recorded as `session_identity` with `minted: false`. Then remove the
   notices hook from factory's own `.claude/settings.json`, so factory's sessions do not run it twice.
4. **Planted controls (controls filing).** No step for factory. A dispatcher tries its limits before its first launch
   after the merge. To see the result in a project, run `seldon dispatch controls` there. Seldon's launch line admits
   only `dispatch.allow` rules (`Bash(<pattern>)`). The Hive client is admitted one call at a time only if a
   project's `dispatch.allow` lists it, for example `Bash(/opt/anaconda3/bin/python /Users/brock/GitHub/factory/
   scripts/hive.py *)` with the task instruction that needs it. Otherwise auto mode's classifier decides each call.

### Acceptance

- `check: sh -c "grep -q coordination_lane seldon.yaml"` passes.
- `check: sh -c "grep -q 'order_oodas_first: false' scripts/coordinator_tick.yaml"` passes.
- `check: sh -c "grep -q HIVE_TOKEN scripts/hive.py"` passes.
