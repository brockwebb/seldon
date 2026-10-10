"""c7 names what failed, and a stuck streak is counted only where it is kept.

`ai-readiness-kg/cc_tasks/2026-10-09_main_green_dispatch_stuck_without_a_path.md`. The
incident: ai-readiness-kg's daily suite runs in a DETACHED worktree, so c7 failed on its branch
half with a clean tree. The pass reported `dirty_tree`, printed `dirty: (branch)`, and the
suite's own three passes (four seconds apart, against a 300 s poll) shared one streak file and
wrote `dispatch_stuck{criterion: dirty_tree, dirty_paths: []}` on 2026-10-08 and 2026-10-09.

Pure: no graph, no CLI. The pass-level behaviour on a real detached checkout is in
`tests/test_dispatch_stuck_and_journal.py`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from seldon.commands import dispatch as CMD
from seldon.core import dispatch as D

CFG = {"branch": "main", "lease_file": ".seldon/dispatch.lock", "stuck_after_passes": 3,
       "poll_interval_s": 300}


def _git(p: Path, *a):
    return subprocess.run(["git", *a], cwd=p, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    p = tmp_path / "repo"
    p.mkdir()
    _git(p, "init", "-q", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    (p / "a.txt").write_text("a\n")
    _git(p, "add", "a.txt")
    _git(p, "commit", "-q", "-m", "a")
    return p


def _row(task_id: str, tree: dict) -> dict:
    c7 = {"branch": tree["branch"], "configured_branch": "main", "dirty": tree["dirty"],
          "dirty_count": tree["dirty_count"], "dirty_paths": tree["dirty_paths"],
          "ok": tree["branch"] == "main" and not tree["dirty"] and not tree.get("read_error")}
    if tree.get("read_error"):
        c7["read_error"] = tree["read_error"]
    return {"task_id": task_id, "candidate": True, "criteria": {"c7": c7},
            "failed": [] if c7["ok"] else ["c7"], "name": task_id, "source_file": "t.md"}


def test_a_failed_git_read_is_tree_unreadable_never_a_clean_or_dirty_tree(tmp_path, monkeypatch):
    nowhere = tmp_path / "not_a_repo"
    nowhere.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    tree = D.tree_state(nowhere)
    assert tree["read_error"] and "exited" in tree["read_error"]
    assert tree["dirty"] is False and tree["dirty_paths"] == []
    assert D.first_refusal_reason(_row("t", tree)) == "tree_unreadable"


def test_a_detached_clean_checkout_is_wrong_branch_not_dirty_tree(repo):
    _git(repo, "checkout", "-q", "--detach")
    tree = D.tree_state(repo)
    assert tree["branch"] == "HEAD" and tree["dirty_paths"] == [] and "read_error" not in tree
    assert D.first_refusal_reason(_row("t", tree)) == "wrong_branch"


def test_dirty_tree_always_names_a_path(repo):
    (repo / "stray.md").write_text("x\n")
    for detach in (False, True):
        if detach:
            _git(repo, "checkout", "-q", "--detach")
        tree = D.tree_state(repo)
        assert D.first_refusal_reason(_row("t", tree)) == "dirty_tree"
        assert tree["dirty_paths"] == ["stray.md"]


def test_the_new_reasons_are_in_the_closed_set():
    assert {"wrong_branch", "tree_unreadable", "dirty_tree"} <= set(D.REFUSAL_REASONS)


def test_the_streak_file_honours_the_override(tmp_path, monkeypatch):
    monkeypatch.delenv(D.STUCK_STATE_ENV, raising=False)
    assert D.stuck_state_path(tmp_path, CFG) == tmp_path / ".seldon" / D.STUCK_STATE_FILE
    monkeypatch.setenv(D.STUCK_STATE_ENV, str(tmp_path / "elsewhere.json"))
    D.write_stuck_state(tmp_path, CFG, {"t": {"criterion": "wrong_branch", "passes": 1}})
    assert (tmp_path / "elsewhere.json").is_file()
    assert not (tmp_path / ".seldon").exists()
    assert D.read_stuck_state(tmp_path, CFG)["t"]["passes"] == 1


@pytest.fixture
def no_side_effects(monkeypatch):
    """`_stuck` emits and notifies on an alarm; record instead of doing either."""
    emitted = []
    monkeypatch.setattr(CMD, "_emit", lambda *a, **k: emitted.append(a))
    monkeypatch.setattr(CMD, "_run_notifier", lambda *a, **k: emitted.append(("notify", a)))
    return emitted


def test_an_unreadable_tree_advances_no_streak(tmp_path, monkeypatch, no_side_effects):
    monkeypatch.delenv(D.STUCK_STATE_ENV, raising=False)
    tree = {"branch": "", "dirty": False, "dirty_paths": [], "dirty_count": 0,
            "read_error": "git status exited 128: fatal"}
    prior = {"t": {"criterion": "wrong_branch", "passes": 2, "notified": False,
                   "first_seen": "then"}}
    D.write_stuck_state(tmp_path, CFG, prior)
    for _ in range(5):
        assert CMD._stuck(tmp_path, "s", CFG, [_row("t", tree)], tree, None, False) == []
    assert D.read_stuck_state(tmp_path, CFG) == prior
    assert no_side_effects == []


def test_two_isolated_streak_files_do_not_see_each_others_passes(
        tmp_path, repo, monkeypatch, no_side_effects):
    _git(repo, "checkout", "-q", "--detach")
    tree = D.tree_state(repo)
    rows = [_row("t", tree)]
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    for which in (a, b, a, b):
        monkeypatch.setenv(D.STUCK_STATE_ENV, str(which))
        assert CMD._stuck(repo, "s", CFG, rows, tree, None, False) == []
    for which in (a, b):
        monkeypatch.setenv(D.STUCK_STATE_ENV, str(which))
        assert D.read_stuck_state(repo, CFG)["t"]["passes"] == 2
    assert not (repo / ".seldon").exists()
    assert no_side_effects == []


def test_status_says_which_candidate_the_next_pass_would_alarm_on(tmp_path, repo, monkeypatch):
    _git(repo, "checkout", "-q", "--detach")
    tree = D.tree_state(repo)
    monkeypatch.setenv(D.STUCK_STATE_ENV, str(tmp_path / "s.json"))
    rows = [_row("t", tree)]
    assert CMD._stuck_due(repo, CFG, rows, tree, None) == []
    D.write_stuck_state(repo, CFG, {"t": {"criterion": "wrong_branch", "passes": 2,
                                          "notified": False, "first_seen": "then"}})
    assert CMD._stuck_due(repo, CFG, rows, tree, None) == ["t"]
    # Looking writes nothing.
    assert D.read_stuck_state(repo, CFG)["t"]["passes"] == 2
    # A claim in flight or an unreadable tree: the pass would count nothing, so nothing is due.
    assert CMD._stuck_due(repo, CFG, rows, tree, {"artifact_id": "x"}) == []
    assert CMD._stuck_due(repo, CFG, rows, {**tree, "read_error": "e"}, None) == []
