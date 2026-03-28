"""
Graph integration tests for AD-018 document structure types and relationships.

Requires Neo4j. Uses seldon-test database (cleaned before each test).
Tests create Table, PaperSection hierarchy, Figure with appears_in edges,
and verify traversal.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.domain.loader import load_domain_config

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def test_create_table_artifact(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Create a Table artifact; verify it exists in graph with correct labels."""
    table_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Table",
        properties={
            "name": "table_comparison",
            "caption": "Comparison of fitness functions across seed counts",
        },
        actor="human",
        authority="accepted",
    )
    assert table_id is not None

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (t:Artifact:Table {artifact_id: $id}) RETURN t",
            id=table_id,
        ).single()
    assert result is not None
    node = dict(result["t"])
    assert node["name"] == "table_comparison"
    assert node["caption"] == "Comparison of fitness functions across seed counts"
    assert node["state"] == "proposed"


def test_create_hierarchy(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Create chapter (depth 0) + section (depth 1), link via contains_section, verify traversal."""
    chapter_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={
            "name": "chapter_02",
            "title": "Methods",
            "depth": 0,
            "sequence": 2,
        },
        actor="human",
        authority="accepted",
    )

    section_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={
            "name": "section_02_01",
            "title": "Fitness Functions",
            "depth": 1,
            "sequence": 1,
        },
        actor="human",
        authority="accepted",
    )

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=chapter_id,
        to_id=section_id,
        from_type="PaperSection",
        to_type="PaperSection",
        rel_type="contains_section",
        actor="human",
        authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (ch:PaperSection {artifact_id: $ch_id})-[:CONTAINS_SECTION]->(sec:PaperSection) "
            "RETURN sec.name AS name",
            ch_id=chapter_id,
        ).data()
    assert len(result) == 1
    assert result[0]["name"] == "section_02_01"


def test_figure_appears_in_section(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Create Figure, link to PaperSection via appears_in, verify edge exists."""
    section_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={"name": "sec_results", "title": "Results"},
        actor="human",
        authority="accepted",
    )

    figure_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Figure",
        properties={
            "name": "fig_convergence",
            "caption": "Convergence curves for 4-terminal experiments",
            "description": "GP convergence over generations",
        },
        actor="human",
        authority="accepted",
    )

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=figure_id,
        to_id=section_id,
        from_type="Figure",
        to_type="PaperSection",
        rel_type="appears_in",
        actor="human",
        authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (f:Figure {artifact_id: $fid})-[:APPEARS_IN]->(s:PaperSection) "
            "RETURN s.name AS name",
            fid=figure_id,
        ).data()
    assert len(result) == 1
    assert result[0]["name"] == "sec_results"


def test_table_tabulates_result(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Create Table, link to Result via tabulates, verify edge exists."""
    result_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={
            "name": "accuracy_4t",
            "value": 0.95,
            "units": "fraction",
            "description": "Accuracy with 4 terminals",
        },
        actor="human",
        authority="accepted",
    )

    table_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Table",
        properties={
            "name": "table_accuracy",
            "caption": "Accuracy by terminal count",
        },
        actor="human",
        authority="accepted",
    )

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=table_id,
        to_id=result_id,
        from_type="Table",
        to_type="Result",
        rel_type="tabulates",
        actor="human",
        authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (t:Table {artifact_id: $tid})-[:TABULATES]->(r:Result) "
            "RETURN r.name AS name",
            tid=table_id,
        ).data()
    assert len(result) == 1
    assert result[0]["name"] == "accuracy_4t"


def test_cross_reference_edge(neo4j_driver, project_dir, domain_config, clean_test_db):
    """PaperSection -[references_figure]-> Figure edge exists after create_link."""
    section_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={"name": "sec_discussion", "title": "Discussion"},
        actor="human",
        authority="accepted",
    )
    figure_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Figure",
        properties={
            "name": "fig_comparison",
            "caption": "Comparison of search strategies",
            "description": "Side-by-side comparison",
        },
        actor="human",
        authority="accepted",
    )

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id,
        to_id=figure_id,
        from_type="PaperSection",
        to_type="Figure",
        rel_type="references_figure",
        actor="human",
        authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (s:PaperSection {artifact_id: $sid})-[:REFERENCES_FIGURE]->(f:Figure) "
            "RETURN f.name AS name",
            sid=section_id,
        ).data()
    assert len(result) == 1
    assert result[0]["name"] == "fig_comparison"


def test_staleness_traversal_through_table(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Result goes stale → Table that tabulates it can be found via downstream traversal."""
    result_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={
            "name": "metric_old",
            "value": 0.8,
            "units": "fraction",
            "description": "Old metric",
        },
        actor="human",
        authority="accepted",
    )
    transition_state(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=result_id,
        artifact_type="Result",
        current_state="proposed",
        new_state="verified",
        actor="human",
        authority="accepted",
    )
    transition_state(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=result_id,
        artifact_type="Result",
        current_state="verified",
        new_state="stale",
        actor="human",
        authority="accepted",
    )

    table_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Table",
        properties={"name": "table_old_metrics", "caption": "Old metrics table"},
        actor="human",
        authority="accepted",
    )
    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=table_id,
        to_id=result_id,
        from_type="Table",
        to_type="Result",
        rel_type="tabulates",
        actor="human",
        authority="accepted",
    )

    from seldon.core.graph import get_dependents
    with neo4j_driver.session(database=NEO4J_DB) as session:
        dependents = get_dependents(session, result_id)
    dep_names = [d["name"] for d in dependents]
    assert "table_old_metrics" in dep_names


def test_section_references_table_edge(neo4j_driver, project_dir, domain_config, clean_test_db):
    """PaperSection -[references_table]-> Table edge created and traversable."""
    section_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={"name": "sec_results", "title": "Results"},
        actor="human",
        authority="accepted",
    )
    table_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Table",
        properties={"name": "table_summary", "caption": "Summary statistics"},
        actor="human",
        authority="accepted",
    )
    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id,
        to_id=table_id,
        from_type="PaperSection",
        to_type="Table",
        rel_type="references_table",
        actor="human",
        authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        result = session.run(
            "MATCH (s:PaperSection {artifact_id: $sid})-[:REFERENCES_TABLE]->(t:Table) "
            "RETURN t.name AS name",
            sid=section_id,
        ).data()
    assert len(result) == 1
    assert result[0]["name"] == "table_summary"
