"""SEL-044 Part D: time `seldon go --portfolio --brief` over the nine rows of factory/registry.md, with the branch's
code, from a scratch portfolio project under /tmp (factory is read, never written). Prints the brief and the time."""
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml
from dotenv import dotenv_values

WT = "/Users/brock/GitHub/seldon/.claude/worktrees/enchanted-cuddling-cake"
G = "/Users/brock/GitHub"
port = Path("/tmp/sel044/port")
port.mkdir(parents=True, exist_ok=True)
nine0 = {"seldon": f"{G}/seldon", "squiddy": f"{G}/squiddy", "hazbrief-mcp": f"{G}/hazbrief-mcp",
        "ai-readiness-kg": f"{G}/ai-readiness-kg", "icsp_notebook": f"{G}/icsp_notebook", "arnold": f"{G}/arnold",
        "aacps-ai-policy": f"{G}/aacps-ai-policy", "authoring": f"{G}/authoring", "factory": f"{G}/factory"}
import glob
nine = {Path(p).parent.name: str(Path(p).parent) for p in sorted(glob.glob(G + "/*/seldon.yaml")) if "-wt-" not in p}
extra = dict(p.split("=", 1) for p in sys.argv[1:])
block = {"repositories": nine}
for k, v in extra.items():
    block[k] = int(v)
(port / "seldon.yaml").write_text(yaml.safe_dump({
    "project": {"name": "portfolio-trial", "domain": "research", "slug": "portfolio-trial"},
    "neo4j": {"database": "seldon-factory", "uri": "bolt://localhost:7687"},
    "event_store": {"path": "seldon_events.jsonl"},
    "portfolio": block}, sort_keys=False), encoding="utf-8")
env = {**os.environ, **{k: v for k, v in dotenv_values(f"{WT}/.env").items() if v is not None}, "PYTHONPATH": WT}
t0 = time.monotonic()
r = subprocess.run([sys.executable, "-m", "seldon", "go", "--portfolio", "--brief"], cwd=port, env=env,
                   capture_output=True, text=True)
wall = time.monotonic() - t0
print(r.stdout)
print(r.stderr[-3000:], file=sys.stderr)
print(f"EXIT={r.returncode} wall={wall:.2f}s settings={block.get('max_workers', 'default')}")
