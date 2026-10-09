"""PA-001 Part D's latency harness obeys constitution section 15: per-unit fsynced checkpoint,
resume by skip, and a SIGKILL mid-loop that loses nothing and repeats no completed unit."""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pa001" / "library_latency.py"

DRIVER = r"""
import importlib.util, json, sys, time
spec = importlib.util.spec_from_file_location("ll", sys.argv[1]); ll = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ll)
from pathlib import Path
ckpt, calls = Path(sys.argv[2]), Path(sys.argv[3])
qs = [{"id": f"Q{i}", "question": f"question {i}"} for i in range(6)]
def measure(mode, questions):
    with calls.open("a") as fh:
        for q in questions:
            fh.write(f"{mode}|{q}\n")
    time.sleep(0.25)
    return [{"seconds": len(q) / 100, "hits": 1, "error": None} for q in questions]
sys.exit(ll.execute(ll.units(qs, "f" * 64), measure, ckpt, Path(sys.argv[4]), 600))
"""


def _run(tmp, ckpt, calls, wait_rows=None):
    drv = tmp / "driver.py"
    drv.write_text(DRIVER)
    p = subprocess.Popen([sys.executable, str(drv), str(SCRIPT), str(ckpt), str(calls),
                          str(tmp / "log.txt")], stdout=subprocess.DEVNULL)
    if wait_rows is None:
        assert p.wait(timeout=60) == 0
        return None
    deadline = time.time() + 30
    while time.time() < deadline:
        if ckpt.is_file() and len(ckpt.read_text().splitlines()) >= wait_rows:
            break
        time.sleep(0.02)
    os.kill(p.pid, signal.SIGKILL)
    p.wait()
    return [json.loads(x)["key"] for x in ckpt.read_text().splitlines()]


def _rows(ckpt):
    return sorted((json.loads(x)["key"], json.loads(x)["seconds"]) for x in ckpt.read_text().splitlines())


def test_sigkill_mid_loop_then_resume_equals_an_uninterrupted_run(tmp_path):
    clean = tmp_path / "clean"
    clean.mkdir()
    _run(clean, clean / "ck.jsonl", clean / "calls.txt")
    killed = tmp_path / "killed"
    killed.mkdir()
    ck, calls = killed / "ck.jsonl", killed / "calls.txt"
    done_at_kill = _run(killed, ck, calls, wait_rows=3)
    assert 3 <= len(done_at_kill) < 12
    n_calls_at_kill = len(calls.read_text().splitlines())
    _run(killed, ck, calls)
    assert _rows(ck) == _rows(clean / "ck.jsonl")              # same final output
    after = calls.read_text().splitlines()[n_calls_at_kill:]
    done_q = {(k.split("|")[0], "question " + k.split("|")[1][1:]) for k in done_at_kill}
    assert not any(tuple(c.split("|", 1)) in done_q for c in after)   # no completed unit re-run


def test_p95_is_nearest_rank():
    spec = importlib.util.spec_from_file_location("ll", SCRIPT)
    ll = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ll)
    assert ll.p95(list(range(1, 21))) == 19 and ll.p95([5.0]) == 5.0 and ll.p95([]) is None
