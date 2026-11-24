"""SEL-043 Part A(2), the measurement as recorded: every `environment_in_flight` refusal in every dispatching
repository's event store, the hours each consumer waited, and the producer's phase over those hours.

Read only. Method (stated in the RESULT):
- A refusal is written once per producer lease acquisition (`dispatch._premise_review`), so a consumer is taken as
  waiting from the refusal until the earlier of (a) its own next `dispatch_launched` and (b) the end of the producer
  dispatch named in `held` (`dispatch_finished`). Per consumer the intervals are unioned, so hours are not counted
  twice when two producers or two acquisitions overlap.
- The producer's dispatch is split into phases from its own store: session = [dispatch_launched,
  launched + dispatch_finished.wall_clock_s]; gate = from the session's end to the last `gate_recorded`/`gate_run`
  of that dispatch (the round does little else; its own seconds are monotonic and leave out sleep, so the wall span
  is used); merge = from the last gate's end to `dispatch_finished`. A round with no gate event is all merge.
- A refusal whose lease named no task (a pass between tasks) is counted; its wait is capped at the consumer's next
  launch or 15 minutes, the longest a pass runs.
"""
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path("/Users/brock/GitHub")
REPOS = ["seldon", "squiddy", "hazbrief-mcp", "aacps-ai-policy", "factory", "ai-readiness-kg"]
PASS_CAP = timedelta(minutes=15)


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def events(repo):
    p = ROOT / repo / "seldon_events.jsonl"
    out = []
    for line in (p.read_text(encoding="utf-8", errors="replace").splitlines() if p.is_file() else []):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


stores = {r: events(r) for r in REPOS}


def dispatches(repo):
    """{task: [(launch, session_end, gate_end_or_None, finish)]}"""
    out = defaultdict(list)
    ev = stores[repo]
    by = defaultdict(list)
    for e in ev:
        t = (e.get("payload") or {}).get("task_id")
        if t:
            by[t].append(e)
    for t, es in by.items():
        launch = None
        gates = []
        for e in es:
            et = e["event_type"]
            if et == "dispatch_launched":
                launch, gates = ts(e["timestamp"]), []
            elif et in ("gate_recorded", "gate_run") and launch:
                gates.append(ts(e["timestamp"]))
            elif et == "dispatch_finished" and launch:
                fin = ts(e["timestamp"])
                wall = (e["payload"] or {}).get("wall_clock_s") or 0
                send = min(launch + timedelta(seconds=wall), fin)
                gend = max([g for g in gates if g >= send], default=None)
                out[t].append((launch, send, gend, fin))
                launch = None
    return out


disp = {r: dispatches(r) for r in REPOS}


def phases(prod, task, a, b):
    """seconds of [a, b] in each producer phase for the dispatch of `task` covering a."""
    out = defaultdict(float)
    for (launch, send, gend, fin) in disp.get(prod, {}).get(task, []):
        if not (launch <= b and fin >= a):
            continue
        spans = [("session", launch, send)]
        if gend:
            spans += [("gate", send, gend), ("merge", gend, fin)]
        else:
            spans += [("merge", send, fin)]
        for name, s, e in spans:
            lo, hi = max(a, s), min(b, e)
            if hi > lo:
                out[name] += (hi - lo).total_seconds()
    return out


def finish_of(prod, task, when):
    for (launch, send, gend, fin) in disp.get(prod, {}).get(task, []):
        if launch <= when <= fin:
            return fin
    return None


summary = defaultdict(lambda: {"refusals": 0, "session": 0.0, "gate": 0.0, "merge": 0.0, "between_tasks": 0.0})
detail = []
for consumer in REPOS:
    ev = stores[consumer]
    launches = sorted(ts(e["timestamp"]) for e in ev if e["event_type"] == "dispatch_launched")
    intervals = []  # (a, b, producer, task)
    for e in ev:
        p = e.get("payload") or {}
        if e["event_type"] != "dispatch_refused" or p.get("reason") != "environment_in_flight":
            continue
        when = ts(e["timestamp"])
        nxt = min((t for t in launches if t > when), default=None)
        for prod, h in (p.get("held") or {}).items():
            task = h.get("task")
            fin = finish_of(prod, task, when) if task else None
            end = min([x for x in (nxt, fin) if x] or [when + PASS_CAP])
            if not task:
                end = min(end, when + PASS_CAP)
            intervals.append((when, end, prod, task))
            summary[(consumer, prod)]["refusals"] += 1
            detail.append({"consumer": consumer, "consumer_task": (p.get("task_id") or "")[:8], "at": e["timestamp"],
                           "producer": prod, "producer_task": (task or "")[:8], "until": end.isoformat(),
                           "hours": round((end - when).total_seconds() / 3600, 2)})
    # union per (consumer, producer, task) timeline: walk second-free merge of intervals
    intervals.sort()
    covered = []
    for a, b, prod, task in intervals:
        if covered and a < covered[-1][1] and covered[-1][2] == prod and covered[-1][3] == task:
            if b > covered[-1][1]:
                covered[-1] = (covered[-1][0], b, prod, task)
        else:
            covered.append((a, b, prod, task))
    # remove overlap across producers (count each second once, attributing to the first producer)
    last_end = None
    for a, b, prod, task in covered:
        if last_end and a < last_end:
            a = last_end
        if b <= a:
            continue
        last_end = b
        s = summary[(consumer, prod)]
        if task:
            for k, v in phases(prod, task, a, b).items():
                s[k] += v
        else:
            s["between_tasks"] += (b - a).total_seconds()

json.dump(detail, open("/tmp/sel043/refusals_detail.json", "w"), indent=1)
tot = defaultdict(float)
print("| consumer | producer | refusals | hours waited | in producer session | in producer gate | in producer merge | between tasks |")
print("|---|---|---|---|---|---|---|---|")
for (c, p), s in sorted(summary.items()):
    h = {k: s[k] / 3600 for k in ("session", "gate", "merge", "between_tasks")}
    total = sum(h.values())
    for k, v in h.items():
        tot[k] += v
    tot["refusals"] += s["refusals"]
    print(f"| {c} | {p} | {s['refusals']} | {total:.1f} | {h['session']:.1f} | {h['gate']:.1f} | {h['merge']:.2f} | {h['between_tasks']:.2f} |")
T = tot["session"] + tot["gate"] + tot["merge"] + tot["between_tasks"]
print(f"| all | | {int(tot['refusals'])} | {T:.1f} | {tot['session']:.1f} | {tot['gate']:.1f} | {tot['merge']:.2f} | {tot['between_tasks']:.2f} |")
first = min(d["at"] for d in detail)
last = max(d["at"] for d in detail)
print("span:", first, "to", last)
