"""
Shared fixtures for Seldon test suite.

Neo4j fixtures:
- FAIL (not skip) when Neo4j is unreachable or its credentials are unresolved, unless
  SELDON_TESTS_ALLOW_NEO4J_SKIP=1 excuses the tier explicitly. A skipped tier reported as a
  green suite was the defect (ai-readiness-kg/cc_tasks/2026-09-16_neo4j_fixture_fails_not_skips.md:
  an ordinary shell printed `1177 passed, 730 skipped, EXIT=0`).
- Credentials come from `seldon.config.resolve_neo4j_credentials`, the resolver production uses.
- Use a dedicated, per-process database to avoid polluting production databases
  and to keep concurrent pytest processes from wiping each other's fixtures.
  The name is resolved once in `tests/testdb.py` — see that module for the
  resolution order and the sweeper's safety argument.
- Clear the test database before each test that uses it.
"""
import os
import uuid
from pathlib import Path

import pytest

from seldon.config import NEO4J_CREDENTIAL_ENV_PAIRS, resolve_neo4j_credentials
from tests.testdb import (
    TEST_DATABASE,
    TEST_DATABASE_IS_EPHEMERAL,
    TEST_PROJECT_DATABASE,
    create_database,
    drop_database,
    sweep_stale_test_databases,
)

# ── Session identity isolation ────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_inherited_session_identity(monkeypatch):
    """Run every test with no session id inherited from the process that launched pytest.

    `get_current_session` reads `SELDON_SESSION_ID` and `CLAUDE_CODE_SESSION_ID` before any
    file (ai-readiness-kg/cc_tasks/2026-09-16_session_id_names_the_process.md decision 1), and
    a suite run from inside a Claude Code session inherits the second. Left in place, every
    file-based session test would read the runner's id instead of the file it wrote. A test
    that wants an environment id sets it itself.
    """
    import seldon.config as config
    for var in config.SESSION_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(config, "_process_session_id", None)


# ── Event store fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def project_dir(tmp_path):
    """Temp directory simulating a Seldon project root."""
    return tmp_path


@pytest.fixture
def sample_artifact_id():
    return str(uuid.uuid4())


# ── Neo4j fixtures ────────────────────────────────────────────────────────────

# TEST_DATABASE / TEST_PROJECT_DATABASE are imported from tests.testdb and
# re-exported here because most test modules already import them from conftest.
__all__ = ["TEST_DATABASE", "TEST_PROJECT_DATABASE"]


#: The only way to excuse the Neo4j tier. Nothing on the development machine sets it; an
#: environment with no Neo4j (CI) sets it on purpose, and the excuse is then on the record.
ALLOW_NEO4J_SKIP_ENV = "SELDON_TESTS_ALLOW_NEO4J_SKIP"


def _neo4j_creds():
    """Return ``(uri, username, password)``; either credential may be ``None`` (unresolved)."""
    username, password = resolve_neo4j_credentials()
    return os.getenv("NEO4J_URI", "bolt://localhost:7687"), username, password


def _neo4j_unavailable_reason():
    """Return why the Neo4j tier cannot run, or ``None`` when it can."""
    uri, username, password = _neo4j_creds()
    if username is None or password is None:
        pairs = " or ".join(f"{u}/{p}" for u, p in NEO4J_CREDENTIAL_ENV_PAIRS)
        missing = [n for n, v in (("username", username), ("password", password)) if v is None]
        return (f"Neo4j credentials unresolved ({' and '.join(missing)}): export {pairs}. "
                "No file is read for them (seldon/.env is loaded only by "
                "load_project_config, never by the test suite).")
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(uri, auth=(username, password))
        try:
            with driver.session() as session:
                session.run("RETURN 1")
        finally:
            driver.close()
    except Exception as exc:  # any connect/auth failure is the reason, reported verbatim
        return f"Neo4j not usable at {uri} as {username!r}: {type(exc).__name__}: {exc}"
    return None


@pytest.fixture(scope="session")
def neo4j_available():
    """Session-scoped gate for every Neo4j-backed test.

    Fails when the tier cannot run. Skips only when ``SELDON_TESTS_ALLOW_NEO4J_SKIP=1``: a
    skipped test is a distinct outcome so a reader can refuse to count it (TAP ``# SKIP``,
    JUnit ``<skipped/>``), and an excused test is excused explicitly, by someone, on the record.
    """
    reason = _neo4j_unavailable_reason()
    if reason is None:
        return True
    if os.getenv(ALLOW_NEO4J_SKIP_ENV) == "1":
        pytest.skip(f"{reason} (excused by {ALLOW_NEO4J_SKIP_ENV}=1)")
    pytest.fail(f"{reason} Set {ALLOW_NEO4J_SKIP_ENV}=1 only to excuse the Neo4j tier "
                "on purpose.", pytrace=False)


@pytest.fixture(scope="session")
def neo4j_driver(neo4j_available):
    """Session-scoped Neo4j driver bound to this process's test database.

    Creates the database at session start (after reclaiming orphans left by
    interrupted runs) and drops it at session teardown, so concurrent pytest
    processes never share graph state.

    Yields:
        A connected `neo4j.Driver`.
    """
    from neo4j import GraphDatabase
    uri, username, password = _neo4j_creds()
    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        # Self-healing: an interrupted run leaves its database behind. Reclaim
        # only those whose owning process is gone (see tests/testdb.py).
        sweep_stale_test_databases(driver)
        create_database(driver, TEST_DATABASE)
        yield driver
    finally:
        if TEST_DATABASE_IS_EPHEMERAL:
            # TEST_PROJECT_DATABASE is created on demand by the ontology tests;
            # drop_database is a no-op when it was never created.
            drop_database(driver, TEST_PROJECT_DATABASE)
            drop_database(driver, TEST_DATABASE)
        driver.close()


@pytest.fixture(autouse=False)
def clean_test_db(neo4j_driver):
    """
    Clear all nodes and relationships in the test database before each test.
    Use this fixture in tests that write to Neo4j.
    """
    with neo4j_driver.session(database=TEST_DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield


@pytest.fixture
def test_db_session(neo4j_driver, clean_test_db):
    """Provide a session to the test database, with the db pre-cleared."""
    with neo4j_driver.session(database=TEST_DATABASE) as session:
        yield session
