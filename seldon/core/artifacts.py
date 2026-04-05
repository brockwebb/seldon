from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from neo4j import Driver

from seldon.domain.loader import DomainConfig, validate_artifact_type, validate_relationship
from seldon.core.state import validate_transition
from seldon.core.events import append_event, make_event
from seldon.core import graph


def create_artifact(
    project_dir: Path,
    driver: Driver,
    database: str,
    domain_config: DomainConfig,
    artifact_type: str,
    properties: Dict[str, Any],
    actor: str,
    authority: str,
    session_id: Optional[str] = None,
) -> str:
    """
    Validate, write JSONL event, then write Neo4j node.

    Returns the new artifact_id.

    Raises:
        ValueError: If artifact_type is "OntologyTerm" and the project has shared_ontology.inheritance
            configured as "read-only", or if required properties are missing.
    """
    validate_artifact_type(domain_config, artifact_type)

    # Validate required properties
    required = domain_config.get_required_properties(artifact_type)
    missing = [r for r in required if r not in properties or not str(properties[r]).strip()]
    if missing:
        raise ValueError(
            f"Missing required properties for {artifact_type}: {', '.join(missing)}"
        )

    # Write protection for OntologyTerm in project databases
    if artifact_type == "OntologyTerm":
        from seldon.config import load_project_config
        try:
            config = load_project_config(project_dir)
            shared = config.get("shared_ontology", {})
            if shared.get("inheritance") == "read-only":
                raise ValueError(
                    "OntologyTerm artifacts are inherited from the shared ontology and cannot be "
                    "created directly in this project. Use `seldon ontology sync` to pull from master, "
                    "or add terms to the canonical vocabulary via CC task and `seldon ontology ingest`."
                )
        except FileNotFoundError:
            pass  # No seldon.yaml — allow (e.g., when init is running for master DB itself)

    artifact_id = str(uuid.uuid4())
    initial_state = domain_config.get_initial_state(artifact_type)

    event = make_event(
        event_type="artifact_created",
        actor=actor,
        authority=authority,
        payload={
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "properties": properties,
            "from_state": None,
            "to_state": initial_state,
        },
        session_id=session_id,
    )
    append_event(project_dir, event)

    props = dict(properties)
    props["artifact_id"] = artifact_id
    props["state"] = initial_state
    props["authority"] = authority
    props["created_by"] = actor

    with driver.session(database=database) as session:
        graph.create_artifact(session, artifact_type, props)

    return artifact_id


def update_artifact(
    project_dir: Path,
    driver: Driver,
    database: str,
    artifact_id: str,
    properties: Dict[str, Any],
    actor: str,
    authority: str,
    session_id: Optional[str] = None,
) -> None:
    """
    Write JSONL event then update Neo4j node properties.

    Raises:
        ValueError: If attempting to update an OntologyTerm artifact in a project with
            shared_ontology.inheritance configured as "read-only".
    """
    # Write protection for OntologyTerm in project databases
    from seldon.config import load_project_config
    try:
        config = load_project_config(project_dir)
        shared = config.get("shared_ontology", {})
        if shared.get("inheritance") == "read-only":
            # Look up the artifact type to check if it's OntologyTerm
            with driver.session(database=database) as session:
                artifact = graph.get_artifact(session, artifact_id)
            if artifact and artifact.get("artifact_type") == "OntologyTerm":
                raise ValueError(
                    "OntologyTerm artifacts are read-only in this project and cannot be updated directly. "
                    "Use `seldon ontology sync` to pull updates from master."
                )
    except FileNotFoundError:
        pass  # No seldon.yaml — allow

    event = make_event(
        event_type="artifact_updated",
        actor=actor,
        authority=authority,
        payload={
            "artifact_id": artifact_id,
            "properties": properties,
        },
        session_id=session_id,
    )
    append_event(project_dir, event)

    with driver.session(database=database) as session:
        graph.update_artifact(session, artifact_id, properties)


