"""SEL-036 Part F: AD-013 ADDENDUM 01's library searches, and three more, against BOTH library graphs (AD-036-R21).

    python scripts/sel036/proof.py --biblio <path to the seldon-biblio graph holding a served release>

Read-only over the graphs; writes graphs/seldon-biblio/evidence/sel036/proof.json and prints one receipt per graph per
query. `--biblio` exists because seldon.yaml names `graphs/seldon-biblio` at the PRIMARY checkout (AD-036 ADDENDUM 06),
and a release cut in a dispatched worktree is served from the worktree until the primary rebuilds it. The searches do
not go through `seldon prior-art search`, so nothing is appended to the query log or committed: this is a measurement,
not a receipt for a note.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from seldon.config import load_project_config  # noqa: E402
from seldon.core import prior_art as pa  # noqa: E402

#: AD-013 ADDENDUM 01 section 2 ran the first two (SEL-033); the task names the other three.
QUERIES = ["requirements traceability matrix", "trace link maintenance", "suspect link", "generated region markers",
           "verification method inspection analysis demonstration test"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--biblio", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "graphs/seldon-biblio/evidence/sel036/proof.json")
    a = ap.parse_args(argv)
    s = pa.settings(ROOT, load_project_config(ROOT))
    graphs = tuple((n, (a.biblio.resolve() if n == "seldon-biblio" else p)) for n, p in s.library_graphs)
    s = dataclasses.replace(s, library_graphs=graphs)
    libs = pa.Libraries(s)
    out = []
    try:
        for q in QUERIES:
            for res in libs.search(q):
                row = {"query": q, "graph": res["graph"]}
                if res.get("error"):
                    row["error"] = res["error"]
                else:
                    row.update({"release": res["release"], "sha256": res["sha256"], "rows": res["rows"],
                                "documents": list(dict.fromkeys(h["doc_id"] for h in res["hits"])),
                                "receipt": pa.Library.receipt(res)})
                out.append(row)
                print(f"{q!r} [{row['graph']}]: " + (row.get("error") or ", ".join(row["documents"][:8])))
    finally:
        libs.close()
    a.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
