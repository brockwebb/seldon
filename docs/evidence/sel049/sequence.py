"""SEL-049's runs, one at a time (none beside another, so none adds load to the next).

Usage: python docs/evidence/sel049/sequence.py
Launched detached under `caffeinate -i` by launch.py; each run appends its own line to runs.jsonl. Resume by skip: a
run whose name already has a line on runs.jsonl is not run again, so re-running this command after a kill continues.

Order: the full `-n 6` run first (Part B: an unrelated red there stops the task, so learn it first), then
`tests/test_dispatch_parallel.py` alone ten times (Part A), in the gate's form with pytest-randomly left on.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs.jsonl"
ALONE = 10

PLAN = [("full_n6_1", ["--gate-command"])] + [
    (f"alone_dispatch_parallel_{i:02d}", ["-v", "tests/test_dispatch_parallel.py"]) for i in range(1, ALONE + 1)]


def done() -> set[str]:
    if not RUNS.exists():
        return set()
    return {json.loads(ln)["run"] for ln in RUNS.read_text().splitlines() if ln.strip()}


def main() -> int:
    for name, args in PLAN:
        if name in done():
            print(f"skip {name} (on runs.jsonl)", flush=True)
            continue
        print(f"run {name}", flush=True)
        subprocess.run([sys.executable, str(HERE / "run.py"), name, *args], check=False)
    print("SEQUENCE DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
