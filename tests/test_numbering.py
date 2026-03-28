"""
Tests for seldon/paper/numbering.py — figure/table number computation and XREF resolution.

Integration tests require Neo4j. Unit tests (resolve_xref_tokens) run without it.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from seldon.core.artifacts import create_artifact, create_link
from seldon.domain.loader import load_domain_config

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


# ---------------------------------------------------------------------------
# Integration tests: figure numbering
# ---------------------------------------------------------------------------

def test_figure_numbering_flat(neo4j_driver, project_dir, domain_config, clean_test_db):
    """No chapter structure: figures numbered 1, 2 by section sequence."""
    from seldon.paper.numbering import compute_figure_numbers

    sec1_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "sec_intro", "title": "Introduction", "sequence": 1},
        actor="human", authority="accepted",
    )
    sec2_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "sec_methods", "title": "Methods", "sequence": 2},
        actor="human", authority="accepted",
    )

    fig1_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Figure",
        properties={"name": "fig_a", "caption": "Fig A", "description": "First figure"},
        actor="human", authority="accepted",
    )
    fig2_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Figure",
        properties={"name": "fig_b", "caption": "Fig B", "description": "Second figure"},
        actor="human", authority="accepted",
    )

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, from_id=fig1_id, to_id=sec1_id,
        from_type="Figure", to_type="PaperSection",
        rel_type="appears_in", actor="human", authority="accepted",
    )
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, from_id=fig2_id, to_id=sec2_id,
        from_type="Figure", to_type="PaperSection",
        rel_type="appears_in", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        numbers = compute_figure_numbers(session, NEO4J_DB)

    assert fig1_id in numbers
    assert fig2_id in numbers
    values = sorted(numbers.values())
    assert values == ["1", "2"]


def test_figure_numbering_chaptered(neo4j_driver, project_dir, domain_config, clean_test_db):
    """With chapters (depth=0): figures numbered {chapter}.{n} within chapter."""
    from seldon.paper.numbering import compute_figure_numbers

    ch2_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "chapter_02", "title": "Methods", "depth": 0, "sequence": 2},
        actor="human", authority="accepted",
    )
    ch3_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "chapter_03", "title": "Results", "depth": 0, "sequence": 3},
        actor="human", authority="accepted",
    )
    sec21_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "sec_2_1", "title": "Setup", "depth": 1, "sequence": 1},
        actor="human", authority="accepted",
    )
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, from_id=ch2_id, to_id=sec21_id,
        from_type="PaperSection", to_type="PaperSection",
        rel_type="contains_section", actor="human", authority="accepted",
    )

    fig_ch2_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Figure",
        properties={"name": "fig_setup", "caption": "Experimental setup", "description": "GP setup"},
        actor="human", authority="accepted",
    )
    fig_ch3_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Figure",
        properties={"name": "fig_results", "caption": "Results comparison", "description": "Accuracy curves"},
        actor="human", authority="accepted",
    )

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, from_id=fig_ch2_id, to_id=sec21_id,
        from_type="Figure", to_type="PaperSection",
        rel_type="appears_in", actor="human", authority="accepted",
    )
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, from_id=fig_ch3_id, to_id=ch3_id,
        from_type="Figure", to_type="PaperSection",
        rel_type="appears_in", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        numbers = compute_figure_numbers(session, NEO4J_DB)

    assert numbers[fig_ch2_id] == "2.1"
    assert numbers[fig_ch3_id] == "3.1"


def test_table_numbering_flat(neo4j_driver, project_dir, domain_config, clean_test_db):
    """No chapter structure: table numbered 1."""
    from seldon.paper.numbering import compute_table_numbers

    sec_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "sec_results", "title": "Results", "sequence": 3},
        actor="human", authority="accepted",
    )
    tbl_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Table",
        properties={"name": "tbl_summary", "caption": "Summary"},
        actor="human", authority="accepted",
    )
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, from_id=tbl_id, to_id=sec_id,
        from_type="Table", to_type="PaperSection",
        rel_type="appears_in", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        numbers = compute_table_numbers(session, NEO4J_DB)

    assert tbl_id in numbers
    assert numbers[tbl_id] == "1"


# ---------------------------------------------------------------------------
# Unit tests: resolve_xref_tokens (no Neo4j, but pytestmark applies)
# ---------------------------------------------------------------------------

def test_resolve_xref_tokens_figure():
    """{{figure:NAME}} resolves to 'Figure 2.1'."""
    from seldon.paper.numbering import resolve_xref_tokens

    figure_by_name = {"fig_setup": "2.1"}
    text = "As shown in {{figure:fig_setup}}, the results are clear."
    result = resolve_xref_tokens(text, figure_by_name, {}, {})
    assert result == "As shown in Figure 2.1, the results are clear."


def test_resolve_xref_tokens_table():
    """{{table:NAME}} resolves to 'Table 3.1'."""
    from seldon.paper.numbering import resolve_xref_tokens

    table_by_name = {"tbl_summary": "3.1"}
    text = "See {{table:tbl_summary}} for details."
    result = resolve_xref_tokens(text, {}, table_by_name, {})
    assert result == "See Table 3.1 for details."


def test_resolve_xref_tokens_section():
    """{{section:NAME}} resolves to display string from section_by_name dict."""
    from seldon.paper.numbering import resolve_xref_tokens

    section_by_name = {
        "chapter_03": "Chapter 3",
        "sec_3_2": "Section 3.2",
    }
    text = "As described in {{section:chapter_03}} and {{section:sec_3_2}}."
    result = resolve_xref_tokens(text, {}, {}, section_by_name)
    assert result == "As described in Chapter 3 and Section 3.2."
