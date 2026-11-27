"""SEL-055: survey gate_run records in seldon's and hazbrief's event stores (read-only)."""
import json
import sys
from pathlib import Path

REPOS = {"seldon": Path("/Users/brock/GitHub/seldon"), "hazbrief": Path("/Users/brock/GitHub/hazbrief-mcp")}
for name, root in REPOS.items():
    rows = []
    with (root / "seldon_events.jsonl").open() as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("event_type") == "gate_run":
                p = e.get("payload") or {}
                rows.append((e.get("timestamp", "")[:19], p.get("call_site"), p.get("tier"),
                             (p.get("reason") or "")[:70], p.get("outcome"), p.get("seconds"), p.get("wall_seconds"),
                             p.get("files_selected"), p.get("files_total"), (p.get("task_id") or "")[:8],
                             p.get("branch")))
    print(f"== {name}: {len(rows)} gate_run records")
    for r in rows[-int(sys.argv[1] if len(sys.argv) > 1 else 40):]:
        print("  ", " | ".join(str(x) for x in r))
