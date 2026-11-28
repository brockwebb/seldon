# Reviewer report, part1 (/tmp/qz_delta/part1.diff), as returned to REVIEW-001

# Review: the SEL-052/054/055/056/057/058/060 delta (`/tmp/qz_delta/part1.diff`)

**Suite and lint.** I did not run the suite, as the brief asked. `ruff` is not installed. `python -m pyflakes` on the changed modules found one real defect, at `seldon/commands/cc.py:2191`: `undefined name 'update_artifact'`. That line predates this diff (see L2-7). The other pyflakes hits are unused imports and f-strings with no placeholders. `py_compile` passes on every new module.

## Deletion and guard accounting

| Removed or changed line (diff) | What it guarded | What guards it in the snapshot |
|---|---|---|
| `seldon.yaml` `--deselect tests/test_pa002_release_resolve.py::test_rebuilding…` | It kept a test that read squiddy's live library out of the full gate | The test now builds its own fixture (`tests/test_pa002_release_resolve.py:355-367`). It still skips through `importorskip("squiddy.index")` (`:361`), so a gate run where squiddy is missing passes without running it. Nothing checks that squiddy is installed. |
| `seldon.yaml` `-p no:cacheprovider` changed to `… -n 6` | No guard was removed | It adds a dependency nobody declared (L8-1) |
| `dispatch.py` `claim = _claim_in_flight(...)` (now only in the non-lane branch, `:1503`) | c6: one in-place claim in flight | Non-lane: `dispatch.py:1503`. Lane: `split_claims`/`apply_lane_c6` (`dispatch_lane.py:200-216`, `lane.py:98-113`). A running lane task is no longer a claim, so `claim is None` while a lane session runs (L1-3). |
| `dispatch.py` `_session_settings` hooks dict rebuilt | Stop gate, PermissionDenied, PreToolUse tool gate | All three are still emitted (`dispatch.py:2211-2243`); the tool gate is at `:2238` |
| `dispatch.py` `_run` env filter | It kept API keys and the inherited network allowlist out of a session | Still stripped, plus `HIVE_TOKEN` (`dispatch.py:2353`) |
| `dispatch_worktree.py` `if r["concurrency"]["exclusive"]:` changed to `… and not r.get("lane")` | An exclusive task ran in place, alone | `plan_launches` (`core/dispatch.py:666`) drops lane tasks from `running`, so exclusive tasks no longer wait for them. What replaces exclusion is the R41 merge check (`dispatch_worktree.py:1243`). The comment at `:337` ("only when nothing runs, and alone") is now false. |
| `dispatch_worktree.py` `_pass_lease` timeout | The pass/merge lease wait | `timeout_s or cfg["merge_lock_timeout_s"]` (`:669`). A lane waits `merge_wait_s`, which `lane.py:78-81` bounds. |
| `dispatch_worktree.py` `WT.link(...)` changed to `link_report` | Linking only what exists | It links the same way (`worktree.py:139-169`) and adds a record of what it skipped |
| `verify.py` inline `CONSTRAINED_BY … d.state <> 'accepted'` query and `fixable_only = False` | Binding findings were reported as **not fixable** | Same predicate at `core/decisions.py:1880-1887`. `fixable_only` is computed at `verify.py:236`, before binding findings are appended at `:265`, so they are now fixable on purpose (AD-033-R16) and `--fix` deletes the edges (`verify.py:477`). |
| `cc.py` `resolved.append(next(iter(ids)))` | The ambiguity and unresolved guards | Both kept. A new refusal of filings is set by `read_after` (`cc.py:451`) and `cross_project.py:222`. |
| `cc.py` `properties={"completed_at": …}` | Nothing | R41 evidence is added. Its guard is bypassable (L1-1, L2-1). |
| `gate.py`, `go.py`, `verify.py` `GP.warnings(...)` and `GP.plan(...)` calls | Nothing removed | They add `lane` and the closure |
| `project.py` plist load and `--enable` | launchd loaded from any checkout | In a linked worktree both are now skipped (added guard) |
| `models.lock.yaml` dates and evidence | Provenance of the alias probe | The evidence file exists (`docs/evidence/model001/refresh_2026-11-28.json`) |

