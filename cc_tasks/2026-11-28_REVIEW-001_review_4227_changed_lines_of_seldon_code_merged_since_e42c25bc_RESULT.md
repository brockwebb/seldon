33 findings (0 blocker, 10 major, 19 minor, 4 note): 4 fixed, 29 queued (to 2 follow-up tasks), 0 declined.

# RESULT: REVIEW-001, a review of seldon's code merged from e42c25bc to 078b80d0 by sessions that did not write it

Recall used: none. None of the eight hits changed the approach: the task fixed the method, and its harness is factory's.

## Coverage

- `git merge-base --is-ancestor 078b80d0 main` held.
- `git diff --no-renames e42c25bc 078b80d0` over the task's counted globs and exclusions came to 4,227 changed lines in 43 files, the task's own count.
- The diff was split into two groups, part1 (commands, `mcp_server.py`, `scripts/sel056`, `seldon.yaml`, `models.lock.yaml`: 1,507 lines, 23 files) and part2 (`seldon/core`, the domain and template YAML: 2,720 lines, 20 files). Both were written under `/tmp/qz_delta/`.
- Each group went to one fresh general-purpose subagent with the task's prompt: the paragraph, then `review_prompt_change.md` with the diff path, then `review_prompt_generic.md` verbatim. Both finished all eight lenses, at about 222k and 219k tokens.
- Their reports are kept verbatim in `docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/reviewer_part{1,2}.md`. They ran 22 and 24 findings, merged to 33.
- Every finding's line was read at the snapshot. 15 are CONFIRMED by reading or running (red tests, and a probe of the session guard); 18 are PLAUSIBLE. None was rejected.
- Coverage, the guard-deletion accounting and the class grounding are in `review.md`, and the record is in `findings.yaml`. `review_findings.py check` passes: 33 findings, 4 fixed, 29 queued, OK.

## Fixes, each with its test, red first (commit b07b559)

| Finding | Class | Fix | Test (`tests/test_review001_fixes.py::`) |
|---|---|---|---|
| F-01 | data_loss | `scheduled_worktree: .` is refused at load. `dispatch_gate._clear` removes a path only when the run's ownership marker (`<name>.scheduled`, written before `git worktree add`) claims it. Otherwise it refuses and leaves the path in place. | `test_a_scheduled_run_does_not_delete_a_tracked_directory_its_config_names`; also `…_does_not_remove_a_task_worktree_its_config_names`, `…_names_the_checkout_itself_is_refused_at_load`, `test_a_checkout_a_killed_scheduled_run_left_is_cleared_by_the_next_run` |
| F-02 | operator_authority | The MCP `seldon_cc_complete` now runs R41 through the same function as the CLI, `cc.r41_completion`. `--ungated` stays CLI-only. | `test_the_mcp_completion_refuses_a_blocked_task_with_no_gate_on_main` |
| F-03 | operator_authority | `gate_plan.completion_evidence` counts only `tier: full` records. | `test_a_scoped_gate_of_the_branch_tip_is_not_completion_evidence`; also `test_cc_complete_refuses_a_blocked_task_whose_only_gate_of_main_is_scoped` |
| F-04 | operator_authority | A task is held to R41 when its newest move into `blocked` comes after its newest `dispatch_launched`, so stepping out of `blocked` by hand does not escape it. A relaunched redrive is not held (control test). | `test_a_blocked_task_moved_out_of_blocked_by_hand_is_still_held_to_r41`; control `test_a_blocked_task_the_dispatcher_launched_again_is_not_held_to_r41` |

Red run before the fix: 10 failed and 1 passed (the `a/..` case, which `..` already refused). Every failure was the defect itself: DID NOT RAISE, the directory deleted, a scoped record accepted, the MCP walk `in_progress → completed`.

Green after the fix:
- The new file and the neighbouring suites: `test_sel058_hazbrief_filings.py`, `test_sel055_scheduled_gate.py`, `test_mcp_tools.py`, `test_mcp_cc_git_guard.py`. 66 passed.

## Follow-up tasks (2, both `After` this task, each with `**Found in:**` its first finding)

- `cc_tasks/2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say.md` (task 67146282) covers F-05 to F-22:
  - the planted controls latch on a harness error;
  - the session guard is bypassable (F-06, probe in `review.md`);
  - the held alarm is missing from the parallel pass;
  - a return's tautological check counts as merge evidence;
  - the lane;
  - the two pass implementations;
  - closure and evidence details.
- `cc_tasks/2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings.md` (task 481d2c09) covers F-23 to F-33:
  - a pre-existing undefined `update_artifact`;
  - recall's stage-4 threshold and the audit's mtime and checkpoint key;
  - the binding prune;
  - `internal_roots_from` requiring a sibling factory checkout;
  - machine paths;
  - undeclared xdist and randomly;
  - the hooks path;
  - the pa002 skip.

Class calls made on the grounding, not escalated:
- F-06 is `other`. R44 claims only "ordinary reach" and names factory's mint ledger as the second check. The non-band-aid fix is an OS-enforced deny, which is a new decision this task may not make.
- F-27 and F-30 are `other`. The prune's removals are recorded as `link_removed`, and the scripts delete only the operator's own scratch argument.

## Issues and orphans

`review_findings.py issues` created 33 `review_finding` Issues, with 0 failed. The checkpoint is `issues.jsonl` beside the record. Each fixed Issue carries `remediated_by` this task and `verified_by` its test. Each queued Issue carries `remediated_by` its follow-up.

`review_findings.py orphans` lists **33 of 33**:
- F-01 to F-04: "fix task not completed (in_progress)". They clear when the dispatcher completes this task on merge.
- F-05 to F-33: "fix task not completed (proposed); no VERIFIED_BY test". They clear when SEL-062 and SEL-063 complete with their tests.

## Suite

The project's gate command, `pytest tests/ -q -p no:cacheprovider -n 6` under dotenv with `PYTHONPATH=.`, ran on this branch at dc5d628. Result: **1 failed, 3,733 passed, 8 skipped in 2,234 s**.

The one failure is `tests/test_dispatch_parallel.py::test_union_merge_of_two_event_appends_is_valid`. It is merge-blocked `main_kept_moving` under load, which SEL-049 recorded as this test's load behaviour. Rerun alone on this branch it passes (1 passed in 40.6 s). It exercises the parallel merge retry, and nothing this task changed is on that path.

## Departures from the letter

- The fixes and the follow-up filings were done before the Issues were created, so each Issue was created once with its final disposition. The checker's key hashes the whole row, so creating a row as `queued` and then re-creating it as `fixed` would make two Issues for one finding. The Part B re-run of `issues` therefore had nothing to do ("already done").
- Spend: the Part A boundary recorded 1.06M tokens against the 950k estimate. The two reviewers took about 441k of that. The estimate did not count the subagents' reading of the snapshot beyond the diff.
