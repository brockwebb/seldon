"""Run one command under Squiddy's egress policy `none`, and record how it was enforced (SEL-001).

    ~/GitHub/squiddy/.venv/bin/python scripts/sel001/offline.py <record.json> -- <command ...>

The kit's own `squiddy.egress.child` builds the command and environment: the proxy variables point at a closed
local port with NO_PROXY empty, the Hugging Face offline switches are set, and on macOS the command runs under
`sandbox-exec` with the kit's deny-network profile (Squiddy DN-031 R-142, X-002). The record names which of these
applied, the command, its exit code and its wall clock, so a reader can tell an offline run from a claimed one.
Exits with the command's own exit code.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from squiddy import egress


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "--":
        raise SystemExit("usage: offline.py <record.json> -- <command ...>")
    record_path, cmd = Path(argv[0]), argv[2:]
    full, env, rec = egress.child(egress.NetPolicy("none"), cmd)
    t0 = time.time()
    rc = subprocess.run(full, env=env).returncode
    record = {"command": cmd, "policy": rec, "returncode": rc, "seconds": round(time.time() - t0, 1),
              "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    record_path.parent.mkdir(parents=True, exist_ok=True)
    runs = json.loads(record_path.read_text(encoding="utf-8")) if record_path.is_file() else []
    runs.append(record)
    record_path.write_text(json.dumps(runs, indent=1) + "\n", encoding="utf-8")
    print(f"offline run: rc {rc}, {record['seconds']}s, sandbox {rec.get('sandbox')}", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
