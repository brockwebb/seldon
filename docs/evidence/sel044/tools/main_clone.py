"""Run one test on seldon MAIN's code: a shared clone of the primary's main under /tmp, PYTHONPATH = the clone.
Usage: python /tmp/sel044/main_clone.py <test node id>"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

PRIMARY = "/Users/brock/GitHub/seldon"
WT = "/Users/brock/GitHub/seldon/.claude/worktrees/enchanted-cuddling-cake"
clone = Path("/tmp/sel044/mainclone")
if clone.exists():
    shutil.rmtree(clone)
subprocess.run(["git", "clone", "-q", "--shared", "--branch", "main", PRIMARY, str(clone)], check=True)
head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
for sib in ("squiddy", "arnold"):
    link = clone.parent / sib
    if not link.exists():
        link.symlink_to(f"/Users/brock/GitHub/{sib}")
env = {**os.environ, **{k: v for k, v in dotenv_values(f"{WT}/.env").items() if v is not None},
       "PYTHONPATH": str(clone)}
r = subprocess.run([sys.executable, "-m", "pytest", sys.argv[1], "-q", "-p", "no:cacheprovider"], cwd=clone, env=env,
                   capture_output=True, text=True)
print(f"main {head}")
print(r.stdout[-1500:])
print(f"EXIT={r.returncode}")
