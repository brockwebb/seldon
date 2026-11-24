"""SEL-045 Part B item 6: what the gate planner would run for hazbrief-mcp as it stands (a gate_command, no slices).

Reads only. Run with the current directory at a `git clone --shared` of hazbrief-mcp's main and PYTHONPATH at this
seldon checkout. It builds the plan exactly as `seldon gate plan --json` does (seldon/commands/gate.py `_context`),
asks the runner which steps it would run (`gate_plan._steps`, the function `gate_plan.run` calls), and compares the
full step's command byte for byte with `dispatch.gate_command` read straight from hazbrief's seldon.yaml by a plain
YAML load, independent of seldon's config loader. Nothing is run.

    python <this file> <out.json>
"""
import json
import sys
from pathlib import Path

import yaml

from seldon.commands.gate import _context
from seldon.core import gate_plan as GP


def main(out: Path) -> int:
    ctx = _context(None, None, False)
    plan = ctx["plan"]
    steps = GP._steps(plan, ctx["gcfg"], ctx["cfg"]["gate_command"])
    raw = yaml.safe_load((Path.cwd() / "seldon.yaml").read_text(encoding="utf-8"))["dispatch"]["gate_command"]
    would_run = steps[0][1] if len(steps) == 1 and steps[0][0] == "full" else None
    doc = {
        "repository": "hazbrief-mcp",
        "clone_head": plan["commit"],
        "slices_declared": GP.declared(ctx["gcfg"]),
        "plan": plan,
        "steps": [list(s) for s in steps],
        "gate_command_in_seldon_yaml": raw,
        "would_run_equals_gate_command_bytes": would_run is not None
        and would_run.encode("utf-8") == raw.encode("utf-8"),
    }
    out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"tier={plan['tier']} reason={plan['reason']} steps={len(steps)} "
          f"byte_equal={doc['would_run_equals_gate_command_bytes']}")
    return 0 if (plan["tier"], plan["reason"], doc["would_run_equals_gate_command_bytes"]) == (
        "full", "no_slices", True) else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
