"""SEL-039 Part C (R26): real design notes whose receipts name `graph seldon-biblio`, verified with this branch's code from
the consumer's own settings, under which seldon-biblio is no longer searched by default. READ ONLY: the query log points
at /tmp and no verdict is recorded. Run as `python - < /tmp/sel039/proof_r26.py` from the worktree."""
import dataclasses
import json
from pathlib import Path

import seldon.core.prior_art as pa
from seldon.config import load_project_config

NOTES = [
    ("/Users/brock/GitHub/hazbrief-mcp",
     "docs/design/2026-11-12_DN-029_the_threat_timeline_rows_order_considerations_occupancy_and_the_exercise_events_list.md"),
    ("/Users/brock/GitHub/squiddy",
     "docs/design/2026-11-15_DN-062_the_no_unasked_model_call_check_reads_the_pass_s_own_run.md"),
]
print("seldon imported from", pa.__file__)
out = []
for proj, rel in NOTES:
    proj = Path(proj)
    s = pa.settings(proj, load_project_config(proj))
    s = dataclasses.replace(s, log=Path("/tmp/sel039/proof_r26_queries.jsonl"))
    v = pa.verify_note(proj / rel, s)
    lib = [r for r in v.receipts if r.kind == "library"]
    row = {"project": proj.name, "note": rel, "verdict": v.verdict,
           "library": [{"graph": r.graph or f"(none -> {s.library_graph.name})", "status": r.status,
                        "source": f"{Path(r.source).name}:{r.line}", "detail": (r.detail or "")[:120]} for r in lib],
           "problems": v.problems}
    out.append(row)
    print(f"\n{proj.name} {Path(rel).name}: {v.verdict.upper()}")
    for r in row["library"]:
        print(f"  {r['status']:<18} graph {r['graph']:<22} {r['source']}")
    for p in v.problems:
        print("  PROBLEM:", p)
Path("/tmp/sel039/proof_r26.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
