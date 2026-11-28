# REVIEW-001: seldon code merged from e42c25bc to 078b80d0, reviewed by sessions that did not write it

**Task:** `cc_tasks/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc.md` (factory FAC-63, F-048, DN-007).
**Record:** `findings.yaml` beside this file. Each row is an Issue of type `review_finding`, `found_in` `seldon:<this file>#<id>`.
**Locations** are lines at the reviewed snapshot `078b80d07b3f9f1f0feecb94487e8f6110601161`. After REVIEW-001's own commit they move by a few lines in `cc.py`, `gate_plan.py`, `dispatch_gate.py` and `mcp_server.py`.

## What was covered

`git merge-base --is-ancestor 078b80d0 main` held. The counted change is `git diff --no-renames e42c25bc 078b80d0` over the task's
code globs, minus its exclusions: **4,227 added and deleted lines in 43 files**. That matches the task's count. It was split into two groups of at most 3,000
lines and written under `/tmp/qz_delta/`, outside the repository:

| Group | Lines | Files |
|---|---|---|
| part1 | 1,507 | `models/models.lock.yaml`, `scripts/sel056/*.sh` (5), `seldon.yaml`, `seldon/commands/{cc,decision,dispatch,dispatch_gate,dispatch_lane,dispatch_ooda,dispatch_stations,dispatch_worktree,gate,go,mcp_call,project,qc,req,verify}.py`, `seldon/mcp_server.py` (23 files) |
| part2 | 2,720 | `seldon/core/{adopt,controls,cross_project,decisions,dispatch,gate_plan,hive,hooks,issue_utils,lane,prior_art,project_new,recall,recall_audit,requirements,returns,stations,worktree}.py`, `seldon/domain/research.yaml`, `seldon/templates/graph_spec/squiddy_graph.yaml` (20 files) |

Each group went to one fresh general-purpose subagent. The prompt was the task's paragraph (this worktree only; `~/GitHub/CLAUDE.md`
and the diff; no suite; no subagents; cite `path:line`; never `cc_tasks/`, `handoffs/` or `docs/evidence/`; the governing notes `CLAUDE.md`,
AD-038 and AD-037), then factory's `scripts/review_prompt_change.md` with the group's diff path, then `scripts/review_prompt_generic.md`
verbatim. Both ran all eight lenses and finished: part1 in 62 tool calls and about 222k tokens, part2 in 60 tool calls and about 219k tokens.
Their reports are in `reviewer_part1.md` and `reviewer_part2.md` beside this file. A `sources` entry such as `part1:L2-3` names a finding in one of them.

**Verification (this session).** Each finding's live line was read at the snapshot (the anchors are listed by `git show 078b80d0:<file>`).
A finding is CONFIRMED where the claim held on reading or running it, and PLAUSIBLE where it rests on the reviewer's reading. Duplicates are merged, and each merged row names all its sources. Nothing was rejected.
The runs behind the CONFIRMED rows:

- **F-01.** `load_gate_config({"scheduled_worktree": "."}, ...)` loads. `_clear` then calls `WT.remove` (`git worktree remove --force`) and
  `shutil.rmtree` on the path. Red tests: a tracked `docs/` and an in-flight `.claude/worktrees/busy` are deleted.
- **F-02.** The MCP `seldon_cc_complete` walked a blocked task `in_progress → completed` with no gate on record. Red test output: `path:
  in_progress → completed`.
- **F-03.** A `tier: scoped` passing record of main's tree was returned as evidence, and `cc complete` completed the blocked task on it.
- **F-04.** `task update --state in_progress` followed by `cc complete` completed with no evidence.
- **F-06.** A probe ran `controls.refusal` over `guard_paths({"guard": {"deny_paths": ["/tmp/rv001_probe/vault/secrets"]}})`. A canonical `Read` and a
  canonical `cat` are refused. `cd /tmp/rv001_probe/vault && cat secrets/x`, `cat .../sec""rets/x` and a `Grep` rooted at `.../vault`
  are all ALLOWED. (The live session guard refused the first probe, which named the real secrets path. That is the guard working on the canonical spelling.)
- **F-05.** `controls.py:164` records `refused: False` on `OSError`/`TimeoutExpired`, and `dispatch.py:2721` re-tries only on a changed fingerprint.
- **F-07.** `dispatch.py:1488` returns `pass_parallel` before `_held` (`:1553`), and `_held` has no other caller.
- **F-08.** `returns.py:484-490` writes `check: test -f <own RESULT>`, and `dispatch_worktree.py:916` counts a passing Stop gate with ≥1 check.
- **F-10.** `core/dispatch.py:663-680` lets a lane candidate `continue` before any `touches_overlap`.
- **F-14, F-23, F-24, F-28, F-30, F-31.** The cited line says what the finding says (see the anchors above, and `pyproject.toml`'s `dev` extras: `pytest`,
  `pytest-asyncio` only).

