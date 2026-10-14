"""QC-002 Part A (AD-037-R6 c): the milestone station. A dispatched session appends `part_complete` at each Part
boundary; the dispatcher runs that Part's `check:` criteria, computes CPI (earned value over actual cost) and records
`milestone`. A failed check stops the session; CPI below 0.8 opens a huddle and does not stop; a task with no
`**Parts:**` header is refused at registration as `parts_undeclared`.

The three plants are the three tests named `test_plant_*`; each fails on the HEAD before QC-002
(docs/evidence/qc002/plants_fail_on_head.txt).
"""
from __future__ import annotations

import os

import pytest
from click.testing import CliRunner

from seldon.cli import main
from tests import stations_scaffold as F

# `seldon.core.stations` is imported inside each test, not here, so that on the HEAD before QC-002 each plant fails
# on its own assertion or call rather than the whole module failing to collect.


def _inspect(p, **kw):
    from seldon.core import stations as S
    scfg = S.load_stations_config(F.config(p)["dispatch"])
    return S.inspect(p, F.TASK_ID, F.events(p), scfg, 300, F.emitter(p), **kw)


def test_plant_a_failing_check_at_a_part_boundary_stops_the_session(tmp_path, monkeypatch):
    p = F.make_project(tmp_path, check_a=F.FAIL)
    F.launch(p, at=F.ago(60))
    F.write_log(p, 400_000)
    monkeypatch.chdir(p)
    monkeypatch.setenv("SELDON_SESSION_ID", "child-1")
    r = CliRunner().invoke(main, ["dispatch", "part-complete", "--part", "A"])
    assert r.exit_code == 0, r.output
    from seldon.core import stations as S
    (pc,) = F.events(p, S.EVENT_PART_COMPLETE)
    assert pc["payload"]["tokens"] == 400_000 and pc["payload"]["planned_share"] == 0.5

    out = _inspect(p)
    (m,) = F.events(p, S.EVENT_MILESTONE)
    assert m["payload"]["defect"] is True and m["payload"]["checks"][0]["outcome"] == "fail"
    (stop,) = F.events(p, S.EVENT_SESSION_STOP)
    assert stop["payload"]["station"] == "milestone" and stop["payload"]["kind"] == "line"
    assert out["reap"] is None, "a line stop is never reaped"

    # The session halts at its next boundary, and says so on the record before it ends.
    r = CliRunner().invoke(main, ["dispatch", "boundary"])
    assert r.exit_code == S.HALT_EXIT, r.output
    (halted,) = F.events(p, S.EVENT_ANDON_HALTED)
    assert halted["payload"]["stop_event_id"] == stop["event_id"]


def test_plant_cpi_below_the_line_opens_a_huddle_and_does_not_stop(tmp_path, monkeypatch):
    # Part A is half the estimate (1M); 800k tokens spent on it: CPI 0.5 / 0.8 = 0.625.
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(60))
    F.write_log(p, 800_000)
    monkeypatch.chdir(p)
    monkeypatch.setenv("SELDON_SESSION_ID", "child-1")
    r = CliRunner().invoke(main, ["dispatch", "part-complete", "--part", "A"])
    assert r.exit_code == 0, r.output
    from seldon.core import stations as S
    _inspect(p)
    (m,) = F.events(p, S.EVENT_MILESTONE)
    assert m["payload"]["cpi"] == pytest.approx(0.625) and m["payload"]["defect"] is False
    (h,) = F.events(p, S.EVENT_HUDDLE)
    assert h["payload"]["opened_by"] == "cpi" and h["payload"]["cause"] is None and h["payload"]["gate"] is None
    assert F.events(p, S.EVENT_SESSION_STOP) == [], "CPI below the line opens a huddle without stopping"
    r = CliRunner().invoke(main, ["dispatch", "boundary"])
    assert r.exit_code == 0, r.output


def test_plant_a_task_with_no_parts_header_is_refused_at_registration(tmp_path, monkeypatch):
    from seldon.commands import cc
    from seldon.core import prior_art
    p = F.make_project(tmp_path, extra="")
    (p / "baseline.txt").write_text("cc_tasks/an_older_task.md\n", encoding="utf-8")
    monkeypatch.setattr(cc, "enforce_design_reference", lambda *a, **k: None)
    monkeypatch.setattr(cc.models, "ensure_fresh", lambda *a, **k: None)
    monkeypatch.setattr(cc, "enforce_task_models", lambda *a, **k: None)
    monkeypatch.setattr(prior_art, "registration_refusal", lambda *a, **k: None)
    with pytest.raises(ValueError, match="parts_undeclared"):
        cc.register_task_file(project_dir=p, config={"qc": {"parts_baseline": "baseline.txt"}}, driver=None,
                              database="none", domain_config=None, task_path=p / "cc_tasks" / f"{F.STEM}.md",
                              allow_untracked=True, session_id=None)


