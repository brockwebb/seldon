"""Seldon MCP server — tools for Desktop/AI session housekeeping."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("seldon")


# ---------------------------------------------------------------------------
# Shared project resolution
# ---------------------------------------------------------------------------

def _resolve_project(project_dir: str):
    """Resolve config, driver, database, and domain_config from project_dir.

    Falls back to SELDON_DEFAULT_PROJECT env var when project_dir is '.'.

    Returns:
        (config, driver, database, domain_config, resolved_project_dir)
    """
    from seldon.config import load_project_config, get_neo4j_driver
    from seldon.domain.loader import load_domain_config

    if project_dir == ".":
        env_path = os.environ.get("SELDON_DEFAULT_PROJECT")
        if env_path and (Path(env_path) / "seldon.yaml").exists():
            project_dir = env_path

    p = Path(project_dir)
    config = load_project_config(p)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent / "domain" / f"{domain_name}.yaml"
    domain_config = load_domain_config(domain_yaml)

    return config, driver, database, domain_config, str(p)


def _resolve_artifact_id(driver, database: str, id_prefix: str) -> str | None:
    """Return full artifact_id for a UUID or prefix. Returns None if not found or ambiguous."""
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (a:Artifact) WHERE a.artifact_id STARTS WITH $prefix "
            "RETURN a.artifact_id AS id",
            prefix=id_prefix,
        ).data()
    if len(records) == 1:
        return records[0]["id"]
    return None


# ---------------------------------------------------------------------------
# seldon_go (existing)
# ---------------------------------------------------------------------------

@mcp.tool()
def seldon_go(project_dir: str = ".", brief: bool = False) -> str:
    """Orient to a Seldon-managed project. Returns engineering standards,
    project context, latest handoff, current state, and available commands.

    Args:
        project_dir: Path to the project root (default: current directory).
            When left as ".", the SELDON_DEFAULT_PROJECT environment variable
            is used if set and contains a valid seldon.yaml.
        brief: If True, skip system CLAUDE.md for a shorter response
    """
    from seldon.commands.go import assemble_go_context
    return assemble_go_context(project_dir=project_dir, brief=brief)


# ---------------------------------------------------------------------------
# Task tools
# ---------------------------------------------------------------------------

@mcp.tool()
def seldon_task_create(
    description: str,
    project_dir: str = ".",
    blocks: str = "",
) -> str:
    """Create a ResearchTask in the project graph.

    Args:
        description: Task description (what needs to be done)
        project_dir: Path to project root (default: current directory or SELDON_DEFAULT_PROJECT)
        blocks: Optional artifact ID (full or prefix) that this task blocks
    """
    from seldon.core.artifacts import create_artifact, create_link
    from seldon.core.graph import get_artifact

    config, driver, database, domain_config, project_dir = _resolve_project(project_dir)
    p = Path(project_dir)

    try:
        artifact_id = create_artifact(
            project_dir=p, driver=driver, database=database,
            domain_config=domain_config, artifact_type="ResearchTask",
            properties={"description": description},
            actor="desktop", authority="accepted",
        )

        if blocks:
            target_id = _resolve_artifact_id(driver, database, blocks)
            if target_id:
                create_link(
                    project_dir=p, driver=driver, database=database,
                    domain_config=domain_config,
                    from_id=artifact_id, to_id=target_id, rel_type="blocks",
                    actor="desktop", authority="accepted",
                )
            else:
                return (
                    f"Created ResearchTask: {artifact_id[:8]}...\n"
                    f"  description: {description}\n"
                    f"  state: proposed\n"
                    f"Warning: could not resolve blocks target '{blocks}' — link not created"
                )

        return (
            f"Created ResearchTask: {artifact_id[:8]}...\n"
            f"  description: {description}\n"
            f"  state: proposed"
        )
    finally:
        driver.close()


@mcp.tool()
def seldon_task_update(
    task_id: str,
    state: str,
    project_dir: str = ".",
    note: str = "",
) -> str:
    """Update a ResearchTask's state.

    Args:
        task_id: Artifact ID (full UUID or prefix)
        state: New state (accepted, in_progress, completed, verified, blocked)
        project_dir: Path to project root
        note: Optional note (currently logged but not stored separately)
    """
    from seldon.core.artifacts import transition_state
    from seldon.core.graph import get_artifact

    config, driver, database, domain_config, project_dir = _resolve_project(project_dir)
    p = Path(project_dir)

    try:
        full_id = _resolve_artifact_id(driver, database, task_id)
        if full_id is None:
            return f"Error: artifact '{task_id}' not found or ambiguous."

        with driver.session(database=database) as session:
            node = get_artifact(session, full_id)
        if node is None:
            return f"Error: artifact '{task_id}' not found."

        current_state = node.get("state", "")
        artifact_type = node.get("artifact_type", "ResearchTask")

        transition_state(
            project_dir=p, driver=driver, database=database,
            domain_config=domain_config,
            artifact_id=full_id, artifact_type=artifact_type,
            current_state=current_state, new_state=state,
            actor="desktop", authority="accepted",
        )

        return (
            f"Updated: {full_id[:8]}...\n"
            f"  {current_state} → {state}"
            + (f"\n  note: {note}" if note else "")
        )
    finally:
        driver.close()


@mcp.tool()
def seldon_task_list(
    project_dir: str = ".",
    state_filter: str = "open",
    brief: bool = True,
) -> str:
    """List ResearchTasks filtered by state.

    Args:
        project_dir: Path to project root
        state_filter: 'open' (proposed/accepted/in_progress/blocked),
                      'completed', 'all', or a specific state name
        brief: If True, one-line summaries. If False, full details including IDs.
    """
    _OPEN_STATES = ["proposed", "accepted", "in_progress", "blocked"]

    config, driver, database, domain_config, project_dir = _resolve_project(project_dir)

    if state_filter == "open":
        where = "WHERE t.state IN ['proposed', 'accepted', 'in_progress', 'blocked']"
    elif state_filter == "all":
        where = ""
    elif state_filter == "completed":
        where = "WHERE t.state = 'completed'"
    else:
        where = f"WHERE t.state = '{state_filter}'"

    try:
        with driver.session(database=database) as session:
            records = session.run(
                f"MATCH (t:Artifact:ResearchTask) {where} "
                "RETURN t ORDER BY t.created_at"
            ).data()
    finally:
        driver.close()

    if not records:
        return f"No ResearchTasks found (filter: {state_filter})"

    lines = [f"ResearchTasks ({state_filter}): {len(records)}"]
    for r in records:
        t = dict(r["t"])
        state = t.get("state", "?")
        desc = (t.get("description") or "")[:80]
        if brief:
            lines.append(f"  [{state}] {desc}")
        else:
            aid = t.get("artifact_id", "?")[:8]
            source = t.get("source_file", "")
            lines.append(f"  [{state}] {desc}")
            lines.append(f"    id: {aid}...")
            if source:
                lines.append(f"    source: {source}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Issue tools
# ---------------------------------------------------------------------------

@mcp.tool()
def seldon_issue_create(
    name: str,
    description: str,
    importance: str = "medium",
    urgency: str = "medium",
    project_dir: str = ".",
) -> str:
    """Create an Issue in the project graph (Eisenhower 3×3 priority matrix).

    Args:
        name: Issue name (short identifier)
        description: Issue description
        importance: high, medium, or low
        urgency: high, medium, or low
        project_dir: Path to project root
    """
    from seldon.core.artifacts import create_artifact
    from seldon.core.issue_utils import validate_issue_enum, eisenhower_quadrant

    config, driver, database, domain_config, project_dir = _resolve_project(project_dir)
    p = Path(project_dir)

    try:
        validate_issue_enum("importance", importance)
        validate_issue_enum("urgency", urgency)
    except ValueError as exc:
        driver.close()
        return f"Error: {exc}"

    try:
        artifact_id = create_artifact(
            project_dir=p, driver=driver, database=database,
            domain_config=domain_config, artifact_type="Issue",
            properties={
                "name": name,
                "description": description,
                "importance": importance,
                "urgency": urgency,
            },
            actor="desktop", authority="accepted",
        )
        quadrant = eisenhower_quadrant(importance, urgency)
        return (
            f"Created Issue: {artifact_id[:8]}...\n"
            f"  name: {name}\n"
            f"  priority: {importance}/{urgency} ({quadrant})\n"
            f"  state: open"
        )
    finally:
        driver.close()


@mcp.tool()
def seldon_issue_update(
    issue_id: str,
    project_dir: str = ".",
    state: str = "",
    importance: str = "",
    urgency: str = "",
) -> str:
    """Update an Issue's state or priority dimensions.

    Args:
        issue_id: Artifact ID (full UUID or prefix)
        project_dir: Path to project root
        state: New state if changing (open, in_progress, resolved, wont_fix, blocked, verified)
        importance: New importance if changing (high, medium, low)
        urgency: New urgency if changing (high, medium, low)
    """
    from seldon.core.artifacts import transition_state, update_artifact
    from seldon.core.graph import get_artifact
    from seldon.core.issue_utils import validate_issue_enum

    config, driver, database, domain_config, project_dir = _resolve_project(project_dir)
    p = Path(project_dir)

    try:
        full_id = _resolve_artifact_id(driver, database, issue_id)
        if full_id is None:
            return f"Error: issue '{issue_id}' not found or ambiguous."

        with driver.session(database=database) as session:
            node = get_artifact(session, full_id)
        if node is None:
            return f"Error: issue '{issue_id}' not found."

        result_parts = []

        if state:
            current_state = node.get("state", "")
            transition_state(
                project_dir=p, driver=driver, database=database,
                domain_config=domain_config,
                artifact_id=full_id, artifact_type="Issue",
                current_state=current_state, new_state=state,
                actor="desktop", authority="accepted",
            )
            result_parts.append(f"state: {current_state} → {state}")

        props_to_update: dict[str, Any] = {}
        if importance:
            validate_issue_enum("importance", importance)
            props_to_update["importance"] = importance
        if urgency:
            validate_issue_enum("urgency", urgency)
            props_to_update["urgency"] = urgency

        if props_to_update:
            update_artifact(
                project_dir=p, driver=driver, database=database,
                artifact_id=full_id, properties=props_to_update,
                actor="desktop", authority="accepted",
            )
            result_parts.extend(f"{k}: {v}" for k, v in props_to_update.items())

        if not result_parts:
            return "No changes specified (provide state, importance, or urgency)."

        return f"Updated {full_id[:8]}...:\n" + "\n".join(f"  {p}" for p in result_parts)
    finally:
        driver.close()


# ---------------------------------------------------------------------------
# CC task tools
# ---------------------------------------------------------------------------

@mcp.tool()
def seldon_cc_complete(
    filepath: str,
    project_dir: str = ".",
    note: str = "",
) -> str:
    """Mark a CC task file as completed in the graph.

    Creates a ResearchTask in 'completed' state linked to the CC task file.
    Running twice on the same file warns instead of creating a duplicate.

    Args:
        filepath: Path to the CC task file (relative to project root)
        project_dir: Path to project root
        note: Optional description override (default: auto-extracted from file)
    """
    from seldon.commands.cc import (
        _find_existing, _walk_to_completed,
        _name_from_filepath, _extract_description,
    )
    from seldon.core.artifacts import create_artifact
    from datetime import datetime, timezone

    config, driver, database, domain_config, project_dir = _resolve_project(project_dir)
    p = Path(project_dir)

    task_path = Path(filepath)
    if not task_path.is_absolute():
        task_path = p / task_path

    if not task_path.exists():
        driver.close()
        return f"Error: file not found: {filepath}"

    try:
        rel_path = str(task_path.relative_to(p))
    except ValueError:
        rel_path = str(task_path)

    existing_id = _find_existing(driver, database, rel_path)
    if existing_id:
        driver.close()
        return f"Warning: CC task already recorded as completed (id: {existing_id[:8]}...). No duplicate created."

    name = _name_from_filepath(rel_path)
    description = note if note else _extract_description(task_path)
    completed_at = datetime.now(timezone.utc).isoformat()

    try:
        artifact_id = create_artifact(
            project_dir=p, driver=driver, database=database,
            domain_config=domain_config, artifact_type="ResearchTask",
            properties={
                "description": description,
                "name": name,
                "source_file": rel_path,
                "completed_at": completed_at,
            },
            actor="desktop", authority="accepted",
        )
        _walk_to_completed(
            project_dir=p, driver=driver, database=database,
            domain_config=domain_config, artifact_id=artifact_id, session_id=None,
        )
        return (
            f"Recorded: {name}\n"
            f"  source_file: {rel_path}\n"
            f"  id: {artifact_id[:8]}...\n"
            f"  state: completed"
        )
    finally:
        driver.close()


@mcp.tool()
def seldon_cc_register(
    filepath: str,
    project_dir: str = ".",
) -> str:
    """Register a CC task file as a proposed ResearchTask in the graph.

    Use at task creation time to track the task before execution.
    Running twice on the same file warns instead of creating a duplicate.

    Args:
        filepath: Path to the CC task file (relative to project root)
        project_dir: Path to project root
    """
    from seldon.commands.cc import (
        _find_existing, _name_from_filepath, _extract_description,
    )
    from seldon.core.artifacts import create_artifact

    config, driver, database, domain_config, project_dir = _resolve_project(project_dir)
    p = Path(project_dir)

    task_path = Path(filepath)
    if not task_path.is_absolute():
        task_path = p / task_path

    if not task_path.exists():
        driver.close()
        return f"Error: file not found: {filepath}"

    try:
        rel_path = str(task_path.relative_to(p))
    except ValueError:
        rel_path = str(task_path)

    existing_id = _find_existing(driver, database, rel_path)
    if existing_id:
        driver.close()
        return f"Warning: CC task already registered (id: {existing_id[:8]}...). No duplicate created."

    name = _name_from_filepath(rel_path)
    description = _extract_description(task_path)

    try:
        artifact_id = create_artifact(
            project_dir=p, driver=driver, database=database,
            domain_config=domain_config, artifact_type="ResearchTask",
            properties={
                "description": description,
                "name": name,
                "source_file": rel_path,
            },
            actor="desktop", authority="accepted",
        )
        return (
            f"Registered: {name}\n"
            f"  source_file: {rel_path}\n"
            f"  id: {artifact_id[:8]}...\n"
            f"  state: proposed"
        )
    finally:
        driver.close()


# ---------------------------------------------------------------------------
# Read-only Cypher query
# ---------------------------------------------------------------------------

_WRITE_PATTERN = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|REMOVE|DETACH)\b",
    re.IGNORECASE,
)


@mcp.tool()
def seldon_query(
    cypher: str,
    project_dir: str = ".",
) -> str:
    """Read-only Cypher query against the project's graph database.

    Results are returned as readable text. Write operations are rejected.

    Args:
        cypher: Cypher query string (SELECT-style only — no CREATE/MERGE/SET/DELETE/REMOVE)
        project_dir: Path to project root
    """
    if _WRITE_PATTERN.search(cypher):
        return (
            "Error: write operations are not allowed via seldon_query. "
            "Use the dedicated MCP tools for mutations."
        )

    config, driver, database, domain_config, project_dir = _resolve_project(project_dir)

    try:
        with driver.session(database=database) as session:
            records = session.run(cypher).data()
    except Exception as exc:
        driver.close()
        return f"Query error: {exc}"
    finally:
        driver.close()

    if not records:
        return "No results."

    lines = []
    for i, row in enumerate(records):
        parts = []
        for key, val in row.items():
            if isinstance(val, dict):
                val_str = ", ".join(f"{k}={v}" for k, v in val.items() if k != "artifact_id" or True)
                parts.append(f"{key}: {{{val_str}}}")
            else:
                parts.append(f"{key}: {val}")
        lines.append(f"  {i + 1}. " + " | ".join(parts))

    return f"{len(records)} result(s):\n" + "\n".join(lines)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
