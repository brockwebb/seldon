"""PRUNE-002 Part B step 3: one instruction-context reading for this checkout, as the dispatcher records it.

Usage: python scripts/prune002/reading.py [STANDARDS_PATH]

A worktree does not resolve `~/GitHub/CLAUDE.md` from the package location (`seldon.paths.system_standards_candidates`
walks up from the checkout), so the standards file can be named; the dispatcher runs in the primary checkout,
where it resolves without help. The checkout this script sits in is imported, not an installed copy.
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
if len(sys.argv) > 1:
    os.environ["SELDON_SYSTEM_CLAUDE_MD"] = sys.argv[1]
from seldon.core import instruction_context as IC  # noqa: E402

print(json.dumps(IC.measure(REPO), indent=1))
