"""SEL-015 success criteria, run as written; plus ahead-of-origin counts."""
import subprocess

REPOS = ["squiddy", "arnold", "ai-readiness-kg", "hazbrief-mcp"]
rc_all = 0
for repo in REPOS:
    p = f"/Users/brock/GitHub/{repo}"
    for cmd in (["seldon", "hooks", "status", "--repo", p],
                ["git", "-C", p, "ls-files", "--error-unmatch", ".githooks/prepare-commit-msg"],
                ["git", "-C", p, "rev-list", "--count", "--left-right", "origin/main...main"]):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd="/tmp/sel015")
        last = (r.stdout.strip().splitlines() or [""])[-1] if cmd[0] == "git" else ""
        print(f"{repo}: {' '.join(cmd[-3:])} -> exit {r.returncode} {last}")
        if cmd[1] != "-C" or "ls-files" in cmd:
            rc_all |= r.returncode
print("ALL_CHECKS_EXIT", rc_all)
