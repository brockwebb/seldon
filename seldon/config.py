from __future__ import annotations

import os
import re
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
    slug = re.sub(r"[\s]+", "_", slug)
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    slug = slug.strip("-_")
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
    """Create and return a Neo4j driver from project config + env variables."""
    from neo4j import GraphDatabase
    uri = config["neo4j"]["uri"]
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(username, password))
