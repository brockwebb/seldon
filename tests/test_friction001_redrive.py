"""FRICTION-001 Part B (AD-038-R2): a halted task is redriven, not re-issued.

Before this, `blocked` led only to `in_progress`, `superseded` and `withdrawn`, and only `proposed` and `accepted`
are dispatchable, so DESK-002's false stop cost a new task file (DESK-002R), a supersede and a re-registration. The
SQS dead-letter redrive is the prior art: the message goes back to its source queue with its identity intact.

The task's three tests, then the automatic redrive (step 3). Each fails on main 92f491b, where neither the edge nor
the command exists.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.commands.dispatch import dispatch_group
from seldon.core.artifacts import transition_task
from seldon.core.events import append_event, make_event, read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, add_task, git, make_project, register, run_cli, write_stub,
)
from tests.testdb import TEST_DATABASE as NEO4J_DB

STORE = "seldon_events.jsonl"

#: The registered task's id per project (a Path takes no attributes).
TIDS: dict = {}


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def project(tmp_path, neo4j_driver, clean_test_db, monkeypatch, domain_config):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    p = make_project(tmp_path, dispatch_extra={"stuck_after_passes_by_criterion": {}})
    add_task(p, "t1")
    tid = register(p, neo4j_driver, domain_config, "t1", "2026-10-17T00:00:00Z")
    git(p, "commit", "-q", "-m", "register t1", "--", STORE)
    git(p, "push", "-q")
    TIDS[p] = tid
    return p


def _halt(p: Path, driver, domain_config, reason: str) -> str:
    """The state a station's line stop leaves: launched, claimed by the dispatcher, a `session_stop`, blocked."""
    tid = TIDS[p]
    for cur, new, claim in (("proposed", "accepted", None), ("accepted", "in_progress", "dispatcher:h:1")):
        transition_task(project_dir=p, driver=driver, database=NEO4J_DB, domain_config=domain_config,
                        artifact_id=tid, current_state=cur, new_state=new, actor="dispatcher", claimed_by=claim)
    append_event(p, make_event("dispatch_launched", "dispatcher", "accepted",
                               {"task_id": tid, "source_file": "cc_tasks/t1.md"}))
    append_event(p, make_event("session_stop", "dispatcher", "accepted",
                               {"task_id": tid, "station": "milestone", "kind": "line", "reason": reason}))
    append_event(p, make_event("dispatch_finished", "dispatcher", "accepted", {"task_id": tid, "ok": False}))
    transition_task(project_dir=p, driver=driver, database=NEO4J_DB, domain_config=domain_config,
                    artifact_id=tid, current_state="in_progress", new_state="blocked", actor="dispatcher")
    git(p, "commit", "-q", "-m", "halted", "--", STORE)
    return tid


def _task(driver, tid) -> dict:
    with driver.session(database=NEO4J_DB) as s:
        return dict(s.run("MATCH (t:ResearchTask {artifact_id: $id}) RETURN t.state AS state, "
                          "t.claimed_by AS claimed_by", id=tid).single())


def test_a_blocked_task_redriven_is_a_candidate_on_the_next_pass(project, neo4j_driver, domain_config):
    tid = _halt(project, neo4j_driver, domain_config, "check_failed")
    out = run_cli(project, dispatch_group, ["redrive", tid[:8]])
    assert out.exit_code == 0, out.output
    assert _task(neo4j_driver, tid) == {"state": "accepted", "claimed_by": None}
    write_stub(project, {"t1": {"complete": True}})
    out = run_cli(project, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    assert f"launching {tid[:8]}" in out.output, out.output


def test_redrive_refuses_a_task_that_is_not_blocked(project, neo4j_driver):
    out = run_cli(project, dispatch_group, ["redrive", TIDS[project][:8]])
    assert out.exit_code != 0
    assert "not blocked" in out.output, out.output
    assert _task(neo4j_driver, TIDS[project])["state"] == "proposed"
    assert not [e for e in read_events(project) if e["event_type"] == "dispatch_redrive"]


def test_the_record_names_the_stop(project, neo4j_driver, domain_config):
    tid = _halt(project, neo4j_driver, domain_config, "check_failed")
    stop = [e for e in read_events(project) if e["event_type"] == "session_stop"][-1]
    out = run_cli(project, dispatch_group, ["redrive", "t1", "--actor", "desktop"])
    assert out.exit_code == 0, out.output
    rec = [e for e in read_events(project) if e["event_type"] == "dispatch_redrive"]
    assert len(rec) == 1
    p = rec[0]["payload"]
    assert (p["task_id"], p["answers"], p["stop_reason"], p["by"]) == (tid, stop["event_id"], "check_failed",
                                                                        "desktop")
    assert p["cleared_claim"] == "dispatcher:h:1"
    assert rec[0]["actor"] == "desktop"


def test_the_dispatcher_redrives_its_own_wrong_tree_stop_once(project, neo4j_driver, domain_config):
    """Step 3: a stop whose cause is the dispatcher's own defect is answered by the next pass, once."""
    tid = _halt(project, neo4j_driver, domain_config, "check_unrunnable_wrong_tree")
    write_stub(project, {"t1": {"complete": True}})
    out = run_cli(project, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    assert f"redrive: {tid[:8]}" in out.output, out.output
    assert f"launching {tid[:8]}" in out.output, out.output
    recs = [e for e in read_events(project) if e["event_type"] == "dispatch_redrive"]
    assert len(recs) == 1 and recs[0]["actor"] == "dispatcher" and recs[0]["payload"]["automatic"] is True


def test_any_other_stop_waits_for_a_session(project, neo4j_driver, domain_config):
    tid = _halt(project, neo4j_driver, domain_config, "check_failed")
    out = run_cli(project, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    assert "redrive:" not in out.output
    assert _task(neo4j_driver, tid)["state"] == "blocked"
