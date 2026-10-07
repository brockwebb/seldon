"""SEL-004: tasks run in parallel, each in its own git worktree, and merge on green.

`cc_tasks/2026-10-07_SEL-004_worktree_per_task_dispatch.md` decisions 1 to 4 and 7, and its
Tests section, against a scratch repository (a bare `origin`, a tracked event store marked
`merge=union`) and the per-process scratch Neo4j database. Every pass is a real `seldon
dispatch once`; every launch starts a real detached supervisor (`python -m seldon dispatch
supervise`) that runs the stub `claude` in a real worktree and merges with real git. Zero
model calls, no network beyond the local bare remote.

Supervisors are detached, so each test waits on what the operator would read: the task's
graph state and the worktree lease's release record.
"""
from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

import pytest

from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    NEO4J_DB, RESEARCH_YAML, add_task, git, make_project, register, run_cli, task_states,
    write_stub,
)

pytestmark = pytest.mark.usefixtures("neo4j_available")

PARALLEL = {"max_parallel": 3, "gate_command": "test ! -e RED",
            "resources": {"neo4j": {"paths": []}}, "merge_lock_timeout_s": 60,
            "gate_timeout_s": 60}

NONEXCL = "**Exclusive:** no\n**Touches:** {touches}\n"


@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _project(tmp_path, **extra):
    return make_project(tmp_path, dispatch_extra={**PARALLEL, **extra})


def _once(p):
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    return res.output


