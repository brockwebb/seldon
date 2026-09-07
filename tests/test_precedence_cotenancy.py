"""Co-tenancy: a domain KG sharing the project database must be invisible to Seldon.

The arrangement under test is the documented one — a project database holds the
Seldon artifact graph and a domain knowledge graph side by side, under disjoint
labels. ai-readiness-kg's `kg/schema.yaml` whitelists `precedes: Concept →
Concept` (BFO_0000063), which collides with AD-029's `precedes` by *name* while
sharing no label with it.

Before the fix, `read_edges` ran `MATCH (a)-[r:PRECEDES]->(b)` with no endpoint
label and swept the domain KG's edges into the task graph: 117
`? [missing] → ? [missing]` rows in `seldon verify`, and readiness unanswerable.

Each test here builds both graphs in one database and asserts that the Seldon
surface reads exactly its own half — while the three things the label bind must
NOT cost are held down: illegal endpoints inside the Seldon graph still report,
a straddling edge still reports, and a rebuild leaves the co-tenant intact.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.task import task_group
from seldon.commands.verify import check_precedence
from seldon.core import precedence
from seldon.core.artifacts import create_artifact, open_states
from seldon.core.precedence import (
    add_chain,
    precedence_view,
    read_edges,
    read_half_artifact_edges,
    read_pairs,
    read_task_states,
)
from seldon.core.replay_check import fingerprint_graph
from seldon.core.sync import SELDON_OWNED_LABELS, full_replay
from seldon.domain.loader import load_domain_config

from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"

neo4j_tests = pytest.mark.usefixtures("neo4j_available")


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def cli_project(project_dir, monkeypatch):
    """A project directory whose seldon.yaml points at the test database."""
    (project_dir / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    monkeypatch.chdir(project_dir)
    return project_dir


def _make_task(project_dir, driver, domain_config, description="Test task"):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": description}, actor="human", authority="accepted",
    )


def _chain(project_dir, driver, domain_config, *task_ids, reason=None):
    return add_chain(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, task_ids=list(task_ids), reason=reason,
        actor="human", authority="accepted",
    )


def _plant_domain_kg(driver, edges: int = 3) -> None:
    """Create a co-tenant `(:Concept)-[:PRECEDES]->(:Concept)` graph.

    Deliberately uses the properties a BFO-derived KG would carry — `key`, not
    `artifact_id` — and no `:Artifact` label, which is the whole arrangement:
    disjoint labels in one database.
    """
    with driver.session(database=NEO4J_DB) as session:
        session.run(
            "UNWIND range(0, $n) AS i "
            "CREATE (a:Concept {key: 'c' + toString(i), "
            "                   bfo: 'BFO_0000063'}) "
            "WITH collect(a) AS cs "
            "UNWIND range(0, size(cs) - 2) AS j "
            "WITH cs[j] AS x, cs[j + 1] AS y "
            "CREATE (x)-[:PRECEDES {source: 'kg/schema.yaml'}]->(y)",
            n=edges,
        )


def _count_domain_concepts(driver) -> int:
    with driver.session(database=NEO4J_DB) as session:
        return session.run(
            "MATCH (c:Concept) RETURN count(c) AS n"
        ).single()["n"]


# ══════════════════════════════════════════════════════════════════════════════
# The reads see only the Seldon half
# ══════════════════════════════════════════════════════════════════════════════

@neo4j_tests
def test_read_edges_ignores_a_co_tenant_precedes_graph(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)
    _plant_domain_kg(neo4j_driver, edges=5)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        edges = read_edges(session)

    assert [(e.from_id, e.to_id) for e in edges] == [(a, b)]
    assert {e.from_type for e in edges} == {"ResearchTask"}


@neo4j_tests
def test_read_task_states_ignores_a_co_tenant_node_graph(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    _plant_domain_kg(neo4j_driver, edges=5)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert set(read_task_states(session)) == {a}


@neo4j_tests
def test_readiness_is_unchanged_by_a_co_tenant_graph(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """The defect's headline symptom: readiness became unanswerable."""
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    c = _make_task(cli_project, neo4j_driver, domain_config, "c")
    _chain(cli_project, neo4j_driver, domain_config, a, b, c)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        before = precedence_view(session, open_states(domain_config, "ResearchTask"))

    _plant_domain_kg(neo4j_driver, edges=20)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        after = precedence_view(session, open_states(domain_config, "ResearchTask"))

    assert after["ready"] == before["ready"] == [a]
    assert after["pairs"] == before["pairs"] == [(a, b), (b, c)]
    assert [ch.nodes for ch in after["chains"]] == [ch.nodes for ch in before["chains"]]


@neo4j_tests
def test_verify_stays_green_beside_a_co_tenant_graph(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)
    _plant_domain_kg(neo4j_driver, edges=20)

    result = check_precedence(neo4j_driver, NEO4J_DB)

    assert result.symbol == "pass", result.details
    assert "1 edge" in result.summary


