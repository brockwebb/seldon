"""Tests for per-process Neo4j test-database naming and the orphan sweeper.

These guard the fix for the 2026-09-03 defect: a single shared `seldon-test`
database that `clean_test_db` wipes before every test, so concurrent pytest
processes destroy each other's fixtures.

The sweeper drops databases, which is irreversible, so the match pattern gets
adversarial coverage here — real project databases must never be candidates.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tests import testdb
from tests.testdb import (
    BASE_DATABASE,
    OVERRIDE_ENV_VAR,
    TEST_DATABASE,
    TEST_PROJECT_DATABASE,
    XDIST_ENV_VAR,
    drop_database,
    is_ephemeral,
    resolve_database,
    stale_databases,
    stale_pid,
)


def _dead_pid() -> int:
    """Return the PID of a process that has exited and been reaped.

    Returns:
        A PID that names no live process at the moment of return.
    """
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


# ── Resolution order ─────────────────────────────────────────────────────────

def test_default_name_is_process_specific():
    """With no env override, the name embeds this process's PID."""
    name = resolve_database(env={})
    assert name == f"{BASE_DATABASE}-p{os.getpid()}"
    assert str(os.getpid()) in name


def test_default_name_differs_between_processes():
    """Two different PIDs resolve to two different databases."""
    a = resolve_database(env={}, pid=111)
    b = resolve_database(env={}, pid=222)
    assert a != b
    assert a == f"{BASE_DATABASE}-p111"


def test_live_test_database_is_process_specific():
    """The module-level constant the suite actually uses is per-process."""
    if os.environ.get(OVERRIDE_ENV_VAR):
        pytest.skip(f"{OVERRIDE_ENV_VAR} override in effect")
    assert TEST_DATABASE != BASE_DATABASE
    assert TEST_DATABASE.startswith(f"{BASE_DATABASE}-p{os.getpid()}")
    assert TEST_PROJECT_DATABASE == f"{TEST_DATABASE}-project"


def test_override_is_used_verbatim():
    """SELDON_TEST_DATABASE wins over the PID and xdist paths."""
    env = {OVERRIDE_ENV_VAR: "ci-dedicated-db", XDIST_ENV_VAR: "gw3"}
    assert resolve_database(env=env, pid=555) == "ci-dedicated-db"


def test_override_is_stripped():
    """Surrounding whitespace in the override is not carried into the name."""
    assert resolve_database(env={OVERRIDE_ENV_VAR: "  ci-db \n"}) == "ci-db"


def test_empty_override_fails_loud():
    """An empty override is an operator mistake, not a silent fallback."""
    with pytest.raises(ValueError, match=OVERRIDE_ENV_VAR):
        resolve_database(env={OVERRIDE_ENV_VAR: "   "})


def test_xdist_worker_name_includes_pid_not_only_worker():
    """gw0 exists in every concurrent xdist run, so the PID must be present."""
    name = resolve_database(env={XDIST_ENV_VAR: "gw0"}, pid=777)
    assert name == f"{BASE_DATABASE}-p777-gw0"
    other = resolve_database(env={XDIST_ENV_VAR: "gw0"}, pid=888)
    assert name != other


def test_xdist_worker_id_is_sanitised():
    """Characters Neo4j rejects in a database name are stripped from the worker id."""
    name = resolve_database(env={XDIST_ENV_VAR: "gw_0/x"}, pid=1)
    assert name == f"{BASE_DATABASE}-p1-gw0x"


def test_blank_xdist_worker_falls_through_to_pid():
    """An empty worker id is treated as absent, not as an empty suffix."""
    assert resolve_database(env={XDIST_ENV_VAR: "  "}, pid=9) == f"{BASE_DATABASE}-p9"


# ── Sweeper match pattern (destructive — must be strict) ─────────────────────

EPHEMERAL_NAMES = [
    "seldon-test-p1",
    "seldon-test-p12345",
    "seldon-test-p12345-gw0",
    "seldon-test-p12345-project",
    "seldon-test-p12345-gw0-project",
]

