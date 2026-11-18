"""SEL-040 Part B: a session its transport cut off is resumed by the dispatcher, not blocked for a person.

`cc_tasks/2026-11-16_SEL-040_..._premise_can_wait_for_launch.md` Part B, AD-034-R21..R23. The fixture
`tests/fixtures/sel040/hb189_log_tail.jsonl` is the end of hazbrief HB-189's real session stream (2026-11-16), cut by
`docs/evidence/sel040/cut_fixture.py` with every tool output, thinking block and prompt elided: its last model turns,
the CLI's ten `api_retry` records (attempt 10 of 10, no HTTP status), its synthetic "API Error ... (ENOTFOUND)" and
its `result` record. The stub CLI prints it as the session's own end, after committing work and no RESULT, so the
dispatcher's finish reads exactly what it read for HB-189.

Before SEL-040 that finish recorded `stop_gate_unpassed` (`test_the_hb189_tail_was_blocked_for_a_person`, run on
the pre-change code; `docs/evidence/sel040/reproduction.txt`).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from seldon.core import dispatch as D
from seldon.core import interruption as INT
from seldon.core.events import read_events
from tests.dispatch_scaffold import (
    RESEARCH_YAML, add_task, git, make_project, register, run_cli, task_states, write_stub,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sel040" / "hb189_log_tail.jsonl"
PARTS = "**Parts:** A 1.0.\n\n## Part A: the work\n\nAcceptance:\n- `check: test -f out/a.txt`\n"
SETTINGS = INT.load_settings(None)
NO_SLEEP = {"read": True, "sleeps": [], "error": None}
LID = {"read": True, "sleeps": [{"at": "2026-11-16T10:37:00Z", "what": "Entering Sleep state due to 'Clamshell "
                                                                       "Sleep'"}], "error": None}


def _lines():
    return FIXTURE.read_text(encoding="utf-8").splitlines()


@pytest.fixture
def dc():
    from seldon.domain.loader import load_domain_config
    return load_domain_config(RESEARCH_YAML)


def _finishes(p):
    return [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_FINISHED]


def _launches(p):
    return [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_LAUNCHED]


def _cut_off(p, n=1):
    """The stub's spec for a session that commits work, declares Part A, and ends as HB-189 ended."""
    return {"a": {"write": {f"out/work{n}.txt": f"work {n}\n"}, "work_commit": f"a: work {n}", "result": False,
                  "part_complete": ["A"], "tail": str(FIXTURE), "exit": 1, "worktree_name": "a"}}


def _no_host_log(monkeypatch):
    # The real host's power log is not this test's evidence; the fixture's own records are.
    monkeypatch.setattr(INT, "host_sleeps", lambda settings, start, end, run=None: NO_SLEEP)


@pytest.mark.usefixtures("neo4j_available")
def test_the_hb189_tail_is_interrupted_not_blocked_for_a_person(tmp_path, neo4j_driver, dc, monkeypatch):
    """The reproduction, now inverted: the finish classes the HB-189 tail `interrupted`, names its evidence and the
    tokens it carries, and blocks it with the reason the automatic redrive answers."""
    from seldon.commands.dispatch import dispatch_group
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _no_host_log(monkeypatch)
    p = make_project(tmp_path)
    add_task(p, "a", PARTS)
    register(p, neo4j_driver, dc, "a", "2026-11-16T00:00:00Z")
    write_stub(p, _cut_off(p))
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    fin = _finishes(p)[-1]
    assert fin["outcome"] == INT.INTERRUPTED, fin
    assert fin["failure"] == INT.INTERRUPTED
    inter = fin["interruption"]
    assert inter["evidence"] == ["transport_error", "retries_exhausted"], inter
    assert "ENOTFOUND" in inter["tail"]["transport_error"]
    assert inter["resumes_before"] == 0 and inter["carried_tokens"] > 0
    assert task_states(neo4j_driver)["a"] == "blocked"
    assert (p / ".claude" / "worktrees" / "a").is_dir(), "the work is kept for the resume"


