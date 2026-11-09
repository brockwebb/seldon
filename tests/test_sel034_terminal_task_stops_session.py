"""SEL-034 Part A (AD-037-R16): a task that goes terminal stops its running session at the next tool boundary.

hazbrief HB-140 (249b85dc, SEL-030) was withdrawn at 05:10:20Z, five minutes after launch, and its session ran on for
ninety minutes: the PreToolUse gate delivered only hard stops, and a withdrawal wrote none. Each test here fails on
main before this build: `terminal_transition`, `terminal_stop_due` and `signal_terminal` do not exist there, and the
gate lets the withdrawn session's call through. The gate tests need no Neo4j (tests/stations_scaffold.py); the
signal test drives `seldon task withdraw`'s core path against the test database.
"""
from __future__ import annotations

import json

from click.testing import CliRunner

from seldon.cli import main
from seldon.core import stations as S
from seldon.core.events import append_event, make_event
from tests import stations_scaffold as F

DESKTOP_SESSION = "desktop-session-1"


def _state(p, to_state: str, session_id: str = DESKTOP_SESSION, from_state: str = "in_progress",
           actor: str = "desktop") -> dict:
    ev = make_event(S.EVENT_STATE_CHANGED, actor, "accepted",
                    {"artifact_id": F.TASK_ID, "artifact_type": "ResearchTask", "from_state": from_state,
                     "to_state": to_state}, session_id=session_id)
    append_event(p, ev)
    return ev


def _gate(p, monkeypatch, tool="Bash"):
    monkeypatch.chdir(p)
    monkeypatch.setenv("SELDON_SESSION_ID", "child-1")
    return CliRunner().invoke(main, ["dispatch", "tool-gate", "--project", str(p)],
                              input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                                                "tool_input": {"command": "python -m pytest"}}))


def test_a_withdrawn_tasks_session_is_refused_at_its_next_call_and_ended(tmp_path, monkeypatch):
    """The fixture of the task's Part A: HB-140's shape. The call before the withdrawal proceeds; the next one is
    refused with the state and the actor, `andon_halted` says `task_terminal`, and the hook ends the session."""
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(300))
    r = _gate(p, monkeypatch)
    assert r.exit_code == 0 and r.output.strip() == "", "the task is running: the call proceeds"
    withdrawal = _state(p, "withdrawn")
    r = _gate(p, monkeypatch)
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "withdrawn" in decision["permissionDecisionReason"] and "desktop" in decision["permissionDecisionReason"]
    assert out["continue"] is False and "withdrawn" in out["stopReason"], "the session ends, not only this call"
    (halted,) = F.events(p, S.EVENT_ANDON_HALTED)
    hp = halted["payload"]
    assert hp["stop_reason"] == S.STOP_REASON_TASK_TERMINAL and hp["task_state"] == "withdrawn"
    assert hp["transition_event_id"] == withdrawal["event_id"] and hp["by"] == "desktop"
    # Every later call is refused too, and `andon_halted` is not written again.
    r = _gate(p, monkeypatch, tool="Write")
    assert json.loads(r.output)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert len(F.events(p, S.EVENT_ANDON_HALTED)) == 1


def test_superseded_rejected_and_verified_by_another_hand_also_halt(tmp_path, monkeypatch):
    for state in ("superseded", "rejected", "verified"):
        p = F.make_project(tmp_path / state)
        F.launch(p, at=F.ago(300))
        _state(p, state)
        r = _gate(p, monkeypatch)
        assert json.loads(r.output)["continue"] is False, state


def test_the_session_withdrawing_its_own_task_is_not_halted_by_its_own_act(tmp_path, monkeypatch):
    """A session whose premise turned out false withdraws its own task and then writes its RESULT."""
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(300))
    _state(p, "withdrawn", session_id="child-1", actor="cc")
    r = _gate(p, monkeypatch)
    assert r.exit_code == 0 and r.output.strip() == ""
    assert F.events(p, S.EVENT_ANDON_HALTED) == []


def test_a_non_terminal_move_does_not_halt(tmp_path, monkeypatch):
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(300))
    _state(p, "blocked")
    r = _gate(p, monkeypatch)
    assert r.exit_code == 0 and r.output.strip() == ""


def test_the_withdrawal_answers_the_task_terminal_stop_when_one_is_written(tmp_path, monkeypatch):
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(300))
    _state(p, "withdrawn")
    stop = S.signal_terminal(p, F.TASK_ID, "desktop")
    assert stop["payload"]["reason"] == S.STOP_REASON_TASK_TERMINAL and stop["payload"]["kind"] == "hard"
    _gate(p, monkeypatch)
    (halted,) = F.events(p, S.EVENT_ANDON_HALTED)
    assert halted["payload"]["stop_event_id"] == stop["event_id"]
    assert S.pending_hard_stop(S.task_records(F.events(p), F.TASK_ID)) is None, "answered: the reap does not fire"


