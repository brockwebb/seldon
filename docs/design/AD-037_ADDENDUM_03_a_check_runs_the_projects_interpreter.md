# AD-037 ADDENDUM 03: a check runs under the project's declared interpreter, not the dispatcher's

**Date:** 2026-10-22. **Written by:** STATION-001 (`cc_tasks/2026-10-22_STATION-001_a_check_runs_the_projects_declared_interpreter.md`).
**Amends:** AD-037-R14's "the dispatcher's python" for a project that declares its own. R14's import path rule is
unchanged. One new ruling, numbered from the register.

## Evidence: squiddy SQ-019, 2026-10-21

squiddy `cc_tasks/2026-10-21_SQ-019_ai_readiness_kg_onto_the_kit_RESULT.md`, "Stop gate, round 1": every `pytest`
check in SQ-019's Parts ran as anaconda's `python -m pytest`. Anaconda has no `linkml`, so every fixture that called
`squiddy init` errored at `gen-pydantic`. SQ-019 passed its gate only after adding generator placeholders to its own
tests (`tests/sq019_generation.py`). The cause is R14's `check_argv`, which turns `pytest` into
`[sys.executable, "-m", "pytest"]`. `sys.executable` is the python the DISPATCHER runs in, `/opt/anaconda3/bin/python`
(`scripts/jobs/seldon_dispatch.sh` puts `/opt/anaconda3/bin` first on PATH). That is seldon's own environment, so R14 was
right for seldon. It is wrong for any project whose environment is its own venv. The row's `interpreter` was the
dispatcher's too, so the record misreported what ran. The dispatched session had the same defect one level up: its
PATH is the launchd job's, so a bare `pytest` typed in a squiddy worktree also resolved to anaconda.

Measured on this branch (STATION-001 Part C, the RESULT has the rows): `pytest tests/test_init.py -q` in squiddy
through `run_check` gives 28 failed and 28 passed under anaconda (`FileNotFoundError` at `/opt/anaconda3/bin/gen-pydantic`).
Under the declared `.venv/bin/python` it gives 56 passed.

## The rule

- **AD-037-R15. The interpreter a project's checks and dispatched sessions run under is the project's declaration, never the dispatcher's own.**
  `dispatch.stations.interpreter` is a path to the project's python, relative to its primary checkout (squiddy:
  `.venv/bin/python`). It is resolved at config load, and a declared path that does not exist or is not executable
  refuses there with a `StationsConfigError` that names the key. It never falls back silently. When it is declared,
  a check's `pytest` and `seldon` run as `<interpreter> -m <it>`, a first word of `python` or `python3` becomes
  `<interpreter>`, and `run_check` puts the interpreter's `bin` first on `PATH` and sets `VIRTUAL_ENV` to its parent.
  A child the check starts therefore resolves the same python. The row records that interpreter and the `pytest` that
  `PATH` resolves, and the `stop_gate` record names it. The dispatched session's environment (`_worktree_env`) gets the
  same `PATH` prefix and `VIRTUAL_ENV`. When it is absent, the interpreter is `sys.executable`, and the argv, the row
  and the session environment are exactly R14's. Seldon's own config does not change. Code: `seldon/core/stations.py`
  `STATIONS_DEFAULTS["interpreter"]`, `resolve_interpreter`, `interpreter_kw`, `interpreter_env`, `check_argv`,
  `run_check`, `stop_gate`, `inspect`, `review_premises`; `seldon/core/dispatch.py` `load_dispatch_config`;
  `seldon/commands/dispatch.py` `_worktree_env`; `seldon/commands/dispatch_worktree.py` `run_task_checks`; tests
  `tests/test_station001_project_interpreter.py`.

*Scope, recorded rather than widened:* the Stop, PermissionDenied and PreToolUse hooks still run as the dispatcher's
python (`_session_settings` names `sys.executable` absolutely). That is right, because the hook is seldon's gate and not
the project's code. The project's `bin` first on the hook's inherited PATH does not change which python runs the hook.
A console script other than `pytest` and `seldon` that a check names (`gen-pydantic`, say) is found on PATH. The declared
`bin` comes first, so it is the venv's.

## Prior art

### External

- library receipt: query "project virtual environment interpreter selected by path not PATH" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-22_arXiv_2505_20286#p6:107:0-163

  The library's one relevant row (arXiv 2505.20286, p. 6) is an agent benchmark: "the environment is explicitly
  activated prior to invoking the code interpreter". That is the same discipline in one sentence. The other rows are
  unrelated uses of "path" and "environment". The engineering sources below are the prior art, and each decided one
  thing here:

- **PEP 405, Python virtual environments.** A venv is selected by running its `bin/python` by path. The `activate`
  script only puts that `bin` first on `PATH` and sets `VIRTUAL_ENV`. *Decided here:* the declaration is a path to
  the interpreter, and R15's environment change is exactly what `activate` does, no more.
- **Project-scoped runners: `uv run`, `poetry run`, `tox`, `nox`.** Each executes a project's commands under the
  project's declared environment, and the interpreter that invoked the runner is irrelevant. *Decided here:* the
  dispatcher is such a runner. Its own `sys.executable` is a default for a project that declares nothing, never a
  choice it makes for a project that does.
- **Nextflow's per-process `conda` and `container` directives.** The process declares its environment and the
  executor honours it. *Decided here:* the declaration lives in the project's `seldon.yaml`, beside the checks it
  governs, and the dispatcher reads it rather than inferring it.
- **direnv.** An environment is bound to a directory and loaded on entry. *Decided here:* the dispatched session gets
  the project's `PATH` and `VIRTUAL_ENV` when it starts in the project's worktree, so a bare `pytest` the session types
  is the project's. That is the binding direnv makes, applied by the launcher instead of a shell hook.

### Internal

- internal receipt: query "anaconda" | repo squiddy@63dbe15cd1dfddc8da1aa4bbd8e2d867fff13752 | hits handoffs/2026-10-22_dn049_sq019_ai_readiness_onto_kit_merged.md:19
- internal receipt: query ".venv/bin/python" | repo seldon@3a0f71ea682a399a49fd53e55c66c9e0a9ba418f | hits docs/SEL-002_delivery_report.md:289
- internal receipt: query "interpreter venv sys.executable" | repo seldon@3a0f71ea682a399a49fd53e55c66c9e0a9ba418f | hits none

The squiddy handoff (line 19) files this defect as SUITE-001 and STATION-001. SEL-002's delivery report (line 289)
records the portfolio's own convention: squiddy's suite is `.venv/bin/python -m pytest tests -q` and seldon's is
`python -m pytest` under anaconda. Each project already has a declared interpreter in prose, and R15 moves it into
config. No earlier ruling chose an interpreter per project. The third search, for the mechanism's own words, found
none.

## Negative control (AD-038-R6)

`tests/test_station001_project_interpreter.py::test_the_negative_control_undeclared_the_same_check_fails_and_the_row_is_todays`
and `::test_the_stop_gate_undeclared_records_the_dispatchers_interpreter`. Without the declaration, the check that
passes only under the fake declared interpreter fails, the gate blocks, and the row carries R14's keys and
`sys.executable` and nothing more.
