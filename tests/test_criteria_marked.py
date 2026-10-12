"""QC-001 Part E (AD-037-R1): `seldon cc register` refuses a task whose acceptance criteria are not each marked
`check: <command>` or `judgment: <why no program decides it>`, as `criterion_unmarked`. Zero model calls."""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.core import criteria

SELDON = Path(__file__).resolve().parents[1]
QC001 = SELDON / "cc_tasks" / "2026-10-11_QC-001_ad037_receipts_records_judge_calibration_mechanism_filing.md"

PLANTED = """# T: a task

## Part A

1. Do the thing.
2. Acceptance:
   - `check: pytest tests/test_thing.py` passes.
   - the output reads well.

- Acceptance: `judgment:` no program reads tone; a reader does.

## Acceptance
- `check:` the build is green.
- the numbers look right.
- `judgment:`
"""


def test_every_form_of_criterion_is_found():
    found = [c for _n, c in criteria.acceptance_criteria(PLANTED)]
    assert found == ["`check: pytest tests/test_thing.py` passes.", "the output reads well.",
                     "`judgment:` no program reads tone; a reader does.", "`check:` the build is green.",
                     "the numbers look right.", "`judgment:`"]


def test_a_planted_unmarked_criterion_is_refused(tmp_path):
    task = tmp_path / "cc_tasks" / "2026-10-12_T_planted.md"
    task.parent.mkdir()
    task.write_text(PLANTED, encoding="utf-8")
    refusal = criteria.registration_refusal(task, tmp_path, {})
    assert refusal and refusal.startswith("criterion_unmarked: 3 acceptance criterion(s)")
    assert "the output reads well" in refusal and "the numbers look right" in refusal
    assert "line 15" in refusal, "a `judgment:` with no reason after it is not marked"


def test_this_tasks_file_passes():
    """QC-001's own criteria are marked: the positive case."""
    assert len(criteria.acceptance_criteria(QC001.read_text(encoding="utf-8"))) == 11
    assert criteria.registration_refusal(QC001, SELDON, {}) is None


def test_a_baseline_task_is_not_rechecked(tmp_path):
    task = tmp_path / "cc_tasks" / "old.md"
    task.parent.mkdir()
    task.write_text(PLANTED, encoding="utf-8")
    (tmp_path / "baseline.txt").write_text("# header\ncc_tasks/old.md\n", encoding="utf-8")
    cfg = {"qc": {"criteria_baseline": "baseline.txt"}}
    assert criteria.registration_refusal(task, tmp_path, cfg) is None
    with pytest.raises(FileNotFoundError):
        criteria.registration_refusal(task, tmp_path, {"qc": {"criteria_baseline": "missing.txt"}})


def test_registration_refuses_before_anything_is_written(tmp_path, monkeypatch):
    """The gate sits in `register_task_file` before the graph is touched: a driver of None is never used."""
    from seldon.commands import cc
    from seldon.core import prior_art
    task = tmp_path / "cc_tasks" / "2026-10-12_T_planted.md"
    task.parent.mkdir()
    task.write_text(PLANTED + "\nGoverning: AD-037.\n", encoding="utf-8")
    monkeypatch.setattr(cc, "enforce_design_reference", lambda *a, **k: None)
    monkeypatch.setattr(cc.models, "ensure_fresh", lambda *a, **k: None)
    monkeypatch.setattr(cc, "enforce_task_models", lambda *a, **k: None)
    monkeypatch.setattr(prior_art, "registration_refusal", lambda *a, **k: None)
    with pytest.raises(ValueError, match="criterion_unmarked"):
        cc.register_task_file(project_dir=tmp_path, config={}, driver=None, database="none", domain_config=None,
                              task_path=task, allow_untracked=True, session_id=None)
