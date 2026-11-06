# RESULT: SEL-025 (task 915acf48): the dispatcher cannot dirty its own tree: the rotated log is ignored, and an untracked filing is committed by the pass

**Date:** 2026-11-06. **Branch:** `worktree-linked-rolling-parasol` (the dispatcher merges it).
**Rulings:** AD-038-R22 and R23 (`docs/design/AD-038_ADDENDUM_09_the_dispatcher_cannot_dirty_its_own_tree.md`).
Their records are in `docs/decisions/register/pending/` (00001, 00002), numbered on main by the merge step.
**Tests:** `tests/test_sel025_dispatcher_cannot_dirty_its_own_tree.py` (10). Suite: §4.
**Commit:** `87653df`. **Addenda:** none existed.

Recall used: none

## 1. What was measured before building

- The pass's sweep is no longer `_commit_registered` (the third premise names it only in `_reconcile`'s docstring):
  since FRICTION-001 it is `seldon.core.reconcile`, a class table keyed on path and change. Part B is a new class
  there, `filing`, not an extension of a per-writer sweep.
- `D.header_hits(text, "Status")` reads FAC-03's header as `proposed (consumer filing; ...)`, and `D.kind_of_text`
  reads it as `task` (it has no `**Kind:**`). So both rules in the task are needed: Kind for SEL-023-era filings,
  Status for the older form.
- Over seldon's current `cc_tasks/`, the new `filing_path` finds four files: FAC-03, the two squiddy filings with
  `**Kind:** filing`, and one addendum to one of them. Three other squiddy filings (2026-11-04 and two of 2026-11-06)
  say "Consumer filing" only in the title, so the class would not commit them (§5).

## 2. What landed, by Part

**A (AD-038-R22).** `scripts/jobs/seldon_dispatch.sh` rotates to `logs/dispatch/<base>.<UTC stamp>.log` (the `.log`
suffix last, logrotate's `extension` convention). Retention deletes only `<base>.*.log` in `logs/dispatch/` at depth
1, so the dispatched sessions' own logs there are untouched, plus the old `<log>.*` name in `logs/` until those age
out. `.gitignore` gains `logs/**` with its reason. `SELDON_DISPATCH_BIN` lets a test run the wrapper without a pass,
the same seam `SELDON_DISPATCH_LOG` already gave the log; launchd sets neither.

**B (AD-038-R23).** `seldon/core/reconcile.py`: class `filing` (ordered after `task_files`) admits an UNTRACKED file
directly under `cc_tasks/`, `.md`, whose header block has `**Kind:** filing` or a `**Status:**` matching
`consumer filing`. It also admits an untracked addendum whose base file is a filing. Each filing is its own
path-limited commit through the hooks: `dispatcher: filing: <basename>`. A new base and its new addenda share the
base's commit. `seldon/commands/dispatch.py` `_reconcile` prints
`filing_committed: <path> -> <commit> (<subject>)`. A tracked filing edited, a nested file, a file outside
`cc_tasks/`, or a cc_tasks file that only mentions a consumer filing in its body all stay unreconciled. c7 refuses on
them and names them, as before.

## 3. Tests (each failed before the fix: 7 red, 3 green guards, then 10 green)

| test | what it holds |
|---|---|
| `test_the_wrapper_rotates_to_a_dot_log_name_under_logs_dispatch_and_it_is_ignored` | real wrapper run: the rotated file is `logs/dispatch/seldon_dispatch.<stamp>.log`, `git check-ignore` ignores it, porcelain empty |
| `test_retention_deletes_an_old_rotation_and_keeps_a_young_one_and_the_session_logs` | 40-day-old new-name and old-name rotations go; a young one and a session log stay |
| `test_this_repositorys_gitignore_ignores_every_log_path` (3) | seldon's `.gitignore` ignores the new name, the 2026-11-04 name, and any `logs/` path |
| `test_a_filing_by_kind_or_by_status_is_its_own_class_and_scratch_is_not` | Kind, Status and addendum admitted; scratch, nested and out-of-dir not |
| `test_a_tracked_filing_edited_is_not_a_filing_commit` | only an untracked filing is the class |
| `test_each_filing_is_its_own_path_limited_commit_with_the_dispatcher_subject` | one commit per filing, one path each, exact subject |
| `test_an_untracked_filing_is_committed_by_the_pass_and_the_next_candidate_launches` | Neo4j: `filing_committed:` printed, the candidate launches, no `dirty_tree` |
| `test_an_untracked_scratch_file_still_refuses_and_is_named` | Neo4j: `dirty_tree`, `unreconciled: cc_tasks/scratch.md: ...`, HEAD unchanged |

## 4. Suite

`python -m dotenv -f .env run -- python -m pytest tests/ -q -n 6`: **3241 passed, 2 failed, 7 skipped** in 24:43.

- `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`: the known library
  drift, failing on main.
- `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing`:
  under `-n 6` the filing landed after the gate ended (`gate_running_at_end: False`). Run alone it passes (55 s).
  It is a wall-clock race between a sleeping gate and a filer, and it does not reach the reconciler's classes. It is
  load-sensitive, not a regression.

## 5. Open, not done here

1. **Filings marked only by their title.** Three squiddy filings in seldon (`2026-11-04_consumer_filing_from_squiddy_a_merged_worktrees...`,
   `2026-11-06_consumer_filing_from_squiddy_twelve_docs_evidence...`, `2026-11-06_consumer_filing_from_squiddy_two_merges_blocked...`)
   carry neither `**Kind:** filing` nor a Status naming one. Left untracked, they would still refuse c7. They are
   tracked now. R23 keeps to the header block, as the task specifies and as AD-038-R14 reads every header. The cure
   is at the filer: `seldon cc file` / `seldon_cc_file` with `**Kind:** filing` (SEL-023), which also commits.
2. **The pass commits; it does not register.** A committed filing is tracked, which is what registration needs.
   Registering it (and retagging a Status-only filing with `seldon task update --kind filing`) is left to whoever
   answers it, per SEL-023 A.
3. **Other projects running this wrapper** get the new rotation name. Those whose `.gitignore` has `*.log` now
   ignore it. Any other project needs its own ignore line (ADDENDUM 09 §4.5).
4. **The live stray** `logs/seldon_dispatch.log.20261104T021957Z`, if it still exists in the primary, is ignored by
   `logs/**` once this merges. The second `find` deletes it after 30 days.

## 6. Parts

`seldon dispatch part-complete --part A` and `--part B` were recorded from this worktree. No stop was written.
