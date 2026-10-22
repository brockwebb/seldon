"""STATION-001 (AD-037 ADDENDUM 03): a check runs under the project's declared interpreter, not the dispatcher's.

AD-037 ADDENDUM 02 ran a check's `pytest` and `seldon` as `sys.executable -m <it>`, and `sys.executable` is the
interpreter the DISPATCHER runs in (anaconda). squiddy's environment is its own venv, so every SQ-019 `pytest` check ran
without linkml and errored at `gen-pydantic` (squiddy SQ-019 RESULT, "Stop gate, round 1"). Each test here declares a
fake interpreter, a shell script that marks its environment and execs the real python, so only a check that ran under
the declared interpreter can see the mark. The undeclared tests pin today's argv, row and session env byte for byte.
"""
from __future__ import annotations

import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from seldon.commands import dispatch as CD
from seldon.core import stations as S
from seldon.core.dispatch import DispatchConfigError, load_dispatch_config
from tests import stations_scaffold as F

MARK = "STATION001_DECLARED_INTERPRETER"
DECLARED = ".venv/bin/python"
#: Passes only when the process that runs it was started by the fake interpreter.
UNDER_FAKE = f"python -c \"import os, sys; sys.exit(0 if os.environ.get('{MARK}') else 1)\""


def _executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _fake_venv(project: Path) -> Path:
    """`<project>/.venv/bin/python`, which marks the environment and runs the real interpreter; and a `pytest` beside
    it, so the row's `pytest` reading has one to find."""
    py = _executable(project / DECLARED, textwrap.dedent(f"""\
        #!/bin/sh
        export {MARK}=1
        exec {sys.executable} "$@"
        """))
    _executable(py.parent / "pytest", f"#!/bin/sh\nexec {py} -m pytest \"$@\"\n")
    return py


def _project(tmp_path: Path, declare: bool = True, **kw) -> tuple[Path, Path | None]:
    p = F.make_project(tmp_path, stations={"interpreter": DECLARED} if declare else None, **kw)
    return p, (_fake_venv(p) if declare else None)


# ---------------------------------------------------------------------------------------------- check_argv

def test_an_undeclared_interpreter_leaves_argv_as_today():
    assert S.check_argv("pytest tests/x.py -q") == [sys.executable, "-m", "pytest", "tests/x.py", "-q"]
    assert S.check_argv("seldon verify") == [sys.executable, "-m", "seldon", "verify"]
    assert S.check_argv("python -c pass") == ["python", "-c", "pass"]
    assert S.check_argv("grep -q x f") == ["grep", "-q", "x", "f"]


def test_a_declared_interpreter_runs_pytest_seldon_and_python():
    py = "/p/.venv/bin/python"
    assert S.check_argv("pytest tests/x.py -q", py) == [py, "-m", "pytest", "tests/x.py", "-q"]
    assert S.check_argv("seldon verify", py) == [py, "-m", "seldon", "verify"]
    assert S.check_argv("python -c pass", py) == [py, "-c", "pass"]
    assert S.check_argv("python3 -c pass", py) == [py, "-c", "pass"]
    assert S.check_argv("grep -q x f", py) == ["grep", "-q", "x", "f"]


# ---------------------------------------------------------------------------------------------- the config

def test_a_declared_path_resolves_against_the_project_at_load(tmp_path):
    p, py = _project(tmp_path)
    cfg = load_dispatch_config(p)
    assert cfg["stations"]["interpreter"] == str(py)
    assert S.load_stations_config(cfg)["interpreter"] == str(py)


def test_undeclared_is_none(tmp_path):
    p, _ = _project(tmp_path, declare=False)
    assert S.load_stations_config(load_dispatch_config(p))["interpreter"] is None


def test_a_declared_path_that_does_not_exist_refuses_at_load(tmp_path):
    p = F.make_project(tmp_path, stations={"interpreter": DECLARED})
    with pytest.raises(DispatchConfigError, match=r"dispatch\.stations\.interpreter.*does not exist"):
        load_dispatch_config(p)
    with pytest.raises(S.StationsConfigError, match=r"dispatch\.stations\.interpreter"):
        S.load_stations_config({"stations": {"interpreter": DECLARED}}, p)


def test_a_declared_path_that_is_not_executable_refuses(tmp_path):
    p = F.make_project(tmp_path, stations={"interpreter": DECLARED})
    (p / ".venv" / "bin").mkdir(parents=True)
    (p / DECLARED).write_text("", encoding="utf-8")
    with pytest.raises(DispatchConfigError, match="not an executable file"):
        load_dispatch_config(p)


