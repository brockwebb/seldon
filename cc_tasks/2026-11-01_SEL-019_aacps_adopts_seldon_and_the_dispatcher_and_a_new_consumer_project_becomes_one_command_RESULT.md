# RESULT: SEL-019, a new consumer project is one command (`seldon project new`)

**Task:** `905de0b4`, `cc_tasks/2026-11-01_SEL-019_aacps_adopts_seldon_and_the_dispatcher_and_a_new_consumer_project_becomes_one_command.md`.
No addenda existed at launch.
**Date:** 2026-11-01. **Branch:** `worktree-optimized-skipping-codd`.
**Outcome:** Parts A and B are done. The stop condition did not fire: `seldon dispatch adopt` is composed and not
changed (`seldon/core/adopt.py` and `seldon/commands/dispatch.py` are untouched). The one existing function that was
refactored is `seldon init`. Its body moved, unchanged, into `initialize_project` so the new command can call it.
**Spend:** zero model calls. Tokens are in the `part_complete` records.
**Network:** none. Nothing was pushed: the launch clause leaves the merge and push to the dispatcher.

Recall used: seldon:2026-10-26_SEL-010R2_dispatch_waits_for_the_desktop_ooda_between_chained_tasks_RESULT, seldon:AD-037-R15

Why each hit mattered:
- SEL-010R2's RESULT and adopt's own tests gave the kit-fixture pattern the new tests reuse.
- AD-037-R15, with SEL-016's note that hazbrief's interpreter was left undeclared because its venv lacks seldon,
  is why `--interpreter` is refused unless the interpreter imports seldon.

## Part A: the command

**Usage:**

```
seldon project new <path> [--graph <name>] [--dispatch [--enable] [--no-load] [--interpreter PY]
                          [--standing-band-ref REF] [--label L] [--gate-command CMD]]
                          [--name N] [--template T] [--database D] [--branch B] [--force-init]
```

### The sequence it runs, in order

Each step reads the state it would produce and acts only on the difference, then reports `changed`, `ok`,
`skipped` or `refused`.

| # | Step | What it calls | SEL-016 (hazbrief) | aacps 8869c47 |
|---|---|---|---|---|
| 1 | `git init -b main`, only if the directory is not a repository. A directory inside another repository is refused. | git | already a repository | already a repository |
| 2 | `seldon init <name>`, skipped when `seldon.yaml` exists | `seldon.commands.init.initialize_project` | already initialized | `seldon init` (database `seldon-aacps-ai-policy`) |
| 3 | `seldon hooks install` and the `merge=union` declaration | `hooks.install`, `hooks.declare_union` | already `.githooks` | not in the commit |
| 4 | `seldon dispatch adopt --yes`, passing through `--standing-band-ref`, `--branch`, `--label`, `--gate-command` | `adopt.adoption`, `adopt.write_adoption`, unchanged | `adopt` with the band ref and gate command | `adopt` |
| 5 | the keys the hand adoptions added after adopt, each only when absent (list below) | new: `project_new.environment_text` | added by hand in `f98e44b` | added by hand |
| 6 | `squiddy init graphs/<name> --spec graphs/<name>/graph.yaml`, with `--graph` | squiddy's console script, run as a subprocess | (graph predates this task) | (graph made in AP-01 by hand) |
| 7 | one commit, through the hooks, of exactly the paths this run made dirty | git | `f98e44b` | `8869c47` |
| 8 | the plist symlinked into `~/Library/LaunchAgents`, then `launchctl bootstrap gui/<uid>` | `project_new.load_plist` | `ln -s` + `bootstrap gui/502` by hand | by hand |
| 9 | `dispatch.enabled: true` and its own commit, with `--enable`, after the load | `project_new.enabled_text` | `enabled: true` in `f98e44b` | `enabled: true` in 8869c47 |

The keys step 5 adds:
- `environment.packages`;
- `desktop_commit.scan`, copied from the kit's block, with its program re-rooted at the project;
- with `--dispatch`, `dispatch.stations.environment_ref: seldon.yaml#environment.packages`;
- with `--interpreter`, `dispatch.stations.interpreter`.

How steps 6 to 8 behave in detail:
- **Step 6, no spec yet.** When `graph.yaml` is absent, a skeleton is written from
  `seldon/templates/graph_spec/squiddy_graph.yaml`. Its required title, description and scope are blank: the scope
  is the operator's words (squiddy DN-028 R-129). squiddy's refusal is reported and the run exits 1. The next run
  initializes the graph.
- **Step 6, already initialized.** A graph with `.squiddy_init.json` is left alone.
- **Step 7.** Paths that were dirty before the run are left uncommitted and reported as `refused`.
- **Step 8.** A different file already at the symlink is refused, never overwritten. `--no-load` skips this step.

**Composition boundaries:**
- `adopt` writes `enabled: false`, and that is not changed. `--enable` flips the line afterwards.
- The kill-switch comment adopt wrote, "set true once the plist is loaded", is kept.

