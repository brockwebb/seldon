"""Run one test on MAIN's code (a /tmp shared clone of the primary), to tell a regression from a load flake."""
import os
import shutil
import subprocess
import sys

PRIMARY = "/Users/brock/GitHub/seldon"
CLONE = "/tmp/sel043/main_clone"
TEST = sys.argv[1]
if os.path.exists(CLONE):
    shutil.rmtree(CLONE)
subprocess.run(["git", "clone", "-q", "--shared", "--branch", "main", PRIMARY, CLONE], check=True)
head = subprocess.run(["git", "-C", CLONE, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout
print("main at", head.strip())
env = {**os.environ, "PYTHONPATH": CLONE}
r = subprocess.run([sys.executable, "-m", "dotenv", "-f", f"{PRIMARY}/.env", "run", "--", sys.executable, "-m",
                    "pytest", "-q", "-p", "no:cacheprovider", TEST], cwd=CLONE, env=env, capture_output=True,
                   text=True)
print(r.stdout[-800:])
print("EXIT", r.returncode)
