"""SEL-049 run recorder: runs one pytest command the gate's way and appends one line to runs.jsonl.

Usage:
    python docs/evidence/sel049/run.py <run name> <pytest args...>
    python docs/evidence/sel049/run.py <run name> --gate-command

The first form is the gate's prefix (`python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=.
python -m pytest -p no:cacheprovider ...`) with the given arguments, as SEL-048's `run.py`. The second runs
`dispatch.gate_command` read from this tree's `seldon.yaml`, verbatim, through `/bin/sh -c` in the tree's root with
`SELDON_PRIMARY_CHECKOUT` set, which is how `seldon/core/gate_plan.py` `run` executes the full tier.

Each run appends one line carrying the task's fields (run, command, started_at, ended_at, wall_s, load_before, passed,
failed, failed_ids) plus load_after, returncode, summary and `sleep_spanned` (wall-clock span minus monotonic seconds
over 30 s means the machine slept during the run, SEL-047). The line is flushed and fsynced before the next run starts.
The full pytest output goes to logs/<run>.log beside this file (`*.log` is gitignored; the logs are added with
`git add -f`, as SEL-047's were).
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

import yaml

HERE = Path(__file__).resolve().parent
TREE = HERE.parents[2]
RUNS = HERE / "runs.jsonl"
LOGS = HERE / "logs"
SLEEP_SPAN_S = 30   # SEL-047's threshold for a run that spanned a machine sleep


def _command(args: list[str], primary: str) -> list[str]:
    if args == ["--gate-command"]:
        gate = yaml.safe_load((TREE / "seldon.yaml").read_text())["dispatch"]["gate_command"]
        return ["/bin/sh", "-c", gate]
    return [sys.executable, "-m", "dotenv", "-f", f"{primary}/.env", "run", "--", "env", "PYTHONPATH=.",
            sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    name, args = argv[0], argv[1:]
    primary = os.environ.get("SELDON_PRIMARY_CHECKOUT")
    if not primary:
        print("SELDON_PRIMARY_CHECKOUT is not set", file=sys.stderr)
        return 2
    cmd = _command(args, primary)
    LOGS.mkdir(exist_ok=True)
    log = LOGS / f"{name}.log"
    load_before = [round(x, 2) for x in os.getloadavg()]
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    with log.open("w") as fh:
        rc = subprocess.run(cmd, cwd=TREE, stdout=fh, stderr=subprocess.STDOUT,
                            env={**os.environ, "SELDON_PRIMARY_CHECKOUT": primary}).returncode
    wall = round(time.monotonic() - t0, 1)
    ended = datetime.now(timezone.utc)
    text = log.read_text(errors="replace")
    summary = text.strip().splitlines()[-1] if text.strip() else ""

    def count(word):
        return sum(int(n) for n in re.findall(rf"(\d+) {word}", summary))

    failed_ids = sorted({m.split("::", 1)[-1] for m in re.findall(r"^(?:FAILED|ERROR) (\S+)", text, re.M)})
    row = {"run": name, "command": " ".join(cmd), "started_at": started.isoformat(timespec="seconds"),
           "ended_at": ended.isoformat(timespec="seconds"), "wall_s": wall, "load_before": load_before,
           "load_after": [round(x, 2) for x in os.getloadavg()], "returncode": rc,
           "passed": count("passed"), "failed": count("failed") + count("errors?"), "failed_ids": failed_ids,
           "summary": summary,
           "sleep_spanned": (ended - started).total_seconds() - wall > SLEEP_SPAN_S}
    with RUNS.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    print(json.dumps(row))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
