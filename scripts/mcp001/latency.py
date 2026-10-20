"""MCP-001 Part A step 3: wall time of the three most-called seldon-mcp read tools, as the server calls them.

Run from the checkout whose code is measured, as a module so `seldon` imports from it (cwd first on sys.path):

    python -m dotenv -f .env run -- python -m scripts.mcp001.latency --phase before
    python -m dotenv -f .env run -- python -m scripts.mcp001.latency --phase after

Each call goes through the registered tool (what FastMCP invokes), so `before` includes the in-process stale guard
and `after` includes the fresh `python -P -m seldon mcp-call` child. One JSON row per call is appended and flushed as
it completes (CLAUDE.md section 15: a killed run keeps what it measured); a `summary` row per tool closes each phase.
Read-only calls against this project's own graph; no model calls, no spend.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

#: The tools the task names, with the arguments each is called with. Read-only, against this project's graph.
CALLS = {
    "seldon_query": {"cypher": "MATCH (t:Artifact:ResearchTask) RETURN count(t) AS n"},
    "seldon_task_list": {},
    "seldon_decision_show": {"record_id": "seldon:AD-011"},
}
#: The task's threshold: a median above this is reported in the RESULT, not optimized here.
MEDIAN_LIMIT_S = 2.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--phase", required=True, choices=["before", "after"])
    ap.add_argument("--n", type=int, default=10, help="calls per tool (the task: 10)")
    ap.add_argument("--project", default=".", help="project_dir passed to every tool")
    ap.add_argument("--out", default="docs/evidence/mcp001/latency.jsonl")
    args = ap.parse_args()

    import seldon.mcp_server as m

    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True).stdout.strip()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        def write(row: dict) -> None:
            fh.write(json.dumps(row) + "\n")
            fh.flush()

        for tool, kwargs in CALLS.items():
            fn = getattr(m, tool)
            secs = []
            for i in range(args.n):
                t0 = time.perf_counter()
                answer = fn(project_dir=args.project, **kwargs)
                dt = time.perf_counter() - t0
                ok = isinstance(answer, str) and not answer.startswith("Error")
                secs.append(dt)
                write({"phase": args.phase, "tool": tool, "i": i, "seconds": round(dt, 4), "ok": ok,
                       "code": head, "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
                if not ok:
                    print(f"{tool} call {i} answered an error: {str(answer)[:300]}")
            med = statistics.median(secs)
            write({"phase": args.phase, "tool": tool, "summary": True, "n": len(secs),
                   "median_s": round(med, 4), "min_s": round(min(secs), 4), "max_s": round(max(secs), 4),
                   "over_limit": med > MEDIAN_LIMIT_S, "limit_s": MEDIAN_LIMIT_S, "code": head})
            print(f"{args.phase:6s} {tool:22s} n={len(secs)} median={med:.3f}s min={min(secs):.3f}s "
                  f"max={max(secs):.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
