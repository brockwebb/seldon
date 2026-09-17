from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml


ONTOLOGY_MASTER_DB = "seldon-ontology"


def slugify(name: str) -> str:
    """
    Convert a project name to a valid slug.

    Rules:
    - Lowercase
    - Spaces and underscores become underscores
    - Hyphens are kept as hyphens
    - All other non-alphanumeric characters removed
    - Leading/trailing hyphens/underscores stripped

    Examples:
        "My Project" → "my_project"
        "pragmatics-paper" → "pragmatics-paper"
        "Test 123!" → "test_123"
    """
    slug = name.lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = slug.strip("-")
    return slug


def load_project_config(project_dir: Optional[Path] = None) -> dict:
    """
    Load seldon.yaml from the given directory (or cwd if not specified).
    Also loads .env from the same directory if present (override=False so
    shell env vars always win).
    Raises FileNotFoundError if seldon.yaml does not exist.
    """
    from dotenv import load_dotenv

    base = Path(project_dir) if project_dir else Path.cwd()

    # Load .env from project directory (no-op if file doesn't exist)
    load_dotenv(base / ".env", override=False)

    config_path = base / "seldon.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"No seldon.yaml found in {base}. "
            f"Run `seldon init <project-name>` to create one."
        )
    with open(config_path) as f:
        return yaml.safe_load(f)


#: Environment variable pairs that carry Neo4j credentials, in priority order. The first pair
#: is Seldon's own spelling; the second is the one the rest of this machine's projects export.
NEO4J_CREDENTIAL_ENV_PAIRS = (("NEO4J_USERNAME", "NEO4J_PASSWORD"), ("NEO4J_USER", "NEO4J_PASS"))


def resolve_neo4j_credentials() -> tuple[Optional[str], Optional[str]]:
    """Return ``(username, password)`` from the environment, ``None`` for whichever is unset.

    The one credential resolver: production (`get_neo4j_driver`) and the test suite's Neo4j
    fixture both call it, so the suite cannot read a different spelling from the code it tests
    (ai-readiness-kg/cc_tasks/2026-09-16_neo4j_fixture_fails_not_skips.md decision 1). Each
    field takes the first pair in ``NEO4J_CREDENTIAL_ENV_PAIRS`` that sets it. Callers decide
    what an unresolved field means; this function supplies no default.
    """
    username = next((os.getenv(u) for u, _ in NEO4J_CREDENTIAL_ENV_PAIRS if os.getenv(u)), None)
    password = next((os.getenv(p) for _, p in NEO4J_CREDENTIAL_ENV_PAIRS if os.getenv(p)), None)
    return username, password


def get_neo4j_driver(config: dict):
    """Create and return a Neo4j driver from project config + env variables.

    Suppresses GQL notification noise via driver-level config (5.7+).
    Falls back gracefully on older drivers.
    """
    from neo4j import GraphDatabase
    uri = config["neo4j"]["uri"]
    resolved_username, resolved_password = resolve_neo4j_credentials()
    username = resolved_username or "neo4j"
    password = resolved_password or "password"

    extra_kwargs = {}
    try:
        from neo4j import NotificationMinimumSeverity
        extra_kwargs["notifications_min_severity"] = NotificationMinimumSeverity.OFF
        extra_kwargs["warn_notification_severity"] = NotificationMinimumSeverity.OFF
    except ImportError:
        pass  # older driver, live with the noise

    return GraphDatabase.driver(uri, auth=(username, password), **extra_kwargs)


#: Environment variables that carry a session id set by the process that started this one, in
#: resolution order. `SELDON_SESSION_ID` is what the dispatcher gives the session it launches;
#: `CLAUDE_CODE_SESSION_ID` is what Claude Code sets in every Bash call of an interactive or
#: headless session. Prior art: a trace identity is created at the root process and propagated
#: to children through the environment (W3C Trace Context `traceparent`; OpenTelemetry context
#: propagation), never recovered from a mutable file.
SESSION_ENV_VARS = ("SELDON_SESSION_ID", "CLAUDE_CODE_SESSION_ID")

#: How long `.seldon/current_session.json` is evidence of a live session. A claim of a live
#: session older than one working day is not evidence of one: the file's authority is bounded
#: by age, as a lease or lockfile's is (Chubby, Burrows OSDI 2006). Set by
#: ai-readiness-kg/cc_tasks/2026-09-16_session_id_names_the_process.md decision 1(d), after one
#: project's file held the same id for 25 days and stamped 34,137 events with it.
SESSION_FILE_MAX_AGE = timedelta(hours=24)

#: The id of this process, when a long-lived process (the MCP server, the dispatcher) has bound
#: one with `bind_process_session`. Held in memory only, so it dies with the process.
_process_session_id: Optional[str] = None


