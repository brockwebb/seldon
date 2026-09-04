"""Single source of truth for the Neo4j database the test suite writes to.

Every Neo4j-backed test in this suite calls ``MATCH (n) DETACH DELETE n`` before
it runs (``conftest.clean_test_db``). When all tests share one database name,
two concurrent ``pytest`` processes delete each other's fixture data mid-test.
That was observed on 2026-09-03 (defect sweep RESULT §9.1): four lanes running
``pytest`` at once produced ``assert 10 == 4`` failures that passed 15/15 on an
immediate serial re-run.

The fix is to give every pytest *process* its own database.

Resolution order (first match wins)
-----------------------------------
1. ``SELDON_TEST_DATABASE`` — used **verbatim**. An explicit operator override
   for environments that provision one dedicated database (CI, a container that
   is torn down wholesale). Never swept, never dropped by the suite.
2. ``PYTEST_XDIST_WORKER`` set → ``<base>-p<pid>-<worker>``. The PID, not the
   worker id, is what makes this unique: ``gw0`` exists in *every* concurrent
   xdist run, so a worker-only suffix would reintroduce the exact collision this
   module exists to prevent. The worker id is appended purely for readability
   when reading ``SHOW DATABASES`` output.
3. Otherwise → ``<base>-p<pid>``. One pytest process is one PID for the whole
   session, which is precisely the concurrency case that broke.

Cases 2 and 3 are *ephemeral*: created at session start and dropped at session
teardown by ``conftest.neo4j_driver``.

Sweeper safety
--------------
An interrupted run (Ctrl-C, crash, OOM) leaves an orphan database behind, so
``sweep_stale_test_databases`` drops ephemeral databases whose owning process is
gone. Dropping a database destroys data irrecoverably, so the match is
deliberately narrow — see ``stale_pid`` for the full argument. In short, a name
is only ever a drop candidate when it matches ``EPHEMERAL_RE`` (which requires
the literal ``seldon-test-p`` followed by digits), is not the base name, is not
the operator override, is not this process's own database, and names a PID that
is no longer alive.
"""
from __future__ import annotations

import os
import re
from typing import Iterable, Optional

# Base name kept for backwards compatibility with pre-existing operator habits
# and with `SELDON_TEST_DATABASE=seldon-test` as an explicit serial-run override.
BASE_DATABASE = "seldon-test"

#: Environment variable that overrides the resolved name verbatim.
OVERRIDE_ENV_VAR = "SELDON_TEST_DATABASE"

#: Environment variable pytest-xdist sets in each worker subprocess.
XDIST_ENV_VAR = "PYTEST_XDIST_WORKER"

#: Matches only names this module could have generated for a *process*:
#: ``seldon-test-p<digits>`` plus zero or more alphanumeric ``-`` suffixes
#: (the xdist worker id, and derived databases such as ``-project``).
#: Anchored at both ends. Deliberately does NOT match ``seldon-test`` itself,
#: ``seldon-test-project``, or any ``seldon-<project-slug>`` database.
EPHEMERAL_RE = re.compile(r"^" + re.escape(BASE_DATABASE) + r"-p(\d+)(?:-[A-Za-z0-9]+)*$")


def resolve_database(env: Optional[dict] = None, pid: Optional[int] = None) -> str:
    """Resolve the test database name for this process.

    Args:
        env: Mapping to read environment variables from. Defaults to ``os.environ``.
        pid: Process id to embed. Defaults to ``os.getpid()``.

    Returns:
        The database name. See the module docstring for the resolution order.

    Raises:
        ValueError: If ``SELDON_TEST_DATABASE`` is set but empty or whitespace —
            an empty override is always an operator mistake, and silently
            falling through to a generated name would hide it.
    """
    env = os.environ if env is None else env
    pid = os.getpid() if pid is None else pid

    override = env.get(OVERRIDE_ENV_VAR)
    if override is not None:
        stripped = override.strip()
        if not stripped:
            raise ValueError(
                f"{OVERRIDE_ENV_VAR} is set but empty. Unset it to use a "
                f"per-process database, or set it to a real database name."
            )
        return stripped

    worker = (env.get(XDIST_ENV_VAR) or "").strip()
    if worker:
        # Sanitise: Neo4j database names allow only alphanumerics, dots and
        # dashes. xdist ids are `gw<n>` / `master`, but do not trust that.
        safe_worker = re.sub(r"[^A-Za-z0-9]", "", worker)
        if safe_worker:
            return f"{BASE_DATABASE}-p{pid}-{safe_worker}"

    return f"{BASE_DATABASE}-p{pid}"


def is_ephemeral(name: str, env: Optional[dict] = None) -> bool:
    """Return True if ``name`` is a database this module owns and may drop.

    Args:
        name: Database name as reported by ``SHOW DATABASES``.
        env: Mapping to read environment variables from. Defaults to ``os.environ``.

    Returns:
        True when the name matches the generated per-process pattern and is not
        the operator override. False for the base name, for real project
        databases (``seldon-<project-slug>``), and for anything else.
    """
    env = os.environ if env is None else env
    if not EPHEMERAL_RE.match(name):
        return False
    override = (env.get(OVERRIDE_ENV_VAR) or "").strip()
    if override and name == override:
        return False
    return True


