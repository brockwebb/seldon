from __future__ import annotations

from typing import List

from seldon.domain.loader import DomainConfig


class InvalidStateTransition(Exception):
    """Raised when a state transition is not permitted by the state machine."""

    def __init__(
        self,
        artifact_type: str,
        current_state: str,
        attempted_state: str,
        valid_transitions: List[str],
    ):
        self.artifact_type = artifact_type
        self.current_state = current_state
        self.attempted_state = attempted_state
        self.valid_transitions = valid_transitions

        if not valid_transitions:
            message = (
                f"Cannot transition '{artifact_type}' from '{current_state}': "
                f"this is a terminal state with no valid transitions."
            )
        else:
            message = (
                f"Invalid transition for '{artifact_type}': "
                f"'{current_state}' → '{attempted_state}'. "
                f"Valid transitions from '{current_state}': {valid_transitions}"
            )
        super().__init__(message)


def validate_transition(
    domain_config: DomainConfig,
    artifact_type: str,
    current_state: str,
    new_state: str,
) -> None:
    """
    Validate that transitioning artifact_type from current_state to new_state
    is permitted by the domain's state machine.

    Raises:
        ValueError: if the artifact_type has no state machine or current_state is unknown.
        InvalidStateTransition: if the transition is not permitted.
    """
    state_machines = domain_config.state_machines
    if artifact_type not in state_machines:
        raise ValueError(
            f"No state machine defined for artifact type: '{artifact_type}'. "
            f"Types with state machines: {sorted(state_machines.keys())}"
        )

    sm = state_machines[artifact_type]
    if current_state not in sm:
        raise ValueError(
            f"Unknown state '{current_state}' for artifact type '{artifact_type}'. "
            f"Known states: {sorted(sm.keys())}"
        )

    valid_transitions = sm[current_state]
    if new_state not in valid_transitions:
        raise InvalidStateTransition(
            artifact_type=artifact_type,
            current_state=current_state,
            attempted_state=new_state,
            valid_transitions=valid_transitions,
        )
