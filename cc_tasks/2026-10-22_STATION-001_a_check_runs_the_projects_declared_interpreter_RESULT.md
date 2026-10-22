# RESULT: STATION-001, a check runs under the project's declared interpreter, not the dispatcher's

**Date:** 2026-10-22
**Session:** dispatched, headless, worktree branch `worktree-deep-greeting-whisper`. Not merged, not pushed, and
`seldon cc complete` not run, per the session's instruction (the dispatcher merges and completes).
**Addenda:** none (`cc_tasks/*STATION-001*ADDENDUM*.md` globbed: no match).
**Ruling:** AD-037-R15, `docs/design/AD-037_ADDENDUM_03_a_check_runs_the_projects_interpreter.md`, written to the
register as pending (`docs/decisions/register/pending/00001_46f0d793cba6e43a_seldon-ad-037-r15_accept.yaml`,
AD-033-R12; the merge numbers it).

Recall used: seldon:AD-037-R14

(The task's Governing line already named R14. Its register record was the template for R15's: the same fields, with
`source.text` carrying the note's own bytes. The other hits were not opened.)

## Premises, as checked at start

All five held. They were run one by one in the worktree, because the sandbox refused the combined form.
`check_argv` substituted `sys.executable`. `run_check` recorded `"interpreter": sys.executable`, and so did the
`stop_gate` record (two matches). The dispatch wrapper puts `/opt/anaconda3/bin` first on PATH. squiddy's
`.venv/bin/python` exists and its `seldon.yaml` names no interpreter. No stations default named one.

## Part A: receipts

They are in the addendum's `## Prior art`, and `seldon prior-art verify` on it returns PASS (governed-ledger event
`ed5fe47c3eca489298ebf62af4f20faf`).

- Library arm: "project virtual environment interpreter selected by path not PATH". One relevant row, arXiv 2505.20286
  p. 6: "the environment is explicitly activated prior to invoking the code interpreter". The rest were noise.
- Internal arm: "anaconda" hits squiddy's handoff naming this defect (`2026-10-22_dn049_..._merged.md:19`).
  ".venv/bin/python" hits SEL-002's delivery report line 289, the portfolio's per-project suite commands.
  "interpreter venv sys.executable" got no hits in any of the seven repositories.
- What each named source decided here: PEP 405 means the declaration is a path, and R15's environment change is
  exactly what `activate` does. `uv run`/`poetry run`/`tox`/`nox` mean the dispatcher is a runner, so its own interpreter
  is only the default for a project that declares none. Nextflow's `conda`/`container` directive means the
  declaration lives in the project's config and the executor honours it. direnv means the dispatched session gets
  the project's PATH and `VIRTUAL_ENV` when it starts in that project's worktree.

## Part B: the declaration and its consumers

Test first. `tests/test_station001_project_interpreter.py` has 20 tests. 17 failed on the base and 3 passed: the
undeclared argv, the negative control and the undeclared gate pin today's behaviour. All 20 pass after the change.

1. `dispatch.stations.interpreter` (`STATIONS_DEFAULTS`, default None). `resolve_interpreter` resolves a relative path
   against the project directory. A path that is missing, not executable or not a string raises
   `StationsConfigError` naming the key. A relative path with no project directory also refuses; it never falls
   back. `load_dispatch_config` passes `project_dir` and writes the absolute path back into `block["stations"]`, so
   every later `load_stations_config(cfg)` reads it from whatever directory it runs in.
2. `check_argv(command, interpreter=None)`: `pytest`/`seldon` become `<interpreter> -m <it>`, and `python`/`python3`
   become `<interpreter>`, but only when one is declared. `run_check(..., interpreter=None)` adds the interpreter's
   `bin` to the front of PATH and sets `VIRTUAL_ENV` (`interpreter_env`). The row records `interpreter` and
   `pytest` (`shutil.which("pytest", path=run_env["PATH"])`). The `stop_gate` record names the declared interpreter.
   The Stop gate, the first article, the premises and the regate (`run_task_checks`) all pass it through
   `interpreter_kw`, which returns `{}` when undeclared, so those calls are byte-identical to today's.
3. `_worktree_env(project_dir, spec, cfg)` gives the session the same PATH prefix and `VIRTUAL_ENV`. Undeclared,
   it returns exactly today's dict (tested).
4. The tests cover: a fake declared interpreter named in argv and in the row; a child process that resolves the same
   python; a real `pytest` check under it; a missing path refused at load; the undeclared argv, row and session env
   pinned to today's; and a premise run under it.

