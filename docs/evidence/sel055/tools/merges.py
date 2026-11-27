"""SEL-055 Part B: the last N merged tasks of each repository, from `dispatch_finished` records (read-only).
Writes /tmp/sel055/merges_<repo>.json: [{task_id, name, ts, branch, commit, writes, lane, gate, evidence}]."""
import json
import sys
from pathlib import Path

REPOS = {"seldon": Path("/Users/brock/GitHub/seldon"), "hazbrief": Path("/Users/brock/GitHub/hazbrief-mcp")}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
for name, root in REPOS.items():
    rows = []
    with (root / "seldon_events.jsonl").open() as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("event_type") != "dispatch_finished":
                continue
            p = e.get("payload") or {}
            m = p.get("merge") or {}
            if p.get("outcome") != "merged" or not m.get("commit"):
                continue
            ev = m.get("gate_evidence") or {}
            g = m.get("gate") or {}
            rows.append({"task_id": p.get("task_id"), "source_file": p.get("source_file"), "ts": e.get("timestamp"),
                         "branch": p.get("branch"), "commit": m.get("commit"), "writes": m.get("writes") or [],
                         "lane": bool(p.get("lane")), "evidence": ev.get("source"),
                         "gate_tier": g.get("tier") or ev.get("tier"), "gate_reason": g.get("reason") or ev.get("reason"),
                         "gate_seconds": g.get("seconds") or ev.get("seconds"), "regated": m.get("regated")})
    rows = rows[-N:]
    Path(f"/tmp/sel055/merges_{name}.json").write_text(json.dumps(rows, indent=1))
    print(f"== {name}: {len(rows)}")
    for r in rows:
        print(f"  {r['ts'][:16]} {r['task_id'][:8]} {Path(r['source_file'] or '').stem[11:50]:40} w={len(r['writes']):3} "
              f"lane={r['lane']} ev={r['evidence']} {r['gate_tier']} {str(r['gate_reason'])[:40]} {r['gate_seconds']}")
