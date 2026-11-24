"""SEL-043 Part A: each dispatching repository's dispatch mode, environment and gate (read only)."""
import json, sys
from pathlib import Path
import yaml

ROOT = Path("/Users/brock/GitHub")
REPOS = ["seldon", "squiddy", "hazbrief-mcp", "aacps-ai-policy", "factory", "ai-readiness-kg"]
out = {}
for r in REPOS:
    p = ROOT / r / "seldon.yaml"
    if not p.is_file():
        out[r] = "no seldon.yaml"; continue
    c = yaml.safe_load(p.read_text()) or {}
    d = c.get("dispatch") or {}
    st = d.get("stations") or {}
    env_ref = st.get("environment_ref")
    env = None
    if env_ref:
        path, _, key = env_ref.partition("#")
        data = yaml.safe_load((ROOT / r / path).read_text())
        for k in key.split("."):
            data = data.get(k)
        env = data
    else:
        env = (c.get("decisions") or {}).get("repositories")
    out[r] = {"dispatch": bool(d), "max_parallel": d.get("max_parallel"), "mode": d.get("mode"),
              "worktree": d.get("worktree"), "lease_file": d.get("lease_file"),
              "environment_ref": env_ref, "environment": env,
              "gate_command": d.get("gate_command"), "gate_record": d.get("gate_record"),
              "gate_timeout_s": d.get("gate_timeout_s"),
              "interpreter": st.get("interpreter"),
              "keys": sorted(d)}
print(json.dumps(out, indent=1, default=str))
