"""DISP-003R Part C (AD-034 ADDENDUM 03): a task blocked `stop_gate_unpassed` whose kept worktree is complete is re-gated
in place and merged.

PA-002 (`314a3942`) finished with exit 0, its RESULT committed and its tests green, and was blocked
`stop_gate_unpassed` only because its check ran the wrong code (Part A). The one way back was a fresh launch that
redid the work. `seldon dispatch regate <task>` rebases the kept branch onto main, runs the task's `check:` lines in
its tree, and on pass hands the branch to the merge path; the dispatcher does the same on every pass.

Driven end to end through `seldon dispatch once` with the stub CLI of `tests/dispatch_scaffold.py`. The task's check
names a file main does not hold at launch, so the session's Stop gate blocks; the file then lands on main, which is
the case of a fix merged after the session ended.
"""
from __future__ import annotations

import pytest

from seldon.commands import dispatch_worktree as W
from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import NEO4J_DB, RESEARCH_YAML, add_task, git, make_project, register, run_cli, write_stub

STEM = "disp003_regate"
PARTS = "**Parts:** A 1.0.\n\n## Part A: the work\n\nAcceptance:\n- `check: test -f fix/landed.txt`\n"


@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _payloads(p, kind):
    return [e["payload"] for e in read_events(p) if e["event_type"] == kind]


def _state(neo4j_driver, task_id):
    with neo4j_driver.session(database=NEO4J_DB) as s:
        return s.run("MATCH (t:ResearchTask {artifact_id: $i}) RETURN t.state AS s", i=task_id).single()["s"]


def _blocked_session(p, neo4j_driver, dc):
    add_task(p, STEM, PARTS)
    tid = register(p, neo4j_driver, dc, STEM, "2026-10-20T00:00:00Z")
    write_stub(p, {STEM: {"write": {"out/work.txt": "work\n"}, "part_complete": ["A"], "stop_hook": True,
                          "exit": 0}})
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "stop_gate_unpassed" and fin["result_present"] is True, fin
    assert _state(neo4j_driver, tid) == "blocked", res.output
    assert (p / fin["worktree"]).exists(), "the unmerged task keeps its worktree"
    return tid, fin


def _land_fix_on_main(p):
    (p / "fix").mkdir()
    (p / "fix" / "landed.txt").write_text("fixed\n")
    git(p, "add", "fix/landed.txt")
    git(p, "commit", "-q", "-m", "fix lands on main", "--", "fix/landed.txt")


@pytest.mark.usefixtures("neo4j_available")
def test_a_blocked_task_whose_checks_now_pass_is_regated_and_merged(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)
    tid, fin = _blocked_session(p, neo4j_driver, dc)

    # Negative control (AD-038-R6): while the check still fails, regate leaves the task blocked and quotes it.
    res = run_cli(p, dispatch_group, ["regate", tid])
    assert res.exit_code == 1, res.output
    (rg,) = _payloads(p, W.EVENT_REGATED)
    assert rg["outcome"] == "fail" and rg["failed"][0]["command"] == "test -f fix/landed.txt", rg
    assert "test -f fix/landed.txt" in res.output
    assert _state(neo4j_driver, tid) == "blocked"
    assert _payloads(p, D.EVENT_FINISHED)[-1]["outcome"] == "stop_gate_unpassed", "a failed regate writes no finish"

    # A pass with nothing changed does not re-run the same failed regate.
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    assert len(_payloads(p, W.EVENT_REGATED)) == 1

    _land_fix_on_main(p)
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    assert "regate:" in res.output, res.output
    rg = _payloads(p, W.EVENT_REGATED)[-1]
    assert rg["outcome"] == "pass" and rg["checks"][0]["outcome"] == "pass", rg
    assert rg["checks"][0]["pythonpath"].split(":")[0].endswith(fin["worktree"]), "Part A's path: the kept tree"
    done = _payloads(p, D.EVENT_FINISHED)[-1]
    assert done["outcome"] == "merged", done
    assert done["regate"]["regate_id"] == rg["regate_id"], done
    assert _state(neo4j_driver, tid) == "completed"
    assert git(p, "show", "main:out/work.txt").stdout == "work\n"
    assert git(p, "merge-base", "--is-ancestor", fin["branch"], "main", check=False).returncode == 0
    assert not (p / fin["worktree"]).exists(), "the merge path swept the worktree"

    n = len(_payloads(p, W.EVENT_REGATED))
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    assert len(_payloads(p, W.EVENT_REGATED)) == n, "a merged task is not regated again"


@pytest.mark.usefixtures("neo4j_available")
def test_regate_refuses_a_task_that_is_not_blocked_stop_gate_unpassed(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)
    stem = STEM + "_refused"           # its own name: the test database is shared, and a name may recur
    add_task(p, stem, PARTS)
    tid = register(p, neo4j_driver, dc, stem, "2026-10-20T00:00:00Z")
    res = run_cli(p, dispatch_group, ["regate", tid])
    assert res.exit_code != 0 and "not a regate candidate" in res.output, res.output
    assert _payloads(p, W.EVENT_REGATED) == []
