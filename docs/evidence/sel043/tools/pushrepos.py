"""Of the refusals, how many named a producer task whose launch declared other repositories to write (push_repos)."""
import json
from pathlib import Path
ROOT = Path("/Users/brock/GitHub")
detail = json.load(open("/tmp/sel043/refusals_detail.json"))
launch = {}
for repo in {d["producer"] for d in detail}:
    for line in (ROOT / repo / "seldon_events.jsonl").read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("event_type") == "dispatch_launched":
            p = e["payload"]
            launch[(repo, p["task_id"][:8])] = [Path(x["repo"]).name for x in p.get("push_repos") or []]
hits = [(d["consumer"], d["producer"], d["producer_task"], launch.get((d["producer"], d["producer_task"])))
        for d in detail if launch.get((d["producer"], d["producer_task"]))]
print(len(detail), "refusals;", len(hits), "named a producer task that declared writes to other repositories")
for h in hits:
    print(h)
