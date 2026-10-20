"""RECALL-001 Part B: the measurement. Did a listed hit change the task?

Every RESULT of a task registered with a Recall list carries `Recall used: <ids>` or `Recall used: none`.
`seldon cc complete` refuses a RESULT without it; the dispatcher, which completes worktree tasks, records the line it
finds (or its absence) at the merge; `seldon qc chart` counts per week the tasks registered, those with a hit, and
those whose RESULT names a used hit. That rate decides whether the cross-agent knowledge exchange is built (squiddy
DN-040 area). Each test fails on HEAD 9e6f42c, where none of this exists.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.core import recall as R
from seldon.core.events import make_event, read_events
from tests.test_recall001_registration import OLD_RESULT, TASK, _config

TID = "c0ffee00-0000-4000-8000-000000000001"
HIT = "test:2026-01-05_frobnicator_pin_RESULT"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(tmp_path, *args)
    cfg = _config()
    cfg["qc"] = {"chart_min_points": 10}
    (tmp_path / "seldon.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    (tmp_path / "cc_tasks").mkdir()
    (tmp_path / "cc_tasks" / "2026-01-05_frobnicator_pin_RESULT.md").write_text(OLD_RESULT, encoding="utf-8")
    (tmp_path / "cc_tasks" / "2026-02-01_frobnicator_returns.md").write_text(TASK, encoding="utf-8")
    (tmp_path / "seldon_events.jsonl").write_text("", encoding="utf-8")
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


def _listed(repo: Path, tid: str = TID, hits=(HIT,), ts: str | None = None) -> None:
    ev = make_event(R.EVENT_LISTED, "cc", "accepted", {
        "task_id": tid, "source_file": "cc_tasks/x.md", "query": "q",
        "hits": [{"kind": "result", "id": h, "date": "2026-01-05", "headline": "h", "repo": "test", "path": None,
                  "status": None, "dead_end": False, "score": 0.1, "shared_terms": [], "arms": ["lexical"]}
                 for h in hits], "notes": [], "repositories": {}})
    if ts:
        ev["timestamp"] = ts
    with (repo / "seldon_events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev) + "\n")


# ======================================================================================== the RESULT's line

def test_the_line_names_listed_hits_or_none():
    assert R.used_value("# RESULT\n\nRecall used: none (nothing applied)\n") == "none (nothing applied)"
    assert R.used_value("**Recall used:** seldon:AD-031-R3, squiddy:R-110\n") == "seldon:AD-031-R3, squiddy:R-110"
    assert R.used_value("- Recall used: none\n") == "none"
    assert R.used_value("no such line\n") is None
    allowed = {"seldon:AD-031-R3", "squiddy:R-110", "squiddy:R-11"}
    assert R.parse_used("none", allowed) == []
    assert R.parse_used("squiddy:R-110 changed the ranking; seldon:AD-031-R3 too", allowed) == \
        ["seldon:AD-031-R3", "squiddy:R-110"]
    with pytest.raises(R.RecallError, match="names no hit registration listed"):
        R.parse_used("squiddy:R-999", allowed)
    with pytest.raises(R.RecallError, match="empty"):
        R.parse_used("", allowed)


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_cc_complete_refuses_a_result_without_the_line(repo):
    from seldon.commands.cc import cc_group

    out = _cli(repo, cc_group, ["register", "cc_tasks/2026-02-01_frobnicator_returns.md"])
    assert out.exit_code == 0, out.output
    assert HIT in out.output
    result = repo / "cc_tasks" / "2026-02-01_frobnicator_returns_RESULT.md"
    result.write_text("# RESULT: drift returns\n\nDone. Tokens 0.1M.\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "result")
    out = _cli(repo, cc_group, ["complete", "cc_tasks/2026-02-01_frobnicator_returns.md"])
    assert out.exit_code == 1, out.output
    assert "no `Recall used:` line" in out.output, out.output
    assert not [e for e in read_events(repo) if e["event_type"] == R.EVENT_USED]

    result.write_text(f"# RESULT: drift returns\n\nDone.\n\nRecall used: {HIT} (pinned first)\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "result line")
    out = _cli(repo, cc_group, ["complete", "cc_tasks/2026-02-01_frobnicator_returns.md"])
    assert out.exit_code == 0, out.output
    assert f"recall used: {HIT}" in out.output, out.output
    used = [e["payload"] for e in read_events(repo) if e["event_type"] == R.EVENT_USED]
    assert len(used) == 1 and used[0]["used"] == [HIT]
    assert used[0]["result_path"] == "cc_tasks/2026-02-01_frobnicator_returns_RESULT.md"


def test_a_task_registered_before_recall_owes_no_line(repo):
    task = repo / "cc_tasks" / "2026-02-01_frobnicator_returns.md"
    assert R.used_for_completion(repo, task, "dddd0000-0000-4000-8000-000000000009") is None


def test_the_merge_records_the_line_or_its_absence(repo):
    _listed(repo)
    rel = "cc_tasks/2026-02-01_frobnicator_returns_RESULT.md"
    row = R.used_at_merge(repo, TID, rel)
    assert row == {"task_id": TID, "result_path": rel, "used": None, "missing": True}
    (repo / rel).write_text("Recall used: none\n", encoding="utf-8")
    assert R.used_at_merge(repo, TID, rel)["used"] == []
    (repo / rel).write_text("Recall used: somebody:else\n", encoding="utf-8")
    assert "names no hit" in R.used_at_merge(repo, TID, rel)["refused"]
    assert R.used_at_merge(repo, "eeee0000-0000-4000-8000-000000000000", rel) is None


# ================================================================================================ the chart

def test_the_chart_counts(repo):
    a, b, c = (f"{n}aaa0000-0000-4000-8000-000000000000" for n in (1, 2, 3))
    _listed(repo, a, ts="2026-10-19T10:00:00Z")                     # ISO week 2026-W43
    _listed(repo, b, hits=(), ts="2026-10-20T10:00:00Z")            # W43, no hit
    _listed(repo, c, ts="2026-10-27T10:00:00Z")                     # W44
    _listed(repo, a, ts="2026-10-28T10:00:00Z")                     # a re-listing counts once, at its first week
    events = read_events(repo)
    events.append(make_event(R.EVENT_USED, "cc", "accepted", {"task_id": a, "used": [HIT], "missing": False}))
    events.append(make_event(R.EVENT_USED, "dispatcher", "accepted", {"task_id": b, "used": [], "missing": False}))
    events.append(make_event(R.EVENT_USED, "dispatcher", "accepted", {"task_id": c, "used": None, "missing": True}))
    out = R.chart(events, [])
    assert out["weeks"] == [
        {"week": "2026-W43", "registered": 2, "with_hits": 1, "results_read": 2, "used": 1},
        {"week": "2026-W44", "registered": 1, "with_hits": 1, "results_read": 1, "used": 0},
    ]


def test_qc_chart_prints_the_recall_series(repo):
    from seldon.commands.qc import qc_group

    _listed(repo, ts="2026-10-19T10:00:00Z")
    out = _cli(repo, qc_group, ["chart"])
    assert out.exit_code == 0, out.output
    assert "recall per week (RECALL-001 Part B" in out.output, out.output
    assert "2026-W43" in out.output
    js = json.loads(_cli(repo, qc_group, ["chart", "--json"]).output)
    assert js["recall"]["weeks"] == [{"week": "2026-W43", "registered": 1, "with_hits": 1, "results_read": 0,
                                      "used": 0}]
