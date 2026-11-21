"""SEL-041 Part A: squiddy's kit pass ledger, wall seconds per recorded pass (read only)."""
import json

rows = []
for line in open("/Users/brock/GitHub/squiddy/kit/ledger/passes.jsonl"):
    e = json.loads(line)
    p = e.get("payload") or {}
    secs = [r.get("seconds") or r.get("wall_s") or r.get("duration_s") for r in p.get("runs") or []]
    keys = sorted((p.get("runs") or [{}])[0].keys())
    rows.append((e["ts"][:16], e["type"], len(p.get("runs") or []), secs, p.get("wall_s") or p.get("seconds")))
print("run keys:", keys)
for r in rows[-20:]:
    print(r)
