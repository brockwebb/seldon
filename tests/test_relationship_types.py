"""Endpoint-type contract for the provenance and commentary relationship types.

Covers the edge types extended or introduced by AD-028 (Lane B of the
2026-09-03 defect sweep):

    generated_by   Result | Figure | Table | DataFile  ->  Script
    computed_from  Result | DataFile                   ->  DataFile
    corrects       DesignNote                          ->  DesignNote | Result
    annotates      Issue                               ->  Result
    disputes       Issue                               ->  Result

Two layers are asserted:

1. `seldon.domain.loader.validate_relationship` — the validator in isolation,
   over the full accept/reject matrix. Cheap, no Neo4j.
2. `seldon.core.artifacts.create_link` — the path a real caller takes. One
   accepted case and one rejected case per edge type, asserting that a rejected
   link writes no `link_created` event and no Neo4j relationship. The isolated
   validator passing is not evidence that the caller-facing path enforces it.

The endpoint types themselves live in `seldon/domain/research.yaml` under
`relationship_types`. They are NOT in the shared `seldon-ontology` master
database: that database holds `OntologyTerm` vocabulary artifacts and edges
between them, not a schema registry for artifact relationship types.
"""
import uuid
from pathlib import Path

import pytest

from seldon.core.artifacts import create_artifact, create_link
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config, validate_relationship

pytestmark = pytest.mark.usefixtures("neo4j_available")

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
NEO4J_DB = "seldon-test"

# Minimal property sets satisfying each type's required properties in
# research.yaml. Values are only meaningful enough to pass creation.
PROPS_BY_TYPE = {
    "Result": {"value": 0.5, "units": "ratio", "description": "edge-contract fixture"},
    "Script": {"name": "edge_contract_script", "path": "scripts/edge_contract.py"},
    "DataFile": {"name": "edge_contract_data", "path": "data/edge_contract.parquet"},
    "Figure": {
        "name": "edge_contract_figure",
        "caption": "edge-contract fixture",
        "description": "edge-contract fixture",
    },
    "Table": {"name": "edge_contract_table", "caption": "edge-contract fixture"},
    "DesignNote": {
        "name": "edge_contract_note",
        "title": "Edge contract fixture",
        "path": "docs/design/edge_contract.md",
        "description": "edge-contract fixture",
        "note_type": "lessons_learned",
    },
    "Issue": {
        "description": "edge-contract fixture",
        "issue_type": "factual_error",
        "importance": "low",
        "urgency": "low",
        "detection_method": "audit",
        "target": "content",
    },
    "PaperSection": {"name": "edge_contract_section", "title": "Edge contract fixture"},
}

# (rel_type, from_type, to_type) triples that must be ACCEPTED.
ACCEPTED = [
    # generated_by — DataFile added by AD-028; the pre-existing origins must survive.
    ("generated_by", "Result", "Script"),
    ("generated_by", "Figure", "Script"),
    ("generated_by", "Table", "Script"),
    ("generated_by", "DataFile", "Script"),
    # computed_from — DataFile -> DataFile added by AD-028.
    ("computed_from", "Result", "DataFile"),
    ("computed_from", "DataFile", "DataFile"),
    # corrects — erratum authored as a DesignNote.
    ("corrects", "DesignNote", "DesignNote"),
    ("corrects", "DesignNote", "Result"),
    # annotates / disputes — Issue commentary on a Result.
    ("annotates", "Issue", "Result"),
    ("disputes", "Issue", "Result"),
]