def bind_process_session(session_id: Optional[str] = None) -> str:
    """Bind this process's session id, generating one if none is given; return the bound id.

    Idempotent: once bound, later calls without an argument return the same id. Called once
    at startup by processes that write events on behalf of callers who carry no environment
    id of their own (decision 1(c)).
    """
    global _process_session_id
    if session_id is not None:
        _process_session_id = session_id
    elif _process_session_id is None:
        _process_session_id = str(uuid.uuid4())
    return _process_session_id


def process_session_id() -> Optional[str]:
    """Return the id this process inherited or bound, or ``None`` when it has neither.

    Cases (a) to (c) of the resolution order: `SELDON_SESSION_ID`, then
    `CLAUDE_CODE_SESSION_ID`, then the in-memory id from `bind_process_session`. An empty
    environment value is not an id. No file is read.
    """
    for var in SESSION_ENV_VARS:
        value = os.environ.get(var)
        if value:
            return value
    return _process_session_id


def _session_file(project_dir: Optional[Path]) -> Path:
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".seldon" / "current_session.json"


def _is_fresh(data: Optional[dict], now: datetime) -> bool:
    """True when a session file's record is recent enough to stand for a live session.

    A record with no id, or no parseable `started_at`, is not evidence of anything.
    """
    if not data or not data.get("session_id"):
        return False
    try:
        started = datetime.fromisoformat(str(data["started_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return False
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return now - started <= SESSION_FILE_MAX_AGE


def _write_new_session(session_file: Path) -> str:
    session_file.parent.mkdir(exist_ok=True)
    session_id = str(uuid.uuid4())
    data = {
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with open(session_file, "w") as f:
        json.dump(data, f)
    return session_id


def start_session(project_dir: Optional[Path] = None) -> str:
    """Start a file session. A fresh one already on disk is kept; a stale one is replaced."""
    session_file = _session_file(project_dir)
    data = get_current_session_data(project_dir)
    if _is_fresh(data, datetime.now(timezone.utc)):
        return data["session_id"]
    return _write_new_session(session_file)


def get_current_session(project_dir: Optional[Path] = None) -> str:
    """Return the session id an event written now should carry.

    Resolution order (ai-readiness-kg/cc_tasks/2026-09-16_session_id_names_the_process.md
    decision 1): (a) `SELDON_SESSION_ID`; (b) `CLAUDE_CODE_SESSION_ID`; (c) this process's
    bound id; (d) `.seldon/current_session.json` if younger than `SESSION_FILE_MAX_AGE`;
    (e) otherwise a fresh id, written to that file so the rest of the working day agrees.
    """
    inherited = process_session_id()
    if inherited:
        return inherited
    return start_session(project_dir)


def get_current_session_data(project_dir: Optional[Path] = None) -> Optional[dict]:
    """Return the session file's record (session_id, started_at) as written, or None.

    Reads the file only, with no freshness bound: this is the record, not the resolution.
    Writers want `get_current_session`.
    """
    session_file = _session_file(project_dir)
    if not session_file.exists():
        return None
    with open(session_file) as f:
        return json.load(f)


def end_session(project_dir: Optional[Path] = None) -> None:
    """Delete the current session file. No-op if no session is active."""
    base = Path(project_dir) if project_dir else Path.cwd()
    session_file = base / ".seldon" / "current_session.json"
    if session_file.exists():
        session_file.unlink()


def get_sections_dir(config: dict, project_dir: Optional[Path] = None) -> Path:
    """Return the directory containing section/chapter files for this project.

    Resolution order:
    1. seldon.yaml paths.sections (explicit override)
    2. seldon.yaml paths.book (book-style projects like ai-workflow-design)
    3. Default: paper/sections/ (standard paper layout)

    Returns an absolute Path (resolved against project_dir).
    """
    base = Path(project_dir) if project_dir else Path.cwd()
    paths = config.get("paths", {})

    if paths.get("sections"):
        return base / paths["sections"]
    if paths.get("book"):
        return base / paths["book"]
    return base / "paper" / "sections"


def get_shared_ontology_source(config: dict) -> Optional[Path]:
    """Return resolved path to first vocabulary file from shared_ontology config, or None.

    Reads shared_ontology.source (base directory) and shared_ontology.vocabularies[0]
    (filename) from the project config and returns their joined path.
    """
    shared = config.get("shared_ontology")
    if not shared:
        return None
    source = shared.get("source", "")
    vocabs = shared.get("vocabularies", [])
    if not source or not vocabs:
        return None
    return Path(source) / vocabs[0]


def get_shared_ontology_sources(config: dict) -> list[Path]:
    """Return resolved paths to all vocabulary files from shared_ontology config.

    Reads shared_ontology.source (base directory) and shared_ontology.vocabularies
    (list of filenames) from the project config. Returns all paths that exist on disk.
    """
    shared = config.get("shared_ontology")
    if not shared:
        return []
    source = shared.get("source", "")
    vocabs = shared.get("vocabularies", [])
    if not source or not vocabs:
        return []
    return [Path(source) / v for v in vocabs]
