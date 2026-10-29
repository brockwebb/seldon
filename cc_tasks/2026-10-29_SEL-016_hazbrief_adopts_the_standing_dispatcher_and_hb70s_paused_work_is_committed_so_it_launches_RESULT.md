# RESULT: SEL-016, hazbrief adopts the standing dispatcher; HB-70's wip is on main, and HB-70 is not a candidate

**Task:** `c4d813a9`, `cc_tasks/2026-10-29_SEL-016_hazbrief_adopts_the_standing_dispatcher_and_hb70s_paused_work_is_committed_so_it_launches.md`.
No addenda existed at launch.
**Date:** 2026-10-29. **Branch:** `worktree-twinkling-drifting-walrus` (this RESULT only; every other change is in
hazbrief-mcp).
**Outcome:** Parts A and B done. Part C stopped, as the stop condition says, at the first pass. That pass launched
nothing. HB-70 can never launch as registered: it is `NOT A CANDIDATE (no_source_file)`, and behind that its Spend
header fails c4 (`spend_unreadable`). The remedy is a re-filed HB-70R (below). The finding is not worked around here.
**Spend:** 106,603 tokens at Part B's boundary (`part_complete`), against an estimate of 0.3M. Zero model calls.
**Network:** hazbrief's own dispatcher pushed hazbrief main on its first pass. This session pushed nothing (the launch
clause forbids it); seldon is pushed by the dispatcher's merge.

Recall used: seldon:2026-10-26_SEL-010R2_dispatch_waits_for_the_desktop_ooda_between_chained_tasks_RESULT, seldon:AD-038-R11

(SEL-010R2's RESULT supplied the adopt dry run against hazbrief that I repeated before writing anything. Its R11
finding, that registration and candidacy read only the base file, is why the HB-70 remedy below is a re-filed task
and not a fourth addendum.)

## Part A: HB-70's paused work is committed on hazbrief main

- **`b587409`** `HB-70 (wip): the paused work as it stands, so the dispatcher launches HB-70 from main`. It went in
  through hazbrief's hooks (`core.hooksPath=.githooks`). 17 files, +604/-38:
  - the nine modified source and test files, plus `eval/harness.yaml`, as listed in `git diff --stat` (11 files,
    315 lines);
  - HB-70's two registration lines in `seldon_events.jsonl` (`artifact_created 8d66641d`, `link_created precedes`
    from HB-69);
  - `docs/evidence/hb70/sq052r_gate_stderr.log`, a copy of `logs/2026-10-29_sq052r_gate_stderr.log` (5,430 bytes;
    the original stays in `logs/`; ADDENDUM-02 item 3).
- **Decided: five untracked files the task did not list went into the same commit.** They are
  `src/hazbrief/brief/stated_wind.py`, `docs/schema/scenario_stated_wind.schema.json`, HB-70's own base task file,
  and its ADDENDUM-00 and ADDENDUM-01. All five are HB-70's paused work. The reasons:
  - `derive.py:2021` imports `hazbrief.brief.stated_wind`, so without that file main would import a module it lacks.
  - The dispatcher reads the task file from main, and a worktree launched from main would not see an untracked
    file.
  - An untracked file also leaves the tree dirty for c7.

  The task's "nine files" count did not include them. The commit body says so.
- **`52e6eac`** commits `cc_tasks/2026-10-29_HB-70_ADDENDUM_03_the_dispatcher_launches_hb70_from_main.md`. It says:
  - the wip is at `b587409`;
  - ADDENDUM-02 items 1 and 2 are superseded by a dispatcher launch in a worktree from main;
  - item 3 is done;
  - HB-70 resumes from ADDENDUM-01 item 4, and merge, push and complete are left to the dispatcher.

  Part C's finding below means that launch cannot happen as HB-70 is registered. ADDENDUM-03 stays correct for the
  re-filed task.