#: Names the sweeper must NEVER touch. Includes the shared base database, the
#: pre-existing ontology pair, real project databases (`seldon-<slug>`), Neo4j's
#: own databases, and near-misses on the pattern.
PROTECTED_NAMES = [
    "seldon-test",
    "seldon-test-project",
    "seldon-test-master",
    "seldon-seldon-self",
    "seldon-leibniz-pi",
    "seldon-ontology",
    "seldon-sas-graph-code-conversion",
    "seldon-production",
    "neo4j",
    "system",
    "",
    "seldon-testp123",          # no dash before p
    "seldon-test-p",            # no digits
    "seldon-test-px1",          # non-digit after p
    "seldon-test-p1x",          # trailing junk not dash-separated
    "seldon-test-p1-",          # trailing dash, empty suffix
    "seldon-test-p1-gw0-",      # trailing dash
    "xseldon-test-p1",          # not anchored at start
    "seldon-test-p1x2",         # not anchored at end
    "seldon-test-1",            # missing the p marker
    "SELDON-TEST-P1",           # case differs
]


@pytest.mark.parametrize("name", EPHEMERAL_NAMES)
def test_ephemeral_names_are_recognised(name):
    assert is_ephemeral(name, env={}) is True


@pytest.mark.parametrize("name", PROTECTED_NAMES)
def test_protected_names_are_never_ephemeral(name):
    assert is_ephemeral(name, env={}) is False


@pytest.mark.parametrize("name", PROTECTED_NAMES)
def test_protected_names_are_never_stale(name):
    assert stale_pid(name, env={}, self_pid=os.getpid()) is None


def test_override_database_is_never_swept():
    """An operator-provisioned database is off limits even if it matches the pattern."""
    env = {OVERRIDE_ENV_VAR: "seldon-test-p4242"}
    assert is_ephemeral("seldon-test-p4242", env=env) is False
    assert stale_pid("seldon-test-p4242", env=env, self_pid=os.getpid()) is None


# ── Liveness ─────────────────────────────────────────────────────────────────

def test_own_database_is_not_stale():
    """A session must never sweep the database it is using right now."""
    assert stale_pid(f"{BASE_DATABASE}-p{os.getpid()}", env={}) is None
    assert stale_pid(TEST_PROJECT_DATABASE, env={}) is None


def test_live_process_database_is_not_stale():
    """A database owned by another *running* process is left alone."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert stale_pid(f"{BASE_DATABASE}-p{proc.pid}", env={}, self_pid=os.getpid()) is None
    finally:
        proc.kill()
        proc.wait()


def test_dead_process_database_is_stale():
    """An orphan left by a crashed run is reclaimable."""
    pid = _dead_pid()
    assert stale_pid(f"{BASE_DATABASE}-p{pid}", env={}, self_pid=os.getpid()) == pid


def test_stale_databases_filters_a_realistic_listing():
    """Given a full SHOW DATABASES listing, only the orphan is selected."""
    dead = _dead_pid()
    names = [
        "system",
        "neo4j",
        "seldon-seldon-self",
        "seldon-leibniz-pi",
        "seldon-test",
        "seldon-test-project",
        f"{BASE_DATABASE}-p{os.getpid()}",
        f"{BASE_DATABASE}-p{dead}",
        f"{BASE_DATABASE}-p{dead}-project",
    ]
    assert stale_databases(names, env={}, self_pid=os.getpid()) == [
        f"{BASE_DATABASE}-p{dead}",
        f"{BASE_DATABASE}-p{dead}-project",
    ]


# ── Drop guard ───────────────────────────────────────────────────────────────

class _ExplodingDriver:
    """Driver stand-in that fails the test if any session is opened."""

    def session(self, **kwargs):
        raise AssertionError("drop_database opened a session for a protected name")


@pytest.mark.parametrize("name", ["seldon-test", "seldon-seldon-self", "neo4j", "system"])
def test_drop_database_refuses_protected_names(name):
    """The drop helper refuses non-ephemeral names before touching Neo4j."""
    with pytest.raises(ValueError, match="refusing to drop"):
        drop_database(_ExplodingDriver(), name)


# ── Wiring ───────────────────────────────────────────────────────────────────

def test_conftest_uses_the_shared_constant():
    """conftest must not reintroduce its own database literal."""
    from tests import conftest

    assert conftest.TEST_DATABASE is testdb.TEST_DATABASE


def test_no_hardcoded_database_literal_in_test_modules():
    """The literal name lives in exactly one module."""
    import pathlib

    tests_dir = pathlib.Path(__file__).parent
    offenders = []
    for path in sorted(tests_dir.glob("test_*.py")):
        if path.name == "test_testdb.py":
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if f'"{BASE_DATABASE}"' in line or f"'{BASE_DATABASE}'" in line:
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert offenders == [], "hardcoded test database name:\n" + "\n".join(offenders)