@pytest.mark.usefixtures("neo4j_available")
def test_an_interrupted_task_resumes_in_its_kept_worktree_once_the_api_answers(tmp_path, neo4j_driver, dc,
                                                                               monkeypatch):
    """No person: the pass that finds the API unreachable leaves the task blocked and says why; the pass that finds
    it answering redrives it, relaunches it in its kept worktree with the interruption stated, and merges it."""
    from seldon.commands.dispatch import dispatch_group
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _no_host_log(monkeypatch)
    p = make_project(tmp_path)
    add_task(p, "a", PARTS)
    register(p, neo4j_driver, dc, "a", "2026-11-16T00:00:00Z")
    write_stub(p, _cut_off(p))
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    work_sha = git(p, "rev-parse", "worktree-a").stdout.strip()

    monkeypatch.setattr(INT, "probe", lambda settings, connect=None: {"ok": False, "host": "api", "port": 443,
                                                                       "error": "OSError: no route"})
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    assert task_states(neo4j_driver)["a"] == "blocked", "the API did not answer: the task waits"
    probes = [e["payload"] for e in read_events(p) if e["event_type"] == INT.EVENT_PROBE]
    assert probes and probes[-1]["ok"] is False and probes[-1]["task_id"]

    monkeypatch.setattr(INT, "probe", lambda settings, connect=None: {"ok": True, "host": "api", "port": 443,
                                                                       "error": None})
    write_stub(p, {"a": {"write": {"out/a.txt": "a\n"}, "part_complete": ["A"], "stop_hook": True}})
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    redrives = [e["payload"] for e in read_events(p) if e["event_type"] == "dispatch_redrive"]
    assert redrives and redrives[-1]["stop_reason"] == INT.INTERRUPTED and redrives[-1]["automatic"] is True
    launch = _launches(p)[-1]
    assert launch["resume"]["worktree"] == ".claude/worktrees/a" and launch["resume"]["last_commit"] == work_sha
    assert launch["resume"]["prior_tokens"] == _finishes(p)[-2]["interruption"]["carried_tokens"]
    assert "--worktree a" in launch["command"] and "RESUMED (AD-034-R21)" in launch["command"]
    assert work_sha[:12] in launch["command"]
    fin = _finishes(p)[-1]
    assert fin["outcome"] == "merged", fin
    assert fin["worktree"] == ".claude/worktrees/a" and fin["base"] == _finishes(p)[-2]["base"]
    assert task_states(neo4j_driver)["a"] == "completed"
    assert git(p, "show", "main:out/work1.txt").stdout == "work 1\n", "the interrupted session's work merged"


@pytest.mark.usefixtures("neo4j_available")
def test_a_third_interruption_blocks_with_interrupted_thrice(tmp_path, neo4j_driver, dc, monkeypatch):
    from seldon.commands.dispatch import dispatch_group
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _no_host_log(monkeypatch)
    monkeypatch.setattr(INT, "probe", lambda settings, connect=None: {"ok": True, "host": "api", "port": 443,
                                                                       "error": None})
    p = make_project(tmp_path)
    add_task(p, "a", PARTS)
    register(p, neo4j_driver, dc, "a", "2026-11-16T00:00:00Z")
    outcomes = []
    for n in (1, 2, 3, 4):
        write_stub(p, _cut_off(p, n))
        assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
        outcomes.append(_finishes(p)[-1]["outcome"])
        if outcomes[-1] == INT.INTERRUPTED_THRICE:
            break
    assert outcomes == [INT.INTERRUPTED, INT.INTERRUPTED, INT.INTERRUPTED_THRICE], outcomes
    assert task_states(neo4j_driver)["a"] == "blocked"
    write_stub(p, _cut_off(p, 9))
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    assert task_states(neo4j_driver)["a"] == "blocked", "a third interruption waits for a person"
    assert len(_launches(p)) == 3


