"""FRICTION-002 Part C: the Stop hook is the completion gate; the milestone station reads its record.

`cc_tasks/2026-10-17_FRICTION-002_vendor_isolation_replaces_hand_built_plumbing.md` Part C. Every dispatched session
is launched with a `Stop` hook, `seldon dispatch stop-gate`, which runs the `check:` criteria of each Part the session
declared complete and, while one fails under the token ceiling, prints the CLI's block decision so the session keeps
working. At the ceiling it lets the session end and writes a hard stop. The milestone station runs no check of its
own: it answers a `part_complete` from the gate's `stop_gate` record.

The hook is driven here as the CLI drives it: the command line from the launch settings, the hook's JSON on stdin,
and `SELDON_SESSION_ID` in the environment. No model call, no Neo4j.
"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from seldon.commands import dispatch as S
from seldon.core import dispatch as D
from seldon.core import stations as Q
from seldon.core.events import append_event, make_event, read_events
from tests.dispatch_scaffold import (
    RESEARCH_YAML, SELDON_REPO, add_task, git, make_project, register, run_cli, task_states, write_stub,
)

CHILD = "11111111-2222-3333-4444-555555555555"

TASK = """# T

**Date:** 2026-10-17
**Spend:** est. 1000 tokens. **Network:** none.
**Parts:** A 0.5, B 0.5.

## Part A: make the file

Acceptance:
- `check: test -f done_a.txt`

## Part B: never declared here

Acceptance:
- `check: false`
"""


@pytest.fixture
def project(tmp_path):
    p = make_project(tmp_path)
    (p / "cc_tasks" / "t.md").write_text(TASK, encoding="utf-8")
    (p / "logs" / "dispatch").mkdir(parents=True)
    (p / "logs" / "dispatch" / "t.log").write_text("", encoding="utf-8")
    append_event(p, make_event(D.EVENT_LAUNCHED, "dispatcher", "accepted",
                               {"task_id": "task-0001-t", "source_file": "cc_tasks/t.md", "child_session_id": CHILD,
                                "log_path": "logs/dispatch/t.log", "launched_at": "2026-10-17T00:00:00Z",
                                "permission_mode": "auto"}))
    return p


def _part_complete(p, part="A"):
    return append_event(p, make_event(Q.EVENT_PART_COMPLETE, "cc", "accepted",
                                      {"task_id": "task-0001-t", "part": part, "planned_share": 0.5, "tokens": 10,
                                       "cwd": str(p), "branch": "main"}))


def _usage(p, tokens):
    msg = {"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": tokens, "output_tokens": 0}}}
    with (p / "logs" / "dispatch" / "t.log").open("a", encoding="utf-8") as fh:
        fh.write("=== 2026-10-17T00:00:00Z | dispatch | claude\n" + json.dumps(msg) + "\n")


def _hook_command(p) -> list:
    """The Stop hook's command exactly as the launch settings install it."""
    settings = S._session_settings(p, D.load_dispatch_config(p))
    cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    return shlex.split(cmd)


def _stop(p, cwd=None, session=CHILD):
    """Run the Stop hook as the CLI runs it. Returns (exit code, decision or None)."""
    env = {"PATH": "/usr/bin:/bin", "SELDON_SESSION_ID": session, "PYTHONPATH": str(SELDON_REPO), "HOME": str(p)}
    r = subprocess.run(_hook_command(p), input=json.dumps({"hook_event_name": "Stop", "cwd": str(cwd or p),
                                                           "stop_hook_active": False, "session_id": "x"}),
                       capture_output=True, text=True, env=env, cwd=cwd or p)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def _records(p, kind):
    return [e for e in read_events(p) if e["event_type"] == kind]


def test_the_launch_installs_the_stop_gate_hook(project):
    settings = S._session_settings(project, D.load_dispatch_config(project))
    hook = settings["hooks"]["Stop"][0]["hooks"][0]
    assert hook["type"] == "command" and "dispatch stop-gate --project" in hook["command"]
    assert " -P -m seldon " in hook["command"], "the gate must not import the session's branch code"
    assert hook["timeout"] == Q.STATIONS_DEFAULTS["stop_gate_timeout_s"]


def test_a_failing_check_keeps_the_session_alive_and_the_record_names_it(project):
    _part_complete(project, "A")
    decision = _stop(project)
    assert decision is not None and decision["decision"] == "block", decision
    assert "test -f done_a.txt" in decision["reason"]
    gate = _records(project, Q.EVENT_STOP_GATE)[-1]["payload"]
    assert gate["verdict"] == "block" and gate["failed"] == ["test -f done_a.txt"]
    assert [p["part"] for p in gate["parts"]] == ["A"], "only declared Parts are checked"
    assert not _records(project, Q.EVENT_SESSION_STOP)