- Nothing else was run in hazbrief. HB-70 was not advanced.

## Part B: adopted, loaded

- **Read first:** seldon's own `dispatch:` block. Then a dry run of `seldon dispatch adopt --project
  /Users/brock/GitHub/hazbrief-mcp --yes --dry-run --standing-band-ref
  ../squiddy/squiddy/spend.yaml#job_token_cap_default --gate-command "uv run pytest tests/ -q -p no:cacheprovider"`.
  It proposed 17 `dispatch:` keys and 3 `jobs.dispatch` keys. Then the same command ran without `--dry-run`.
- **The gate command** is hazbrief's CLAUDE.md suite (`uv run pytest tests/`), quiet and without the cache plugin.
  hazbrief's tests read no `.env`: conftest sets replay mode. So nothing from the primary checkout is needed.
- **Edits after adopt** (`f98e44b`, through the hooks):
  - Every placeholder comment ("Copied from the kit's dispatch block ... where its reason is") is replaced by the
    reason in seldon's block, restated, together with the `jobs.dispatch` caps' reason.
  - `enabled: true`.
  - The notify banner is titled `hazbrief`.
  - **`dispatch.stations.environment_ref: seldon.yaml#environment.packages`**, with a new top-level
    `environment: {packages: [squiddy, seldon]}`. Each name resolves to the sibling directory of that name, and
    `stations.environment_repositories` returns exactly `{squiddy: ../squiddy, seldon: ../seldon}`.
  - Why not `decisions.repositories`, which is where seldon's environment comes from: the decision register
    (`decisions.py:865`), recall (`recall.py:239`) and `cross_project.py:151` read that key too, and federating
    hazbrief's register is not this task. Why not squiddy's `kit.yaml#environment_packages`: it names `[seldon]`
    only.
  - **`stations.interpreter` is deliberately undeclared.** hazbrief's `.venv` has no seldon (`import seldon`
    fails), and a declared interpreter runs a check's `seldon` as `<interpreter> -m seldon` (AD-037-R15).
  - **Gap, recorded and not fixed:** a hazbrief Part check whose first word is `pytest` therefore runs under the
    dispatcher's anaconda python, which lacks hazbrief's dependencies. squiddy hit this in SQ-019 and fixed it by
    putting seldon in its venv. hazbrief needs the same before its tasks declare `pytest` checks.
- **Validated:** `load_dispatch_config` and `load_stations_config` load the edited block (headers
  `('Spend', 'Network')`, label `com.brock.hazbrief-mcp-dispatch`). `seldon dispatch status` in hazbrief reads the
  band `2,000,000 tokens <- ../squiddy/squiddy/spend.yaml#job_token_cap_default`, with the tree clean.
- **Not needed:**
  - No `.seldon/` or ignore changes: adopt wrote none, because hazbrief already ignores `.seldon/`, `logs/` and the
    worktrees.
  - `seldon hooks install`: `core.hooksPath` was already `.githooks`.
- **Loaded:**
  - `ln -s .../hazbrief-mcp/scripts/jobs/com.brock.hazbrief-mcp-dispatch.plist ~/Library/LaunchAgents/`.
  - `launchctl bootstrap gui/502 ...` returned exit 0.
  - The uid is 502. `gui/501` failed with 125 first, and that call loaded nothing.
  - `launchctl print` reads `run interval = 300 seconds`.
- **Label:** `com.brock.hazbrief-mcp-dispatch`.

## Part C: the first pass

hazbrief's dispatch log is `/Users/brock/GitHub/hazbrief-mcp/logs/seldon_dispatch.log`. It is gitignored.

```
=== 2026-10-29T12:49:06Z | seldon-dispatch fire
record: record: dispatch_refused fd1b07c7 — 1 line(s) written by dispatcher; reconciled by the standing dispatcher (event_store, AD-038-R1) -> 76d06db
push: pushed 5 commit(s)
refused: environment_in_flight: a dispatcher holds a lease on seldon, which this project's environment names
=== rc=0
```

