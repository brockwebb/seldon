"""The Neo4j tier fails when it cannot run; it skips only when explicitly excused.

ai-readiness-kg/cc_tasks/2026-09-16_neo4j_fixture_fails_not_skips.md decisions 1 and 2. The
defect: the fixture read only NEO4J_USERNAME/NEO4J_PASSWORD while this machine exports
NEO4J_USER/NEO4J_PASS, and with neither set it skipped, so an ordinary shell reported
`1177 passed, 730 skipped, EXIT=0` and was quoted as green.

The gate is exercised in a subprocess because it is a session-scoped fixture: its outcome is
the outcome of a whole pytest run, which is what a RESULT quotes. These tests need no Neo4j:
every case either has no credentials or points at a port nothing listens on.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from seldon.config import NEO4J_CREDENTIAL_ENV_PAIRS, resolve_neo4j_credentials

REPO = Path(__file__).resolve().parent.parent
PROBE = "tests/neo4j_gate_probe.py"
CREDENTIAL_VARS = [name for pair in NEO4J_CREDENTIAL_ENV_PAIRS for name in pair]
#: Loopback port 1 (tcpmux) is not served on a development machine: connection refused, fast.
UNREACHABLE_URI = "bolt://127.0.0.1:1"


def _run_probe(**env_overrides: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in CREDENTIAL_VARS and k != "SELDON_TESTS_ALLOW_NEO4J_SKIP"}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "pytest", PROBE, "-p", "no:cacheprovider", "-rs", "-q"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=120)


def test_no_credentials_and_no_excuse_fails_and_names_both_pairs():
    """The negative control of decision 2: nothing exported, nothing excused → not green."""
    run = _run_probe()
    out = run.stdout + run.stderr
    assert run.returncode != 0, out
    assert "skipped" not in out.splitlines()[-1], out
    for name in CREDENTIAL_VARS + ["SELDON_TESTS_ALLOW_NEO4J_SKIP"]:
        assert name in out, (name, out)


def test_no_credentials_with_the_excuse_skips_on_the_record():
    run = _run_probe(SELDON_TESTS_ALLOW_NEO4J_SKIP="1")
    out = run.stdout + run.stderr
    assert run.returncode == 0, out
    assert "1 skipped" in out, out
    assert "excused by SELDON_TESTS_ALLOW_NEO4J_SKIP=1" in out, out


def test_an_excuse_other_than_1_does_not_excuse():
    run = _run_probe(SELDON_TESTS_ALLOW_NEO4J_SKIP="true")
    assert run.returncode != 0, run.stdout + run.stderr


@pytest.mark.parametrize("user_var,pass_var", NEO4J_CREDENTIAL_ENV_PAIRS)
def test_either_spelling_reaches_the_connect_and_an_unreachable_server_fails(user_var, pass_var):
    """Credentials in either spelling are resolved (the failure is a connect failure naming the
    URI, not an unresolved-credentials one), and an unreachable server fails rather than skips."""
    run = _run_probe(**{user_var: "u", pass_var: "p", "NEO4J_URI": UNREACHABLE_URI})
    out = run.stdout + run.stderr
    assert run.returncode != 0, out
    assert f"Neo4j not usable at {UNREACHABLE_URI}" in out, out
    assert "credentials unresolved" not in out, out


@pytest.mark.parametrize("user_var,pass_var", NEO4J_CREDENTIAL_ENV_PAIRS)
def test_the_resolver_reads_either_spelling(monkeypatch, user_var, pass_var):
    for name in CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(user_var, "u")
    monkeypatch.setenv(pass_var, "p")
    assert resolve_neo4j_credentials() == ("u", "p")


def test_the_resolver_supplies_no_default(monkeypatch):
    for name in CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)
    assert resolve_neo4j_credentials() == (None, None)
