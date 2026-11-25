"""SEL-047 Part B: run the measured pytest invocations one after another and record each as one JSON line.

Usage (from the worktree root, detached by launch.py):
    python docs/evidence/sel047/scripts/runs.py <plan>      plan: alone | full | <run name> ...

Each run is one line in docs/evidence/sel047/runs.jsonl, written (flushed, fsynced) as the run ends, with the load
average and the machine's pytest process count before and after (the task's rules). A run whose name is already in
runs.jsonl is skipped, so re-running the same command resumes (Section 15 rule 2). The full log stays in
/tmp/sel047/logs/; the evidence copy is trimmed to its failures and summary when over 2 MB (and says so).
No model or network calls: the checkpoint is per run, and the abort ceiling is each run's wall-clock timeout.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EVID = ROOT / "docs/evidence/sel047"
LEDGER = EVID / "runs.jsonl"
FULL_LOGS = Path("/tmp/sel047/logs")
TRIM_BYTES = 2 * 1024 * 1024
PA002 = "tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index"
ALONE_REPEATS = 20
ALONE_FILES = ["tests/test_sel024_gate_record.py", "tests/test_dispatch_parallel.py"]
PARALLEL_REPEATS = 3
PARALLEL_WORKERS = 6
# Per-run wall ceiling: twice the slowest serial merge gate recorded (5,788 s on 2026-11-25).
TIMEOUT_FULL_S = 12000
TIMEOUT_ALONE_S = 1200

BASE = ['python', '-m', 'dotenv', '-f', os.environ["SELDON_PRIMARY_CHECKOUT"] + "/.env", 'run', '--',
        'env', 'PYTHONPATH=.', 'python', '-m', 'pytest', '-p', 'no:cacheprovider', '-p', 'no:randomly', '-v']


def plan() -> list:
    runs = []
    for f in ALONE_FILES:
        stem = Path(f).stem
        for i in range(1, ALONE_REPEATS + 1):
            runs.append((f"alone_{stem}_{i:02d}", BASE + [f], TIMEOUT_ALONE_S))
    runs.append(("full_serial_1", BASE + ["tests/", "--deselect", PA002], TIMEOUT_FULL_S))
    for i in range(1, PARALLEL_REPEATS + 1):
        runs.append((f"full_n{PARALLEL_WORKERS}_{i}", BASE + ["tests/", "-n", str(PARALLEL_WORKERS), "--deselect", PA002],
                     TIMEOUT_FULL_S))
    return runs


def load() -> list:
    out = subprocess.run(["uptime"], capture_output=True, text=True).stdout
    m = re.search(r"load averages?:\s*([\d.]+),?\s+([\d.]+),?\s+([\d.]+)", out)
    return [float(x) for x in m.groups()] if m else []


def pytest_procs() -> int:
    out = subprocess.run(["pgrep", "-f", "pytest"], capture_output=True, text=True).stdout
    return len([x for x in out.split() if x.strip()])


def done() -> set:
    if not LEDGER.is_file():
        return set()
    return {json.loads(line)["run"] for line in LEDGER.read_text().splitlines() if line.strip()}


SUMMARY = re.compile(r"^=+ (.*\bin [\d.]+s.*) =+$")


def parse(text: str) -> dict:
    counts = {"passed": 0, "failed": 0, "errors": 0}
    summary = None
    for line in text.splitlines():
        m = SUMMARY.match(line.strip())
        if m:
            summary = m.group(1)
    if summary:
        for n, word in re.findall(r"(\d+) (passed|failed|errors?)", summary):
            counts["errors" if word.startswith("error") else word] = int(n)
    ids = sorted({line.split(" ", 2)[1] for line in text.splitlines()
                  if line.startswith(("FAILED ", "ERROR ")) and len(line.split(" ")) > 1})
    return {**counts, "failed_ids": ids, "summary": summary}


def trim(text: str) -> str:
    keep, inside = [], False
    for line in text.splitlines():
        if re.match(r"^=+ (FAILURES|ERRORS|short test summary info) =+$", line):
            inside = True
        if inside or SUMMARY.match(line.strip()):
            keep.append(line)
    return "\n".join(keep) + "\n"


def one(name: str, cmd: list, timeout_s: int) -> dict:
    FULL_LOGS.mkdir(parents=True, exist_ok=True)
    (EVID / "logs").mkdir(parents=True, exist_ok=True)
    full_log = FULL_LOGS / f"{name}.log"
    lb, pb = load(), pytest_procs()
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    timed_out = False
    with open(full_log, "w") as fh:
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
        try:
            rc = p.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            p.kill()
            rc = p.wait()
            timed_out = True
    wall = round(time.monotonic() - t0, 1)
    ended = datetime.now(timezone.utc)
    la, pa = load(), pytest_procs()
    text = full_log.read_text(errors="replace")
    got = parse(text)
    ev_log = EVID / "logs" / f"{name}.log"
    trimmed = len(text.encode()) > TRIM_BYTES
    ev_log.write_text(trim(text) if trimmed else text)
    line = {"run": name, "command": " ".join(cmd), "started_at": started.isoformat(timespec="seconds"),
            "ended_at": ended.isoformat(timespec="seconds"), "wall_s": wall, "load_before": lb, "load_after": la,
            "pytest_procs_before": pb, "pytest_procs_after": pa, "passed": got["passed"], "failed": got["failed"],
            "errors": got["errors"], "failed_ids": got["failed_ids"], "summary": got["summary"], "exit_code": rc,
            "timed_out": timed_out, "log": str(ev_log.relative_to(ROOT)),
            "log_trimmed": (f"trimmed to failures and summary ({len(text.encode())} bytes in full; full log "
                            f"{full_log})") if trimmed else False}
    with open(LEDGER, "a") as fh:
        fh.write(json.dumps(line) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return line


def main(argv: list) -> int:
    runs = plan()
    if argv and argv[0] == "alone":
        runs = [r for r in runs if r[0].startswith("alone_")]
    elif argv and argv[0] == "full":
        runs = [r for r in runs if r[0].startswith("full_")]
    elif argv:
        runs = [r for r in runs if r[0] in argv]
    have = done()
    todo = [r for r in runs if r[0] not in have]
    print(f"{len(runs)} planned, {len(runs) - len(todo)} already recorded, {len(todo)} to run", flush=True)
    for i, (name, cmd, timeout_s) in enumerate(todo, 1):
        print(f"[{datetime.now().isoformat(timespec='seconds')}] {i}/{len(todo)} start {name}", flush=True)
        r = one(name, cmd, timeout_s)
        print(f"[{datetime.now().isoformat(timespec='seconds')}] {i}/{len(todo)} done {name}: wall {r['wall_s']} s, "
              f"{r['passed']} passed, {r['failed']} failed, {r['errors']} errors, load {r['load_after']}, "
              f"failed {r['failed_ids']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
