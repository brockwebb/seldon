"""DISP-002 Part A: a classifier breaker trip does not veto a merge the Stop gate passed (AD-034 ADDENDUM 02).

`cc_tasks/2026-10-19_DISP-002_breaker_does_not_veto_a_green_merge.md`. DISP-001R (eadf9e03) exited 0 with its RESULT
committed and its Stop gate passed, and was blocked anyway because the CLI's breaker had tripped on three refusals
two hours earlier. The finish now merges green work whatever the breaker count, recording the denials as
`breaker_tripped_merged`; a breaker with the gate unpassed still blocks. A pass applies the same rule to a
`classifier_breaker` finish recorded before the change.

Driven end to end through `seldon dispatch once` with the stub CLI of `tests/dispatch_scaffold.py`: the stub runs the
launch's own PermissionDenied hook three times, declares Part A, runs the launch's own Stop hook, then prints the
CLI's breaker text.
"""
from __future__ import annotations

import pytest

from seldon.commands import dispatch_worktree as W
from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core import stations as Q
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    NEO4J_DB, RESEARCH_YAML, add_task, git, make_project, register, run_cli, write_stub,
)

BREAKER = "Error: Agent aborted: too many classifier denials in headless mode"
PARTS = "**Parts:** A 1.0.\n\n## Part A: the work\n\nAcceptance:\n- `check: test -f out/a.txt`\n"
STEM = "disp002_breaker"
DENIALS = ["blocked 0", "blocked 1", "blocked 2"]


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
    """By id, not by name: the test database is shared, so a name may recur across test files."""
    with neo4j_driver.session(database=NEO4J_DB) as s:
        return s.run("MATCH (t:ResearchTask {artifact_id: $i}) RETURN t.state AS s", i=task_id).single()["s"]


def _breaker_session(p, neo4j_driver, dc, green: bool):
    add_task(p, STEM, PARTS)
    task_id = register(p, neo4j_driver, dc, STEM, "2026-10-19T00:00:00Z")
    write_stub(p, {STEM: {"write": {"out/a.txt": "a\n"} if green else {}, "classifier_blocks": 3,
                          "part_complete": ["A"], "stop_hook": True, "print": BREAKER, "exit": 0}})
    return task_id


def _classifier_stops(p):
    return [s for s in _payloads(p, Q.EVENT_SESSION_STOP) if s.get("station") == "classifier"]


@pytest.mark.usefixtures("neo4j_available")
def test_a_breaker_trip_with_green_work_is_merged_and_completed(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path, dispatch_extra={"permission_mode": "auto", "notify": "true"})
    tid = _breaker_session(p, neo4j_driver, dc, green=True)
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output

    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert f"notify: sent ({fin['task_id'][:8]} {W.BREAKER_MERGED})" in res.output, res.output
    assert fin["exit_code"] == 0 and fin["result_present"] is True and fin["stop_gate"]["verdict"] == "pass"
    assert fin["classifier_blocks"] == 3
    assert fin["outcome"] == "merged", fin
    assert fin["breaker"] == {"outcome": W.BREAKER_MERGED, "blocks": 3, "denials": DENIALS}
    assert _state(neo4j_driver, tid) == "completed"
    assert git(p, "show", "main:out/a.txt").stdout == "a\n"
    assert not _classifier_stops(p), "green work is not a line stop"


@pytest.mark.usefixtures("neo4j_available")
def test_a_breaker_trip_with_the_gate_unpassed_stays_blocked(tmp_path, neo4j_driver, dc):
    """The negative control: the breaker still stops work its own gate did not pass."""
    p = make_project(tmp_path, dispatch_extra={"permission_mode": "auto"})
    tid = _breaker_session(p, neo4j_driver, dc, green=False)
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0

    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["stop_gate"]["verdict"] == "block"
    assert fin["outcome"] == "classifier_breaker" and "breaker" not in fin
    assert _state(neo4j_driver, tid) == "blocked"
    (stop,) = _classifier_stops(p)
    assert stop["reason"] == "classifier_breaker" and stop["blocks"] == 3
    assert git(p, "show", f"main:cc_tasks/{STEM}_RESULT.md", check=False).returncode != 0


@pytest.mark.usefixtures("neo4j_available")
def test_a_green_breaker_finish_recorded_before_the_ruling_is_merged_by_the_next_pass(tmp_path, neo4j_driver, dc,
                                                                                      monkeypatch):
    """DISP-001R's case on disk: blocked as `classifier_breaker` with exit 0, a RESULT and a passed gate. The next
    pass merges it, completes it and removes its worktree; a pass after that finds nothing to do."""
    p = make_project(tmp_path, dispatch_extra={"permission_mode": "auto"})
    tid = _breaker_session(p, neo4j_driver, dc, green=True)
    with monkeypatch.context() as m:
        m.setattr(W, "is_green", lambda *a, **k: False)          # the finish as it stood before DISP-002
        assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    assert _payloads(p, D.EVENT_FINISHED)[-1]["outcome"] == "classifier_breaker"
    assert _state(neo4j_driver, tid) == "blocked"
    branch = _payloads(p, D.EVENT_FINISHED)[-1]["branch"]

    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    assert "remerge:" in res.output
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merged", fin
    assert fin["breaker"]["outcome"] == W.BREAKER_MERGED and fin["breaker"]["remerged"] is True
    assert fin["breaker"]["denials"] == DENIALS
    assert _state(neo4j_driver, tid) == "completed"
    assert git(p, "merge-base", "--is-ancestor", branch, "main", check=False).returncode == 0
    assert not (p / fin["worktree"]).exists()

    n = len(_payloads(p, D.EVENT_FINISHED))
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    assert len(_payloads(p, D.EVENT_FINISHED)) == n, "a task is reconsidered once"


def test_green_needs_a_gate_that_ran_and_passed():
    assert W.is_green(0, True, {"verdict": "pass"})
    assert not W.is_green(0, True, {"verdict": None, "passed": True}), "no gate ran: not evidence"
    assert not W.is_green(0, True, {"verdict": "block"})
    assert not W.is_green(1, True, {"verdict": "pass"})
    assert not W.is_green(0, False, {"verdict": "pass"})
