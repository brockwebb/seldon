from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from neo4j import Session


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_artifact(
    session: Session,
    artifact_type: str,
    properties: Dict[str, Any],
) -> None:
    """
    Create a node with double-label pattern: :Artifact:<artifact_type>.

    artifact_type is used as the second label directly. Properties dict
    must include 'artifact_id' and 'state'.

    Note: Neo4j driver does not support parameterized labels, so artifact_type
    is injected via string formatting. It must be validated by domain config
    before reaching this function.
    """
    props = dict(properties)
    props.setdefault("artifact_type", artifact_type)
    props.setdefault("created_at", _now_iso())

    cypher = f"CREATE (a:Artifact:{artifact_type} $props)"
    session.run(cypher, props=props)


def update_artifact(
    session: Session,
    artifact_id: str,
    properties: Dict[str, Any],
) -> None:
    """SET additional properties on an existing artifact node."""
    session.run(
        "MATCH (a:Artifact {artifact_id: $id}) SET a += $props",
        id=artifact_id,
        props=properties,
    )


def change_state(
    session: Session,
    artifact_id: str,
    new_state: str,
) -> None:
    """
    Update the state property on an artifact node.

    State machine validation must be performed by core/state.py BEFORE
    calling this function. This function only writes to Neo4j.
    """
    session.run(
        "MATCH (a:Artifact {artifact_id: $id}) SET a.state = $state",
        id=artifact_id,
        state=new_state,
    )


def create_link(
    session: Session,
    from_id: str,
    to_id: str,
    rel_type: str,
    properties: Dict[str, Any],
) -> None:
    """
    Create a directed relationship between two artifact nodes.

    rel_type is validated by domain config before reaching this function.
    Uses uppercase convention (e.g., GENERATED_BY).
    """
    props = dict(properties)
    props.setdefault("created_at", _now_iso())
    cypher = (
        f"MATCH (a:Artifact {{artifact_id: $from_id}}), "
        f"(b:Artifact {{artifact_id: $to_id}}) "
        f"CREATE (a)-[r:{rel_type} $props]->(b)"
    )
    session.run(cypher, from_id=from_id, to_id=to_id, props=props)


def remove_link(
    session: Session,
    from_id: str,
    to_id: str,
    rel_type: str,
) -> None:
    """Delete a specific directed relationship between two artifacts."""
    cypher = (
        f"MATCH (a:Artifact {{artifact_id: $from_id}})"
        f"-[r:{rel_type}]->"
        f"(b:Artifact {{artifact_id: $to_id}}) "
        f"DELETE r"
    )
    session.run(cypher, from_id=from_id, to_id=to_id)


def get_artifact(
    session: Session,
    artifact_id: str,
) -> Optional[Dict[str, Any]]:
    """Return artifact properties dict, or None if not found."""
    result = session.run(
        "MATCH (a:Artifact {artifact_id: $id}) RETURN a",
        id=artifact_id,
    ).single()
    if result is None:
        return None
    return dict(result["a"])


def get_artifacts_by_type(
    session: Session,
    artifact_type: str,
) -> List[Dict[str, Any]]:
    """Return all artifacts with the given type label."""
    cypher = f"MATCH (a:Artifact:{artifact_type}) RETURN a"
    records = session.run(cypher).data()
    return [dict(r["a"]) for r in records]


def get_artifacts_by_state(
    session: Session,
    state: str,
) -> List[Dict[str, Any]]:
    """Return all artifacts with the given state value."""
    records = session.run(
        "MATCH (a:Artifact {state: $state}) RETURN a",
        state=state,
    ).data()
    return [dict(r["a"]) for r in records]


def get_neighbors(
    session: Session,
    artifact_id: str,
    rel_type: Optional[str] = None,
    direction: str = "both",
) -> List[Dict[str, Any]]:
    """
    Return 1-hop neighbors of the given artifact.

    direction: 'both' | 'out' | 'in'
    rel_type: if provided, filter by relationship type (e.g., 'GENERATED_BY')
    """
    rel_clause = f"[r:{rel_type}]" if rel_type else "[r]"
    if direction == "out":
        pattern = f"(a:Artifact {{artifact_id: $id}})-{rel_clause}->(b:Artifact)"
    elif direction == "in":
        pattern = f"(b:Artifact)-{rel_clause}->(a:Artifact {{artifact_id: $id}})"
    else:  # both
        pattern = f"(a:Artifact {{artifact_id: $id}})-{rel_clause}-(b:Artifact)"

    records = session.run(f"MATCH {pattern} RETURN DISTINCT b", id=artifact_id).data()
    return [dict(r["b"]) for r in records]


