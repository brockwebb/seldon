# REVIEW-001: review 4227 changed lines of seldon's code merged since e42c25bc, by a session that did not write it

**Status:** proposed
**Author:** scripts/coordinator_tick.py (FAC-63; F-048; factory DN-007), 2026-11-28T04:27:41Z, because FAC-63 Part B item 3: its code merged since 2026-11-26 (4227 changed lines). Generated from factory's templates/review_task.md; no model wrote this file.
**Repo:** seldon. L4: commit on the task branch; the dispatcher merges.
**After:** none
**Governing:** factory's design note (`/Users/brock/GitHub/factory/docs/design/2026-11-27_DN-007_new_code_is_reviewed_by_a_session_that_did_not_write_it.md`) and F-048: merged code is reviewed by a session that did not write it, with the harness FAC-63 measured (20 of 20 planted defects found when the reviewer is given the diff); a finding is an Issue (F-010); only what can lose data, spend without bound or take the operator's authority is fixed here, each with a red test first. No new decision.
**Model:** primary
**Spend:** est. 950k tokens. Basis: 2 harness pass(es) of at most 3000 counted lines (one pass measured at about 230k tokens, FAC-63 Part A), the findings record, and test-first fixes of the three classes only.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.5, B 0.5.
**Premises:**
- premise: seldon's seldon sessions grant for this allowance week is not spent (FAC-30, F-045) | check: /opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/cost_manager.py status --project seldon --unit seldon_sessions --stop-only | at: launch
- premise: factory's review harness and findings checker are in its primary checkout | check: test -f /Users/brock/GitHub/factory/scripts/review_findings.py | at: launch

## What is reviewed

`main` from `e42c25bc82b56cd15740f8c2875860841f29bc66` (exclusive) to `078b80d07b3f9f1f0feecb94487e8f6110601161`: 4227 added and deleted lines in 43 files, 24
commits, the oldest at 2026-11-26T03:24:27Z. Counted as code: `**/*.py`, `**/*.sh`, `**/*.yaml`, `**/*.yml`, `**/*.toml`, `**/*.js`, `**/*.ts`, `**/*.sql`, `**/*.plist`. Not counted: `tests/**`, `test/**`, `**/tests/**`, `docs/**`, `cc_tasks/**`, `handoffs/**`, `for_operator/**`, `reviews/**`, `experiments/**`, `corpus/**`, `graphs/**`, `site/**`, `view/**`, `register/**`, `**/register/**`, `seldon_events.jsonl`, `**/*.jsonl`, `**/*.md`, `**/*.lock`, `**/uv.lock`, `**/__pycache__/**`, `**/*.csv`, `**/*.parquet`. The governing notes
the reviewer is given:
  - `CLAUDE.md`
  - `docs/design/AD-038_the_machine_reconciles_its_own_state.md`
  - `docs/design/AD-037_in_process_quality_control_for_dispatched_sessions.md`

Before anything else, confirm `078b80d07b3f9f1f0feecb94487e8f6110601161` is an ancestor of `main` in this checkout (`git merge-base --is-ancestor
078b80d07b3f9f1f0feecb94487e8f6110601161 main`). If it is not, stop and say so in the RESULT.

## Part A: the harness on the diff, by a session that did not write it

1. Write the change outside the repository, so the reviewer reads it only as given: `git diff --no-renames e42c25bc82b56cd15740f8c2875860841f29bc66
   078b80d07b3f9f1f0feecb94487e8f6110601161 -- <the counted files>` into a new directory under `/tmp` whose name says nothing about review or seeding.
   With more than 3000 counted lines, split the files into 2 groups of at most that many lines
   each, one diff per group.
2. For each group, run one fresh general-purpose subagent (the Agent tool; it is metered under this task and starts
   with no context). Its prompt is, in this order:
   - one paragraph: the directory under review is this worktree; read nothing outside it except `~/GitHub/CLAUDE.md`
     and the diff's path; do not run the suite (this session runs it); no subagents, run the lenses in turn; cite
     every finding as `path:line`; do not read `cc_tasks/`, `handoffs/` or `docs/evidence/` (the authors' own account);
   - `/Users/brock/GitHub/factory/scripts/review_prompt_change.md` with `<DIFF PATH>` replaced by the group's diff path;
   - `/Users/brock/GitHub/factory/scripts/review_prompt_generic.md`, verbatim.
   Name the governing notes above in the first paragraph. Wait for every subagent; a run that ends with one in flight
   produced nothing.
3. Read the live line behind every finding. CONFIRMED where the claim holds on reading or running it; PLAUSIBLE where
   it rests on the reviewer's reading; a finding shown wrong is declined `rejected` with the evidence. Merge duplicates,
   naming every source.
4. Write `docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/review.md` (the findings table and what was covered) and `docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/findings.yaml`:
   ```yaml
   review: {repo: seldon, task: <this task's file stem>, review_file: docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/review.md}
   findings:
     - {id: F-01, severity: blocker|major|minor|note, verdict: CONFIRMED|PLAUSIBLE, location: "path:line",
        summary: "...", sources: [...], class: data_loss|unbounded_spend|operator_authority|other,
        disposition: fixed|queued|rejected|duplicate|wont_fix, task: <fixing task's file stem>,
        test: "tests/<file>.py::<test>", evidence: "why not fixed, and where that is recorded"}
   ```
5. Make each finding an Issue: `/opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/review_findings.py issues --record docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/findings.yaml` (one
   `seldon issue create --type review_finding --found-in seldon:docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/review.md#<id>` per finding, checkpointed; a
   rerun skips what is done). Then `seldon dispatch part-complete --part A`.

Acceptance:
- `check: test -f docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/findings.yaml` passes.

## Part B: fix only what can lose data, spend without bound or take the operator's authority

1. For each finding of class `data_loss`, `unbounded_spend` or `operator_authority`: write the test that fails on
   this code first and run it red; then fix it; then run it green. Its disposition is `fixed`, its task this one, its
   test that node.
2. Every other finding is `queued` to at most two follow-up tasks filed with `seldon cc file` (each with
   `**After:** REVIEW-001` and `**Found in:**` its finding), or declined (`rejected`, `duplicate` or `wont_fix`) with
   its evidence. No third task: group findings, or decline them with reasons.
3. Re-run `/Users/brock/GitHub/factory/scripts/review_findings.py issues --record docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/findings.yaml` so each Issue carries its disposition, then run the suite.
4. Write `cc_tasks/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc_RESULT.md`. Its first line: how many findings, by severity; how many fixed, queued, declined.
   Then the coverage, each fix with its test, the follow-up tasks, and what `/Users/brock/GitHub/factory/scripts/review_findings.py orphans --record
   docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/findings.yaml` lists (the fixed findings clear when this task completes; the queued ones when their tasks do). Then
   `seldon dispatch part-complete --part B`.

**This task may not:** change code outside the three classes, file more than two tasks, send anything off this
machine, or touch another repository (a defect another repository owns is a follow-up filed there, counted in the two).

Acceptance:
- `check: /opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/review_findings.py check --record docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/findings.yaml` passes.
- `check: test -f cc_tasks/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc_RESULT.md` passes.
