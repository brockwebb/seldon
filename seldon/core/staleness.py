from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from neo4j import Driver

from seldon.core.state import InvalidStateTransition
from seldon.domain.loader import DomainConfig


def propagate_staleness(
    driver: Driver,
    database: str,
    project_dir: Path,
    domain_config: DomainConfig,
    artifact_id: str,
    actor: str = "system",
    session_id: Optional[str] = None,
) -> List[str]:
    """
    Find all downstream artifacts that CITES the given artifact.
    Transition each to 'stale' if the state machine permits it.

    Returns list of affected artifact_ids.

    Called automatically by artifacts.transition_state when new_state == 'stale'.
    Validation is best-effort: artifacts whose state machine does not permit
    a transition to 'stale' are silently skipped.
    """
    # Lazy import to avoid circular dependency (staleness → artifacts → staleness)
    from seldon.core.artifacts import transition_state
    from seldon.core.state import validate_transition

    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (downstream:Artifact)-[:CITES]->(target:Artifact {artifact_id: $id}) "
            "RETURN downstream",
            id=artifact_id,
        ).data()

    affected: List[str] = []

    for r in records:
        downstream: Dict[str, Any] = dict(r["downstream"])
        ds_id = downstream["artifact_id"]
        ds_type = downstream.get("artifact_type", "")
        ds_state = downstream.get("state", "")

        # Skip if this type/state cannot transition to stale
        try:
            validate_transition(domain_config, ds_type, ds_state, "stale")
        except (InvalidStateTransition, ValueError):
            continue

        transition_state(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_id=ds_id,
            artifact_type=ds_type,
            current_state=ds_state,
            new_state="stale",
            actor=actor,
            authority="accepted",
            session_id=session_id,
        )
        affected.append(ds_id)

    return affected
