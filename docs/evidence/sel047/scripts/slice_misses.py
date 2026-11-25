"""SEL-047 Part D: what the gate slices miss, over every task merge on seldon's main since 2026-10-25.

The dispatcher lands a task by rebase and fast-forward, so `git log --first-parent main` holds no merge commits (721
single-parent commits since 2026-10-25). The task merges are read from main's reflog instead: each
`merge worktree-<name>: Fast-forward` entry names the merged tip, and the reflog entry before it is the main tip it
was merged onto (its first parent in the task's sense). The branch is mapped to its task through the dispatcher's
`dispatch_finished` records.

For each merge, a scratch worktree is added at the tip (`git worktree add --detach`, under a temporary directory
outside the repository) and two plans are read, then the scratch worktree is removed:

- `literal`: `python -m seldon gate plan --base <prev> --json`, run in the scratch worktree with this worktree's code
  first on PYTHONPATH, exactly as the task says. It reads the commit's own seldon.yaml, so a merge before SEL-041
  (no `dispatch.gate.slices`) plans `no_slices`.
- `today`: the same diff planned against today's gate block (this worktree's seldon.yaml, main at e42c25b), with the
  event store cut at the merge's own time, so the cadence reason is the one that merge would have seen.

Writes docs/evidence/sel047/slice_misses.json (one row per merge) and prints the prefix counts. Reads only; no
model or network calls. Resumes by skipping merges already in the output (rows written per merge).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from seldon.config import load_project_config  # noqa: E402
from seldon.core import dispatch as D  # noqa: E402
from seldon.core import gate_plan as GP  # noqa: E402
from seldon.core.events import read_events  # noqa: E402

OUT = ROOT / "docs/evidence/sel047/slice_misses.json"
SINCE = "2026-10-25"
PRIMARY = Path(os.environ["SELDON_PRIMARY_CHECKOUT"])
MERGE = re.compile(r"^merge (worktree-[\w-]+): Fast-forward$")


def git(*args, cwd=ROOT) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def merges() -> list:
    lines = git("reflog", "show", "main", "--date=iso-strict", "--format=%H|%gd|%gs").splitlines()
    rows = []
    for i, line in enumerate(lines):
        sha, gd, gs = line.split("|", 2)
        m = MERGE.match(gs)
        if not m or i + 1 >= len(lines):
            continue
        when = gd[gd.index("{") + 1:-1]
        if when[:10] < SINCE:
            continue
        prev = lines[i + 1].split("|", 1)[0]
        rows.append({"commit": sha, "prev": prev, "branch": m.group(1), "merged_at": when})
    return list(reversed(rows))


def task_of(events: list) -> dict:
    out = {}
    for e in events:
        p = e.get("payload") or {}
        if e.get("event_type") == "dispatch_finished" and p.get("branch") and p.get("outcome") in (
                "merged", "breaker_tripped_merged"):
            out[p["branch"]] = {"task_id": p.get("task_id"), "source_file": p.get("source_file"),
                                "gate": (p.get("merge") or {}).get("gate")}
    return out


def top2(path: str) -> str:
    parts = path.split("/")
    return "/".join(parts[:2]) + ("/" if len(parts) > 2 else "")


def main() -> int:
    events = read_events(PRIMARY)
    tasks = task_of(events)
    cfg = D.load_dispatch_config(ROOT, load_project_config(ROOT))
    gcfg = cfg[GP.CONFIG_KEY]
    rows = json.loads(OUT.read_text()) if OUT.is_file() else []
    have = {r["commit"] for r in rows}
    todo = [m for m in merges() if m["commit"] not in have]
    print(f"{len(todo)} merge(s) to plan, {len(have)} already planned", flush=True)
    scratch_root = Path(tempfile.mkdtemp(prefix="sel047_slices_"))
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    for m in todo:
        t = tasks.get(m["branch"], {})
        row = {**m, "task_id": t.get("task_id"), "task": t.get("source_file"),
               "recorded_gate": t.get("gate"), "changed": None, "literal": None, "today": None}
        tree = scratch_root / m["commit"][:12]
        git("worktree", "add", "--detach", str(tree), m["commit"])
        try:
            # -P: without it `python -m` puts the cwd (the scratch tree, the commit's own seldon) first on sys.path,
            # and a commit before SEL-041 has no `gate` command. The planner is today's; the config is the commit's.
            r = subprocess.run([sys.executable, "-P", "-m", "seldon", "gate", "plan", "--base", m["prev"], "--json"],
                               cwd=tree, env=env, capture_output=True, text=True)
            if r.returncode == 0:
                p = json.loads(r.stdout)
                row["literal"] = {"exit": 0, "tier": p["tier"], "reason": p["reason"], "reasons": p["reasons"],
                                  "unmatched": p["unmatched"], "files_selected": p["files_selected"]}
            else:
                row["literal"] = {"exit": r.returncode, "error": (r.stderr or r.stdout).strip()[-600:]}
            at = datetime.fromisoformat(m["merged_at"])
            cut = [e for e in events if (GP._ts(e) or at) < at]
            p = GP.plan(tree, gcfg, base=m["prev"], gate_command=cfg["gate_command"], events=cut, now=at)
            row["changed"] = p["changed"]
            row["today"] = {"tier": p["tier"], "reason": p["reason"], "reasons": p["reasons"],
                            "unmatched": p["unmatched"], "slices": sorted(p["slices"]),
                            "files_selected": p["files_selected"], "files_total": p["files_total"]}
        finally:
            git("worktree", "remove", "--force", str(tree))
        rows.append(row)
        rows.sort(key=lambda r: r["merged_at"])
        OUT.write_text(json.dumps(rows, indent=1) + "\n")
        print(f"{m['merged_at']} {m['branch']}: literal {row['literal'].get('tier') or row['literal'].get('error')}"
              f" | today {row['today']['tier']} ({row['today']['reason']})", flush=True)
    git("worktree", "prune")
    return 0


if __name__ == "__main__":
    sys.exit(main())