@pytest.mark.parametrize("value", ["", "  ", 3, ["a"]])
def test_a_malformed_value_refuses(value):
    with pytest.raises(S.StationsConfigError, match=r"dispatch\.stations\.interpreter must be"):
        S.load_stations_config({"stations": {"interpreter": value}}, Path("/"))


def test_a_relative_path_without_the_project_refuses(tmp_path):
    with pytest.raises(S.StationsConfigError, match="project directory"):
        S.load_stations_config({"stations": {"interpreter": DECLARED}})


# ---------------------------------------------------------------------------------------------- run_check

def test_a_check_runs_under_the_declared_interpreter_and_the_row_says_so(tmp_path):
    p, py = _project(tmp_path)
    r = S.run_check(UNDER_FAKE, p, 60, interpreter=str(py))
    assert r["outcome"] == "pass", r
    assert r["interpreter"] == str(py)
    assert r["pytest"] == str(py.parent / "pytest")


def test_a_child_the_check_starts_resolves_the_same_python(tmp_path):
    """`run_check` puts the interpreter's `bin` first on PATH and sets VIRTUAL_ENV, so a bare `python` a check's
    child types is the project's too."""
    p, py = _project(tmp_path)
    (p / "child.sh").write_text(f"{UNDER_FAKE} && test \"$VIRTUAL_ENV\" = {py.parent.parent}\n", encoding="utf-8")
    assert S.run_check("sh child.sh", p, 60, interpreter=str(py))["outcome"] == "pass"
    assert S.run_check("sh child.sh", p, 60)["outcome"] == "fail"


def test_a_declared_pytest_check_runs_the_declared_interpreter(tmp_path):
    p, py = _project(tmp_path)
    (p / "test_mark.py").write_text(f"import os\ndef test_mark():\n    assert os.environ.get('{MARK}')\n",
                                    encoding="utf-8")
    assert S.run_check("pytest test_mark.py -q -p no:cacheprovider", p, 120, interpreter=str(py))["outcome"] == "pass"


def test_the_negative_control_undeclared_the_same_check_fails_and_the_row_is_todays(tmp_path):
    """AD-038-R6: without the declaration the fake-only check does not pass, and the row carries exactly today's
    keys and the dispatcher's own interpreter."""
    p, _ = _project(tmp_path, declare=False)
    r = S.run_check(UNDER_FAKE, p, 60)
    assert r["outcome"] == "fail", r
    assert r["interpreter"] == sys.executable
    assert set(r) == {"command", "interpreter", "pythonpath", "outcome", "exit", "seconds", "tail", "output_sha256"}


# ---------------------------------------------------------------------------------------------- the stations

def _gated(tmp_path: Path, declare: bool) -> dict:
    p, _ = _project(tmp_path, declare=declare, check_a=UNDER_FAKE)
    F.launch(p, at=F.ago(60))
    F.write_log(p, 1000)
    F.record(p, "part_complete", {"part": "A", "planned_share": 0.5, "tokens": 1000})
    return F.gate(p)["record"]


def test_the_stop_gate_runs_and_records_the_declared_interpreter(tmp_path):
    rec = _gated(tmp_path, declare=True)
    py = str(tmp_path / "proj" / DECLARED)
    assert rec["verdict"] == "pass", rec
    assert rec["interpreter"] == py
    assert rec["parts"][0]["checks"][0]["interpreter"] == py


def test_the_stop_gate_undeclared_records_the_dispatchers_interpreter(tmp_path):
    rec = _gated(tmp_path, declare=False)
    assert rec["verdict"] == "block", rec
    assert rec["interpreter"] == sys.executable


def test_a_premise_runs_under_the_declared_interpreter(tmp_path):
    p, _ = _project(tmp_path)
    scfg = S.load_stations_config(load_dispatch_config(p))
    text = f"**Premises:**\n- premise: the venv is the project's | check: `{UNDER_FAKE}`\n"
    review = S.review_premises(p, text, scfg)
    assert review["ok"], review


# ---------------------------------------------------------------------------------------------- the session

def test_the_session_env_puts_the_declared_bin_first(tmp_path):
    p, py = _project(tmp_path)
    env = CD._worktree_env(p, {"env": {}}, load_dispatch_config(p))
    assert env["PATH"].split(os.pathsep)[0] == str(py.parent)
    assert env["PATH"].split(os.pathsep)[1:] == os.environ.get("PATH", "").split(os.pathsep)
    assert env["VIRTUAL_ENV"] == str(py.parent.parent)


def test_the_session_env_undeclared_is_todays(tmp_path):
    p, _ = _project(tmp_path, declare=False)
    env = CD._worktree_env(p, {"env": {"X": "1"}}, load_dispatch_config(p))
    assert env == {"X": "1", "SELDON_PRIMARY_CHECKOUT": str(p)}
