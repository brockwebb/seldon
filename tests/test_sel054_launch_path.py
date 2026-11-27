"""SEL-054 Part A: a coordination task launches beside an exclusive build, and a project's premises gate every launch.

`cc_tasks/2026-11-27_SEL-054_four_things_the_factory_needs_from_the_dispatcher_are_built.md`, answering factory's
filings `2026-11-27_filing_from_factory_a_coordinator_task_launches_beside_an_exclusive_build_task.md` and
`2026-11-26_filing_from_factory_a_project_needs_a_premise_the_dispatcher_evaluates_for_every_task_so_a_spent_grant_
stops_new_launches.md`; AD-038 ADDENDUM 16, R40 to R42.

The planner and config tests need no database. The two scenarios run real `seldon dispatch once` passes against a
scratch repository and the per-process Neo4j test database, with the stub `claude`: an exclusive build holds the pass
lease for its whole session, and the OODA filed beside it launches from the holder's own inspection loop.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core import lane as L
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, add_task, git, make_project, register, run_cli, task_states, write_stub,
)

LANE = {"name_pattern": r"^OODA-\d+", "slots": 1, "writes": ["notes/**"]}


def conc(exclusive=None, touches=None):
    raw_ex = exclusive
    return D.parse_concurrency(raw_ex, touches, {})


def _cand(tid, exclusive=None, touches=None, lane=False):
    return {"task_id": tid, "concurrency": conc(exclusive, touches), "lane": lane}


# ============================================================================ configuration

def test_a_lane_is_absent_unless_declared(tmp_path):
    p = make_project(tmp_path)
    cfg = D.load_dispatch_config(p)
    assert cfg["coordination_lane"] is None and cfg["premises"] == []


def test_a_lane_without_a_writes_declaration_is_refused_at_load(tmp_path):
    p = make_project(tmp_path, dispatch_extra={"coordination_lane": {"name_pattern": "^OODA-", "slots": 1}})
    with pytest.raises(D.DispatchConfigError, match="writes"):
        D.load_dispatch_config(p)


def test_a_lane_pattern_that_does_not_compile_is_refused_at_load(tmp_path):
    p = make_project(tmp_path, dispatch_extra={"coordination_lane": {**LANE, "name_pattern": "^OODA-("}})
    with pytest.raises(D.DispatchConfigError, match="does not compile"):
        D.load_dispatch_config(p)


def test_a_project_premise_needs_a_statement_and_a_check(tmp_path):
    p = make_project(tmp_path, dispatch_extra={"premises": [{"statement": "grant has room"}]})
    with pytest.raises(D.DispatchConfigError, match="check"):
        D.load_dispatch_config(p)


# ============================================================================ the planner

def test_lane_tasks_go_first_among_eligible_candidates():
    lane = L.load_lane(LANE)
    rows = [{"task_id": "b", "name": "FAC-31", "created_at": "2026-11-26T01:00:00Z"},
            {"task_id": "o", "name": "OODA-001", "created_at": "2026-11-26T03:00:00Z"},
            {"task_id": "c", "name": "FAC-32", "created_at": "2026-11-26T02:00:00Z"}]
    assert [r["task_id"] for r in D.fifo(rows, lane)] == ["o", "b", "c"]
    assert [r["task_id"] for r in D.fifo(rows)] == ["b", "c", "o"], "no lane, no change (DN-006 decision 9)"


def test_a_lane_task_launches_beside_a_running_exclusive_task():
    running = [{"task_id": "build", "concurrency": conc(), "lane": False}]
    plan = D.plan_launches([_cand("ooda", lane=True)], running, 1, {}, lane=L.load_lane(LANE))
    assert plan["launch"] == ["ooda"]


def test_a_lane_task_launches_beside_a_waiting_exclusive_task():
    running = [{"task_id": "r", "concurrency": conc("no", "kg/**"), "lane": False}]
    plan = D.plan_launches([_cand("x"), _cand("ooda", lane=True)], running, 2, {}, lane=L.load_lane(LANE))
    assert plan["launch"] == ["ooda"] and plan["deferred"]["x"]["reason"] == "exclusive_waits"


def test_a_second_lane_task_waits_for_the_first():
    running = [{"task_id": "ooda1", "concurrency": conc(), "lane": True}]
    plan = D.plan_launches([_cand("ooda2", lane=True)], running, 1, {}, lane=L.load_lane(LANE))
    assert plan["launch"] == []
    assert plan["deferred"]["ooda2"] == {"reason": L.DEFERRED_LANE_SLOTS, "with": ["ooda1"], "overlap": []}


def test_two_lane_candidates_in_one_pass_take_one_slot():
    plan = D.plan_launches([_cand("o1", lane=True), _cand("o2", lane=True)], [], 1, {}, lane=L.load_lane(LANE))
    assert plan["launch"] == ["o1"] and plan["deferred"]["o2"]["reason"] == L.DEFERRED_LANE_SLOTS


def test_a_running_lane_task_neither_holds_an_exclusive_task_nor_takes_its_slot():
    running = [{"task_id": "ooda", "concurrency": conc(), "lane": True}]
    plan = D.plan_launches([_cand("build")], running, 1, {}, lane=L.load_lane(LANE))
    assert plan["launch"] == ["build"]


def test_without_a_lane_the_flag_changes_nothing():
    running = [{"task_id": "build", "concurrency": conc(), "lane": False}]
    plan = D.plan_launches([_cand("ooda", lane=True)], running, 1, {})
    assert plan["launch"] == [] and plan["deferred"]["ooda"]["reason"] == "exclusive_waits"


def test_a_lane_rows_c6_is_its_slot_not_the_in_place_claim():
    lane = L.load_lane(LANE)
    row = {"candidate": True, "eligible": False, "failed": ["c6"],
           "criteria": {"c1": {"ok": True}, "c6": {"in_progress_claim": {"artifact_id": "b"}, "ok": False}}}
    L.apply_lane_c6(row, [], lane)
    assert row["eligible"] and row["criteria"]["c6"]["lane"] and row["failed"] == []
    L.apply_lane_c6(row, ["o1"], lane)
    assert not row["eligible"] and row["criteria"]["c6"]["reason"] == L.DEFERRED_LANE_SLOTS


def test_a_lane_branch_may_change_only_what_its_lane_declares():
    lane = L.load_lane({**LANE, "writes": ["notes/**", "for_operator/"]})
    writes = ["notes/a.md", "notes/sub/b.md", "for_operator/x.md", "seldon/core/dispatch.py",
              "cc_tasks/OODA-1_RESULT.md", "seldon_events.jsonl"]
    exempt = {"cc_tasks/OODA-1_RESULT.md", "seldon_events.jsonl"}
    assert L.outside_writes(writes, lane, exempt) == ["seldon/core/dispatch.py"]


# ============================================================================ project premises (no database)

def test_project_premises_name_each_false_one_with_its_output(tmp_path):
    from seldon.core import stations as S
    ok = f"{sys.executable} -c pass"
    spent = f"{sys.executable} -c \"print('grant G-2026-11-28 spent'); raise SystemExit(4)\""
    review = L.review_project_premises(
        [{"statement": "the grant has room", "check": spent}, {"statement": "always", "check": ok}],
        S.run_check, tmp_path, 30)
    assert review["outcome"] == "false"
    (f,) = review["false"]
    assert f["statement"] == "the grant has room" and "G-2026-11-28" in f["output"] and f["exit_code"] == 4
    assert L.episode_identity(review) == "the grant has room"


# ============================================================================ the scenarios (Neo4j)

@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _wait(pred, what, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {what}")


def _events(p, kind):
    return [e for e in read_events(p) if e["event_type"] == kind]


def _supervisor_log(p, stem):
    path = p / "logs" / "dispatch" / f"{stem}.supervisor.log"
    return path.read_text() if path.exists() else "(no supervisor log)"


def _lane_project(tmp_path, **extra):
    p = make_project(tmp_path, dispatch_extra={"coordination_lane": {**LANE, "merge_wait_s": 120},
                                               "poll_interval_s": 1, **extra})
    git(p, "add", "-A")
    return p


@pytest.mark.usefixtures("neo4j_available")
def test_an_ooda_filed_beside_an_exclusive_build_launches_during_the_build_and_merges_after(
        tmp_path, neo4j_driver, dc):
    """factory's test of the filing: an OODA filed while an exclusive build is in flight is launched at the
    dispatcher's next look, and a second OODA filed meanwhile waits for the first."""
    p = _lane_project(tmp_path)
    marks = tmp_path / "marks.txt"
    add_task(p, "FAC-31-build")
    add_task(p, "OODA-001")
    add_task(p, "OODA-002")
    register(p, neo4j_driver, dc, "FAC-31-build", "2026-11-26T01:00:00Z")
    write_stub(p, {
        # The build waits for the first OODA to have started, up to a ceiling, so the overlap is a rendezvous.
        "FAC-31-build": {"write": {"src/build.txt": "b\n"}, "complete": True, "mark": str(marks),
                         "rendezvous": {"peers": ["OODA-001"], "ceiling_s": 60}},
        "OODA-001": {"write": {"notes/ooda1.md": "o\n"}, "complete": True, "mark": str(marks), "sleep": 3},
        "OODA-002": {"write": {"notes/ooda2.md": "o\n"}, "complete": True, "mark": str(marks)},
    })
    # Both OODAs are registered after the build launches: the holder's loop is the only thing that can launch them.
    import threading

    def file_oodas():
        _wait(lambda: task_states(neo4j_driver).get("FAC-31-build") == "in_progress", "the build to launch", 60)
        register(p, neo4j_driver, dc, "OODA-001", "2026-11-26T03:00:00Z")
        register(p, neo4j_driver, dc, "OODA-002", "2026-11-26T03:00:01Z")
    t = threading.Thread(target=file_oodas)
    t.start()
    res = run_cli(p, dispatch_group, ["once"])
    t.join()
    assert res.exit_code == 0, res.output
    lines = {ln.split()[0] + " " + ln.split()[1] for ln in marks.read_text().splitlines()}
    assert "FAC-31-build rendezvous_met" in lines, (res.output, _supervisor_log(p, "OODA-001"))
    def ooda_finish():
        return [e["payload"] for e in _events(p, D.EVENT_FINISHED)
                if e["payload"].get("source_file") == "cc_tasks/OODA-001.md"]
    _wait(lambda: ooda_finish(), "OODA-001's finish")
    assert ooda_finish()[-1]["outcome"] == "merged", (ooda_finish()[-1], _supervisor_log(p, "OODA-001"))
    launched = {e["payload"]["source_file"]: e for e in _events(p, D.EVENT_LAUNCHED)}
    assert "cc_tasks/OODA-001.md" in launched
    assert launched["cc_tasks/OODA-001.md"]["payload"]["lane"] is True
    # The second OODA did not launch beside the first (one lane slot): it is still queued after this pass.
    assert "cc_tasks/OODA-002.md" not in launched
    assert task_states(neo4j_driver)["FAC-31-build"] == "completed"
    assert git(p, "show", "main:notes/ooda1.md", check=False).returncode == 0


