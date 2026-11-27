"""SEL-055 Part B: what the selected gate would have cost for each of the last 20 merges, against the full gate.

Per-file test seconds come from a junit XML of a whole run (seldon: this task's baseline, -n 6, under load; hazbrief:
HB-230's step-1 map build, under testmon, so its seconds are inflated alike for every file: only shares are used). A
scoped plan's cost is estimated as its files' share of the run's summed test seconds times the full gate's wall
seconds; a full plan costs the full gate. Measured scoped gates are reported beside the estimate where one exists.
Writes /tmp/sel055/timing_<repo>.json and prints a table."""
import json
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

REPO = sys.argv[1]
JUNIT = {"seldon": "/tmp/sel055/base_junit.xml", "hazbrief": "/tmp/hb230/build/step1.xml"}[REPO]
# The full gate's wall seconds: seldon, this task's baseline run (2,408 s at load 50 to 60); hazbrief, the median of its
# merge_gate and cli full runs on record since 2026-11-25 (gate_run records).
FULL_S = {"seldon": 2408.0, "hazbrief": None}[REPO]
if FULL_S is None:
    secs = []
    with open("/Users/brock/GitHub/hazbrief-mcp/seldon_events.jsonl") as fh:
        for line in fh:
            if '"gate_run"' not in line:
                continue
            p = json.loads(line).get("payload") or {}
            if p.get("tier") == "full" and p.get("outcome") == "pass" and p.get("wall_seconds"):
                secs.append(float(p["wall_seconds"]))
    FULL_S = statistics.median(secs)

per_file = defaultdict(float)
for tc in ET.parse(JUNIT).getroot().iter("testcase"):
    cls = tc.get("classname") or ""
    f = tc.get("file") or ("tests/" + cls.split(".")[1] + ".py" if cls.startswith("tests.") else None)
    if f:
        per_file[f] += float(tc.get("time") or 0)
total = sum(per_file.values())
rows = json.loads(Path(f"/tmp/sel055/replay_{REPO}_new.json").read_text())
out = []
for r in rows:
    if r.get("error"):
        continue
    if r["tier"] == "scoped":
        share = sum(per_file.get(t, 0.0) for t in r["tests"]) / total
        est = share * FULL_S
    else:
        share, est = 1.0, FULL_S
    out.append({"task": Path(r["source_file"]).stem[11:60], "tier": r["tier"], "files": r["files_selected"],
                "of": r["files_total"], "share": round(share, 4), "est_s": round(est), "full_s": round(FULL_S),
                "recorded": r["recorded"]})
    print(f"{out[-1]['task'][:45]:45} {r['tier']:6} {r['files_selected']:4}/{r['files_total']:<4} share={share:6.3f} "
          f"est={est:7.0f}s full={FULL_S:7.0f}s recorded={r['recorded']['gate_tier']}:{r['recorded']['gate_seconds']}")
tot_sel = sum(x["est_s"] for x in out)
print(f"sum selected {tot_sel} s against sum full {round(FULL_S) * len(out)} s over {len(out)} merges; "
      f"junit total {total:.0f} test-seconds over {len(per_file)} files")
Path(f"/tmp/sel055/timing_{REPO}.json").write_text(json.dumps({"full_s": FULL_S, "rows": out}, indent=1))
