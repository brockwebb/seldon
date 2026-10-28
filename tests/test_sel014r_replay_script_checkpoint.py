"""SEL-014R Part D: the paid replay script is checkpointed (CLAUDE.md section 15, item 8).

`scripts/sel014r_replay_with_the_model.py` in its `--fake-sleep-s` mode: the OODA run is replaced by a fake that
records each call and sleeps. A run is SIGKILLed while its second unit is in flight, then re-run with the same
command; the checkpoint must equal an uninterrupted run's, and no completed unit's call may be made twice.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sel014r_replay_with_the_model.py"
STABLE = ("key", "pid", "sid", "commit", "kind", "note", "tokens", "model")


def _cmd(root: Path, sleep: float) -> list:
    return [sys.executable, str(SCRIPT), "--root", str(root), "--fake-sleep-s", str(sleep), "--progress-s", "0.5"]


def _rows(root: Path) -> list:
    path = root / "checkpoint.jsonl"
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln] if path.is_file() else []


def _stable(rows: list) -> list:
    return [{k: r.get(k) for k in STABLE} for r in rows]


def test_a_killed_run_resumes_to_the_same_checkpoint_without_repeating_a_finished_call(tmp_path):
    whole = tmp_path / "whole"
    assert subprocess.run(_cmd(whole, 0), capture_output=True, text=True).returncode == 0
    expected = _rows(whole)
    assert len(expected) == 3

    killed = tmp_path / "killed"
    proc = subprocess.Popen(_cmd(killed, 2), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 60
    while len(_rows(killed)) < 1 and time.monotonic() < deadline:
        time.sleep(0.05)
    calls = killed / "calls.txt"
    while (len(calls.read_text().splitlines()) if calls.is_file() else 0) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait()
    assert len(_rows(killed)) == 1, "killed while the second unit was in flight"

    assert subprocess.run(_cmd(killed, 0), capture_output=True, text=True).returncode == 0
    assert _stable(_rows(killed)) == _stable(expected)
    made = calls.read_text().splitlines()
    first = expected[0]["key"]
    assert made.count(first) == 1, "the completed unit's call was made again"
    assert sorted(set(made)) == sorted(r["key"] for r in expected)
    assert "resume" in (killed / "progress.txt").read_text()
