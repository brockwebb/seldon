"""DISP-004R Part A: a cross-repo task's commits are pushed in every repository its Repo line names (AD-034-R12).

`cc_tasks/2026-10-27_DISP-004R_a_cross_repo_task_is_pushed_in_every_repository_it_names.md`. SQ-019 committed
ai-readiness-kg 04c26099 and said "committed and not pushed": its header said L4 push in both repositories, the launch
prompt forbade pushing, and squiddy's dispatcher pushed only squiddy. The launch now reads the `**Repo:**` line's L4
clause and records each other repository's HEAD; a merged finish pushes main in each one whose HEAD moved and whose
tree is clean, recording `push` per repository, and a dirty tree there refuses that push and alarms.

The parser is tested on the Repo lines the three governed repositories actually carry. The finish is driven end to end
through `seldon dispatch once` with the stub CLI of `tests/dispatch_scaffold.py`, which commits on a sibling
repository's main by path, as a cross-repo session does (AD-036-R12).
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from seldon.commands import dispatch_worktree as W
from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, add_task, git, make_project, register, run_cli, write_stub,
)

STEM = "disp004r_cross"


@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _sibling(root: Path, name: str, origin: bool = True) -> Path:
    """A git checkout `root/name` on main with one commit, pushed to a bare origin beside it."""
    repo = root / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "README").write_text(f"{name}\n", encoding="utf-8")
    git(repo, "add", "README")
    git(repo, "commit", "-q", "-m", "init")
    if origin:
        bare = root / f"{name}_origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
        git(repo, "remote", "add", "origin", str(bare))
        git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def _ahead(repo: Path) -> int:
    return int(git(repo, "rev-list", "--count", "@{u}..HEAD").stdout.strip())


def _payloads(p, kind):
    return [e["payload"] for e in read_events(p) if e["event_type"] == kind]


# ======================================================================== the Repo line, read


@pytest.fixture
def root(tmp_path):
    for name in ("seldon", "squiddy", "ai-readiness-kg", "hazbrief-mcp", "arnold"):
        _sibling(tmp_path, name, origin=False)
    return tmp_path


def _targets(root, line, own="seldon"):
    return [p.name for p in D.repo_push_targets(line, root / own, root)]


def test_this_task_s_own_repo_line_names_squiddy_and_ai_readiness_kg(root):
    line = ("seldon (primary); squiddy and ai-readiness-kg (first run pushes their outstanding main). L4: commit, "
            "merge, push in all three.")
    assert _targets(root, line) == ["squiddy", "ai-readiness-kg"]


def test_a_push_segment_that_names_a_repository_pushes_that_one_only(root):
    line = ("squiddy (primary). Cross-repo by absolute path: `{r}/hazbrief-mcp` (governed graph at "
            "`graphs/hazbrief-corpus`, read as evidence in Parts A and B, written in Part D). L4: commit, merge, push in "
            "squiddy; the hazbrief graph release commits in hazbrief-mcp.").format(r=root)
    assert _targets(root, line, own="squiddy") == []
    line = "seldon (primary). L4: commit, merge, push in seldon and arnold. hazbrief-mcp is read, never written."
    assert _targets(root, line) == ["arnold"]


def test_a_quantified_clause_pushes_every_absolute_path_the_line_names(root):
    line = ("seldon. Cross-repo by absolute path: `{r}/squiddy`, `{r}/arnold`, `{r}/ai-readiness-kg` (Part C, one "
            "config line each). L4: commit, merge, push in every repo touched.").format(r=root)
    assert _targets(root, line) == ["squiddy", "arnold", "ai-readiness-kg"]


@pytest.mark.parametrize("line", [
    # A bare clause is the primary's own push: an evidence repository is never pushed by it.
    "squiddy. Evidence read from `{r}/hazbrief-mcp` (read only). L4: commit, merge and push; the dispatcher merges.",
    "seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green.",
    "seldon (primary); squiddy. L4: commit and merge in both.",            # no push
    "seldon (primary); squiddy and arnold.",                                # no L4 clause
    "seldon",
    None,
])
def test_a_line_with_no_cross_repo_push_pushes_nothing_else(root, line):
    assert _targets(root, line.format(r=root) if line else line) == []


def test_a_word_that_names_no_checkout_is_prose(root):
    line = "seldon (primary); wintermute and squiddy. L4: commit, merge, push in all repositories touched."
    assert _targets(root, line) == ["squiddy"], "wintermute is not a checkout under this root"


def test_the_config_defaults_and_refuses_a_blank_root(tmp_path):
    p = make_project(tmp_path)
    cfg = D.load_dispatch_config(p)
    assert cfg["cross_repo_root"] == ".." and cfg["cross_repo_branch"] == "main"
    with pytest.raises(D.DispatchConfigError, match="cross_repo_root"):
        D.load_dispatch_config(p, {"dispatch": {**cfg, "cross_repo_root": " "}})


# ===================================================================== the finish, end to end


def _cross_task(p, neo4j_driver, dc, line, stub):
    add_task(p, STEM, f"**Repo:** {line}\n")
    tid = register(p, neo4j_driver, dc, STEM, "2026-10-27T00:00:00Z")
    write_stub(p, {STEM: {"write": {"out/a.txt": "a\n"}, **stub}})
    return tid


@pytest.mark.usefixtures("neo4j_available")
def test_a_session_committing_in_two_repositories_is_pushed_in_both(tmp_path, neo4j_driver, dc):
    """The task's fixture: a task naming two repositories, a session committing in both, both pushed. A third
    repository the line names as evidence moves too (its own work) and is left alone."""
    p = make_project(tmp_path)
    other = _sibling(tmp_path, "other")
    evidence = _sibling(tmp_path, "evidence")
    _cross_task(p, neo4j_driver, dc, "proj (primary); other. L4: commit, merge, push in both. evidence is read only.",
                {"other_commit": {str(other): {"x.txt": "x\n"}, str(evidence): {"e.txt": "e\n"}}})

    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output

    launch = _payloads(p, D.EVENT_LAUNCHED)[-1]
    assert [Path(r["repo"]).name for r in launch["push_repos"]] == ["other"]
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merged", (fin, res.output)
    (push,) = fin["push_repos"]
    assert push["push"] == "pushed" and push["ahead"] == 1, push
    assert push["head_at_finish"] != push["head_at_launch"]
    assert "push: other pushed 1 commit(s)" in res.output, res.output
    assert _ahead(other) == 0, "the sibling's main is on its origin"
    assert git(p, "rev-list", "--count", "@{u}..HEAD").stdout.strip() == "0", "and so is the project's"
    assert _ahead(evidence) == 1, "a repository outside the push clause is never pushed"


@pytest.mark.usefixtures("neo4j_available")
def test_a_parallel_supervisor_carries_the_reading_to_its_finish_and_pushes(tmp_path, neo4j_driver, dc, monkeypatch):
    """The same through `_start_claimed` and the detached supervisor, whose `--extra` keeps only `LEASE_EXTRA_KEYS`.
    AD-037-R9's hold is not under test: the opt-in stands in for an accepted record, as in test_dispatch_parallel."""
    from seldon.core import qc
    monkeypatch.setattr(qc, "parallel_opted_in", lambda project_dir, config: True)
    p = make_project(tmp_path, dispatch_extra={"max_parallel": 2, "gate_command": "true",
                                               "resources": {"neo4j": {"paths": []}},
                                               "merge_lock_timeout_s": 60, "gate_timeout_s": 60})
    other = _sibling(tmp_path, "other")
    add_task(p, STEM, "**Repo:** proj; other. L4: commit, merge, push in both.\n"
                      "**Exclusive:** no\n**Touches:** out/\n")
    tid = register(p, neo4j_driver, dc, STEM, "2026-10-27T00:00:00Z")
    write_stub(p, {STEM: {"write": {"out/a.txt": "a\n"}, "other_commit": {str(other): {"x.txt": "x\n"}}}})

    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline and not [f for f in _payloads(p, D.EVENT_FINISHED) if f["task_id"] == tid]:
        time.sleep(0.25)
    sup = p / "logs" / "dispatch" / f"{STEM}.supervisor.log"
    fins = [f for f in _payloads(p, D.EVENT_FINISHED) if f["task_id"] == tid]
    assert len(fins) == 1, (res.output, sup.read_text() if sup.exists() else "(no supervisor log)")
    assert fins[0]["outcome"] == "merged", fins[0]
    (push,) = fins[0]["push_repos"]
    assert push["push"] == "pushed", push
    assert _ahead(other) == 0