**What it does not do:**
- It registers nothing. It prints the `seldon cc register --project <path> cc_tasks/<file>` line to run next.
- It does not push. A new project has no remote.
- It does not add `worktree_links`. aacps added them for its gitignored inbox, and they are specific to each
  project.

**Config:** a new `project_new:` block in seldon's `seldon.yaml`. Every key is required:
- `environment_packages: [squiddy, seldon]`, the list hazbrief and aacps use;
- `squiddy_command: [../squiddy/.venv/bin/squiddy]`. squiddy has no `__main__`, so `python -m squiddy` does not
  run; this was measured;
- `launch_agents_dir`.

The secret scan is read from the existing `desktop_commit.scan` and is not restated.

**Prior art**, cited in `seldon/core/project_new.py`:
- convergent, idempotent steps that report `ok` or `changed`: CFEngine (Burgess) and Ansible;
- the one-seed-file scaffolding of cookiecutter and the OBO ODK, which `squiddy init` already adopted (K-001).

Nothing is templated twice.

**Files:**
- `seldon/core/project_new.py` (new)
- `seldon/commands/project.py` (new)
- `seldon/templates/graph_spec/squiddy_graph.yaml` (new)
- `seldon/commands/init.py`: the body moved to `initialize_project` with an optional `database`
- `seldon/cli.py`
- `pyproject.toml`: package data for the template
- `seldon.yaml`
- `docs/design/2026-09-15_standing_dispatcher.md`
- `CLAUDE.md`

### Tests

All 14 are in `tests/test_sel019_project_new.py` and pass (14 passed, 77.9 s).

The end-to-end tests use the real `seldon init` (against this process's test database), the real hooks and the real
adopt. `launchctl` is faked, and so is the kit:
- `test_a_temp_directory_becomes_a_project_with_a_dispatch_block_and_a_loaded_plist`: the dispatch block validates
  with `enabled: true`. `plistlib` parses the plist, and its Label and StartInterval match the block. The symlink
  and one `bootstrap` call are checked. The tree is clean on `main` and the hooks are installed.
- `test_a_second_run_on_an_adopted_project_changes_nothing_and_says_so`: HEAD and every file's bytes are unchanged.
  The only launchctl call is `print`.
- `test_an_existing_seldon_project_is_adopted_without_reinitializing`: the aacps shape.
- `test_with_a_graph_the_skeleton_is_committed_and_the_refusal_is_reported`

The step tests:
- `test_the_graph_step_converges_skeleton_then_init_then_ok`
- `test_the_real_squiddy_initializes_a_filled_skeleton`: runs the real squiddy beside the kit
- `test_enable_flips_only_the_dispatch_blocks_line_and_keeps_its_comments`
- `test_the_plist_load_refuses_a_foreign_file_at_the_link`
- `test_the_plist_load_reports_a_failed_bootstrap`
- `test_an_interpreter_that_cannot_import_seldon_is_refused`
- `test_a_directory_inside_another_repository_is_refused`
- `test_the_dispatch_only_options_need_dispatch`
- `test_the_kit_block_is_required_whole`
- `test_seldons_own_kit_block_loads`

A manual run on a scratch project printed each step's status, and its second run printed `nothing changed; already
a project`. The scratch Neo4j database it used (`seldon-sel019-demo`) was dropped afterwards.

**Full suite:** 3,255 passed, 1 failed, 12 skipped. It ran in two passes under `python -m dotenv -f .env run`:
- The first pass ran with `-x` over everything except the new file and stopped at the first failure: 1,848 passed,
  1 failed, 6 skipped, 3,101 s.
- The second pass ran every file after the failing one, including the new file: 1,407 passed, 6 skipped, 586 s.

The one failure is `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`.
- **The error:** `release_unavailable`. The `index:` block of squiddy's `graphs/library/extract/control.yaml` at
  `edd5d5d66bf2` differs from today's.
- **It also fails on main.** That is recorded on 2026-10-24 as library drift, and this branch touches nothing it
  reads.

## Part B: the record

This file. The design-note section the command replaces is `docs/design/2026-09-15_standing_dispatcher.md`,
"Adopting it in another project". Its hand steps, from "Add a `dispatch:` block" through the SEL-010R2 paragraph's
"prints the commit, `seldon hooks install` and `launchctl` lines to run", are now the "Since SEL-019" paragraph and
its list. The sequence table above maps each step to SEL-016 and to aacps 8869c47.

## For the operator

Nothing is required. Two notes:
1. **Until this merges,** the kit is the primary checkout and `seldon` on PATH runs it, so the command exists only
   after the dispatcher merges this branch. The next consumer repository then starts with this line in a shell (any
   directory):
   `seldon project new /Users/brock/GitHub/<repo> --dispatch --enable --graph <graph-name>`
   It then prints the `seldon cc register` line for the first task.
2. **When the run is made from a worktree,** `shared_ontology.source` points at that worktree's `ontology/`
   (`seldon init`'s existing behaviour). Run it from the installed `seldon`, which resolves to the primary.