@pytest.mark.usefixtures("neo4j_available")
def test_a_session_that_committed_its_result_is_never_redriven(tmp_path, neo4j_driver, dc, monkeypatch):
    """The HB-189 tail after a committed RESULT: the work is done; the regate (AD-034-R10) answers it, not a
    resume."""
    from seldon.commands.dispatch import dispatch_group
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _no_host_log(monkeypatch)
    p = make_project(tmp_path)
    add_task(p, "a", PARTS)
    register(p, neo4j_driver, dc, "a", "2026-11-16T00:00:00Z")
    write_stub(p, {"a": {"write": {"out/b.txt": "b\n"}, "part_complete": ["A"], "tail": str(FIXTURE), "exit": 1,
                         "worktree_name": "a"}})
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    fin = _finishes(p)[-1]
    assert fin["outcome"] == "stop_gate_unpassed", fin
    assert fin["interruption"]["excluded"] == "result_committed"


# ------------------------------------------------------------------------------------------- the classifier alone

GATE_NONE = {"passed": False, "verdict": None, "runs": 0, "why": "Parts declared and no stop gate ran"}
END = datetime(2026, 11, 16, 11, 38, tzinfo=timezone.utc)


def test_the_fixture_tail_reads_as_the_cli_wrote_it():
    tail = INT.read_tail(_lines(), SETTINGS)
    assert tail["last_model_at"] == "2026-11-16T10:36:44.301Z"
    assert len(tail["retries"]) == 10 and tail["retries_exhausted"] is True
    assert tail["transport_error"].startswith("API Error: Can't reach the API server")
    assert tail["result_record"] is True


def test_a_closed_lid_is_named_when_the_host_log_shows_it():
    seen = {}

    def sleeps(start, end):
        seen["window"] = (start, end)
        return LID
    out = INT.classify(lines=_lines(), exit_code=1, result_committed=False, gate=GATE_NONE, stopped=[],
                       settings=SETTINGS, ended_at=END, sleeps=sleeps)
    assert out["interrupted"] and out["evidence"] == ["transport_error", "retries_exhausted", "host_slept"]
    assert seen["window"][0] == datetime(2026, 11, 16, 10, 36, 44, 301000, tzinfo=timezone.utc)


@pytest.mark.parametrize("gate,stopped,committed,why", [
    ({"passed": False, "verdict": "no_progress", "runs": 2}, [], False, "stop_gate_no_progress"),
    ({"passed": False, "verdict": "ceiling", "runs": 1}, [], False, "stop_gate_ceiling"),
    (GATE_NONE, [{"reason": "spend_ceiling"}], False, "stopped: spend_ceiling"),
    (GATE_NONE, [], True, "result_committed"),
], ids=["gate-no-progress", "gate-ceiling", "dispatcher-stop", "result"])
def test_a_session_that_ran_to_its_gate_or_was_stopped_is_not_interrupted(gate, stopped, committed, why):
    out = INT.classify(lines=_lines(), exit_code=1, result_committed=committed, gate=gate, stopped=stopped,
                       settings=SETTINGS, ended_at=END, sleeps=lambda s, e: LID)
    assert not out["interrupted"] and out["excluded"] == why


def test_a_gate_that_refused_and_kept_the_session_working_does_not_hide_a_later_cut():
    out = INT.classify(lines=_lines(), exit_code=1, result_committed=False,
                       gate={"passed": False, "verdict": "block", "runs": 1}, stopped=[], settings=SETTINGS,
                       ended_at=END, sleeps=lambda s, e: NO_SLEEP)
    assert out["interrupted"]


def _killed_lines():
    return [ln for ln in _lines() if '"api_retry"' not in ln and '"<synthetic>"' not in ln
            and '"type": "result"' not in ln]


def test_a_killed_session_is_interrupted_only_with_the_host_log_beside_it():
    lines = _killed_lines()
    alone = INT.classify(lines=lines, exit_code=-15, result_committed=False, gate=GATE_NONE, stopped=[],
                         settings=SETTINGS, ended_at=END, sleeps=lambda s, e: NO_SLEEP)
    assert not alone["interrupted"] and "look alike" in alone["undecided"]
    slept = INT.classify(lines=lines, exit_code=-15, result_committed=False, gate=GATE_NONE, stopped=[],
                         settings=SETTINGS, ended_at=END, sleeps=lambda s, e: LID)
    assert slept["interrupted"] and slept["evidence"] == ["host_slept", "killed_no_result"]