## Lens 1: scope and invariants

- **ID:** L1-1
- **Severity:** major
- **Location:** `seldon/mcp_server.py:1506`; `seldon/commands/cc.py:1196`
- **Evidence:** The CLI guard is gated on state, `if current_state == "blocked": gate_props, gate_refusal = _blocked_completion(...)`. The MCP `seldon_cc_complete` calls `transitions = _walk_task_to_completed(..., current_state=current_state, ...)` with no `_blocked_completion`. The state machine allows `blocked: [accepted, in_progress, superseded, withdrawn]` (`seldon/domain/research.yaml:1318`).
- **Why it matters:** AD-034-R41 says a blocked task completes only on gate evidence or a recorded override. A Desktop thread can complete a hand-merged blocked task through the MCP tool, which is the HB-221 path. Anyone can also step it out of `blocked` first (`seldon task update --state in_progress`), and then `cc complete` never sees `blocked`.
- **Fix:** Move the R41 check into the shared completion walk that every entry point uses, `walk_to_completed`/`_walk_task_to_completed`. Key it on "the task's walk starts at or passes through `blocked` since its last `dispatch_finished merged`", not on the state at call time. Add `ungated` to the MCP tool.

- **ID:** L1-2
- **Severity:** major
- **Location:** `seldon/commands/dispatch.py:1488` and `:1553`; `seldon/commands/dispatch_worktree.py:280`
- **Evidence:** `_held(...)` is called only in the serial `_pass`, after `return W.pass_parallel(...)` has already returned for `max_parallel > 1`. `pass_parallel` calls `S._stuck` and never `_held`.
- **Why it matters:** The SEL-052 held alarm never rings in a parallel project. `held_alarm_after_s` and `held_repeat_s` are loaded and validated but never act there.
- **Fix:** Call `S._held(...)` in `pass_parallel` next to `S._stuck`. Add a parallel-pass test.

- **ID:** L1-3
- **Severity:** minor
- **Location:** `seldon/commands/dispatch.py:1497-1501` and `:1566`; `seldon/commands/dispatch_worktree.py:1135-1140`
- **Evidence:** With a lane, `claim` is built from `inplace` only, so `claim is None` while a lane session runs. `GATE.maybe_run(...)` then runs the scheduled full gate. `_merge` documents "no pass runs one while a session is in flight", and `pass_parallel` requires `not running` (`:290`).
- **Why it matters:** The invariant the closure-read relies on is false in serial lane projects. The lease serialises the merge, so the damage is limited to a stale premise and a wait of up to 7,200 s.
- **Fix:** In `_pass`, gate `maybe_run`/`project_imports` on `claim is None and not lane_running`, as `pass_parallel` does.

- **ID:** L1-4
- **Severity:** minor
- **Location:** `seldon/core/lane.py:11-12` and `:86-88`; `seldon/commands/cc.py:103-112`
- **Evidence:** The docstring says "no task file can put itself in the lane; only the configured pattern does". But `is_lane` matches `t.name`, which is `_name_from_filepath`, i.e. the file's own stem.
- **Why it matters:** Any filer, including one filing from another repository, joins the lane by naming the file. That gets it priority and lets it run beside an exclusive build, against DN-006 decision 9. Only R41 limits the damage.
- **Fix:** Grant lane membership through a property only the operator or registration policy sets (for example `lane: true`, written by `cc register --lane` and refused for filings), or match the pattern against a field the file author does not control. Correct the docstring.

## Lens 2: correctness

