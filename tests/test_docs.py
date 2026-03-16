"""
Unit tests for AD-013 schema extension.
Tests DomainConfig with dict-format artifact_types, property helpers,
and required property validation.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import (
    load_domain_config, validate_artifact_type, DomainConfig,
    PropertyDef, ArtifactTypeConfig,
)

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def research_config():
    return load_domain_config(RESEARCH_YAML)


# ── Schema parsing ────────────────────────────────────────────────────────────

def test_artifact_types_is_dict(research_config):
    assert isinstance(research_config.artifact_types, dict)


def test_artifact_types_has_all_types(research_config):
    expected = {
        "Script", "Result", "DataFile", "Figure", "PipelineRun",
        "PaperSection", "Citation", "ResearchTask", "LabNotebookEntry", "SRS_Requirement",
    }
    assert set(research_config.artifact_types.keys()) == expected


def test_artifact_type_config_has_properties(research_config):
    script_config = research_config.artifact_types["Script"]
    assert isinstance(script_config, ArtifactTypeConfig)
    assert "name" in script_config.properties
    assert "path" in script_config.properties
    assert "description" in script_config.properties


def test_property_def_required_true(research_config):
    name_prop = research_config.artifact_types["Script"].properties["name"]
    assert name_prop.required is True
    assert name_prop.category == "required"


def test_property_def_documentation_category(research_config):
    desc_prop = research_config.artifact_types["Script"].properties["description"]
    assert desc_prop.required is False
    assert desc_prop.category == "documentation"


# ── get_required_properties ───────────────────────────────────────────────────

def test_get_required_properties_script(research_config):
    required = research_config.get_required_properties("Script")
    assert "name" in required
    assert "path" in required
    assert "description" not in required


def test_get_required_properties_result(research_config):
    required = research_config.get_required_properties("Result")
    assert "value" in required
    assert "units" in required
    assert "description" in required
    assert "interpretation" not in required


def test_get_required_properties_unknown_type(research_config):
    assert research_config.get_required_properties("Nonexistent") == []


# ── get_documentation_properties ──────────────────────────────────────────────

def test_get_documentation_properties_script(research_config):
    doc_props = research_config.get_documentation_properties("Script")
    assert "description" in doc_props
    assert "inputs" in doc_props
    assert "outputs" in doc_props
    assert "usage" in doc_props
    assert "name" not in doc_props  # name is required, not documentation


def test_get_documentation_properties_result(research_config):
    doc_props = research_config.get_documentation_properties("Result")
    assert "interpretation" in doc_props
    assert "methodology_note" in doc_props
    assert "value" not in doc_props  # value is required


def test_get_documentation_properties_unknown_type(research_config):
    assert research_config.get_documentation_properties("Nonexistent") == []


# ── get_all_schema_properties ────────────────────────────────────────────────

def test_get_all_schema_properties(research_config):
    all_props = research_config.get_all_schema_properties("Script")
    assert "name" in all_props
    assert "description" in all_props
    assert isinstance(all_props["name"], PropertyDef)


def test_get_all_schema_properties_unknown_type(research_config):
    assert research_config.get_all_schema_properties("Nonexistent") == {}


# ── validate_artifact_type with dict ─────────────────────────────────────────

def test_validate_artifact_type_works_with_dict(research_config):
    validate_artifact_type(research_config, "Result")   # must not raise
    validate_artifact_type(research_config, "Script")   # must not raise


def test_validate_artifact_type_invalid_still_raises(research_config):
    with pytest.raises(ValueError, match="Unknown artifact type"):
        validate_artifact_type(research_config, "Unicorn")


# ── state machine still works ─────────────────────────────────────────────────

def test_state_machine_validator_works_with_dict(research_config):
    assert "Result" in research_config.state_machines
    assert research_config.get_initial_state("Result") == "proposed"


def test_state_machine_unknown_type_raises():
    with pytest.raises(ValueError, match="State machine defined for unknown artifact type"):
        DomainConfig(
            domain="test",
            version="0.1",
            artifact_types={"Result": ArtifactTypeConfig()},
            relationship_types={},
            state_machines={
                "Result": {"proposed": ["verified"]},
                "UnknownType": {"proposed": []},  # not in artifact_types
            },
        )


# ── required property validation via create_artifact ─────────────────────────

def test_required_validation_missing_raises(neo4j_driver, project_dir, domain_config_fixture,
                                             clean_test_db):
    from seldon.core.artifacts import create_artifact
    with pytest.raises(ValueError, match="Missing required properties"):
        create_artifact(
            project_dir=project_dir,
            driver=neo4j_driver,
            database="seldon-test",
            domain_config=domain_config_fixture,
            artifact_type="Result",
            properties={"value": 1.0},  # missing units and description
            actor="human",
            authority="accepted",
        )


def test_required_validation_passes(neo4j_driver, project_dir, domain_config_fixture,
                                     clean_test_db):
    from seldon.core.artifacts import create_artifact
    artifact_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database="seldon-test",
        domain_config=domain_config_fixture,
        artifact_type="Result",
        properties={"value": 1.0, "units": "score", "description": "complete result"},
        actor="human",
        authority="accepted",
    )
    assert artifact_id is not None


# ── conftest fixtures used above ────────────────────────────────────────────

@pytest.fixture
def domain_config_fixture():
    return load_domain_config(RESEARCH_YAML)
