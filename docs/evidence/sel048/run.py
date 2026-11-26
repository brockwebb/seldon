"""SEL-048 run recorder: runs one pytest command the gate's way and appends one line to runs.jsonl.

Usage: python docs/evidence/sel048/run.py <run name> <pytest args...>

The command is the gate's form (`python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python
-m pytest -p no:cacheprovider ...`). The line carries the fields the task names: run, command, started_at, ended_at,
wall_s, load_before, passed, failed, failed_ids. The full pytest output goes to logs/<run>.log beside this file
(gitignored as *.log), and the summary line is kept on the row.
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

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs.jsonl"
LOGS = HERE / "logs"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    name, args = argv[0], argv[1:]
    primary = os.environ.get("SELDON_PRIMARY_CHECKOUT")
    if not primary:
        print("SELDON_PRIMARY_CHECKOUT is not set", file=sys.stderr)
        return 2
    cmd = [sys.executable, "-m", "dotenv", "-f", f"{primary}/.env", "run", "--", "env", "PYTHONPATH=.",
           sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args]
    LOGS.mkdir(exist_ok=True)
    log = LOGS / f"{name}.log"
    load_before = [round(x, 2) for x in os.getloadavg()]
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    with log.open("w") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
    wall = round(time.monotonic() - t0, 1)
    ended = datetime.now(timezone.utc)
    text = log.read_text(errors="replace")
    count = lambda word: sum(int(n) for n in re.findall(rf"(\d+) {word}", text.splitlines()[-1] if text else ""))
    failed_ids = sorted({m.split("::")[-1] for m in re.findall(r"^(?:FAILED|ERROR) (\S+)", text, re.M)})
    summary = text.strip().splitlines()[-1] if text.strip() else ""
    row = {"run": name, "command": " ".join(cmd), "started_at": started.isoformat(timespec="seconds"),
           "ended_at": ended.isoformat(timespec="seconds"), "wall_s": wall, "load_before": load_before,
           "load_after": [round(x, 2) for x in os.getloadavg()], "returncode": rc,
           "passed": count("passed"), "failed": count("failed") + count("error"), "failed_ids": failed_ids,
           "summary": summary}
    with RUNS.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    print(json.dumps(row))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
