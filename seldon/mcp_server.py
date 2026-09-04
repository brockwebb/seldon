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


# Actor recorded on events written by the MCP tools. The CLI writes 'human'.
MCP_ACTOR = "desktop"


def _walk_task_to_completed(
    project_dir: Path,
    driver,
    database: str,
    domain_config,
    artifact_id: str,
    current_state: str,
) -> list[str]:
    """Walk a ResearchTask from current_state to completed.

    Thin adapter over :func:`seldon.core.artifacts.walk_to_completed` — the single
    close walk shared with `seldon task close`, so both surfaces emit the same event
    sequence (AD-028). There is deliberately no second walker here.

    Args:
        project_dir: Project root, for the JSONL event store.
        driver: Neo4j driver.
        database: Database name.
        domain_config: Loaded domain configuration.
        artifact_id: Full artifact_id of the ResearchTask.
        current_state: The task's current state in the graph.

    Returns:
        List of 'from → to' transition strings performed.

    Raises:
        ValueError: If current_state has no known path to completed.
    """
    from seldon.core.artifacts import walk_to_completed

    return walk_to_completed(
        project_dir=project_dir,
        driver=driver,
        database=database,
        domain_config=domain_config,
        artifact_id=artifact_id,
        current_state=current_state,
        actor=MCP_ACTOR,
    )


