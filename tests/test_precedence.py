"""`precedes` task ordering — AD-029.

Four layers, in increasing cost:

1. the domain declaration;
2. the pure graph algorithms (no Neo4j at all);
3. the write paths, their invariants and their error messages;
4. the read surfaces — `task list`, the briefing, `seldon verify` — and the
   recoverability guarantee that a log containing `precedes` events replays
   into an identical graph.

Layers 3 and 4 require Neo4j.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.go import _format_project_state
from seldon.commands.session import get_briefing_data
from seldon.commands.task import READY_MARKER, task_group
from seldon.commands.verify import check_precedence
from seldon.core import precedence
from seldon.core.artifacts import create_artifact, create_link, open_states
from seldon.core.graph import get_artifact
from seldon.core.precedence import (
    SATISFIED_PREDECESSOR_STATES,
    add_chain,
    chains,
    cycle_if_added,
    find_cycles,
    find_path,
    is_ready,
    precedence_view,
    read_pairs,
    remove_precedence,
    topological_order,
    unsatisfied_predecessors,
)
from seldon.core.replay_check import replay_check
from seldon.core.sync import full_replay
from seldon.domain.loader import load_domain_config
from seldon.mcp_server import (
    seldon_task_chain,
    seldon_task_precede,
    seldon_task_unprecede,
    seldon_task_update,
)

from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"

neo4j_tests = pytest.mark.usefixtures("neo4j_available")


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Domain declaration
# ══════════════════════════════════════════════════════════════════════════════

def test_domain_declares_precedes_between_tasks(domain_config):
    rel = domain_config.relationship_types["precedes"]
    assert rel.from_types == ["ResearchTask"]
    assert rel.to_types == ["ResearchTask"]
    assert rel.cardinality == "many_to_many"


def test_domain_declares_the_inverse_read_name(domain_config):
    """`preceded_by` is a read-name, so it must not also be a stored edge type."""
    assert domain_config.get_relationship_inverse("precedes") == "preceded_by"
    assert "preceded_by" not in domain_config.relationship_types


def test_domain_declares_an_optional_reason_property(domain_config):
    props = domain_config.get_relationship_properties("precedes")
    assert set(props) == {"reason"}
    assert props["reason"].required is False


def test_domain_version_was_bumped(domain_config):
    assert domain_config.version == "0.3"


def test_an_inverse_colliding_with_a_real_type_is_refused(tmp_path):
    """A stored `preceded_by` would silently disagree with the stored `precedes`."""
    import yaml

    raw = yaml.safe_load(RESEARCH_YAML.read_text())
    raw["relationship_types"]["preceded_by"] = {
        "from_types": ["ResearchTask"],
        "to_types": ["ResearchTask"],
    }
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(raw))

    with pytest.raises(ValueError, match="read-name only"):
        load_domain_config(bad)


def test_undeclared_edge_properties_are_refused(domain_config):
    from seldon.domain.loader import validate_relationship_properties

    with pytest.raises(ValueError, match="does not accept"):
        validate_relationship_properties(
            domain_config, "precedes", {"reason": "ok", "weight": 3}
        )


def test_edge_types_without_a_property_schema_still_accept_anything(domain_config):
    """`assumes` carries undeclared topic/strength. Validation must stay opt-in."""
    from seldon.domain.loader import validate_relationship_properties

    validate_relationship_properties(
        domain_config, "assumes", {"topic": "x", "strength": "high"}
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2. Pure graph algorithms
# ══════════════════════════════════════════════════════════════════════════════

def test_find_path_walks_forward_only():
    pairs = [("a", "b"), ("b", "c")]
    assert find_path(pairs, "a", "c") == ["a", "b", "c"]
    assert find_path(pairs, "c", "a") is None


def test_find_path_returns_the_shortest_route():
    pairs = [("a", "b"), ("b", "c"), ("c", "d"), ("a", "d")]
    assert find_path(pairs, "a", "d") == ["a", "d"]


def test_cycle_if_added_names_the_closing_path():
    pairs = [("a", "b"), ("b", "c")]
    assert cycle_if_added(pairs, "c", "a") == ["c", "a", "b", "c"]
    assert cycle_if_added(pairs, "a", "c") is None


def test_cycle_if_added_catches_a_self_edge():
    assert cycle_if_added([], "a", "a") == ["a", "a"]


def test_find_cycles_on_a_dag_is_empty():
    assert find_cycles([("a", "b"), ("b", "c"), ("a", "c")]) == []


def test_find_cycles_extracts_a_concrete_cycle():
    cycles = find_cycles([("a", "b"), ("b", "c"), ("c", "a")])
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"a", "b", "c"}


def test_find_cycles_reports_a_self_loop():
    assert ["a", "a"] in find_cycles([("a", "a")])


def test_find_cycles_ignores_a_dag_tail_hanging_off_a_cycle():
    """Kahn leaves the tail in the residue; the reported cycle must not."""
    cycles = find_cycles([("a", "b"), ("b", "a"), ("b", "z")])
    assert len(cycles) == 1
    assert set(cycles[0]) == {"a", "b"}


def test_topological_order_respects_edges_and_the_rank_tiebreak():
    pairs = [("b", "c")]
    rank = {"a": 0, "b": 1, "c": 2}
    assert topological_order(pairs, ["a", "b", "c"], rank) == ["a", "b", "c"]


def test_topological_order_keeps_cyclic_nodes_rather_than_dropping_them():
    order = topological_order([("a", "b"), ("b", "a")], ["a", "b"], {"a": 0, "b": 1})
    assert sorted(order) == ["a", "b"]


def test_chains_splits_components_and_drops_singletons():
    pairs = [("a", "b"), ("c", "d")]
    rank = {k: i for i, k in enumerate("abcd")}
    found = chains(pairs, rank)
    assert [c.nodes for c in found] == [["a", "b"], ["c", "d"]]
    assert all(c.is_simple_path for c in found)


def test_a_branching_component_is_not_rendered_as_a_line():
    pairs = [("a", "b"), ("a", "c")]
    chain = chains(pairs, {k: i for i, k in enumerate("abc")})[0]
    assert chain.is_simple_path is False
    lines = precedence.chain_lines(chain, {"a": "completed"}, {})
    assert lines[0].startswith("(branching")


def test_unsatisfied_predecessors_uses_the_declared_satisfied_set():
    pairs = [("a", "b")]
    for state in SATISFIED_PREDECESSOR_STATES:
        assert unsatisfied_predecessors("b", pairs, {"a": state}) == []
    for state in ("proposed", "accepted", "in_progress", "blocked", "rejected"):
        assert unsatisfied_predecessors("b", pairs, {"a": state}) == ["a"]


def test_a_missing_predecessor_counts_as_unsatisfied():
    assert unsatisfied_predecessors("b", [("a", "b")], {}) == ["a"]


def test_is_ready_requires_both_openness_and_satisfaction():
    pairs = [("a", "b")]
    open_set = {"proposed", "accepted", "in_progress", "blocked"}
    assert is_ready("b", "proposed", open_set, pairs, {"a": "completed"}) is True
    assert is_ready("b", "proposed", open_set, pairs, {"a": "in_progress"}) is False
    assert is_ready("b", "completed", open_set, pairs, {"a": "completed"}) is False


# ══════════════════════════════════════════════════════════════════════════════
# Neo4j-backed fixtures
# ══════════════════════════════════════════════════════════════════════════════

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


def _make_result(project_dir, driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 1.0, "units": "count", "description": "r"},
        actor="human", authority="accepted",
    )


def _force_state(driver, artifact_id, state):
    """Put a task directly into `state`, bypassing the machine (fixture only)."""
    with driver.session(database=NEO4J_DB) as session:
        session.run(
            "MATCH (t:ResearchTask {artifact_id: $id}) SET t.state = $state",
            id=artifact_id, state=state,
        )


def _pairs(driver):
    with driver.session(database=NEO4J_DB) as session:
        return read_pairs(session)


def _chain(project_dir, driver, domain_config, *task_ids, reason=None):
    return add_chain(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, task_ids=list(task_ids), reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 3. Write paths
# ══════════════════════════════════════════════════════════════════════════════

@neo4j_tests
def test_add_chain_writes_the_consecutive_pairs(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    c = _make_task(cli_project, neo4j_driver, domain_config, "c")

    result = _chain(cli_project, neo4j_driver, domain_config, a, b, c)

    assert result.created == [(a, b), (b, c)]
    assert set(_pairs(neo4j_driver)) == {(a, b), (b, c)}


@neo4j_tests
def test_the_reason_is_stored_on_the_edge(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b, reason="corpus first")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        edge = precedence.read_edges(session)[0]
    assert edge.reason == "corpus first"


@neo4j_tests
def test_re_running_a_chain_writes_nothing_new(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)

    again = _chain(cli_project, neo4j_driver, domain_config, a, b)
    assert again.created == []
    assert again.skipped == [(a, b)]
    assert len(_pairs(neo4j_driver)) == 1


@neo4j_tests
def test_a_self_loop_is_refused(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    with pytest.raises(ValueError, match="cannot precede itself"):
        _chain(cli_project, neo4j_driver, domain_config, a, a)
    assert _pairs(neo4j_driver) == []


@neo4j_tests
def test_a_cycle_is_refused_and_the_error_names_the_path(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    c = _make_task(cli_project, neo4j_driver, domain_config, "c")
    _chain(cli_project, neo4j_driver, domain_config, a, b, c)

    with pytest.raises(ValueError) as exc:
        _chain(cli_project, neo4j_driver, domain_config, c, a)

    message = str(exc.value)
    assert "acyclic" in message
    for node in (a, b, c):
        assert node[:8] in message
    # The reported path closes: it starts and ends on the same task.
    rendered = message.split("cycle ")[1].rstrip(".")
    steps = [s.strip() for s in rendered.split("→")]
    assert steps[0] == steps[-1] == c[:8]
    assert set(_pairs(neo4j_driver)) == {(a, b), (b, c)}


@neo4j_tests
def test_a_chain_that_fails_late_writes_nothing_at_all(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """All-or-nothing: the good first link must not survive the bad second one."""
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")

    with pytest.raises(ValueError):
        _chain(cli_project, neo4j_driver, domain_config, a, b, a)

    assert _pairs(neo4j_driver) == []


@neo4j_tests
def test_a_non_task_endpoint_is_refused(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    r = _make_result(cli_project, neo4j_driver, domain_config)
    with pytest.raises(ValueError, match="orders tasks only"):
        _chain(cli_project, neo4j_driver, domain_config, a, r)
    assert _pairs(neo4j_driver) == []


@neo4j_tests
def test_one_id_is_refused(neo4j_driver, cli_project, domain_config, clean_test_db):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    with pytest.raises(ValueError, match="at least two tasks"):
        _chain(cli_project, neo4j_driver, domain_config, a)


@neo4j_tests
def test_the_guard_also_covers_the_generic_link_command(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """`seldon link create` reaches the same gate, so it cannot author a cycle."""
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)

    with pytest.raises(ValueError, match="acyclic"):
        create_link(
            project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, from_id=b, to_id=a,
            from_type="ResearchTask", to_type="ResearchTask",
            rel_type="precedes", actor="human", authority="accepted",
        )
    assert set(_pairs(neo4j_driver)) == {(a, b)}


@neo4j_tests
def test_remove_precedence_deletes_the_edge(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)

    remove_precedence(
        project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
        before_id=a[:8], after_id=b[:8],
    )
    assert _pairs(neo4j_driver) == []


@neo4j_tests
def test_removing_an_absent_edge_is_an_error(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    with pytest.raises(ValueError, match="No 'precedes' edge"):
        remove_precedence(
            project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
            before_id=a, after_id=b,
        )


# ── CLI surface ───────────────────────────────────────────────────────────────

@neo4j_tests
def test_cli_precede_accepts_id_prefixes(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")

    result = CliRunner().invoke(task_group, ["precede", a[:8], b[:8]])
    assert result.exit_code == 0, result.output
    assert set(_pairs(neo4j_driver)) == {(a, b)}


@neo4j_tests
def test_cli_chain_writes_the_whole_sequence(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    ids = [
        _make_task(cli_project, neo4j_driver, domain_config, f"t{i}") for i in range(4)
    ]
    result = CliRunner().invoke(
        task_group, ["chain", *(i[:8] for i in ids), "--reason", "week order"]
    )
    assert result.exit_code == 0, result.output
    assert set(_pairs(neo4j_driver)) == set(zip(ids, ids[1:]))


@neo4j_tests
def test_cli_chain_refuses_a_single_task(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    result = CliRunner().invoke(task_group, ["chain", a[:8]])
    assert result.exit_code != 0
    assert "at least two" in result.output


@neo4j_tests
def test_cli_unprecede_removes_the_edge(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    CliRunner().invoke(task_group, ["precede", a[:8], b[:8]])

    result = CliRunner().invoke(task_group, ["unprecede", a[:8], b[:8]])
    assert result.exit_code == 0, result.output
    assert _pairs(neo4j_driver) == []


@neo4j_tests
def test_cli_cycle_rejection_exits_nonzero_with_the_path(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    CliRunner().invoke(task_group, ["precede", a[:8], b[:8]])

    result = CliRunner().invoke(task_group, ["precede", b[:8], a[:8]])
    assert result.exit_code != 0
    assert "acyclic" in result.output
    assert a[:8] in result.output and b[:8] in result.output


# ── CLI / MCP parity ──────────────────────────────────────────────────────────

@neo4j_tests
def test_cli_and_mcp_precede_produce_the_same_edges(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    cli_a = _make_task(cli_project, neo4j_driver, domain_config, "cli a")
    cli_b = _make_task(cli_project, neo4j_driver, domain_config, "cli b")
    mcp_a = _make_task(cli_project, neo4j_driver, domain_config, "mcp a")
    mcp_b = _make_task(cli_project, neo4j_driver, domain_config, "mcp b")

    CliRunner().invoke(task_group, ["precede", cli_a[:8], cli_b[:8]])
    out = seldon_task_precede(
        before_id=mcp_a[:8], after_id=mcp_b[:8], project_dir=str(cli_project)
    )
    assert "Error" not in out, out

    pairs = set(_pairs(neo4j_driver))
    assert pairs == {(cli_a, cli_b), (mcp_a, mcp_b)}


@neo4j_tests
def test_cli_and_mcp_reject_a_cycle_with_the_same_message(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    CliRunner().invoke(task_group, ["precede", a[:8], b[:8]])

    cli_out = CliRunner().invoke(task_group, ["precede", b[:8], a[:8]]).output
    mcp_out = seldon_task_precede(
        before_id=b[:8], after_id=a[:8], project_dir=str(cli_project)
    )

    assert cli_out.strip().removeprefix("Error: ") == mcp_out.strip().removeprefix(
        "Error: "
    )


@neo4j_tests
def test_cli_and_mcp_chain_write_the_same_pairs(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    cli_ids = [
        _make_task(cli_project, neo4j_driver, domain_config, f"cli{i}") for i in range(3)
    ]
    mcp_ids = [
        _make_task(cli_project, neo4j_driver, domain_config, f"mcp{i}") for i in range(3)
    ]

    CliRunner().invoke(task_group, ["chain", *(i[:8] for i in cli_ids)])
    out = seldon_task_chain(
        task_ids=[i[:8] for i in mcp_ids], project_dir=str(cli_project)
    )
    assert "Error" not in out, out

    pairs = set(_pairs(neo4j_driver))
    assert pairs == set(zip(cli_ids, cli_ids[1:])) | set(zip(mcp_ids, mcp_ids[1:]))


@neo4j_tests
def test_mcp_unprecede_removes_the_edge(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    seldon_task_precede(before_id=a, after_id=b, project_dir=str(cli_project))

    out = seldon_task_unprecede(
        before_id=a[:8], after_id=b[:8], project_dir=str(cli_project)
    )
    assert "Error" not in out, out
    assert _pairs(neo4j_driver) == []


@neo4j_tests
def test_the_two_surfaces_record_their_own_actor(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """Parity is about behaviour, not provenance — the actor must still differ."""
    from seldon.core.events import read_events

    cli_a = _make_task(cli_project, neo4j_driver, domain_config, "cli a")
    cli_b = _make_task(cli_project, neo4j_driver, domain_config, "cli b")
    mcp_a = _make_task(cli_project, neo4j_driver, domain_config, "mcp a")
    mcp_b = _make_task(cli_project, neo4j_driver, domain_config, "mcp b")

    CliRunner().invoke(task_group, ["precede", cli_a[:8], cli_b[:8]])
    seldon_task_precede(before_id=mcp_a, after_id=mcp_b, project_dir=str(cli_project))

    actors = {
        (e["payload"]["from_id"], e["payload"]["to_id"]): e["actor"]
        for e in read_events(cli_project)
        if e["event_type"] == "link_created"
        and e["payload"].get("rel_type") == "precedes"
    }
    assert actors[(cli_a, cli_b)] == "human"
    assert actors[(mcp_a, mcp_b)] == "desktop"


# ── Advisory transition warnings ──────────────────────────────────────────────

@neo4j_tests
@pytest.mark.parametrize("target", ["accepted", "in_progress"])
def test_starting_a_task_ahead_of_its_predecessor_warns_and_proceeds(
    neo4j_driver, cli_project, domain_config, clean_test_db, target,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)
    if target == "in_progress":
        _force_state(neo4j_driver, b, "accepted")

    result = CliRunner().invoke(task_group, ["update", b[:8], "--state", target])

    assert result.exit_code == 0, result.output
    assert "unsatisfied predecessor" in result.output
    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert get_artifact(session, b)["state"] == target


@neo4j_tests
def test_no_warning_once_the_predecessor_is_satisfied(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)
    _force_state(neo4j_driver, a, "completed")

    result = CliRunner().invoke(task_group, ["update", b[:8], "--state", "accepted"])
    assert result.exit_code == 0, result.output
    assert "unsatisfied predecessor" not in result.output


@neo4j_tests
def test_the_mcp_update_returns_the_same_warning(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)

    out = seldon_task_update(
        task_id=b[:8], state="accepted", project_dir=str(cli_project)
    )
    assert "unsatisfied predecessor" in out
    assert "Error" not in out


@neo4j_tests
def test_closing_a_task_surfaces_the_warning_but_still_closes(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)

    result = CliRunner().invoke(task_group, ["close", b[:8]])
    assert result.exit_code == 0, result.output
    assert "unsatisfied predecessor" in result.output
    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert get_artifact(session, b)["state"] == "completed"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Read surfaces
# ══════════════════════════════════════════════════════════════════════════════

@neo4j_tests
@pytest.mark.parametrize(
    "predecessor_state,successor_is_ready",
    [
        ("completed", True),
        ("verified", True),
        ("superseded", True),
        ("withdrawn", True),
        ("rejected", False),
        ("proposed", False),
        ("accepted", False),
        ("in_progress", False),
        ("blocked", False),
    ],
)
def test_readiness_for_every_predecessor_state(
    neo4j_driver, cli_project, domain_config, clean_test_db,
    predecessor_state, successor_is_ready,
):
    """The satisfied set, exercised against the real graph, state by state."""
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)
    _force_state(neo4j_driver, a, predecessor_state)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        view = precedence_view(session, open_states(domain_config, "ResearchTask"))

    assert (b in view["ready"]) is successor_is_ready
    assert (view["waits_on"][b] == []) is successor_is_ready


@neo4j_tests
def test_task_list_marks_ready_tasks_and_names_what_the_others_wait_on(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "first")
    b = _make_task(cli_project, neo4j_driver, domain_config, "second")
    _chain(cli_project, neo4j_driver, domain_config, a, b)

    result = CliRunner().invoke(task_group, ["list", "--open"])
    assert result.exit_code == 0, result.output

    lines = {
        line[2:10]: line for line in result.output.splitlines() if a[:8] in line or b[:8] in line
    }
    assert lines[a[:8]].startswith(READY_MARKER)
    assert not lines[b[:8]].startswith(READY_MARKER)
    assert a[:8] in lines[b[:8]].split(b[:8])[1]  # waits_on column names the blocker
    assert "WAITS_ON" in result.output


@neo4j_tests
def test_task_list_shows_no_waits_when_there_is_no_precedence(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    _make_task(cli_project, neo4j_driver, domain_config, "lonely")
    result = CliRunner().invoke(task_group, ["list", "--open"])
    assert result.exit_code == 0, result.output
    assert READY_MARKER in result.output


def _briefing_fixture(project_dir, driver, domain_config):
    """Two chains and one isolated task — the fixture the task file specifies.

    Returns:
        (chain_one_ids, chain_two_ids, isolated_id)
    """
    one = [_make_task(project_dir, driver, domain_config, f"one-{i}") for i in range(3)]
    two = [_make_task(project_dir, driver, domain_config, f"two-{i}") for i in range(2)]
    isolated = _make_task(project_dir, driver, domain_config, "isolated")
    add_chain(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, task_ids=one,
    )
    add_chain(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, task_ids=two,
    )
    return one, two, isolated


@neo4j_tests
def test_briefing_renders_two_chains_and_omits_the_isolated_task(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    one, two, isolated = _briefing_fixture(cli_project, neo4j_driver, domain_config)

    data = get_briefing_data(neo4j_driver, NEO4J_DB, domain_config)
    rendered = _format_project_state(data)

    assert "**Chains:** 2" in rendered
    chain_lines = [
        line for line in rendered.splitlines()
        if line.startswith("- ") and "→" in line
    ]
    assert len(chain_lines) == 2
    assert all(n[:8] in chain_lines[0] for n in one)
    assert all(n[:8] in chain_lines[1] for n in two)
    # A component of one node is not a chain.
    assert isolated[:8] not in " ".join(chain_lines)


@neo4j_tests
def test_briefing_next_ready_lists_only_the_startable_heads(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    one, two, isolated = _briefing_fixture(cli_project, neo4j_driver, domain_config)

    data = get_briefing_data(neo4j_driver, NEO4J_DB, domain_config)
    ready = data["precedence"]["ready"]

    assert ready == [one[0], two[0], isolated]
    assert one[1] not in ready


@neo4j_tests
def test_briefing_next_ready_advances_as_the_chain_completes(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    one, two, isolated = _briefing_fixture(cli_project, neo4j_driver, domain_config)
    _force_state(neo4j_driver, one[0], "completed")

    data = get_briefing_data(neo4j_driver, NEO4J_DB, domain_config)
    assert data["precedence"]["ready"] == [one[1], two[0], isolated]


@neo4j_tests
def test_go_renders_next_ready_after_open_tasks(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    _briefing_fixture(cli_project, neo4j_driver, domain_config)
    rendered = _format_project_state(
        get_briefing_data(neo4j_driver, NEO4J_DB, domain_config)
    )
    assert rendered.index("**Open Tasks:**") < rendered.index("**Next ready:**")
    assert rendered.index("**Next ready:**") < rendered.index("**Chains:**")


@neo4j_tests
def test_the_briefing_command_renders_the_same_sections(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    from seldon.commands.session import briefing_command

    one, _, _ = _briefing_fixture(cli_project, neo4j_driver, domain_config)
    result = CliRunner().invoke(briefing_command, [])
    assert result.exit_code == 0, result.output
    assert "NEXT READY" in result.output
    assert "CHAINS (2)" in result.output
    assert one[0][:8] in result.output


# ── seldon verify ─────────────────────────────────────────────────────────────

@neo4j_tests
def test_verify_passes_on_a_clean_dag(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    one, _, _ = _briefing_fixture(cli_project, neo4j_driver, domain_config)
    result = check_precedence(neo4j_driver, NEO4J_DB)
    assert result.symbol == "pass"
    assert "acyclic" in result.summary


@neo4j_tests
def test_verify_passes_when_there_are_no_edges(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    result = check_precedence(neo4j_driver, NEO4J_DB)
    assert result.symbol == "pass"


@neo4j_tests
def test_verify_reports_a_cycle_written_behind_the_gate(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """Raw Cypher can still author one; that is exactly what this check is for."""
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    b = _make_task(cli_project, neo4j_driver, domain_config, "b")
    _chain(cli_project, neo4j_driver, domain_config, a, b)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run(
            "MATCH (x {artifact_id: $b}), (y {artifact_id: $a}) "
            "CREATE (x)-[:PRECEDES]->(y)",
            a=a, b=b,
        )

    result = check_precedence(neo4j_driver, NEO4J_DB)
    assert result.symbol == "fail"
    assert "cycle" in result.summary
    assert any("cycle:" in d for d in result.details)


@neo4j_tests
def test_verify_reports_a_self_loop(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run(
            "MATCH (x {artifact_id: $a}) CREATE (x)-[:PRECEDES]->(x)", a=a
        )

    result = check_precedence(neo4j_driver, NEO4J_DB)
    assert result.symbol == "fail"
    assert any("self-loop" in d for d in result.details)


@neo4j_tests
def test_verify_reports_an_illegal_endpoint(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    a = _make_task(cli_project, neo4j_driver, domain_config, "a")
    r = _make_result(cli_project, neo4j_driver, domain_config)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run(
            "MATCH (x {artifact_id: $a}), (y {artifact_id: $r}) "
            "CREATE (x)-[:PRECEDES]->(y)",
            a=a, r=r,
        )

    result = check_precedence(neo4j_driver, NEO4J_DB)
    assert result.symbol == "fail"
    assert any("illegal endpoint" in d for d in result.details)


@neo4j_tests
def test_the_precedence_check_runs_in_the_default_verify_pass():
    from seldon.commands.verify import _run_all_checks
    import inspect

    source = inspect.getsource(_run_all_checks)
    assert "check_precedence" in source


# ── Recoverability ────────────────────────────────────────────────────────────

@neo4j_tests
def test_a_log_containing_precedes_events_replays_identically(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """The graph is a projection of the log — including these edges."""
    one, two, _ = _briefing_fixture(cli_project, neo4j_driver, domain_config)
    remove_precedence(
        project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
        before_id=two[0], after_id=two[1],
    )

    comparison = replay_check(cli_project, neo4j_driver, NEO4J_DB)

    assert comparison.error is None, comparison.error
    assert comparison.matches, comparison.summary_lines()


@neo4j_tests
def test_a_rebuilt_graph_answers_readiness_the_same_way(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """Replay is only recovery if the derived view survives it too."""
    one, two, isolated = _briefing_fixture(cli_project, neo4j_driver, domain_config)
    open_set = open_states(domain_config, "ResearchTask")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        before = precedence_view(session, open_set)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run("MATCH (n) DETACH DELETE n")
    full_replay(cli_project, neo4j_driver, NEO4J_DB)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        after = precedence_view(session, open_set)

    assert after["ready"] == before["ready"]
    assert sorted(after["pairs"]) == sorted(before["pairs"])
    assert [c.nodes for c in after["chains"]] == [c.nodes for c in before["chains"]]
