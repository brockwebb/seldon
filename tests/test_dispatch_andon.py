"""QC-002 Part C (AD-037-R6 d): andon and huddle. `seldon dispatch stop <task>` writes the session stop; the session
reads it at its next Part or loop boundary and halts, writing `andon_halted`. A hard stop (a spend or disk ceiling, or
the operator's `--hard` for FC-32's toxic tier) kills nothing by hand: it is written, the session halts at its
boundary, and the lease holder reaps the session only if no `andon_halted` came within one poll interval.
`seldon dispatch huddle` writes FC-29's record; `seldon go` lists the open ones.

The plants are the tests named `test_plant_*`; each fails on the HEAD before QC-002
(docs/evidence/qc002/plants_fail_on_head.txt).
"""
from __future__ import annotations

import subprocess
import sys
import time

from click.testing import CliRunner

from seldon.cli import main
from tests import stations_scaffold as F


def _cli(p, monkeypatch, *argv):
    monkeypatch.chdir(p)
    monkeypatch.setenv("SELDON_SESSION_ID", "child-1")
    return CliRunner().invoke(main, ["dispatch", *argv])


def test_plant_an_operator_stop_halts_the_session_at_its_next_boundary(tmp_path, monkeypatch):
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(60))
    assert _cli(p, monkeypatch, "boundary").exit_code == 0, "no stop written: continue"
    r = _cli(p, monkeypatch, "stop", F.STEM, "--reason", "the output is out of spec")
    assert r.exit_code == 0, r.output
    from seldon.core import stations as S
    (stop,) = F.events(p, S.EVENT_SESSION_STOP)
    assert stop["payload"]["kind"] == "andon" and stop["payload"]["station"] == "operator"
    r = _cli(p, monkeypatch, "part-complete", "--part", "A")
    assert r.exit_code == S.HALT_EXIT, r.output
    (halted,) = F.events(p, S.EVENT_ANDON_HALTED)
    assert halted["payload"]["stop_event_id"] == stop["event_id"] and halted["payload"]["at"] == "Part A"
    assert _cli(p, monkeypatch, "boundary").exit_code == 0, "an answered stop does not halt twice"


def test_plant_a_hard_stop_is_reaped_after_one_interval_and_not_before(tmp_path, monkeypatch):
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(3600))
    r = _cli(p, monkeypatch, "stop", F.STEM, "--hard", "--reason", "toxic: deletes the ledger")
    assert r.exit_code == 0, r.output
    from seldon.core import stations as S
    scfg = S.load_stations_config({})
    (stop,) = F.events(p, S.EVENT_SESSION_STOP)
    written = S._parse_ts(stop["timestamp"])
    early = S.inspect(p, F.TASK_ID, F.events(p), scfg, 300, F.emitter(p), now=written + F.timedelta(seconds=299))
    assert early["reap"] is None, "not before one poll interval"
    late = S.inspect(p, F.TASK_ID, F.events(p), scfg, 300, F.emitter(p), now=written + F.timedelta(seconds=300))
    assert late["reap"]["stop_event_id"] == stop["event_id"] and late["reap"]["wait_s"] == 300
    # A session that halted in time is not reaped.
    F.record(p, S.EVENT_ANDON_HALTED, {"stop_event_id": stop["event_id"], "at": "Part A"})
    halted = S.inspect(p, F.TASK_ID, F.events(p), scfg, 300, F.emitter(p), now=written + F.timedelta(seconds=900))
    assert halted["reap"] is None


def test_the_holder_reaps_its_own_session_group_when_the_inspector_says_so(tmp_path):
    """`_run`'s wait loop: inspected every slice, and a due reap ends the session's process group (SIGTERM)."""
    from seldon.commands import dispatch as cmd
    calls, reaped = [], []

    def inspector():
        calls.append(time.monotonic())
        return {"reap": {"stop_event_id": "e1", "reason": "spend_ceiling", "age_s": 300, "wait_s": 300}} \
            if len(calls) >= 2 else {"reap": None}

    # The child spawns a grandchild: the group kill ends both.
    child = [sys.executable, "-c",
             "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
             "time.sleep(60)"]
    t0 = time.monotonic()
    code = cmd._run(child, tmp_path, tmp_path / "s.log", "child-1", inspector=inspector, inspect_every_s=0.2,
                    on_reap=lambda reap, pid, sig: reaped.append((reap["reason"], sig)))
    assert time.monotonic() - t0 < 30 and code == -15
    assert reaped == [("spend_ceiling", "SIGTERM")] and len(calls) == 2
    assert "EXIT=-15" in (tmp_path / "s.log").read_text()


def test_a_spend_ceiling_writes_one_hard_stop(tmp_path):
    from seldon.core import stations as S
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(60))
    F.write_log(p, 1_300_000)          # the estimate is 1M; the ceiling 1.2M
    for _ in range(2):
        S.inspect(p, F.TASK_ID, F.events(p), S.load_stations_config({}), 300, F.emitter(p))
    (stop,) = F.events(p, S.EVENT_SESSION_STOP)
    assert stop["payload"]["kind"] == "hard" and stop["payload"]["reason"] == "spend_ceiling"


def test_plant_go_lists_an_open_huddle_and_none_once_it_is_closed(tmp_path, monkeypatch):
    from seldon.commands import go
    p = F.make_project(tmp_path)
    F.launch(p, at=F.ago(60))
    r = _cli(p, monkeypatch, "huddle", F.STEM, "--reading", "CPI 0.5 below 0.8 at Part A")
    assert r.exit_code == 0, r.output
    section = go._get_stations_section(str(p))
    assert section and "Open huddles (1)" in section and "CPI 0.5 below 0.8" in section
    hid = r.output.split()[1]
    r = _cli(p, monkeypatch, "huddle", F.STEM, "--id", hid, "--cause", "the estimate was a guess",
             "--gate", "FC-12: estimates are measured")
    assert r.exit_code == 0, r.output
    monkeypatch.delenv("CLAUDECODE", raising=False)
    assert go._get_stations_section(str(p)) is None
    # A huddle written with all three of FC-29's fields is closed when written.
    _cli(p, monkeypatch, "huddle", F.STEM, "--reading", "r", "--cause", "c", "--gate", "g")
    monkeypatch.delenv("CLAUDECODE", raising=False)
    assert go._get_stations_section(str(p)) is None


def test_go_prints_the_protocols_three_lines_in_a_claude_code_session(tmp_path, monkeypatch):
    from seldon.commands import go
    p = F.make_project(tmp_path)
    monkeypatch.setenv("CLAUDECODE", "1")
    section = go._get_stations_section(str(p))
    assert section.count("seldon dispatch ") >= 3 and len(go.SESSION_PROTOCOL_LINES) == 3
    monkeypatch.delenv("CLAUDECODE")
    assert go._get_stations_section(str(p)) is None
