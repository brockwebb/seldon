"""PA-001 Part C: run the pre-registered recall control of the internal search tool (AD-036-R5).

    python scripts/pa001/recall_control.py [--prereg docs/evidence/pa001/recall_control_prereg.yaml]

Reads the pre-registration, runs each entry's fixed query on the internal arm over the corpus
declared in seldon.yaml, and counts an entry as found when one of the query's top-k hits (over the
whole corpus) is a paragraph of the entry's root and path that spans the entry's line. Writes
`docs/evidence/pa001/recall_control_result.json` with the commits read, every entry's rank or
miss, recall, its Wilson-95 interval and the verdict against the pre-registered bar. Zero model
calls; local files only. Re-run on every change to the tool (R5).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import yaml

from seldon.config import load_project_config
from seldon.core import prior_art as pa


def wilson(k: int, n: int, z: float) -> tuple[float, float]:
    """Wilson score interval (Wilson 1927) for k successes in n trials."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prereg", default="docs/evidence/pa001/recall_control_prereg.yaml")
    ap.add_argument("--out", default="docs/evidence/pa001/recall_control_result.json")
    a = ap.parse_args(argv)
    project = Path.cwd()
    config = load_project_config(project)
    s = pa.settings(project, config)
    pre = yaml.safe_load((project / a.prereg).read_text(encoding="utf-8"))
    if pre["tool"] != pa.TOOL_VERSION:
        print(f"the pre-registration names tool {pre['tool']}, this is {pa.TOOL_VERSION}",
              file=sys.stderr)
        return 2
    k, z, bar = int(pre["top_k"]), float(pre["z"]), float(pre["bar_lower_bound"])
    tool = pa.Internal(s)
    rows, found = [], 0
    corpora = None
    for e in pre["entries"]:
        res = tool.search(e["query"])
        corpora = corpora or {n: m["identity"] for n, m in res["corpora"].items()}
        rank = None
        for i, h in enumerate(res["hits"][:k], 1):
            if h.root == e["root"] and h.path == e["path"] and h.start <= e["line"] <= h.end:
                rank = i
                break
        anywhere = next((i for i, h in enumerate(res["hits"], 1) if h.root == e["root"]
                         and h.path == e["path"] and h.start <= e["line"] <= h.end), None)
        found += rank is not None
        pa.log_query(s, {"arm": "internal", "purpose": "recall_control", "entry": e["id"],
                         "query": e["query"], "corpora": corpora, "hits": len(res["hits"]),
                         "rank": rank})
        rows.append({"id": e["id"], "query": e["query"], "root": e["root"], "path": e["path"],
                     "line": e["line"], "hits": len(res["hits"]), "rank_top_k": rank,
                     "rank_anywhere": anywhere,
                     "top3": [f"{h.root}:{h.path}:{h.start}" for h in res["hits"][:3]]})
    n = len(rows)
    lo, hi = wilson(found, n, z)
    out = {"tool": pa.TOOL_VERSION, "prereg": a.prereg, "top_k": k, "n": n, "found": found,
           "recall": round(found / n, 4), "wilson95": [round(lo, 4), round(hi, 4)],
           "bar_lower_bound": bar, "verdict": "pass" if lo >= bar else "fail",
           "corpora": corpora, "entries": rows,
           "misses": [r["id"] for r in rows if r["rank_top_k"] is None]}
    (project / a.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({x: out[x] for x in ("n", "found", "recall", "wilson95", "verdict",
                                          "misses")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
