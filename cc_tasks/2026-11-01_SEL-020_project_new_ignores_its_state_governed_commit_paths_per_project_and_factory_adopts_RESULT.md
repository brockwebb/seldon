# RESULT: SEL-020, `project new` ignores its own state, the governed commit takes per-project paths, and factory adopts Seldon

**Task:** `cd2bb27d`,
`cc_tasks/2026-11-01_SEL-020_project_new_ignores_its_state_governed_commit_paths_per_project_and_factory_adopts.md`.
No addenda existed at launch.
**Date:** 2026-11-01. **Branch:** `worktree-ancient-leaping-bonbon`.

**Outcome:** Parts A, B and C are done. This file is Part D.
- **The stop condition did not fire.** A project without `desktop_commit.paths` behaves exactly as before; a test pins
  the refusal text. Factory's tree was clean before Part C began.
- **One defect was found and fixed beyond the task.** It was in SEL-019's `project new`. See "Found in Part C" below.

**Spend:** zero model calls. Tokens are in the `part_complete` records: A 97K, B 132K, C 164K cumulative.

**Network:**
- **seldon:** nothing was pushed. The launch clause leaves the merge and push to the dispatcher.
- **factory:** its new dispatcher's first pass pushed to `origin/main`. The pass ran at 12:03Z and pushed 22 commits:
  - the FCT-2 commits that were already unpushed;
  - this task's five.

  The task header allows "git push". Before the push, I grepped the tree for key values and found none (the check is
  under Part C).

Recall used: seldon:2026-11-01_SEL-019_aacps_adopts_seldon_and_the_dispatcher_and_a_new_consumer_project_becomes_one_command_RESULT, seldon:2026-10-15_DESK-001_desktop_writes_are_committed_RESULT

Why each hit mattered:
- **SEL-019's RESULT** gave two things:
  - the step table, which is where Part A's step goes;
  - its note that a worktree run writes the worktree's `ontology/` path. That is why factory was made with
    `SELDON_ONTOLOGY_PATH` set to the primary's tree.
- **DESK-001's RESULT and its tests** gave the governed-commit fixture that Part B's tests reuse. DESK-003's
  symlink rule in `desktop_commit.settings` is what identified the scan-program defect in Part C.

## Part A: `project new` writes the `.seldon/` ignore line

**Two changes:**
- **`seldon init`, step 5** (`seldon/commands/init.py`): `.seldon/` is now ensured in the `.gitignore` along with
  `.env`.
- **`project new`, new `ignore` step** (`project_new.ignore_step`, step 1b): it runs after init and appends `.seldon/`
  to the project's own `.gitignore` when that file does not already ignore it.
  - **A rule only in `.git/info/exclude` does not count.** That is where aacps carried it, and no clone or dispatched
    worktree inherits that file.
  - **It acts only on the difference,** like every SEL-019 step.

**Tests** (`tests/test_sel020_project_new_state_and_commit_paths.py`):
- `test_a_new_project_stays_clean_after_one_dry_run_pass`. A fresh directory goes through
  `project new --dispatch --enable` (real init, hooks and adopt; fake launchctl). The test then plants files under
  `.seldon/leases/` and `.seldon/` and runs one real `dispatch once --dry-run`. `git status --porcelain -uall` must be
  empty. **It failed before the fix:** `.seldon/` was not in `.gitignore`.
- `test_the_ignore_step_converges_and_keeps_existing_lines`
- `test_the_ignore_step_accepts_a_tracked_rule_written_another_way`
- `test_a_rule_only_in_info_exclude_is_not_enough`

## Part B: `desktop_commit.paths`

`seldon/core/desktop_commit.py`, used by both `seldon_commit_governed` and `seldon commit-governed`.

**When the key is absent:** `DEFAULT_ROOTS` or `roots`, unchanged.

**When `paths` is present,** it replaces the fixed set:
- **Entry format:** each entry is either an exact file or a directory written with a trailing `/`. The trailing-slash
  convention is gitignore(5)'s.
- **Other refusals, as `config_invalid`:**
  - an entry naming a directory without the trailing `/`;
  - an absolute path, or one containing `..`;
  - an empty entry;
  - a project that declares both `roots` and `paths`.
- **Every path committed is secret-scanned,** not only paths under `scan.roots`. For that reason the list is refused
  without `scan.command`, so a wider allowlist can never commit anything unscanned.
- **What still applies unchanged:** the hooks, the register rule and the draft rule.
- **Commit message kinds:**
  - a default root keeps its own kind (`task`, `handoff`);
  - any other directory is named by itself (`docs`);
  - an exact file is named `file`.
- **Docs updated:** the MCP and CLI docstrings, the `seldon.yaml` comment, and
  `docs/design/2026-09-15_standing_dispatcher.md` ("Since SEL-020").

**Tests:**
- `test_a_project_without_the_key_refuses_readme_exactly_as_before`: `README.md` is refused as `outside_roots`, with
  the detail text compared byte for byte. Nothing is staged.
