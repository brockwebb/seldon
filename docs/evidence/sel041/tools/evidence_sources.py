"""SEL-041 Part A (ADDENDUM 01 item 5): merge records' gate evidence by source, per repository, with the gate's
seconds where its log says (`.gate.log`'s pytest summary line). Read only."""
import json
import os
import re
import sys

ROOT = "/Users/brock/GitHub"
SUMMARY = re.compile(r"in ([0-9.]+)s")
for repo in ["seldon", "hazbrief-mcp", "squiddy", "aacps-ai-policy", "ai-readiness-kg", "factory"]:
    store = os.path.join(ROOT, repo, "seldon_events.jsonl")
    if not os.path.isfile(store):
        print(repo, "no store")
        continue
    by_source, regated, merges = {}, 0, 0
    rows = []
    with open(store, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"dispatch_finished"' not in line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            p = e.get("payload") or {}
            m = p.get("merge") or {}
            if not m.get("commit"):
                continue
            merges += 1
            ev = m.get("gate_evidence") or {}
            src = ev.get("source") or "(pre-R26)"
            by_source[src] = by_source.get(src, 0) + 1
            gate = m.get("gate") or (ev.get("gate") if isinstance(ev.get("gate"), dict) else None)
            secs = None
            if gate and gate.get("log_path"):
                lp = os.path.join(ROOT, repo, gate["log_path"])
                if os.path.isfile(lp):
                    found = SUMMARY.findall(open(lp, errors="replace").read())
                    secs = float(found[-1]) if found else None
            if m.get("regated") or src in ("merge_gate", "regate"):
                rows.append((e.get("timestamp", "")[:16], src, m.get("regated"), gate and gate.get("ok"), secs,
                             (p.get("source_file") or "")[9:60]))
    print(f"== {repo}: merges={merges} evidence={by_source}")
    for r in rows[-20:]:
        print("   ", r)
