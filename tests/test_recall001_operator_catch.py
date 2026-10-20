"""RECALL-001 Part C: operator judgment is recorded.

Touchpoint 3 is the case where the operator saw something the system did not (2026-10-17: a fixed slice count across
varying segment lengths blowing up a solver). Until now that left no record, so the boundary of L4 could not be
measured. `seldon decision operator-catch` writes a Decision record with `decided_by: operator`, `kind: catch`, bound
to the task, and `seldon qc chart` counts catches per week by class. Each test fails on HEAD 9e6f42c, where the kind,
the verb and the series do not exist.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.core import decisions as dr
from seldon.core import recall as R
from seldon.core.events import make_event, read_events
from tests.test_recall001_registration import RECALL_BLOCK

TID = "5ca7c400-0000-4000-8000-000000000001"
REL = "cc_tasks/2026-10-17_solver_slices.md"
TASK = "# CC Task: segment the solver's input into slices\n\n**Implements:** DN-006\n"
SEEN = "A fixed slice count across varying segment lengths blows up the solver."


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _config() -> dict:
    return {"project": {"name": "test", "domain": "research"}, "event_store": {"path": "seldon_events.jsonl"},
            "decisions": {"repository": "test"}, "qc": {"chart_min_points": 10}, "recall": RECALL_BLOCK}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(tmp_path, *args)
    (tmp_path / "seldon.yaml").write_text(yaml.safe_dump(_config()), encoding="utf-8")
    (tmp_path / "cc_tasks").mkdir()
    (tmp_path / REL).write_text(TASK, encoding="utf-8")
    ev = make_event("artifact_created", "cc", "accepted", {
        "artifact_id": TID, "artifact_type": "ResearchTask", "to_state": "proposed",
        "properties": {"name": "solver slices", "source_file": REL}})
    (tmp_path / "seldon_events.jsonl").write_text(json.dumps(ev) + "\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _cli(repo: Path, group, args: list):
    prev = Path.cwd()
    os.chdir(repo)
    try:
        return CliRunner().invoke(group, args, catch_exceptions=False)
    finally:
        os.chdir(prev)


def _catch(repo: Path, task: str = "2026-10-17_solver_slices", cls: str = "numerical_instability",
           date: str = "2026-10-17"):
    from seldon.commands.decision import decision_group

    return _cli(repo, decision_group, ["operator-catch", task, "--class", cls, "--text", SEEN, "--date", date])


def test_the_record_validates(repo):
    out = _catch(repo)
    assert out.exit_code == 0, out.output
    assert "docs/decisions/register/00001_test-catch-001_accept.yaml" in out.output, out.output
    reg = dr.Register("test", repo, dr.DEFAULT_REGISTER_DIR)
    assert reg.verify() == []
    rec = dr.fold(reg.events())["test:CATCH-001"]
    assert (rec.status, rec.get("kind"), rec.get("decided_by")) == ("accepted", "catch", "operator")
    assert (rec.get("catch_class"), rec.get("task"), rec.get("statement")) == ("numerical_instability", TID, SEEN)
    assert rec.get("source")["path"] == REL and rec.get("source")["text"] == TASK.splitlines()[0]
    assert rec.get("operator_stated") is False                     # no receipt given
    assert dr.check(repo, _config()) == []
    # A second catch takes the next number; the task may be named by its id prefix too.
    assert _catch(repo, task=TID[:8], cls="wrong_premise").exit_code == 0
    assert "test:CATCH-002" in dr.fold(reg.events())


def test_the_shape_is_enforced():
    base = {"event": "accept", "id": "test:CATCH-009", "date": "2026-10-17", "decided_by": "operator",
            "operator_stated": False, "kind": "catch", "status": "accepted", "statement": SEEN,
            "source": {"path": REL, "lines": [1, 1], "sha256": "x", "text": "t"}, "scope": ["test"],
            "rationale": {"path": REL}, "review_only": "rationale", "seq": 1, "written_by": "w",
            "prev_hash": "0" * 64, "record_hash": "x"}
    assert dr.validate_shape(dict(base, catch_class="c", task=TID)) == []
    assert "a catch requires catch_class (RECALL-001 Part C)" in dr.validate_shape(dict(base, task=TID))
    assert "a catch requires task (RECALL-001 Part C)" in dr.validate_shape(dict(base, catch_class="c"))
    wrong = dict(base, kind="decision", catch_class="c", task=TID)
    assert "catch_class and task belong to a catch only (RECALL-001 Part C)" in dr.validate_shape(wrong)


def test_bad_input_is_refused(repo):
    out = _catch(repo, cls="Numerical Instability")
    assert out.exit_code == 1 and "one lowercase identifier" in out.output, out.output
    out = _catch(repo, task="no-such-task")
    assert out.exit_code == 1 and "names no registered ResearchTask" in out.output, out.output
    assert not (repo / "docs" / "decisions" / "register").exists()


def test_a_catch_binds_nothing_and_is_recalled(repo):
    assert _catch(repo).exit_code == 0
    u = dr.universe(repo, _config())
    assert dr.bind(u, f"# solver slices\n{SEEN}\nCATCH-001 test:CATCH-001", 0.0) == []
    task = "# CC Task: solver slice count for varying segment lengths\n"
    r = R.recall(repo, _config(), task, task_stem="new")
    hit = next(h for h in r.hits if h.id == "test:CATCH-001")
    assert hit.kind == "catch" and hit.headline.startswith("numerical_instability: A fixed slice count")


def test_the_chart_counts_it(repo):
    from seldon.commands.qc import qc_group

    assert _catch(repo, date="2026-10-17").exit_code == 0               # 2026-W42
    assert _catch(repo, cls="wrong_premise", date="2026-10-19").exit_code == 0   # 2026-W43
    assert _catch(repo, date="2026-10-20").exit_code == 0               # 2026-W43
    out = R.chart(read_events(repo), R.catches(repo, _config()))
    assert out["catches"] == [
        {"week": "2026-W42", "total": 1, "by_class": {"numerical_instability": 1}},
        {"week": "2026-W43", "total": 2, "by_class": {"numerical_instability": 1, "wrong_premise": 1}},
    ]
    text = _cli(repo, qc_group, ["chart"]).output
    assert "operator catches per week (RECALL-001 Part C" in text, text
    assert "2026-W43    2  numerical_instability 1, wrong_premise 1" in text, text


def test_the_mcp_verb_writes_the_same_record(repo):
    from seldon.mcp_server import seldon_decision_operator_catch as tool

    fn = getattr(tool, "__wrapped__", tool)
    text = fn(task=REL, catch_class="numerical_instability", text=SEEN, project_dir=str(repo), date="2026-10-17",
              receipts="handoffs/2026-10-17_x.md: he said the slices blow up")
    assert "wrote docs/decisions/register/00001_test-catch-001_accept.yaml" in text, text
    rec = dr.fold(dr.Register("test", repo, dr.DEFAULT_REGISTER_DIR).events())["test:CATCH-001"]
    assert rec.get("operator_stated") is True and rec.get("receipts")
