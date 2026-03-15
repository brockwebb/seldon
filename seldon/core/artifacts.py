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
    """
    validate_artifact_type(domain_config, artifact_type)

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
    """Write JSONL event then update Neo4j node properties."""
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
) -> None:
    """Validate relationship, write JSONL event, then create Neo4j relationship."""
    validate_relationship(domain_config, rel_type, from_type, to_type)

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
            "properties": {},
        },
        session_id=session_id,
    )
    append_event(project_dir, event)

    with driver.session(database=database) as session:
        graph.create_link(session, from_id, to_id, rel_type.upper(), {})