# (rel_type, from_type, to_type, expected_error_fragment) triples that must be
# REJECTED. `cannot originate` and `cannot target` are the validator's own
# wording for a bad from_type and a bad to_type respectively.
REJECTED = [
    # generated_by: only Script may be the target, and a Script does not
    # generate itself.
    ("generated_by", "Script", "Script", "cannot originate"),
    ("generated_by", "Issue", "Script", "cannot originate"),
    ("generated_by", "Result", "DataFile", "cannot target"),
    ("generated_by", "DataFile", "DataFile", "cannot target"),
    # computed_from: targets are data, never code. This is the distinction
    # `generated_by` carries, and collapsing them would lose it.
    ("computed_from", "DataFile", "Script", "cannot target"),
    ("computed_from", "Figure", "DataFile", "cannot originate"),
    # corrects: an erratum is authored as a DesignNote. A Result correcting a
    # Result is rejected on purpose — see the module docstring in the
    # sub-RESULT and `test_corrects_result_to_result_is_rejected` below.
    ("corrects", "Result", "Result", "cannot originate"),
    ("corrects", "Issue", "Result", "cannot originate"),
    ("corrects", "DesignNote", "Script", "cannot target"),
    ("corrects", "DesignNote", "Issue", "cannot target"),
    # annotates / disputes: Issue -> Result only, in both directions.
    ("annotates", "Result", "Result", "cannot originate"),
    ("annotates", "DesignNote", "Result", "cannot originate"),
    ("annotates", "PaperSection", "Result", "cannot originate"),
    ("annotates", "Issue", "Script", "cannot target"),
    ("annotates", "Issue", "DataFile", "cannot target"),
    ("annotates", "Issue", "PaperSection", "cannot target"),
    ("disputes", "Result", "Result", "cannot originate"),
    ("disputes", "DesignNote", "Result", "cannot originate"),
    ("disputes", "PaperSection", "Result", "cannot originate"),
    ("disputes", "Issue", "Script", "cannot target"),
    ("disputes", "Issue", "DataFile", "cannot target"),
    ("disputes", "Issue", "PaperSection", "cannot target"),
]

# One accepted and one rejected case per edge type, exercised end to end
# through create_link rather than through the validator alone.
END_TO_END_ACCEPTED = [
    ("generated_by", "DataFile", "Script"),
    ("computed_from", "DataFile", "DataFile"),
    ("corrects", "DesignNote", "Result"),
    ("annotates", "Issue", "Result"),
    ("disputes", "Issue", "Result"),
]

END_TO_END_REJECTED = [
    ("generated_by", "Script", "Script"),
    ("computed_from", "DataFile", "Script"),
    ("corrects", "Result", "Result"),
    ("annotates", "Issue", "Script"),
    ("disputes", "DesignNote", "Result"),
]


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make(project_dir, driver, domain_config, artifact_type):
    """Create one artifact of `artifact_type` with unique required properties.

    Args:
        project_dir: Temp project root the JSONL event store is written under.
        driver: Neo4j driver.
        domain_config: Loaded research domain config.
        artifact_type: Artifact type name present in PROPS_BY_TYPE.

    Returns:
        The new artifact's artifact_id.

    Raises:
        KeyError: If artifact_type has no fixture property set.
    """
    props = dict(PROPS_BY_TYPE[artifact_type])
    suffix = uuid.uuid4().hex[:8]
    if "name" in props:
        props["name"] = f"{props['name']}_{suffix}"
    return create_artifact(
        project_dir=project_dir,
        driver=driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type=artifact_type,
        properties=props,
        actor="human",
        authority="accepted",
    )


# ── Config surface ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel_type,from_types,to_types", [
    ("generated_by", {"Result", "Figure", "Table", "DataFile"}, {"Script"}),
    ("computed_from", {"Result", "DataFile"}, {"DataFile"}),
    ("corrects", {"DesignNote"}, {"DesignNote", "Result"}),
    ("annotates", {"Issue"}, {"Result"}),
    ("disputes", {"Issue"}, {"Result"}),
])
def test_domain_config_declares_endpoints(domain_config, rel_type, from_types, to_types):
    """The domain config — not the ontology master DB — carries the endpoints."""
    rel = domain_config.relationship_types[rel_type]
    assert set(rel.from_types) == from_types
    assert set(rel.to_types) == to_types