- **No launch line, no worktree, no session log.** The pass looked at HB-63 (`fd1b07c7`), the one eligible task, and
  refused it with **`environment_in_flight`**.
  - The lease it found is held by `dispatcher:HexagonMBP.local:48283` for task `c4d813a9`. That is SEL-016, this
    session.
  - So the environment premise wired in Part B worked on its first pass: it held hazbrief's queue while a seldon
    task was in flight.
  - Effect: while any seldon task runs, hazbrief launches nothing. That is the premise as AD-037-R6 (a) states it.
- **HB-70 (`8d66641d`) was not evaluated at all.** `seldon dispatch status` before the plist loaded reported it as
  `NOT A CANDIDATE (no_source_file)`. Reason codes:
  1. **`no_source_file`.** HB-70's registration (`artifact_created`, actor `desktop`, 2026-10-29T01:40:43Z, now in
     `b587409`) carries only a `description`. It has no `name`, `source_file` or `file_hash`. HB-63's registration
     has all three. `evaluate` (`seldon/core/dispatch.py:2273`) makes a task with no `source_file` a non-candidate.
     The file was also never committed, so this registration did not go through `seldon cc register`. That path
     commits the file and writes `source_file`.
  2. **`spend_unreadable`, latent.** Run on HB-70's file, `static_checks` (the checks `cc register` refuses on)
     fails: `Spend header 'none. No model call.' names neither zero nor a token count`. HB-64 (`0448b253`) fails c4
     the same way.
  - Under AD-038-R11 an addendum cannot supply a base header, so neither code can be cleared by an addendum.
- **What the next pass does.** It runs once this session's lease is released. It will launch **HB-63**, not HB-70:
  HB-63 is eligible on every criterion. HB-64 stays held on c2 (After HB-63) and on c4. If HB-63 should not run
  unattended, the line is in "For the operator" below.

## For the operator

Run 1 now if HB-63 must not launch unattended; otherwise skip it. Then 2 in the hazbrief Desktop thread, then 3.

1. *(Optional; shell, any directory.)* Hold hazbrief's queue without editing config:
   `touch /Users/brock/GitHub/hazbrief-mcp/.seldon/DISPATCH_STOP`. Release it with
   `rm /Users/brock/GitHub/hazbrief-mcp/.seldon/DISPATCH_STOP`.
2. *(hazbrief Desktop thread.)* File HB-70R as a new task file. It is the same work with a base that registers:
   - **Spend:** `zero` (no model calls);
   - **Network:** HB-70's line;
   - **After:** HB-69, as HB-70 has;
   - a body that points at HB-70 and its ADDENDA 00 to 03 and resumes from ADDENDUM-01 item 4.

   Register it so `source_file` is written and the file is committed:
   `seldon cc register --project /Users/brock/GitHub/hazbrief-mcp cc_tasks/<HB-70R file>`.
   Then mark HB-70 (`8d66641d`) superseded by it.
3. *(Optional.)* Re-file HB-64 the same way (`**Spend:** zero`) if it should launch after HB-63.

## Deliverables

| | |
|---|---|
| A | hazbrief `b587409` (wip, evidence copy, registration lines, HB-70's untracked files); `52e6eac` (ADDENDUM-03) |
| B | hazbrief `f98e44b` (`dispatch:` and `jobs.dispatch`, environment, plist); plist loaded as `com.brock.hazbrief-mcp-dispatch` |
| C | first pass 2026-10-29T12:49:06Z: `environment_in_flight` on HB-63 (`76d06db`, the dispatcher's record); HB-70 `no_source_file` (plus latent `spend_unreadable`) |

hazbrief main is pushed (`## main...origin/main`, by its dispatcher's first pass). No tests were written. The task
changes no seldon code, so no suite was run. The only change in seldon is this RESULT.