- **ID:** L2-1
- **Severity:** major
- **Location:** `seldon/core/gate_plan.py:739-749` (and `passing_record` at `:730`)
- **Evidence:** `return passing_record(events, out.stdout.strip())` accepts any passing, clean `gate_run` of the tree, whatever its tier. `seldon gate run` (without `--full`) in the primary on clean main plans `changed=[]`. That gives tier scoped and `reason "declared_none…"`, and `run` "passes at once" (`:631-633`).
- **Why it matters:** R41 names "a scheduled run, `seldon gate main`, or a full `seldon gate run`". `_blocked_completion` itself cites R26: "a gate that ran nothing is not evidence". One `seldon gate run` that ran zero tests satisfies the guard, and `completion_gate` then records it as evidence.
- **Fix:** In `completion_evidence`, require `tier == "full"` (or `call_site == "scheduled"`). Test it with a scoped `declared_none` record.

- **ID:** L2-2
- **Severity:** major
- **Location:** `seldon/commands/dispatch.py:2721` and `:2815-2833`; `seldon/core/controls.py:164-166`
- **Evidence:** The controls are re-tried only when `if state.get("fingerprint") != fp:`. A harness error counts as a failed limit: `except (OSError, subprocess.TimeoutExpired) as exc: rows.append({**row, "refused": False, ...})`. `dispatch_controls` prints but never writes `dispatch_controls.json`.
- **Why it matters:** One planted hook call that takes longer than `HOOK_TIMEOUT_S = 30` on a loaded host (the repo records load averages of 7-8) blocks every launch until seldon.yaml changes. The refusal tells the operator to run `seldon dispatch controls`, which cannot clear it. The fingerprint also leaves out the code (`limits_spec`, `controls.py:225-228`), so a regression in `refusal()` or `stations.inspect` after an upgrade is never re-tried.
- **Fix:** Record a harness error as `refused: None` ("untried") and retry it on the next pass. Have `seldon dispatch controls` write the state file and the `limits_tried` record. Add the installed seldon version (or a hash of `controls.py` and `stations.py`) to the spec fingerprint.

- **ID:** L2-3
- **Severity:** major
- **Location:** `seldon/commands/dispatch_gate.py:48-55`; `seldon/core/gate_plan.py:189-191`
- **Evidence:** `_clear` runs `if wt.exists(): shutil.rmtree(wt)`. `scheduled_worktree` is validated only by `_relative` (no leading `/`, no `..`), so `"."`, `"tests"` and `".claude/worktrees"` all pass.
- **Why it matters:** A config typo, or a merged branch that edits `dispatch.gate.scheduled_worktree`, makes the next scheduled pass delete the primary checkout or every in-flight worktree. The docstring's "never a task's" is not enforced.
- **Fix:** At load, require the path to be strictly under `.seldon/` and different from it. In `_clear`, remove only a path `git worktree list --porcelain` names, or that holds a marker file `run_scheduled` wrote. Refuse anything else.

- **ID:** L2-4
- **Severity:** minor
- **Location:** `seldon/commands/dispatch_gate.py:161-176`
- **Evidence:** The docstring says "Never raises", but the code only has `except (ScheduledBusy, GP.GateConfigError)`. `WT.link`, `GP.run` (Popen, log I/O) and `GP.emit` can raise `OSError`.
- **Why it matters:** When the run is due, every pass reaches the same call, so one persistent `OSError` crashes every pass.
- **Fix:** Catch `OSError`, record a `gate_run`-adjacent failure event once per distinct error (as `project_imports` does), and continue.

- **ID:** L2-5
- **Severity:** minor
- **Location:** `seldon/commands/dispatch.py:246`; `seldon/commands/dispatch_worktree.py:367-373`
- **Evidence:** `D.fifo(rows)` and `D.plan_launches(..., cfg["max_parallel"], cfg["resources"])` in `status`/`survey` pass no `lane` and no `apply_lane_c6`.
- **Why it matters:** In a lane project, `seldon dispatch status` shows an order and deferrals the pass does not apply. That is a lane task "waiting" on an exclusive build it would in fact launch beside.
- **Fix:** Pass `lane` to `fifo`/`plan_launches` and call `mark_lane_rows` in both status paths.

