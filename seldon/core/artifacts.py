from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from neo4j import Driver

from seldon.domain.loader import (
    DomainConfig,
    validate_artifact_type,
    validate_relationship,
    validate_relationship_properties,
)
from seldon.core.state import validate_transition
from seldon.core.events import append_event, make_event
from seldon.core import graph, precedence

# AD-028 — ResearchTask lifecycle semantics.
#
# CLAIM_TRANSITION is the single edge in the ResearchTask state machine that means
# "an agent has taken ownership of this work". It is domain semantics, not a tunable:
# the state names come from `seldon/domain/research.yaml`, and if that machine ever
# renames the edge this constant must move with it.
CLAIM_TRANSITION = ("accepted", "in_progress")

# Terminal states that record *why* the task ended rather than *that* it ended.
# `rejected` and `verified` are terminal too but carry their meaning in the state
# name alone; `withdrawn` (premise turned out false) and `superseded` (something
# else overtook the work) are indistinguishable without an operator-supplied reason.
REASON_REQUIRED_STATES = ("withdrawn", "superseded")

# Relationship written by `seldon task supersede --superseded-by`.
SUPERSEDED_BY_REL = "superseded_by"


def _now_iso() -> str:
    """ISO-8601 UTC timestamp for updated_at."""
    return datetime.now(timezone.utc).isoformat()


def validate_snapshot_property(properties: Dict[str, Any]) -> None:
    """Reject a non-boolean ``snapshot`` value (AD-027).

    ``snapshot`` is a cross-type artifact property: True means the artifact records a
    file as it stood at registration, so its ``content_hash`` is the identity of that
    state and the live file is expected to diverge. Absence means False. Anything other
    than a real bool is refused here so that a string such as ``"yes"`` can never be
    stored and later read as truthy by ``seldon verify``.

    Raises:
        ValueError: If ``snapshot`` is present and not a bool.
    """
    if "snapshot" in properties and not isinstance(properties["snapshot"], bool):
        raise ValueError(
            f"Property 'snapshot' must be a boolean (true/false), "
            f"got {properties['snapshot']!r}"
        )


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
    validate_snapshot_property(properties)

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

    now = _now_iso()
    props = dict(properties)
    props["artifact_id"] = artifact_id
    props["state"] = initial_state
    props["authority"] = authority
    props["created_by"] = actor
    props.setdefault("created_at", now)
    props["updated_at"] = now

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
            shared_ontology.inheritance configured as "read-only", or if ``snapshot``
            is present and not a bool.
    """
    validate_snapshot_property(properties)

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

    properties = dict(properties)
    properties["updated_at"] = _now_iso()

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
        graph.update_artifact(session, artifact_id, {"updated_at": _now_iso()})

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

    Every precondition is checked before the first write, so a rejected call
    leaves nothing in the event log or the graph.

    Args:
        rel_properties: Optional properties to set on the relationship itself
            (e.g., topic and strength for `assumes` edges).

    Raises:
        ValueError: If the endpoints are illegal for the relationship type, if a
            declared edge-property schema is violated, or — for `precedes` — if
            the edge would be a self-loop or close a cycle (AD-029).
    """
    validate_relationship(domain_config, rel_type, from_type, to_type)

    props = rel_properties or {}
    validate_relationship_properties(domain_config, rel_type, props)

    # The DAG invariant is enforced here rather than in the CLI so that every
    # write path reaches it, `seldon link create` included (AD-029).
    if rel_type == precedence.REL_TYPE:
        precedence.validate_precedes_write(driver, database, from_id, to_id)

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


def _state_machine(domain_config: DomainConfig, artifact_type: str) -> Dict[str, list]:
    """Return the state machine for ``artifact_type``.

    Args:
        domain_config: Loaded domain configuration.
        artifact_type: Artifact type to look up.

    Returns:
        Mapping of state name to its list of permitted successor states.

    Raises:
        ValueError: If the domain config defines no state machine for the type.
    """
    machines = domain_config.state_machines
    if artifact_type not in machines:
        raise ValueError(
            f"No state machine defined for artifact type: '{artifact_type}'. "
            f"Types with state machines: {sorted(machines.keys())}"
        )
    return machines[artifact_type]


def terminal_states(domain_config: DomainConfig, artifact_type: str) -> List[str]:
    """States of ``artifact_type`` from which no further transition is possible.

    Derived from the domain config's state machine rather than enumerated in code, so
    adding a terminal state to ``research.yaml`` needs no corresponding code change.

    Args:
        domain_config: Loaded domain configuration.
        artifact_type: Artifact type whose state machine is inspected.

    Returns:
        Sorted list of terminal state names.

    Raises:
        ValueError: If the domain config defines no state machine for the type.
    """
    machine = _state_machine(domain_config, artifact_type)
    return sorted(state for state, successors in machine.items() if not successors)


