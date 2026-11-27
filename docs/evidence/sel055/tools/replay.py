"""SEL-055 Part B: for each of a repository's last 20 merged tasks, what the gate planner selects for the change the
merge brought to main, under today's declared `dispatch.gate` (read-only: a shared clone under /tmp, one detached
checkout moved from tip to tip).

The change a merge brought is `prev_main..tip`, where `prev_main` is main before the fast-forward (the reflog entry
before `merge <branch>: Fast-forward`) and `tip` is `merge.commit` of the `dispatch_finished` record.

Usage: python replay.py <seldon|hazbrief> <mode>   mode: old (cadence promotes, as main does today) | new (no cadence
promotion: R38) . Prints a TSV row per task and writes /tmp/sel055/replay_<repo>_<mode>.json.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = sys.argv[1]
MODE = sys.argv[2]
SRC = {"seldon": Path("/Users/brock/GitHub/seldon"), "hazbrief": Path("/Users/brock/GitHub/hazbrief-mcp")}[REPO]
CLONE = {"seldon": Path("/tmp/sel055/clone/seldon"), "hazbrief": Path("/tmp/sel055/hzclone/hazbrief-mcp")}[REPO]
WTREE = Path(f"/tmp/sel055/replay_wt_{REPO}")
# Today's declaration: seldon's from this branch (the worktree's seldon.yaml), hazbrief's from its main.
CONF = {"seldon": Path("/Users/brock/GitHub/seldon/.claude/worktrees/ethereal-enchanting-valiant/seldon.yaml"),
        "hazbrief": SRC / "seldon.yaml"}[REPO]
sys.path.insert(0, "/Users/brock/GitHub/seldon/.claude/worktrees/ethereal-enchanting-valiant")
from seldon.core import gate_plan as GP  # noqa: E402


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {args} failed: {r.stderr}")
    return r.stdout


if not CLONE.exists():
    CLONE.parent.mkdir(parents=True, exist_ok=True)
    git(CLONE.parent, "clone", "-q", "--shared", "--no-checkout", str(SRC), str(CLONE))
if not WTREE.exists():
    git(CLONE, "worktree", "add", "-q", "--detach", str(WTREE), "HEAD")

# main's reflog in the SOURCE repository: `<sha> main@{n}: merge <branch>: Fast-forward`; the next older line is the
# main the branch was fast-forwarded from.
log = git(SRC, "reflog", "show", "--format=%H %gs", "main").splitlines()
prev_of = {}
for i, line in enumerate(log):
    sha, _, subject = line.partition(" ")
    if subject.startswith("merge ") and "Fast-forward" in subject and i + 1 < len(log):
        prev_of[sha] = log[i + 1].split(" ", 1)[0]

doc = yaml.safe_load(CONF.read_text())["dispatch"]
gcfg = GP.load_gate_config(doc.get("gate"), doc.get("gate_command"))
merges = json.loads(Path(f"/tmp/sel055/merges_{REPO}.json").read_text())
now = datetime.now(timezone.utc)
# `new`: a passing full gate recorded a moment ago, so the cadence never promotes (R38 takes the cadence off the
# merge round). `old`: no record, so every plan with no other reason is `cadence_due`, as a day without a scheduled
# full gate leaves main today.
events = [] if MODE == "old" else [{"event_type": "gate_run", "timestamp": now.isoformat(),
                                     "payload": {"tier": "full", "outcome": "pass", "failed_files": []}}]
out = []
for m in merges:
    tip = m["commit"]
    prev = prev_of.get(tip)
    row = {"task_id": m["task_id"], "source_file": m["source_file"], "tip": tip, "prev_main": prev,
           "lane": m["lane"], "recorded": {k: m[k] for k in ("evidence", "gate_tier", "gate_reason", "gate_seconds")}}
    if prev is None:
        row["error"] = "tip not found in main's reflog as a fast-forward"
        out.append(row)
        print(f"{m['task_id'][:8]}\tNO_REFLOG")
        continue
    git(WTREE, "checkout", "-q", "--detach", "--force", tip)
    p = GP.plan(WTREE, gcfg, base=prev, gate_command=doc.get("gate_command"), events=events, now=now)
    row.update({"changed": p["changed"], "tier": p["tier"], "reason": p["reason"], "reasons": p["reasons"][:20],
                "n_reasons": len(p["reasons"]), "slices": sorted(p["slices"]), "unmatched": p["unmatched"],
                "tests": p["tests"], "markers": p["markers"], "commands": p["commands"],
                "files_selected": p["files_selected"], "files_total": p["files_total"]})
    out.append(row)
    print(f"{m['task_id'][:8]}\t{Path(m['source_file']).stem[11:45]}\tchanged={len(p['changed'])}\t{p['tier']}\t"
          f"{p['files_selected']}/{p['files_total']}\t{p['reason'][:70]}")
Path(f"/tmp/sel055/replay_{REPO}_{MODE}.json").write_text(json.dumps(out, indent=1))
