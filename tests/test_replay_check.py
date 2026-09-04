"""Replay-fidelity check: scratch-database safety and live-vs-replay diffing.

The safety tests are pure and always run. The comparison tests need Neo4j and
are skipped without it, per the suite's convention.
"""
from __future__ import annotations

import json
import os
import uuid

import pytest

from seldon.core.events import append_event, make_event
from seldon.core.legacy_events import LEGACY_ASSIGNMENT_EVENT_TYPE, make_assignment_payload
from seldon.core.replay_check import (
    GraphFingerprint,
    SCRATCH_PREFIX,
    SCRATCH_RE,
    compare_fingerprints,
    create_scratch_database,
    drop_scratch_database,
    fingerprint_graph,
    is_scratch_database,
    replay_check,
    scratch_database_name,
    stale_scratch_databases,
)
from seldon.core.sync import _AUDIT_ONLY_EVENT_TYPES, _apply_event, full_replay

from tests.testdb import BASE_DATABASE, TEST_DATABASE


# ── scratch-database naming and safety (no Neo4j) ─────────────────────────────

def test_generated_name_matches_the_guard():
    name = scratch_database_name()
    assert SCRATCH_RE.match(name)
    assert is_scratch_database(name)
    assert str(os.getpid()) in name


def test_generated_names_are_unique_within_one_process():
    """The all-projects sweep runs many checks from one PID."""
    assert len({scratch_database_name() for _ in range(50)}) == 50


@pytest.mark.parametrize("name", [
    "seldon-seldon-self",          # a real project database
    "seldon-ai-readiness-kg",      # another one
    "seldon-ontology",             # the shared ontology master
    "neo4j", "system",             # server databases
    BASE_DATABASE,                 # the suite's base name
    f"{BASE_DATABASE}-p12345",     # a per-process test database
    f"{BASE_DATABASE}-p12345-gw0", # an xdist test database
    "seldon-replaycheck",          # the bare prefix, no pid
    "seldon-replaycheck-p12-xyz",  # suffix is not 8 hex
    "seldon-replaycheck-pabc-1234abcd",
    "xseldon-replaycheck-p1-1234abcd",   # not anchored at the start
    "seldon-replaycheck-p1-1234abcd-x",  # not anchored at the end
])
def test_real_databases_are_never_scratch(name):
    assert not is_scratch_database(name)


@pytest.mark.parametrize(
    "name", ["seldon-seldon-self", f"{BASE_DATABASE}-p1", "neo4j"]
)
def test_drop_refuses_a_non_scratch_name(name):
    """The guard is what stops a caller mistake destroying a project."""
    with pytest.raises(ValueError, match="refusing to drop"):
        drop_scratch_database(object(), name)


@pytest.mark.parametrize("name", ["seldon-seldon-self", f"{BASE_DATABASE}-p1"])
def test_create_refuses_a_non_scratch_name(name):
    with pytest.raises(ValueError, match="refusing to create"):
        create_scratch_database(object(), name)


def test_stale_sweep_skips_this_process():
    """Dropping our own scratch database mid-check would be self-sabotage."""
    mine = scratch_database_name()
    assert stale_scratch_databases([mine]) == []


def test_stale_sweep_skips_a_live_pid():
    """A recycled PID that is now live leaves a harmless orphan, not a drop."""
    live = f"{SCRATCH_PREFIX}p{os.getpid()}-deadbeef"
    assert stale_scratch_databases([live], self_pid=os.getpid() + 1) == []


def test_stale_sweep_reclaims_a_dead_pid():
    dead = f"{SCRATCH_PREFIX}p999999999-deadbeef"
    assert stale_scratch_databases([dead]) == [dead]


def test_stale_sweep_ignores_everything_it_does_not_own():
    names = ["seldon-seldon-self", f"{BASE_DATABASE}-p999999999", "neo4j", "system"]
    assert stale_scratch_databases(names) == []


# ── comparison (pure) ─────────────────────────────────────────────────────────

def fp(states=None, edges=None, nodes=None, rels=None) -> GraphFingerprint:
    from collections import Counter
    states = states or {}
    return GraphFingerprint(
        node_count=len(states) if nodes is None else nodes,
        relationship_count=(len(edges or []) if rels is None else rels),
        states=dict(states),
        types={k: "Result" for k in states},
        edges=Counter(edges or []),
    )


def test_identical_fingerprints_match():
    live = fp({"a": "proposed"}, [("a", "CITES", "a")])
    cmp = compare_fingerprints("db", live, fp({"a": "proposed"}, [("a", "CITES", "a")]), 3)
    assert cmp.matches
    assert cmp.summary_lines() == []


class TestNonArtifactNodesAreNotCountedAsDivergence:
    """A project may hold non-Seldon nodes in the same database.

    `seldon-ai-readiness-kg` stores a ~23k-node knowledge graph alongside its
    Seldon artifacts. Comparing raw node totals rendered a two-artifact
    divergence as a 23,000-node failure — a check that loud stops being read,
    which is worse than no check.
    """

    def test_foreign_nodes_do_not_make_a_matching_replay_fail(self):
        live = fp({"a": "proposed"}, nodes=23_000)
        replayed = fp({"a": "proposed"})
        cmp = compare_fingerprints("db", live, replayed, 1)
        assert cmp.matches
        assert not any("artifact count" in line for line in cmp.summary_lines())

    def test_foreign_nodes_are_reported_as_context_not_failure(self):
        live = fp({"a": "proposed"}, nodes=23_000)
        cmp = compare_fingerprints("db", live, fp({"a": "proposed"}), 1)
        note = [l for l in cmp.summary_lines() if l.startswith("note:")]
        assert len(note) == 1
        assert "22999 live node(s) carry no artifact_id" in note[0]

    def test_real_artifact_divergence_is_still_reported(self):
        # The two-artifact case that the node-count noise was burying.
        live = fp({"a": "proposed", "b": "proposed"}, nodes=23_000)
        cmp = compare_fingerprints("db", live, fp({"a": "proposed"}), 1)
        lines = cmp.summary_lines()
        assert not cmp.matches
        assert any("artifact count: live 2, replayed 1" in l for l in lines)
        assert any("unrecoverable graph state" in l for l in lines)


class TestInheritedArtifactsAreNotDivergence:
    """OntologyTerms are replicated from master, not projected from the log.

    `seldon ontology sync` writes them into a replica and `create_artifact`
    refuses to make one locally (AD-017), so no local event exists and replay
    can never produce them. Counting them made all 13 ontology-carrying
    projects report permanent "unrecoverable graph state" — 2 phantom findings
    each, burying the genuine ones.
    """

    def _fp_with_ontology(self, states, ontology_ids):
        f = fp(states)
        for oid in ontology_ids:
            f.states[oid] = "active"
            f.types[oid] = "OntologyTerm"
        f.node_count = len(f.states)
        return f

    def test_live_only_ontology_term_is_not_a_mismatch(self):
        live = self._fp_with_ontology({"a": "proposed"}, ["ont1", "ont2"])
        cmp = compare_fingerprints("db", live, fp({"a": "proposed"}), 1)
        assert cmp.matches
        assert cmp.missing_artifacts == []
        assert cmp.inherited_skipped == 2

    def test_exclusion_is_reported_as_context(self):
        live = self._fp_with_ontology({"a": "proposed"}, ["ont1", "ont2"])
        cmp = compare_fingerprints("db", live, fp({"a": "proposed"}), 1)
        note = [l for l in cmp.summary_lines() if "inherited artifact" in l]
        assert len(note) == 1
        assert "OntologyTerm" in note[0]
        assert "ontology sync" in note[0]

    def test_a_real_missing_artifact_alongside_ontology_still_fails(self):
        # The genuine finding must survive the exclusion.
        live = self._fp_with_ontology(
            {"a": "proposed", "lost": "proposed"}, ["ont1", "ont2"]
        )
        cmp = compare_fingerprints("db", live, fp({"a": "proposed"}), 1)
        assert not cmp.matches
        assert cmp.missing_artifacts == ["lost"]


def test_live_only_artifact_is_reported_as_unrecoverable():
    cmp = compare_fingerprints("db", fp({"a": "proposed", "b": "proposed"}), fp({"a": "proposed"}), 1)
    assert not cmp.matches
    assert cmp.missing_artifacts == ["b"]
    assert any("unrecoverable graph state" in line for line in cmp.summary_lines())


def test_replay_only_artifact_is_reported():
    cmp = compare_fingerprints("db", fp({"a": "proposed"}), fp({"a": "proposed", "b": "proposed"}), 2)
    assert cmp.extra_artifacts == ["b"]


def test_state_mismatch_is_reported():
    """The failure mode the nine legacy records produce: same node, wrong state."""
    cmp = compare_fingerprints("db", fp({"a": "active"}), fp({"a": "proposed"}), 2)
    assert cmp.state_mismatches == [("a", "active", "proposed")]
    assert cmp.missing_artifacts == []


def test_live_only_edge_is_reported():
    """Raw-Cypher edges with no link_created event show up here."""
    cmp = compare_fingerprints(
        "db",
        fp({"a": "x", "b": "x"}, [("a", "INFORMS", "b")]),
        fp({"a": "x", "b": "x"}, []),
        2,
    )
    assert cmp.missing_edges == [("a", "INFORMS", "b", 1)]
    assert any("written outside the event path" in line for line in cmp.summary_lines())


def test_error_comparison_never_matches():
    from seldon.core.replay_check import ReplayComparison
    cmp = ReplayComparison(database="db", error="boom")
    assert not cmp.matches
    assert cmp.summary_lines() == ["replay check could not run: boom"]


# ── sync integration ──────────────────────────────────────────────────────────

def test_legacy_assignment_is_an_audit_only_event_type():
    """It is listed deliberately, not left to the unknown-type branch."""
    assert LEGACY_ASSIGNMENT_EVENT_TYPE in _AUDIT_ONLY_EVENT_TYPES


# ── Neo4j-backed ──────────────────────────────────────────────────────────────

neo4j_tests = pytest.mark.usefixtures("neo4j_available")

LEGACY_LINE = {
    "event_type": "artifact_state_changed",
    "artifact_id": "11111111-1111-4111-8111-111111111111",
    "artifact_type": "Result",
    "from_state": "proposed",
    "to_state": "accepted",
    "actor": "human",
    "authority": "accepted",
}


def create_event(artifact_id, artifact_type="Result", state="proposed"):
    return make_event(
        event_type="artifact_created",
        actor="human",
        authority="accepted",
        payload={
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "properties": {"name": "n"},
            "from_state": None,
            "to_state": state,
        },
    )


@neo4j_tests
def test_legacy_assignment_event_replays_without_a_warning(test_db_session, caplog):
    """Nine of these per replay would drown the unknown-type signal if unhandled."""
    event = make_event(
        event_type=LEGACY_ASSIGNMENT_EVENT_TYPE,
        actor="human",
        authority="accepted",
        payload=make_assignment_payload(1, LEGACY_LINE),
    )
    with caplog.at_level("WARNING"):
        assert _apply_event(test_db_session, event) is False
    assert "Unknown event_type" not in caplog.text


@neo4j_tests
def test_a_legacy_state_change_replays_after_its_creation(
    neo4j_driver, project_dir, clean_test_db
):
    """An id alone is not enough — replay also needs the flat shape repaired.

    Without the payload repair this raises KeyError('artifact_id') inside
    `_apply_event`, so recoverability would still be broken.
    """
    aid = LEGACY_LINE["artifact_id"]
    append_event(project_dir, create_event(aid))
    with open(project_dir / "seldon_events.jsonl", "a") as f:
        f.write(json.dumps(LEGACY_LINE) + "\n")

    assert full_replay(project_dir, neo4j_driver, TEST_DATABASE) == 2
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        state = s.run(
            "MATCH (a:Artifact {artifact_id: $id}) RETURN a.state AS s", id=aid
        ).single()["s"]
    assert state == "accepted"


@neo4j_tests
def test_a_legacy_state_change_before_its_creation_cannot_be_replayed(
    neo4j_driver, project_dir, clean_test_db
):
    """The real defect in seldon-seldon-self's log, reproduced.

    The nine legacy records precede the `artifact_created` events for the very
    artifacts they transition. `change_state` matches nothing, then the create
    lands at its own `to_state`. Replay is well-defined and does not crash — it
    just cannot reproduce the live state. Recording it as a test so a later
    "fix" that reorders the log has to argue with a pinned expectation.
    """
    aid = LEGACY_LINE["artifact_id"]
    with open(project_dir / "seldon_events.jsonl", "a") as f:
        f.write(json.dumps(LEGACY_LINE) + "\n")
    append_event(project_dir, create_event(aid, state="proposed"))

    assert full_replay(project_dir, neo4j_driver, TEST_DATABASE) == 2
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        state = s.run(
            "MATCH (a:Artifact {artifact_id: $id}) RETURN a.state AS s", id=aid
        ).single()["s"]
    assert state == "proposed"


@neo4j_tests
def test_fingerprint_excludes_internal_bookkeeping_nodes(
    neo4j_driver, project_dir, clean_test_db
):
    """_SeldonMeta is written by replay itself and would always differ."""
    append_event(project_dir, create_event(str(uuid.uuid4())))
    full_replay(project_dir, neo4j_driver, TEST_DATABASE)
    print_fp = fingerprint_graph(neo4j_driver, TEST_DATABASE)
    assert print_fp.node_count == 1
    assert "_SeldonMeta" not in print_fp.labels


@neo4j_tests
def test_replay_check_reports_a_clean_project(neo4j_driver, project_dir, clean_test_db):
    """Live graph produced entirely by replay must reproduce exactly."""
    for _ in range(3):
        append_event(project_dir, create_event(str(uuid.uuid4())))
    full_replay(project_dir, neo4j_driver, TEST_DATABASE)

    cmp = replay_check(project_dir, neo4j_driver, TEST_DATABASE)
    assert cmp.error is None, cmp.error
    assert cmp.matches, cmp.summary_lines()
    assert cmp.events_replayed == 3


@neo4j_tests
def test_replay_check_catches_an_un_evented_write(
    neo4j_driver, project_dir, clean_test_db
):
    """A node written by raw Cypher cannot be rebuilt — that is the finding."""
    append_event(project_dir, create_event(str(uuid.uuid4())))
    full_replay(project_dir, neo4j_driver, TEST_DATABASE)
    orphan = str(uuid.uuid4())
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        s.run(
            "CREATE (a:Artifact:Result {artifact_id: $id, state: 'proposed', "
            "artifact_type: 'Result'})",
            id=orphan,
        )

    cmp = replay_check(project_dir, neo4j_driver, TEST_DATABASE)
    assert not cmp.matches
    assert cmp.missing_artifacts == [orphan]


@neo4j_tests
def test_replay_check_leaves_no_scratch_database_behind(
    neo4j_driver, project_dir, clean_test_db
):
    """Cleanup is in a finally block; a leaked database is a real cost."""
    from seldon.core.replay_check import existing_databases

    append_event(project_dir, create_event(str(uuid.uuid4())))
    full_replay(project_dir, neo4j_driver, TEST_DATABASE)
    replay_check(project_dir, neo4j_driver, TEST_DATABASE)

    leftovers = [n for n in existing_databases(neo4j_driver) if is_scratch_database(n)]
    assert leftovers == []


@neo4j_tests
def test_replay_check_never_writes_to_the_live_database(
    neo4j_driver, project_dir, clean_test_db
):
    """The live graph is read only. Anything else would make the check unsafe."""
    append_event(project_dir, create_event(str(uuid.uuid4())))
    full_replay(project_dir, neo4j_driver, TEST_DATABASE)
    before = fingerprint_graph(neo4j_driver, TEST_DATABASE)

    replay_check(project_dir, neo4j_driver, TEST_DATABASE)

    after = fingerprint_graph(neo4j_driver, TEST_DATABASE)
    assert after.states == before.states
    assert after.edges == before.edges
    assert after.node_count == before.node_count
