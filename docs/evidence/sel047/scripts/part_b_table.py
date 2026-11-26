"""SEL-047 Part B: the README's tables, printed as markdown from runs.jsonl (sleep-spanned attempts excluded and
counted)."""
import collections
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
rows = [json.loads(x) for x in (ROOT / "docs/evidence/sel047/runs.jsonl").read_text().splitlines() if x.strip()]
slept = [r for r in rows if r.get("spanned_sleep")]
rows = [r for r in rows if not r.get("spanned_sleep")]
short = lambda i: i.split("::", 1)[1] if "::" in i else i  # noqa: E731

print("### Alone, 20 serial runs per file\n")
print("| file | runs | runs with a failure | failing test ids (count) | wall s (min / median / max) | 1-min load "
      "before (min to max) | other suites' xdist workers before (min to max, measured from run 6) |")
print("|---|---|---|---|---|---|---|")
for f in ("test_sel024_gate_record", "test_dispatch_parallel"):
    rs = [r for r in rows if r["run"].startswith(f"alone_{f}_")]
    c = collections.Counter(i for r in rs for i in r["failed_ids"])
    w = [r["wall_s"] for r in rs]
    lb = [r["load_before"][0] for r in rs]
    xb = [r["xdist_workers_before"] for r in rs if r.get("xdist_workers_before") is not None]
    print(f"| `{f}.py` | {len(rs)} | {sum(1 for r in rs if r['failed'] or r['errors'])} | "
          f"{'; '.join(f'`{short(i)}` ({n})' for i, n in c.most_common()) or 'none'} | "
          f"{min(w):.0f} / {statistics.median(w):.0f} / {max(w):.0f} | {min(lb)} to {max(lb)} | "
          f"{min(xb) if xb else '-'} to {max(xb) if xb else '-'} |")
print()
print("### Per alone run\n")
print("| run | wall s | load before (1/5/15 min) | load after | other xdist workers before / after | failed |")
print("|---|---|---|---|---|---|")
for r in rows:
    if not r["run"].startswith("alone_"):
        continue
    xb, xa = r.get("xdist_workers_before"), r.get("xdist_workers_after")
    print(f"| {r['run'].replace('alone_', '')} | {r['wall_s']:.0f} | {r['load_before']} | {r['load_after']} | "
          f"{'-' if xb is None else xb} / {'-' if xa is None else xa} | "
          f"{', '.join('`' + short(i) + '`' for i in r['failed_ids']) or '-'} |")
print()
print("### Full suite\n")
print("| run | wall s (min) | passed | failed | errors | summary | load before / after (1-min) | other xdist workers "
      "before / after | failed ids |")
print("|---|---|---|---|---|---|---|---|---|")
for r in rows:
    if not r["run"].startswith("full_"):
        continue
    print(f"| {r['run']} | {r['wall_s']:.0f} ({r['wall_s'] / 60:.1f}) | {r['passed']} | {r['failed']} | {r['errors']} | "
          f"{r['summary']} | {r['load_before'][0]} / {r['load_after'][0]} | {r.get('xdist_workers_before')} / "
          f"{r.get('xdist_workers_after')} | {', '.join('`' + short(i) + '`' for i in r['failed_ids']) or '-'} |")
print()
print(f"Sleep-spanned attempts on the ledger, excluded above and run again: {len(slept)}"
      + (": " + ", ".join(f"{r['run']} ({r['slept_s']} s asleep)" for r in slept) if slept else "."))