def get_provenance_chain(
    session: Session,
    artifact_id: str,
) -> List[Dict[str, Any]]:
    """
    Recursive upstream traversal — all ancestors reachable via any relationship.

    Uses Cypher variable-length path: (start)-[*]->(ancestor)
    """
    records = session.run(
        "MATCH (start:Artifact {artifact_id: $id})-[*]->(ancestor:Artifact) "
        "RETURN DISTINCT ancestor",
        id=artifact_id,
    ).data()
    return [dict(r["ancestor"]) for r in records]


def get_dependents(
    session: Session,
    artifact_id: str,
) -> List[Dict[str, Any]]:
    """
    Recursive downstream traversal — all artifacts that depend on this one.

    Uses Cypher variable-length path: (dependent)-[*]->(target)
    """
    records = session.run(
        "MATCH (dependent:Artifact)-[*]->(target:Artifact {artifact_id: $id}) "
        "RETURN DISTINCT dependent",
        id=artifact_id,
    ).data()
    return [dict(r["dependent"]) for r in records]


def get_stale_artifacts(session: Session) -> List[Dict[str, Any]]:
    """Return all artifacts in 'stale' state."""
    records = session.run(
        "MATCH (a:Artifact {state: 'stale'}) RETURN a"
    ).data()
    return [dict(r["a"]) for r in records]


def graph_stats(session: Session) -> Dict[str, Any]:
    """Return summary counts: total nodes, by_type, by_state, total_relationships."""
    total = session.run(
        "MATCH (a:Artifact) RETURN count(a) AS total"
    ).single()["total"]

    by_type_records = session.run(
        "MATCH (a:Artifact) RETURN a.artifact_type AS type, count(a) AS cnt"
    ).data()

    by_state_records = session.run(
        "MATCH (a:Artifact) RETURN a.state AS state, count(a) AS cnt"
    ).data()

    rel_count = session.run(
        "MATCH (:Artifact)-[r]->(:Artifact) RETURN count(r) AS total"
    ).single()["total"]

    return {
        "total_nodes": total,
        "total_relationships": rel_count,
        "by_type": {r["type"]: r["cnt"] for r in by_type_records if r["type"]},
        "by_state": {r["state"]: r["cnt"] for r in by_state_records if r["state"]},
    }


ALLOWED_LOOKUP_PROPERTIES = {"name", "path", "description"}


def find_artifact_by_property(
    session: Session,
    artifact_type: str,
    property_name: str,
    property_value: str,
) -> Optional[Dict[str, Any]]:
    """Find a single artifact by type and a unique property value.

    Returns the artifact dict, or None if not found.
    Raises ValueError if multiple matches found.
    Raises ValueError if property_name is not in ALLOWED_LOOKUP_PROPERTIES.
    """
    if property_name not in ALLOWED_LOOKUP_PROPERTIES:
        raise ValueError(
            f"Cannot search by property '{property_name}'. "
            f"Allowed: {ALLOWED_LOOKUP_PROPERTIES}"
        )
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', artifact_type):
        raise ValueError(f"Invalid artifact_type: '{artifact_type}'")
    cypher = (
        f"MATCH (a:Artifact:{artifact_type}) "
        f"WHERE a.{property_name} = $value "
        f"RETURN a"
    )
    records = session.run(cypher, value=property_value).data()
    if len(records) == 0:
        return None
    if len(records) > 1:
        raise ValueError(
            f"Multiple {artifact_type} artifacts with {property_name}='{property_value}'. "
            f"Use --script-id with the exact UUID."
        )
    return dict(records[0]["a"])


def find_any_artifact_by_name(
    session: Session,
    name: str,
) -> Optional[Dict[str, Any]]:
    """Find any artifact by its 'name' property across all types.

    Returns the artifact dict, or None if not found.
    Raises ValueError if multiple matches found.
    """
    records = session.run(
        "MATCH (a:Artifact) WHERE a.name = $name RETURN a",
        name=name,
    ).data()
    if len(records) == 0:
        return None
    if len(records) > 1:
        raise ValueError(
            f"Multiple artifacts with name='{name}'. Use --from-id with the exact UUID."
        )
    return dict(records[0]["a"])


def create_indexes(session: Session) -> None:
    """Create indexes on Artifact nodes. Called once during `seldon init`."""
    session.run(
        "CREATE INDEX artifact_id IF NOT EXISTS FOR (a:Artifact) ON (a.artifact_id)"
    )
    session.run(
        "CREATE INDEX artifact_type IF NOT EXISTS FOR (a:Artifact) ON (a.artifact_type)"
    )
    session.run(
        "CREATE INDEX artifact_state IF NOT EXISTS FOR (a:Artifact) ON (a.state)"
    )
