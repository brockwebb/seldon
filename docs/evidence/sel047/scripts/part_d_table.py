"""SEL-047 Part D: the README's per-merge table and prefix counts, printed as markdown from slice_misses.json."""
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
d = json.loads((ROOT / "docs/evidence/sel047/slice_misses.json").read_text())
ART = "slice_tests_missing"


def task(r):
    s = Path(r["task"] or "?").stem
    return f"{s.split('_', 2)[1]} ({r['branch']})" if r["task"] else r["branch"]


print("| merged (main reflog) | task | literal tier: first reason | today's slices: tier, first reason (replay artifact "
      "removed) | unmatched (today) |")
print("|---|---|---|---|---|")
pref = collections.Counter()
for r in d:
    lit = r["literal"]
    t = r["today"]
    real = [x for x in t["reasons"] if not x.startswith(ART)]
    first = real[0] if real else "none: scoped (" + (", ".join(t["slices"]) or "changed tests") + ")"
    um = t["unmatched"]
    print(f"| {r['merged_at'][:16]} | {task(r)} | {lit.get('tier')}: {lit.get('reason')} | "
          f"{'full' if real else 'scoped'}: {first} | {len(um)}: {', '.join(um[:4])}{' ...' if len(um) > 4 else ''} |")
    for u in set("/".join(p.split("/")[:2]) + ("/" if p.count("/") > 1 else "") for p in um):
        pref[u] += 1
print()
print("| top two levels of an unmatched path | merges it sent full |")
print("|---|---|")
for p, n in pref.most_common():
    print(f"| `{p}` | {n} |")