def stale_pid(name: str, env: Optional[dict] = None, self_pid: Optional[int] = None) -> Optional[int]:
    """Return the owning PID if ``name`` is an *abandoned* ephemeral database.

    A name is stale only when every one of these holds:

    1. It matches :data:`EPHEMERAL_RE` — literally ``seldon-test-p`` + digits,
       anchored. ``seldon-test``, ``seldon-test-project`` and every real
       project database ``seldon-<slug>`` fail this.
    2. It is not the ``SELDON_TEST_DATABASE`` override.
    3. The embedded PID is not this process's own PID.
    4. The embedded PID names no live process.

    Condition 4 fails *safe*: if the PID was recycled and now belongs to some
    unrelated live process, the database is left alone (a harmless orphan)
    rather than dropped out from under a running test session.

    Args:
        name: Database name as reported by ``SHOW DATABASES``.
        env: Mapping to read environment variables from. Defaults to ``os.environ``.
        self_pid: This process's PID. Defaults to ``os.getpid()``.

    Returns:
        The abandoned owner PID, or None if the database must not be dropped.
    """
    env = os.environ if env is None else env
    self_pid = os.getpid() if self_pid is None else self_pid

    if not is_ephemeral(name, env=env):
        return None
    match = EPHEMERAL_RE.match(name)
    assert match is not None  # guaranteed by is_ephemeral
    pid = int(match.group(1))
    if pid == self_pid or pid <= 0:
        return None
    if _pid_alive(pid):
        return None
    return pid


def _pid_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` currently exists.

    Args:
        pid: Process id to probe.

    Returns:
        True if the process exists (including when it is owned by another user,
        which surfaces as PermissionError). False only when the OS reports that
        no such process exists.

    Raises:
        OSError: For any errno other than ESRCH/EPERM — an unexpected failure
            must not be silently read as "dead", because that would authorise a
            destructive drop.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stale_databases(names: Iterable[str], env: Optional[dict] = None,
                    self_pid: Optional[int] = None) -> list[str]:
    """Filter ``names`` down to the abandoned ephemeral test databases.

    Args:
        names: Database names, e.g. from ``SHOW DATABASES YIELD name``.
        env: Mapping to read environment variables from. Defaults to ``os.environ``.
        self_pid: This process's PID. Defaults to ``os.getpid()``.

    Returns:
        The subset of ``names`` that are safe to drop, in input order.
    """
    return [n for n in names if stale_pid(n, env=env, self_pid=self_pid) is not None]


#: The database every Neo4j-backed test in this suite reads and writes.
TEST_DATABASE = resolve_database()

#: Secondary database used by the ontology sync tests, which need a *pair*
#: (master + project replica). Derived from TEST_DATABASE so it inherits the
#: same per-process isolation and the same sweeper coverage.
TEST_PROJECT_DATABASE = f"{TEST_DATABASE}-project"

#: True when the suite owns TEST_DATABASE and must drop it at session teardown.
TEST_DATABASE_IS_EPHEMERAL = is_ephemeral(TEST_DATABASE)


def create_database(driver, name: str) -> None:
    """Create ``name`` if it does not exist, waiting for it to come online.

    Args:
        driver: A connected ``neo4j.Driver``.
        name: Database to create.

    Returns:
        None.

    Raises:
        neo4j.exceptions.Neo4jError: If the CREATE fails.
    """
    with driver.session(database="system") as session:
        # WAIT: CREATE/DROP DATABASE are asynchronous by default, and a create
        # that has not completed produces confusing DatabaseNotFound errors in
        # the first test that runs.
        session.run(f"CREATE DATABASE `{name}` IF NOT EXISTS WAIT")


def drop_database(driver, name: str) -> None:
    """Drop ``name`` if it exists, waiting for the drop to complete.

    Refuses to drop anything that is not an ephemeral per-process test database,
    so a caller mistake cannot destroy a real project database.

    Args:
        driver: A connected ``neo4j.Driver``.
        name: Database to drop.

    Returns:
        None.

    Raises:
        ValueError: If ``name`` is not an ephemeral test database.
        neo4j.exceptions.Neo4jError: If the DROP fails for a reason other than
            the database having already been removed concurrently.
    """
    if not is_ephemeral(name):
        raise ValueError(
            f"refusing to drop {name!r}: not an ephemeral per-process test "
            f"database (pattern {EPHEMERAL_RE.pattern})"
        )
    from neo4j.exceptions import Neo4jError

    with driver.session(database="system") as session:
        try:
            session.run(f"DROP DATABASE `{name}` IF EXISTS WAIT")
        except Neo4jError:
            # A concurrent session may have swept the same orphan between our
            # listing and this drop. That is benign — but only if the database
            # really is gone. Anything else is a real failure and must surface.
            if name in existing_databases(driver):
                raise


def existing_databases(driver) -> list[str]:
    """List database names known to the server.

    Args:
        driver: A connected ``neo4j.Driver``.

    Returns:
        Database names, as reported by ``SHOW DATABASES``.

    Raises:
        neo4j.exceptions.Neo4jError: If the query fails.
    """
    with driver.session(database="system") as session:
        return [record["name"] for record in session.run("SHOW DATABASES YIELD name")]


def sweep_stale_test_databases(driver) -> list[str]:
    """Drop per-process test databases whose owning process is gone.

    An interrupted run (Ctrl-C, crash) leaves its database behind. This is the
    self-healing step: called at session start, it reclaims those orphans.

    Args:
        driver: A connected ``neo4j.Driver``.

    Returns:
        The names actually dropped, so a caller can report them.

    Raises:
        neo4j.exceptions.Neo4jError: If listing or dropping fails.
    """
    stale = stale_databases(existing_databases(driver))
    for name in stale:
        drop_database(driver, name)
    return stale