- `test_declared_paths_commit_a_file_and_a_directory_and_refuse_the_rest`, with `[friction-log.md, docs/]`:
  - `friction-log.md` and `docs/x.md` are committed together;
  - `scripts/x.sh` is refused and left untracked;
  - `cc_tasks/t.md` is refused, because the list replaces the fixed set.
- `test_a_declared_path_holding_a_planted_secret_is_refused_by_the_scan`: `docs/leak.md` is refused as `secret_found`.
  `scan.roots` names only `handoffs/`.
- `test_a_malformed_declared_list_is_refused` (7 cases)
- `test_a_declared_list_needs_a_scan_and_excludes_roots`

The existing governed-commit tests pass unchanged: DESK-001, DESK-002 (both files) and DESK-004R, 17 + 14 tests.

## Part C: factory adopts Seldon

### 1. The key leaves the repository

- **The move:** `/Users/brock/GitHub/factory/.env` was moved (`mv -n`) to **`~/.config/factory/api.env`**. The
  directory is mode 700 and the file mode 600. Its contents were never printed; only the variable names were listed,
  to check what the file held.
- **`scripts/api_review.sh`** now sources only that file and refuses with exit 2 before anything else runs when the
  file is absent. The `factory/.env`, `~/GitHub/.env` and `~/.env` fallbacks are gone.
- **No other script under `factory/scripts/` reads the key.**
- **`.env.example`** now says where the key lives.
- **`decisions.md` was not amended.**

### 2. `seldon project new /Users/brock/GitHub/factory --dispatch --enable --database seldon-factory --branch main`

**How it was run:**
- It ran with this branch's code (`python -m seldon` from the worktree), so Part A's step applied.
- `SELDON_ONTOLOGY_PATH` was set to `/Users/brock/GitHub/seldon/ontology`, so factory's `seldon.yaml` names the
  primary's ontology and not the worktree's.
- Neo4j credentials came from seldon's `.env` through python-dotenv.
- The wrapper is `/tmp/sel020/project_new_factory.py`.

The first run's steps:

| step | status | detail |
|---|---|---|
| git | ok | already a git repository |
| init | changed | `seldon init factory`; database `seldon-factory`; `.gitignore` + `.seldon/` and the AD-039 stanza |
| ignore | ok | `.seldon/` was already ignored, because init now writes it |
| hooks | changed | `core.hooksPath .githooks`; `5d3f294`; merge=union `seldon_events.jsonl` (`08e3fcf`) |
| adopt | changed | `seldon.yaml`, `scripts/jobs/com.brock.factory-dispatch.plist`, `.gitignore` |
| environment | changed | `environment.packages`, `desktop_commit.scan`, `dispatch.stations.environment_ref` |
| graph | skipped | no `--graph` |
| commit | changed | `daa31d7`, 4 paths |
| plist | changed | symlinked into `~/Library/LaunchAgents`; `launchctl bootstrap gui/502` |
| enable | changed | `dispatch.enabled true` (`688ce79`) |

### 3. `desktop_commit.paths`, written exactly

```yaml
desktop_commit:
  paths:
  - decisions.md
  - friction-log.md
  - registry.md
  - README.md
  - docs/
  - reviews/
  - experiments/
  - handoffs/
  - cc_tasks/
  - scripts/
```

With this branch's code, that list parses to 6 directory roots and 4 exact files, with `scan_all` true. The scanner
it names, `../squiddy/.venv/bin/python -m squiddy.secret_scan`, ran from factory on `README.md` and `decisions.md`
and returned `scanned 2 file(s); exit 0`.

### Found in Part C: `project new` wrote a scan program that cannot run

**The defect:** step 5 re-rooted the kit's `../squiddy/.venv/bin/python` with `resolve()`. That follows the venv's
symlink to the bare uv CPython, so factory's first `seldon.yaml` named
`../../.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3.12`.

**Why it matters:**
- That interpreter runs outside the venv and cannot import `squiddy.secret_scan`. This is DESK-003's failure, the one
  `desktop_commit.settings` already guards against.
- So every scanned commit in factory would have refused as `scan_failed`. Under Part B that means every governed
  commit, since every committed path is scanned.

**Who it affected:** only a project that `project new` made. aacps and hazbrief were adopted by hand and carry the
correct path.

**The fix:**
- **In seldon (`550b160`):** the path is re-rooted lexically (`normpath`) instead. Test
  `test_the_copied_scan_program_keeps_the_venvs_symlink` failed first (`'../cpython/bin/python3' ==
  '../scanner/.venv/bin/python'`) and passes after the fix.
- **In factory:** `project new` never rewrites a key that is already present, so factory's line was corrected by hand
  in the same commit as `paths` (`ebf82b5`). The commit message and a comment beside the line both say so.

### Factory's commits

| sha | what |
|---|---|
| `f3e4b80` | C1: the key leaves the repository (`api_review.sh`, `.env.example`) |
| `5d3f294` | `seldon hooks install` commits the hook files |
| `08e3fcf` | merge=union for `seldon_events.jsonl` |
| `daa31d7` | `project new`'s commit: `seldon.yaml`, `.gitignore`, the plist, `seldon_events.jsonl` |
| `688ce79` | `dispatch.enabled: true` |
| `ebf82b5` | C3: `desktop_commit.paths` and the corrected scan program |

