"""SEL-015: record each sibling's hook status and porcelain, install, record again.

Usage: python /tmp/sel015/run.py before|install
Writes /tmp/sel015/<repo>.<phase>.txt and prints everything.
"""
import subprocess
import sys

REPOS = ["squiddy", "arnold", "ai-readiness-kg", "hazbrief-mcp"]
ROOT = "/Users/brock/GitHub"


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd="/tmp/sel015")
    return f"$ {' '.join(cmd)}\n{p.stdout}{p.stderr}[exit {p.returncode}]\n", p.returncode


def snapshot(repo, path):
    out = ""
    for cmd in (
        ["seldon", "hooks", "status", "--repo", path],
        ["git", "-C", path, "status", "--porcelain=v1", "--untracked-files=all"],
        ["git", "-C", path, "rev-parse", "HEAD"],
        ["git", "-C", path, "branch", "--show-current"],
        ["git", "-C", path, "config", "--show-origin", "--get-all", "core.hooksPath"],
    ):
        text, _ = run(cmd)
        out += text
    return out


phase = sys.argv[1]
rc_all = 0
for repo in REPOS:
    path = f"{ROOT}/{repo}"
    if phase == "before":
        out = snapshot(repo, path)
    elif phase == "install":
        head, _ = run(["git", "-C", path, "rev-parse", "HEAD"])
        out = head
        text, rc = run(["seldon", "hooks", "install", "--repo", path])
        out += text
        rc_all |= rc
        before_head = head.splitlines()[1].strip()
        text, _ = run(["git", "-C", path, "log", "--stat", "--format=%H %s", f"{before_head}..HEAD"])
        out += text
        out += snapshot(repo, path)
    else:
        sys.exit(f"unknown phase {phase}")
    with open(f"/tmp/sel015/{repo}.{phase}.txt", "w") as f:
        f.write(out)
    print(f"===== {repo} ({phase}) =====\n{out}")
sys.exit(rc_all)
