"""SEL-042 Part B: cut the fixture of HB-197's and HB-198's ends from hazbrief-mcp's event store (read only).

Writes `tests/fixtures/sel042/hb197_hb198_events.jsonl`: for each task, its launch's c12 disk reading, the dispatcher's
hard stop, the `andon_halted` that delivered it, the Stop gate's record and the `dispatch_finished` that merged it,
with every field the tests and the RESULT read and nothing else (`dispatch_finished` loses its 40-path
`discarded_ignored` list and its model receipt). Run from the seldon checkout:

    python docs/evidence/sel042/cut_fixture.py /Users/brock/GitHub/hazbrief-mcp/seldon_events.jsonl
"""
import json
import sys
from pathlib import Path

#: hazbrief's event ids (filing `2026-11-18_filing_from_hazbrief_two_tasks_stopped_...`; its store, 2026-11-18).
WANTED = {
    "HB-197": ["063a6d1a", "c3163e6c", "0406da34", "37465e8c", "fa01658b", "e214e7d7"],
    "HB-198": ["5782cbf6", "5d755186", "ccf4bb27", "b33be2ca", "22ca77f9", "b650f591"],
}
OUT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sel042" / "hb197_hb198_events.jsonl"


def cut(e: dict) -> dict:
    p = dict(e.get("payload") or {})
    if e["event_type"] == "dispatch_launched":
        p = {"task_id": p["task_id"], "child_session_id": p["child_session_id"],
             "criteria": {"c12": p["criteria"]["c12"]}}
    elif e["event_type"] == "dispatch_finished":
        merge = {k: v for k, v in (p.get("merge") or {}).items() if k in ("commit", "attempts", "regated", "gate")}
        p = {k: p[k] for k in ("task_id", "child_session_id", "exit_code", "result_present", "graph_state_observed",
                               "stop_gate", "ok", "outcome") if k in p}
        p["merge"] = merge
    return {k: e[k] for k in ("event_id", "event_type", "timestamp", "actor")} | {"payload": p}


def main(store: str) -> int:
    want = {i: label for label, ids in WANTED.items() for i in ids}
    rows = []
    for raw in Path(store).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        e = json.loads(raw)
        label = want.get(str(e.get("event_id", ""))[:8])
        if label:
            rows.append({"task": label, **cut(e)})
    missing = set(want) - {r["event_id"][:8] for r in rows}
    if missing:
        raise SystemExit(f"not found in {store}: {sorted(missing)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} events -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