def _wait(pred, what, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {what}")


def _leases(p):
    return {Path(x["path"]).stem: x for x in D.worktree_leases(
        p, {"lease_dir": PARALLEL.get("lease_dir", ".seldon/leases")})}


def _settled(p, driver, names):
    """Every named task has left `in_progress` and no worktree lease is held."""
    states = task_states(driver)
    return (all(states.get(n) not in ("in_progress", None) for n in names)
            and not any(x["held"] for x in _leases(p).values()))


def _supervisor_log(p, stem):
    path = p / "logs" / "dispatch" / f"{stem}.supervisor.log"
    return path.read_text() if path.exists() else "(no supervisor log)"


def _wait_settled(p, driver, names, timeout=90):
    try:
        _wait(lambda: _settled(p, driver, names), f"{names} to settle", timeout)
    except AssertionError:
        logs = "\n".join(f"--- {n}\n{_supervisor_log(p, n)}" for n in names)
        raise AssertionError(f"timed out; states {task_states(driver)}\n{logs}")


def _marks(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        stem, what, t = line.split()
        out.setdefault(stem, {})[what] = float(t)
    return out


def _finished(p, stem=None):
    evs = [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_FINISHED]
    if stem:
        evs = [e for e in evs if e.get("source_file") == f"cc_tasks/{stem}.md"]
    return evs


def _show(p, rev, path):
    r = git(p, "show", f"{rev}:{path}", check=False)
    return r.stdout if r.returncode == 0 else None


# ======================================================== concurrency, from the declaration

def test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge(
        tmp_path, neo4j_driver, clean_test_db, dc):
    p = _project(tmp_path)
    marks = tmp_path / "marks.txt"
    add_task(p, "a", NONEXCL.format(touches="out/a/"))
    add_task(p, "b", NONEXCL.format(touches="out/b/"))
    write_stub(p, {"a": {"write": {"out/a/x.txt": "a\n"}, "sleep": 3, "mark": str(marks)},
                   "b": {"write": {"out/b/x.txt": "b\n"}, "sleep": 3, "mark": str(marks)}})
    ta = register(p, neo4j_driver, dc, "a", "2026-10-07T00:00:01Z")
    tb = register(p, neo4j_driver, dc, "b", "2026-10-07T00:00:02Z")

    out = _once(p)
    assert out.count("launching") == 2, out
    _wait_settled(p, neo4j_driver, ["a", "b"])

    m = _marks(marks)
    assert m["a"]["start"] < m["b"]["end"] and m["b"]["start"] < m["a"]["end"], m
    assert task_states(neo4j_driver) == {"a": "completed", "b": "completed"}
    assert _show(p, "main", "out/a/x.txt") == "a\n" and _show(p, "main", "out/b/x.txt") == "b\n"
    assert _show(p, "main", "cc_tasks/a_RESULT.md") and _show(p, "main", "cc_tasks/b_RESULT.md")
    # Worktrees removed, branches deleted, main pushed, primary clean.
    assert not (p / ".worktrees" / "a").exists() and not (p / ".worktrees" / "b").exists()
    assert git(p, "branch", "--list", "task/*").stdout.strip() == ""
    assert git(p, "rev-parse", "main").stdout == git(p, "rev-parse", "origin/main").stdout
    assert git(p, "status", "--porcelain").stdout == ""
    fin = {e["task_id"]: e for e in _finished(p)}
    assert fin[ta]["outcome"] == "merged" and fin[tb]["outcome"] == "merged"
    assert fin[ta]["ok"] is True and fin[ta]["merge"]["undeclared_writes"] == []
    launched = [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_LAUNCHED]
    assert {pl["mode"] for pl in launched} == {"worktree"}
    assert all(pl["criteria"]["c10"]["ok"] and pl["criteria"]["c11"]["ok"] for pl in launched)


@pytest.mark.parametrize("touches_a,touches_b", [
    ("out/**", "out/b.txt"),
    ("neo4j", "neo4j, out/b/"),
], ids=["overlapping_paths", "two_neo4j_tasks"])
def test_overlapping_tasks_serialize(tmp_path, neo4j_driver, clean_test_db, dc, touches_a,
                                     touches_b):
    """Two overlapping ones serialize, and two `neo4j` tasks serialize: the later one waits,
    says on what, and starts on a later pass once the first has merged."""
    p = _project(tmp_path)
    marks = tmp_path / "marks.txt"
    add_task(p, "a", NONEXCL.format(touches=touches_a))
    add_task(p, "b", NONEXCL.format(touches=touches_b))
    write_stub(p, {"a": {"write": {"out/a.txt": "a\n"}, "sleep": 2, "mark": str(marks)},
                   "b": {"write": {"out/b.txt": "b\n"}, "mark": str(marks)}})
    ta = register(p, neo4j_driver, dc, "a", "2026-10-07T00:00:01Z")
    register(p, neo4j_driver, dc, "b", "2026-10-07T00:00:02Z")

    out = _once(p)
    assert out.count("launching") == 1 and f"waits (overlap) on {ta[:8]}" in out, out
    _wait_settled(p, neo4j_driver, ["a"])
    assert task_states(neo4j_driver)["b"] == "proposed"
    assert _once(p).count("launching") == 1
    _wait_settled(p, neo4j_driver, ["a", "b"])
    m = _marks(marks)
    assert m["a"]["end"] <= m["b"]["start"], m
    assert task_states(neo4j_driver) == {"a": "completed", "b": "completed"}


def test_an_exclusive_task_waits_for_running_ones_and_blocks_new_ones(
        tmp_path, neo4j_driver, clean_test_db, dc):
    """A task with neither header is exclusive. It waits for the running worktree task; a
    disjoint task registered after it does not start ahead of it; it then runs ALONE in the
    primary checkout, as before SEL-004; the disjoint task follows."""
    p = _project(tmp_path)
    marks = tmp_path / "marks.txt"
    add_task(p, "r", NONEXCL.format(touches="out/r/"))
    add_task(p, "x")
    add_task(p, "b", NONEXCL.format(touches="out/b/"))
    write_stub(p, {"r": {"write": {"out/r/1.txt": "r\n"}, "sleep": 3, "mark": str(marks)},
                   "x": {"write": {"out/x.txt": "x\n"}, "complete": True, "mark": str(marks)},
                   "b": {"write": {"out/b/1.txt": "b\n"}, "mark": str(marks)}})
    tr = register(p, neo4j_driver, dc, "r", "2026-10-07T00:00:01Z")
    assert _once(p).count("launching") == 1
    tx = register(p, neo4j_driver, dc, "x", "2026-10-07T00:00:02Z")
    register(p, neo4j_driver, dc, "b", "2026-10-07T00:00:03Z")

    out = _once(p)
    assert "launching" not in out, out
    assert f"waits (exclusive_waits) on {tr[:8]}" in out
    assert f"waits (exclusive) on {tx[:8]}" in out
    _wait_settled(p, neo4j_driver, ["r"])

    out = _once(p)   # x runs in place, synchronously, and b waits behind it
    assert f"launching {tx[:8]} cc_tasks/x.md -> logs/dispatch/x.log" in out, out
    assert "stub cwd: primary" in (p / "logs" / "dispatch" / "x.log").read_text()
    assert task_states(neo4j_driver)["x"] == "completed"
    assert task_states(neo4j_driver)["b"] == "proposed"
    assert _once(p).count("launching") == 1
    _wait_settled(p, neo4j_driver, ["b"])
    m = _marks(marks)
    assert m["r"]["end"] <= m["x"]["start"] and m["x"]["end"] <= m["b"]["start"], m
    assert task_states(neo4j_driver) == {"r": "completed", "x": "completed", "b": "completed"}


# ================================================================ merge on green, by union

def test_union_merge_of_two_event_appends_is_valid(tmp_path, neo4j_driver, clean_test_db, dc):
    """Decision 4: both sessions append to the tracked event store in their own worktrees;
    `merge=union` merges them, and the merged store is valid JSONL with unique event ids and
    both appends in it."""
    p = _project(tmp_path)
    add_task(p, "a", NONEXCL.format(touches="out/a/"))
    add_task(p, "b", NONEXCL.format(touches="out/b/"))
    write_stub(p, {"a": {"append_event": True, "sleep": 1},
                   "b": {"append_event": True, "sleep": 2}})
    register(p, neo4j_driver, dc, "a", "2026-10-07T00:00:01Z")
    register(p, neo4j_driver, dc, "b", "2026-10-07T00:00:02Z")
    assert _once(p).count("launching") == 2
    _wait_settled(p, neo4j_driver, ["a", "b"])

    assert task_states(neo4j_driver) == {"a": "completed", "b": "completed"}
    store = _show(p, "main", "seldon_events.jsonl")
    lines = [json.loads(ln) for ln in store.splitlines() if ln.strip()]
    ids = [e["event_id"] for e in lines]
    assert len(ids) == len(set(ids))
    notes = sorted(e["payload"]["stem"] for e in lines if e["event_type"] == "note_recorded")
    assert notes == ["a", "b"]
    assert {e["outcome"] for e in _finished(p)} == {"merged"}


def test_a_duplicate_event_id_in_a_union_file_is_merge_blocked(tmp_path, neo4j_driver,
                                                               clean_test_db, dc):
    """The union driver keeps both sides' lines and cannot see a duplicated record; the
    post-merge check does, and the merge fails as merge_blocked."""
    p = _project(tmp_path)
    add_task(p, "a", NONEXCL.format(touches="out/a/"))
    register(p, neo4j_driver, dc, "a", "2026-10-07T00:00:01Z")
    first = (p / "seldon_events.jsonl").read_text().splitlines()[0]
    write_stub(p, {"a": {"write": {"seldon_events.jsonl": first + "\n"}}})
    assert _once(p).count("launching") == 1
    _wait_settled(p, neo4j_driver, ["a"])
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merge_blocked" and fin["merge"]["reason"] == "union_invalid"
    assert fin["merge"]["files"] == ["seldon_events.jsonl"]
    assert task_states(neo4j_driver)["a"] == "blocked"


def _issues(driver):
    with driver.session(database=NEO4J_DB) as s:
        return [dict(r) for r in s.run(
            "MATCH (i:Issue)-[:remediated_by|REMEDIATED_BY]->(t:ResearchTask) "
            "RETURN i.issue_type AS type, i.files AS files, i.merge_reason AS reason, "
            "t.name AS task, i.state AS state")]


def test_a_conflicting_rebase_ends_merge_blocked_with_an_issue(tmp_path, neo4j_driver,
                                                              clean_test_db, dc):
    """Decision 3: both declare disjoint Touches but both append to `shared.txt`. The first
    merges; the second's rebase conflicts, is aborted, and nothing is resolved: the task is
    blocked and `dispatch_merge: merge_blocked`, an Issue names the file, the worktree and
    branch stay as the session left them, and main does not move."""
    p = _project(tmp_path)
    (p / "shared.txt").write_text("base\n")
    git(p, "add", "shared.txt")
    git(p, "commit", "-q", "-m", "shared")
    add_task(p, "a", NONEXCL.format(touches="out/a/"))
    add_task(p, "b", NONEXCL.format(touches="out/b/"))
    write_stub(p, {"a": {"write": {"shared.txt": "from a\n"}, "sleep": 1},
                   "b": {"write": {"shared.txt": "from b\n"}, "sleep": 3}})
    register(p, neo4j_driver, dc, "a", "2026-10-07T00:00:01Z")
    tb = register(p, neo4j_driver, dc, "b", "2026-10-07T00:00:02Z")
    assert _once(p).count("launching") == 2
    _wait_settled(p, neo4j_driver, ["a", "b"])

    assert task_states(neo4j_driver) == {"a": "completed", "b": "blocked"}
    fin = _finished(p, "b")[-1]
    assert fin["outcome"] == "merge_blocked" and fin["merge"]["reason"] == "rebase_conflict"
    assert fin["merge"]["files"] == ["shared.txt"]
    assert _issues(neo4j_driver) == [{"type": "merge_blocked", "files": ["shared.txt"],
                                      "reason": "rebase_conflict", "task": "b",
                                      "state": "open"}]
    with neo4j_driver.session(database=NEO4J_DB) as s:
        assert s.run("MATCH (t:ResearchTask {artifact_id:$i}) RETURN t.dispatch_merge AS m",
                     i=tb).single()["m"] == "merge_blocked"
    # Left exactly as the session left it: the worktree, the branch with b's commit, no
    # rebase in progress, and main carrying only a's line.
    wt = p / ".worktrees" / "b"
    assert wt.is_dir() and (wt / "shared.txt").read_text() == "base\nfrom b\n"
    assert git(wt, "status", "--porcelain").stdout == ""
    assert _show(p, "main", "shared.txt") == "base\nfrom a\n"
    assert _finished(p, "a")[-1]["merge"]["undeclared_writes"] == ["shared.txt"]


@pytest.mark.parametrize("red", [False, True], ids=["green", "red"])
def test_main_moving_under_the_write_set_reruns_the_gate(tmp_path, neo4j_driver,
                                                         clean_test_db, dc, red):
    """Decision 3: when main moved and the rebase changed a file in the task's write set, the
    gate is rerun in the worktree. Green merges with `regated: true`; red is merge_blocked
    with the overlapping files named and main untouched by the task."""
    p = _project(tmp_path)
    (p / "shared.txt").write_text("one\ntwo\nthree\nfour\nfive\nsix\n")
    git(p, "add", "shared.txt")
    git(p, "commit", "-q", "-m", "shared")
    add_task(p, "a", NONEXCL.format(touches="out/a/"))
    add_task(p, "b", NONEXCL.format(touches="out/b/"))
    a_spec = {"replace": {"shared.txt": ["one\n", "ONE\n"]}, "sleep": 1}
    if red:
        a_spec["write"] = {"RED": "the gate fails while this file exists\n"}
    write_stub(p, {"a": a_spec, "b": {"replace": {"shared.txt": ["six\n", "SIX\n"]},
                                      "sleep": 3}})
    register(p, neo4j_driver, dc, "a", "2026-10-07T00:00:01Z")
    register(p, neo4j_driver, dc, "b", "2026-10-07T00:00:02Z")
    assert _once(p).count("launching") == 2
    _wait_settled(p, neo4j_driver, ["a", "b"])

    fa, fb = _finished(p, "a")[-1], _finished(p, "b")[-1]
    assert fa["outcome"] == "merged" and fa["merge"]["regated"] is False
    gate_log = p / "logs" / "dispatch" / "b.gate.log"
    assert gate_log.is_file() and "test ! -e RED" in gate_log.read_text()
    if red:
        assert fb["outcome"] == "merge_blocked" and fb["merge"]["reason"] == "regate_red"
        assert fb["merge"]["files"] == ["shared.txt"]
        assert task_states(neo4j_driver)["b"] == "blocked"
        assert _show(p, "main", "shared.txt").endswith("six\n")
    else:
        assert fb["outcome"] == "merged" and fb["merge"]["regated"] is True
        assert _show(p, "main", "shared.txt") == "ONE\ntwo\nthree\nfour\nfive\nSIX\n"


# ============================================================================== recovery

def test_a_killed_supervisor_is_marked_by_the_next_pass_and_its_worktree_kept(
        tmp_path, neo4j_driver, clean_test_db, dc):
    """Decision 7: SIGKILL the supervisor and its session mid-run. The next pass finds the
    worktree lease naming a dead PID, blocks the task with `outcome: holder_gone`, keeps the
    worktree, and keeps the lease for the operator's PID-gated reap."""
    p = _project(tmp_path)
    add_task(p, "a", NONEXCL.format(touches="out/a/"))
    write_stub(p, {"a": {"write": {"out/a/1.txt": "partial\n"}, "sleep": 60}})
    ta = register(p, neo4j_driver, dc, "a", "2026-10-07T00:00:01Z")
    assert _once(p).count("launching") == 1
    log = p / "logs" / "dispatch" / "a.log"
    _wait(lambda: log.exists() and "stub cwd: worktree" in log.read_text(), "session start")
    pid = _leases(p)["a"]["body"]["pid"]
    os.killpg(pid, signal.SIGKILL)
    os.waitpid(pid, 0)   # this test process is its parent; in production launchd reaps it

    out = run_cli(p, dispatch_group, ["once"]).output
    assert f"STALE: {ta[:8]} a" in out, out
    assert task_states(neo4j_driver)["a"] == "blocked"
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "holder_gone" and fin["ok"] is False
    assert (p / ".worktrees" / "a" / "out" / "a" / "1.txt").read_text() == "partial\n"
    lease = _leases(p)["a"]
    assert lease["held"] and not lease["alive"]
    assert "STALE" not in run_cli(p, dispatch_group, ["once"]).output  # marked once
    reap = run_cli(p, dispatch_group, ["lease", "reap", "--task", "a"])
    assert json.loads(reap.output)["reaped"] is True


# ========================================================== the declaration, at the pass

def test_an_unparseable_declaration_refuses_with_the_grammar_and_status_shows_waits(
        tmp_path, neo4j_driver, clean_test_db, dc):
    p = _project(tmp_path)
    add_task(p, "bad", "**Exclusive:** no\n**Touches:** neo4J\n")
    register(p, neo4j_driver, dc, "bad", "2026-10-07T00:00:01Z")
    out = _once(p)
    assert "concurrency_undeclared: c10" in out and D.CONCURRENCY_GRAMMAR in out, out
    assert "unknown resource 'neo4J'" in out
    assert task_states(neo4j_driver)["bad"] == "proposed"
    status = json.loads(run_cli(p, dispatch_group, ["status", "--json"]).output)
    assert status["max_parallel"] == PARALLEL["max_parallel"]
    row = status["tasks"][0]
    assert row["criteria"]["c10"]["ok"] is False


def test_status_shows_a_running_worktree_and_why_the_next_task_waits(
        tmp_path, neo4j_driver, clean_test_db, dc):
    p = _project(tmp_path)
    add_task(p, "a", NONEXCL.format(touches="neo4j"))
    add_task(p, "b", NONEXCL.format(touches="neo4j"))
    write_stub(p, {"a": {"sleep": 4}})
    ta = register(p, neo4j_driver, dc, "a", "2026-10-07T00:00:01Z")
    register(p, neo4j_driver, dc, "b", "2026-10-07T00:00:02Z")
    assert _once(p).count("launching") == 1
    text = run_cli(p, dispatch_group, ["status"]).output
    assert "worktree     : a  .worktrees/a on task/a  lease dispatcher:" in text, text
    assert "(alive)" in text
    status = json.loads(run_cli(p, dispatch_group, ["status", "--json"]).output)
    b = next(r for r in status["tasks"] if r["name"] == "b")
    assert b["criteria"]["c6"]["deferred"] == {"reason": "overlap", "with": [ta],
                                               "overlap": ["neo4j"]}
    _wait_settled(p, neo4j_driver, ["a"])
