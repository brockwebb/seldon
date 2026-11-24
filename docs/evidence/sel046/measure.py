"""SEL-046 Part B: read-only measurement from two git blobs (no other worktree is touched)."""
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from seldon.core import kept_events as K

BRANCH, MAIN = "worktree-cached-noodling-minsky", "main"


def show(ref):
    return subprocess.run(["git", "show", f"{ref}:seldon_events.jsonl"], capture_output=True, text=True,
                          check=True).stdout


tip, main = show(BRANCH), show(MAIN)
counts = Counter((json.loads(l).get("event_id")) for l in tip.splitlines() if l.strip())
twice = {k for k, v in counts.items() if k and v > 1}
with tempfile.TemporaryDirectory() as d:
    (Path(d) / "s.jsonl").write_text(main, encoding="utf-8")
    every = K.reconciled_ids(Path(d), "s.jsonl")
    by_finisher = K.reconciled_ids(Path(d), "s.jsonl", "8315cc7a-7516-4106-9f9c-a9b0acf3f60c")
owners = set()
for l in main.splitlines():
    if '"kept_events_reconciled"' in l:
        p = json.loads(l).get("payload") or {}
        if set(p.get("event_ids") or []) & twice:
            owners.add(p.get("task_id"))
main_ids = {json.loads(l).get("event_id") for l in main.splitlines() if l.strip()}
print(f"ids held twice at {BRANCH} tip: {len(twice)}")
print(f"  of them on main already: {len(twice & main_ids)}")
print(f"  returned by the all-task lookup reconciled_ids(main, store): {len(twice & every)}")
print(f"  not returned: {len(twice - every)}")
print(f"  returned by the old per-finisher lookup (task 8315cc7a, SEL-045R): {len(twice & by_finisher)}")
print(f"  kept_events_reconciled records holding them, by task_id: {sorted(owners)}")
