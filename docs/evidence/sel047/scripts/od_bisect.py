"""SEL-047 Part B item 5: halve the polluter file's tests (delta debugging as iDFlakies does) until one test, run
before the victim in one process, makes it fail. Each replay is one `runs.py extra` line (`od_bisect_<n>`).
Stops at one test, or after SEARCH_CAP_S of wall time."""
import json
import subprocess
import sys
import time

POLLUTER_FILE = "tests/test_sel008_cross_project_waits_and_block_reason.py"
VICTIM = "tests/test_sel018_relative_dispatch_paths.py::test_dispatch_status_reads_the_cap_from_a_worktree"
SEARCH_CAP_S = 45 * 60

ids = [x.strip() for x in subprocess.run(
    [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:randomly", "-p", "no:cacheprovider",
     POLLUTER_FILE], capture_output=True, text=True).stdout.splitlines() if x.startswith(POLLUTER_FILE + "::")]
print(f"{len(ids)} candidate tests", flush=True)


def fails(n: int, cands: list) -> bool:
    name = f"od_bisect_{n:02d}"
    subprocess.run([sys.executable, "docs/evidence/sel047/scripts/runs.py", "extra", name, *cands, VICTIM], check=True)
    for line in open("docs/evidence/sel047/runs.jsonl"):
        r = json.loads(line)
        if r["run"] == name:
            return VICTIM in r["failed_ids"]
    raise SystemExit(f"{name} not on the ledger")


t0, n, cands = time.monotonic(), 0, ids
while len(cands) > 1 and time.monotonic() - t0 < SEARCH_CAP_S:
    half = len(cands) // 2
    first, second = cands[:half], cands[half:]
    n += 1
    if fails(n, first):
        cands = first
    else:
        n += 1
        if fails(n, second):
            cands = second
        else:
            print(f"neither half alone reproduces it: the pollution needs tests from both halves {first} {second}",
                  flush=True)
            break
    print(f"after replay {n}: {len(cands)} candidate(s): {cands[:4]}", flush=True)
print(f"RESULT: {cands if len(cands) <= 3 else str(len(cands)) + ' candidates'}; {n} replays; "
      f"{time.monotonic() - t0:.0f} s", flush=True)
