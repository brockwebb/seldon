"""SEL-012 Part C: in a scratch clone of squiddy, fork the pass ledger on a rebase and show seldon's
prepare-commit-msg hook refuses it (DN-052 R-237), then show main's side plus the pass recorded again goes through.

The scratch clone runs this branch's seldon (PYTHONPATH = the SEL-012 worktree), i.e. the state every
governed repository is in once this branch is on main and `seldon hooks install` has run there.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

WT = Path("/Users/brock/GitHub/seldon/.claude/worktrees/flickering-prancing-stream")
SRC = Path("/Users/brock/GitHub/squiddy")
CLONE = Path("/tmp/sel012/partc/squiddy")
LEDGER = "kit/ledger/passes.jsonl"
LOG = Path("/tmp/sel012/partc.log")

env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
env["PYTHONPATH"] = str(WT)
env["GIT_EDITOR"] = "true"
out = LOG.open("w")


def say(s):
    print(s)
    out.write(s + "\n")
    out.flush()


def run(argv, cwd=CLONE, check=True, show=True):
    r = subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True, text=True)
    if show:
        say(f"$ {' '.join(argv)}")
        for line in (r.stdout + r.stderr).rstrip().splitlines():
            say(f"  {line}")
        say(f"  [exit {r.returncode}]")
    if check and r.returncode != 0:
        raise SystemExit(f"step failed: {argv}")
    return r


def git(*args, check=True, show=True):
    return run(["git", "-c", "user.email=sel012@scratch", "-c", "user.name=SEL-012 scratch", *args],
               check=check, show=show)


RECORD = """
import sys, datetime
from pathlib import Path
from squiddy import kitpass
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
ev = kitpass.record({"commit": sys.argv[1], "package_tree": "0" * 40, "seeds": [1], "runs": 1, "passed": True,
                     "started_utc": now, "finished_utc": now, "note": "SEL-012 scratch, not a real pass"},
                    Path("kit/ledger/passes.jsonl"))
print("recorded", ev["etype"] if "etype" in ev else ev.get("type"), "for", sys.argv[1][:12])
"""


def record(label):
    head = git("rev-parse", "HEAD", show=False).stdout.strip()
    run([sys.executable, "-c", RECORD, head])
    say(f"  ({label})")


if CLONE.parent.exists():
    shutil.rmtree(CLONE.parent)
CLONE.parent.mkdir(parents=True)
# relative refs (`../seldon/seldon.yaml#prior_art`) resolve beside the checkout: the siblings, read only
for sib in ("seldon", "arnold", "ai-readiness-kg", "hazbrief-mcp", "wintermute"):
    if (SRC.parent / sib).is_dir():
        (CLONE.parent / sib).symlink_to(SRC.parent / sib)
say(f"seldon under test: {WT} @ " + subprocess.run(["git", "-C", str(WT), "rev-parse", "--short", "HEAD"],
                                                  capture_output=True, text=True).stdout.strip())
run(["git", "clone", "-q", str(SRC), str(CLONE)], cwd=CLONE.parent)
git("log", "--oneline", "-1")
n_main = len([ln for ln in (CLONE / LEDGER).read_text().splitlines() if ln.strip()])
say(f"main's ledger: {n_main} line(s)")
run([sys.executable, "-m", "seldon", "hooks", "install", "--repo", str(CLONE)])
run([sys.executable, "-m", "seldon", "hooks", "status", "--repo", str(CLONE)])

say("\n## the branch records a pass chained onto main's last line")
git("checkout", "-q", "-b", "sel012-fork")
record("branch line")
git("commit", "-qam", "scratch: a kit pass on the branch")

say("\n## main moves on: another pass chained onto the same line")
git("checkout", "-q", "main")
record("main line")
git("commit", "-qam", "scratch: a kit pass on main")
git("update-ref", "refs/remotes/origin/main", "HEAD")

say("\n## rebase the branch onto main; resolve the ledger conflict to the BRANCH's side (the SQ-021M2 mistake)")
git("checkout", "-q", "sel012-fork")
git("rebase", "main", check=False)
git("checkout", "--theirs", "--", LEDGER)
git("add", LEDGER)
r = git("rebase", "--continue", check=False)
refused = r.returncode != 0 and "pass_ledger_forked" in r.stderr
say(f"\nREFUSED at rebase --continue with pass_ledger_forked: {refused}")

say("\n## the right resolution: take main's side and record the pass again")
# HEAD during a rebase is the onto commit, main's side; `--ours` reads the index once the conflict was added
git("checkout", "HEAD", "--", LEDGER)
record("branch line recorded again onto main's last")
git("add", LEDGER)
r2 = git("rebase", "--continue", check=False)
ok = r2.returncode == 0
say(f"\nACCEPTED after main's side plus the pass recorded again: {ok}")
git("log", "--oneline", "-3")
out.close()
raise SystemExit(0 if (refused and ok) else 1)