- **ID:** L2-6
- **Severity:** note
- **Location:** `seldon/commands/dispatch_worktree.py:337`
- **Evidence:** The comment says "`plan_launches` launches an exclusive task only when nothing runs, and alone", but `core/dispatch.py:666` removes lane tasks from `running`.
- **Why it matters:** The comment states an invariant the code no longer keeps.
- **Fix:** Reword it to say exclusive tasks wait for non-lane tasks only (AD-038-R40).

- **ID:** L2-7
- **Severity:** note (pre-existing, outside the diff)
- **Location:** `seldon/commands/cc.py:2191`
- **Evidence:** pyflakes reports `undefined name 'update_artifact'`. The module imports only `plan_update_artifact` (`:16`).
- **Why it matters:** `seldon cc rederive-description` without `--dry-run` raises `NameError` after printing its plan.
- **Fix:** Import `update_artifact` from `seldon.core.artifacts`, with a test that runs the non-dry path.

## Lens 3: security and egress

- **ID:** L3-1
- **Severity:** minor
- **Location:** `seldon/core/controls.py:129-136`; `seldon/core/hive.py:10-13`
- **Evidence:** For Bash and search tools the guard is a substring test, `if any(s in value for s in _spellings(root))`. The R45 plants are a `Read` and a literal `cat <path>` (`:157`).
- **Why it matters:** `cat ~/.factory/hi""ve/secrets/x`, `cd ~/.factory && cat hive/secrets/x`, a glob, or `python -c` with a joined path all get past it. MCP tools whose path key is not in `_PATH_KEYS` are not checked at all. The plants test only the spellings the guard was written for, so "limits_tried ok" says nothing about bypass. hive.py admits this.
- **Fix:** Enforce the deny at the OS layer. Options are Claude Code's sandbox filesystem read-deny for Bash, plus `Read(//abs/path/**)` deny rules generated from the same list, or file permissions. Keep the hook as defence in depth, and add plants for one obfuscated spelling so the control tests the claim being made.

- **ID:** L3-2
- **Severity:** minor
- **Location:** `scripts/sel056/trial.sh:8`; `scripts/sel056/conformance_pair.sh:12`, `:42`
- **Evidence:** `rm -rf "$scratch" && mkdir -p "$scratch"` takes an unchecked argument. `py=/Users/brock/GitHub/squiddy/.venv/bin/python` is hardcoded, as is the same path in `sq.sh:5`.
- **Why it matters:** `trial.sh .` deletes the working tree. The scripts are tracked but run on one machine only, against CLAUDE.md §2.
- **Fix:** Refuse a scratch path that is not under `$TMPDIR`, or that already exists without the script's marker. Read the squiddy interpreter from `project_new.squiddy_command` or an env var. Alternatively, remove the one-off scripts once SEL-056's evidence is recorded.

## Lens 4: tests

- **ID:** L4-1
- **Severity:** major
- **Location:** `tests/test_sel058_hazbrief_filings.py:86-108`
- **Evidence:** `_gate_run` always writes `"tier": "full"`. No case feeds a scoped or `declared_none` passing record, and no test covers the MCP `seldon_cc_complete` path or a `blocked → in_progress → cc complete` sequence.
- **Why it matters:** L1-1 and L2-1 both pass the suite.
- **Fix:** Add three tests. A scoped passing record of main's tree must be refused. MCP `seldon_cc_complete` on a blocked task must be refused. A task moved out of `blocked` by hand must still be refused.

