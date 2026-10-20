"""RECALL-001 Part A: registration retrieves the repositories' own history and hands it to the launched session.

Before RECALL-001, `seldon cc register` returned the rulings a task is constrained by (AD-031-R1) and nothing else
from the record: a RESULT that had already tried the approach, an Issue that had already named the failure, a branch
the dispatcher kept because it failed, all sat unread at the moment of decision. Each test fails on HEAD 9e6f42c
(main before RECALL-001), where `seldon.core.recall` does not exist and registration prints no `Recall:` block.
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
from tests.testdb import TEST_DATABASE

RECALL_BLOCK = {
    "top_n": 8, "min_shared_terms": 2, "max_file_bytes": 2000000, "headline_chars": 120,
    "result_globs": ["cc_tasks/*_RESULT*.md"],
    "failure_terms": ["fail", "unpassed", "blocked", "breaker", "conflict"],
    "bm25": {"k1": 1.2, "b": 0.75},
    "served": {"enabled": False, "k": 20, "rrf_k": 60, "graphs": {}},
}

OLD_RESULT = """# RESULT: frobnicator calibration drift, fixed by pinning the oscillator

The frobnicator calibration drifted because the oscillator was not pinned. Pinned it; drift gone.
"""

TASK = """# CC Task: frobnicator calibration drift returns under load

**Implements:** DN-006
**Parts:** A 1.0

## Part A: measure the oscillator drift

Acceptance:
- `check: true`
"""

UNRELATED_TASK = """# CC Task: quaternion zebra lattice

**Implements:** DN-006
**Parts:** A 1.0

## Part A: lattice

