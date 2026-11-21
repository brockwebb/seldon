"""SEL-041 Part C, the testmon arm's subprocess probe. `seldon hooks pre-commit` (seldon/commands/hooks.py,
`hooks_pre_commit`) runs only inside `git commit` -> .githooks/pre-commit -> `python -m seldon hooks pre-commit`, a
grandchild process of the test. Every test that builds a scaffold project (`make_project`, which installs the commit
gate) and commits runs it that way. Ground truth: test files that call `make_project(` and never name
`hooks_pre_commit` or `pre-commit` (so their only route to the function is the subprocess). Seed the function's body,
ask testmon for its selection, restore the file."""
import json
import os
import re
import subprocess
from pathlib import Path

CLONE = Path("/tmp/sel041/tmroot/seldon")
PY = "/tmp/sel041/tm/bin/python"
env = {**os.environ, "PYTHONPATH": str(CLONE), "SELDON_PRIMARY_CHECKOUT": str(CLONE)}
truth = sorted(str(t.relative_to(CLONE)) for t in (CLONE / "tests").glob("test_*.py")
               if "make_project(" in (txt := t.read_text(encoding="utf-8"))
               and "hooks_pre_commit" not in txt and "pre-commit" not in txt and "pre_commit" not in txt)
path = CLONE / "seldon/commands/hooks.py"
orig = path.read_text(encoding="utf-8")
seeded = orig.replace('    """What .githooks/pre-commit runs. Exit 1 refuses the commit."""\n',
                      '    """What .githooks/pre-commit runs. Exit 1 refuses the commit."""\n    _sel041_seed = 1  # noqa\n', 1)
assert seeded != orig
path.write_text(seeded, encoding="utf-8")
try:
    r = subprocess.run([PY, "-m", "dotenv", "-f", ".env", "run", "--", PY, "-m", "pytest", "tests/", "-q",
                        "--testmon-nocollect", "--testmon", "--collect-only", "-p", "no:randomly"],
                       cwd=CLONE, env=env, capture_output=True, text=True, timeout=1800)
finally:
    path.write_text(orig, encoding="utf-8")
selected = sorted({ln.split("::", 1)[0] for ln in r.stdout.splitlines() if "::" in ln})
hit = [t for t in truth if t in selected]
out = {"truth": truth, "selected": selected, "hit": hit, "miss": sorted(set(truth) - set(hit)), "exit": r.returncode}
json.dump(out, open("/tmp/sel041/tm_sub.json", "w"), indent=1)
print(f"subprocess-only callers {len(truth)}; selected {len(hit)}; testmon selected {len(selected)} files in all; "
      f"misses {len(out['miss'])}: {out['miss'][:10]}")
