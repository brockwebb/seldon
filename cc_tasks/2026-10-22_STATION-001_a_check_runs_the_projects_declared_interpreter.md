# STATION-001: a check runs under the project's declared interpreter, not the dispatcher's

**Repo:** seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green (AD-034 ADDENDUM 01). Evidence read in `/Users/brock/GitHub/squiddy` (read only; squiddy's own change is SUITE-001 there).
**Date:** 2026-10-22. **Authored by:** a Desktop session in squiddy (SQ9).
**Governing:** AD-037 ADDENDUM 02 (a check runs the branch code; `MODULE_COMMANDS` run as `<this python> -m`), AD-034-R8, AD-035 R3. Write the fix as AD-037 ADDENDUM 03. One new ruling: the interpreter a project's checks and sessions run under is the project's declaration, never the dispatcher's own.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.25M tokens. Basis: PA-002 (one resolver change, tests, re-verify) was estimated at 0.25M; this is one config key, two call sites, tests, and one measured re-run of a squiddy check. The floor is 131K (AD-037-R11).
**Parts:** A 0.3, B 0.5, C 0.2.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: `check_argv` substitutes the dispatcher's own interpreter for `pytest` and `seldon` | check: `grep -q 'argv = \[sys.executable, "-m", argv\[0\]' seldon/core/stations.py`
- premise: `run_check` records `sys.executable` as the check's interpreter | check: `grep -q '"interpreter": sys.executable' seldon/core/stations.py`
- premise: the dispatcher runs under anaconda, so `sys.executable` is anaconda's python for every project | check: `grep -q '/opt/anaconda3/bin:' scripts/jobs/seldon_dispatch.sh`
- premise: squiddy's interpreter is a project venv the station does not know about | check: `sh -c 'test -x /Users/brock/GitHub/squiddy/.venv/bin/python && ! grep -q interpreter /Users/brock/GitHub/squiddy/seldon.yaml'`
- premise: no stations default names an interpreter today | check: `sh -c '! grep -qE "^\s+\"interpreter(_ref)?\": None" seldon/core/stations.py'`

Glob and read every sibling `*STATION-001*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.30M. If Part B's change needs more than the stations module, the dispatch command module and their tests, stop and report what else it reaches.

## The defect, measured in a consuming project

squiddy `cc_tasks/2026-10-21_SQ-019_ai_readiness_kg_onto_the_kit_RESULT.md` line 16 ("Stop gate, round 1"): every `pytest` check in SQ-019's Parts ran as anaconda's `python -m pytest`, which has no `linkml`, so every fixture calling `squiddy init` errored at `gen-pydantic`. SQ-019 passed its gate only by adding generator placeholders to its own tests. The cause is AD-037 ADDENDUM 02's `check_argv`: `pytest` becomes `[sys.executable, "-m", "pytest"]`, and `sys.executable` is the interpreter the DISPATCHER runs in (`/opt/anaconda3/bin/python`, per `scripts/jobs/seldon_dispatch.sh`). That was the right fix for seldon, whose environment IS anaconda, and the wrong fix for every project whose environment is its own venv. The `interpreter` the row records is likewise the dispatcher's, so the record says the wrong thing about what ran.

The dispatched session has the same defect one level up: its PATH is the launchd job's, anaconda first, so a bare `pytest` or `python` typed by the session inside a squiddy worktree also resolves to anaconda.

## Part A: receipts

`seldon prior-art search`, both arms, logged in the addendum. The named prior art: PEP 405 (a venv is the project's interpreter, selected by path, never by whichever python is first on PATH); project-scoped runners (`uv run`, `poetry run`, `tox`, `nox`) that execute a project's commands under the project's declared environment and treat the invoking interpreter as irrelevant; Nextflow's per-process `conda`/`container` directive (the process declares its environment; the executor honours it); direnv (an environment bound to a directory, loaded on entry). State in one line what each decided here.

## Part B: the declaration and its two consumers

Test first.

1. One key, `dispatch.stations.interpreter`, project-relative path to the project's python (squiddy: `.venv/bin/python`). Absent means `sys.executable`, which is today's behaviour, so seldon's own config does not change. A declared path that does not exist is a `StationsConfigError` at config load, named, not a silent fallback.
2. `check_argv(command, interpreter)`: `MODULE_COMMANDS` run as `<interpreter> -m <it>`; a first word of `python` or `python3` also becomes `<interpreter>`. `run_check` prepends the interpreter's `bin` directory to `PATH` and sets `VIRTUAL_ENV` to its parent, so a child the check starts resolves the same python. The row records the interpreter actually used, and `shutil.which("pytest", path=run_env["PATH"])`, not `sys.executable`.
3. `_worktree_env` (commands/dispatch.py) gives the dispatched session the same `PATH` prefix and `VIRTUAL_ENV`, so a bare `pytest` inside the session is the project's.
4. Tests: a fixture project declaring a fake interpreter sees `check_argv` name it and the row record it; an undeclared project is byte-identical to today's argv and row; a declared path that does not exist refuses at load; the session env carries the bin directory first.

## Part C: measured on squiddy

With squiddy's `seldon.yaml` carrying `dispatch.stations.interpreter: .venv/bin/python` (SUITE-001 adds it; if it is not there yet, add it in squiddy on a scratch copy of the config for this measurement only and say so), run one squiddy check through `run_check` from this branch: `pytest tests/test_sq019_init_inbox.py -q`. Record the row's interpreter and outcome. Before the fix it errors at `gen-pydantic`; after, it passes. That pair is the delivery evidence.

## Deliverables

Code and tests; `docs/design/AD-037_ADDENDUM_03_a_check_runs_the_projects_interpreter.md` with the receipts and the ruling; `cc_tasks/2026-10-22_STATION-001_a_check_runs_the_projects_declared_interpreter_RESULT.md` with the before/after row from Part C and premises wrong.
