"""SEL-001 step 7, arm O: registration's own concept-overlap scorer, run read-only (AD-031-R3).

Run with Seldon's interpreter, from the Seldon repository root, with the Neo4j credentials loaded, after
`gold.py`:

    python -m dotenv -f .env run -- python scripts/sel001/arm_o.py

Nothing is re-implemented. The rulings are read by `seldon.core.governed.read_rulings` from each graph's Seldon
database, and each task is scored by `seldon.core.governed.match_rulings`, the function `seldon cc register`
calls, with `threshold=0.0` and `limit` equal to the number of rulings so that it returns its whole ranking
(protocol section 2). A ruling with score 0.0 is dropped: it shares no term with the task.

Checkpointed per task (engineering standards section 15): each task's ranking is one fsynced row in
`arm_o_runs.jsonl`, keyed by the stripped text's sha256, the ruling set's fingerprint and the scorer's threshold
and stop list; a re-run skips every key it holds. Zero model calls; the only ceiling is wall clock.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

from seldon.config import get_neo4j_driver, load_project_config  # noqa: E402
from seldon.core import governed  # noqa: E402

#: Bump when what a row records changes.
ARM_O_RULE = "sel001-arm-o/1"


def rulings_of(repo_root: Path, graph: str) -> tuple[list[dict], str]:
    """Every binding Ruling in one graph's Seldon database, tagged with its graph, and the set's fingerprint."""
    cfg = load_project_config(repo_root)
    driver = get_neo4j_driver(cfg)
    try:
        rows = governed.read_rulings(driver, cfg["neo4j"]["database"])
    finally:
        driver.close()
    if not rows:
        raise SystemExit(f"FATAL: {cfg['neo4j']['database']} holds no Ruling; run `seldon governed sync` in "
                         f"{repo_root} (SEL-001 step 1)")
    out = [{**r, "graph": graph} for r in rows]
    fp = C.canonical_sha(sorted((r["artifact_id"], r["name"], C.sha256_text(r["text"] or "")) for r in out))
    return out, fp


def main() -> int:
    cfg = C.load_config()
    queries = C.read_rows(C.evidence(cfg, "queries.jsonl"))
    if not queries:
        raise SystemExit("FATAL: no queries; run scripts/sel001/gold.py first")
    catalog = json.loads(C.evidence(cfg, "catalog.json").read_text(encoding="utf-8"))
    graphs = sorted({g for q in queries for g in q["scope"]})
    rulings, fps = {}, {}
    for g in graphs:
        rulings[g], fps[g] = rulings_of(Path(cfg["repos"][g]["root"]), g)
        # The Seldon artifact's `name` is the governed node id (seldon.core.governed._child_properties).
        unknown = [r["name"] for r in rulings[g] if r["name"] not in catalog[g]["rulings"]]
        if unknown:
            raise SystemExit(f"FATAL: {len(unknown)} Ruling(s) in {g}'s database are not in its governed ledger, "
                             f"e.g. {unknown[:3]}; re-run `seldon governed sync` and gold.py")
    thresholds = {repo: governed.ruling_match_threshold(load_project_config(Path(r["root"])))
                  for repo, r in cfg["repos"].items()}
    scorer = {"rule": ARM_O_RULE, "min_term_length": governed.MIN_TERM_LENGTH,
              "stop_terms": sorted(governed.STOP_TERMS), "threshold_called": 0.0}

    out_path = C.evidence(cfg, "arm_o_runs.jsonl")
    done = {r["key"] for r in C.read_rows(out_path)}
    prog = C.Progress(len(queries), C.evidence(cfg, "arm_o.log"), int(cfg["run"]["progress_every_units"]),
                      float(cfg["run"]["progress_every_seconds"]), "arm O")
    pilot_n = int(cfg["run"]["pilot_units"])
    for i, q in enumerate(queries):
        key = C.canonical_sha({"q": q["stripped_sha256"], "scope": q["scope"], "family": q["family_doc_ids"],
                               "rulings": {g: fps[g] for g in q["scope"]}, "scorer": scorer})
        if key in done:
            prog.tick(new=False)
            continue
        if prog.elapsed() > float(cfg["run"]["wall_seconds_max"]):
            raise SystemExit(f"FATAL: arm O crossed run.wall_seconds_max; {prog.done} of {len(queries)} tasks are "
                             f"in {out_path}; re-run the same command to resume")
        try:
            family = {g: set(v) for g, v in q["family_doc_ids"].items()}
            pool = [r for g in q["scope"] for r in rulings[g]
                    if catalog[g]["rulings"][r["name"]]["doc_id"] not in family[g]]
            by_id = {r["artifact_id"]: r for r in pool}
            ranked = governed.match_rulings(q["stripped_text"], pool, 0.0, limit=len(pool))
            cands = [[by_id[m.artifact_id]["graph"], m.name, m.match_score, m.matched_terms[:8]]
                     for m in ranked if (m.match_score or 0.0) > 0.0]
            thr = thresholds[q["repo"]]
            above = sum(1 for c in cands if c[2] >= thr)
            row = {"key": key, "rule": ARM_O_RULE, "query_id": q["query_id"], "candidates": cands,
                   "pool": len(pool), "nonzero": len(cands), "threshold": thr, "above_threshold": above,
                   "registration_would_bind": min(above, 8), "error": None}
        except Exception as exc:  # a failed unit is a row, never a crash of the units already landed (15.7)
            row = {"key": key, "rule": ARM_O_RULE, "query_id": q["query_id"], "candidates": [],
                   "error": f"{type(exc).__name__}: {exc}"}
        C.append_row(out_path, row)
        prog.tick(new=True, failed=bool(row["error"]))
        if prog.new == pilot_n:
            per = prog.elapsed() / prog.new
            prog.say(f"pilot: {pilot_n} tasks in {prog.elapsed():.1f}s, {per:.2f}s per task; projected "
                     f"{per * (len(queries) - prog.done):.0f}s for the {len(queries) - prog.done} remaining "
                     f"(measured, zero model calls)")
    prog.say(f"done: {prog.done}/{len(queries)} tasks, {prog.new} this run, failures {prog.failed}")
    return 1 if prog.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