def test_the_signal_is_written_once_and_never_after_the_finish(tmp_path):
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(300))
    _state(p, "withdrawn")
    assert S.signal_terminal(p, F.TASK_ID, "desktop") is not None
    assert S.signal_terminal(p, F.TASK_ID, "desktop") is None, "one task_terminal stop per launch"
    q = F.make_project(tmp_path / "finished")
    F.launch(q, at=F.ago(300))
    F.record(q, "dispatch_finished", {"outcome": "merged"})
    _state(q, "withdrawn")
    assert S.signal_terminal(q, F.TASK_ID, "desktop") is None, "no session is running: nothing to stop"


def test_the_holders_inspection_writes_the_stop_and_reaps_a_live_session(tmp_path):
    """The backstop: a transition that wrote no stop (any path) gets one from the inspection, and a `task_terminal`
    stop past the reap interval is reaped even while the session's log is growing (HB-140's log grew throughout)."""
    p = F.make_project(tmp_path)
    scfg = S.load_stations_config({})
    F.launch(p, at=F.ago(3600))
    F.write_log(p, 1)
    _state(p, "withdrawn")
    out = S.inspect(p, F.TASK_ID, F.events(p), scfg, 300, F.emitter(p))
    (stop,) = [s for s in out["stops"] if s["reason"] == S.STOP_REASON_TASK_TERMINAL]
    assert stop["kind"] == "hard" and stop["reading"]["state"] == "withdrawn"
    assert out["reap"] is None, "a stop written now is not yet due"
    # Age the stop past the interval with the log still growing: reaped, not deferred.
    events = F.events(p)
    for e in events:
        if e["event_type"] == S.EVENT_SESSION_STOP:
            e["timestamp"] = F._iso(F.ago(400))
    out = S.inspect(p, F.TASK_ID, events, scfg, 300, F.emitter(p))
    assert out["reap"] is not None and out["reap"]["reason"] == S.STOP_REASON_TASK_TERMINAL
    assert "reap_deferred" not in out
    assert len([e for e in F.events(p, S.EVENT_SESSION_STOP)
                if e["payload"]["reason"] == S.STOP_REASON_TASK_TERMINAL]) == 1


def test_the_stop_gate_lets_a_terminal_tasks_session_end_without_running_checks(tmp_path, monkeypatch):
    p = F.make_project(tmp_path, check_a="false")
    F.launch(p, at=F.ago(300))
    F.record(p, S.EVENT_PART_COMPLETE, {"part": "A"})
    _state(p, "withdrawn")
    monkeypatch.chdir(p)
    monkeypatch.setenv("SELDON_SESSION_ID", "child-1")
    r = CliRunner().invoke(main, ["dispatch", "stop-gate", "--project", str(p)],
                           input=json.dumps({"hook_event_name": "Stop", "cwd": str(p)}))
    assert r.exit_code == 0 and r.output.strip() == "", r.output
    assert F.events(p, S.EVENT_STOP_GATE) == []


def test_seldon_task_withdraw_on_an_in_progress_task_signals_the_dispatcher(tmp_path, neo4j_driver, clean_test_db):
    """The transition itself writes the stop (CLI and MCP both go through `transition_task`)."""
    from seldon.core.artifacts import create_artifact, transition_task
    from seldon.domain.loader import load_domain_config
    from tests.dispatch_scaffold import RESEARCH_YAML
    from tests.testdb import TEST_DATABASE

    dc = load_domain_config(RESEARCH_YAML)
    p = F.make_project(tmp_path)
    tid = create_artifact(project_dir=p, driver=neo4j_driver, database=TEST_DATABASE, domain_config=dc,
                          artifact_type="ResearchTask", properties={"description": "t", "name": "sel034-a-signal"},
                          actor="desktop", authority="accepted", artifact_id=F.TASK_ID)
    for cur, new, claim in (("proposed", "accepted", None), ("accepted", "in_progress", "dispatcher:h:1")):
        transition_task(project_dir=p, driver=neo4j_driver, database=TEST_DATABASE, domain_config=dc,
                        artifact_id=tid, current_state=cur, new_state=new, actor="dispatcher", claimed_by=claim)
    F.launch(p, at=F.ago(60))
    transition_task(project_dir=p, driver=neo4j_driver, database=TEST_DATABASE, domain_config=dc, artifact_id=tid,
                    current_state="in_progress", new_state="withdrawn", actor="desktop", session_id=DESKTOP_SESSION,
                    terminal_reason="premise false")
    (stop,) = [e for e in F.events(p, S.EVENT_SESSION_STOP)]
    assert stop["payload"]["reason"] == S.STOP_REASON_TASK_TERMINAL and stop["payload"]["by"] == "desktop"