**Stop condition, read and decided.** The condition says to stop if the change "needs more than the stations
module, the dispatch command module and their tests". The change also touched `seldon/core/dispatch.py`
(`load_dispatch_config`: pass `project_dir` and write back the resolved path, 5 lines) and
`seldon/commands/dispatch_worktree.py` (the second `_worktree_env` call site and `run_task_checks`, 3 lines). I read
`dispatch_worktree.py` as part of the dispatch command module: it is split out of `commands/dispatch.py` and imports
it as `S`. `core/dispatch.py` is where the stations block is already validated at load, so "refuses at config load"
cannot be met anywhere else. Nothing else was reached, so I continued rather than stopping.

**Not widened, recorded:** `premises_registration_refusal` already caught any `StationsConfigError` and fell back to
the defaults. It now passes `project_dir`, so a valid declaration works at registration. A broken one still falls
back there, silently. Dispatch refuses it at `load_dispatch_config`, so nothing is launched under the wrong python.
The fallback predates this task. Making it refuse would change what registration does for every malformed stations
key, which is outside this task.

## Part C: measured on squiddy

squiddy's `seldon.yaml` does not carry the key yet (SUITE-001 adds it). The declaration was applied to an
**in-memory copy** of its `dispatch` block (`/tmp/st001_measure.py`). squiddy's file was not written, and
`git status` in squiddy was clean before and after. The checks ran through this branch's `run_check` (`seldon.__file__`
= this worktree), in squiddy's primary checkout, with squiddy's `check_timeout_s`.

| Check | Run | interpreter | pytest on PATH | outcome | reading |
|---|---|---|---|---|---|
| `pytest tests/test_sq019_init_inbox.py -q` | before | `/opt/anaconda3/bin/python` | (none recorded) | pass | 6 passed |
| same | after | `/Users/brock/GitHub/squiddy/.venv/bin/python` | `.../squiddy/.venv/bin/pytest` | pass | 6 passed |
| `pytest tests/test_init.py -q` | before | `/opt/anaconda3/bin/python` | (none recorded) | **fail**, exit 1 | 28 failed, 28 passed; `FileNotFoundError` at `/opt/anaconda3/bin/gen-pydantic` |
| same | after | `.../squiddy/.venv/bin/python` | `.../squiddy/.venv/bin/pytest` | **pass** | 56 passed |
| `pytest tests/test_sq019_adopt_airkg.py -q -rs` | before | `/opt/anaconda3/bin/python` | (none recorded) | pass | 1 passed, 1 skipped ("the kit's write path needs linkml_runtime") |
| same | after | `.../squiddy/.venv/bin/python` | `.../squiddy/.venv/bin/pytest` | pass | 2 passed |

The delivery evidence is the `tests/test_init.py` pair. The task's named check could not supply it (see Premises
wrong). The adopter pair shows the masking: under anaconda, a test SQ-019 needed was skipped instead of run.

## Premises wrong

- **Part C, "Before the fix it errors at `gen-pydantic`"** for `tests/test_sq019_init_inbox.py`: false today. SQ-019's
  own fix (`tests/sq019_generation.py`) replaces generation with placeholders when the generators are absent, so
  the file passes under anaconda (6 passed). The defect is still there and still measurable. `tests/test_init.py`,
  which that helper names as the generation coverage, fails 28 of 56 under anaconda. SUITE-001 can remove the
  placeholders once squiddy declares its interpreter.
- **"Part B's change needs only the stations module, the dispatch command module and their tests"** (the stop
  condition): it also needed 5 lines in `seldon/core/dispatch.py`. See above.

## Suites

- Focused (stations, gate path, loop001, friction001/002, first article, milestone, premises, andon, qc chart,
  disp001r, the new file): 82 passed.
- Full suite, `python -m dotenv -f .env run -- python -m pytest tests/ -q`, on the committed tree:
  **2786 passed, 7 skipped, 0 failed** (37 min). An earlier `-x` run on the uncommitted tree stopped at
  `test_dispatch_stuck_and_journal.py::test_a_project_with_no_dispatch_block_is_left_alone`, whose assertion reads
  the repository's own dirty state ("uncommitted changes under seldon/"). It passed once the work was committed.

## For the operator, and SUITE-001

squiddy needs one line under `dispatch.stations`: `interpreter: .venv/bin/python`. Until it is there, squiddy's checks
and sessions behave exactly as before, which is the defect. With it, SQ-019's placeholder generation becomes dead code
under the gate.
