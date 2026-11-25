"""SEL-043 ADDENDUM 01: a dispatch scenario's task name is its own in the session's shared test database.

The merge round's full gate failed two tests that pass alone (`test_friction002_stop_hook_gate.py` `[passing]` and
`test_friction002_worktree_only.py`'s unmerged-task test): each read, through `task_states`, the state of an `a`
task an earlier test in the same pytest session had registered, because the session's database is shared and
`task_states` keys its result by name. Every dispatcher scenario registers the same handful of names (`a`, `b`, ...)
with one `created_at`, so which `a` a read returns, and which `a` the dispatcher's queue launches, depended on
Neo4j's scan order. Evidence and the bisection: `docs/evidence/sel043/round_two.txt`.
"""
from __future__ import annotations

import pytest

from tests.dispatch_scaffold import NEO4J_DB, RESEARCH_YAML, make_project, register, task_states


@pytest.fixture
def dc():
    from seldon.domain.loader import load_domain_config
    return load_domain_config(RESEARCH_YAML)


@pytest.mark.usefixtures("neo4j_available")
def test_registering_a_name_an_earlier_scenario_left_in_the_graph_leaves_only_this_scenarios_task(
        tmp_path, neo4j_driver, dc):
    earlier = make_project(tmp_path / "earlier")
    left = register(earlier, neo4j_driver, dc, "a", "2026-10-17T00:00:00Z")
    with neo4j_driver.session(database=NEO4J_DB) as s:
        s.run("MATCH (t:ResearchTask {artifact_id: $id}) SET t.state = 'completed'", id=left)

    p = make_project(tmp_path / "this")
    mine = register(p, neo4j_driver, dc, "a", "2026-10-17T00:00:00Z")

    with neo4j_driver.session(database=NEO4J_DB) as s:
        ids = [r["id"] for r in s.run("MATCH (t:ResearchTask {name: 'a'}) RETURN t.artifact_id AS id")]
    assert ids == [mine], "an earlier scenario's `a` is still in the graph beside this one's"
    assert task_states(neo4j_driver)["a"] != "completed"