`origin/main` is now `ebf82b5`; the dispatcher's push put it there.

### The tests

1. **The first dispatcher pass:** it was launchd's own, at `2026-11-01T12:03:09Z`, three minutes after the
   bootstrap. Its log, `factory/logs/seldon_dispatch.log`:
   ```
   === 2026-11-01T12:03:09Z | seldon-dispatch fire
   nothing eligible (0 open, 0 candidate(s))
   push: pushed 22 commit(s)
   === rc=0
   ```
2. **`git status --porcelain -uall` in factory after that pass:** empty.
3. **`seldon dispatch status` in factory after that pass:**
   ```
   dispatch: enabled=True  branch=main (configured main)  dirty=False (0 path(s))
     stop file   : .seldon/DISPATCH_STOP absent
     standing band: 2,000,000 tokens  <- ../squiddy/squiddy/spend.yaml#job_token_cap_default
     lease        : free (released 2026-11-01T12:03:14.352787Z)
     claim        : none
     max_parallel : 1  (every task in a worktree under .claude/worktrees/, gate: None)
     open tasks   : 0  candidates: 0  eligible: 0
   ```
   Factory's `seldon_events.jsonl` holds no `refused` event; its one line is `ontology_synced`.
4. **`grep -r ANTHROPIC_API_KEY /Users/brock/GitHub/factory`:** no match holds a value.
   - The matches are:
     - the `.env.example` placeholder (`<short-lived key>`);
     - the name in `api_review.sh`'s refusal check;
     - prose in `decisions.md` and `docs/plan.md`;
     - Claude CLI warning lines in three `reviews/*/stderr.log` files and one `stream.jsonl`.
   - Two value-shaped greps found nothing: `ANTHROPIC_API_KEY=<6+ non-placeholder chars>` and `sk-ant-<8 chars>`.
   - **The test as written is not met literally.** Its "only `.env.example`" wording does not allow for the script's
     own check or the prose mentions. What it guards, no key value in the repository, holds.
5. **`api_review.sh` with the key file renamed away:** exit 2, `refused: no key file at
   /Users/brock/.config/factory/api.env`.
   - A fake `claude` placed first on `PATH` was never launched.
   - The key file was restored afterwards.
   - Harness: `/tmp/sel020/keytest.py`.
6. **A second `project new` run:** `nothing changed; already a project`. Every step reported `ok`, except `graph`,
   which reported `skipped` because it was not asked for.

## Full suite

**Result:** 3,130 passed, 1 failed, 7 skipped, in 1,340 s. The run was `python -m dotenv -f .env run -- python -m
pytest tests/ -q -n 8` at `550b160`.

The one failure is `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`.
- **The error:** `release_unavailable`. The `index:` block of squiddy's `graphs/library/extract/control.yaml` at
  `edd5d5d66bf2` differs from today's.
- **It also fails on main.** It is the library drift recorded on 2026-10-24 and again in SEL-019's RESULT. This
  branch touches nothing it reads.

## Files

**seldon:**
- `seldon/core/project_new.py`: `ignore_step` and `SESSION_STATE_LINE`; the scan program is now re-rooted lexically.
- `seldon/commands/project.py`: the `ignore` step.
- `seldon/commands/init.py`: `.seldon/` in step 5.
- `seldon/core/desktop_commit.py`: `paths`, `files`, `scan_all`, `_declared_paths`.
- `seldon/mcp_server.py` and `seldon/commands/commit_governed.py`: docstrings.
- `seldon.yaml`: comment.
- `docs/design/2026-09-15_standing_dispatcher.md`
- `CLAUDE.md`
- `tests/test_sel020_project_new_state_and_commit_paths.py` (new; 10 test functions, 16 cases with the parametrized
  one)

**factory:**
- `scripts/api_review.sh`
- `.env.example`
- `seldon.yaml`, `.gitignore`, `.gitattributes`, `.githooks/`, `scripts/jobs/com.brock.factory-dispatch.plist`,
  `seldon_events.jsonl`, all written by `project new`

## For the operator

Nothing is required to finish this task. Three things to know:
1. **Factory's dispatcher is live:** `com.brock.factory-dispatch` runs every 300 s.
   - **To stop it:** `touch /Users/brock/GitHub/factory/.seldon/DISPATCH_STOP`.
   - **To register factory's first task:** in a shell, run
     `seldon cc register --project /Users/brock/GitHub/factory cc_tasks/<YYYY-MM-DD_slug>.md`.
2. **The F-006 record is the coordinator's to write.** The key now lives at `~/.config/factory/api.env`, and
   `api_review.sh` has no fallbacks. `decisions.md` was not touched.
3. **Until this branch merges,** the primary's `desktop_commit.settings` ignores `paths`. A Desktop
   `seldon_commit_governed` call in factory therefore uses the fixed roots until the dispatcher merges this branch.