def test_annotates_and_disputes_are_distinct_edge_types(domain_config):
    """Both are Issue -> Result, but they are separate types on purpose.

    `disputes` asserts the Result is wrong; `annotates` adds a caveat without
    that claim. A single type would lose the distinction.
    """
    assert "annotates" in domain_config.relationship_types
    assert "disputes" in domain_config.relationship_types


# ── Validator matrix ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel_type,from_type,to_type", ACCEPTED)
def test_endpoint_pair_accepted(domain_config, rel_type, from_type, to_type):
    validate_relationship(domain_config, rel_type, from_type, to_type)


@pytest.mark.parametrize("rel_type,from_type,to_type,fragment", REJECTED)
def test_endpoint_pair_rejected(domain_config, rel_type, from_type, to_type, fragment):
    with pytest.raises(ValueError, match=fragment):
        validate_relationship(domain_config, rel_type, from_type, to_type)


def test_corrects_result_to_result_is_rejected(domain_config):
    """A Result may not `corrects` another Result.

    An erratum is an authored claim, and the domain models authored claims as
    DesignNote artifacts that carry the rationale. Result -> Result supersession
    already has two edge types (`validates`, `derived_from`); admitting
    `corrects` there would add a third path for the same relation while letting
    the correction exist with no written justification anywhere in the graph.
    """
    with pytest.raises(ValueError, match="cannot originate"):
        validate_relationship(domain_config, "corrects", "Result", "Result")


# ── End-to-end through create_link ────────────────────────────────────────────

@pytest.mark.parametrize("rel_type,from_type,to_type", END_TO_END_ACCEPTED)
def test_create_link_accepts_endpoint_pair(
    neo4j_driver, project_dir, domain_config, clean_test_db, rel_type, from_type, to_type
):
    """create_link writes the event and the Neo4j edge for a valid pair."""
    from_id = _make(project_dir, neo4j_driver, domain_config, from_type)
    to_id = _make(project_dir, neo4j_driver, domain_config, to_type)

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=from_id,
        to_id=to_id,
        from_type=from_type,
        to_type=to_type,
        rel_type=rel_type,
        actor="human",
        authority="accepted",
    )

    link_events = [e for e in read_events(project_dir) if e["event_type"] == "link_created"]
    assert len(link_events) == 1
    assert link_events[0]["payload"]["rel_type"] == rel_type

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            f"MATCH (a:Artifact {{artifact_id: $from_id}})"
            f"-[r:{rel_type.upper()}]->"
            f"(b:Artifact {{artifact_id: $to_id}}) RETURN r",
            from_id=from_id, to_id=to_id,
        ).single()
    assert rel is not None


@pytest.mark.parametrize("rel_type,from_type,to_type", END_TO_END_REJECTED)
def test_create_link_rejects_endpoint_pair(
    neo4j_driver, project_dir, domain_config, clean_test_db, rel_type, from_type, to_type
):
    """A rejected pair raises, writes no event, and leaves no edge behind."""
    from_id = _make(project_dir, neo4j_driver, domain_config, from_type)
    to_id = _make(project_dir, neo4j_driver, domain_config, to_type)

    with pytest.raises(ValueError):
        create_link(
            project_dir=project_dir,
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
            from_id=from_id,
            to_id=to_id,
            from_type=from_type,
            to_type=to_type,
            rel_type=rel_type,
            actor="human",
            authority="accepted",
        )

    link_events = [e for e in read_events(project_dir) if e["event_type"] == "link_created"]
    assert link_events == []

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            f"MATCH (a:Artifact {{artifact_id: $from_id}})"
            f"-[r:{rel_type.upper()}]->"
            f"(b:Artifact {{artifact_id: $to_id}}) RETURN r",
            from_id=from_id, to_id=to_id,
        ).single()
    assert rel is None