def test_a_baseline_task_and_a_project_without_a_baseline_are_not_rechecked(tmp_path):
    from seldon.core import stations as S
    p = F.make_project(tmp_path, extra="")
    task = p / "cc_tasks" / f"{F.STEM}.md"
    (p / "baseline.txt").write_text(f"cc_tasks/{F.STEM}.md\n", encoding="utf-8")
    assert S.parts_registration_refusal(task, p, {"qc": {"parts_baseline": "baseline.txt"}}) is None
    assert S.parts_registration_refusal(task, p, {}) is None, "no baseline named: the project has not opted in"
    task.write_text(task.read_text() + "\n**Parts:** A 0.5, B 0.6.\n", encoding="utf-8")
    (p / "baseline.txt").write_text("\n", encoding="utf-8")
    assert "sum to 1.100" in S.parts_registration_refusal(task, p, {"qc": {"parts_baseline": "baseline.txt"}})


def test_cpi_is_earned_over_actual_and_each_part_is_answered_once(tmp_path):
    from seldon.core import stations as S
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(60))
    F.record(p, S.EVENT_PART_COMPLETE, {"part": "A", "planned_share": 0.5, "tokens": 400_000})
    _inspect(p)
    F.record(p, S.EVENT_PART_COMPLETE, {"part": "B", "planned_share": 0.5, "tokens": 900_000})
    _inspect(p)
    _inspect(p)        # idempotent: a second inspector answers nothing twice
    ms = F.events(p, S.EVENT_MILESTONE)
    assert [m["payload"]["part"] for m in ms] == ["A", "B"]
    assert ms[0]["payload"]["cpi"] == pytest.approx(1.25) and ms[1]["payload"]["cpi"] == pytest.approx(1 / 0.9, 1e-3)
    # Part B's `judgment:` criterion is planned for the sampler and read by nobody until QC-003 (zero calls).
    j = ms[1]["payload"]["judgment"]
    assert j["items"] == 1 and j["model_calls"] == 0 and j["status"].startswith("deferred")
    assert ms[1]["payload"]["inspection"]["reserve_tokens"] == 100_000


def test_an_unrunnable_check_opens_a_huddle_and_is_not_a_pass(tmp_path):
    from seldon.core import stations as S
    p = F.make_project(tmp_path, check_a="no-such-command-qc002 --x")
    F.launch(p, at=F.ago(60))
    F.record(p, S.EVENT_PART_COMPLETE, {"part": "A", "planned_share": 0.5, "tokens": 100_000})
    _inspect(p)
    (m,) = F.events(p, S.EVENT_MILESTONE)
    assert m["payload"]["checks"][0]["outcome"] == "unrunnable" and m["payload"]["defect"] is False
    (h,) = F.events(p, S.EVENT_HUDDLE)
    assert h["payload"]["opened_by"] == "check_unrunnable"


def test_session_tokens_count_each_message_once_and_leave_cache_reads_out(tmp_path):
    from seldon.core import stations as S
    p = F.make_project(tmp_path)
    F.write_log(p, 123_456)
    t = S.session_tokens(p / "logs" / "dispatch" / f"{F.STEM}.log")
    assert t["tokens"] == 123_456 and t["messages"] == 2 and t["cache_read"] == 1000


def test_the_parts_header_and_part_criteria_parse_from_this_tasks_own_file():
    from seldon.core import stations as S
    text = (F.Path(__file__).resolve().parents[1] / "cc_tasks"
            / "2026-10-14_QC-002_ad037_r6_four_stations_in_the_dispatcher.md").read_text(encoding="utf-8")
    assert [(x["name"], x["share"]) for x in S.parse_parts(text)["parts"]] == [
        ("A", 0.35), ("B", 0.25), ("C", 0.25), ("D", 0.15)]
    assert S.part_criteria(text, "A")["checks"] == ["pytest tests/test_dispatch_milestone.py -q", "seldon cc register"]
    assert S.part_criteria(text, "D")["checks"][-1] == "seldon verify"
