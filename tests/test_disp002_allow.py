"""DISP-002 Part B: the launch allows exactly the command classes a task may run, and a kept tree that holds nothing
is removed by the dispatcher (AD-034 ADDENDUM 02).

`cc_tasks/2026-10-19_DISP-002_breaker_does_not_veto_a_green_merge.md`. DISP-001R's three classifier blocks were false
positives against work its task file ordered: `git worktree remove` of empty kept trees, a `cp` out of one, and a
pytest run. The launch's settings now carry `permissions.allow` for five shapes, each quoted with its instruction in
`seldon.yaml`, and nothing else. The kept trees that a dispatched session may not remove are removed by the pass
once their task is redriven or ended and their branch holds nothing beyond main.
"""
from __future__ import annotations

import json

import pytest

from seldon.commands import dispatch as S
from seldon.commands import dispatch_worktree as W
from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core.artifacts import transition_task
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    NEO4J_DB, RESEARCH_YAML, SELDON_REPO, add_task, git, make_project, register, run_cli, task_states, write_stub,
)

FIVE = ["Bash(git worktree *)", "Bash(git branch -D *)", "Bash(cp *)", "Bash(pytest *)", "Bash(python -m pytest *)"]


def test_a_seldon_launch_carries_the_five_allow_rules_and_no_others():
    cfg = D.load_dispatch_config(SELDON_REPO)
    settings = S._session_settings(SELDON_REPO, cfg)
    assert settings["permissions"] == {"allow": FIVE}
    spec = {"cli_path": "/x/claude", "args": ["--model", "m", "--settings", json.dumps({"switchModelsOnFlag": False})]}
    cmd = S._launch_cmd(cfg, "p", spec, worktree="t", settings=settings)
    launched = json.loads(cmd[cmd.index("--settings") + 1])
    assert launched["permissions"] == {"allow": FIVE}, "the rules reach the CLI's one --settings"
    assert all(a["instruction"].strip() for a in cfg["allow"]), "each rule carries the instruction that needs it"


def test_a_project_without_allow_rules_launches_without_a_permissions_block(tmp_path):
    p = make_project(tmp_path)
    assert "permissions" not in S._session_settings(p, D.load_dispatch_config(p))


@pytest.mark.parametrize("entry", [{"rule": "Bash(cp *)"}, {"rule": "Bash(cp *)", "instruction": " "},
                                   {"rule": "Write(*)", "instruction": "x"}, "Bash(cp *)"])
def test_an_allow_rule_without_its_instruction_or_not_a_bash_rule_refuses_at_load(tmp_path, entry):
    p = make_project(tmp_path, dispatch_extra={"allow": [entry]})
    with pytest.raises(D.DispatchConfigError, match="dispatch.allow"):
        D.load_dispatch_config(p)


# ------------------------------------------------------------------------------------------ the stale kept tree

@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


def _kept(tmp_path, neo4j_driver, dc, monkeypatch, stems):
    """A project whose tasks each failed in their session (exit 1, no RESULT): blocked, tree and branch kept."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = make_project(tmp_path)
    ids = {}
    for n, stem in enumerate(stems):
        add_task(p, stem)
        ids[stem] = register(p, neo4j_driver, dc, stem, f"2026-10-19T00:00:0{n}Z")
    write_stub(p, {s: {"result": False, "exit": 1} for s in stems})
    for _ in stems:
        assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    kept = {e["payload"]["task_id"]: e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_WORKTREE_KEPT}
    states = task_states(neo4j_driver)
    assert set(kept) == set(ids.values()) and {states[s] for s in stems} == {"blocked"}
    return p, ids, kept


def _to(neo4j_driver, dc, p, task_id, state):
    transition_task(project_dir=p, driver=neo4j_driver, database=NEO4J_DB, domain_config=dc, artifact_id=task_id,
                    current_state="blocked", new_state=state, actor="cc", authority="accepted",
                    terminal_reason="test" if state in ("superseded", "withdrawn") else None)


@pytest.mark.usefixtures("neo4j_available")
def test_an_empty_kept_tree_of_a_redriven_task_is_removed_with_its_branch(tmp_path, neo4j_driver, dc, monkeypatch):
    p, ids, kept = _kept(tmp_path, neo4j_driver, dc, monkeypatch, ["r", "b"])
    from seldon.core import redrive as RD
    RD.redrive(p, neo4j_driver, NEO4J_DB, dc, ids["r"], "cc")
    removed = W.sweep_stale_kept(p, neo4j_driver, NEO4J_DB)
    assert [r["task_id"] for r in removed] == [ids["r"]]
    assert removed[0]["reason"] == "stale_kept" and removed[0]["branch_kept"] is False
    assert not (p / kept[ids["r"]]["worktree"]).exists()
    assert git(p, "rev-parse", "--verify", "-q", kept[ids["r"]]["branch"], check=False).returncode != 0
    # The negative control: a task still blocked keeps its tree and branch, the operator's evidence.
    assert (p / kept[ids["b"]]["worktree"]).exists()
    assert git(p, "rev-parse", "--verify", "-q", kept[ids["b"]]["branch"], check=False).returncode == 0
    assert [e["payload"]["task_id"] for e in read_events(p)
            if e["event_type"] == D.EVENT_WORKTREE_REMOVED] == [ids["r"]]


@pytest.mark.usefixtures("neo4j_available")
def test_untracked_files_keep_a_redriven_tree_and_go_with_a_superseded_one(tmp_path, neo4j_driver, dc, monkeypatch):
    p, ids, kept = _kept(tmp_path, neo4j_driver, dc, monkeypatch, ["r2", "s2"])
    for stem in ("r2", "s2"):
        (p / kept[ids[stem]]["worktree"] / "tests").mkdir(exist_ok=True)
        (p / kept[ids[stem]]["worktree"] / "tests" / "test_left.py").write_text("x = 1\n")
    _to(neo4j_driver, dc, p, ids["r2"], "accepted")
    _to(neo4j_driver, dc, p, ids["s2"], "superseded")
    removed = W.sweep_stale_kept(p, neo4j_driver, NEO4J_DB)
    assert [r["task_id"] for r in removed] == [ids["s2"]]
    assert removed[0]["discarded_untracked"] == ["tests/"] and removed[0]["task_state"] == "superseded"
    assert (p / kept[ids["r2"]]["worktree"] / "tests" / "test_left.py").exists()


@pytest.mark.usefixtures("neo4j_available")
def test_a_kept_branch_with_a_commit_beyond_main_is_never_removed(tmp_path, neo4j_driver, dc, monkeypatch):
    p, ids, kept = _kept(tmp_path, neo4j_driver, dc, monkeypatch, ["c3"])
    wt = p / kept[ids["c3"]]["worktree"]
    (wt / "work.txt").write_text("work\n")
    git(wt, "add", "work.txt")
    git(wt, "commit", "-q", "-m", "work", "--", "work.txt")
    _to(neo4j_driver, dc, p, ids["c3"], "superseded")
    assert W.sweep_stale_kept(p, neo4j_driver, NEO4J_DB) == []
    assert wt.exists()


@pytest.mark.usefixtures("neo4j_available")
def test_the_pass_runs_the_stale_sweep(tmp_path, neo4j_driver, dc, monkeypatch):
    p, ids, kept = _kept(tmp_path, neo4j_driver, dc, monkeypatch, ["w4"])
    _to(neo4j_driver, dc, p, ids["w4"], "withdrawn")
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    assert "sweep: removed kept" in res.output, res.output
    assert not (p / kept[ids["w4"]]["worktree"]).exists()
