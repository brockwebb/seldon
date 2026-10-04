"""Constitution section 15.8 for SEL-002 Part E's statement pass: SIGKILL mid-loop, restart, compare.

Runs in Squiddy's environment, offline (the harness's --mock client: no network, no spend):

    cd /Users/brock/GitHub/squiddy && .venv/bin/python ../seldon/scripts/sel002/statements_kill_test.py

1. An uninterrupted run over 12 synthetic records (writer pass, then validator pass) in one directory.
2. The same command in a second directory, SIGKILLed (not a polite exception) once at least four writer rows are
   fsynced, then re-run to completion with the same command.
3. Asserts: the two final checkpoints hold the same completed rows key for key; and no call whose row was in the
   checkpoint at the moment of the kill was made again (each such prompt appears once in the mock's call log; a
   call in flight at the kill had no row and may be asked again, which is the resume working).

Exit 0 and a PASS line, or a non-zero exit naming what differed. The output is recorded in
evidence/sel002/statements_kill_test.txt.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "statements.py"


def synth(evid: Path, n: int = 12) -> None:
    evid.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(n):
        text = f"Rule {i}: every call to the store number {i} reserves before dispatch and settles after."
        rows.append({"id": f"squiddy:R-{900 + i}", "kind": "decision", "status": "accepted", "source_text": text,
                     "source_sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text)})
    (evid / "units.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def cmd(evid: Path) -> list[str]:
    return [sys.executable, str(HARNESS), "run", "--mock", "--evid", str(evid)]


def rows(path: Path) -> dict[str, dict]:
    out = {}
    if path.is_file():
        for ln in path.read_text().splitlines():
            if ln.strip():
                r = json.loads(ln)
                if r.get("status") == "ok":
                    out[r["key"]] = {k: v for k, v in r.items() if k not in ("seconds",)}
    return out


def main() -> int:
    env = dict(os.environ, SEL002_MOCK_DELAY="0.3", PYTHONUNBUFFERED="1")
    with tempfile.TemporaryDirectory() as t:
        a, b = Path(t) / "uninterrupted", Path(t) / "killed"
        synth(a), synth(b)
        r = subprocess.run(cmd(a), env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:], r.stderr[-2000:])
            raise SystemExit("FAIL: the uninterrupted run failed")
        p = subprocess.Popen(cmd(b), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 60
        while time.time() < deadline and len(rows(b / "writer.jsonl")) < 4:
            time.sleep(0.05)
        os.kill(p.pid, signal.SIGKILL)
        p.wait()
        at_kill_w, at_kill_v = rows(b / "writer.jsonl"), rows(b / "validator.jsonl")
        if not at_kill_w or len(at_kill_w) >= 12:
            raise SystemExit(f"FAIL: the kill did not land mid-loop ({len(at_kill_w)} writer rows)")
        log_at_kill = (b / "mock_calls.log").read_text().splitlines()
        r = subprocess.run(cmd(b), env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:], r.stderr[-2000:])
            raise SystemExit("FAIL: the resumed run failed")
        for name in ("writer.jsonl", "validator.jsonl"):
            ua, ub = rows(a / name), rows(b / name)
            if ua != ub:
                diff = sorted(set(ua) ^ set(ub))[:5]
                raise SystemExit(f"FAIL: {name} differs from the uninterrupted run (keys {diff})")
        counts = collections.Counter((b / "mock_calls.log").read_text().splitlines())
        done_before = {r["key"] for r in list(at_kill_w.values()) + list(at_kill_v.values())}
        # each completed row's prompt hash: recompute from its reply? The mock logs the prompt hash; map row -> prompt
        # by re-deriving the prompt the harness sends (same functions, imported).
        sys.path.insert(0, str(HERE))
        import statements as st  # noqa: E402
        units = {u["id"]: u for u in st.units_in(b)}
        twice = []
        for key, row in list(at_kill_w.items()):
            h = hashlib.sha256(st.writer_prompt(units[row["item"]]).encode()).hexdigest()
            if counts[h] != 1:
                twice.append((row["item"], "writer", counts[h]))
        for key, row in list(at_kill_v.items()):
            stt = rows(b / "writer.jsonl")
            statement = next(r["parsed"]["statement"].strip() for r in stt.values() if r["item"] == row["item"])
            h = hashlib.sha256(st.validator_prompt(units[row["item"]], statement).encode()).hexdigest()
            if counts[h] != 1:
                twice.append((row["item"], "validator", counts[h]))
        if twice:
            raise SystemExit(f"FAIL: a completed unit's call was made again: {twice}")
        print(f"PASS: killed with {len(at_kill_w)} writer and {len(at_kill_v)} validator rows fsynced "
              f"({len(log_at_kill)} calls made); resumed to {len(rows(b / 'writer.jsonl'))} + "
              f"{len(rows(b / 'validator.jsonl'))} rows equal to the uninterrupted run; no completed call repeated "
              f"({sum(counts.values())} calls in all, {len(done_before)} completed before the kill)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
