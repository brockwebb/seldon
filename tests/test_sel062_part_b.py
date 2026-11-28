"""SEL-062 Part B: the passes (REVIEW-001 F-07, F-09 to F-15, F-17, F-18, F-20).

`cc_tasks/2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say.md`;
rulings AD-038 ADDENDUM 17 (R40 amended, R46 new), AD-034 ADDENDUM 15 (R38 amended) and AD-037 erratum 01 (R23).

* F-15 (the root of F-07 and F-13): every pass and every status view evaluates the queue through one stage
  (`dispatch.evaluate_queue`) and runs one alarm stage (`dispatch.pass_alarms`); the parallel pass gains the held
  alarm, c13, c15 and station (a), and the status views plan with the lane.
* F-10: a lane task is exempt from exclusive holds only; its lane's `writes` overlap like any declaration.
* F-11: no scheduled full gate starts while a lane session is in flight in a serial lane project.
* F-12: `dispatch_gate.maybe_run` never raises; an unexpected error is recorded and printed.
* F-17: the event store is parsed once per pass while it is unchanged, and an append is read as its tail.
* F-18 and F-20: `dispatch status` shows the newest full gate's age and the effective alarm thresholds.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from seldon.commands import dispatch as dispatch_cmd
from seldon.commands import dispatch_gate as GATE
from seldon.commands import dispatch_lane as LANE
from seldon.commands import dispatch_worktree as W
from seldon.core import dispatch as D
from seldon.core import events as EV
from seldon.core import gate_plan as GP
from seldon.core import lane as LN
from seldon.core.artifacts import transition_task
from seldon.core.events import append_event, make_event
from tests.test_dispatch_stuck_and_journal import (  # noqa: F401  (fixtures)
    NEO4J_DB, _events, _notifications, _register, _run, domain_config, project)


def _set_dispatch(project, **values):
    body = yaml.safe_load((project / "seldon.yaml").read_text(encoding="utf-8"))
    body["dispatch"].update(values)
    (project / "seldon.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")


def _parallel(project, monkeypatch):
    from seldon.core import qc
    _set_dispatch(project, max_parallel=2)
    monkeypatch.setattr(qc, "parallel_opted_in", lambda project_dir, config: True)


def _block(project, driver, domain_config, tid, reason):
    for a, b in (("proposed", "accepted"), ("accepted", "in_progress")):
        transition_task(project_dir=project, driver=driver, database=NEO4J_DB, domain_config=domain_config,
                        artifact_id=tid, current_state=a, new_state=b, actor="desktop", authority="accepted")
    transition_task(project_dir=project, driver=driver, database=NEO4J_DB, domain_config=domain_config,
                    artifact_id=tid, current_state="in_progress", new_state="blocked", actor="dispatcher",
                    authority="accepted", block_reason=reason)


# ============================================================================ F-07 / F-15: one alarm stage

@pytest.mark.usefixtures("clean_test_db")
def test_part_b_the_held_alarm_rings_in_the_parallel_pass_too(project, neo4j_driver, domain_config, monkeypatch):
    _parallel(project, monkeypatch)
    tid = _register(project, neo4j_driver, domain_config)
    _block(project, neo4j_driver, domain_config, tid, "merge_blocked: uncommitted_changes")
    (blocked_at,) = [e["timestamp"] for e in _events(project, "artifact_state_changed")
                     if e["payload"].get("to_state") == "blocked"]
    start = datetime.fromisoformat(blocked_at.replace("Z", "+00:00"))
    monkeypatch.setattr(dispatch_cmd, "_utcnow", lambda: start + timedelta(minutes=20))
    out = _run(project, ["once"])
    assert out.exit_code == 0, out.output
    (ev,) = _events(project, D.EVENT_HELD)
    assert ev["payload"]["task_id"] == tid


@pytest.mark.usefixtures("clean_test_db")
def test_part_b_every_pass_and_status_view_evaluates_through_one_stage(project, neo4j_driver, domain_config,
                                                                      monkeypatch):
    # No task: a registered one would launch; the stage runs over an empty queue all the same.
    seen = []
    real = dispatch_cmd.evaluate_queue

    def spy(*a, **k):
        seen.append(k.get("view"))
        return real(*a, **k)
    monkeypatch.setattr(dispatch_cmd, "evaluate_queue", spy)
    assert _run(project, ["once"]).exit_code == 0
    assert _run(project, ["status"]).exit_code == 0
    _parallel(project, monkeypatch)
    assert _run(project, ["once"]).exit_code == 0
    assert _run(project, ["status"]).exit_code == 0
    assert seen == ["pass", "status", "pass", "status"], seen


@pytest.mark.usefixtures("clean_test_db")
def test_part_b_the_parallel_pass_applies_c13_and_c15_as_the_serial_pass_does(project, neo4j_driver, domain_config,
                                                                             monkeypatch):
    tid = _register(project, neo4j_driver, domain_config)
    hold = {tid: {"issue_id": "i-1", "false": [{"line": 1, "statement": "x", "outcome": "false"}]}}
    monkeypatch.setattr(dispatch_cmd, "_premise_holds", lambda project_dir, driver, database, **k: hold)
    for parallel in (False, True):
        if parallel:
            _parallel(project, monkeypatch)
        out = _run(project, ["status", "--json"])
        assert out.exit_code == 0, out.output
        body = json.loads(out.output[out.output.index("{"):])
        (row,) = [r for r in body["tasks"] if r["task_id"] == tid]
        assert row["criteria"]["c13"]["ok"] is False, (parallel, row["criteria"].get("c13"))


@pytest.mark.usefixtures("clean_test_db")
def test_part_b_the_status_views_order_the_lane_first_as_the_pass_does(project, neo4j_driver, domain_config,
                                                                      monkeypatch):
    first = _register(project, neo4j_driver, domain_config, rel="cc_tasks/build-1.md")
    lane = _register(project, neo4j_driver, domain_config, rel="cc_tasks/OODA-1.md")
    _set_dispatch(project, coordination_lane={"name_pattern": "^OODA-", "slots": 1, "writes": ["cc_tasks/**"]})
    for parallel in (False, True):
        if parallel:
            _parallel(project, monkeypatch)
        out = _run(project, ["status", "--json"])
        assert out.exit_code == 0, out.output
        body = json.loads(out.output[out.output.index("{"):])
        ids = [r["task_id"] for r in body["tasks"] if r["task_id"] in (first, lane)]
        assert ids == [lane, first], (parallel, ids)


# ============================================================================ F-10: the lane overlaps like anyone

LANE_CFG = {"name_pattern": "^OODA-", "slots": 1, "writes": ["cc_tasks/**", "for_operator/**"], "merge_wait_s": 60}


def _conc(paths, exclusive=False):
    return {"exclusive": exclusive, "paths": list(paths), "resources": []}


def test_part_b_a_lane_candidate_waits_on_a_running_task_that_touches_its_writes():
    lane = LN.load_lane(LANE_CFG)
    plan = D.plan_launches([{"task_id": "ooda", "concurrency": _conc([]), "lane": True}],
                           [{"task_id": "b", "concurrency": _conc(["for_operator/x.md"]), "lane": False}],
                           2, {}, lane=lane)
    assert plan["launch"] == [] and plan["deferred"]["ooda"]["reason"] == "overlap"


def test_part_b_a_running_lane_task_holds_its_writes_for_others():
    lane = LN.load_lane(LANE_CFG)
    plan = D.plan_launches([{"task_id": "b", "concurrency": _conc(["cc_tasks/new.md"]), "lane": False}],
                           [{"task_id": "ooda", "concurrency": _conc([]), "lane": True}],
                           2, {}, lane=lane)
    assert plan["launch"] == [] and plan["deferred"]["b"]["reason"] == "overlap"


def test_part_b_a_lane_task_still_runs_beside_an_exclusive_build():
    """R40 unchanged: the exclusive hold is the only one a lane task is exempt from."""
    lane = LN.load_lane(LANE_CFG)
    plan = D.plan_launches([{"task_id": "ooda", "concurrency": _conc([]), "lane": True}],
                           [{"task_id": "build", "concurrency": _conc([], exclusive=True), "lane": False}],
                           1, {}, lane=lane)
    assert plan["launch"] == ["ooda"]
    plan = D.plan_launches([{"task_id": "b", "concurrency": _conc(["src/x.py"]), "lane": False}],
                           [{"task_id": "ooda", "concurrency": _conc([]), "lane": True}],
                           2, {}, lane=lane)
    assert plan["launch"] == ["b"], "a lane task holds only its writes"


# ============================================================================ F-11: no scheduled gate beside a lane

@pytest.mark.usefixtures("clean_test_db")
def test_part_b_no_scheduled_gate_starts_while_a_lane_session_is_in_flight(project, neo4j_driver, domain_config,
                                                                          monkeypatch):
    _set_dispatch(project, coordination_lane=dict(LANE_CFG))
    calls = []
    monkeypatch.setattr(GATE, "maybe_run", lambda *a, **k: calls.append(k) or None)
    running = [{"artifact_id": "lane-1", "task_id": "lane-1", "name": "OODA-9", "source_file": "cc_tasks/OODA-9.md",
                "lane": True}]
    monkeypatch.setattr(LANE, "split_claims", lambda project_dir, cfg, claims: (list(running), []))
    monkeypatch.setattr(W, "_reap_stale", lambda *a, **k: a[-1])
    assert _run(project, ["once"]).exit_code == 0
    assert calls == [], "a lane session is in flight: no scheduled run"
    running.clear()
    assert _run(project, ["once"]).exit_code == 0
    assert len(calls) == 1, "the control: with nothing in flight the pass asks the schedule"


# ============================================================================ F-12: maybe_run never raises

def test_part_b_maybe_run_records_an_unexpected_error_and_does_not_raise(tmp_path, monkeypatch, capsys):
    (tmp_path / "seldon_events.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(GP, "declared", lambda g: True)
    monkeypatch.setattr(GP, "scheduled_due", lambda events, g, idle: "due: test")

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(GATE, "run_scheduled", boom)
    out = GATE.maybe_run(tmp_path, {"gates": {"slices": []}, "gate_command": "true"}, idle=True, session_id="s")
    assert out is None
    assert "disk full" in capsys.readouterr().err
    (ev,) = [e for e in EV.read_events(tmp_path) if e["event_type"] == GATE.EVENT_SCHEDULED_ERROR]
    assert "OSError: disk full" in ev["payload"]["error"] and ev["payload"]["why"] == "due: test"


# ============================================================================ F-17: one parse per pass

def _append(p: Path, kind: str, **payload):
    append_event(p, make_event(kind, "test", "accepted", payload))


def test_part_b_the_store_is_parsed_once_while_unchanged_and_an_append_is_read_as_its_tail(tmp_path):
    for i in range(5):
        _append(tmp_path, "x", n=i)
    with EV.pass_scope() as stats:
        a = EV.read_events(tmp_path)
        b = EV.read_events(tmp_path)
        _append(tmp_path, "x", n=5)
        c = EV.read_events(tmp_path)
        assert [len(a), len(b), len(c)] == [5, 5, 6]
        assert c == EV.read_events_uncached(tmp_path)
        assert stats["full"] == 1 and stats["tail"] == 1 and stats["hits"] >= 1, stats


def test_part_b_a_caller_that_mutates_what_it_read_does_not_change_what_the_next_reads(tmp_path):
    _append(tmp_path, "x", n=1)
    with EV.pass_scope():
        first = EV.read_events(tmp_path)
        first[0]["payload"]["n"] = 99
        first.append({"event_type": "planted"})
        again = EV.read_events(tmp_path)
    assert again[0]["payload"]["n"] == 1 and len(again) == 1


def test_part_b_a_rewritten_store_is_parsed_again_not_tailed(tmp_path):
    for i in range(3):
        _append(tmp_path, "x", n=i)
    with EV.pass_scope() as stats:
        EV.read_events(tmp_path)
        lines = (tmp_path / "seldon_events.jsonl").read_text(encoding="utf-8").splitlines()
        # A union merge or a rebase rewrites the file: the first line moves, so the prefix read before is gone.
        (tmp_path / "seldon_events.jsonl").write_text("\n".join(lines[1:] + lines[:1]) + "\n", encoding="utf-8")
        out = EV.read_events(tmp_path)
    assert [e["payload"]["n"] for e in out] == [1, 2, 0] and stats["full"] == 2


@pytest.mark.usefixtures("clean_test_db")
def test_part_b_a_pass_parses_the_store_once(project, neo4j_driver, domain_config, monkeypatch):
    counts = {}
    real = dispatch_cmd._pass

    def counted(*a, **k):
        with EV.pass_scope() as stats:
            out = real(*a, **k)
            counts.update(stats)
        return out
    # The pass opens its own scope; this outer one only reads the counters of the same scope.
    monkeypatch.setattr(dispatch_cmd, "_pass", counted)
    assert _run(project, ["once"]).exit_code == 0
    assert counts["full"] == 1, counts


# ============================================================================ F-18 / F-20: what status shows

def test_part_b_the_newest_full_gates_age_is_read_from_the_record():
    now = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
    gcfg = {"full_every_s": 86400, "full_overdue_s": 172800}
    events = [{"event_type": GP.EVENT_GATE_RUN, "timestamp": "2026-11-27T12:00:00Z",
               "payload": {"call_site": GP.CALL_SITE_SCHEDULED, "tier": GP.TIER_FULL, "outcome": GP.OUTCOME_PASS}}]
    age = GP.full_gate_age(events, gcfg, now=now)
    assert age["age_s"] == 86400 and age["anchor"] == "2026-11-27T12:00:00Z" and age["state"] == "due"
    assert GP.full_gate_age([], gcfg, now=now)["state"] == "never"


@pytest.mark.usefixtures("clean_test_db")
def test_part_b_status_shows_the_full_gates_age_and_the_effective_thresholds(project, neo4j_driver, domain_config):
    _register(project, neo4j_driver, domain_config)
    out = _run(project, ["status", "--json"])
    body = json.loads(out.output[out.output.index("{"):])
    assert body["stuck_thresholds"]["environment_in_flight"] == D.ENVIRONMENT_WAIT_PASSES_DEFAULT
    assert "full_gate" in body
    out = _run(project, ["status"])
    assert "environment_in_flight" in out.output and "full gate" in out.output


def test_part_b_the_environment_wait_default_is_past_a_producers_longest_normal_window():
    """AD-037 erratum 01: a producer's normal window is bounded by its gate timeout (seldon and hazbrief: 7,200 s), and
    seldon's full merge gates took p50 4,854 s and max 5,788 s (n=5). Twelve passes (3,600 s) rang inside them."""
    assert D.ENVIRONMENT_WAIT_PASSES_DEFAULT * 300 > D.PRODUCER_WINDOW_BOUND_S >= 5788
