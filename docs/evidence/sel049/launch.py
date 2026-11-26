"""Start sequence.py detached under `caffeinate -i`, its output to logs/sequence.out ending `EXIT=<rc>`.

Usage: python docs/evidence/sel049/launch.py
Poll with `tail logs/sequence.out` (and `runs.jsonl`). Detached by a new session, as RECALL-001 found works from a
worktree where `nohup ... &` is refused.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    (HERE / "logs").mkdir(exist_ok=True)
    out = HERE / "logs" / "sequence.out"
    script = (f'caffeinate -i "{sys.executable}" "{HERE / "sequence.py"}" > "{out}" 2>&1; '
              f'echo "EXIT=$?" >> "{out}"')
    proc = subprocess.Popen(["/bin/sh", "-c", script], cwd=HERE.parents[2], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print(f"launched pid {proc.pid}; output {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
