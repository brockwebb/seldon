"""Tests for scripts/mcp_launch.sh (SEC-001R).

The launcher starts an MCP server with its secrets read from a directory's
`.env` instead of from an inline `env` block in claude_desktop_config.json.
It parses dotenv format literally (python-dotenv semantics, no shell
evaluation) because the operator's Neo4j password holds an unquoted `'`,
which `set -a; . .env` silently drops.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

LAUNCHER = Path(__file__).parent.parent / "scripts" / "mcp_launch.sh"

# Prints the child's parent pid and its environment as JSON, so a test can
# check both what was exported and that the launcher exec'd (no extra process).
DUMP_ENV = [sys.executable, "-c",
            "import json, os; print(json.dumps({'ppid': os.getppid(), 'env': dict(os.environ)}))"]

ENV_TEXT = """\
# comment line

export EXPORTED_KEY=exported
PLAIN=plain-value
QUOTE_INSIDE=ab'cd'ef
HASH_INSIDE=ab#cd
TRAILING_COMMENT=value  # a comment
SINGLE='single # not a comment'
DOUBLE="double value"
EMPTY=
SPACED = spaced
CRLF=crlf\r
PRESET=from-dotenv
DUP=first
DUP=second
"""


def _run(tmp_path, *args, env=None):
    base = {"PATH": os.environ["PATH"]}
    base.update(env or {})
    return subprocess.run([str(LAUNCHER), str(tmp_path), *args], capture_output=True,
                          text=True, env=base)


def _write_env(tmp_path, text=ENV_TEXT):
    (tmp_path / ".env").write_text(text, newline="")


def test_exports_keys_and_execs(tmp_path):
    _write_env(tmp_path)
    r = _run(tmp_path, "--", *DUMP_ENV)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    # exec, not fork: the child's parent is this test process, not a shell.
    assert out["ppid"] == os.getpid()
    env = out["env"]
    assert env["EXPORTED_KEY"] == "exported"
    assert env["PLAIN"] == "plain-value"
    assert env["QUOTE_INSIDE"] == "ab'cd'ef"
    assert env["HASH_INSIDE"] == "ab#cd"
    assert env["TRAILING_COMMENT"] == "value"
    assert env["SINGLE"] == "single # not a comment"
    assert env["DOUBLE"] == "double value"
    assert env["EMPTY"] == ""
    assert env["SPACED"] == "spaced"
    assert env["CRLF"] == "crlf"
    assert env["DUP"] == "second"


def test_matches_python_dotenv(tmp_path):
    """The launcher's parse equals python-dotenv's, the parser the repos already use."""
    _write_env(tmp_path)
    expected = dotenv_values(tmp_path / ".env", interpolate=False)
    r = _run(tmp_path, "--", *DUMP_ENV)
    assert r.returncode == 0, r.stderr
    env = json.loads(r.stdout)["env"]
    for key, value in expected.items():
        assert env[key] == (value or ""), key


def test_existing_environment_wins(tmp_path):
    """Config `env` values beat the .env file (python-dotenv override=False)."""
    _write_env(tmp_path)
    r = _run(tmp_path, "--", *DUMP_ENV, env={"PRESET": "from-config"})
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["env"]["PRESET"] == "from-config"


def test_only_limits_exported_keys(tmp_path):
    _write_env(tmp_path)
    r = _run(tmp_path, "--only", "PLAIN,QUOTE_INSIDE", "--", *DUMP_ENV)
    assert r.returncode == 0, r.stderr
    env = json.loads(r.stdout)["env"]
    assert env["PLAIN"] == "plain-value"
    assert env["QUOTE_INSIDE"] == "ab'cd'ef"
    assert "HASH_INSIDE" not in env and "EXPORTED_KEY" not in env


def test_only_key_missing_fails_loud(tmp_path):
    _write_env(tmp_path)
    r = _run(tmp_path, "--only", "PLAIN,NOT_THERE", "--", *DUMP_ENV)
    assert r.returncode == 2
    assert "NOT_THERE" in r.stderr
    assert r.stdout == ""


def test_only_key_satisfied_by_environment(tmp_path):
    _write_env(tmp_path)
    r = _run(tmp_path, "--only", "NOT_THERE", "--", *DUMP_ENV, env={"NOT_THERE": "x"})
    assert r.returncode == 0, r.stderr


def test_missing_env_file_fails_loud(tmp_path):
    r = _run(tmp_path, "--", *DUMP_ENV)
    assert r.returncode == 2
    assert ".env" in r.stderr


def test_bad_line_fails_without_printing_value(tmp_path):
    _write_env(tmp_path, "GOOD=1\nthis-line-holds-s3cret-material\n")
    r = _run(tmp_path, "--", *DUMP_ENV)
    assert r.returncode == 2
    assert ":2:" in r.stderr
    assert "s3cret" not in r.stderr


def test_interpolation_refused(tmp_path):
    """python-dotenv would expand ${VAR}; the launcher refuses rather than diverge."""
    _write_env(tmp_path, "A=${HOME}/x\n")
    r = _run(tmp_path, "--", *DUMP_ENV)
    assert r.returncode == 2
    assert "A" in r.stderr


def test_no_command_fails(tmp_path):
    _write_env(tmp_path)
    r = _run(tmp_path, "--")
    assert r.returncode == 2
