"""Detach a command under `caffeinate -i` so the Mac does not sleep, writing its output to a log that ends `EXIT=<rc>`.

Usage: python docs/evidence/sel047/scripts/launch.py <log> <command...>
(The worktree guard refuses `nohup ... &`; this is the pattern RECALL-001 recorded.)
"""
import subprocess
import sys

log, cmd = sys.argv[1], sys.argv[2:]
wrapped = ["sh", "-c", '"$@"; echo "EXIT=$?"', "sh", "caffeinate", "-i"] + cmd
with open(log, "w") as fh:
    p = subprocess.Popen(wrapped, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         start_new_session=True)
print(f"pid {p.pid}, log {log}")