def _mcp_terminal_transition(
    task_id: str,
    new_state: str,
    reason: str,
    superseded_by: str | None,
    project_dir: str,
) -> str:
    """Shared body for seldon_task_withdraw and seldon_task_supersede.

    Args:
        task_id: Artifact ID (full UUID or prefix).
        new_state: Terminal state to move to ('withdrawn' or 'superseded').
        reason: Operator-supplied reason, stored as `terminal_reason`.
        superseded_by: Optional artifact ID that overtook the task, or None.
        project_dir: Path to project root.

    Returns:
        A human-readable result or an "Error: ..." line. Every precondition is
        checked before the first write, so an error means nothing was written.
    """
    from seldon.core.artifacts import transition_task
    from seldon.core.graph import get_artifact
    from seldon.core.state import InvalidStateTransition

    if not reason or not reason.strip():
        return f"Error: '{new_state}' requires a reason."

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
        desc = (node.get("description") or "")[:60]

        transition_task(
            project_dir=p, driver=driver, database=database,
            domain_config=domain_config, artifact_id=full_id,
            current_state=current_state, new_state=new_state,
            actor=MCP_ACTOR, authority="accepted",
            terminal_reason=reason, superseded_by=superseded_by,
        )

        lines = [
            f"Updated: {full_id[:8]}... — {desc}",
            f"  {current_state} → {new_state}",
            f"  reason: {reason}",
        ]
        if superseded_by:
            lines.append(f"  superseded_by: {superseded_by}")
        return "\n".join(lines)
    except (ValueError, InvalidStateTransition) as exc:
        return f"Error: {exc}"
    finally:
        driver.close()


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
                with driver.session(database=database) as session:
                    target_node = get_artifact(session, target_id)
                create_link(
                    project_dir=p, driver=driver, database=database,
                    domain_config=domain_config,
                    from_id=artifact_id, to_id=target_id, rel_type="blocks",
                    from_type="ResearchTask",
                    to_type=target_node.get("artifact_type", ""),
                    actor=MCP_ACTOR, authority="accepted",
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
    """Update a ResearchTask's state (single transition).

    Use seldon_task_withdraw or seldon_task_supersede for the two terminal states
    that require a recorded reason — this tool refuses them, because its `note`
    argument is echoed back and not stored, and a terminal state with a silently
    dropped reason is indistinguishable from the other terminal states later.

    Args:
        task_id: Artifact ID (full UUID or prefix)
        state: New state (accepted, in_progress, completed, verified, blocked,
            rejected). The accepted → in_progress transition records claimed_by
            ('desktop') and claimed_at.
        project_dir: Path to project root
        note: Optional note (echoed back, not stored)
    """
    from seldon.core.artifacts import REASON_REQUIRED_STATES, transition_task
    from seldon.core.graph import get_artifact
    from seldon.core.state import InvalidStateTransition

    if state in REASON_REQUIRED_STATES:
        return (
            f"Error: '{state}' requires a recorded reason, which seldon_task_update "
            f"cannot store. Use seldon_task_withdraw or seldon_task_supersede."
        )

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

        transition_task(
            project_dir=p, driver=driver, database=database,
            domain_config=domain_config,
            artifact_id=full_id,
            current_state=current_state, new_state=state,
            actor=MCP_ACTOR, authority="accepted",
        )

        return (
            f"Updated: {full_id[:8]}...\n"
            f"  {current_state} → {state}"
            + (f"\n  note: {note}" if note else "")
        )
    except (ValueError, InvalidStateTransition) as exc:
        return f"Error: {exc}"
    finally:
        driver.close()


@mcp.tool()
def seldon_task_withdraw(
    task_id: str,
    reason: str,
    project_dir: str = ".",
) -> str:
    """Withdraw a ResearchTask: its premise turned out to be false.

    Terminal. Reachable only from an open state (proposed/accepted/in_progress/
    blocked) — never from completed or verified, because relabelling a finished
    task would corrupt the honest completion record. The reason is stored on the
    task as `terminal_reason`.

    Args:
        task_id: Artifact ID (full UUID or prefix)
        reason: Why the task's premise no longer holds. Required.
        project_dir: Path to project root
    """
    return _mcp_terminal_transition(task_id, "withdrawn", reason, None, project_dir)


@mcp.tool()
def seldon_task_supersede(
    task_id: str,
    reason: str,
    project_dir: str = ".",
    superseded_by: str = "",
) -> str:
    """Supersede a ResearchTask: the work was valid but something else overtook it.

    Terminal, with the same reachability as withdrawn. The reason is stored as
    `terminal_reason`. When `superseded_by` is given it is validated (the artifact
    must exist and be a legal endpoint for the edge) and a `superseded_by` edge is
    written; an unknown or illegal id is a hard error that leaves the state unchanged.

    Args:
        task_id: Artifact ID (full UUID or prefix)
        reason: What overtook this task, and why. Required.
        project_dir: Path to project root
        superseded_by: Optional artifact ID (full or prefix) of the ResearchTask,
            ArchitecturalDecision, DesignNote or Result that overtook this task.
    """
    return _mcp_terminal_transition(
        task_id, "superseded", reason, superseded_by or None, project_dir
    )


@mcp.tool()
def seldon_task_close(
    task_id: str,
    project_dir: str = ".",
    note: str = "",
) -> str:
    """Close a ResearchTask by walking it from current state to completed in one call.

    Handles the full state machine path (proposed→accepted→in_progress→completed)
    regardless of current state. Use this instead of multiple seldon_task_update
    calls when bulk-closing tasks.

    Args:
        task_id: Artifact ID (full UUID or prefix)
        project_dir: Path to project root
        note: Optional note explaining why the task is being closed
    """
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
        desc = (node.get("description") or "")[:60]

        if current_state == "completed":
            return f"Already completed: {full_id[:8]}... — {desc}"

        transitions = _walk_task_to_completed(
            project_dir=p, driver=driver, database=database,
            domain_config=domain_config, artifact_id=full_id,
            current_state=current_state,
        )

        result = f"Closed: {full_id[:8]}... — {desc}\n  path: {' → '.join(t.split(' → ')[1] for t in transitions)}"
        if note:
            result += f"\n  note: {note}"
        return result
    except ValueError as exc:
        return f"Error: {exc}"
    finally:
        driver.close()


@mcp.tool()
def seldon_task_list(
    project_dir: str = ".",
    state_filter: str = "open",
    brief: bool = True,
) -> str:
    """List ResearchTasks filtered by state.

    The default filter, 'open', excludes every terminal state (verified, rejected,
    superseded, withdrawn) and also 'completed'. The open set is derived from the
    domain config's state machine, so a terminal state added to research.yaml drops
    out of this view without a code change. Use 'all' to see everything.

    For in_progress tasks the claim marker (claimed_by / claimed_at) is shown when
    present — advisory only, staleness is never auto-released.

    Args:
        project_dir: Path to project root
        state_filter: 'open' (the default: live work only), 'completed', 'all',
                      or a specific state name
        brief: If True, one-line summaries. If False, full details including IDs.
    """
    from seldon.core.artifacts import open_states

    config, driver, database, domain_config, project_dir = _resolve_project(project_dir)

    params: dict[str, Any] = {}
    if state_filter == "open":
        where = "WHERE t.state IN $states"
        params["states"] = open_states(domain_config, "ResearchTask")
    elif state_filter == "all":
        where = ""
    else:
        where = "WHERE t.state = $state"
        params["state"] = state_filter

    try:
        with driver.session(database=database) as session:
            records = session.run(
                f"MATCH (t:Artifact:ResearchTask) {where} "
                "RETURN t ORDER BY t.created_at",
                **params,
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
        claim = ""
        if state == "in_progress" and t.get("claimed_by"):
            claim = f" (claimed by {t['claimed_by']} at {t.get('claimed_at', '?')})"
        if brief:
            lines.append(f"  [{state}] {desc}{claim}")
        else:
            aid = t.get("artifact_id", "?")[:8]
            source = t.get("source_file", "")
            lines.append(f"  [{state}] {desc}{claim}")
            lines.append(f"    id: {aid}...")
            if source:
                lines.append(f"    source: {source}")
            if t.get("terminal_reason"):
                lines.append(f"    reason: {t['terminal_reason']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Issue tools
# ---------------------------------------------------------------------------

@mcp.tool()
def seldon_issue_create(
    name: str,
    description: str,
    issue_type: str = "factual_error",
    detection_method: str = "incidental",
    target: str = "content",
    importance: str = "medium",
    urgency: str = "medium",
    project_dir: str = ".",
) -> str:
    """Create an Issue artifact for a research production quality problem.

    Issues track problems found in research outputs: factual errors, citation
    gaps, unsupported claims, terminology inconsistencies, stale content, etc.
    Issues are NOT for software bugs or feature requests — use CC tasks for those.

    Args:
        name: Short identifier for the issue
        description: The problem statement — what's wrong
        issue_type: Category of problem. Values: factual_error, citation_gap,
            unsupported_claim, terminology_inconsistency, internal_contradiction,
            missing_content, stale_content, structural_flow, style_formatting
        detection_method: How found. Values: automated_check, audit, incidental, build_failure
        target: What needs to change. Values: content, citation, terminology, data, structure
        importance: Eisenhower importance (high, medium, low)
        urgency: Eisenhower urgency (high, medium, low)
        project_dir: Path to project root
    """
    from seldon.core.artifacts import create_artifact
    from seldon.core.issue_utils import validate_issue_enum, eisenhower_quadrant

    config, driver, database, domain_config, project_dir = _resolve_project(project_dir)
    p = Path(project_dir)

    try:
        validate_issue_enum("issue_type", issue_type)
        validate_issue_enum("detection_method", detection_method)
        validate_issue_enum("target", target)
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
                "issue_type": issue_type,
                "detection_method": detection_method,
                "target": target,
                "importance": importance,
                "urgency": urgency,
            },
            actor="desktop", authority="accepted",
        )
        quadrant = eisenhower_quadrant(importance, urgency)
        return (
            f"Created Issue: {artifact_id[:8]}...\n"
            f"  name: {name}\n"
            f"  type: {issue_type} / detected: {detection_method} / target: {target}\n"
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
        _find_existing, _name_from_filepath, _extract_description,
    )
    from seldon.core.artifacts import create_artifact, update_artifact, walk_to_completed
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
        # State-aware duplicate guard
        from seldon.core.graph import get_artifact
        with driver.session(database=database) as sess:
            node = get_artifact(sess, existing_id)
        current_state = node.get("state") if node else None

        if current_state == "completed":
            driver.close()
            return f"Warning: CC task already completed (id: {existing_id[:8]}...). No action taken."

        # Pre-registered task — walk it to completed
        name = _name_from_filepath(rel_path)
        completed_at = datetime.now(timezone.utc).isoformat()
        try:
            update_artifact(
                project_dir=p, driver=driver, database=database,
                artifact_id=existing_id,
                properties={"completed_at": completed_at},
                actor="desktop", authority="accepted",
            )
            transitions = _walk_task_to_completed(
                project_dir=p, driver=driver, database=database,
                domain_config=domain_config, artifact_id=existing_id,
                current_state=current_state,
            )
            path_str = " → ".join(t.split(" → ")[1] for t in transitions) if transitions else "completed"
            return (
                f"Completed pre-registered task: {name}\n"
                f"  source_file: {rel_path}\n"
                f"  id: {existing_id[:8]}...\n"
                f"  path: {path_str}\n"
                f"  state: completed"
            )
        finally:
            driver.close()

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
        walk_to_completed(
            project_dir=p, driver=driver, database=database,
            domain_config=domain_config, artifact_id=artifact_id,
            current_state="proposed", actor="desktop",
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
# Audit orchestration (AD-019 + AD-020 pipeline, Desktop entry point)
# ---------------------------------------------------------------------------

_VALID_GATES = (
    "content_audit",
    "practitioner_stress_test",
    "argument_completeness",
    "bloom_depth_check",
    "secondary_sweep",
)


def _resolve_paper_root(project_dir: Path, config: dict) -> Path | None:
    """Return absolute path to the paper root for this project, or None.

    Resolution order:
      1. `paths.paper` from seldon.yaml
      2. `paths.sections` minus trailing 'sections/' segment
      3. Common conventions: `sfv-paper/paper`, `paper`, `book`
    """
    paths = config.get("paths") or {}
    if paths.get("paper"):
        candidate = project_dir / paths["paper"]
        if candidate.exists():
            return candidate.resolve()
    if paths.get("sections"):
        sections = (project_dir / paths["sections"]).resolve()
        if sections.name == "sections" and sections.parent.exists():
            return sections.parent
    for convention in ("sfv-paper/paper", "paper", "book"):
        candidate = project_dir / convention
        if candidate.exists():
            return candidate.resolve()
    return None


def _next_run_id(audits_dir: Path) -> str:
    """Return next sequential run-id (e.g. 'run-007') by scanning audits_dir.

    Looks for any directory named `run-NNN_*` and picks max(NNN) + 1.
    """
    if not audits_dir.exists():
        return "run-001"
    pattern = re.compile(r"^run-(\d{3})(?:_|$)")
    highest = 0
    for child in audits_dir.iterdir():
        if not child.is_dir():
            continue
        m = pattern.match(child.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return f"run-{highest + 1:03d}"


@mcp.tool()
def seldon_audit(
    section: str,
    project_dir: str = ".",
    gates: str = "all",
    audit_model: str = "",
    run_id: str = "",
) -> str:
    """Run AD-020 audit pipeline gates against a paper section.

    Creates an audits/run-NNN_<date>/ directory, dispatches each requested
    gate through the configured AUDIT_MODEL (via litellm), writes the run
    manifest, and returns a findings summary. Wraps seldon.paper.audit_dispatch
    so Desktop threads can trigger audits without authoring a CC task.

    Args:
        section: Path to the section file. Absolute, or relative to project root.
        project_dir: Path to project root (defaults to SELDON_DEFAULT_PROJECT).
        gates: Comma-separated gate names, or "all" for the full sweep.
            Valid gates: content_audit, practitioner_stress_test,
            argument_completeness, bloom_depth_check, secondary_sweep.
        audit_model: Override AUDIT_MODEL env var for this run. Empty = use env
            var or fall back to audit_dispatch.DEFAULT_MODEL.
        run_id: Override the auto-generated run-id (e.g. "run-006"). Empty =
            auto-increment from existing runs in <paper_root>/audits/.
    """
    import datetime as _dt
    import yaml as _yaml

    # Resolve section file
    try:
        config, driver, database, domain_config, resolved_project_dir = _resolve_project(project_dir)
    except Exception as exc:
        return f"Error: cannot resolve project at {project_dir!r}: {exc}"
    driver.close()  # this tool doesn't touch Neo4j

    project_root = Path(resolved_project_dir).resolve()
    section_path = Path(section)
    if not section_path.is_absolute():
        section_path = (project_root / section_path).resolve()
    if not section_path.exists():
        return f"Error: section file not found: {section_path}"

    # Resolve paper root + audits dir
    paper_root = _resolve_paper_root(project_root, config)
    if paper_root is None:
        return (
            "Error: cannot resolve paper root for project. "
            "Set `paths.paper` in seldon.yaml, or place sections under "
            "'paper/', 'sfv-paper/paper/', or 'book/'."
        )
    audits_dir = paper_root / "audits"

    # Resolve gates
    if gates == "all":
        gates_to_run = list(_VALID_GATES)
    else:
        requested = [g.strip() for g in gates.split(",") if g.strip()]
        invalid = [g for g in requested if g not in _VALID_GATES]
        if invalid:
            return f"Error: unknown gate(s): {invalid}. Valid: {list(_VALID_GATES)}"
        gates_to_run = requested

    # Resolve run-id
    today = _dt.date.today().isoformat()
    rid = run_id or _next_run_id(audits_dir)
    run_dir = audits_dir / f"{rid}_{today}"
    section_slug = section_path.stem
    section_run_dir = run_dir / section_slug
    section_run_dir.mkdir(parents=True, exist_ok=True)

    # Import dispatch lazily so server startup doesn't require litellm
    try:
        from seldon.paper.audit_dispatch import dispatch, resolve_audit_model
        from seldon.commands.audit_dispatch import _system_prompt_for, _user_prompt_for
    except ImportError as exc:
        return f"Error: audit dispatch unavailable ({exc}). Install litellm."

    # Apply audit_model override if provided
    original_audit_model_env = os.environ.get("AUDIT_MODEL")
    if audit_model:
        os.environ["AUDIT_MODEL"] = audit_model

    section_text = section_path.read_text(encoding="utf-8")
    gates_succeeded: list[str] = []
    gates_failed: list[dict] = []

    try:
        resolved_model = resolve_audit_model()
        for gate in gates_to_run:
            try:
                system = _system_prompt_for(gate, None)
                user_prompt = _user_prompt_for(gate, section_path, section_text)
                result_text = dispatch(
                    prompt=user_prompt,
                    system=system,
                    temperature=0.2,
                    max_tokens=8192,
                )
                (section_run_dir / f"{gate}.yaml").write_text(result_text, encoding="utf-8")
                gates_succeeded.append(gate)
            except Exception as exc:
                gates_failed.append({"gate": gate, "error": str(exc)})
    finally:
        if audit_model:
            if original_audit_model_env is None:
                os.environ.pop("AUDIT_MODEL", None)
            else:
                os.environ["AUDIT_MODEL"] = original_audit_model_env

    # Best-effort: parse top-level finding counts from each successful YAML
    findings_summary: dict[str, int] = {}
    for gate in gates_succeeded:
        gate_file = section_run_dir / f"{gate}.yaml"
        try:
            parsed = _yaml.safe_load(gate_file.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                if "findings_count" in parsed:
                    findings_summary[gate] = int(parsed["findings_count"])
                elif isinstance(parsed.get("findings"), list):
                    findings_summary[gate] = len(parsed["findings"])
                elif isinstance(parsed.get("questions"), list):
                    findings_summary[gate] = len(parsed["questions"])
        except Exception:
            pass  # malformed YAML — leave gate out of summary; raw file still on disk

    # Write run manifest
    document_type = (config.get("project") or {}).get("document_type", "academic_paper")
    manifest = {
        "run_manifest": {
            "run_id": rid,
            "date": today,
            "model": resolved_model,
            "pipeline": "AD-019 + AD-020",
            "document_type": document_type,
            "sections_audited": [section_slug],
            "gates_run": gates_succeeded,
            "gates_failed": gates_failed,
            "findings_summary": findings_summary,
            "produced_by": "seldon_audit MCP tool",
        }
    }
    manifest_path = run_dir / "run_manifest.yaml"
    manifest_path.write_text(_yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    # Build summary text
    rel_run_dir = run_dir.relative_to(project_root) if run_dir.is_relative_to(project_root) else run_dir
    gate_lines = [f"{g} ✓" for g in gates_succeeded]
    for failed in gates_failed:
        gate_lines.append(f"{failed['gate']} ✗ ({failed['error'][:60]})")
    summary_lines = [
        f"Audit {rid} complete: {section_slug}",
        f"  Model: {resolved_model}",
        f"  Gates: {', '.join(gate_lines) if gate_lines else '(none)'}",
        f"  Output: {rel_run_dir}",
    ]
    if findings_summary:
        total = sum(findings_summary.values())
        per_gate = ", ".join(f"{g}={n}" for g, n in findings_summary.items())
        summary_lines.append(f"  Findings: {total} total ({per_gate})")
    return "\n".join(summary_lines)


# ---------------------------------------------------------------------------
# Audit ingest (AD-020 pipeline → graph)
# ---------------------------------------------------------------------------

@mcp.tool()
def seldon_audit_ingest(
    run_dir: str,
    project_dir: str = ".",
    advance_states: bool = False,
) -> str:
    """Ingest an audit run directory into the project's Seldon graph.

    Reads run_manifest.yaml plus per-gate YAML scorecards, creates an
    AuditRun artifact plus AuditFinding artifacts for each parseable
    finding, and wires `audited_in`, `has_finding`, `finding_in` edges.
    Idempotent — re-ingesting the same run-id is a no-op.

    Args:
        run_dir: Path to the run directory (absolute or relative to project_dir).
        project_dir: Path to project root.
        advance_states: If True, advance PaperSection state from
            proposed/draft/review → `audited` for sections that have no
            open blocking/high findings in this run. Default False (safe
            for backfill).
    """
    from seldon.paper import audit_ingest

    try:
        config, driver, database, domain_config, resolved_project_dir = _resolve_project(project_dir)
    except Exception as exc:
        return f"Error: cannot resolve project at {project_dir!r}: {exc}"

    project_root = Path(resolved_project_dir).resolve()
    rd = Path(run_dir)
    if not rd.is_absolute():
        rd = (project_root / rd).resolve()
    if not rd.exists() or not rd.is_dir():
        driver.close()
        return f"Error: run directory not found: {rd}"

    try:
        plan = audit_ingest.plan_ingest(rd)
    except FileNotFoundError as exc:
        driver.close()
        return f"Error: {exc}"

    try:
        summary = audit_ingest.write_ingest(
            plan=plan,
            project_dir=project_root,
            driver=driver,
            database=database,
            domain_config=domain_config,
            actor="desktop",
            advance_states=advance_states,
        )
    finally:
        driver.close()

    if summary["action"] == "already_ingested":
        return (
            f"Run {plan.run_id} already ingested into {database}\n"
            f"  existing artifact: {summary['existing_artifact_id'][:8]}..."
        )

    lines = [
        f"Ingested {plan.run_id} into {database}:",
        f"  AuditRun: {plan.run_id} ({plan.date}, {plan.model})",
        f"  Layout: {plan.layout}",
        f"  Sections in run: {summary['sections_total']} ({summary['sections_linked']} matched to graph)",
        f"  Findings written: {summary['findings_written']}",
    ]
    if summary["sections_missing_in_graph"]:
        miss = summary["sections_missing_in_graph"]
        shown = ", ".join(miss[:5]) + (" ..." if len(miss) > 5 else "")
        lines.append(f"  Sections without PaperSection nodes (no finding_in edges): {shown}")
    if plan.gate_warnings:
        lines.append(f"  Gate warnings: {len(plan.gate_warnings)}")
        for w in plan.gate_warnings[:3]:
            lines.append(f"    - {w}")
    if advance_states:
        advanced = [c for c in summary["state_changes"] if c["action"] == "advanced"]
        skipped = [c for c in summary["state_changes"] if c["action"] == "skipped"]
        lines.append(f"  State changes: {len(advanced)} advanced to audited, {len(skipped)} skipped (high-severity findings)")
    return "\n".join(lines)


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
