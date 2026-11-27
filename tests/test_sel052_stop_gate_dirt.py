"""SEL-052 Part B, the coordinator's observation of critical-thinking-ai CTAI-006R (2026-11-26).

All five Parts passed and the work was committed, but the session ended with one untracked directory in its worktree
(`graphs/critical-thinking-evidence/archive:inbox/`, a `.gitkeep`). The merge round refused it as
`merge_blocked: uncommitted_changes` at 22:55:16Z, nothing rang, and a person redrove it at 23:15:18Z so a second
session could delete one directory (3 minutes). The Stop gate now reads the merge round's own predicate in the
session's tree, so the session that left the path removes or commits it before it may end.
"""
from __future__ import annotations

from tests.dispatch_scaffold import git
from tests.test_friction002_stop_hook_gate import _records, _stop, project  # noqa: F401
from seldon.core import stations as Q


def _worktree(p):
    wt = p / ".claude" / "worktrees" / "w"
    git(p, "worktree", "add", "-q", "-b", "worktree-w", str(wt))
    return wt


def test_a_session_that_leaves_an_untracked_path_is_held_to_remove_it(project):
    wt = _worktree(project)
    stray = wt / "graphs" / "g" / "archive:inbox"
    stray.mkdir(parents=True)
    (stray / ".gitkeep").write_text("", encoding="utf-8")
    decision = _stop(project, cwd=wt)
    assert decision is not None and decision["decision"] == "block", decision
    # git collapses an untracked directory to its first untracked ancestor, as the merge round's Issue names it.
    assert "commit or remove before ending: graphs/" in decision["reason"], decision["reason"]
    gate = _records(project, Q.EVENT_STOP_GATE)[-1]["payload"]
    assert gate["verdict"] == "block" and gate["dirt"] == ["graphs/"]

    (stray / ".gitkeep").unlink()
    stray.rmdir()
    assert _stop(project, cwd=wt) is None
    gate = _records(project, Q.EVENT_STOP_GATE)[-1]["payload"]
    assert gate["verdict"] == "pass" and gate["dirt"] == []


def test_a_clean_worktree_ends_on_its_first_stop(project):
    """The negative control (AD-038-R6): committed work is not held."""
    wt = _worktree(project)
    (wt / "made.txt").write_text("x\n", encoding="utf-8")
    git(wt, "add", "made.txt")
    git(wt, "commit", "-q", "-m", "the work")
    assert _stop(project, cwd=wt) is None
    assert _records(project, Q.EVENT_STOP_GATE)[-1]["payload"]["verdict"] == "pass"
