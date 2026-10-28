"""SEL-012 Part B rehearsal: `seldon hooks install` (this branch's code) in a scratch clone of each sibling, with
the primary's untracked .githooks files copied in, so the clone is in the primary's hook state. Prints what the
install commits and whether the clone is clean after. Touches no sibling repository."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

WT = "/Users/brock/GitHub/seldon/.claude/worktrees/flickering-prancing-stream"
GH = Path("/Users/brock/GitHub")
BASE = Path("/tmp/sel012/rehearse")
env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
env["PYTHONPATH"] = WT


def run(argv, cwd):
    r = subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


if BASE.exists():
    shutil.rmtree(BASE)
BASE.mkdir(parents=True)
for sib in ("seldon", "squiddy", "arnold", "ai-readiness-kg", "hazbrief-mcp", "wintermute"):
    if (GH / sib).is_dir():
        (BASE / sib).symlink_to(GH / sib)
rc_all = 0
for name in ("squiddy", "arnold", "ai-readiness-kg", "hazbrief-mcp"):
    clone = BASE / f"{name}"
    (BASE / name).unlink()
    print(f"== {name}")
    print(" ", run(["git", "clone", "-q", str(GH / name), str(clone)], BASE))
    for p in (GH / name / ".githooks").glob("*"):
        if not (clone / ".githooks" / p.name).exists():
            shutil.copy2(p, clone / ".githooks" / p.name)
            print(f"  copied untracked .githooks/{p.name} from the primary")
    rc, out = run([sys.executable, "-m", "seldon", "hooks", "install", "--repo", str(clone)], clone)
    print(f"  install exit {rc}:\n    " + out.replace("\n", "\n    "))
    rc_all |= rc
    print("  last commit:", run(["git", "show", "--stat", "--format=%h %s", "HEAD"], clone)[1].replace("\n", " | "))
    rc, out = run([sys.executable, "-m", "seldon", "hooks", "status", "--repo", str(clone)], clone)
    print(f"  status exit {rc}:", " ".join(out.split()))
    rc_all |= rc
    print("  porcelain after:", repr(run(["git", "status", "--porcelain"], clone)[1]))
raise SystemExit(rc_all)