Acceptance:
- `check: true`
"""


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _config(name: str = "test") -> dict:
    return {"project": {"name": name, "domain": "research"},
            "neo4j": {"database": TEST_DATABASE, "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687")},
            "event_store": {"path": "seldon_events.jsonl"}, "recall": RECALL_BLOCK}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(tmp_path, *args)
    (tmp_path / "seldon.yaml").write_text(yaml.safe_dump(_config()), encoding="utf-8")
    (tmp_path / "cc_tasks").mkdir()
    (tmp_path / "cc_tasks" / "2026-01-05_frobnicator_pin_RESULT.md").write_text(OLD_RESULT, encoding="utf-8")
    (tmp_path / "cc_tasks" / "2026-02-01_frobnicator_returns.md").write_text(TASK, encoding="utf-8")
    (tmp_path / "cc_tasks" / "2026-02-02_zebra.md").write_text(UNRELATED_TASK, encoding="utf-8")
    (tmp_path / "seldon_events.jsonl").write_text("", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _append(repo: Path, event: dict) -> None:
    with (repo / "seldon_events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def _recall(repo: Path, task: str) -> R.Recall:
    path = repo / "cc_tasks" / task
    return R.recall(repo, _config(), path.read_text(encoding="utf-8"), task_stem=path.stem)


def test_a_task_whose_title_matches_a_past_result_lists_it(repo):
    r = _recall(repo, "2026-02-01_frobnicator_returns.md")
    ids = [h.id for h in r.hits]
    assert "test:2026-01-05_frobnicator_pin_RESULT" in ids, R.render(r)
    hit = r.hits[ids.index("test:2026-01-05_frobnicator_pin_RESULT")]
    assert (hit.kind, hit.date) == ("result", "2026-01-05")
    assert "frobnicator calibration drift" in hit.headline
    text = R.render(r)
    assert text.startswith("Recall: ")
    assert "  - result  test:2026-01-05_frobnicator_pin_RESULT  2026-01-05  RESULT: frobnicator" in text, text


def test_the_tasks_own_files_are_not_its_history(repo):
    (repo / "cc_tasks" / "2026-02-01_frobnicator_returns_RESULT.md").write_text(
        "# RESULT: frobnicator calibration drift returns under load\n", encoding="utf-8")
    r = _recall(repo, "2026-02-01_frobnicator_returns.md")
    assert all("frobnicator_returns" not in h.id for h in r.hits), R.render(r)


def test_a_dead_end_branch_is_marked(repo):
    tid = "7d1f0000-0000-4000-8000-000000000001"
    _append(repo, make_event("artifact_created", "cc", "accepted", {
        "artifact_id": tid, "artifact_type": "ResearchTask", "to_state": "proposed",
        "properties": {"name": "frobnicator oscillator rewrite", "source_file": "cc_tasks/2026-01-20_osc_rewrite.md",
                       "description": "Rewrite the frobnicator oscillator to cure calibration drift."}}))
    _append(repo, make_event("worktree_kept", "dispatcher", "accepted", {
        "task_id": tid, "outcome": "session_failed",
        "reason": "session_failed: the oscillator rewrite broke calibration under load"}))
    # A kept branch whose reason names no failure is listed but not marked.
    tid2 = "7d1f0000-0000-4000-8000-000000000002"
    _append(repo, make_event("artifact_created", "cc", "accepted", {
        "artifact_id": tid2, "artifact_type": "ResearchTask", "to_state": "proposed",
        "properties": {"name": "frobnicator calibration notes", "source_file": "cc_tasks/2026-01-21_notes.md"}}))
    _append(repo, make_event("worktree_kept", "dispatcher", "accepted", {
        "task_id": tid2, "outcome": "released", "reason": "operator parked the frobnicator calibration notes"}))
    r = _recall(repo, "2026-02-01_frobnicator_returns.md")
    by_id = {h.id: h for h in r.hits}
    dead = by_id["test:2026-01-20_osc_rewrite"]
    assert (dead.kind, dead.dead_end) == ("worktree_kept", True)
    assert "worktree_kept DEAD END" in dead.line(), dead.line()
    assert "session_failed" in dead.line()
    assert by_id["test:2026-01-21_notes"].dead_end is False
    assert "DEAD END" not in by_id["test:2026-01-21_notes"].line()


def test_issues_open_and_resolved_are_listed(repo):
    for n, state in ((1, "open"), (2, "resolved")):
        _append(repo, make_event("artifact_created", "cc", "accepted", {
            "artifact_id": f"1550e00{n}-0000-4000-8000-000000000000", "artifact_type": "Issue", "to_state": "open",
            "properties": {"name": f"frobnicator calibration drift under load {n}", "description": "drift"}}))
        if state != "open":
            _append(repo, make_event("artifact_state_changed", "cc", "accepted", {
                "artifact_id": f"1550e00{n}-0000-4000-8000-000000000000", "artifact_type": "Issue",
                "from_state": "open", "to_state": state}))
    r = _recall(repo, "2026-02-01_frobnicator_returns.md")
    issues = {h.id: h.status for h in r.hits if h.kind == "issue"}
    assert issues == {"test:issue-1550e001": "open", "test:issue-1550e002": "resolved"}, R.render(r)
    assert "  - issue [resolved]  test:issue-1550e002  " in R.render(r)


def test_a_task_with_no_history_prints_recall_none(repo):
    r = _recall(repo, "2026-02-02_zebra.md")
    assert r.hits == []
    assert R.render(r).startswith("Recall: none"), R.render(r)


def test_the_launch_prompt_carries_the_list(repo):
    from seldon.commands.dispatch import DISPATCH_LINE
    from seldon.commands.dispatch_worktree import worktree_prompt

    tid = "aaaa0000-0000-4000-8000-000000000003"
    rel = "cc_tasks/2026-02-01_frobnicator_returns.md"
    r = _recall(repo, "2026-02-01_frobnicator_returns.md")
    R.record_listed(repo, r, task_id=tid, source_file=rel, actor="cc", session_id=None)
    prompt = worktree_prompt(rel, repo, tid)
    head, _, tail = prompt.partition(DISPATCH_LINE.format(rel=rel, stem=Path(rel).stem))
    assert tail, "the protocol's dispatch line is carried verbatim"
    assert head.startswith(R.PROMPT_HEAD), head
    assert "test:2026-01-05_frobnicator_pin_RESULT" in head, head
    assert "Recall used:" in head
    # Read before CLAUDE.md: the list is ahead of the dispatch line's "Read CLAUDE.md".
    assert prompt.index("frobnicator_pin_RESULT") < prompt.index("Read CLAUDE.md")
    # A task registered with no history still hears it, and must answer `none`.
    zid = "aaaa0000-0000-4000-8000-000000000004"
    R.record_listed(repo, _recall(repo, "2026-02-02_zebra.md"), task_id=zid, source_file="cc_tasks/2026-02-02_zebra.md",
                    actor="cc", session_id=None)
    assert "  Recall: none" in worktree_prompt("cc_tasks/2026-02-02_zebra.md", repo, zid)
    # A task registered before RECALL-001 has no record, and its prompt is the protocol's line unchanged.
    assert worktree_prompt(rel, repo, "bbbb0000-0000-4000-8000-000000000005").startswith("Read CLAUDE.md")


def test_a_served_graph_that_cannot_serve_is_named_not_fatal(repo, monkeypatch):
    """Squiddy exits with `SystemExit("FATAL: no served export ...")` on a graph never admitted (a worktree has no
    gitignored export). Found running RECALL-001 on itself: that exit would have aborted the registration."""
    import squiddy.config
    import squiddy.serve

    graph = repo / "governed"
    graph.mkdir()
    (graph / "config.yaml").write_text("{}\n", encoding="utf-8")

    def fatal(_graph):
        raise SystemExit(f"FATAL: no served export at {graph}/exports/governed_graph.json; run an admission first")

    monkeypatch.setattr(squiddy.config, "load_graph", lambda p: p)
    monkeypatch.setattr(squiddy.serve, "Verbs", fatal)
    cfg = _config()
    cfg["recall"] = {**RECALL_BLOCK, "served": {"enabled": True, "k": 20, "rrf_k": 60, "graphs": {"test": "governed"}}}
    path = repo / "cc_tasks" / "2026-02-01_frobnicator_returns.md"
    r = R.recall(repo, cfg, path.read_text(encoding="utf-8"), task_stem=path.stem)
    assert "test:2026-01-05_frobnicator_pin_RESULT" in [h.id for h in r.hits]       # the lexical arm still ran
    assert any("served arm failed for test" in n and "no served export" in n for n in r.notes), r.notes
    assert "(note: served arm failed for test" in R.render(r)


def test_a_malformed_recall_block_is_refused():
    with pytest.raises(R.RecallError, match="missing"):
        R.settings({"recall": {"top_n": 3}})
    assert R.settings({}) is None


def test_siblings_are_searched_from_a_worktree_path(repo):
    """`decisions.repositories` paths resolve against the PRIMARY checkout, so a worktree session reaches them."""
    sib = repo / "sibling"
    (sib / "cc_tasks").mkdir(parents=True)
    (sib / "cc_tasks" / "2025-12-01_osc_RESULT.md").write_text(
        "# RESULT: oscillator frobnicator calibration\n", encoding="utf-8")
    cfg = _config()
    cfg["decisions"] = {"repository": "test", "repositories": {"sib": "sibling"}}
    _git(repo, "worktree", "add", "-q", "-b", "w", str(repo / ".wt" / "w"))
    tree = repo / ".wt" / "w"
    repos = R.repositories(tree, cfg)
    assert repos == {"test": tree.resolve(), "sib": sib.resolve()}
    path = tree / "cc_tasks" / "2026-02-01_frobnicator_returns.md"
    r = R.recall(tree, cfg, path.read_text(encoding="utf-8"), task_stem=path.stem)
    assert "sib:2025-12-01_osc_RESULT" in [h.id for h in r.hits], R.render(r)


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_registration_prints_recall_and_records_it(repo):
    from seldon.commands.cc import cc_group

    prev = Path.cwd()
    os.chdir(repo)
    try:
        out = CliRunner().invoke(cc_group, ["register", "cc_tasks/2026-02-01_frobnicator_returns.md"],
                                 catch_exceptions=False)
    finally:
        os.chdir(prev)
    assert out.exit_code == 0, out.output
    assert "Recall: " in out.output, out.output
    assert "test:2026-01-05_frobnicator_pin_RESULT" in out.output, out.output
    rows = [e for e in read_events(repo) if e["event_type"] == R.EVENT_LISTED]
    assert len(rows) == 1
    assert rows[0]["payload"]["source_file"] == "cc_tasks/2026-02-01_frobnicator_returns.md"
    assert rows[0]["payload"]["hits"][0]["id"] == "test:2026-01-05_frobnicator_pin_RESULT"