def test_a_passing_session_ends_on_its_first_stop(project):
    """The negative control (AD-038-R6): a correct session is not held."""
    _part_complete(project, "A")
    (project / "done_a.txt").write_text("x", encoding="utf-8")
    assert _stop(project) is None
    gate = _records(project, Q.EVENT_STOP_GATE)[-1]["payload"]
    assert gate["verdict"] == "pass" and gate["failed"] == []
    assert len(_records(project, Q.EVENT_STOP_GATE)) == 1


def test_the_ceiling_ends_a_session_with_failing_checks_and_writes_a_hard_stop(project):
    _part_complete(project, "A")
    _usage(project, 1300)          # estimate 1000 x spend_ceiling_factor 1.2 = 1200
    assert _stop(project) is None
    gate = _records(project, Q.EVENT_STOP_GATE)[-1]["payload"]
    assert gate["verdict"] == "ceiling" and gate["tokens"] == 1300 and gate["ceiling"] == 1200
    stop = _records(project, Q.EVENT_SESSION_STOP)[-1]
    assert stop["payload"]["kind"] == "hard" and stop["payload"]["reason"] == "spend_ceiling"
    assert stop["payload"]["failed"] == ["test -f done_a.txt"]
    halted = _records(project, Q.EVENT_ANDON_HALTED)[-1]["payload"]
    assert halted["stop_event_id"] == stop["event_id"], "the gate answers its own stop so nothing is reaped"


def test_a_session_the_dispatcher_did_not_launch_ends_untouched(project):
    _part_complete(project, "A")
    assert _stop(project, session="not-a-dispatched-session") is None
    assert not _records(project, Q.EVENT_STOP_GATE)


def test_the_milestone_station_reads_the_gate_record_and_runs_no_check(project):
    _part_complete(project, "A")
    events = read_events(project)

    def no_check(*a, **k):
        raise AssertionError("the milestone station ran a check of its own")
    scfg = Q.load_stations_config({})
    emitted = []
    out = Q.inspect(project, "task-0001-t", events, scfg, 300, lambda t, pl: emitted.append((t, pl)), run=no_check)
    assert out["milestones"] == [], "no milestone before a Stop has run the Part's checks"

    _stop(project)                                   # fails: done_a.txt is absent
    out = Q.inspect(project, "task-0001-t", read_events(project), scfg, 300,
                    lambda t, pl: emitted.append((t, pl)), run=no_check)
    (m,) = out["milestones"]
    assert m["checks_source"] == "stop_gate" and m["defect"] is True
    assert m["checks"][0]["command"] == "test -f done_a.txt"
    assert not out["stops"], "a failure the gate is holding the session on is not also a line stop"


PARTS = "**Parts:** A 1.0.\n\n## Part A: the work\n\nAcceptance:\n- `check: test -f out/a.txt`\n"


@pytest.fixture
def dc():
    from seldon.domain.loader import load_domain_config
    return load_domain_config(RESEARCH_YAML)


@pytest.mark.usefixtures("neo4j_available")
@pytest.mark.parametrize("writes,merged", [({"out/a.txt": "a\n"}, True), ({}, False)], ids=["passing", "failing"])
def test_a_session_let_go_with_its_gate_unpassed_is_never_merged(tmp_path, neo4j_driver, dc, monkeypatch, writes,
                                                                merged):
    """End to end through the dispatcher: the session declares Part A and tries to end; the Stop hook runs the
    Part's check in the worktree. Passing, the branch merges. Failing, the CLI would refuse the end until its block
    cap (observed: 9) lets the session go; the finish then reads the gate's last verdict and keeps the branch."""
    from seldon.commands.dispatch import dispatch_group
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = make_project(tmp_path)
    add_task(p, "a", PARTS)
    register(p, neo4j_driver, dc, "a", "2026-10-17T00:00:00Z")
    write_stub(p, {"a": {"write": writes, "part_complete": ["A"], "stop_hook": True, "worktree_name": "a"}})
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    fin = [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_FINISHED][-1]
    gates = [e["payload"] for e in read_events(p) if e["event_type"] == Q.EVENT_STOP_GATE]
    assert gates and Path(gates[-1]["cwd"]).resolve() == (p / ".claude" / "worktrees" / "a").resolve()
    if merged:
        assert gates[-1]["verdict"] == "pass" and fin["outcome"] == "merged", fin
        assert task_states(neo4j_driver)["a"] == "completed"
    else:
        assert gates[-1]["verdict"] == "block" and fin["outcome"] == "stop_gate_unpassed", fin
        assert task_states(neo4j_driver)["a"] == "blocked"
        kept = [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_WORKTREE_KEPT]
        assert kept and kept[-1]["reason"] == "stop_gate_unpassed: block: test -f out/a.txt", kept
        assert git(p, "show", "main:cc_tasks/a_RESULT.md", check=False).returncode != 0
