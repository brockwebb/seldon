"""REVIEW-001 Part B: the review findings of classes data_loss and operator_authority, each red before its fix.

F-01 (data_loss): `dispatch.gate.scheduled_worktree` was checked only for a leading `/` and `..`, and the scheduled
run's `_clear` removed whatever it named, as a worktree (`git worktree remove --force`) and then with `rmtree`. A value of
`.`, a tracked directory or an in-flight task's worktree deleted it. Now `.` is refused at load, and `_clear` removes a
path only when the scheduled run's own ownership marker says the run created it.

F-02, F-03, F-04 (operator_authority, AD-034-R41): a task the dispatcher blocked completes only on a passing full gate
of the branch's tip or the operator's recorded `--ungated` reason. The MCP `seldon_cc_complete` skipped the check (F-02);
a scoped gate that selected nothing counted as evidence (F-03); and a task stepped out of `blocked` by hand before
`cc complete` was not checked at all (F-04).

The review record: docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from seldon.commands import dispatch_gate as GATE
from seldon.core import gate_plan as GP
from seldon.core.events import append_event, make_event
from tests.test_sel055_scheduled_gate import _cfg, _scheduled_repo, _write
from tests.test_sel058_hazbrief_filings import REL, _block, _gate_run, _git, _in, _state, repo  # noqa: F401


def _sh(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=cwd, check=True, capture_output=True, text=True)


# ============================================================================== F-01: the scheduled checkout's path

@pytest.mark.parametrize("value", [".", "./", "a/.."])
def test_a_scheduled_worktree_that_names_the_checkout_itself_is_refused_at_load(value):
    with pytest.raises(GP.GateConfigError, match="scheduled_worktree"):
        GP.load_gate_config({"scheduled_worktree": value}, "true")


def _with_worktree(cfg: dict, rel: str) -> dict:
    gate = dict(cfg["gate"])
    gate["scheduled_worktree"] = rel
    return {**cfg, "gate": gate}


def test_a_scheduled_run_does_not_delete_a_tracked_directory_its_config_names(tmp_path):
    p = _scheduled_repo(tmp_path)
    _write(p, {"docs/keep.md": "kept\n"})
    _sh(p, "git", "add", "-A")
    _sh(p, "git", "commit", "-q", "-m", "docs")
    with pytest.raises(GP.GateConfigError, match="did not create"):
        GATE.run_scheduled(p, _with_worktree(_cfg(p, "true", tmp_path / "n.txt"), "docs"), "due")
    assert (p / "docs" / "keep.md").read_text() == "kept\n"


def test_a_scheduled_run_does_not_remove_a_task_worktree_its_config_names(tmp_path):
    p = _scheduled_repo(tmp_path)
    task_wt = p / ".claude" / "worktrees" / "busy"
    _sh(p, "git", "worktree", "add", "-q", "-b", "worktree-busy", str(task_wt))
    (task_wt / "work.txt").write_text("in flight\n")
    with pytest.raises(GP.GateConfigError, match="did not create"):
        GATE.run_scheduled(p, _with_worktree(_cfg(p, "true", tmp_path / "n.txt"), ".claude/worktrees/busy"), "due")
    assert (task_wt / "work.txt").read_text() == "in flight\n"
    assert str(task_wt) in _sh(p, "git", "worktree", "list").stdout


def test_a_checkout_a_killed_scheduled_run_left_is_cleared_by_the_next_run(tmp_path):
    p = _scheduled_repo(tmp_path)
    wt = p / ".seldon" / "gate_main"
    wt.parent.mkdir(parents=True)
    # What a run killed between its checkout and its clear leaves: the ownership marker and the detached checkout.
    GATE._marker_path(wt).write_text(str(wt) + "\n")
    _sh(p, "git", "worktree", "add", "-q", "--detach", str(wt), "main")
    out = GATE.run_scheduled(p, _cfg(p, "test -f tests/test_a.py", tmp_path / "n.txt"), "due")
    assert out["ok"]
    assert not wt.exists() and not GATE._marker_path(wt).exists()
    assert "gate_main" not in _sh(p, "git", "worktree", "list").stdout


# ============================================================================== F-03: R41 evidence is a full gate

def _scoped_run(tree: str, reason: str = "declared_none: every changed path is in a `tests: none` slice") -> dict:
    return make_event("gate_run", "cli", "accepted", {"tree": tree, "outcome": "pass", "dirty": False,
                                                      "tier": GP.TIER_SCOPED, "reason": reason, "call_site": "cli",
                                                      "seconds": 0.0, "tests_run": 0})


def test_a_scoped_gate_of_the_branch_tip_is_not_completion_evidence(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
        _sh(root, "git", *args)
    (root / "f.txt").write_text("x\n")
    _sh(root, "git", "add", "f.txt")
    _sh(root, "git", "commit", "-q", "-m", "one")
    tree = _git(root, "rev-parse", "main^{tree}")
    assert GP.completion_evidence(root, "main", [_scoped_run(tree)]) is None
    full = _gate_run(tree)
    assert GP.completion_evidence(root, "main", [full, _scoped_run(tree)])["event_id"] == full["event_id"], \
        "a newer scoped run does not hide an older full one"


def test_cc_complete_refuses_a_blocked_task_whose_only_gate_of_main_is_scoped(repo, neo4j_driver):
    from seldon.commands.cc import cc_group
    tid = _block(repo, neo4j_driver)
    append_event(repo, _scoped_run(_git(repo, "rev-parse", "main^{tree}")))
    refused = _in(repo, cc_group, ["complete", REL])
    assert refused.exit_code == 1, refused.output
    assert _state(neo4j_driver, tid)["state"] == "blocked"


# ============================================================================== F-02: the MCP completion

def test_the_mcp_completion_refuses_a_blocked_task_with_no_gate_on_main(repo, neo4j_driver):
    from seldon.mcp_server import seldon_cc_complete
    tid = _block(repo, neo4j_driver)
    out = seldon_cc_complete(filepath=REL, project_dir=str(repo))
    assert out.startswith("Error:") and "blocked_ungated" in out and "AD-034-R41" in out, out
    assert _state(neo4j_driver, tid)["state"] == "blocked"

    ok = _gate_run(_git(repo, "rev-parse", "main^{tree}"))
    append_event(repo, ok)
    done = seldon_cc_complete(filepath=REL, project_dir=str(repo))
    assert "state: completed" in done, done
    st = _state(neo4j_driver, tid)
    assert st["state"] == "completed" and st["gate"] == ok["event_id"]


# ============================================================================== F-04: a block stepped out of by hand

def test_a_blocked_task_moved_out_of_blocked_by_hand_is_still_held_to_r41(repo, neo4j_driver):
    from seldon.commands.cc import cc_group
    from seldon.commands.task import task_group
    tid = _block(repo, neo4j_driver)
    moved = _in(repo, task_group, ["update", tid, "--state", "in_progress"])
    assert moved.exit_code == 0, moved.output
    refused = _in(repo, cc_group, ["complete", REL])
    assert refused.exit_code == 1, refused.output
    assert "blocked_ungated" in refused.output, refused.output
    assert _state(neo4j_driver, tid)["state"] == "in_progress"


def test_a_blocked_task_the_dispatcher_launched_again_is_not_held_to_r41(repo, neo4j_driver):
    from seldon.commands.cc import cc_group
    from seldon.commands.task import task_group
    tid = _block(repo, neo4j_driver)
    for state in ("accepted", "in_progress"):
        res = _in(repo, task_group, ["update", tid, "--state", state])
        assert res.exit_code == 0, res.output
    # The redrive's relaunch: the dispatcher's newest word on the task comes after the block.
    append_event(repo, make_event("dispatch_launched", "dispatcher", "accepted", {"task_id": tid}))
    done = _in(repo, cc_group, ["complete", REL])
    assert done.exit_code == 0, done.output
    assert _state(neo4j_driver, tid)["state"] == "completed"
