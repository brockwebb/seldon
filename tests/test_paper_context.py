"""
Tests for semantic anchor schema and seldon paper context command.

Covers:
  - New PaperSection properties accepted at creation time
  - List-valued properties round-trip through Neo4j
  - `assumes` relationship creation with topic/strength properties
  - paper context output (text and YAML) for a small section graph
  - Graceful output when a section has no anchor properties
"""
from __future__ import annotations

import pytest
from pathlib import Path

from seldon.core.artifacts import create_artifact, create_link
from seldon.core.graph import get_artifact
from seldon.domain.loader import load_domain_config
from seldon.paper.context import (
    get_section_context,
    format_context_text,
    format_context_yaml,
)

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
NEO4J_DB = "seldon-test"

needs_neo4j = pytest.mark.usefixtures("neo4j_available")


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_section(project_dir, neo4j_driver, domain_config, name, title, extra_props=None):
    props = {"name": name, "title": title}
    if extra_props:
        props.update(extra_props)
    return create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties=props,
        actor="test",
        authority="accepted",
    )


# ── Unit tests (no Neo4j) ─────────────────────────────────────────────────────

def test_schema_loads_new_properties(domain_config):
    """New anchor properties should appear in the domain config for PaperSection."""
    props = domain_config.get_all_schema_properties("PaperSection")
    assert "core_argument" in props
    assert "claims" in props
    assert "terminology_defined" in props
    assert "forward_promises" in props
    assert "open_threads" in props
    assert "anchor_date" in props
    assert "anchor_source" in props


def test_assumes_relationship_in_domain_config(domain_config):
    """assumes relationship type must be defined PaperSection -> PaperSection."""
    # validate_relationship raises ValueError if the relationship type is unknown
    # or the types are wrong — no exception means it's valid
    from seldon.domain.loader import validate_relationship
    validate_relationship(domain_config, "assumes", "PaperSection", "PaperSection")


def test_format_context_text_no_anchors():
    """format_context_text works when anchor properties are absent."""
    ctx = {
        "section": {"name": "chapter-01", "title": "Introduction"},
        "assumes": [],
        "assumed_by": [],
        "cross_references_out": [],
        "cross_references_in": [],
        "siblings": [],
    }
    text = format_context_text(ctx)
    assert "chapter-01" in text
    assert "Introduction" in text
    assert "(not set)" in text


def test_format_context_text_with_anchors():
    """format_context_text renders all populated anchor blocks."""
    ctx = {
        "section": {
            "name": "chapter-07",
            "title": "Checkpoints, Failures, and Recovery",
            "core_argument": "Defensive patterns protect the development process.",
            "claims": ["Error classification: transient, permanent, data-dependent"],
            "terminology_defined": ["recursive stochasticity: the development tools themselves are non-deterministic"],
            "forward_promises": ["chapter-09: drift detection"],
            "open_threads": ["Mid-run config changes — deferred"],
        },
        "assumes": [
            {
                "artifact": {"name": "chapter-06", "title": "Parallel Batch Architecture"},
                "rel_props": {"topic": "exponential backoff", "strength": "strong"},
            }
        ],
        "assumed_by": [
            {
                "artifact": {"name": "chapter-09", "title": "State Management"},
                "rel_props": {"topic": "thought experiment callback", "strength": "strong"},
            }
        ],
        "cross_references_out": [{"name": "chapter-09", "title": "State Management"}],
        "cross_references_in": [{"name": "chapter-06", "title": "Parallel Batch Architecture"}],
        "siblings": [],
    }
    text = format_context_text(ctx)
    assert "chapter-07" in text
    assert "Defensive patterns" in text
    assert "Error classification" in text
    assert "recursive stochasticity" in text
    assert "chapter-09: drift detection" in text
    assert "Mid-run config changes" in text
    assert "chapter-06" in text
    assert "exponential backoff" in text
    assert "[strong]" in text
    assert "thought experiment callback" in text


def test_format_context_yaml_structure():
    """format_context_yaml returns valid YAML with expected top-level keys."""
    import yaml as yaml_lib
    ctx = {
        "section": {"name": "chapter-01", "title": "Intro"},
        "assumes": [],
        "assumed_by": [],
        "cross_references_out": [],
        "cross_references_in": [],
        "siblings": [],
    }
    output = format_context_yaml(ctx)
    parsed = yaml_lib.safe_load(output)
    assert "section" in parsed
    assert "assumes" in parsed
    assert "assumed_by" in parsed
    assert parsed["section"]["name"] == "chapter-01"


# ── Integration tests (Neo4j required) ───────────────────────────────────────