@neo4j_tests
def test_a_co_tenant_cycle_is_not_reported_as_a_seldon_cycle(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """A domain KG may hold cyclic `precedes`; it is not Seldon's DAG."""
    _make_task(cli_project, neo4j_driver, domain_config, "a")
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run(
            "CREATE (x:Concept {key: 'x'})-[:PRECEDES]->(y:Concept {key: 'y'}) "
            "CREATE (y)-[:PRECEDES]->(x)"
        )

    result = check_precedence(neo4j_driver, NEO4J_DB)

    assert result.symbol == "pass", result.details


@neo4j_tests
def test_task_list_is_unchanged_by_a_co_tenant_graph(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "alpha")
    b = _make_task(cli_project, neo4j_driver, domain_config, "beta")
    _chain(cli_project, neo4j_driver, domain_config, a, b)
    _plant_domain_kg(neo4j_driver, edges=20)

    result = CliRunner().invoke(task_group, ["list"])

    assert result.exit_code == 0, result.output
    assert "alpha" in result.output and "beta" in result.output
    assert "Concept" not in result.output


# ══════════════════════════════════════════════════════════════════════════════
# What the label bind must NOT cost
# ══════════════════════════════════════════════════════════════════════════════

@neo4j_tests
def test_an_illegal_artifact_endpoint_still_reports(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """The bind narrows to `:Artifact`; it does not stop checking within it."""
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    wrong = create_artifact(
        project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 1.0, "units": "count", "description": "r"},
        actor="human", authority="accepted",
    )
    _plant_domain_kg(neo4j_driver, edges=5)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run(
            "MATCH (x:Artifact {artifact_id: $a}), (y:Artifact {artifact_id: $w}) "
            "CREATE (x)-[:PRECEDES]->(y)",
            a=a, w=wrong,
        )

    result = check_precedence(neo4j_driver, NEO4J_DB)

    assert result.symbol == "fail"
    assert "illegal endpoint" in result.summary
    assert any("[Result]" in d for d in result.details)


@neo4j_tests
def test_an_artifact_endpoint_without_an_id_still_reports(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run(
            "MATCH (x:Artifact {artifact_id: $a}) "
            "CREATE (x)-[:PRECEDES]->(:Artifact:ResearchTask {description: 'no id'})",
            a=a,
        )

    result = check_precedence(neo4j_driver, NEO4J_DB)

    assert result.symbol == "fail"
    assert any("[missing]" in d for d in result.details)


@neo4j_tests
def test_a_straddling_edge_reports_rather_than_vanishing(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """One end Seldon, one end co-tenant. Illegal — and the bind must not hide it."""
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run(
            "MATCH (x:Artifact {artifact_id: $a}) "
            "CREATE (x)-[:PRECEDES]->(:Concept {key: 'c0'})",
            a=a,
        )
        straddling = read_half_artifact_edges(session)

    assert len(straddling) == 1
    assert straddling[0].from_id == a
    assert straddling[0].to_id is None
    assert straddling[0].to_type == "Concept"

    result = check_precedence(neo4j_driver, NEO4J_DB)
    assert result.symbol == "fail"
    assert "straddling endpoint" in result.summary
    assert any("Concept" in d for d in result.details)


@neo4j_tests
def test_a_purely_co_tenant_edge_is_not_straddling(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    _make_task(cli_project, neo4j_driver, domain_config, "a")
    _plant_domain_kg(neo4j_driver, edges=5)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert read_half_artifact_edges(session) == []


@neo4j_tests
def test_the_write_gate_still_refuses_a_cycle_beside_a_co_tenant_graph(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)
    _plant_domain_kg(neo4j_driver, edges=20)

    with pytest.raises(ValueError, match="acyclic"):
        _chain(cli_project, neo4j_driver, domain_config, b, a)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert read_pairs(session) == [(a, b)]


# ══════════════════════════════════════════════════════════════════════════════
# A rebuild must not wipe the co-tenant
# ══════════════════════════════════════════════════════════════════════════════

def test_the_owned_label_set_covers_every_label_seldon_writes():
    """A creation path added without extending the set would orphan its nodes."""
    import re

    roots = [Path("seldon/core"), Path("seldon/commands")]
    repo = Path(__file__).resolve().parent.parent
    written = set()
    for root in roots:
        for path in (repo / root).rglob("*.py"):
            for label in re.findall(
                r"(?:CREATE|MERGE) \(\w*:([A-Za-z_][A-Za-z0-9_]*)",
                path.read_text(encoding="utf-8"),
            ):
                written.add(label)

    assert written <= set(SELDON_OWNED_LABELS), (
        "a Cypher write creates a node label that a rebuild would not clear: "
        f"{sorted(written - set(SELDON_OWNED_LABELS))}"
    )


@neo4j_tests
def test_full_replay_leaves_the_co_tenant_graph_standing(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """An unscoped `MATCH (n) DETACH DELETE n` destroyed data Seldon never owned."""
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b, reason="corpus first")
    _plant_domain_kg(neo4j_driver, edges=7)
    concepts_before = _count_domain_concepts(neo4j_driver)
    assert concepts_before == 8

    full_replay(cli_project, neo4j_driver, NEO4J_DB)

    assert _count_domain_concepts(neo4j_driver) == concepts_before
    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert read_pairs(session) == [(a, b)]


@neo4j_tests
def test_the_replay_fingerprint_ignores_the_co_tenant_graph(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """Recoverability is a claim about Seldon's graph, not about the database."""
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)

    before = fingerprint_graph(neo4j_driver, NEO4J_DB)
    _plant_domain_kg(neo4j_driver, edges=9)
    after = fingerprint_graph(neo4j_driver, NEO4J_DB)

    assert after.node_count == before.node_count
    assert after.relationship_count == before.relationship_count
    assert after.labels == before.labels
    assert after.rel_types == before.rel_types