def transition_state(
    project_dir: Path,
    driver: Driver,
    database: str,
    domain_config: DomainConfig,
    artifact_id: str,
    artifact_type: str,
    current_state: str,
    new_state: str,
    actor: str,
    authority: str,
    session_id: Optional[str] = None,
) -> None:
    """Validate transition, write JSONL event, then update Neo4j state."""
    validate_transition(domain_config, artifact_type, current_state, new_state)

    event = make_event(
        event_type="artifact_state_changed",
        actor=actor,
        authority=authority,
        payload={
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "from_state": current_state,
            "to_state": new_state,
        },
        session_id=session_id,
    )
    append_event(project_dir, event)

    with driver.session(database=database) as session:
        graph.change_state(session, artifact_id, new_state)

    # Auto-propagate staleness downstream when an artifact goes stale
    if new_state == "stale":
        from seldon.core.staleness import propagate_staleness
        propagate_staleness(
            driver=driver,
            database=database,
            project_dir=project_dir,
            domain_config=domain_config,
            artifact_id=artifact_id,
            session_id=session_id,
        )


def create_link(
    project_dir: Path,
    driver: Driver,
    database: str,
    domain_config: DomainConfig,
    from_id: str,
    to_id: str,
    from_type: str,
    to_type: str,
    rel_type: str,
    actor: str,
    authority: str,
    session_id: Optional[str] = None,
    rel_properties: Optional[Dict[str, Any]] = None,
) -> None:
    """Validate relationship, write JSONL event, then create Neo4j relationship.

    Args:
        rel_properties: Optional properties to set on the relationship itself
            (e.g., topic and strength for `assumes` edges).
    """
    validate_relationship(domain_config, rel_type, from_type, to_type)

    props = rel_properties or {}

    event = make_event(
        event_type="link_created",
        actor=actor,
        authority=authority,
        payload={
            "from_id": from_id,
            "to_id": to_id,
            "from_type": from_type,
            "to_type": to_type,
            "rel_type": rel_type,
            "properties": props,
        },
        session_id=session_id,
    )
    append_event(project_dir, event)

    with driver.session(database=database) as session:
        graph.create_link(session, from_id, to_id, rel_type.upper(), props)


def walk_to_completed(
    project_dir: Path,
    driver: Driver,
    database: str,
    domain_config,
    artifact_id: str,
    current_state: str,
    actor: str = "cc",
    session_id: Optional[str] = None,
) -> list[str]:
    """Walk a ResearchTask from current_state to completed.

    State-aware: skips transitions for states already passed. Raises ValueError
    if current_state is not on a known path to completed.

    Args:
        current_state: The artifact's current state in the graph.
        actor: Actor string written to events ('cc' or 'desktop').

    Returns:
        List of 'from → to' transition strings performed.

    Raises:
        ValueError: If current_state has no known path to completed.
    """
    path_to_completed: Dict[str, list[str]] = {
        "proposed": ["accepted", "in_progress", "completed"],
        "accepted": ["in_progress", "completed"],
        "in_progress": ["completed"],
        "completed": [],
        "blocked": ["in_progress", "completed"],
    }

    steps = path_to_completed.get(current_state)
    if steps is None:
        raise ValueError(
            f"Cannot walk ResearchTask to completed from state '{current_state}'"
        )

    transitions = []
    state = current_state
    for next_state in steps:
        transition_state(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_id=artifact_id,
            artifact_type="ResearchTask",
            current_state=state,
            new_state=next_state,
            actor=actor,
            authority="accepted",
            session_id=session_id,
        )
        transitions.append(f"{state} → {next_state}")
        state = next_state

    return transitions


def remove_link(
    project_dir: Path,
    driver: Driver,
    database: str,
    from_id: str,
    to_id: str,
    rel_type: str,
    actor: str,
    authority: str,
    session_id: Optional[str] = None,
) -> None:
    """Write JSONL event then delete Neo4j relationship."""
    event = make_event(
        event_type="link_removed",
        actor=actor,
        authority=authority,
        payload={
            "from_id": from_id,
            "to_id": to_id,
            "rel_type": rel_type,
        },
        session_id=session_id,
    )
    append_event(project_dir, event)

    with driver.session(database=database) as session:
        graph.remove_link(session, from_id, to_id, rel_type.upper())
