"""DISP-001R Part B: the spend ceiling has a measured floor; a hard stop waits for a tool boundary; the reap reads
liveness.

`cc_tasks/2026-10-19_DISP-001R_worktree_name_and_spend_floor.md` Part B, AD-037 ADDENDUM 01. DISP-001 was reaped
five minutes after launch: `session_tokens` read 134,746 against 80,000 x 1.2 (`session_stop` 04926773), and the
reap (`andon_reaped` d787bf17) fired one poll later while the session was inside a five-minute pytest call with no
boundary at which to read the stop. No Neo4j, no model call (tests/stations_scaffold.py).
"""
from __future__ import annotations

import json
import os
import time

from click.testing import CliRunner

from seldon.cli import main
from seldon.core import stations as S
from seldon.core.events import append_event, make_event
from tests import stations_scaffold as F

#: DISP-001's reading at its first inspection, and the estimate it was stopped against.
DISP001_TOKENS = 134_746
DISP001_ESTIMATE = "0.08M"


def _low_estimate(p) -> None:
    task = p / "cc_tasks" / f"{F.STEM}.md"
    task.write_text(task.read_text().replace("est. 1M", f"est. {DISP001_ESTIMATE}"))


def _history(p, readings: list) -> None:
    """Finished launches whose logs read `readings[k]` at their first inspection, plus a later message that must
    not count (it lands after the first inspection's window)."""
    for k, tokens in enumerate(readings):
        at = F.ago(7200 + 600 * k)
        sid = f"hist-{k}"
        log = f"logs/dispatch/hist{k}.log"
        ev = make_event("dispatch_launched", "dispatcher", "accepted",
                        {"task_id": f"hist-task-{k}", "source_file": f"cc_tasks/hist{k}.md", "child_session_id": sid,
                         "log_path": log, "launched_at": F._iso(at)})
        ev["timestamp"] = F._iso(at)
        append_event(p, ev)
        head = at + F.timedelta(seconds=1)
        lines = [f"=== {F._iso(head)} | dispatch | claude -p ...",
                 json.dumps({"type": "assistant", "timestamp": F._iso(head + F.timedelta(seconds=60)),
                             "message": {"id": "a", "usage": {"input_tokens": tokens}}}),
                 json.dumps({"type": "assistant", "timestamp": F._iso(head + F.timedelta(seconds=900)),
                             "message": {"id": "b", "usage": {"input_tokens": 10_000_000}}})]
        (p / log).write_text("\n".join(lines) + "\n", encoding="utf-8")
        fin = make_event("dispatch_finished", "dispatcher", "accepted",
                         {"task_id": f"hist-task-{k}", "child_session_id": sid, "outcome": "merged"})
        fin["timestamp"] = F._iso(at + F.timedelta(seconds=1200))
        append_event(p, fin)


def _spend_stops(p) -> list:
    return [e for e in F.events(p, S.EVENT_SESSION_STOP) if e["payload"]["reason"] == "spend_ceiling"]


def test_an_estimate_below_the_floor_does_not_stop_at_the_first_inspection(tmp_path):
    p = F.make_project(tmp_path)
    _low_estimate(p)
    _history(p, [131_243, 127_741, 163_760])
    F.launch(p, at=F.ago(310))
    F.write_log(p, DISP001_TOKENS)
    out = S.inspect(p, F.TASK_ID, F.events(p), S.load_stations_config({}), 300, F.emitter(p))
    assert _spend_stops(p) == [], out["stops"]
    # The floor is the median of the three first-inspection readings, and it is the binding term.
    assert out["ceiling"]["binding"] == "floor" and out["ceiling"]["floor"]["value"] == 131_243
    assert out["ceiling"]["floor"]["n"] == 3 and out["ceiling"]["ceiling"] == int(131_243 * 1.2)


def test_with_no_measured_floor_the_estimate_alone_still_stops_disp001(tmp_path):
    """The negative control (AD-038-R6): with no finished launch to measure, the ceiling is the estimate's, and
    DISP-001's reading is stopped as it was."""
    p = F.make_project(tmp_path)
    _low_estimate(p)
    F.launch(p, at=F.ago(310))
    F.write_log(p, DISP001_TOKENS)
    S.inspect(p, F.TASK_ID, F.events(p), S.load_stations_config({}), 300, F.emitter(p))
    (stop,) = _spend_stops(p)
    assert stop["payload"]["reading"]["binding"] == "estimate" and stop["payload"]["reading"]["ceiling"] == 96_000


def test_a_reading_above_the_floor_ceiling_records_the_floor_in_its_stop(tmp_path):
    p = F.make_project(tmp_path)
    _low_estimate(p)
    _history(p, [100_000])
    F.launch(p, at=F.ago(310))
    F.write_log(p, 200_000)
    S.inspect(p, F.TASK_ID, F.events(p), S.load_stations_config({}), 300, F.emitter(p))
    (stop,) = _spend_stops(p)
    reading = stop["payload"]["reading"]
    assert reading["binding"] == "floor" and reading["floor"]["value"] == 100_000 and reading["tokens"] == 200_000


