"""A supersession with a live successor is a DECISION, and the four surfaces agree on it.

`ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence_after.md` decision 1.
On 2026-09-19 that project's graph held 41 artifacts in state `stale`: 5 withdrawn (exempt
since DD-066) and 36 carrying a `superseded_by` that named exactly one artifact in state
`published`. Those 36 were the entire reason `seldon verify` warned at `EXIT=1` and
`seldon go` printed "Stale Artifacts: 41".

**What a decision is, and what it is not.** A pointer that does not land is not a decision: a
`superseded_by` resolving to nothing, to two artifacts, or to a successor that is itself
undecided-stale keeps the artifact in the warning set, with the reason on its detail line.
Otherwise a typo in a hand-written property would silence the check, which is the failure mode
any exemption has to be designed against.

The fixture below is the whole truth table in one graph, and the second test asserts the thing
the decision is actually for: `verify`, `go`, `briefing` and `status` count the same set.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from seldon.commands.session import get_briefing_data
from seldon.commands.verify import check_stale_artifacts
from seldon.core.graph import get_stale_artifacts
from seldon.core.staleness import (
    BASIS_SUPERSEDED,
    BASIS_WITHDRAWN,
    decided_not_drifted,
    partition_stale,
    resolver_for_session,
)
from tests.testdb import TEST_DATABASE

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = TEST_DATABASE

#: (a)..(f) of the task's fixture, by artifact_id. The expected warning set is c, e (both
#: nodes of the cycle) and f.
EXPECTED_UNDECIDED = {"c_dangling", "e_cycle_1", "e_cycle_2", "f_plain"}


@pytest.fixture
def stale_zoo(neo4j_driver, clean_test_db):
    """Every shape a `stale` artifact can have, in one graph."""
    with neo4j_driver.session(database=NEO4J_DB) as s:
        # (a) stale + withdrawn_reason — a decision since DD-066.
        s.run("CREATE (:Artifact:Result {artifact_id: 'a_withdrawn', name: 'a_withdrawn', "
              "state: 'stale', withdrawn_reason: 'leg withdrawn, DD-066'})")
        # (b) stale + superseded_by naming a PUBLISHED artifact, by name.
        s.run("CREATE (:Artifact:Result {artifact_id: 'b_superseded', name: 'b_superseded', "
              "state: 'stale', superseded_by: 'b_successor'})")
        s.run("CREATE (:Artifact:Result {artifact_id: 'b_successor', name: 'b_successor', "
              "state: 'published'})")
        # (c) stale + a superseded_by that names nothing.
        s.run("CREATE (:Artifact:Result {artifact_id: 'c_dangling', name: 'c_dangling', "
              "state: 'stale', superseded_by: 'nobody_by_this_name'})")
        # (d) a two-link chain whose last link is published: both links are decided.
        s.run("CREATE (:Artifact:Result {artifact_id: 'd_link_1', name: 'd_link_1', "
              "state: 'stale', superseded_by: 'd_link_2'})")
        s.run("CREATE (:Artifact:Result {artifact_id: 'd_link_2', name: 'd_link_2', "
              "state: 'stale', superseded_by: 'd_live'})")
        s.run("CREATE (:Artifact:Result {artifact_id: 'd_live', name: 'd_live', "
              "state: 'published'})")
        # (e) a two-node cycle: a pointer that never lands.
        s.run("CREATE (:Artifact:Result {artifact_id: 'e_cycle_1', name: 'e_cycle_1', "
              "state: 'stale', superseded_by: 'e_cycle_2'})")
        s.run("CREATE (:Artifact:Result {artifact_id: 'e_cycle_2', name: 'e_cycle_2', "
              "state: 'stale', superseded_by: 'e_cycle_1'})")
        # (f) plain stale — the drift the state was built for.
        s.run("CREATE (:Artifact:Result {artifact_id: 'f_plain', name: 'f_plain', "
              "state: 'stale'})")
    return neo4j_driver


def _partition(driver):
    with driver.session(database=NEO4J_DB) as s:
        return partition_stale(get_stale_artifacts(s), resolver_for_session(s))


# --------------------------------------------------------------------- the predicate itself

def test_the_warning_set_is_exactly_the_undecided_ones(stale_zoo):
    part = _partition(stale_zoo)
    assert {a["artifact_id"] for a, _ in part.undecided} == EXPECTED_UNDECIDED
    assert {a["artifact_id"] for a in part.withdrawn} == {"a_withdrawn"}
    assert {a["artifact_id"] for a in part.superseded} == {
        "b_superseded", "d_link_1", "d_link_2"}


def test_each_undecided_line_says_why(stale_zoo):
    reasons = {a["artifact_id"]: why for a, why in _partition(stale_zoo).undecided}
    assert "does not resolve" in reasons["c_dangling"]
    assert "nobody_by_this_name" in reasons["c_dangling"]
    assert "cycle" in reasons["e_cycle_1"] or "undecided-stale" in reasons["e_cycle_1"]
    assert "no withdrawal and no superseded_by" in reasons["f_plain"]


def test_a_superseded_by_naming_two_artifacts_is_not_a_decision():
    """Ambiguity is not a decision. A pure-function check, no graph needed."""
    twins = [{"artifact_id": "x", "state": "published"},
             {"artifact_id": "y", "state": "published"}]
    verdict = decided_not_drifted({"artifact_id": "s", "superseded_by": "twin"},
                                  lambda ref: twins)
    assert verdict.decided is False
    assert "2 artifacts" in verdict.reason


def test_a_superseded_by_resolving_by_artifact_id_is_a_decision(neo4j_driver, clean_test_db):
    """`seldon task supersede` records an id; ai-readiness-kg writes a name. Both resolve."""
    with neo4j_driver.session(database=NEO4J_DB) as s:
        s.run("CREATE (:Artifact:Result {artifact_id: 'by_id_old', name: 'by_id_old', "
              "state: 'stale', superseded_by: 'by_id_new'})")
        s.run("CREATE (:Artifact:Result {artifact_id: 'by_id_new', name: 'a_different_name', "
              "state: 'published'})")
    part = _partition(neo4j_driver)
    assert not part.undecided
    assert [a["artifact_id"] for a in part.superseded] == ["by_id_old"]


def test_a_withdrawal_wins_over_a_dangling_supersession():
    verdict = decided_not_drifted(
        {"artifact_id": "s", "withdrawn_reason": "by decision", "superseded_by": "nowhere"},
        lambda ref: [])
    assert verdict.decided and verdict.basis == BASIS_WITHDRAWN


def test_an_empty_superseded_by_is_not_a_supersession():
    verdict = decided_not_drifted({"artifact_id": "s", "superseded_by": "   "}, lambda r: [])
    assert verdict.decided is False


def test_a_chain_ending_published_is_one_decision(stale_zoo):
    part = _partition(stale_zoo)
    bases = {a["artifact_id"] for a in part.superseded}
    assert {"d_link_1", "d_link_2"} <= bases, "a supersession chain is still a supersession"
    assert BASIS_SUPERSEDED != BASIS_WITHDRAWN


# ----------------------------------------------------------- the four surfaces, one count

def test_verify_warns_on_the_undecided_and_counts_the_decided(stale_zoo):
    out = check_stale_artifacts(stale_zoo, NEO4J_DB)
    assert out.symbol == "warn", out.summary
    assert out.summary.startswith(f"{len(EXPECTED_UNDECIDED)} stale"), out.summary
    assert "1 withdrawn by decision" in out.summary
    assert "3 superseded by decision" in out.summary
    assert "b_superseded" not in out.summary, "a decision was counted as a drift"


def test_verify_passes_when_every_stale_artifact_is_decided(neo4j_driver, clean_test_db):
    """The condition the task is FOR: ai-readiness-kg's 41, all decided, all quiet."""
    with neo4j_driver.session(database=NEO4J_DB) as s:
        s.run("CREATE (:Artifact:Result {artifact_id: 'w', name: 'w', state: 'stale', "
              "withdrawn_reason: 'DD-066'})")
        s.run("CREATE (:Artifact:Result {artifact_id: 'o', name: 'o', state: 'stale', "
              "superseded_by: 'n'})")
        s.run("CREATE (:Artifact:Result {artifact_id: 'n', name: 'n', state: 'published'})")
    out = check_stale_artifacts(neo4j_driver, NEO4J_DB)
    assert out.symbol == "pass", out.summary
    assert "1 withdrawn by decision" in out.summary
    assert "1 superseded by decision" in out.summary


