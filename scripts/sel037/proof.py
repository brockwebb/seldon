"""SEL-037 Part C: SEL-036 Part F's five queries through the prior-art gate's library arm, as an operator runs them.

    python -m dotenv -f .env run -- python scripts/sel037/proof.py [--out graphs/seldon-biblio/evidence/sel037/proof.json]

Each query is `seldon prior-art search "<q>" --library --json`, the gate's own command (not squiddy's search called
directly, which is what SEL-036's scripts/sel036/proof.py did), so the rows are the ones a note's receipt would carry.
Run from a worktree, the gate resolves `graphs/seldon-biblio` to the PRIMARY checkout's directory
(`seldon.core.prior_art.corpus_anchor`, AD-036 ADDENDUM 06); the proof records the directory each graph was read from,
so it shows which checkout served the release. Five subprocesses, zero network, zero model calls.

`--project DIR` runs the queries with DIR as the project (its seldon.yaml, its graphs/). SEL-037 used it on a scratch
directory holding exactly what the primary holds once this branch merges (the branch's tracked graph record plus the
release's ignored outputs, byte for byte the files installed in the primary), because before the merge the primary
pairs the new index with the old tracked manifest and the arm reports the graph unavailable (SEL-037 RESULT, Part C).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
#: SEL-036 Part F's five: AD-013 ADDENDUM 01's two library queries and SEL-036's three.
QUERIES = ["requirements traceability matrix", "trace link maintenance", "suspect link", "generated region markers",
           "verification method inspection analysis demonstration test"]
TOP = 8


def run(q: str, project: Path) -> dict:
    p = subprocess.run(["seldon", "prior-art", "search", q, "--library", "--json"], cwd=project, capture_output=True,
                       text=True)
    if p.returncode != 0:
        raise SystemExit(f"FATAL: the gate refused query {q!r} (rc {p.returncode}): {p.stderr[-800:]}")
    return json.loads(p.stdout)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "graphs/seldon-biblio/evidence/sel037/proof.json")
    ap.add_argument("--project", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    from seldon.core import prior_art as pa
    served_from = str(pa.corpus_anchor(a.project / "graphs" / "seldon-biblio"))
    out = {"project": str(a.project), "served_from": served_from, "queries": []}
    ok = True
    for q in QUERIES:
        res = run(q, a.project)
        rows = {}
        # the arm's JSON: `graphs`, one result per library graph, each with its `release` and its `top` documents,
        # every document carrying the receipt `rows` cut from it (seldon/commands/prior_art.py, AD-036-R21)
        for g in res.get("graphs") or []:
            top = g.get("top") or []
            rows[g["graph"]] = {"release": g.get("release"), "sha256": g.get("sha256"),
                                "rows": sum(len(t.get("rows") or []) for t in top),
                                "top_documents": [t["doc_id"] for t in top][:TOP],
                                "unavailable": g.get("unavailable") or g.get("error")}
        out["queries"].append({"query": q, "graphs": rows})
        b = rows.get("seldon-biblio") or {}
        ok &= bool(b.get("rows"))
        print(f"[seldon-biblio] {q!r}: {b.get('rows')} rows from {b.get('release')}; top {b.get('top_documents')}")
    out["every_query_has_seldon_biblio_rows"] = ok
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"served from {served_from}; every query answered by seldon-biblio: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
