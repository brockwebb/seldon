"""RECALL-002R Part B: the recall step `seldon cc register` runs (seldon/commands/cc.py lines 1379-1506), read-only.

Same calls in the same order (settings -> recall -> render) minus `record_listed` and the registration itself, so
nothing is written to any repository. One existing task file per repository.
"""
import sys
import time
from pathlib import Path

import yaml

from seldon.core import recall as R

CASES = [
    ("/Users/brock/GitHub/squiddy",
     "cc_tasks/2026-10-24_SQ-087_the_served_recall_indexes_rebuilt_under_the_current_index_rule.md"),
    ("/Users/brock/GitHub/arnold", "cc_tasks/2026-10-22_workout-start-time.md"),
    ("/Users/brock/GitHub/ai-readiness-kg",
     "cc_tasks/2026-10-21_fcsm_concern_edges_and_sixteen_checks_one_pager.md"),
]

rc = 0
for root, rel in CASES:
    project_dir = Path(root)
    config = yaml.safe_load((project_dir / "seldon.yaml").read_text(encoding="utf-8")) or {}
    print(f"=== {project_dir.name}  {rel}")
    s = R.settings(config)
    if s is None:
        print("Recall: not configured (seldon.yaml has no `recall:` block; RECALL-001)")
        rc = 1
        continue
    text = (project_dir / rel).read_text(encoding="utf-8")
    t0 = time.time()
    found = R.recall(project_dir, config, text, task_stem=Path(rel).stem, task_id=None)
    print(R.render(found))
    print(f"[{time.time() - t0:.1f} s]")
sys.exit(rc)
