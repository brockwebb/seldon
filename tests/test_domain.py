import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config, validate_artifact_type, validate_relationship

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def research_config():
    return load_domain_config(RESEARCH_YAML)


def test_load_domain_config(research_config):
    assert research_config.domain == "research"
    assert research_config.version == "0.1"
    assert "Result" in research_config.artifact_types
    assert "ResearchTask" in research_config.artifact_types
    assert len(research_config.artifact_types) == 10  # dict with 10 keys


def test_validate_artifact_type_valid(research_config):
    # Must not raise
    validate_artifact_type(research_config, "Result")
    validate_artifact_type(research_config, "Script")
    validate_artifact_type(research_config, "DataFile")


def test_validate_artifact_type_invalid(research_config):
    with pytest.raises(ValueError, match="Unknown artifact type"):
        validate_artifact_type(research_config, "Unicorn")


def test_validate_relationship_valid(research_config):
    # PaperSection -[cites]-> Result is valid
    validate_relationship(research_config, "cites", "PaperSection", "Result")
    # Result -[generated_by]-> Script is valid
    validate_relationship(research_config, "generated_by", "Result", "Script")


def test_validate_relationship_invalid_type(research_config):
    with pytest.raises(ValueError, match="Unknown relationship type"):
        validate_relationship(research_config, "invented_rel", "Result", "Script")


def test_validate_relationship_invalid_from(research_config):
    with pytest.raises(ValueError, match="cannot originate"):
        # Script cannot cite (only PaperSection and Figure can)
        validate_relationship(research_config, "cites", "Script", "Result")


def test_validate_relationship_invalid_to(research_config):
    with pytest.raises(ValueError, match="cannot target"):
        # cites can only go to Result or Citation, not Script
        validate_relationship(research_config, "cites", "PaperSection", "Script")


def test_state_machine_loaded(research_config):
    assert "Result" in research_config.state_machines
    result_sm = research_config.state_machines["Result"]
    assert "proposed" in result_sm
    assert "verified" in result_sm["proposed"]


def test_get_initial_state(research_config):
    assert research_config.get_initial_state("Result") == "proposed"
    assert research_config.get_initial_state("ResearchTask") == "proposed"
