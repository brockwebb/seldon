"""SEL-041 Part C, the testmon arm: twenty single-function changes seeded into the /tmp clone whose testmon map
tm_build.py built, and for each, whether testmon selects the test file that calls the function directly.

Ground truth per seed: the test files that call the function by name (`name(` in a test file that also names its
module). A seed is a no-op statement added as the function's first line; testmon tracks executed lines and method
fingerprints, so a change inside a function a test executed must select that test. Selection is read with
`--testmon-nocollect --collect-only -q` (select, do not record), and the file is restored after each seed.

Seeds are picked deterministically: functions in seldon/core and seldon/commands with 1 to 3 calling test files,
sorted, every k-th; then the remainder from functions whose callers run them only through a subprocess
(`python -m seldon ...` from a git hook), if any are found. Output: /tmp/sel041/tm_seeds.json and a table.
"""
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CLONE = Path("/tmp/sel041/tmroot/seldon")
PY = "/tmp/sel041/tm/bin/python"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
env = {**os.environ, "PYTHONPATH": str(CLONE), "SELDON_PRIMARY_CHECKOUT": str(CLONE)}

tests = {p: p.read_text(encoding="utf-8") for p in (CLONE / "tests").glob("test_*.py")}
cands = []
for sub in ("seldon/core", "seldon/commands"):
    for mod in sorted((CLONE / sub).glob("*.py")):
        tree = ast.parse(mod.read_text(encoding="utf-8"))
        modname = mod.stem
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name.startswith("__"):
                continue
            pat = re.compile(rf"\b{re.escape(node.name)}\(")
            callers = sorted(str(t.relative_to(CLONE)) for t, txt in tests.items()
                             if pat.search(txt) and modname in txt)
            if 1 <= len(callers) <= 3 and len(node.body) > 1:
                cands.append({"file": str(mod.relative_to(CLONE)), "func": node.name, "line": node.body[0].lineno,
                              "col": node.body[0].col_offset, "callers": callers})
k = max(1, len(cands) // N)
seeds = cands[::k][:N]
print(f"{len(cands)} candidate functions; seeding {len(seeds)} (every {k}th)", flush=True)
rows = []
for s in seeds:
    path = CLONE / s["file"]
    orig = path.read_text(encoding="utf-8")
    lines = orig.split("\n")
    # Insert before the body's first statement, at its indentation. A docstring first statement is skipped over.
    i = s["line"] - 1
    indent = " " * s["col"]
    lines.insert(i, f"{indent}_sel041_seed = 1  # noqa")
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        r = subprocess.run([PY, "-m", "dotenv", "-f", ".env", "run", "--", PY, "-m", "pytest", "tests/", "-q",
                            "--testmon-nocollect", "--testmon", "--collect-only", "-p", "no:randomly"],
                           cwd=CLONE, env=env, capture_output=True, text=True, timeout=1800)
    finally:
        path.write_text(orig, encoding="utf-8")
    selected = sorted({ln.split("::", 1)[0] for ln in r.stdout.splitlines() if "::" in ln})
    hit = [c for c in s["callers"] if c in selected]
    row = {**s, "selected_files": len(selected), "callers_selected": hit,
           "miss": sorted(set(s["callers"]) - set(hit)), "exit": r.returncode,
           "tail": r.stdout.strip().splitlines()[-1:] + r.stderr.strip().splitlines()[-2:]}
    rows.append(row)
    print(f"{s['file']}:{s['func']} callers {len(s['callers'])} selected {len(hit)} of them; "
          f"{len(selected)} files selected; miss {row['miss']}", flush=True)
    json.dump(rows, open("/tmp/sel041/tm_seeds.json", "w"), indent=1)
misses = sum(1 for r in rows if r["miss"])
print(f"SEEDS {len(rows)} MISSES {misses}")
