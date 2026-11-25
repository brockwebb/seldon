"""Render Part A's table from survey.json (open = the research domain's open ResearchTask states)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/brock/GitHub/seldon/.claude/worktrees/enchanted-cuddling-cake")
from seldon.core.artifacts import open_states  # noqa: E402
from seldon.domain.loader import load_domain_config  # noqa: E402

dc = load_domain_config(Path("/Users/brock/GitHub/seldon/.claude/worktrees/enchanted-cuddling-cake/seldon/domain/research.yaml"))
OPEN = set(open_states(dc, "ResearchTask"))
rows = json.load(open("/tmp/sel044/survey.json"))
print("| repository | graph | tasks (open) | dispatch block | enabled | launchd job | last pass | last event |")
print("|---|---|---|---|---|---|---|---|")
for r in rows:
    st = r.get("tasks_by_state") or {}
    tot = sum(st.values())
    op = sum(c for s, c in st.items() if s in OPEN)
    print(f"| {r['repo']} | `{r.get('database')}` | {tot} ({op}) | {'yes' if r.get('dispatch_block') else 'no'} | "
          f"{r.get('dispatch_enabled') if r.get('dispatch_block') else '-'} | {', '.join(r.get('plist') or []) or '-'} | "
          f"{(r.get('last_pass_at') or '-')[:19]} | {(r.get('last_event') or '-')[:19]} |")
