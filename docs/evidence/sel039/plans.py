"""SEL-039: the library arm's plan for each real repository, with the branch's code. Read only: no search, no log line.
Run as `python - < /tmp/sel039/plans.py` from the worktree, so the worktree's seldon is imported."""
from pathlib import Path

import seldon.core.prior_art as pa
from seldon.config import load_project_config

print("seldon imported from", pa.__file__)
WT = Path("/Users/brock/GitHub/seldon/.claude/worktrees/fluffy-chasing-pond")
for proj in [WT, *(Path("/Users/brock/GitHub") / n for n in
                   ("hazbrief-mcp", "squiddy", "arnold", "ai-readiness-kg", "slosh-pipe"))]:
    try:
        cfg = load_project_config(proj)
        s = pa.settings(proj, cfg)
        plan = pa.library_plan(s)
        notice = pa.own_graph_notice(proj, cfg)
    except pa.PriorArtError as exc:
        print(proj.name, "ERROR", exc)
        continue
    print(f"{proj.name}: search {[(g['name'], g['origin']) for g in plan['search']]}")
    for g in plan["not_searched"]:
        print(f"    not searched {g['name']}: {g['why'][:110]}")
    print(f"    default (unnamed receipt) -> {s.library_graph.name}; reachable {sorted(plan['reachable'])}")
    print(f"    R27 notice: {notice}")
