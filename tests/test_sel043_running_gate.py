"""SEL-043 Part D (AD-037-R20, R21): a running gate writes its output to the dispatch log while it runs, and every gate
record carries wall-clock start and end and the seconds the host slept, from its power log.

squiddy's filing 083863ef: `stations.run_check` captured a gate's output until it exited and kept 1,500 characters,
so a two-hour gate and a hung one looked the same; and `time.monotonic()` does not advance while a Mac sleeps, so
SQ-133R's pass was recorded as 7,734 s when it ran 10,834 s by the wall clock (Clamshell Sleep 19:14:26Z to
20:07:58Z inside its third run).
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from seldon.core import gate_plan as GP
from seldon.core import gate_record as GR
from seldon.core import stations as S

#: `pmset -g log` lines as macOS writes them, cut to the SQ-133R gate's window (2026-11-13, host offset -0500).
PMSET = """\
2026-11-13 12:38:06 -0500 Assertions          \tPID 1(launchd) Created PreventUserIdleSystemSleep
2026-11-13 14:14:26 -0500 Sleep               \tEntering Sleep state due to 'Clamshell Sleep': Using Batt
2026-11-13 14:14:30 -0500 Wake Requests       \t[*process=dasd request=SleepService deltaSecs=1054]
2026-11-13 14:40:00 -0500 DarkWake            \tDarkWake from Deep Idle [CDNP] : due to smc.sysState.Wake
2026-11-13 14:41:00 -0500 Sleep               \tEntering Sleep state due to 'Maintenance Sleep'
2026-11-13 15:07:58 -0500 Wake                \tWake from Deep Idle [CDNVA] : due to lid UserActivity
"""


def test_asleep_seconds_sums_each_sleep_until_the_next_wake_inside_the_window():
    # 14:14:26 to 14:40:00 (1,534 s) and 14:41:00 to 15:07:58 (1,618 s), all inside 12:38:06 to 15:38:40 local.
    got = S.asleep_seconds("2026-11-13T17:38:06Z", "2026-11-13T20:38:40Z", PMSET)
    assert got == 1534.0 + 1618.0
    # A window that starts inside a sleep counts from its start; one that ends inside counts to its end.
    assert S.asleep_seconds("2026-11-13T19:20:00Z", "2026-11-13T19:30:00Z", PMSET) == 600.0
    # No power log on this host: unknown, never zero.
    assert S.asleep_seconds("2026-11-13T17:38:06Z", "2026-11-13T20:38:40Z", None) is None
    assert S.asleep_seconds("2026-11-13T17:38:06Z", "2026-11-13T17:40:00Z", PMSET) == 0.0


def test_a_window_the_power_log_does_not_reach_back_to_is_unknown_not_zero():
    """Found on real data (docs/evidence/sel043/asleep_sq133r.txt): this host's power log begins 2026-11-17, so for
    SQ-133R's gate on 2026-11-13 it holds no line, and an empty sum read as 'never slept'."""
    later = "\n".join(line for line in PMSET.splitlines() if line.startswith("2026-11-13 14:41"))
    assert S.asleep_seconds("2026-11-13T17:38:06Z", "2026-11-13T20:38:40Z", later) is None
    assert S.asleep_seconds("2026-11-13T17:38:06Z", "2026-11-13T20:38:40Z", "") is None


def test_wall_clock_fields_ask_the_power_log_only_when_wall_and_monotonic_disagree(monkeypatch):
    calls = []
    monkeypatch.setattr(S, "power_log_text", lambda: calls.append(1) or PMSET)
    f = S.wall_fields("2026-11-13T17:38:06Z", "2026-11-13T20:38:40Z", monotonic_s=7734.619)
    assert f == {"started_at": "2026-11-13T17:38:06Z", "ended_at": "2026-11-13T20:38:40Z", "wall_seconds": 10834.0,
                 "asleep_s": 3152.0}
    assert calls == [1]
    f = S.wall_fields("2026-11-13T17:38:06Z", "2026-11-13T17:40:06Z", monotonic_s=119.5)
    assert f["asleep_s"] == 0.0 and calls == [1], "agreeing clocks need no power log"


def test_run_check_streams_each_line_to_the_log_while_the_command_runs(tmp_path):
    log = tmp_path / "logs" / "t.gate.log"
    cmd = (f"{sys.executable} -c \"import time; print('first', flush=True); time.sleep(3); "
           f"print('second', flush=True)\"")
    seen = {}

    def watch():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if log.is_file() and "first" in log.read_text(encoding="utf-8").splitlines():
                seen["first_at"] = time.monotonic()
                seen["second_yet"] = "second" in log.read_text(encoding="utf-8").splitlines()
                return
            time.sleep(0.05)

    t = threading.Thread(target=watch)
    t.start()
    row = S.run_check(cmd, tmp_path, 30, stream_to=log, stream_header="gate record")
    t.join()
    assert seen and seen["second_yet"] is False, "the first line was readable before the command finished"
    text = log.read_text(encoding="utf-8")
    assert text.startswith("=== ") and "| gate record |" in text.splitlines()[0]
    assert text.rstrip().endswith("EXIT=0") and "first\nsecond\n" in text
    assert row["outcome"] == "pass" and "second" in row["tail"], "the tail is still kept for the record"
    assert row["started_at"] and row["ended_at"] and row["wall_seconds"] >= 3


def test_a_streamed_check_that_times_out_is_killed_and_says_so(tmp_path):
    log = tmp_path / "t.gate.log"
    cmd = f"{sys.executable} -c \"import time; print('working', flush=True); time.sleep(30)\""
    row = S.run_check(cmd, tmp_path, 2, stream_to=log)
    assert row["outcome"] == "fail" and row["exit"] is None and "timed out after 2" in row["tail"]
    assert "working" in log.read_text(encoding="utf-8")


def test_an_unstreamed_check_keeps_todays_row_and_gains_its_wall_clock(tmp_path):
    row = S.run_check(f"{sys.executable} -c \"print('x')\"", tmp_path, 30)
    assert row["outcome"] == "pass" and row["tail"] == "x\n" and row["output_sha256"]
    assert row["started_at"] <= row["ended_at"] and "wall_seconds" in row


def test_the_declared_pass_record_streams_and_its_summary_keeps_the_wall_clock(tmp_path):
    decl = {"command": f"{sys.executable} -c \"print('seed 1 done', flush=True)\"", "timeout_s": 30, "requires": [],
            "unrunnable_exits": [2, 3, 4]}
    log = tmp_path / "w.gate.log"
    row = GR.run(tmp_path, decl, log_path=log)
    assert "seed 1 done" in log.read_text(encoding="utf-8")
    s = GR.summary(row)
    assert {"started_at", "ended_at", "wall_seconds"} <= set(s) and s["seconds"] is not None


def test_a_gate_run_record_carries_wall_clock_start_end_and_sleep(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(S, "power_log_text", lambda: PMSET)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    plan = GP.unplanned(tmp_path, "b", "a scratch tree")
    result = GP.run(tmp_path, plan, GP.load_gate_config(None, "true"), gate_command="echo gating", timeout_s=30,
                    log_path=tmp_path / "g.log", primary=tmp_path)
    assert result["started_at"] and result["ended_at"] and result["wall_seconds"] is not None
    assert "asleep_s" in result
    payload = GP.record_payload(plan, result, call_site="merge_gate", events=[], task_id="t", branch=None,
                                log_rel="g.log")
    assert {"started_at", "ended_at", "wall_seconds", "asleep_s"} <= set(payload)
