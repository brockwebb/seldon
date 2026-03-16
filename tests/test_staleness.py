"""
Staleness propagation tests. Requires Neo4j.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact
from seldon.core.staleness import propagate_staleness

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_result(project_dir, neo4j_driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 1.0, "units": "score", "description": "test result"},
        actor="human", authority="accepted",
    )


def _make_section(project_dir, neo4j_driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "test_section", "title": "Test Section"},
        actor="human", authority="accepted",
    )


def test_propagate_staleness_marks_citing_draft_section(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    section_id = _make_section(project_dir, neo4j_driver, domain_config)

    # Advance section to draft
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=section_id,
        artifact_type="PaperSection", current_state="proposed", new_state="draft",
        actor="human", authority="accepted",
    )

    # Link section -[cites]-> result
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id, to_id=result_id,
        from_type="PaperSection", to_type="Result",
        rel_type="cites", actor="human", authority="accepted",
    )

    affected = propagate_staleness(
        driver=neo4j_driver, database=NEO4J_DB,
        project_dir=project_dir, domain_config=domain_config,
        artifact_id=result_id,
    )

    assert section_id in affected

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, section_id)
    assert node["state"] == "stale"


def test_propagate_staleness_returns_affected_ids(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    section1 = _make_section(project_dir, neo4j_driver, domain_config)
    section2 = _make_section(project_dir, neo4j_driver, domain_config)

    for s in [section1, section2]:
        transition_state(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=s,
            artifact_type="PaperSection", current_state="proposed", new_state="draft",
            actor="human", authority="accepted",
        )
        create_link(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config,
            from_id=s, to_id=result_id,
            from_type="PaperSection", to_type="Result",
            rel_type="cites", actor="human", authority="accepted",
        )

    affected = propagate_staleness(
        driver=neo4j_driver, database=NEO4J_DB,
        project_dir=project_dir, domain_config=domain_config,
        artifact_id=result_id,
    )

    assert section1 in affected
    assert section2 in affected
    assert len(affected) == 2


def test_propagate_staleness_skips_non_citing_artifacts(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    # Another result — not linked
    other_id = _make_result(project_dir, neo4j_driver, domain_config)

    affected = propagate_staleness(
        driver=neo4j_driver, database=NEO4J_DB,
        project_dir=project_dir, domain_config=domain_config,
        artifact_id=result_id,
    )

    assert other_id not in affected
    assert len(affected) == 0


def test_propagate_staleness_skips_proposed_section(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """PaperSection in 'proposed' state cannot go stale — skip it."""
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    section_id = _make_section(project_dir, neo4j_driver, domain_config)
    # section is in 'proposed' — state machine has no proposed→stale transition

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id, to_id=result_id,
        from_type="PaperSection", to_type="Result",
        rel_type="cites", actor="human", authority="accepted",
    )

    affected = propagate_staleness(
        driver=neo4j_driver, database=NEO4J_DB,
        project_dir=project_dir, domain_config=domain_config,
        artifact_id=result_id,
    )

    # PaperSection can't go stale from proposed, so it should not be affected
    assert section_id not in affected

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, section_id)
    assert node["state"] == "proposed"


def test_transition_to_stale_auto_propagates(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Transitioning a Result to stale should auto-propagate to citing sections."""
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    section_id = _make_section(project_dir, neo4j_driver, domain_config)

    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=section_id,
        artifact_type="PaperSection", current_state="proposed", new_state="draft",
        actor="human", authority="accepted",
    )
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id, to_id=result_id,
        from_type="PaperSection", to_type="Result",
        rel_type="cites", actor="human", authority="accepted",
    )

    # proposed → verified → stale
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="verified", new_state="stale",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, section_id)
    assert node["state"] == "stale"
