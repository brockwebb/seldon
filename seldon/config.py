from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


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
    Raises FileNotFoundError if seldon.yaml does not exist.
    """
    base = Path(project_dir) if project_dir else Path.cwd()
    config_path = base / "seldon.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"No seldon.yaml found in {base}. "
            f"Run `seldon init <project-name>` to create one."
        )
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_neo4j_driver(config: dict):
    """Create and return a Neo4j driver from project config + env variables.

    Suppresses GQL notification noise via driver-level config (5.7+).
    Falls back gracefully on older drivers.
    """
    from neo4j import GraphDatabase
    uri = config["neo4j"]["uri"]
    username = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER") or "neo4j"
    password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS") or "password"

    extra_kwargs = {}
    try:
        from neo4j import NotificationMinimumSeverity
        extra_kwargs["notifications_min_severity"] = NotificationMinimumSeverity.OFF
        extra_kwargs["warn_notification_severity"] = NotificationMinimumSeverity.OFF
    except ImportError:
        pass  # older driver, live with the noise

    return GraphDatabase.driver(uri, auth=(username, password), **extra_kwargs)


def start_session(project_dir: Optional[Path] = None) -> str:
    """Start a session. If one already exists, return its ID without overwriting."""
    base = Path(project_dir) if project_dir else Path.cwd()
    seldon_dir = base / ".seldon"
    seldon_dir.mkdir(exist_ok=True)
    session_file = seldon_dir / "current_session.json"

    # If session already active, return existing
    if session_file.exists():
        with open(session_file) as f:
            data = json.load(f)
        if "session_id" in data:
            return data["session_id"]

    # Otherwise create new
    session_id = str(uuid.uuid4())
    data = {
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with open(session_file, "w") as f:
        json.dump(data, f)
    return session_id


def get_current_session(project_dir: Optional[Path] = None) -> Optional[str]:
    """Return the active session_id, or None if no session file exists."""
    data = get_current_session_data(project_dir)
    return data["session_id"] if data else None


def get_current_session_data(project_dir: Optional[Path] = None) -> Optional[dict]:
    """Return full session dict (session_id, started_at), or None if no session."""
    base = Path(project_dir) if project_dir else Path.cwd()
    session_file = base / ".seldon" / "current_session.json"
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