def test_an_ordinary_failure_with_no_transport_evidence_is_not_interrupted():
    lines = _killed_lines()
    out = INT.classify(lines=lines, exit_code=1, result_committed=False, gate=GATE_NONE, stopped=[],
                       settings=SETTINGS, ended_at=END, sleeps=lambda s, e: LID)
    assert not out["interrupted"] and out["evidence"] == [] and out["host"] is None


def test_a_client_refusal_is_not_a_transport_failure():
    lines = [json.dumps({"type": "assistant", "timestamp": "2026-11-16T10:00:00Z",
                         "message": {"id": "m", "model": "claude-opus-5-5", "content": []}})]
    lines += [json.dumps({"type": "system", "subtype": "api_retry", "attempt": n, "max_retries": 3,
                          "error_status": 401, "error": "authentication_error"}) for n in (1, 2, 3)]
    out = INT.classify(lines=lines, exit_code=1, result_committed=False, gate=GATE_NONE, stopped=[],
                       settings=SETTINGS, ended_at=END, sleeps=lambda s, e: NO_SLEEP)
    assert not out["interrupted"]


def test_the_host_power_log_is_parsed_for_sleeps_in_the_window():
    log = ("2026-11-16 05:36:00 -0500 Wake                	Wake from Normal Sleep\n"
           "2026-11-16 05:37:00 -0500 Sleep               	Entering Sleep state due to 'Clamshell Sleep':TCP\n"
           "2026-11-16 05:37:02 -0500 Wake Requests       	[process=dasd]\n"
           "2026-11-16 07:00:00 -0500 Sleep               	Entering Sleep state due to 'Maintenance Sleep'\n")

    class R:
        returncode, stdout, stderr = 0, log, ""
    out = INT.host_sleeps(SETTINGS, datetime(2026, 11, 16, 10, 36, 44, tzinfo=timezone.utc), END,
                          run=lambda *a, **k: R)
    assert out["read"] and [s["at"] for s in out["sleeps"]] == ["2026-11-16T10:37:00Z"]
    assert "Clamshell Sleep" in out["sleeps"][0]["what"]


def test_the_probe_reports_an_unreachable_host_and_never_raises():
    def refuse(addr, timeout):
        raise OSError("[Errno 8] nodename nor servname provided")
    assert INT.probe(SETTINGS, connect=refuse)["ok"] is False

    class C:
        def close(self):
            pass
    assert INT.probe(SETTINGS, connect=lambda addr, timeout: C())["ok"] is True


def test_the_config_block_refuses_what_it_cannot_read():
    for bad in ({"probe_port": 0}, {"transport_patterns": []}, {"nope": 1}, {"transport_patterns": ["("]},
                {"host_sleep_command": "pmset"}):
        with pytest.raises(INT.InterruptionConfigError):
            INT.load_settings(bad)


def test_a_resumed_launch_counts_the_interrupted_sessions_tokens(tmp_path):
    """AD-034-R22: tokens already spent count toward the task's cap, at the gate, the inspector and part-complete."""
    from seldon.core import stations as Q
    log = tmp_path / "t.log"
    msg = {"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 100, "output_tokens": 0}}}
    log.write_text("=== 2026-11-17T00:00:00Z | dispatch | claude\n" + json.dumps(msg) + "\n", encoding="utf-8")
    assert Q.launch_tokens(log, {}) == 100
    assert Q.launch_tokens(log, {"resume": {"prior_tokens": 900}}) == 1000


def test_no_resume_without_a_redrive_or_without_the_kept_tree(tmp_path):
    fin = {"event_id": "f1", "event_type": "dispatch_finished", "timestamp": "2026-11-17T01:00:00Z",
           "payload": {"task_id": "t", "outcome": INT.INTERRUPTED, "worktree": ".claude/worktrees/gone",
                       "branch": "worktree-gone", "base": "abc"}}
    redrive = {"event_type": "dispatch_redrive", "timestamp": "2026-11-17T02:00:00Z", "payload": {"task_id": "t"}}
    assert INT.resume_plan(tmp_path, [fin], "t") is None, "not redriven: no resume"
    assert INT.resume_plan(tmp_path, [fin, redrive], "t") is None, "the kept tree is gone: a fresh launch"
