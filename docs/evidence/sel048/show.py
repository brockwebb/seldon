"""Print runs.jsonl as one short line per run: run, wall s, 1-min load before, passed, failed, failed ids, summary."""
import json
from pathlib import Path

for line in (Path(__file__).resolve().parent / "runs.jsonl").read_text().splitlines():
    r = json.loads(line)
    print(r["run"], r["wall_s"], r["load_before"][0], r["passed"], r["failed"], r["failed_ids"], "|", r["summary"])
