"""SEL-055 Part B: tests that join the REAL repository root to a sliced directory (`<root> / "cc_tasks"`, or a root string
`"cc_tasks/..."` read relative to the repository), against the slices' lists. Root expressions: parents[1],
parent.parent, and module names bound to one (REPO_ROOT, REPO, SELDON, ROOT)."""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(sys.argv[1])
doc = yaml.safe_load((ROOT / "seldon.yaml").read_text())["dispatch"]["gate"]
slices = {s["name"]: s for s in doc["slices"]}
DIR_OF = {"cc_tasks": "task_records", "handoffs": "task_records", "docs": "documents", "governed": "ledgers",
          "state": "ledgers", "graphs": "graphs", "seldon_events.jsonl": "event_store"}
for f in sorted((ROOT / "tests").glob("test_*.py")):
    text = f.read_text(errors="replace")
    roots = {m.group(1) for m in re.finditer(r"^([A-Z_][A-Z0-9_]*)\s*=\s*.*(?:parents\[1\]|parent\.parent)", text, re.M)}
    alt = "|".join([r"parents\[1\]\)?", r"parent\.parent\)?"] + sorted(map(re.escape, roots)))
    rx = re.compile(rf"(?:{alt})\s*/\s*[\"'](cc_tasks|handoffs|docs|governed|state|graphs|seldon_events\.jsonl)")
    found = sorted(set(rx.findall(text)))
    for d in found:
        sl = DIR_OF[d]
        listed = slices[sl]["tests"] if slices[sl]["tests"] != "none" else []
        rel = f"tests/{f.name}"
        print(f"{'listed ' if rel in listed else 'MISSING'}\t{sl:13}\t{d:20}\t{rel}")