**The deletion and guard accounting** that `review_prompt_change.md` asks for is in both reports' first tables. What no snapshot line guards any more:
the per-plan cadence (F-18), the lane's resource overlap (F-10), the `environment_in_flight` alarm at 3 passes (F-20), and R41 on paths other
than the CLI's state test (F-02, F-04). Every other removed guard is kept or made stricter, and each report names the line that keeps it.

**Suite.** This session ran it (see the RESULT); the reviewers did not, by the task's instruction. Reviewer part1 ran `pyflakes` on the changed
modules; that is the source of F-23.

## Dispositions

Only `data_loss`, `unbounded_spend` and `operator_authority` are fixed here, each with a test run red first, in commit `b07b559`:

- **F-01 (data_loss).** At load, `scheduled_worktree` refuses `.`. `_clear` removes a path only when the run's ownership marker
  (`<name>.scheduled` beside the checkout, written before `git worktree add`) claims it. Anything else is refused (GateConfigError, which
  `maybe_run` and `seldon gate main` report) and left in place.
- **F-02, F-03, F-04 (operator_authority, AD-034-R41).** R41 lives in one function, `cc.r41_completion`, which the CLI and the MCP tool both call. Only a
  `tier: full` record counts as evidence (the scheduled run is full). A task is held when it is `blocked` now, or when its newest move into
  `blocked` comes after its newest `dispatch_launched`, so a hand step out of `blocked` does not escape the check and a redrive the dispatcher relaunched is not held.
  The operator's `--ungated` override stays CLI-only.

Every other finding is `queued` to one of two follow-up tasks, both filed with `seldon cc file`, `After` this task:
`2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say` (F-05 to F-22) and
`2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings` (F-23 to F-33).

Two class calls carry their grounding here:

- **F-06 is `other`, not `operator_authority`.** R44 (`seldon/core/hive.py:10-12`) claims only that the guard stops "a session's ordinary
  reach, not a determined process", and it names the board's mint ledger as factory's second check. The finding is that ordinary reach
  passes too. The fix that is not a band-aid is an OS-enforced deny (the reviewers' L7-1). That is a new decision, and this task may make none. More spellings in the
  substring list would be the per-incident patching the review warns against.
- **F-27 and F-30 are `other`, not `data_loss`.** `verify --fix` records each removal as a `link_removed` event, so the graph can be rebuilt and nothing is lost.
  The sel056 scripts delete only the path the operator passes as the documented scratch argument.

## Findings

| Id | Severity | Verdict | Class | Location | Finding | Disposition |
|----|----|----|----|----|----|----|
| F-01 | major | CONFIRMED | data_loss | `seldon/commands/dispatch_gate.py:48` | The scheduled run's _clear removed whatever dispatch.gate.scheduled_worktree named (git worktree remove --force, then rmtree), and the key was checked only for a leading / and ..; `.`, a tracked directory or a task worktree was deleted | fixed; test `tests/test_review001_fixes.py::test_a_scheduled_run_does_not_delete_a_tracked_directory_its_config_names` |
| F-02 | major | CONFIRMED | operator_authority | `seldon/mcp_server.py:1506` | The MCP seldon_cc_complete completed a blocked task with neither gate evidence nor the operator's --ungated override; AD-034-R41 was checked only in the CLI command | fixed; test `tests/test_review001_fixes.py::test_the_mcp_completion_refuses_a_blocked_task_with_no_gate_on_main` |
| F-03 | major | CONFIRMED | operator_authority | `seldon/core/gate_plan.py:739` | completion_evidence accepted any passing clean gate_run of main's tree, including a scoped declared_none run that ran nothing, as R41 evidence | fixed; test `tests/test_review001_fixes.py::test_a_scoped_gate_of_the_branch_tip_is_not_completion_evidence` |
| F-04 | major | CONFIRMED | operator_authority | `seldon/commands/cc.py:1196` | R41 keyed on the state at call time, so a blocked task stepped to in_progress by `seldon task update` before `cc complete` completed with no evidence and no override | fixed; test `tests/test_review001_fixes.py::test_a_blocked_task_moved_out_of_blocked_by_hand_is_still_held_to_r41` |
| F-05 | major | CONFIRMED | other | `seldon/core/controls.py:164` | A harness error in a planted control is recorded as a limit that did not refuse, controls re-run only on a changed fingerprint, `seldon dispatch controls` writes no state, and the fingerprint omits the enforcing code: one slow hook call refuses every launch until seldon.yaml changes | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-06 | major | CONFIRMED | other | `seldon/core/controls.py:112` | The session guard is a substring test; a cd plus relative path, a quote-split spelling and a Grep of the parent directory all pass it (probe in review.md), against R44's 'ordinary reach' | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-07 | major | CONFIRMED | other | `seldon/commands/dispatch.py:1488` | The held alarm (_held) runs only in the serial pass; pass_parallel returns before it, so held_alarm_after_s never acts in a parallel project | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-08 | major | CONFIRMED | other | `seldon/core/returns.py:484` | Every return carries `check: test -f <its own RESULT>`, which the finish already requires, and gate_evidence counts a Stop gate with one passing check as merge evidence (R26) | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-09 | minor | PLAUSIBLE | other | `seldon/core/lane.py:86` | Lane membership matches the task file's own name, so any filer joins the coordination lane by naming the file | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-10 | minor | CONFIRMED | other | `seldon/core/dispatch.py:663` | plan_launches skips the resource-overlap check for lane candidates and drops running lane rows from what is held; R40 exempts lane tasks from exclusive holds only | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-11 | minor | PLAUSIBLE | other | `seldon/commands/dispatch.py:1497` | In a serial lane project a running lane session is not the claim, so the scheduled full gate can run while it is in flight | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-12 | minor | PLAUSIBLE | other | `seldon/commands/dispatch_gate.py:174` | maybe_run says it never raises but catches only ScheduledBusy and GateConfigError; an OSError crashes each pass | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-13 | minor | PLAUSIBLE | other | `seldon/commands/dispatch.py:246` | dispatch status and survey plan without the lane, so they show an order the pass does not apply | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-14 | note | CONFIRMED | other | `seldon/commands/dispatch_worktree.py:337` | A comment says an exclusive task launches only when nothing runs; the lane removed that invariant | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-15 | major | PLAUSIBLE | other | `seldon/commands/dispatch.py:1483` | Two hand-maintained pass implementations plus the lane's launch: each new station is added to some and missed in others (the root of F-07 and F-13) | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-16 | minor | PLAUSIBLE | other | `seldon/commands/cc.py:1196` | R41 is enforced at completion entry points, not as a guard on the blocked transitions; R45 keeps its own standing-condition file | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-17 | minor | PLAUSIBLE | other | `seldon/commands/dispatch.py:2018` | The event store (about 20 MB) is parsed in full several times per pass, and the diff adds more scans | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-18 | minor | PLAUSIBLE | other | `seldon/core/gate_plan.py:543` | Since SEL-055 only a dispatcher pass runs the full suite; with no pass nothing reports the newest full gate's age | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-19 | minor | PLAUSIBLE | other | `seldon/core/gate_plan.py:341` | A declared gate_record is admitted under the closure and clears a red main even when scoped by tree_paths | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-20 | note | PLAUSIBLE | other | `seldon/core/dispatch.py:761` | The environment_in_flight alarm went from 3 passes to 12 for consumers that do not name it, with no measured basis | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-21 | minor | PLAUSIBLE | other | `seldon/core/gate_plan.py:739` | R41's evidence is a full gate of main's tree; nothing checks that the blocked task's branch reached main | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-22 | minor | PLAUSIBLE | other | `seldon/core/hive.py:101` | A failed mint's stderr tail is written into the session_identity event, which is committed and pushed | queued: 2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say |
| F-23 | minor | CONFIRMED | other | `seldon/commands/cc.py:2191` | Pre-existing: cc rederive-description calls update_artifact, which cc.py never imports (NameError past --dry-run) | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
| F-24 | minor | CONFIRMED | other | `seldon/core/recall.py:855` | Recall stage 4 reads the Issue threshold for dead ends instead of the dead end's own kind, which seldon.yaml sets to null | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
| F-25 | minor | PLAUSIBLE | other | `seldon/core/recall_audit.py:552` | recall_audit dates a RESULT's landing by file mtime, which a clone or rebase resets | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
| F-26 | minor | PLAUSIBLE | other | `seldon/core/recall_audit.py:556` | recall_audit's checkpoint key omits the recall block, so a changed block resumes stale rows (section 15.2) | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
| F-27 | minor | PLAUSIBLE | other | `seldon/core/decisions.py:1880` | verify --fix ends constrained_by edges from completed tasks and reads projected state without pending acceptances; removals are recorded as link_removed, so nothing is lost | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
| F-28 | major | CONFIRMED | other | `seldon/core/prior_art.py:385` | prior_art.internal_roots_from names ../factory/seldon.yaml and raises when no sibling factory checkout exists, on the commit hook, verify and cc register paths | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
| F-29 | minor | PLAUSIBLE | other | `seldon.yaml:414` | dispatch.hive.mint_command names one machine's interpreter and checkout | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
| F-30 | minor | CONFIRMED | other | `scripts/sel056/trial.sh:8` | The sel056 scripts rm -rf an unchecked argument and hardcode one machine's squiddy interpreter | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
| F-31 | minor | CONFIRMED | other | `pyproject.toml:23` | The shipped gate_command needs pytest-xdist (-n 6) and relies on pytest-randomly; neither is in the dev extras, and the README has no install section | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
| F-32 | note | PLAUSIBLE | other | `seldon/core/hooks.py:353` | The hooks-path repair rests on the Claude Code CLI's rewrite of core.hooksPath | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
| F-33 | note | PLAUSIBLE | other | `tests/test_pa002_release_resolve.py:361` | The pa002 test that left the --deselect list still skips through importorskip(squiddy.index), so a gate without squiddy passes it unrun | queued: 2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings |
