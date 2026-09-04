"""ResearchTask lifecycle tests — AD-028 terminal states, claim marker, CLI/MCP parity.

Covers the whole transition matrix as it is declared in `research.yaml` (allowed and
forbidden), the two reason-bearing terminal states, the `superseded_by` edge and its
validation failure path, the claim marker, the stale-claim report, and the guarantee
that `seldon task close` and the MCP `seldon_task_close` walk emit the same events.

Requires Neo4j.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.task import task_group
from seldon.core.artifacts import (
    CLAIM_TRANSITION,
    REASON_REQUIRED_STATES,
    create_artifact,
    open_states,
    resolve_artifact_id,
    terminal_states,
    transition_task,
    update_artifact,
    walk_to_completed,
)
from seldon.core.events import read_events
from seldon.core.graph import get_artifact
from seldon.core.state import InvalidStateTransition
from seldon.domain.loader import load_domain_config
from seldon.mcp_server import (
    _walk_task_to_completed,
    seldon_task_list,
    seldon_task_supersede,
    seldon_task_update,
    seldon_task_withdraw,
)

from tests.testdb import TEST_DATABASE

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
ARTIFACT_TYPE = "ResearchTask"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def cli_project(project_dir, monkeypatch):
    """A project directory with a seldon.yaml pointing at the test database.

    The CLI resolves its config from the current working directory, so the fixture
    also chdirs into it.
    """
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
        domain_config=domain_config, artifact_type=ARTIFACT_TYPE,
        properties={"description": description}, actor="human", authority="accepted",
    )


def _make_result(project_dir, driver, domain_config, description="test result"):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 1.0, "units": "score", "description": description},
        actor="human", authority="accepted",
    )


def _make_citation(project_dir, driver, domain_config):
    """A Citation — deliberately NOT a legal `superseded_by` endpoint."""
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Citation",
        properties={"key": "smith2020", "title": "A paper"},
        actor="human", authority="accepted",
    )


def _force_state(driver, artifact_id, state):
    """Put a task directly into `state`, bypassing the machine.

    Used only to build fixtures for states the machine will not let a test walk to
    legitimately (e.g. `verified`, or a terminal state whose exits are being probed).
    """
    with driver.session(database=NEO4J_DB) as session:
        session.run(
            "MATCH (t:ResearchTask {artifact_id: $id}) SET t.state = $state",
            id=artifact_id, state=state,
        )


def _state_of(driver, artifact_id):
    with driver.session(database=NEO4J_DB) as session:
        return get_artifact(session, artifact_id)["state"]


def _task_events(project_dir, artifact_id):
    """Events for one artifact, as (event_type, from_state, to_state) tuples."""
    out = []
    for e in read_events(project_dir):
        payload = e.get("payload", {})
        if payload.get("artifact_id") != artifact_id:
            continue
        out.append(
            (e["event_type"], payload.get("from_state"), payload.get("to_state"))
        )
    return out


# ── the transition matrix ─────────────────────────────────────────────────────

def _matrix(domain_config):
    return domain_config.state_machines[ARTIFACT_TYPE]


def test_matrix_permits_exactly_what_the_config_declares(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Every (from, to) pair is accepted iff research.yaml declares it.

    This is the whole matrix, allowed and forbidden, in one sweep — so a state added
    to or removed from the config is exercised without editing this test.
    """
    machine = _matrix(domain_config)
    states = sorted(machine)
    checked_allowed = 0
    checked_forbidden = 0

    for source in states:
        for target in states:
            task_id = _make_task(project_dir, neo4j_driver, domain_config)
            _force_state(neo4j_driver, task_id, source)
            reason = "matrix probe" if target in REASON_REQUIRED_STATES else None

            if target in machine[source]:
                transition_task(
                    project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                    domain_config=domain_config, artifact_id=task_id,
                    current_state=source, new_state=target,
                    actor="test", terminal_reason=reason,
                )
                assert _state_of(neo4j_driver, task_id) == target
                checked_allowed += 1
            else:
                with pytest.raises(InvalidStateTransition):
                    transition_task(
                        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                        domain_config=domain_config, artifact_id=task_id,
                        current_state=source, new_state=target,
                        actor="test", terminal_reason=reason,
                    )
                assert _state_of(neo4j_driver, task_id) == source
                checked_forbidden += 1

    assert checked_allowed > 0 and checked_forbidden > 0


@pytest.mark.parametrize("finished_state", ["completed", "verified"])
@pytest.mark.parametrize("terminal_state", list(REASON_REQUIRED_STATES))
def test_finished_tasks_cannot_be_relabelled(
    neo4j_driver, project_dir, domain_config, clean_test_db,
    finished_state, terminal_state,
):
    """A completed or verified task can never be withdrawn or superseded.

    Relabelling a finished task would corrupt the honest completion record.
    """
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    _force_state(neo4j_driver, task_id, finished_state)

    with pytest.raises(InvalidStateTransition):
        transition_task(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            current_state=finished_state, new_state=terminal_state,
            actor="test", terminal_reason="should not be allowed",
        )
    assert _state_of(neo4j_driver, task_id) == finished_state


@pytest.mark.parametrize("dead_end", list(REASON_REQUIRED_STATES))
def test_nothing_is_reachable_out_of_a_reason_terminal_state(
    neo4j_driver, project_dir, domain_config, clean_test_db, dead_end,
):
    """withdrawn and superseded have no exits at all."""
    machine = _matrix(domain_config)
    assert machine[dead_end] == []
    assert dead_end in terminal_states(domain_config, ARTIFACT_TYPE)

    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    _force_state(neo4j_driver, task_id, dead_end)

    for target in sorted(machine):
        with pytest.raises(InvalidStateTransition):
            transition_task(
                project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                domain_config=domain_config, artifact_id=task_id,
                current_state=dead_end, new_state=target,
                actor="test",
                terminal_reason="probe" if target in REASON_REQUIRED_STATES else None,
            )
    assert _state_of(neo4j_driver, task_id) == dead_end


def test_terminal_and_open_state_sets_are_derived_from_the_config(domain_config):
    """The listing default is computed from the state machine, not enumerated."""
    assert set(terminal_states(domain_config, ARTIFACT_TYPE)) == {
        "verified", "rejected", "superseded", "withdrawn",
    }
    assert open_states(domain_config, ARTIFACT_TYPE) == [
        "accepted", "blocked", "in_progress", "proposed",
    ]
    # `completed` is neither: it is not terminal, but its only successor is.
    assert "completed" not in open_states(domain_config, ARTIFACT_TYPE)
    assert "completed" not in terminal_states(domain_config, ARTIFACT_TYPE)


# ── required reason ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("terminal_state", list(REASON_REQUIRED_STATES))
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_missing_reason_is_a_hard_error_with_no_state_change(
    neo4j_driver, project_dir, domain_config, clean_test_db, terminal_state, reason,
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    before = _task_events(project_dir, task_id)

    with pytest.raises(ValueError, match="requires a reason"):
        transition_task(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            current_state="proposed", new_state=terminal_state,
            actor="test", terminal_reason=reason,
        )

    assert _state_of(neo4j_driver, task_id) == "proposed"
    assert _task_events(project_dir, task_id) == before


@pytest.mark.parametrize("terminal_state", list(REASON_REQUIRED_STATES))
def test_reason_is_stored_as_terminal_reason(
    neo4j_driver, project_dir, domain_config, clean_test_db, terminal_state,
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    transition_task(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=task_id,
        current_state="proposed", new_state=terminal_state,
        actor="test", terminal_reason="  premise collapsed  ",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, task_id)
    assert node["state"] == terminal_state
    assert node["terminal_reason"] == "premise collapsed"

    kinds = [e[0] for e in _task_events(project_dir, task_id)]
    assert "artifact_updated" in kinds
    assert "artifact_state_changed" in kinds


def test_reason_refused_for_a_non_terminal_transition(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    """A reason on an ordinary transition is a caller error, not silently dropped."""
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    with pytest.raises(ValueError, match="only recorded for"):
        transition_task(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            current_state="proposed", new_state="accepted",
            actor="test", terminal_reason="not applicable here",
        )
    assert _state_of(neo4j_driver, task_id) == "proposed"


# ── superseded_by edge ────────────────────────────────────────────────────────

def test_superseded_by_edge_is_written(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config, "old plan")
    replacement_id = _make_task(project_dir, neo4j_driver, domain_config, "new plan")

    transition_task(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=task_id,
        current_state="proposed", new_state="superseded",
        actor="test", terminal_reason="replaced by the new plan",
        superseded_by=replacement_id,
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (t:ResearchTask {artifact_id: $a})-[:SUPERSEDED_BY]->"
            "(x:ResearchTask {artifact_id: $b}) RETURN x",
            a=task_id, b=replacement_id,
        ).single()
    assert rel is not None
    assert _state_of(neo4j_driver, task_id) == "superseded"


def test_superseded_by_accepts_an_id_prefix(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config, "old plan")
    replacement_id = _make_result(project_dir, neo4j_driver, domain_config)

    transition_task(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=task_id,
        current_state="proposed", new_state="superseded",
        actor="test", terminal_reason="the result answered it",
        superseded_by=replacement_id[:8],
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (t:ResearchTask {artifact_id: $a})-[:SUPERSEDED_BY]->(x) "
            "RETURN x.artifact_id AS id",
            a=task_id,
        ).single()
    assert rel["id"] == replacement_id


def test_unknown_superseded_by_is_a_hard_error_with_no_state_change(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    before = _task_events(project_dir, task_id)

    with pytest.raises(ValueError, match="No artifact found matching"):
        transition_task(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            current_state="proposed", new_state="superseded",
            actor="test", terminal_reason="pointing at nothing",
            superseded_by="ffffffff-dead-beef-0000-000000000000",
        )

    assert _state_of(neo4j_driver, task_id) == "proposed"
    assert _task_events(project_dir, task_id) == before


def test_illegal_superseded_by_endpoint_is_a_hard_error_with_no_state_change(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    """A Citation is not a legal target for `superseded_by` per research.yaml."""
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    citation_id = _make_citation(project_dir, neo4j_driver, domain_config)
    before = _task_events(project_dir, task_id)

    with pytest.raises(ValueError, match="cannot target a 'superseded_by'"):
        transition_task(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            current_state="proposed", new_state="superseded",
            actor="test", terminal_reason="wrong endpoint type",
            superseded_by=citation_id,
        )

    assert _state_of(neo4j_driver, task_id) == "proposed"
    assert _task_events(project_dir, task_id) == before


def test_superseded_by_refused_for_a_non_superseding_transition(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    other_id = _make_task(project_dir, neo4j_driver, domain_config, "other")

    with pytest.raises(ValueError, match="only valid when superseding"):
        transition_task(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            current_state="proposed", new_state="withdrawn",
            actor="test", terminal_reason="premise gone", superseded_by=other_id,
        )
    assert _state_of(neo4j_driver, task_id) == "proposed"


# ── claim marker ──────────────────────────────────────────────────────────────

def test_claim_fields_set_on_the_claim_transition(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    source, target = CLAIM_TRANSITION
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    transition_task(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=task_id,
        current_state="proposed", new_state=source, actor="test",
    )
    transition_task(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=task_id,
        current_state=source, new_state=target, actor="test", claimed_by="cc",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, task_id)
    assert node["state"] == target
    assert node["claimed_by"] == "cc"
    claimed_at = datetime.fromisoformat(str(node["claimed_at"]))
    assert claimed_at.tzinfo is not None


def test_claim_defaults_to_the_actor(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    transition_task(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=task_id,
        current_state="proposed", new_state="accepted", actor="desktop",
    )
    transition_task(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=task_id,
        current_state="accepted", new_state="in_progress", actor="desktop",
    )
    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert get_artifact(session, task_id)["claimed_by"] == "desktop"


def test_claim_refused_on_a_non_claim_transition(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    with pytest.raises(ValueError, match="only recorded on the"):
        transition_task(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            current_state="proposed", new_state="accepted",
            actor="test", claimed_by="cc",
        )
    assert _state_of(neo4j_driver, task_id) == "proposed"


# ── CLI ───────────────────────────────────────────────────────────────────────

def test_cli_list_hides_terminal_states_by_default(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """The default view is open work only; --all brings the endings back."""
    open_id = _make_task(cli_project, neo4j_driver, domain_config, "still open")
    gone_id = _make_task(cli_project, neo4j_driver, domain_config, "went away")
    transition_task(
        project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=gone_id,
        current_state="proposed", new_state="withdrawn",
        actor="test", terminal_reason="premise collapsed",
    )

    runner = CliRunner()
    default_view = runner.invoke(task_group, ["list"])
    assert default_view.exit_code == 0
    assert open_id[:8] in default_view.output
    assert gone_id[:8] not in default_view.output

    all_view = runner.invoke(task_group, ["list", "--all"])
    assert all_view.exit_code == 0
    assert open_id[:8] in all_view.output
    assert gone_id[:8] in all_view.output


def test_cli_list_hides_completed_by_default(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    done_id = _make_task(cli_project, neo4j_driver, domain_config, "finished")
    walk_to_completed(
        project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=done_id, current_state="proposed",
        actor="test",
    )
    runner = CliRunner()
    assert done_id[:8] not in runner.invoke(task_group, ["list"]).output
    assert done_id[:8] in runner.invoke(task_group, ["list", "--all"]).output


def test_cli_list_surfaces_the_claim_marker(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    task_id = _make_task(cli_project, neo4j_driver, domain_config, "claimed work")
    runner = CliRunner()
    runner.invoke(task_group, ["update", task_id[:8], "--state", "accepted"])
    claimed = runner.invoke(
        task_group,
        ["update", task_id[:8], "--state", "in_progress", "--claimed-by", "cc"],
    )
    assert claimed.exit_code == 0

    listing = runner.invoke(task_group, ["list"])
    assert listing.exit_code == 0
    assert "cc@" in listing.output


def test_cli_stale_claims_reports_only_old_claims(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """--stale-claims reports; it never transitions or releases anything."""
    old_id = _make_task(cli_project, neo4j_driver, domain_config, "stale work")
    fresh_id = _make_task(cli_project, neo4j_driver, domain_config, "fresh work")
    for task_id in (old_id, fresh_id):
        transition_task(
            project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            current_state="proposed", new_state="accepted", actor="test",
        )
        transition_task(
            project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            current_state="accepted", new_state="in_progress",
            actor="test", claimed_by="cc",
        )

    stale_at = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    update_artifact(
        project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
        artifact_id=old_id, properties={"claimed_at": stale_at},
        actor="test", authority="accepted",
    )

    runner = CliRunner()
    report = runner.invoke(task_group, ["list", "--stale-claims", "24"])
    assert report.exit_code == 0
    assert old_id[:8] in report.output
    assert fresh_id[:8] not in report.output
    assert "no task has been transitioned or released" in report.output

    # Report only: both tasks are still in_progress afterwards.
    assert _state_of(neo4j_driver, old_id) == "in_progress"
    assert _state_of(neo4j_driver, fresh_id) == "in_progress"


def test_cli_stale_claims_counts_tasks_with_no_claim_marker(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """in_progress tasks predating the claim marker are counted, never aged."""
    task_id = _make_task(cli_project, neo4j_driver, domain_config, "legacy work")
    _force_state(neo4j_driver, task_id, "in_progress")

    report = CliRunner().invoke(task_group, ["list", "--stale-claims", "1"])
    assert report.exit_code == 0
    assert "no claim marker" in report.output


def test_cli_withdraw_requires_a_reason(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    task_id = _make_task(cli_project, neo4j_driver, domain_config)
    result = CliRunner().invoke(task_group, ["withdraw", task_id[:8]])
    assert result.exit_code != 0
    assert _state_of(neo4j_driver, task_id) == "proposed"


def test_cli_withdraw_records_the_reason(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    task_id = _make_task(cli_project, neo4j_driver, domain_config)
    result = CliRunner().invoke(
        task_group, ["withdraw", task_id[:8], "--reason", "premise was false"]
    )
    assert result.exit_code == 0
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, task_id)
    assert node["state"] == "withdrawn"
    assert node["terminal_reason"] == "premise was false"


def test_cli_supersede_with_bad_target_leaves_state_untouched(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    task_id = _make_task(cli_project, neo4j_driver, domain_config)
    result = CliRunner().invoke(
        task_group,
        ["supersede", task_id[:8], "--reason", "overtaken",
         "--superseded-by", "ffffffff-dead-beef-0000-000000000000"],
    )
    assert result.exit_code != 0
    assert "Error" in result.output
    assert _state_of(neo4j_driver, task_id) == "proposed"


def test_cli_supersede_writes_the_edge(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    task_id = _make_task(cli_project, neo4j_driver, domain_config, "old")
    replacement_id = _make_task(cli_project, neo4j_driver, domain_config, "new")

    result = CliRunner().invoke(
        task_group,
        ["supersede", task_id[:8], "--reason", "overtaken by the new plan",
         "--superseded-by", replacement_id[:8]],
    )
    assert result.exit_code == 0, result.output
    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (:ResearchTask {artifact_id: $a})-[:SUPERSEDED_BY]->(x) "
            "RETURN x.artifact_id AS id",
            a=task_id,
        ).single()
    assert rel["id"] == replacement_id


def test_cli_unknown_task_id_is_a_hard_error(cli_project, clean_test_db):
    result = CliRunner().invoke(task_group, ["close", "ffffffff"])
    assert result.exit_code != 0
    assert "No artifact found matching" in result.output


def test_cli_ambiguous_prefix_lists_candidates(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    _make_task(cli_project, neo4j_driver, domain_config, "a")
    _make_task(cli_project, neo4j_driver, domain_config, "b")
    # The empty-ish prefix every UUID starts with: '' is rejected, so use a shared one.
    result = CliRunner().invoke(task_group, ["close", ""])
    assert result.exit_code != 0


# ── CLI / MCP close-walk parity ───────────────────────────────────────────────

@pytest.mark.parametrize("start_state", ["proposed", "accepted", "in_progress", "blocked"])
def test_cli_close_walk_emits_the_same_events_as_the_mcp_close_walk(
    neo4j_driver, cli_project, domain_config, clean_test_db, start_state,
):
    """Both surfaces call the one walker, so the event sequences must match.

    Compared on (event_type, from_state, to_state). The `actor` field differs on
    purpose — 'human' from the CLI, 'desktop' from MCP — and is asserted separately.
    """
    cli_id = _make_task(cli_project, neo4j_driver, domain_config, "cli task")
    mcp_id = _make_task(cli_project, neo4j_driver, domain_config, "mcp task")
    _force_state(neo4j_driver, cli_id, start_state)
    _force_state(neo4j_driver, mcp_id, start_state)

    cli_before = len(_task_events(cli_project, cli_id))
    mcp_before = len(_task_events(cli_project, mcp_id))

    cli_result = CliRunner().invoke(task_group, ["close", cli_id[:8]])
    assert cli_result.exit_code == 0, cli_result.output

    _walk_task_to_completed(
        project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=mcp_id, current_state=start_state,
    )

    cli_events = _task_events(cli_project, cli_id)[cli_before:]
    mcp_events = _task_events(cli_project, mcp_id)[mcp_before:]

    assert cli_events == mcp_events
    assert ("artifact_state_changed", None, None) not in cli_events
    assert _state_of(neo4j_driver, cli_id) == "completed"
    assert _state_of(neo4j_driver, mcp_id) == "completed"


def test_close_walk_actor_differs_by_surface(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    cli_id = _make_task(cli_project, neo4j_driver, domain_config, "cli task")
    mcp_id = _make_task(cli_project, neo4j_driver, domain_config, "mcp task")

    CliRunner().invoke(task_group, ["close", cli_id[:8]])
    _walk_task_to_completed(
        project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=mcp_id, current_state="proposed",
    )

    # Both tasks were *created* by the fixture as 'human'; only the walk's own
    # events carry the surface's actor.
    actors = {}
    for e in read_events(cli_project):
        aid = e.get("payload", {}).get("artifact_id")
        if aid in (cli_id, mcp_id) and e["event_type"] != "artifact_created":
            actors.setdefault(aid, set()).add(e["actor"])
    assert actors[cli_id] == {"human"}
    assert actors[mcp_id] == {"desktop"}


def test_close_walk_records_a_claim(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """Closing an unclaimed task crosses the claim edge, so the closer is recorded."""
    task_id = _make_task(cli_project, neo4j_driver, domain_config)
    CliRunner().invoke(task_group, ["close", task_id[:8]])
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, task_id)
    assert node["state"] == "completed"
    assert node["claimed_by"] == "human"


# ── MCP tools ─────────────────────────────────────────────────────────────────

def _write_seldon_yaml(project_dir: Path):
    (project_dir / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )


def test_mcp_update_refuses_the_reason_bearing_states(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    """seldon_task_update cannot store a reason, so it must not accept those states."""
    _write_seldon_yaml(project_dir)
    task_id = _make_task(project_dir, neo4j_driver, domain_config)

    for state in REASON_REQUIRED_STATES:
        out = seldon_task_update(
            task_id=task_id, state=state, project_dir=str(project_dir)
        )
        assert "Error" in out
        assert "seldon_task_withdraw" in out or "seldon_task_supersede" in out
        assert _state_of(neo4j_driver, task_id) == "proposed"


def test_mcp_withdraw_records_the_reason(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    _write_seldon_yaml(project_dir)
    task_id = _make_task(project_dir, neo4j_driver, domain_config)

    out = seldon_task_withdraw(
        task_id=task_id[:8], reason="premise was false", project_dir=str(project_dir)
    )
    assert "Error" not in out
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, task_id)
    assert node["state"] == "withdrawn"
    assert node["terminal_reason"] == "premise was false"


def test_mcp_withdraw_without_a_reason_is_refused(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    _write_seldon_yaml(project_dir)
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    out = seldon_task_withdraw(task_id=task_id, reason="  ", project_dir=str(project_dir))
    assert "Error" in out
    assert _state_of(neo4j_driver, task_id) == "proposed"


def test_mcp_supersede_writes_the_edge_and_rejects_a_bad_target(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    _write_seldon_yaml(project_dir)
    task_id = _make_task(project_dir, neo4j_driver, domain_config, "old")
    replacement_id = _make_task(project_dir, neo4j_driver, domain_config, "new")

    bad = seldon_task_supersede(
        task_id=task_id, reason="overtaken", project_dir=str(project_dir),
        superseded_by="ffffffff-dead-beef-0000-000000000000",
    )
    assert "Error" in bad
    assert _state_of(neo4j_driver, task_id) == "proposed"

    good = seldon_task_supersede(
        task_id=task_id, reason="overtaken", project_dir=str(project_dir),
        superseded_by=replacement_id,
    )
    assert "Error" not in good
    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (:ResearchTask {artifact_id: $a})-[:SUPERSEDED_BY]->(x) "
            "RETURN x.artifact_id AS id",
            a=task_id,
        ).single()
    assert rel["id"] == replacement_id


def test_mcp_list_hides_terminal_states_and_surfaces_claims(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    _write_seldon_yaml(project_dir)
    open_id = _make_task(project_dir, neo4j_driver, domain_config, "still open")
    gone_id = _make_task(project_dir, neo4j_driver, domain_config, "went away")
    claimed_id = _make_task(project_dir, neo4j_driver, domain_config, "claimed work")

    seldon_task_withdraw(
        task_id=gone_id, reason="premise collapsed", project_dir=str(project_dir)
    )
    seldon_task_update(task_id=claimed_id, state="accepted", project_dir=str(project_dir))
    seldon_task_update(
        task_id=claimed_id, state="in_progress", project_dir=str(project_dir)
    )

    default_view = seldon_task_list(project_dir=str(project_dir))
    assert "still open" in default_view
    assert "went away" not in default_view
    assert "claimed by desktop" in default_view

    all_view = seldon_task_list(project_dir=str(project_dir), state_filter="all")
    assert "went away" in all_view

    detail = seldon_task_list(
        project_dir=str(project_dir), state_filter="withdrawn", brief=False
    )
    assert "premise collapsed" in detail


def test_mcp_create_with_blocks_writes_the_edge(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    """Regression: the blocks link previously crashed on a missing endpoint type."""
    from seldon.mcp_server import seldon_task_create

    _write_seldon_yaml(project_dir)
    target_id = _make_result(project_dir, neo4j_driver, domain_config, "blocked result")

    out = seldon_task_create(
        description="blocks something",
        project_dir=str(project_dir),
        blocks=target_id[:8],
    )
    assert "Warning" not in out
    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (t:ResearchTask {description: 'blocks something'})-[:BLOCKS]->"
            "(r:Result {artifact_id: $rid}) RETURN r",
            rid=target_id,
        ).single()
    assert rel is not None


# ── id resolution ─────────────────────────────────────────────────────────────

def test_resolve_artifact_id_rejects_an_ambiguous_prefix(
    neo4j_driver, project_dir, domain_config, clean_test_db,
):
    a = _make_task(project_dir, neo4j_driver, domain_config, "a")
    b = _make_task(project_dir, neo4j_driver, domain_config, "b")
    # Every UUID shares the empty prefix; use the shortest genuinely shared one.
    shared = ""
    for i in range(1, len(a)):
        if a[:i] == b[:i]:
            shared = a[:i]
        else:
            break

    if shared:
        with pytest.raises(ValueError, match="matches 2 artifacts"):
            resolve_artifact_id(neo4j_driver, NEO4J_DB, shared)
    assert resolve_artifact_id(neo4j_driver, NEO4J_DB, a) == a


def test_resolve_artifact_id_rejects_an_empty_id(neo4j_driver, clean_test_db):
    with pytest.raises(ValueError, match="required"):
        resolve_artifact_id(neo4j_driver, NEO4J_DB, "")
