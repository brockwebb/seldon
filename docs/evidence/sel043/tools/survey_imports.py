"""SEL-043 Part A(1): for each consumer's interpreter, where seldon and squiddy import from, and how installed."""
import json, subprocess
from pathlib import Path

ROOT = Path("/Users/brock/GitHub")
PROBE = r'''
import json, importlib.metadata as md, importlib.util as u
out = {}
for name in ("seldon", "squiddy"):
    spec = u.find_spec(name)
    row = {"origin": spec.origin if spec else None}
    try:
        d = md.distribution(name)
        row["version"] = d.version
        du = d.read_text("direct_url.json")
        row["direct_url"] = json.loads(du) if du else None
    except md.PackageNotFoundError:
        row["installed"] = False
    out[name] = row
print(json.dumps(out))
'''
PYS = {
    "seldon (dispatcher's interpreter, PATH python)": ("python3", ROOT / "seldon"),
    "squiddy (.venv)": (str(ROOT / "squiddy/.venv/bin/python"), ROOT / "squiddy"),
    "hazbrief-mcp (.venv, uv run)": (str(ROOT / "hazbrief-mcp/.venv/bin/python"), ROOT / "hazbrief-mcp"),
    "aacps-ai-policy (gate names squiddy's .venv)": (str(ROOT / "squiddy/.venv/bin/python"), ROOT / "aacps-ai-policy"),
    "factory (.venv if any)": (str(ROOT / "factory/.venv/bin/python"), ROOT / "factory"),
}
res = {}
for label, (py, cwd) in PYS.items():
    if py != "python3" and not Path(py).exists():
        res[label] = f"no interpreter at {py}"; continue
    import shutil
    exe = shutil.which("python") if py == "python3" else py
    p = subprocess.run([exe, "-I", "-c", PROBE], capture_output=True, text=True, cwd="/tmp")
    res[label] = {"python": exe, "out": json.loads(p.stdout) if p.returncode == 0 else p.stderr[-400:]}
print(json.dumps(res, indent=1))
