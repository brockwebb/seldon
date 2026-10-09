"""PA-001 Part D: p95 latency of squiddy-library `search` on the 24 frozen questions (AD-036 s.4).

    python scripts/pa001/library_latency.py [--ceiling-seconds 1800]

Two modes, 24 units each:
- **cold**: each question is the FIRST search of a fresh Python process (index open, dense
  encoder load and query), timed inside the child from just before `Verbs(...)` to the answer.
  This is what a Desktop session waits for when its first call lands on a just-started server
  before the server's background warm-up finishes.
- **warm**: one process opens the index once (untimed), then times each of the 24 searches.

Bound: 10 s on p95 in each mode, stated in AD-036 section 4 before this run (Desktop tool-call
patience; no measured basis otherwise). A failure is a design task, not a block.

**Checkpointed (constitution section 15).** Each unit (mode, question id) is appended to
`docs/evidence/pa001/library_latency_units.jsonl`, flushed and fsynced, before the next starts;
its key carries the release sha256 and the question's text hash, so a changed release or question
is never reused. Re-running the same command is the resume. Progress (done/total, rate, ETA) goes
to stdout and `logs/pa001_library_latency.log`. A wall-clock ceiling stops new units and exits 3;
the summary step reports whatever the checkpoint holds and states its n. The search is local:
zero model calls, network none (HF_HUB_OFFLINE=1).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

QUESTIONS = Path("../squiddy/graphs/library/evidence/20260923_q003/demand_questions.json")
GRAPH = Path("../squiddy/graphs/library")
UNITS = Path("docs/evidence/pa001/library_latency_units.jsonl")
OUT = Path("docs/evidence/pa001/library_latency.json")
LOG = Path("logs/pa001_library_latency.log")
BOUND_S = 10.0
K = 10          # the served verb's default k, which is what a Desktop call asks for

CHILD = r"""
import json, os, sys, time
os.environ.setdefault("HF_HUB_OFFLINE", "1"); os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
graph, k = sys.argv[1], int(sys.argv[2])
qs = json.loads(sys.stdin.read())
t0 = time.perf_counter()
from squiddy.config import load_graph
from squiddy.serve import Verbs
v = Verbs(load_graph(graph))
if len(qs) > 1:
    v._index()                                   # warm: open once, untimed
for q in qs:
    t = time.perf_counter() if len(qs) > 1 else t0
    r = v.search(q, k=k)
    print(json.dumps({"seconds": round(time.perf_counter() - t, 4), "hits": len(r.get("hits", [])),
                      "error": r.get("error"), "release": (r.get("index") or {}).get("release")}),
          flush=True)
"""


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def p95(xs: list) -> float | None:
    """Nearest-rank 95th percentile (the smallest value with at least 95% of values at or below)."""
    if not xs:
        return None
    ys = sorted(xs)
    return ys[max(0, math.ceil(0.95 * len(ys)) - 1)]


def load_done(path: Path) -> dict:
    done = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["key"]] = row
    return done


def append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def progress(log: Path, msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    print(line, flush=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run_child(graph: str, questions: list, k: int, timeout: int) -> list:
    r = subprocess.run([sys.executable, "-c", CHILD, graph, str(k)], input=json.dumps(questions),
                       capture_output=True, text=True, timeout=timeout)
    rows = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    if r.returncode != 0 or len(rows) != len(questions):
        raise RuntimeError(f"child exit {r.returncode}: {r.stderr[-800:]}")
    return rows


def units(questions: list, release_sha: str) -> list:
    """Every (mode, question) unit with its deterministic key."""
    out = []
    for mode in ("cold", "warm"):
        for q in questions:
            out.append({"mode": mode, "id": q["id"], "question": q["question"],
                        "key": f"{mode}|{q['id']}|{sha(q['question'])[:12]}|{release_sha[:12]}|k{K}"})
    return out


def execute(todo: list, measure, ckpt: Path, log: Path, ceiling_s: float) -> int:
    """Run the units not yet in the checkpoint. `measure(mode, [questions])` returns one row per
    question. Warm units are measured in one child per resume (the open is untimed), cold units one
    child each. Returns 0, or 3 when the wall-clock ceiling stopped new units."""
    done = load_done(ckpt)
    left = [u for u in todo if u["key"] not in done]
    started, n0 = time.monotonic(), len(left)
    progress(log, f"{len(todo) - n0}/{len(todo)} units already in the checkpoint; {n0} to run")
    cold = [u for u in left if u["mode"] == "cold"]
    warm = [u for u in left if u["mode"] == "warm"]
    batches = [[u] for u in cold] + ([warm] if warm else [])
    finished = 0
    for batch in batches:
        if time.monotonic() - started > ceiling_s:
            progress(log, f"wall-clock ceiling {ceiling_s:.0f}s reached; stopping with "
                          f"{finished}/{n0} run this time")
            return 3
        try:
            rows = measure(batch[0]["mode"], [u["question"] for u in batch])
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            for u in batch:
                append(ckpt, {**u, "seconds": None, "error": str(exc)[:500]})
            finished += len(batch)
            continue
        for u, r in zip(batch, rows):
            append(ckpt, {**u, **r})
            finished += 1
        el = time.monotonic() - started
        rate = finished / el if el else 0
        eta = (n0 - finished) / rate if rate else float("nan")
        progress(log, f"{finished}/{n0} done this run, {rate:.2f} unit/s, ETA {eta:.0f}s")
    return 0


def summarize(ckpt: Path, keys: set) -> dict:
    rows = [r for k, r in load_done(ckpt).items() if k in keys]
    out = {"bound_s": BOUND_S, "k": K, "modes": {}}
    for mode in ("cold", "warm"):
        xs = [r["seconds"] for r in rows if r["mode"] == mode and r.get("seconds") is not None]
        fails = [r["id"] for r in rows if r["mode"] == mode and r.get("seconds") is None]
        v = p95(xs)
        out["modes"][mode] = {"n": len(xs), "failed": fails, "p95_s": v,
                              "median_s": sorted(xs)[len(xs) // 2] if xs else None,
                              "max_s": max(xs) if xs else None,
                              "verdict": None if v is None else ("pass" if v <= BOUND_S else "fail")}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ceiling-seconds", type=float, default=1800.0)
    ap.add_argument("--child-timeout", type=int, default=300)
    a = ap.parse_args(argv)
    qdoc = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    questions = qdoc["questions"]
    if len(questions) != 24:
        print(f"expected the 24 frozen questions, found {len(questions)}", file=sys.stderr)
        return 2
    export = GRAPH / "exports" / "library_graph.json"
    release_sha = hashlib.sha256(export.read_bytes()).hexdigest()
    todo = units(questions, release_sha)
    measure = lambda mode, qs: run_child(str(GRAPH), qs, K, a.child_timeout)   # noqa: E731
    code = execute(todo, measure, UNITS, LOG, a.ceiling_seconds)
    summary = summarize(UNITS, {u["key"] for u in todo})
    summary.update({"questions": str(QUESTIONS), "questions_sha256": sha(QUESTIONS.read_text()),
                    "release_sha256": release_sha, "units": str(UNITS), "complete": code == 0,
                    "definition": {"cold": "first search of a fresh process, index open included",
                                   "warm": "search after the index is open, one process"}})
    OUT.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary["modes"]))
    return code


if __name__ == "__main__":
    sys.exit(main())