def open_states(domain_config: DomainConfig, artifact_type: str) -> List[str]:
    """States of ``artifact_type`` in which live work is still possible.

    A state is *open* when it is not itself terminal **and** at least one of its
    successors is not terminal — the artifact can still move somewhere that is not an
    ending. For ``ResearchTask`` this derives ``{proposed, accepted, in_progress,
    blocked}`` from ``research.yaml``: ``completed`` is excluded because its only
    successor, ``verified``, is terminal. Deriving the set means a terminal state added
    to the config drops out of default listings without a code change (AD-028).

    Args:
        domain_config: Loaded domain configuration.
        artifact_type: Artifact type whose state machine is inspected.

    Returns:
        Sorted list of open state names.

    Raises:
        ValueError: If the domain config defines no state machine for the type.
    """
    machine = _state_machine(domain_config, artifact_type)
    terminal = set(terminal_states(domain_config, artifact_type))
    return sorted(
        state
        for state, successors in machine.items()
        if state not in terminal and any(s not in terminal for s in successors)
    )


def resolve_artifact_id(driver: Driver, database: str, id_prefix: str) -> str:
    """Resolve a full artifact_id or unambiguous prefix to a single artifact_id.

    Args:
        driver: Neo4j driver.
        database: Database name to query.
        id_prefix: Full UUID or leading prefix of one.

    Returns:
        The full artifact_id.

    Raises:
        ValueError: If nothing matches, or if the prefix matches more than one
            artifact (the message lists the candidates).
    """
    if not id_prefix or not id_prefix.strip():
        raise ValueError("An artifact id (or id prefix) is required.")

    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (a:Artifact) WHERE a.artifact_id STARTS WITH $prefix "
            "RETURN a.artifact_id AS id",
            prefix=id_prefix.strip(),
        ).data()

    if not records:
        raise ValueError(f"No artifact found matching '{id_prefix}'.")
    if len(records) > 1:
        candidates = ", ".join(sorted(r["id"] for r in records))
        raise ValueError(
            f"'{id_prefix}' matches {len(records)} artifacts — use a longer prefix: "
            f"{candidates}"
        )
    return records[0]["id"]


