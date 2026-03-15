"""
Shared fixtures for Seldon test suite.

Neo4j fixtures:
- Skip tests (not fail) if Neo4j is unreachable.
- Use dedicated `seldon_test` database to avoid polluting production databases.
- Clear the test database before each test that uses it.
"""
import os
import uuid
from pathlib import Path

import pytest

# ── Event store fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def project_dir(tmp_path):
    """Temp directory simulating a Seldon project root."""
    return tmp_path


@pytest.fixture
def sample_artifact_id():
    return str(uuid.uuid4())


# ── Neo4j fixtures ────────────────────────────────────────────────────────────

TEST_DATABASE = "seldon-test"


def _neo4j_creds():
    return (
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        os.getenv("NEO4J_USERNAME", "neo4j"),
        os.getenv("NEO4J_PASSWORD", "password"),
    )


def _neo4j_reachable() -> bool:
    """Return True if Neo4j is reachable, False otherwise."""
    try:
        from neo4j import GraphDatabase
        uri, username, password = _neo4j_creds()
        driver = GraphDatabase.driver(uri, auth=(username, password))
        with driver.session() as session:
            session.run("RETURN 1")
        driver.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def neo4j_available():
    """Session-scoped check. Skip entire test session if Neo4j is not running."""
    if not _neo4j_reachable():
        pytest.skip("Neo4j not reachable — skipping Neo4j tests")
    return True


@pytest.fixture(scope="session")
def neo4j_driver(neo4j_available):
    """Session-scoped Neo4j driver connected to the test instance."""
    from neo4j import GraphDatabase
    uri, username, password = _neo4j_creds()
    driver = GraphDatabase.driver(uri, auth=(username, password))

    # Ensure seldon_test database exists
    with driver.session(database="system") as session:
        session.run(f"CREATE DATABASE `{TEST_DATABASE}` IF NOT EXISTS")

    yield driver
    driver.close()


@pytest.fixture(autouse=False)
def clean_test_db(neo4j_driver):
    """
    Clear all nodes and relationships in seldon_test before each test.
    Use this fixture in tests that write to Neo4j.
    """
    with neo4j_driver.session(database=TEST_DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield


@pytest.fixture
def test_db_session(neo4j_driver, clean_test_db):
    """Provide a session to seldon_test, with the db pre-cleared."""
    with neo4j_driver.session(database=TEST_DATABASE) as session:
        yield session