- **ID:** L4-2
- **Severity:** minor
- **Location:** `tests/test_sel054_identity_and_controls.py:229-246`
- **Evidence:** Recovery is tested only by monkeypatching `_session_settings`, which changes the fingerprint.
- **Why it matters:** Nothing tests a transient harness failure, or that `seldon dispatch controls` clears a refusal, so L2-2 is invisible.
- **Fix:** Plant a `TimeoutExpired` from `run` once, then assert that the next pass re-tries and launches.

- **ID:** L4-3
- **Severity:** minor
- **Location:** `tests/test_sel052_held_alarm.py`; `tests/test_sel055_scheduled_gate.py`
- **Evidence:** The held alarm is tested only through the serial pass. No test checks that a `scheduled_worktree` of `.` or `tests` is refused.
- **Why it matters:** L1-2 and L2-3 have no test that would fail.
- **Fix:** Add a parallel-pass held test, and a load-time refusal test for `scheduled_worktree` outside `.seldon/`.

## Lens 5: provenance and evidence

- **ID:** L5-1
- **Severity:** minor
- **Location:** `seldon/commands/cc.py:1037-1039`
- **Evidence:** `return {"completion_gate": found.get("event_id")}, None` records whatever L2-1 accepted.
- **Why it matters:** A completed task's `completion_gate` can name a gate that ran zero tests and still read as evidence.
- **Fix:** This is solved by the L2-1 fix. Also record the evidence's `tier` and `tests_run` next to the id.

## Lens 6: adopter readiness

- **ID:** L6-1
- **Severity:** minor
- **Location:** `README.md`; `pyproject.toml:22-26`
- **Evidence:** README has no install, quick-start or "getting started" text. The `dev` extras are `pytest` and `pytest-asyncio` only, yet the shipped `gate_command` needs `-n` (xdist). The new commands (`seldon gate main`, `seldon dispatch controls`, `seldon qc recall-audit|recall-replay`) appear only in `seldon go`.
- **Why it matters:** A fresh clone installed from `pyproject.toml` gets a red full gate on its first run (`unrecognized arguments: -n 6`).
- **Fix:** Add `pytest-xdist` and `pytest-randomly` to `dev`, and a README install section with one working command.

## Lens 7: brittleness

- **ID:** L7-1
- **Severity:** major (structural)
- **Location:** `seldon/commands/dispatch.py:1483-1640` against `seldon/commands/dispatch_worktree.py:228-350`, plus the status views at `dispatch.py:236-246` and `dispatch_worktree.py:357-375`
- **Evidence:** Every new step has to be added by hand to each pass implementation: `_held`, `maybe_run`, `project_imports`, `_launch_gates`, the lane split and lane `fifo`. This diff did it for some and missed others (L1-2, L2-5). The lane's `launch_beside` (`dispatch_lane.py:76-108`) re-implements a third.
- **Why it matters:** That is the root cause of L1-2 and L2-5. Each future station will diverge the same way.
- **Fix:** Make one pass pipeline: an ordered list of stage functions over a shared pass context (a pipes-and-filters / chain-of-responsibility pattern), with launch policy (serial, parallel, lane-beside) as the only variable. Status runs the same pipeline with writes disabled.

- **ID:** L7-2
- **Severity:** minor
- **Location:** `seldon/commands/cc.py:1196`, `seldon/core/controls.py:31`, `seldon/commands/dispatch.py:2711-2747`
- **Evidence:** R41 is enforced at one CLI entry point rather than on the transition. R45 keeps its own state file with its own re-arm rule, the seventh standing-condition file beside the lease.
- **Why it matters:** Each incident adds a gate where it was noticed rather than where the invariant lives. L1-1 is the result.
- **Fix:** Put guards in the state machine as transition guards (guard conditions on `blocked → *`). Put standing conditions in one table-driven module (key, identity, re-arm rule) instead of a file and a function pair each.

