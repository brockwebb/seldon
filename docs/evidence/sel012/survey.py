"""SEL-012: read-only survey of the five governed repositories' hook configuration."""
import subprocess
from pathlib import Path

ROOT = Path("/Users/brock/GitHub")
REPOS = ["seldon", "squiddy", "arnold", "ai-readiness-kg", "hazbrief-mcp"]


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


for name in REPOS:
    r = ROOT / name
    print(f"== {name}")
    print("  hooksPath:", git(r, "config", "--show-scope", "--show-origin", "--get-all", "core.hooksPath")[1])
    print("  seldon.python:", git(r, "config", "--get", "seldon.python")[1])
    print("  branch:", git(r, "rev-parse", "--abbrev-ref", "HEAD")[1], git(r, "rev-parse", "--short", "HEAD")[1])
    print("  status:", git(r, "status", "--porcelain")[1].splitlines()[:8])
    print("  tracked .githooks:", git(r, "ls-files", ".githooks")[1].split())
    print("  on-disk .githooks:", sorted(p.name for p in (r / ".githooks").glob("*")) if (r / ".githooks").is_dir() else None)
    print("  worktrees:", len(git(r, "worktree", "list")[1].splitlines()))
    y = r / "seldon.yaml"
    print("  seldon.yaml pass_ledger:", "pass_ledger:" in y.read_text() if y.is_file() else "no seldon.yaml")
