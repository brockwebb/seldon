"""SEL-036: the resolver's checkpoint survives a SIGKILL (~/GitHub/CLAUDE.md section 15.8).

The resolver (scripts/sel036/resolve.py) runs with `--fake-sleep-s`, its stand-in for the network, which logs every
request to calls.txt before answering. One run is SIGKILLed mid-loop and re-run with the same command; the test asserts
that its checkpoint then answers every seed exactly as an uninterrupted run's does, and that no unit whose row was
written had its request made twice (only the unit in flight at the kill may be asked again).
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sel036" / "resolve.py"
SEEDS = [{"id": f"w{i}", "kind": "work", "title": f"a fake work number {i} about traceability"} for i in range(8)]


def _run(d: Path, *extra: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(SCRIPT), "--seeds", str(d / "seeds.yaml"),
                             "--checkpoint", str(d / "units.jsonl"), "--fake-sleep-s", "0.4", *extra],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _answers(d: Path) -> dict:
    out = {}
    for line in (d / "units.jsonl").read_text().splitlines():
        r = json.loads(line)
        out[(r["seed"], r["authority"])] = (r["confirmed"], (r.get("answer") or {}).get("title"), r["why"])
    return out


def _setup(d: Path) -> None:
    d.mkdir(parents=True)
    (d / "seeds.yaml").write_text(yaml.safe_dump({"seeds": SEEDS}))


def test_a_killed_run_resumes_to_the_uninterrupted_answer_and_repeats_no_finished_call(tmp_path):
    whole, killed = tmp_path / "whole", tmp_path / "killed"
    _setup(whole)
    _setup(killed)
    p = _run(whole)
    out, _ = p.communicate(timeout=120)
    assert p.returncode == 0, out.decode()

    p = _run(killed)
    deadline = time.time() + 60
    while time.time() < deadline:
        calls = (killed / "calls.txt").read_text().splitlines() if (killed / "calls.txt").exists() else []
        if len(calls) >= 3:
            break
        time.sleep(0.05)
    os.kill(p.pid, signal.SIGKILL)
    p.wait(timeout=10)
    rows_at_kill = (killed / "units.jsonl").read_text().splitlines()
    assert 0 < len(rows_at_kill) < len(SEEDS), "the kill landed mid-loop"
    finished_urls = [c for r in rows_at_kill for c in (q["url"] for q in json.loads(r)["queries"])]

    p = _run(killed)
    out, _ = p.communicate(timeout=120)
    assert p.returncode == 0, out.decode()

    assert _answers(killed) == _answers(whole)
    calls = (killed / "calls.txt").read_text().splitlines()
    repeated = {c for c in calls if calls.count(c) > 1}
    assert not repeated & set(finished_urls), f"a finished unit was asked again: {repeated & set(finished_urls)}"
    assert len(repeated) <= 1, f"more than the one in-flight unit was asked twice: {repeated}"
