# RESULT: SEL-018, a relative path in `dispatch:` resolves against the primary checkout

**Task:** `cc43d8c8`, `cc_tasks/2026-10-30_SEL-018_relative_dispatch_paths_resolve_against_the_primary_checkout.md`.
No addenda were filed.
**Branch:** `worktree-breezy-popping-planet`. The code and tests are in `590d3e8`. The closing commit carries this
file. There was no merge, push or `cc complete`: the dispatcher does those.
**Parts:** A was recorded with `seldon dispatch part-complete` at 119,560 tokens and 1,394 s. B was recorded at
125,949 tokens and 2,892 s.
**Premises:** both held when read. `path = project_dir / rel` was at `seldon/core/dispatch.py:1034`, and
`def primary_checkout` is at `seldon/core/worktree.py:46`.
**Rulings:** none. The fix applies AD-034-R8 (a file that must be one file across worktrees resolves to the primary
checkout) and DN-006 §5 (the standing band is read by reference) to the keys of the `dispatch:` block.

Recall used: AD-034-R8, AD-037-R15

AD-034-R8 widened the scope beyond `standing_band_ref`. The STOP file, the lease, the per-worktree leases and the
log directory are each one file per project, so a worktree must read the primary's copy. Without that, a worktree
session would report no STOP file while one was present. AD-037-R15 (STATION-001) is why
`dispatch.stations.interpreter` is covered as well: squiddy declares `.venv/bin/python`, which is gitignored and so
missing from every worktree. HOOK-002 and `cross_project._anchor` / `recall.project_root` (RECALL-002R) supplied the
rule for paths outside a git work tree: the directory is its own anchor. That rule is not new.

## Part A: the resolver

- **`worktree.anchor(path)`** (`seldon/core/worktree.py`) returns the primary checkout when run from a linked
  worktree. From the primary itself it returns `path` exactly as given, so nothing the dispatcher does there changes,
  including the textual form of the path. Outside a git work tree, `path` is its own anchor.
- **`dispatch.config_path(project_dir, value)`** joins a relative value to the anchor and leaves an absolute value
  alone. **`dispatch.config_rel`** is its inverse, used for paths recorded in events. `part-complete` already joins a
  recorded `log_path` to the primary (AD-038-R4), so a path recorded relative to a worktree would have been read
  from the wrong place.
- **`resolve_standing_band`** now resolves through `config_path`. Its error names the reference, the path it looked
  for, and the primary checkout it resolved against, for example: `standing_band_ref '../sibling/spend.yaml#caps.job'
  names ../sibling/spend.yaml, which does not exist (looked for <primary>/../sibling/spend.yaml, resolved against
  the primary checkout <primary>)`.

**The audit of the block.** Every key that holds a path, with its call sites:

| key | treatment |
|---|---|
| `standing_band_ref` | `config_path` (the HB-73 defect) |
| `stop_file` | `config_path`: `core/dispatch.py` (enabled check, c8), `commands/dispatch.py` (status, pass), `commands/go.py` |
| `lease_file` | `config_path`: `lease_is_held`, the stuck, last-pass and outage state files, `Lease`/`acquire_waiting`, status, reap, inspect, `_lease_dir` (stations lock, premise review), `_sibling_lease`, `prior_art._lease_defers` |
| `lease_dir` | `config_path`: `worktree_lease_path`, `worktree_leases`. The `path` of a listed lease is relative to the primary, which is what `models.py` joins it to |
| `log_dir` | `config_path`: task logs, gate logs and OODA logs. The recorded `log_path` and `lease_path` use `config_rel` |
| `cross_repo_root` | `config_path`: `cross_repo_launch`. From a worktree, `..` had named `.claude/worktrees` |
| `stations.interpreter` | `resolve_interpreter` joins it to the anchor. All three loaders go through that function |
| `stations.environment_ref` | `environment_repositories` reads the ref file, and resolves sibling names, at the anchor |
| `gate_command` | **no change**: it runs with `cwd` set to the task's own worktree, which the dispatcher created from the primary. That is intended: the re-gate tests the worktree's code. It reads `.env` through `$SELDON_PRIMARY_CHECKOUT`, which already resolves at the primary |
| `notify` | no path |