def _gate(p, monkeypatch, tool="Bash"):
    monkeypatch.chdir(p)
    monkeypatch.setenv("SELDON_SESSION_ID", "child-1")
    return CliRunner().invoke(main, ["dispatch", "tool-gate", "--project", str(p)],
                              input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                                                "tool_input": {"command": "python -m pytest"}}))


def test_a_hard_stop_on_the_ledger_makes_the_next_tool_call_refuse_with_its_reason(tmp_path, monkeypatch):
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(600))
    r = _gate(p, monkeypatch)
    assert r.exit_code == 0 and r.output.strip() == "", "no stop written: the call proceeds"
    stop = F.record(p, S.EVENT_SESSION_STOP, {"station": "dispatcher", "kind": "hard", "reason": "spend_ceiling",
                                             "by": "dispatcher", "reading": {"tokens": 134_746, "ceiling": 96_000}})
    r = _gate(p, monkeypatch)
    assert r.exit_code == 0, r.output
    decision = json.loads(r.output)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse" and decision["permissionDecision"] == "deny"
    assert "spend_ceiling" in decision["permissionDecisionReason"]
    (halted,) = F.events(p, S.EVENT_ANDON_HALTED)
    assert halted["payload"]["stop_event_id"] == stop["event_id"] and halted["payload"]["at"] == "tool boundary"
    assert halted["payload"]["tool_name"] == "Bash"
    # Answered: the session may now write its RESULT; the stop is not delivered twice.
    r = _gate(p, monkeypatch, tool="Write")
    assert r.exit_code == 0 and r.output.strip() == ""


def test_an_andon_stop_is_not_delivered_at_the_tool_boundary(tmp_path, monkeypatch):
    """Only a hard stop is enforced at a tool call; an andon or line stop is read at the session's Part boundary."""
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(600))
    F.record(p, S.EVENT_SESSION_STOP, {"station": "operator", "kind": "andon", "reason": "look at this"})
    r = _gate(p, monkeypatch)
    assert r.exit_code == 0 and r.output.strip() == ""


def test_a_session_the_dispatcher_did_not_launch_is_untouched(tmp_path, monkeypatch):
    p = F.make_project(tmp_path)
    F.launch(p, session_id="someone-else", at=F.ago(600))
    F.record(p, S.EVENT_SESSION_STOP, {"station": "dispatcher", "kind": "hard", "reason": "spend_ceiling"})
    r = _gate(p, monkeypatch)
    assert r.exit_code == 0 and r.output.strip() == ""


def _hard_stop_aged(p, wait_s):
    F.launch(p, at=F.ago(3600))
    F.write_log(p, 1)
    stop = F.record(p, S.EVENT_SESSION_STOP, {"station": "dispatcher", "kind": "hard", "reason": "spend_ceiling"},
                    at=F.ago(wait_s + 60))
    return stop


def _log_grew(p, seconds_ago):
    log = p / "logs" / "dispatch" / f"{F.STEM}.log"
    t = time.time() - seconds_ago
    os.utime(log, (t, t))


def test_a_hard_stop_past_the_interval_with_a_log_that_grew_10s_ago_is_not_reaped(tmp_path):
    p = F.make_project(tmp_path)
    scfg = S.load_stations_config({})
    wait_s = scfg["reap_after_intervals"] * 300
    stop = _hard_stop_aged(p, wait_s)
    _log_grew(p, 10)
    out = S.inspect(p, F.TASK_ID, F.events(p), scfg, 300, F.emitter(p))
    assert out["reap"] is None
    assert out["reap_deferred"]["stop_event_id"] == stop["event_id"]
    assert out["reap_deferred"]["last_log_growth_s"] < wait_s


def test_a_hard_stop_past_the_interval_with_a_log_quiet_for_wait_s_plus_1_is_reaped(tmp_path):
    p = F.make_project(tmp_path)
    scfg = S.load_stations_config({})
    wait_s = scfg["reap_after_intervals"] * 300
    stop = _hard_stop_aged(p, wait_s)
    _log_grew(p, wait_s + 1)
    out = S.inspect(p, F.TASK_ID, F.events(p), scfg, 300, F.emitter(p))
    assert out["reap"]["stop_event_id"] == stop["event_id"]
    assert out["reap"]["last_log_growth_s"] >= wait_s
    # The reap's record carries the liveness reading it acted on.
    from seldon.commands import dispatch_stations as ST
    ST.record_reap(p, F.TASK_ID, out["reap"], 4242, "SIGTERM")
    (reaped,) = F.events(p, S.EVENT_ANDON_REAPED)
    assert reaped["payload"]["last_log_growth_s"] == out["reap"]["last_log_growth_s"]


def test_the_launch_settings_carry_the_tool_gate(tmp_path):
    from seldon.commands import dispatch as cmd
    hooks = cmd._session_settings(tmp_path, {})["hooks"]["PreToolUse"]
    assert hooks[0]["matcher"] == "*" and "dispatch tool-gate --project" in hooks[0]["hooks"][0]["command"]
