"""SEL-039: for every graphs/*/graph.yaml beside seldon, the served export as squiddy names it."""
import glob
import os

from squiddy.config import load_graph

for g in sorted(glob.glob("/Users/brock/GitHub/*/graphs/*/graph.yaml")):
    gd = os.path.dirname(g)
    try:
        graph = load_graph(gd)
        p = graph.path("exports_dir") / f"{graph.engine['export']['artifact_stem']}.json"
        print(gd, "served" if p.is_file() else "NOT served", p.name)
    except (Exception, SystemExit) as exc:  # survey only
        print(gd, "LOAD FAILED", type(exc).__name__, str(exc)[:200])
