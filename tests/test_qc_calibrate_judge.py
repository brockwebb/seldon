"""QC-001 Part C (AD-037-R5, R3): `seldon qc calibrate-judge` and the judge resolver's refusal. Zero model calls.

The lesson these tests consume (AD-032 FC-26): squiddy DN-022 §1, 2026-09-29: ABBA and replicate kappa reported as judge
calibration; neither measures self-preference. So a calibration report carries three separate numbers, a report
missing any of them is refused (`calibration_incomplete`), and a judge without a passing report on its current lock
entry is refused (`judge_uncalibrated`).

Every expected number below was computed by hand on the toy set, independently of the code:
  position bias   1 flip of 8 order pairs -> 0.125, Wilson-95 (0.0224, 0.4709)
  test-retest     7 of 8 replicate pairs agree; p_e = 5/8*6/8 + 3/8*2/8 = 0.5625; kappa = 0.3125/0.4375 = 0.7143;
                  Cohen (1960) SE = sqrt(0.875*0.125 / (8 * 0.4375^2)) = 0.2673
  self-preference generator plants caught 2 of 4 (0.5), reference plants 3 of 4 (0.75); difference 0.25,
                  Newcombe (1998) hybrid score interval (-0.3196, 0.6553)
"""
from __future__ import annotations

import json

import pytest
import yaml
from click.testing import CliRunner

from seldon import models as M
from seldon.core import qc
from tests.models_fixture import FIXTURE_IDS, write_models_home

ITEMS = ["i1", "i2", "i3", "i4"]


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = write_models_home(tmp_path)
    monkeypatch.setenv(M.MODELS_HOME_ENV, str(h))
    return h


def _set(path):
    items = [{"id": i, "defect_class": "premise_found_wrong", "receipt": f"toy:{i}", "defect": "toy",
              "criterion": "every count agrees with what it counts",
              "reference": {"source": {"operator_authored": "toy"}, "original": "a b", "planted": "a c",
                            "plant": {"from": "b", "to": "c"}},
              "generator": {"status": "slot", "instructions": "toy"}} for i in ITEMS]
    path.write_text(yaml.safe_dump({"schema": 1, "items": items}), encoding="utf-8")
    return path


def _rows():
    gen1 = {"AB": ["defect", "clean", "clean", "defect"], "BA": ["defect", "defect", "clean", "defect"]}
    ref1 = {"AB": ["defect", "defect", "defect", "clean"], "BA": ["defect", "defect", "defect", "clean"]}
    gen2 = ["defect", "clean", "defect", "defect"]
    ref2 = ["defect", "defect", "defect", "clean"]
    rows = []
    for half, by in (("generator", gen1), ("reference", ref1)):
        for order, vs in by.items():
            rows += [{"item": i, "half": half, "order": order, "replicate": 1, "verdict": v} for i, v in zip(ITEMS, vs)]
    for half, vs in (("generator", gen2), ("reference", ref2)):
        rows += [{"item": i, "half": half, "order": "AB", "replicate": 2, "verdict": v} for i, v in zip(ITEMS, vs)]
    return rows


def _cfg():
    return {"z": 1.959964, "defect_label": "defect", "bar": {"generator_catch_lower": 0.70, "n_min": 30}}


def test_each_number_is_computed_on_a_hand_checked_toy_set(tmp_path):
    items = qc.load_set(_set(tmp_path / "set.yaml"))
    rep = qc.calibrate(items, _rows(), _cfg())
    pb, tr, sp = rep["position_bias"], rep["test_retest"], rep["self_preference"]
    assert pb["n"] == 8 and pb["estimate"] == pytest.approx(0.125)
    assert pb["ci95"] == pytest.approx([0.0224, 0.4709], abs=1e-3)
    assert tr["n"] == 8 and tr["kappa"] == pytest.approx(0.7143, abs=1e-3)
    assert tr["kappa_se"] == pytest.approx(0.2673, abs=1e-3)
    assert tr["agreement"]["estimate"] == pytest.approx(0.875)
    assert sp["generator"]["n"] == 4 and sp["generator"]["estimate"] == pytest.approx(0.5)
    assert sp["reference"]["estimate"] == pytest.approx(0.75)
    assert sp["generator"]["ci95"] == pytest.approx([0.1500, 0.8500], abs=1e-3)
    assert sp["difference"]["estimate"] == pytest.approx(0.25)
    assert sp["difference"]["ci95"] == pytest.approx([-0.3196, 0.6553], abs=1e-3)
    assert rep["passes"] is False, "4 generator plants are under the bar's n of 30"


def test_a_report_missing_self_preference_is_refused(tmp_path):
    items = qc.load_set(_set(tmp_path / "set.yaml"))
    no_reference = [r for r in _rows() if r["half"] == "generator"]
    with pytest.raises(qc.CalibrationIncomplete, match="calibration_incomplete.*self_preference"):
        qc.calibrate(items, no_reference, _cfg())
    rep = qc.calibrate(items, _rows(), _cfg())
    del rep["self_preference"]
    with pytest.raises(qc.CalibrationIncomplete, match="calibration_incomplete"):
        qc.require_complete(rep)


def test_removing_the_incomplete_refusal_fails_its_test(tmp_path, monkeypatch):
    """FC-27's positive control: with the refusal disabled, the incomplete report goes through, so the test above
    is what holds it."""
    rep = qc.calibrate(qc.load_set(_set(tmp_path / "set.yaml")), _rows(), _cfg())
    del rep["self_preference"]
    monkeypatch.setattr(qc, "require_complete", lambda r: None)
    qc.require_complete(rep)


