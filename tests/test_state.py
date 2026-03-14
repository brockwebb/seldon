import pytest
from seldon.core.state import validate_transition, InvalidStateTransition
from seldon.domain.loader import load_domain_config
from pathlib import Path

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def test_valid_transition_result(domain_config):
    # Must not raise
    validate_transition(domain_config, "Result", "proposed", "verified")
    validate_transition(domain_config, "Result", "verified", "published")
    validate_transition(domain_config, "Result", "verified", "stale")
    validate_transition(domain_config, "Result", "stale", "verified")


def test_valid_transition_research_task(domain_config):
    validate_transition(domain_config, "ResearchTask", "proposed", "accepted")
    validate_transition(domain_config, "ResearchTask", "accepted", "in_progress")
    validate_transition(domain_config, "ResearchTask", "in_progress", "completed")
    validate_transition(domain_config, "ResearchTask", "in_progress", "blocked")
    validate_transition(domain_config, "ResearchTask", "blocked", "in_progress")


def test_invalid_transition_raises(domain_config):
    with pytest.raises(InvalidStateTransition) as exc_info:
        validate_transition(domain_config, "Result", "proposed", "published")
    error = exc_info.value
    assert "published" in str(error)
    assert "proposed" in str(error)
    # Error message must list the valid options
    assert "verified" in str(error)
    assert "rejected" in str(error)


def test_terminal_state_raises(domain_config):
    """Transitioning from a terminal state (empty list) must raise."""
    with pytest.raises(InvalidStateTransition) as exc_info:
        validate_transition(domain_config, "Result", "rejected", "proposed")
    assert "terminal" in str(exc_info.value).lower() or "no valid" in str(exc_info.value).lower()


def test_invalid_artifact_type_raises(domain_config):
    with pytest.raises(ValueError, match="No state machine"):
        validate_transition(domain_config, "Unicorn", "proposed", "verified")


def test_unknown_current_state_raises(domain_config):
    with pytest.raises(ValueError, match="Unknown state"):
        validate_transition(domain_config, "Result", "flying", "verified")


def test_invalid_state_transition_carries_valid_options(domain_config):
    """InvalidStateTransition.valid_transitions must be populated."""
    with pytest.raises(InvalidStateTransition) as exc_info:
        validate_transition(domain_config, "ResearchTask", "proposed", "completed")
    assert exc_info.value.valid_transitions == ["accepted", "rejected"]
