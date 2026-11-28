# RESULT: SEL-063, recall's selection and audit, configuration that names one machine, and the smaller review findings

**Task:** `cc_tasks/2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings.md`
(`481d2c09`). **Branch:** `worktree-humble-zooming-owl`. Not merged or completed here; the dispatcher merges on green
and completes.
**Addenda:** none existed (`*SEL-063*ADDENDUM*.md` matched nothing).
**Findings:** REVIEW-001 F-23 to F-33, 11 Issues. All 11 are `fixed`, each with `REMEDIATED_BY` this task and its
tests as `VERIFIED_BY`. F-27, F-28 and F-32 also carry `CHANGES` to the ruling each amended.
**Decisions:**
- AD-033 ADDENDUM 04 amends AD-033-R16 (F-27).
- AD-036 ADDENDUM 17 amends AD-036-R31 (F-32) and AD-036-R32 (F-28).
- These are three pending register records. `seldon decision check`: clean.
- `seldon prior-art verify` passed on both addenda before any code commit (ledger events `be82c56d`, `1f023e71`).

**Commits:**
- `227ec1e`: the red tests. Re-run at `227ec1e` in a scratch clone:
  - 9 of Part A's 10 failed. The one that passed is the control that a dead-end kind with a threshold still gets
    through.
  - 16 of Part B's 17 failed. The one that passed is the control that a malformed portfolio reference is still
    refused.
- `50e87b1`: the notes and records.
- `2053a6d`: Part A.
- `ee54d4a`: Part B.
- `91d3869`: the Issue trace.

Recall used: none. I read the task file, REVIEW-001's `review.md`, `findings.yaml` and both reviewer parts, and the
code at `1c8d372`. Of the hits, AD-033-R16 is the ruling F-27 amends, and I read it because the task names it, not
because recall listed it. The SEL-060 RESULT and the RECALL-001 RESULT were not opened. Neither were the
AD-020/AD-025 lexical hits.

## Part A: recall and the graph (F-23 to F-27)

Tests are in `tests/test_sel063_part_a.py`.

| Finding | Fix | Tests |
|---|---|---|
| F-23 | `seldon/commands/cc.py` imports `update_artifact`. | `test_part_a_rederive_description_writes_past_the_dry_run` runs the non-dry path against Neo4j. It failed with `NameError` at the base. |
| F-24 | Stage 4 reads `lexical_min_shared_terms.get(c.kind)`. A dead end whose kind is `null` is taken only when it shares a file. | `..._a_dead_end_is_held_to_its_own_kinds_threshold_not_the_issues`. Control: `..._a_dead_end_kind_with_a_threshold_still_gets_through_on_shared_words`. |
| F-25 | `recall_audit.landed_times`: one `git log --no-renames --diff-filter=A --format=%ct --name-only` per repository. Each RESULT gets the committer time of the commit that first added it. An uncommitted file keeps its mtime, a missing one 0.0, and a tree that is not a git repository uses mtimes. Committer time is used because the dispatcher rebases just before it merges, so it marks when the commit reached main. | `..._committed_before_the_launch_is_found_whatever_its_mtime`, `..._committed_after_the_launch_is_not_found_whatever_its_mtime`, `..._landing_times_come_from_the_first_commit_that_added_each_file` |
| F-26 | The checkpoint digest hashes `{recall: recall_block, selection: new_selection}`, following constitution §15.2. | `..._a_changed_recall_block_does_not_resume_the_old_rows`. An unchanged run resumes; a changed `top_n` recomputes every unit. |
| F-27 | AD-033-R16 amended, so a finished task keeps its edge as history. `non_binding_decision_edges` and the prune take the domain config and keep only edges whose source is in an open state of its type (`artifacts.open_states`). They also drop edges to a record that a pending record accepts (`decisions.pending_acceptances`: status with pending records folded in, against without). `verify` and `verify --fix` pass both. | `..._a_pending_acceptance_is_read_from_the_register`, `..._a_project_with_no_register_has_no_pending_acceptance`, `..._verify_fix_ends_only_open_tasks_edges_and_keeps_a_pending_acceptance` |

**F-27, the decision the task asked for.** Terminal tasks keep the edge as history. The grounding is in ADDENDUM 04 §2:
- In bitemporal data, ending a fact's interval is not deleting the fact.
- PROV-O records what influenced an activity that has ended.

"Finished" means not in an open state. `completed` counts as finished, because `open_states` excludes it (its only
successor, `verified`, is terminal). A source type with no state machine is held to R4 alone, as before.

Other tests changed:
- `tests/test_sel060_recall_audit.py`: `_replay_repo` now dates its commit. The landed-after-launch test now commits
  the RESULT after the launch instead of touching its mtime. Its intent is unchanged; the input that decides it is the
  commit now.
- `tests/test_sel058_hazbrief_filings.py`: passes `domain_config` to the new signatures. Its task is `proposed`, which
  is open, so its edge is still ended.

## Part B: configuration and adopters (F-28 to F-33)

Tests are in `tests/test_sel063_part_b.py`.

