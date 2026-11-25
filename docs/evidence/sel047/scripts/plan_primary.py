"""SEL-047 Part A item 1: run `seldon gate plan` and `seldon gate plan --json` with the primary checkout as cwd
(reads only), and write both to docs/evidence/sel047/gate_plan_primary.txt."""
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "docs/evidence/sel047/gate_plan_primary.txt"
primary = os.environ["SELDON_PRIMARY_CHECKOUT"]
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=primary, capture_output=True, text=True).stdout.strip()
parts = [f"# SEL-047 Part A item 1: `seldon gate plan` run with cwd {primary} (HEAD {head}) at "
         f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"]
for args in (["seldon", "gate", "plan"], ["seldon", "gate", "plan", "--json"]):
    r = subprocess.run(args, cwd=primary, capture_output=True, text=True)
    parts.append(f"\n$ {' '.join(args)}   (exit {r.returncode})\n{r.stdout}{r.stderr}")
OUT.write_text("".join(parts))
print("".join(parts)[:3000])
