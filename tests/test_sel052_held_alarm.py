"""SEL-052 Part A: a hold that waits on a person reaches the dispatcher's `notify` with its reason and age.

factory's 2026-11-24 filing: FAC-06 sat `merge_blocked` for ten days and nothing rang, because a `blocked` task is not
a candidate and the stuck alarm counts only refused candidates; the one banner its finish raised was dismissed. The
coordinator's own observation of 2026-11-26: critical-thinking-ai CTAI-006R, `merge_blocked: uncommitted_changes`,
sat twenty minutes until a person looked.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from seldon.commands import dispatch as dispatch_cmd
from seldon.core import dispatch as D
from seldon.core.artifacts import transition_task
from tests.test_dispatch_stuck_and_journal import (  # noqa: F401  (fixtures)
    NEO4J_DB, _events, _notifications, _register, _run, domain_config, project)

T0 = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------------------------------------ the rule, pure

def test_a_block_rings_once_it_has_waited_and_again_each_repeat():
    blocked = {"t": {"blocked_at": _iso(T0), "reason": "merge_blocked: uncommitted_changes"}}
    state, rings = D.advance_held({}, blocked, T0 + timedelta(seconds=899), 900, 86400)
    assert rings == [] and state["t"]["rings"] == 0
    state, rings = D.advance_held(state, blocked, T0 + timedelta(seconds=900), 900, 86400)
    assert rings == [("t", 900.0)] and state["t"]["rings"] == 1
    state, rings = D.advance_held(state, blocked, T0 + timedelta(hours=5), 900, 86400)
    assert rings == []
    state, rings = D.advance_held(state, blocked, T0 + timedelta(seconds=900 + 86400), 900, 86400)
    assert [t for t, _ in rings] == ["t"] and state["t"]["rings"] == 2


def test_repeat_zero_rings_once_and_a_new_block_rings_again():
    first = {"t": {"blocked_at": _iso(T0), "reason": "x"}}
    state, rings = D.advance_held({}, first, T0 + timedelta(hours=1), 900, 0)
    assert len(rings) == 1
    state, rings = D.advance_held(state, first, T0 + timedelta(days=30), 900, 0)
    assert rings == []
    # Unblocked (drops out), then blocked again later: a new block, a new ring.
    state, rings = D.advance_held(state, {}, T0 + timedelta(days=31), 900, 0)
    assert state == {} and rings == []
    again = {"t": {"blocked_at": _iso(T0 + timedelta(days=32)), "reason": "y"}}
    state, rings = D.advance_held(state, again, T0 + timedelta(days=32, hours=1), 900, 0)
    assert len(rings) == 1


def test_a_block_with_no_recorded_time_is_aged_from_the_first_pass_that_saw_it():
    blocked = {"t": {"blocked_at": None, "reason": "x"}}
    state, rings = D.advance_held({}, blocked, T0, 900, 0)
    assert rings == [] and state["t"]["blocked_at"] == _iso(T0)
    state, rings = D.advance_held(state, blocked, T0 + timedelta(seconds=901), 900, 0)
    assert len(rings) == 1


def test_the_remedy_names_the_command_that_clears_it():
    assert "redrive abcdef12" in D.held_remedy("abcdef1234", "merge_blocked: uncommitted_changes")
    assert "regate abcdef12" in D.held_remedy("abcdef1234", "stop_gate_unpassed: no RESULT")
    assert "redrive abcdef12" in D.held_remedy("abcdef1234", None)


@pytest.mark.parametrize("bad", [-1, "soon", True])
def test_a_bad_held_setting_is_refused_at_load(project, bad):
    import yaml
    cfg = D.load_dispatch_config(project)
    assert (cfg["held_alarm_after_s"], cfg["held_repeat_s"]) == (D.HELD_ALARM_AFTER_S_DEFAULT,
                                                                 D.HELD_REPEAT_S_DEFAULT)
    body = yaml.safe_load((project / "seldon.yaml").read_text(encoding="utf-8"))
    body["dispatch"]["held_alarm_after_s"] = bad
    (project / "seldon.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")
    with pytest.raises(D.DispatchConfigError, match="held_alarm_after_s"):
        D.load_dispatch_config(project)


# --------------------------------------------------------------------------------------------- through the pass

def _block(project, driver, domain_config, tid, reason):
    for a, b in (("proposed", "accepted"), ("accepted", "in_progress")):
        transition_task(project_dir=project, driver=driver, database=NEO4J_DB, domain_config=domain_config,
                        artifact_id=tid, current_state=a, new_state=b, actor="desktop", authority="accepted")
    transition_task(project_dir=project, driver=driver, database=NEO4J_DB, domain_config=domain_config,
                    artifact_id=tid, current_state="in_progress", new_state="blocked", actor="dispatcher",
                    authority="accepted", block_reason=reason)


def test_a_merge_blocked_task_rings_notify_with_its_reason_and_age(project, neo4j_driver, domain_config,
                                                                   monkeypatch):
    tid = _register(project, neo4j_driver, domain_config)
    _block(project, neo4j_driver, domain_config, tid, "merge_blocked: uncommitted_changes")
    (blocked_at,) = [e["timestamp"] for e in _events(project, "artifact_state_changed")
                     if e["payload"].get("to_state") == "blocked"]
    start = datetime.fromisoformat(blocked_at.replace("Z", "+00:00"))

    monkeypatch.setattr(dispatch_cmd, "_utcnow", lambda: start + timedelta(minutes=5))
    out = _run(project, ["once"])
    assert out.exit_code == 0, out.output
    assert not [n for n in _notifications(project) if n.startswith("held")], "rang before it had waited"

    monkeypatch.setattr(dispatch_cmd, "_utcnow", lambda: start + timedelta(minutes=20))
    out = _run(project, ["once"])
    assert out.exit_code == 0, out.output
    rang = [n for n in _notifications(project) if n.startswith("held")]
    assert rang == ["held merge_blocked: uncommitted_changes  "], _notifications(project)
    (ev,) = _events(project, D.EVENT_HELD)
    assert ev["payload"]["task_id"] == tid and ev["payload"]["age_s"] == 1200
    assert ev["payload"]["reason"] == "merge_blocked: uncommitted_changes"
    assert f"redrive {tid[:8]}" in ev["payload"]["remedy"]
    assert "HELD:" in out.output and "held 20m" in out.output

    # The next pass says nothing more; a day later it rings again.
    out = _run(project, ["once"])
    assert len(_events(project, D.EVENT_HELD)) == 1
    monkeypatch.setattr(dispatch_cmd, "_utcnow", lambda: start + timedelta(minutes=20, days=1))
    out = _run(project, ["once"])
    assert out.exit_code == 0, out.output
    assert len(_events(project, D.EVENT_HELD)) == 2