def test_go_briefing_status_and_verify_agree_on_the_count(stale_zoo, tmp_path, monkeypatch):
    """One predicate, four surfaces. Four filters is how one count comes to mean four things.

    `seldon status` is exercised through its own command so the assertion is over what an
    operator reads, not over a function the renderer might not call.
    """
    import yaml
    from click.testing import CliRunner

    from seldon.commands.go import _format_project_state
    from seldon.commands.status import status_command

    verify_out = check_stale_artifacts(stale_zoo, NEO4J_DB)
    expected = len(EXPECTED_UNDECIDED)
    assert verify_out.summary.startswith(f"{expected} stale")

    data = get_briefing_data(stale_zoo, NEO4J_DB)
    assert len(data["stale_artifacts"]) == expected
    assert {a["artifact_id"] for a in data["stale_artifacts"]} == EXPECTED_UNDECIDED
    assert len(data["stale_decided"]["withdrawn"]) == 1
    assert len(data["stale_decided"]["superseded"]) == 3

    rendered = _format_project_state(data)
    assert f"**Stale Artifacts:** {expected}" in rendered
    assert "**Decided, not drifted:** 1 withdrawn, 3 superseded" in rendered

    (tmp_path / "seldon.yaml").write_text(yaml.safe_dump({
        "event_store": {"path": "seldon_events.jsonl"},
        "neo4j": {"database": NEO4J_DB,
                  "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687")},
        "project": {"domain": "research", "name": "t", "slug": "t"},
    }), encoding="utf-8")
    (tmp_path / "seldon_events.jsonl").write_text("", encoding="utf-8")
    prev = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = CliRunner().invoke(status_command, [], catch_exceptions=False)
    finally:
        os.chdir(prev)
    assert f"Stale artifacts ({expected})" in result.output, result.output
    assert "Decided, not drifted: 1 withdrawn, 3 superseded" in result.output


def test_the_result_state_machine_is_unchanged():
    """Decision 1's last sentence, asserted rather than trusted: this adds no state.

    `stale` keeps carrying both facts and the property keeps naming which; a new lifecycle
    state in a machine several projects share, to name something a property already names, is
    the heavier change and the one every package registry declined to make.
    """
    from seldon.domain.loader import load_domain_config

    cfg = load_domain_config(Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml")
    machine = cfg.state_machines["Result"]
    states = set(machine) | {s for targets in machine.values() for s in targets}
    assert "withdrawn" not in states and "superseded" not in states
    assert "stale" in states
