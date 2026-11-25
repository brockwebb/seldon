"""SEL-044 Part D check: each real repository's `seldon task list` row count against the brief's open count, taken
back to back, and how many gate records in each store carry wall_seconds."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

WT = "/Users/brock/GitHub/seldon/.claude/worktrees/enchanted-cuddling-cake"
G = "/Users/brock/GitHub"
env = {**os.environ, **{k: v for k, v in dotenv_values(f"{WT}/.env").items() if v is not None}, "PYTHONPATH": WT}
r = subprocess.run([sys.executable, "-m", "seldon", "go", "--portfolio", "--json"], cwd="/tmp/sel044/port", env=env,
                   capture_output=True, text=True)
data = json.loads(r.stdout)
for row in data["repositories"]:
    if not row.get("readable"):
        print(f"{row['name']:16} unreadable: {row['reason']}")
        continue
    lst = subprocess.run([sys.executable, "-m", "seldon", "task", "list"], cwd=row["path"], env=env,
                         capture_output=True, text=True)
    ids = re.findall(r"^\S*\s+([0-9a-f]{8}) ", lst.stdout, flags=re.M)
    brief = sorted(t["id"][:8] for t in row["tasks"]["open"])
    walls = other = 0
    with open(Path(row["path"]) / "seldon_events.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if '"gate_run"' in line or '"gate_recorded"' in line:
                e = json.loads(line)
                p = e.get("payload") or {}
                if e.get("event_type") not in ("gate_run", "gate_recorded"):
                    continue
                w = p.get("wall_seconds") if e["event_type"] == "gate_run" else (p.get("gate") or {}).get("wall_seconds")
                walls += w is not None
                other += w is None
    print(f"{row['name']:16} brief={row['tasks']['open_count']:3d} task_list={len(ids):3d} "
          f"same_ids={brief == sorted(ids)} gate_records_with_wall={walls} without={other}")
