"""SEL-039 Part C: the filing's three queries for hazbrief-mcp, with this branch's code, READ ONLY.

`project_dir` is hazbrief's primary and nothing is written there: `Libraries.search` logs nothing (only
`commands.prior_art.run_search` appends to the query log, and it is not called), and the R26 verification below runs with
the query log pointed at /tmp. Run as `python - < /tmp/sel039/proof_c.py` from the worktree so the worktree's seldon is
the one imported. Output: /tmp/sel039/proof_c.json plus a printed digest.
"""
import dataclasses
import json
from pathlib import Path

import seldon.core.prior_art as pa
from seldon.config import load_project_config

HB = Path("/Users/brock/GitHub/hazbrief-mcp")
QUERIES = ["dense gas shallow layer time dependent", "SCIPUFF vertical resolution puff split dense",
           "Jack Rabbit chlorine model comparison"]
print("seldon imported from", pa.__file__)
cfg = load_project_config(HB)
s = pa.settings(HB, cfg)
s = dataclasses.replace(s, log=Path("/tmp/sel039/proof_c_queries.jsonl"))
libs = pa.Libraries(s)
out = {"project": str(HB), "searched": [(n, libs.origin[n]) for n in libs.libs],
       "not_searched": [{"graph": g["name"], "why": g["why"]} for g in libs.not_searched], "queries": []}
try:
    for q in QUERIES:
        res = libs.search(q)
        rec = {"query": q, "graphs": []}
        flat = []
        for r in res:
            if r.get("error"):
                rec["graphs"].append({"graph": r["graph"], "origin": r["origin"], "error": r["error"]})
                continue
            top = [{"doc_id": h["doc_id"], "row": h["rows"][0]["receipt"]["row_id"] if h["rows"] else None,
                    "text": (h["rows"][0]["text"] if h["rows"] else "")[:140]} for h in r["hits"]]
            rec["graphs"].append({"graph": r["graph"], "origin": r["origin"], "release": r["release"],
                                  "rows": len(r["rows"]), "receipt": pa.Library.receipt(r)})
            flat += [{"graph": r["graph"], **t} for t in top]
        rec["first_five"] = flat[:5]
        out["queries"].append(rec)
finally:
    libs.close()
Path("/tmp/sel039/proof_c.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("searched:", out["searched"])
print("not searched:", out["not_searched"])
for rec in out["queries"]:
    print(f"\n## {rec['query']}")
    for g in rec["graphs"]:
        print(f"  graph {g['graph']} ({g['origin']}): " + (f"ERROR {g['error']}" if "error" in g else
                                                         f"{g['rows']} rows, release {g['release']}"))
    for i, t in enumerate(rec["first_five"], 1):
        print(f"  {i}. [{t['graph']}] {t['doc_id']}: {t['text']!r}")