def transition_task(
    project_dir: Path,
    driver: Driver,
    database: str,
    domain_config: DomainConfig,
    artifact_id: str,
    current_state: str,
    new_state: str,
    actor: str,
    authority: str = "accepted",
    session_id: Optional[str] = None,
    claimed_by: Optional[str] = None,
    terminal_reason: Optional[str] = None,
    superseded_by: Optional[str] = None,
) -> List[str]:
    """Transition a ResearchTask, applying the AD-028 lifecycle side effects.

    Wraps :func:`transition_state` with the two ResearchTask-specific behaviours that
    the plain state machine cannot express:

    * ``accepted -> in_progress`` records ``claimed_by`` and ``claimed_at`` so a
      stale claim can be *reported* (never auto-released).
    * ``withdrawn`` and ``superseded`` require a ``terminal_reason``, and
      ``superseded`` may additionally point at the artifact that overtook the task
      via a ``superseded_by`` edge.

    Every precondition is checked before the first event is appended, so a rejected
    call leaves no trace: an unknown ``superseded_by`` target, an illegal edge
    endpoint, a missing reason, or an illegal transition all raise with no state
    change and no event written.

    Args:
        project_dir: Project root, for the JSONL event store.
        driver: Neo4j driver.
        database: Database name.
        domain_config: Loaded domain configuration.
        artifact_id: Full artifact_id of the ResearchTask.
        current_state: The task's current state in the graph.
        new_state: State to transition to.
        actor: Actor string written to events (e.g. 'human', 'cc', 'desktop').
        authority: Authority string written to events.
        session_id: Optional Seldon session id recorded on the events.
        claimed_by: Agent identifier recorded on the claim transition. Defaults to
            ``actor``. Ignored (and rejected) on any other transition.
        terminal_reason: Why the task ended. Required for withdrawn/superseded,
            refused for every other target state.
        superseded_by: Optional artifact_id (or unambiguous prefix) of the artifact
            that overtook this task. Only valid when ``new_state`` is 'superseded'.

    Returns:
        Advisory warning lines the caller should surface — currently the AD-029
        `precedes` warning raised when work starts ahead of an unsatisfied
        predecessor. Empty when there is nothing to say. Advisory means
        advisory: the transition has already happened when these are returned.

    Raises:
        ValueError: If a required reason is missing, if a reason/claim/superseded_by
            argument is supplied for a transition it does not apply to, if the
            ``superseded_by`` target does not exist, or if the ``superseded_by`` edge
            endpoints are not permitted by the domain config.
        InvalidStateTransition: If the transition is not permitted by the state machine.
    """
    artifact_type = "ResearchTask"
    is_claim = (current_state, new_state) == CLAIM_TRANSITION

    # --- Precondition checks: everything that can fail must fail before any write ---
    if new_state in REASON_REQUIRED_STATES:
        if terminal_reason is None or not terminal_reason.strip():
            raise ValueError(
                f"Transition to '{new_state}' requires a reason. "
                f"A terminal state without a recorded reason is indistinguishable "
                f"from the other terminal states later."
            )
    elif terminal_reason is not None:
        raise ValueError(
            f"A terminal reason is only recorded for {list(REASON_REQUIRED_STATES)}, "
            f"not for a transition to '{new_state}'."
        )

    if superseded_by is not None and new_state != "superseded":
        raise ValueError(
            f"--superseded-by is only valid when superseding a task, "
            f"not for a transition to '{new_state}'."
        )

    if claimed_by is not None and not is_claim:
        raise ValueError(
            f"A claim is only recorded on the "
            f"'{CLAIM_TRANSITION[0]} -> {CLAIM_TRANSITION[1]}' transition, "
            f"not on '{current_state} -> {new_state}'."
        )

    superseded_by_id: Optional[str] = None
    superseded_by_type: Optional[str] = None
    if superseded_by is not None:
        # Raises ValueError naming the id when unknown or ambiguous.
        superseded_by_id = resolve_artifact_id(driver, database, superseded_by)
        with driver.session(database=database) as session:
            target = graph.get_artifact(session, superseded_by_id)
        if target is None:
            raise ValueError(f"Artifact '{superseded_by}' not found.")
        superseded_by_type = target.get("artifact_type")
        # Raises ValueError when the endpoint types are not legal for the edge.
        validate_relationship(
            domain_config, SUPERSEDED_BY_REL, artifact_type, superseded_by_type
        )

    validate_transition(domain_config, artifact_type, current_state, new_state)

    # Read before the writes: the question is whether it was legitimate to start
    # this task, which is a fact about the graph as it stood beforehand.
    warnings = precedence.transition_warnings(
        driver, database, artifact_id, new_state
    )

    # --- Writes: property event first, then the state event, then the edge ---
    properties: Dict[str, Any] = {}
    if new_state in REASON_REQUIRED_STATES:
        properties["terminal_reason"] = terminal_reason.strip()
    if is_claim:
        properties["claimed_by"] = (claimed_by or actor).strip()
        properties["claimed_at"] = _now_iso()

    if properties:
        update_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            artifact_id=artifact_id,
            properties=properties,
            actor=actor,
            authority=authority,
            session_id=session_id,
        )

    transition_state(
        project_dir=project_dir,
        driver=driver,
        database=database,
        domain_config=domain_config,
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        current_state=current_state,
        new_state=new_state,
        actor=actor,
        authority=authority,
        session_id=session_id,
    )

    if superseded_by_id is not None:
        create_link(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            from_id=artifact_id,
            to_id=superseded_by_id,
            from_type=artifact_type,
            to_type=superseded_by_type,
            rel_type=SUPERSEDED_BY_REL,
            actor=actor,
            authority=authority,
            session_id=session_id,
        )

    return warnings


def walk_to_completed(
    project_dir: Path,
    driver: Driver,
    database: str,
    domain_config,
    artifact_id: str,
    current_state: str,
    actor: str = "cc",
    session_id: Optional[str] = None,
    claimed_by: Optional[str] = None,
    on_warning: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """Walk a ResearchTask from current_state to completed.

    The single close walk shared by `seldon task close` and the MCP
    `seldon_task_close` tool, so both surfaces emit the same event sequence
    (AD-028). State-aware: skips transitions for states already passed.

    The walk crosses :data:`CLAIM_TRANSITION`, so closing a task that had not yet
    been claimed records the closer as the claimant.

    Args:
        project_dir: Project root, for the JSONL event store.
        driver: Neo4j driver.
        database: Database name.
        domain_config: Loaded domain configuration.
        artifact_id: Full artifact_id of the ResearchTask.
        current_state: The artifact's current state in the graph.
        actor: Actor string written to events ('human', 'cc' or 'desktop').
        session_id: Optional Seldon session id recorded on the events.
        claimed_by: Agent identifier recorded if the walk crosses the claim
            transition. Defaults to ``actor``.
        on_warning: Optional sink for advisory warnings raised along the walk
            (AD-029). A callback rather than a second return value so that the
            walk's return contract — the thing both surfaces render and the
            parity test compares — stays exactly what it was.

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
        step_warnings = transition_task(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_id=artifact_id,
            current_state=state,
            new_state=next_state,
            actor=actor,
            authority="accepted",
            session_id=session_id,
            claimed_by=claimed_by if (state, next_state) == CLAIM_TRANSITION else None,
        )
        if on_warning is not None:
            for line in step_warnings:
                on_warning(line)
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
