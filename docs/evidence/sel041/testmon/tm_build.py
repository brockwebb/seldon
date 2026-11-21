"""SEL-041 Part C, the testmon arm: build testmon's dependency map on seldon's own suite in a shared clone of this
branch under /tmp (so seeded edits never touch the worktree), at -n 6 (xdist). Siblings are symlinked beside the clone
so `../squiddy` resolves as it does in the primary. Writes /tmp/sel041/tm_build.txt ending `EXIT=<rc>`."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

WT = Path("/Users/brock/GitHub/seldon/.claude/worktrees/splendid-seeking-russell")
BASE = Path("/tmp/sel041/tmroot")
DST = BASE / "seldon"
PY = "/tmp/sel041/tm/bin/python"
OUT = Path("/tmp/sel041/tm_build.txt")

if not DST.exists():
    BASE.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--shared", str(WT), str(DST)], check=True)
    for sib in Path("/Users/brock/GitHub").iterdir():
        if sib.is_dir() and sib.name != "seldon" and not (BASE / sib.name).exists():
            (BASE / sib.name).symlink_to(sib)
    shutil.copy2(Path("/Users/brock/GitHub/seldon/.env"), DST / ".env")
env = {**os.environ, "PYTHONPATH": str(DST), "SELDON_PRIMARY_CHECKOUT": str(DST)}
args = sys.argv[1:] or ["-n", "6"]
with OUT.open("w") as fh:
    r = subprocess.run([PY, "-m", "dotenv", "-f", ".env", "run", "--", PY, "-m", "pytest", "tests/", "-q",
                        "--testmon", *args], cwd=DST, env=env, stdout=fh, stderr=subprocess.STDOUT)
    fh.write(f"\nEXIT={r.returncode}\n")
