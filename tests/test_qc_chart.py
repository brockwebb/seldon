"""QC-002 Part D: AD-037-R7's inspection reserve and R8's chart.

R7: the task's reservation sets aside `inspection_reserve_share` (10%) for inspection; the judgment sampler's rate falls
with the reserve, and `check:` commands never skip. R8: `seldon qc chart` reports, per project, the premise-false,
first-article reject and milestone defect rates, CPI per task and huddles per task; its first reading is the five
pre-station tasks of QC-002's spend table (CPI only).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.cli import main
from seldon.core import stations as S
from tests import stations_scaffold as F

SELDON = Path(__file__).resolve().parents[1]


def test_the_sampler_rate_falls_with_the_reserve_and_calls_nothing_without_a_calibrated_judge():
    judge_calls = []

    def judge():
        judge_calls.append(1)
        raise RuntimeError("judge_uncalibrated")
    full = S.judgment_plan(["a", "b", "c", "d"], 1.0, 0.5, judge)
    low = S.judgment_plan(["a", "b", "c", "d"], 0.1, 0.5, judge)
    empty = S.judgment_plan(["a", "b", "c", "d"], 0.0, 0.5, judge)
    assert full["rate"] == 0.5 and full["sampled"] == 2
    assert low["rate"] == 0.05 and low["sampled"] == 1 and empty["sampled"] == 0
    assert full["status"].startswith("deferred: RuntimeError: judge_uncalibrated") and full["model_calls"] == 0


def test_checks_never_skip_when_the_reserve_is_spent(tmp_path):
    """A reserve of zero (an estimate of zero) still runs every `check:` command."""
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(60))
    F.record(p, S.EVENT_PART_COMPLETE, {"part": "B", "planned_share": 0.5, "tokens": 10})
    ran = []
    S.inspect(p, F.TASK_ID, F.events(p), S.load_stations_config({"stations": {"inspection_reserve_share": 1e-9}}),
              300, F.emitter(p), run=lambda cmd, *a, **k: ran.append(cmd) or {"command": cmd, "outcome": "pass",
                                                                             "exit": 0, "seconds": 0.0, "tail": ""})
    (m,) = F.events(p, S.EVENT_MILESTONE)
    assert ran == [F.PASS] and m["payload"]["judgment"]["sampled"] == 0
    assert m["payload"]["inspection"] == {"check_seconds": 0.0, "model_tokens": 0, "reserve_tokens": 0,
                                          "share_of_estimate": 0.0}


def test_the_first_reading_is_the_five_tasks_cpi_only():
    seed = S.load_seed(SELDON / "docs" / "evidence" / "qc002" / "cpi_first_reading.yaml")
    assert [(r["task"], r["ratio"]) for r in seed] == [
        ("SQ-010", 2.198), ("SQ-012", 0.1567), ("SQ-013", 0.5833), ("SQ-014", 0.6), ("SQ-015", 0.6373)]
    assert [round(r["cpi"], 3) for r in seed] == [0.455, 6.383, 1.714, 1.667, 1.569]
    out = S.chart([], "seldon", seed=seed, min_points=10)
    assert out["premise_false_rate"]["n"] == 0 and out["individuals_chart"] == {"drawn": False, "n": 5, "needs": 10}


def test_the_individuals_chart_draws_from_ten_tasks():
    rows = [{"task": f"T{i}", "project": "x", "source": "seed", "cpi": c}
            for i, c in enumerate([1.0, 1.2, 0.8, 1.1, 0.9, 1.0, 1.3, 0.7, 1.0, 1.0])]
    ind = S.chart([], "x", seed=rows, min_points=10)["individuals_chart"]
    assert ind["drawn"] and ind["mean"] == 1.0 and ind["unpl"] > 1.3 and ind["lnpl"] < 0.7


def test_station_rates_are_counted_from_the_records(tmp_path):
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(60))
    F.record(p, S.EVENT_PART_COMPLETE, {"part": "A", "planned_share": 0.5, "tokens": 900_000})
    S.inspect(p, F.TASK_ID, F.events(p), S.load_stations_config({}), 300, F.emitter(p))
    out = S.chart(F.events(p), "proj", seed=[], min_points=10)
    assert out["milestone_defect_rate"] == {"k": 0, "n": 1, "rate": 0.0}
    (row,) = out["tasks"]
    assert row["cpi"] == pytest.approx(0.5 / 0.9, 1e-3) and row["huddles"] == 1


def test_seldon_qc_chart_prints_the_five_rows(monkeypatch):
    monkeypatch.chdir(SELDON)
    r = CliRunner().invoke(main, ["qc", "chart"])
    assert r.exit_code == 0, r.output
    for task, ratio, cpi in (("SQ-010", "2.20", "0.455"), ("SQ-012", "0.16", "6.383"), ("SQ-013", "0.58", "1.714"),
                             ("SQ-014", "0.60", "1.667"), ("SQ-015", "0.64", "1.569")):
        line = next(x for x in r.output.splitlines() if x.strip().startswith(task))
        assert ratio in line and cpi in line, line
