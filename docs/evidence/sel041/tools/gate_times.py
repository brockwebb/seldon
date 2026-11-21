"""SEL-041 Part A: wall time of recorded suite/gate runs, per dispatching repository, from what each recorded.

Sources read (read only): each repo's dispatch logs (session stream-json and `.gate.log`), whose tool results carry
pytest's summary line `N passed[, ...] in S.SSs`; squiddy's kit pass ledger. A run counts as a *full-suite* run when its
total (passed+failed+errors+skipped) is at least FULL_SHARE of the largest total seen in that repository: the summary
line does not say which command produced it, so the share is the only discriminator the logs allow.
"""
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = "/Users/brock/GitHub"
REPOS = ["seldon", "hazbrief-mcp", "squiddy", "aacps-ai-policy", "ai-readiness-kg", "factory"]
FULL_SHARE = 0.9
SUMMARY = re.compile(r"((?:\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)(?:, )?)+) in "
                     r"([0-9.]+)s")
COUNT = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)")


def runs_in(path):
    seen = set()
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        print("unreadable", path, exc, file=sys.stderr)
        return []
    out = []
    for m in SUMMARY.finditer(text.replace("\\n", "\n")):
        counts = {}
        for c in COUNT.finditer(m.group(1)):
            k = c.group(2).rstrip("s") if c.group(2).startswith("error") else c.group(2)
            counts[k] = counts.get(k, 0) + int(c.group(1))
        key = (m.group(1), m.group(2))
        if key in seen:   # the same tool result is echoed in stream-json more than once
            continue
        seen.add(key)
        total = sum(v for k, v in counts.items() if k in ("passed", "failed", "error", "skipped", "xfailed", "xpassed"))
        out.append({"total": total, "seconds": float(m.group(2)), "counts": counts})
    return out


def main():
    report = {}
    for repo in REPOS:
        logdir = os.path.join(ROOT, repo, "logs", "dispatch")
        rows = []
        for path in glob.glob(os.path.join(logdir, "*.log")):
            mtime = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).strftime("%Y-%m-%d")
            for r in runs_in(path):
                rows.append({**r, "log": os.path.basename(path), "date": mtime})
        biggest = max((r["total"] for r in rows), default=0)
        full = sorted([r for r in rows if biggest and r["total"] >= FULL_SHARE * biggest],
                      key=lambda r: (r["date"], r["log"]))
        report[repo] = {"runs_seen": len(rows), "largest_total": biggest, "full_runs": full[-20:]}
    json.dump(report, open("/tmp/sel041/gate_times.json", "w"), indent=1)
    for repo, r in report.items():
        secs = sorted(x["seconds"] for x in r["full_runs"])
        med = secs[len(secs) // 2] if secs else None
        print(f"{repo}: summaries={r['runs_seen']} largest={r['largest_total']} full_runs(last20)={len(secs)} "
              f"median_s={med} min={secs[0] if secs else None} max={secs[-1] if secs else None}")
        for x in r["full_runs"]:
            print(f"   {x['date']} {x['total']:>6} {x['seconds']:>9.1f}s {x['log'][:70]}")


main()
