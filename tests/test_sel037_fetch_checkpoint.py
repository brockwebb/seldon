"""SEL-037: the fetcher's checkpoint survives a SIGKILL (~/GitHub/CLAUDE.md section 15.8), and the catalog overlay
applies only the rows its config plans now.

The fetcher (scripts/sel037/fetch.py) runs with `--fake-sleep-s`, SEL-036's stand-in for the network, which logs every
request to calls.txt before answering. One run is SIGKILLed mid-loop and re-run with the same command; the checkpoint
must then hold exactly an uninterrupted run's outcomes, and no unit whose row was written may have been asked twice.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sel037" / "fetch.py"
REAL = yaml.safe_load((ROOT / "scripts" / "sel037" / "sel037.yaml").read_text(encoding="utf-8"))
N = 8


def _config(d: Path) -> Path:
    cfg = {k: v for k, v in REAL.items() if k != "targets"}
    cfg["checkpoint"] = str(d / "units.jsonl")
    cfg["targets"] = [{"entry": f"w{i}", "mode": "on_entry", "urls": [f"https://example.org/w{i}.pdf"],
                       "licence": "CC BY 4.0", "licence_basis": "fake"} for i in range(N)]
    p = d / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


def _run(d: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(SCRIPT), "--config", str(d / "cfg.yaml"),
                             "--checkpoint", str(d / "units.jsonl"), "--fake-sleep-s", "0.4"],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _outcomes(d: Path) -> dict:
    return {(r := json.loads(line))["entry"]: (r["key"], r["outcome"])
            for line in (d / "units.jsonl").read_text().splitlines()}


def _setup(d: Path) -> None:
    d.mkdir(parents=True)
    _config(d)


def test_a_killed_fetch_resumes_to_the_uninterrupted_outcome_and_repeats_no_finished_call(tmp_path):
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
    assert 0 < len(rows_at_kill) < N, "the kill landed mid-loop"
    finished = [u["url"] for r in rows_at_kill for u in json.loads(r)["steps"]]

    p = _run(killed)
    out, _ = p.communicate(timeout=120)
    assert p.returncode == 0, out.decode()

    assert _outcomes(killed) == _outcomes(whole)
    assert len((killed / "units.jsonl").read_text().splitlines()) == N
    calls = (killed / "calls.txt").read_text().splitlines()
    repeated = {c for c in calls if calls.count(c) > 1}
    assert not repeated & set(finished), f"a finished unit was asked again: {repeated & set(finished)}"
    assert len(repeated) <= 1, f"more than the one in-flight unit was asked twice: {repeated}"


# ------------------------------------------------------------------------------------------------- the overlay

sys.path.insert(0, str(ROOT / "scripts" / "sel037"))


def _overlay_world(tmp_path: Path, outcome: str, got: list | None = None, mode: str = "on_entry"):
    import fetch as F
    target = {"entry": "w0", "mode": mode, "urls": ["https://example.org/w0.pdf"], "licence": "CC BY 4.0",
              "licence_basis": "the journal", **({"new_prefix": "doc_w0_p_"} if mode == "doc_many" else {})}
    cfg = {k: v for k, v in REAL.items() if k != "targets"}
    cfg.update({"checkpoint": "units.jsonl", "targets": [target]})
    (tmp_path / "cfg.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    stale = {"key": "an-older-version", "entry": "w0", "outcome": "acquired", "target": target, "got": []}
    row = {"key": F.unit_key(target), "entry": "w0", "target": target, "outcome": outcome, "got": got or [],
           "steps": [{"url": "https://example.org/w0.pdf"}],
           "manual_posture": None if got else {"posture": "bot_wall", "host": "example.org", "status": 403,
                                               "first_bytes": "Just a moment", "at": "2026-11-12T00:00:00Z"}}
    (tmp_path / "units.jsonl").write_text(json.dumps(stale) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    entry = {"id": "w0", "kind": "work", "title": "W", "disposition": "metadata_only", "access": "restricted_or_unknown",
             "manual_reason": "off the Network line", "metadata_only_reason": "publisher_page_not_reachable_by_script"}
    return tmp_path / "cfg.yaml", [entry]


GOT = {"page_url": "https://example.org/w0.pdf", "final_url": "https://example.org/w0.pdf", "raw_path": "archive:r/w0.pdf",
       "text_path": "archive:r/w0.pdf", "raw_sha256": "a" * 64, "text_sha256": "a" * 64, "bytes": 10,
       "retrieved_at": "2026-11-12T00:00:00Z", "posture": {"host": "example.org", "at": "t"}, "pages": 3,
       "text_chars": 5000, "licence_found": ["CC BY 4.0"]}


def test_an_acquired_text_is_held_on_its_entry_with_the_filled_stub(tmp_path):
    import overlay as OV
    cfg, cands = _overlay_world(tmp_path, "acquired", [GOT])
    out, rep = OV.apply(cands, cfg, tmp_path)
    e = out[0]
    assert (e["local_path"], e["sha256"], e["raw_sha256"]) == ("archive:r/w0.pdf", "a" * 64, "a" * 64)
    assert e["disposition"] == "active" and e["access"] == "open" and e["manual_acquisition"] is False
    assert "manual_reason" not in e and "metadata_only_reason" not in e
    assert all(e[f"inbox_{k}"] for k in ("source_url", "obtained_from", "licence", "stated_by"))
    assert rep["acquired_on_entry"] == ["w0"]


def test_a_refused_text_stays_manual_with_its_status_first_bytes_and_time(tmp_path):
    import overlay as OV
    cfg, cands = _overlay_world(tmp_path, "manual")
    e = OV.apply(cands, cfg, tmp_path)[0][0]
    assert e["manual_acquisition"] is True and e["acquisition"] == "pending_manual"
    assert e["posture"] == "refused" and e["posture_host"] == "example.org"
    assert "HTTP 403" in e["posture_evidence"] and "Just a moment" in e["posture_evidence"]
    assert e["posture_observed_at"] == "2026-11-12T00:00:00Z"


def test_a_planned_target_with_no_row_refuses_the_rebuild(tmp_path):
    import overlay as OV
    cfg, cands = _overlay_world(tmp_path, "acquired", [GOT])
    (tmp_path / "units.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="no row for target w0"):
        OV.apply(cands, cfg, tmp_path)
