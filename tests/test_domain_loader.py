"""Tests for domain config loader — schema validation without Neo4j."""
from pathlib import Path

from seldon.domain.loader import load_domain_config

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


def test_remediated_by_edge_registered():
    """75.4 — remediated_by edge from Issue to change-carrying artifacts."""
    cfg = load_domain_config(RESEARCH_YAML)
    rels = cfg.relationship_types if hasattr(cfg, "relationship_types") else cfg["relationship_types"]

    assert "remediated_by" in rels
    spec = rels["remediated_by"]
    from_types = spec["from_types"] if isinstance(spec, dict) else spec.from_types
    to_types = spec["to_types"] if isinstance(spec, dict) else spec.to_types

    assert from_types == ["Issue"]
    assert "PaperSection" in to_types
    assert "ResearchTask" in to_types
    assert "ArchitecturalDecision" in to_types