**One behaviour kept explicitly.** `prior_art._lease_defers` asks whether another session is working in this
checkout under the dispatcher's lease. The lease guards the primary's tree, where a pass commits. A linked worktree's
tree belongs to its own session (AD-034). Before this change, a worktree never found the lease file, so it never
deferred. With `lease_file` now resolved at the primary, a dispatched worktree session would have deferred its own
prior-art commits to the dispatcher that launched it. The function now returns `False` in a linked worktree on
purpose, and a test holds that. `commit_journal_append` in a worktree now reports `lease_held` where it used to
report `wrong_branch`. Both mean "not committed", so this changes only the reason it gives.

## Part B: the fixture

`tests/test_sel018_relative_dispatch_paths.py` has 13 tests. The fixture is a `primary` checkout beside
`sibling/spend.yaml`, with `standing_band_ref: ../sibling/spend.yaml#caps.job` and a linked worktree at the CLI's own
place (`primary/.claude/worktrees/x`):

- The plant: from the worktree, `../sibling/spend.yaml` does not exist, but from the primary it does.
- `resolve_standing_band` reads the cap from both the worktree and the primary. An absolute ref is left alone.
- **Negative control:** with the sibling removed, it still refuses, and the message contains both the reference and
  `primary checkout <primary>`.
- From the primary, `config_path(p, rel) == p / rel` exactly. In a plain directory, the directory is its own anchor.
- From the worktree, the STOP file, lease, per-worktree leases, stuck-state file, log directory and cross-repo root
  are the primary's. The primary's STOP file is visible from the worktree.
- The interpreter and the `environment_ref` siblings resolve at the primary.
- `_lease_defers` is `False` from the worktree while the primary's lease is live (planted with this process's PID),
  and `True` from the primary.
- **`dispatch status --json` run from inside a worktree** of a full scaffold project (Neo4j) reports
  `standing_band == 1234567`. With the sibling absent it raises `DispatchConfigError` naming the primary checkout.

**Fails before the fix.** I ran the same test file against `main`'s code (`git archive main` into
`/tmp/sel018_main`): 12 failed and 1 passed. The test that passed is the plant check, which describes the condition
rather than the fix. The `dispatch status` test fails there with HB-73's error.

## The suite

`python -m dotenv -f $SELDON_PRIMARY_CHECKOUT/.env run -- env PYTHONPATH=. python -m pytest tests/ -q -n auto`:
**3,098 passed, 3 failed, 7 skipped** (1,390 s).

- `test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index` fails with
  `release_unavailable`, because squiddy's `graphs/library/extract/control.yaml` `index:` block has drifted from its
  release. This is the known pa002 drift and does not touch this change.
- Two tests in `test_dispatch_parallel.py` failed: `test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge`
  (an overlap-window assertion) and `test_a_killed_supervisor_is_marked_by_the_next_pass_and_its_worktree_kept`
  (`< 30 s` wall clock). Both are timing assertions, and both **pass when rerun on their own** (2 passed in 60 s).
  Under `-n auto` the machine is loaded. They run from the primary of a scaffold, where `anchor == project_dir`.

An earlier run found one real regression, which is now fixed: `test_sel014r_ooda_knowledge_source.py::
test_an_amended_verdict_is_found_when_the_project_is_a_linked_worktree`. The OODA runner printed and recorded its
log path relative to the worktree, while the log now lives in the primary. It now uses `config_rel`, and the test
passes.

## Not done

- Nothing outside the `dispatch:` block was changed. `event_store.path`, `decisions.repositories` and the cadence
  instance paths already have their own resolution, or are tracked files that every worktree has.
- `cross_project._anchor` and `recall.project_root` each still inline the same anchor rule. Moving them to
  `worktree.anchor` is a refactor this task did not ask for. Note that `_anchor` resolves symlinks while `anchor`
  preserves the path form from the primary, so the move is not purely mechanical.