@pytest.mark.usefixtures("neo4j_available")
def test_a_named_repository_whose_head_did_not_move_is_not_pushed(tmp_path, neo4j_driver, dc):
    """HEAD unmoved during the session is not this task's to push, even when the repository is ahead of origin."""
    p = make_project(tmp_path)
    other = _sibling(tmp_path, "other")
    (other / "y.txt").write_text("y\n", encoding="utf-8")
    git(other, "add", "y.txt")
    git(other, "commit", "-q", "-m", "someone else's, before the launch")
    _cross_task(p, neo4j_driver, dc, "proj; other. L4: commit, merge, push in both.", {})

    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    (push,) = _payloads(p, D.EVENT_FINISHED)[-1]["push_repos"]
    assert push["push"] == "unmoved", push
    assert _ahead(other) == 1


@pytest.mark.usefixtures("neo4j_available")
def test_a_dirty_tree_in_a_named_repository_refuses_its_push_and_alarms(tmp_path, neo4j_driver, dc):
    alarm = tmp_path / "alarm.jsonl"
    notify = (f"printf '%s\\t%s\\n' \"$SELDON_NOTIFY_OUTCOME\" \"$SELDON_NOTIFY_MESSAGE\" >> {alarm}")
    p = make_project(tmp_path, dispatch_extra={"notify": notify})
    other = _sibling(tmp_path, "other")
    clean = _sibling(tmp_path, "clean")
    (other / "wip.txt").write_text("uncommitted\n", encoding="utf-8")
    _cross_task(p, neo4j_driver, dc, "proj; other and clean. L4: commit, merge, push in all three.",
                {"other_commit": {str(other): {"x.txt": "x\n"}, str(clean): {"c.txt": "c\n"}}})

    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merged", "a refusal elsewhere does not undo this repository's merge"
    by = {Path(r["repo"]).name: r for r in fin["push_repos"]}
    assert by["other"]["push"] == "dirty_tree" and by["other"]["dirty_paths"] == ["wip.txt"], by
    assert by["clean"]["push"] == "pushed", by
    assert _ahead(other) == 1 and _ahead(clean) == 0
    assert "push REFUSED in other (dirty_tree): wip.txt" in res.output, res.output
    lines = [ln.split("\t") for ln in alarm.read_text().splitlines()]
    assert [W.CROSS_REPO_PUSH_REFUSED, f"cross-repo push refused for {STEM}: other dirty_tree"] in lines, lines


@pytest.mark.usefixtures("neo4j_available")
def test_an_unmerged_finish_pushes_nothing_elsewhere_and_says_what_it_held(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)
    other = _sibling(tmp_path, "other")
    _cross_task(p, neo4j_driver, dc, "proj; other. L4: commit, merge, push in both.",
                {"other_commit": {str(other): {"x.txt": "x\n"}}, "exit": 1})

    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "session_failed", fin
    (held,) = fin["push_repos"]
    assert held["push"] == "held_unmerged" and held["head_at_finish"] != held["head_at_launch"], held
    assert _ahead(other) == 1
    assert json.dumps(fin)  # the record is plain JSON