- **ID:** L7-3
- **Severity:** minor
- **Location:** `seldon/commands/dispatch.py` (11 `read_events(` call sites), `_blocked_tasks` (`dispatch.py:2018-2038`), `dispatch_gate.maybe_run`, `_merge`
- **Evidence:** `seldon_events.jsonl` is 14,812 lines (20,140,800 bytes). This diff adds at least three more full parses per pass.
- **Why it matters:** Pass time grows with the store, and every new alarm adds a full scan.
- **Fix:** Read the store once per pass and hand the list down. Longer term, maintain an incremental projection (an offset plus folded state) of the few views passes need: the last block per task, the newest scheduled run, the closure.

## Lens 8: configuration keys

- **ID:** L8-1
- **Severity:** minor
- **Location:** `seldon.yaml:229-231`
- **Evidence:** `gate_command: … python -m pytest tests/ -q -p no:cacheprovider -n 6`. The comment depends on `pytest-randomly` being installed; neither plugin is declared (see L6-1).
- **Why it matters:** The shipped value of a key depends on packages the project does not declare.
- **Fix:** Declare both in `dev`, or make the gate environment premise (`environment.packages`) check for them.

Every other key the diff adds is read by code: `internal_roots_from`, the `default_include` additions, `held_*`, `hive.*`, `project_new.prior_art_baseline` and `.projections`, `recall.selection.*` and `recall.audit.repositories_from`. In parallel projects, `held_*` is read but never acts (L1-2).

## Synthesis

**Executive summary**
1. Most of this delta adds guards; it removes almost none. The one real removal is the `--deselect`, which the test's own fixture replaces.
2. R41 (a blocked task needs gate evidence) has two holes. The MCP completion and a step out of `blocked` both skip it (L1-1), and the evidence check accepts a gate that ran nothing (L2-1).
3. R45 (limits tried by planted requests) latches. A transient harness failure stops every launch, and the remedy the refusal names cannot clear it (L2-2).
4. The scheduled gate deletes whatever `scheduled_worktree` names, with no containment check (L2-3).
5. The held alarm exists only in the serial pass (L1-2).
6. The lane is sound inside its R41 merge fence. Its membership is chosen by the filer (L1-4), its status view disagrees with the pass (L2-5), and in serial mode it voids the "no session in flight" premise of the scheduled run (L1-3).
7. The session guard is a substring denylist, and its control tests only the spellings it knows (L3-1).
8. The tests check what the authors built and miss each of these holes (L4-1 to L4-3).
9. The root structural cause is two hand-maintained pass implementations plus a third (lane-beside) (L7-1).
10. The shipped gate command needs an undeclared plugin (L8-1).

**Fix first**
1. L1-1 with L2-1: move R41 into the completion walk and require a full or scheduled gate.
2. L2-2: treat a harness error as untried, let `dispatch controls` clear the state, and put the code in the fingerprint.
3. L2-3: contain `scheduled_worktree` under `.seldon/` and only ever remove a registered worktree.

**What the suite should add**
- A scoped `declared_none` record and an MCP completion, both refused under R41.
- A transient control failure that recovers on the next pass.
- A parallel-pass held ring.
- `scheduled_worktree` of `.` refused at load.
- A lane-project `dispatch status` that matches the pass's plan.
- A serial lane pass that does not run the scheduled gate while a lane session is live.

**Verdict.** The delta mostly does what its rulings (AD-034-R38 to R41, AD-038-R40 to R45) claim on the main path, and each new mechanism is documented and tested for its intended case. The one ruling written to stop an incident of a hand-completed blocked task (R41) does not hold. Another completion entry point skips it, and it accepts a zero-test gate as evidence. The R45 control can wedge the queue on one slow hook call, with no recovery the operator is told about. These are not documentation gaps. They are cases where the code enforces less than the ruling says, and at least L1-1, L2-1, L2-2 and L2-3 should be fixed before AD-038 calls these rulings implemented. Each one is a review finding to file as an Issue in seldon's graph.