| Finding | Fix | Tests |
|---|---|---|
| F-28 | AD-036-R32 amended. If the `internal_roots_from` file is missing on this machine, `portfolio_roots` adds no roots and records a note in `Settings.notes`. `run_search` returns it as `notes`, logs it on the query line, and prints it to stderr. A malformed reference, or a key the file lacks, is still refused. `tests/test_sel052_prior_art_reach.py` drops its missing-file refusal case. | `..._a_missing_portfolio_file_is_a_noted_degraded_search_not_a_settings_error`, `..._a_degraded_search_says_so_in_its_output`. Control: `..._a_malformed_portfolio_reference_is_still_refused`. |
| F-29 | `hive.resolve_command` handles each command word: `{python}` becomes `sys.executable`, a leading `~` is expanded, and a relative path-shaped word is resolved against the primary checkout (`WT.anchor`), the `kit_relative` rule. `load_dispatch_config` applies it. `seldon.yaml` now reads `"{python} ../factory/scripts/hive.py mint"` and `... notices --hook`. | `..._a_hive_command_resolves_the_interpreter_and_kit_relative_paths`, `..._seldons_hive_block_names_no_machines_paths` |
| F-30 | Hardened rather than removed, because the SEL-056 RESULT cites the scripts as the source of its numbers. `scripts/sel056/lib.sh` has two functions. `sel056_fresh_scratch` accepts only a path strictly under `/tmp` or `$TMPDIR`, and only if it is absent or holds the `.sel056_scratch` marker. `sel056_squiddy_root` returns `$SQUIDDY_ROOT`, else `../squiddy` beside the primary checkout. `trial.sh` and `conformance_pair.sh` use the first; `sq.sh`, `conformance_pair.sh` and `promote_trial.sh` use the second. | `..._no_sel056_script_names_one_machines_path`, `..._trial_refuses_a_scratch_directory_it_did_not_make`, `..._a_scratch_directory_outside_the_temporary_directories_is_refused`, `..._a_scratch_directory_is_made_marked_and_remade`, `..._the_squiddy_wrapper_finds_the_kit_beside_the_primary_checkout` |
| F-31 | `pyproject.toml` `dev` gains `pytest-xdist>=3.0` and `pytest-randomly>=3.12`. The README gains an `## Install` section: `pip install -e ".[dev]"`, the `.env` keys, and the dotenv suite command. | `..._the_gate_commands_plugins_are_declared_in_the_dev_extras`, `..._the_readme_has_an_install_section_with_one_working_command` |
| F-32 | AD-036-R31 amended. `hooks.status` judges installation only by this checkout's own `config.worktree` (extension on and `.githooks`). A shared value other than `shared_hooks_path` becomes an entry in the new `advisories` list. `shared_hooks_path` is also returned. Install is unchanged, and `tests/test_sel052_hook_path.py` stays the tripwire. | `..._whatever_the_shared_value_a_pointed_checkout_reads_installed`, `..._the_installed_shared_value_gives_no_advisory`, `..._a_checkout_nobody_pointed_is_not_installed` |
| F-33 | `tests/squiddy_premise.require` fails when squiddy is missing. It skips only under `SELDON_TESTS_ALLOW_NO_SQUIDDY=1`, the form `neo4j_available` uses. The pa002 rebuild test calls it. | `..._the_pa002_rebuild_test_fails_rather_than_skips_without_squiddy`, `..._no_longer_skips_through_importorskip` |

**F-28, what was not changed.** `recall.audit.repositories_from` still refuses when the file is missing (ADDENDUM 17
§4). `seldon qc recall-audit` is an operator's measurement across the portfolio. It is on no commit, verify or
registration path, and without the list it could not state its n.

**F-29, what is outside seldon.** `secrets_dir: ~/.factory/hive/secrets` stays as written. `~` is per user, not per
machine.

**F-30, a measurement.** At the base, `trial.sh <an existing directory>` deleted the directory and ran the whole
rehearsal in its place. The red run of the refusal test did that inside pytest's `tmp_path`.

## Suite

The project's gate command, `pytest tests/ -q -p no:cacheprovider -n 6` under dotenv with `PYTHONPATH=.`, ran on
this branch at `ee54d4a` (Part B's commit; the Issue trace after it touched only the event store). Result:
**3,815 passed, 8 skipped in 2,474 s, exit 0**.

Earlier, the related suites ran at each Part's commit:
- Part A: `test_sel060_*`, `test_sel058_*`, `test_recall001_*` (68 passed), and every test of the Decision
  register check (59 passed).
- Part B: hooks, prior art, the Hive and pa002 (201 passed, 1 skipped, the live pa002 run behind
  `SELDON_PA002_LIVE`).

## Spend

- Part A's boundary: 271,211 tokens against a 0.5 share of the 800K estimate (400K).
- Part B's boundary: 313,561 tokens cumulative (wall 4,546 s) against the 800K estimate. The estimate was about 2.5
  times what the work took.
- The final figure is the dispatcher's.

## Open, for the operator or a later task

- **A pending acceptance read in `verify`'s report** covers only this checkout's own registers and imports
  (`scope_repos`). Neither the finding nor the ruling covers another repository's pending records.
- **`seldon verify` does not print hook advisories.** They are in `seldon hooks status` JSON only. Printing them is a
  choice for whoever next touches the Commit hook check.
