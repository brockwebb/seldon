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


def main(argv: list[str]) -> int:
    # Default: sequence.py. `launch.py stress.py <args>` starts the stress comparison the same way, to stress.out.
    script_name, args = (argv[0], argv[1:]) if argv else ("sequence.py", [])
    (HERE / "logs").mkdir(exist_ok=True)
    out = HERE / "logs" / f"{Path(script_name).stem}.out"
    quoted = " ".join(f'"{a}"' for a in args)
    script = (f'caffeinate -i "{sys.executable}" "{HERE / script_name}" {quoted} > "{out}" 2>&1; '
              f'echo "EXIT=$?" >> "{out}"')
    proc = subprocess.Popen(["/bin/sh", "-c", script], cwd=HERE.parents[2], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print(f"launched pid {proc.pid}; output {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
