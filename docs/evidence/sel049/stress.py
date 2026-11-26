"""SEL-049 addition, SEL-048's method: the three changed tests under induced CPU contention, old against new.

Usage: python docs/evidence/sel049/stress.py <hogs> <rounds> <old test file>
Starts <hogs> busy-loop processes (10 cores here), waits 20 s for the 1-minute load to climb, then for each round runs
the three tests from <old test file> (a temporary copy of main's `tests/test_dispatch_parallel.py`, which uses only
the scaffold's `sleep`, still served) and then from this branch's file, through run.py, `-p no:randomly`. The hogs are
stopped in a `finally`. Resume by skip, as sequence.py.

Why: the ten alone runs ran at a 1-minute load of 4 to 13, where SEL-047's old tests also mostly passed (its
`two_disjoint` failures were at loads 99, 47 and 18). Passing quietly proves little; the comparison under the same
contention says whether the old window misses and the new condition does not.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TREE = HERE.parents[2]
RUNS = HERE / "runs.jsonl"
SELECT = "two_disjoint or killed_supervisor_is_marked or exclusive_task_waits"
WARMUP_S = 20


def done() -> set[str]:
    return {json.loads(ln)["run"] for ln in RUNS.read_text().splitlines() if ln.strip()} if RUNS.exists() else set()


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    hogs, rounds, old = int(argv[0]), int(argv[1]), argv[2]
    if not (TREE / old).exists():
        print(f"no old test file at {old}", file=sys.stderr)
        return 2
    procs = [subprocess.Popen([sys.executable, "-c", "while True: pass"]) for _ in range(hogs)]
    try:
        time.sleep(WARMUP_S)
        for i in range(1, rounds + 1):
            for which, path in (("old", old), ("new", "tests/test_dispatch_parallel.py")):
                name = f"stress{hogs}_{which}_{i}"
                if name in done():
                    print(f"skip {name}", flush=True)
                    continue
                print(f"run {name}", flush=True)
                subprocess.run([sys.executable, str(HERE / "run.py"), name, "-v", "-p", "no:randomly",
                                path, "-k", SELECT], check=False)
    finally:
        for p in procs:
            p.kill()
        for p in procs:
            p.wait()
    print("STRESS DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