def _passing_report(home, judge_model, generator_model):
    rep = {"schema": 1, "judge": {"role": "judge", "model": judge_model},
           "generator": {"role": "extractor", "model": generator_model},
           "position_bias": {"estimate": 0.0, "ci95": [0.0, 0.1], "n": 40},
           "test_retest": {"kappa": 0.9, "kappa_se": 0.05, "kappa_ci95": [0.8, 1.0], "n": 40,
                           "agreement": {"estimate": 0.95, "ci95": [0.83, 0.99], "n": 40}},
           "self_preference": {"generator": {"estimate": 1.0, "ci95": [0.886, 1.0], "n": 30, "k": 30},
                               "reference": {"estimate": 1.0, "ci95": [0.886, 1.0], "n": 30, "k": 30},
                               "difference": {"estimate": 0.0, "ci95": [-0.11, 0.11]}}}
    path = qc.report_path(home, judge_model, generator_model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rep), encoding="utf-8")
    return path


def test_an_uncalibrated_judge_is_refused_by_the_resolver_and_a_lock_bump_voids_a_report(home, tmp_path):
    with pytest.raises(M.JudgeUncalibrated, match="judge_uncalibrated"):
        M.resolve_judge("judge", generator="extractor")
    _passing_report(home, FIXTURE_IDS["fable"], FIXTURE_IDS["sonnet"])
    assert M.resolve_judge("judge", generator="extractor") == FIXTURE_IDS["fable"]
    bumped = write_models_home(tmp_path / "bumped", ids={**FIXTURE_IDS, "fable": "claude-fable-5-2"})
    _passing_report(bumped, FIXTURE_IDS["fable"], FIXTURE_IDS["sonnet"])     # a report for the OLD fable id
    with pytest.raises(M.JudgeUncalibrated, match="judge_uncalibrated"):
        M.resolve_judge("judge", generator="extractor", home=bumped)


def test_a_judge_whose_report_is_incomplete_or_under_the_bar_is_refused(home):
    path = _passing_report(home, FIXTURE_IDS["fable"], FIXTURE_IDS["sonnet"])
    rep = json.loads(path.read_text())
    rep["self_preference"]["generator"] = {"estimate": 0.6, "ci95": [0.42, 0.75], "n": 30, "k": 18}
    path.write_text(json.dumps(rep))
    with pytest.raises(M.JudgeUncalibrated, match="bar"):
        M.resolve_judge("judge", generator="extractor")
    del rep["self_preference"]
    path.write_text(json.dumps(rep))
    with pytest.raises(M.JudgeUncalibrated, match="calibration_incomplete"):
        M.resolve_judge("judge", generator="extractor")


def test_removing_the_resolver_refusal_fails_its_test(home, monkeypatch):
    """FC-27's positive control for the resolver: with its calibration check disabled, an uncalibrated judge
    resolves, so the refusal test above is what holds it."""
    monkeypatch.setattr(M, "_require_calibration", lambda *a, **k: None)
    assert M.resolve_judge("judge", generator="extractor") == FIXTURE_IDS["fable"]


def test_calibrate_judge_command_writes_the_report_and_refuses_an_incomplete_one(home, tmp_path):
    from seldon.cli import main
    s = _set(tmp_path / "set.yaml")
    v = tmp_path / "verdicts.jsonl"
    v.write_text("".join(json.dumps(r) + "\n" for r in _rows()))
    out = tmp_path / "report.json"
    r = CliRunner().invoke(main, ["qc", "calibrate-judge", "--set", str(s), "--verdicts", str(v), "--judge", "judge",
                                  "--generator", "extractor", "--out", str(out)])
    assert r.exit_code == 0, r.output
    rep = json.loads(out.read_text())
    assert rep["judge"]["model"] == FIXTURE_IDS["fable"] and rep["generator"]["model"] == FIXTURE_IDS["sonnet"]
    assert {"position_bias", "test_retest", "self_preference"} <= set(rep)
    v.write_text("".join(json.dumps(r) + "\n" for r in _rows() if r["half"] == "generator"))
    out2 = tmp_path / "report2.json"
    r = CliRunner().invoke(main, ["qc", "calibrate-judge", "--set", str(s), "--verdicts", str(v), "--judge", "judge",
                                  "--generator", "extractor", "--out", str(out2)])
    assert r.exit_code == 2 and "calibration_incomplete" in r.output and not out2.exists()


def test_the_seeded_calibration_set_is_well_formed():
    """The seed (QC-001 Part C.3): this week's real defects, each with its receipt; reference halves from
    library-held documents published before 2022, planted by a minimal edit; generator halves are slots."""
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "models" / "calibration" / "set.yaml"
    items = qc.load_set(path)
    classes = {}
    for it in items.values():
        classes[it["defect_class"]] = classes.get(it["defect_class"], 0) + 1
        ref = it["reference"]
        assert str(ref["source"]["publication_date"]) < "2022", it["id"]
        assert ref["plant"]["from"] in ref["original"] and ref["plant"]["to"] in ref["planted"], it["id"]
        assert ref["planted"] == ref["original"].replace(ref["plant"]["from"], ref["plant"]["to"], 1), it["id"]
        assert it["generator"]["status"] == "slot" and it["generator"]["instructions"], it["id"]
        assert it["receipt"], it["id"]
    assert classes == {"premise_found_wrong": 6, "implicit_default": 1, "unparsed_label": 1, "label_collision": 1,
                       "unbounded_resource": 1}