@pytest.mark.usefixtures("neo4j_available")
def test_a_lane_branch_that_writes_outside_its_lane_is_not_merged(tmp_path, neo4j_driver, dc):
    p = _lane_project(tmp_path)
    add_task(p, "OODA-003")
    register(p, neo4j_driver, dc, "OODA-003", "2026-11-26T03:00:00Z")
    write_stub(p, {"OODA-003": {"write": {"notes/ok.md": "o\n", "src/build.txt": "not mine\n"}, "complete": True}})
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    def finished():
        return [e["payload"] for e in _events(p, D.EVENT_FINISHED)
                if e["payload"].get("source_file") == "cc_tasks/OODA-003.md"]
    _wait(finished, "OODA-003's finish")
    fin = finished()
    assert fin and fin[-1]["outcome"] == "merge_blocked", _supervisor_log(p, "OODA-003")
    assert fin[-1]["merge"]["reason"] == L.MERGE_LANE_WROTE_OUTSIDE
    assert fin[-1]["merge"]["files"] == ["src/build.txt"]


@pytest.mark.usefixtures("neo4j_available")
def test_a_false_project_premise_refuses_every_launch_once_per_episode_and_clears_itself(
        tmp_path, neo4j_driver, dc):
    flag = tmp_path / "grant_spent"
    check = f"{sys.executable} -c \"import pathlib,sys; p=pathlib.Path({str(flag)!r}); " \
            f"print('grant G-7 spent') if p.exists() else None; sys.exit(4 if p.exists() else 0)\""
    p = make_project(tmp_path, dispatch_extra={"premises": [{"statement": "the week's grant has room",
                                                             "check": check}]})
    add_task(p, "T-1")
    register(p, neo4j_driver, dc, "T-1", "2026-11-26T01:00:00Z")
    write_stub(p, {"T-1": {"complete": True}})
    flag.write_text("x")
    for _ in range(2):
        res = run_cli(p, dispatch_group, ["once"])
        assert res.exit_code == 0, res.output
        assert "project_premise_false" in res.output and "G-7" in res.output
    refused = [e["payload"] for e in _events(p, D.EVENT_REFUSED)
               if e["payload"].get("reason") == L.REFUSED_PROJECT_PREMISE]
    assert len(refused) == 1, "one record per episode, not one per pass"
    assert refused[0]["false"][0]["statement"] == "the week's grant has room"
    assert task_states(neo4j_driver)["T-1"] in ("proposed", "accepted"), "nothing launched"
    issues = [e for e in read_events(p) if e["event_type"] == "artifact_created"
              and (e.get("payload") or {}).get("artifact_type") == "Issue"]
    assert issues == [], "a standing condition files no Issue"
    flag.unlink()
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    assert task_states(neo4j_driver)["T-1"] == "completed", res.output