@needs_neo4j
class TestContextIntegration:
    def test_new_properties_accepted_at_creation(
        self, project_dir, neo4j_driver, domain_config, clean_test_db
    ):
        """New anchor properties should be persisted and retrievable."""
        artifact_id = _make_section(
            project_dir, neo4j_driver, domain_config,
            name="chapter-03",
            title="Methods",
            extra_props={"core_argument": "Methods justify the design."},
        )
        artifact = get_artifact(neo4j_driver.session(database=NEO4J_DB), artifact_id)
        assert artifact["core_argument"] == "Methods justify the design."

    def test_list_property_round_trip(
        self, project_dir, neo4j_driver, domain_config, clean_test_db
    ):
        """List-valued properties (claims, terminology_defined, etc.) round-trip correctly."""
        claims = ["Claim A is valid", "Claim B follows from A"]
        terms = ["stochasticity: variance in outputs given identical inputs"]
        artifact_id = _make_section(
            project_dir, neo4j_driver, domain_config,
            name="chapter-04",
            title="Results",
            extra_props={"claims": claims, "terminology_defined": terms},
        )
        with neo4j_driver.session(database=NEO4J_DB) as session:
            artifact = get_artifact(session, artifact_id)
        assert artifact["claims"] == claims
        assert artifact["terminology_defined"] == terms

    def test_assumes_relationship_creation_with_properties(
        self, project_dir, neo4j_driver, domain_config, clean_test_db
    ):
        """assumes edge should be created with topic and strength properties on the relationship."""
        id_a = _make_section(project_dir, neo4j_driver, domain_config, "chapter-06", "Batching")
        id_b = _make_section(project_dir, neo4j_driver, domain_config, "chapter-07", "Recovery")

        create_link(
            project_dir=project_dir,
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
            from_id=id_b,
            to_id=id_a,
            from_type="PaperSection",
            to_type="PaperSection",
            rel_type="assumes",
            actor="test",
            authority="accepted",
            rel_properties={"topic": "exponential backoff", "strength": "strong"},
        )

        with neo4j_driver.session(database=NEO4J_DB) as session:
            record = session.run(
                "MATCH (b:PaperSection {name: 'chapter-07'})"
                "-[r:ASSUMES]->(a:PaperSection {name: 'chapter-06'}) "
                "RETURN properties(r) AS props"
            ).single()
        assert record is not None
        props = record["props"]
        assert props["topic"] == "exponential backoff"
        assert props["strength"] == "strong"

    def test_paper_context_full_graph(
        self, project_dir, neo4j_driver, domain_config, clean_test_db
    ):
        """get_section_context returns all relationship types for a section."""
        id_06 = _make_section(
            project_dir, neo4j_driver, domain_config, "chapter-06", "Batching",
            extra_props={"depth": 0, "core_argument": "Batching enables scale."},
        )
        id_07 = _make_section(
            project_dir, neo4j_driver, domain_config, "chapter-07", "Recovery",
            extra_props={
                "depth": 0,
                "core_argument": "Defensive patterns protect the process.",
                "claims": ["Transient errors are retriable"],
            },
        )
        id_09 = _make_section(
            project_dir, neo4j_driver, domain_config, "chapter-09", "State",
            extra_props={"depth": 0},
        )

        # chapter-07 ASSUMES chapter-06
        create_link(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config,
            from_id=id_07, to_id=id_06,
            from_type="PaperSection", to_type="PaperSection",
            rel_type="assumes", actor="test", authority="accepted",
            rel_properties={"topic": "backoff strategy", "strength": "strong"},
        )
        # chapter-09 ASSUMES chapter-07
        create_link(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config,
            from_id=id_09, to_id=id_07,
            from_type="PaperSection", to_type="PaperSection",
            rel_type="assumes", actor="test", authority="accepted",
            rel_properties={"topic": "error taxonomy", "strength": "moderate"},
        )
        # chapter-07 CROSS_REFERENCES chapter-09
        create_link(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config,
            from_id=id_07, to_id=id_09,
            from_type="PaperSection", to_type="PaperSection",
            rel_type="cross_references", actor="test", authority="accepted",
        )

        ctx = get_section_context(neo4j_driver, NEO4J_DB, "chapter-07")
        assert ctx is not None
        assert ctx["section"]["name"] == "chapter-07"
        assert ctx["section"]["core_argument"] == "Defensive patterns protect the process."

        # assumes: chapter-07 -> chapter-06
        assert len(ctx["assumes"]) == 1
        assert ctx["assumes"][0]["artifact"]["name"] == "chapter-06"
        assert ctx["assumes"][0]["rel_props"]["topic"] == "backoff strategy"
        assert ctx["assumes"][0]["rel_props"]["strength"] == "strong"

        # assumed_by: chapter-09 -> chapter-07
        assert len(ctx["assumed_by"]) == 1
        assert ctx["assumed_by"][0]["artifact"]["name"] == "chapter-09"
        assert ctx["assumed_by"][0]["rel_props"]["strength"] == "moderate"

        # cross_references_out: chapter-07 -> chapter-09
        assert any(a["name"] == "chapter-09" for a in ctx["cross_references_out"])

        # siblings: chapter-06 and chapter-09 are at same depth=0
        sibling_names = {s["name"] for s in ctx["siblings"]}
        assert "chapter-06" in sibling_names
        assert "chapter-09" in sibling_names
        assert "chapter-07" not in sibling_names

    def test_paper_context_missing_anchors_graceful(
        self, project_dir, neo4j_driver, domain_config, clean_test_db
    ):
        """get_section_context returns a valid ctx even when anchor props are absent."""
        _make_section(project_dir, neo4j_driver, domain_config, "chapter-01", "Intro")
        ctx = get_section_context(neo4j_driver, NEO4J_DB, "chapter-01")
        assert ctx is not None
        assert ctx["section"]["name"] == "chapter-01"
        assert ctx["section"].get("core_argument") is None
        assert ctx["assumes"] == []
        # format_context_text should not raise
        text = format_context_text(ctx)
        assert "(not set)" in text

    def test_paper_context_not_found(
        self, neo4j_driver, domain_config, clean_test_db
    ):
        """get_section_context returns None for an unknown section name."""
        ctx = get_section_context(neo4j_driver, NEO4J_DB, "chapter-99-nonexistent")
        assert ctx is None
