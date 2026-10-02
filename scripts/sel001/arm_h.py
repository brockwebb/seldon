"""SEL-001 step 7, arm H: Squiddy's hybrid search over each governed graph's served index (AD-031-R3).

Run with Squiddy's interpreter, under Squiddy's egress policy `none`, after `gold.py` and the index builds:

    ~/GitHub/squiddy/.venv/bin/python scripts/sel001/offline.py evidence/sel001/arm_h_egress.json -- \
        ~/GitHub/squiddy/.venv/bin/python scripts/sel001/arm_h.py

Nothing is re-implemented and nothing is tuned (protocol section 2). Each graph's index is opened by
`squiddy.index.Index.open`, which refuses a database that does not hash to its index manifest and a shard set the
manifest does not bind. Per task, per index: `Index.lex.search` and `Index.dense.search` (the two sub-arms of the
served verb, 200 candidates each) fused by `squiddy.index.rrf` at the configured `rrf_k`, exactly as
`Index.fused` does before it groups rows by document. The lists of the graphs in scope are merged by fused score
(ties by graph, then row id) and the task's family is removed. Every Ruling row is kept in order; Section rows are
kept to `run.keep_section_rows` for the granularity diagnostic.

Imports nothing from Seldon (this interpreter has no Seldon). Checkpointed per task (standards section 15):
one fsynced row per task in `arm_h_runs.jsonl`, keyed by the stripped text's sha256, the scope, the family and
each index's manifest stamps; a re-run skips every key it holds. Zero model calls: the only inference is the
pinned local encoder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

from squiddy import index as ix  # noqa: E402
from squiddy.config import load_graph  # noqa: E402

#: Bump when what a row records changes.
ARM_H_RULE = "sel001-arm-h/1"


def open_indexes(cfg: dict, graphs: list[str]):
    """Each graph's built index, verified, sharing one query encoder (the graphs must declare the same one)."""
    loaded = {}
    for g in graphs:
        graph = load_graph(Path(cfg["repos"][g]["root"]) / cfg["graph_dir"])
        icfg = ix.load_config(graph)
        loaded[g] = (graph, icfg)
    encs = {g: icfg["encoder"] for g, (_gr, icfg) in loaded.items()}
    first = next(iter(encs.values()))
    if any(e != first for e in encs.values()):
        raise SystemExit(f"FATAL: the governed indexes declare different encoders: {encs}")
    qenc = ix.query_encoder(first)
    out = {}
    for g, (graph, icfg) in loaded.items():
        idx = ix.Index.open(graph, icfg, query_encoder=qenc)
        stamp = {"row_fingerprint": idx.manifest["row_fingerprint"], "db_sha256": idx.manifest["db"]["sha256"],
                 "shard_set_sha256": idx.manifest["dense"]["shard_set_sha256"], "config": icfg["_sha256"],
                 "rule": idx.manifest["rule"]}
        out[g] = (idx, icfg, stamp)
    return out


def fused_rows(idx, icfg: dict, text: str):
    """The served verb's fused row ranking, before it groups rows into documents (`Index.fused`)."""
    return ix.rrf({"fts": idx.lex.search(text), "dense": idx.dense.search(text)}, int(icfg["fusion"]["rrf_k"]))


def main() -> int:
    cfg = C.load_config()
    queries = C.read_rows(C.evidence(cfg, "queries.jsonl"))
    if not queries:
        raise SystemExit("FATAL: no queries; run scripts/sel001/gold.py first")
    catalog = json.loads(C.evidence(cfg, "catalog.json").read_text(encoding="utf-8"))
    graphs = sorted({g for q in queries for g in q["scope"]})
    indexes = open_indexes(cfg, graphs)
    keep_sections = int(cfg["run"]["keep_section_rows"])

    out_path = C.evidence(cfg, "arm_h_runs.jsonl")
    done = {r["key"] for r in C.read_rows(out_path)}
    prog = C.Progress(len(queries), C.evidence(cfg, "arm_h.log"), int(cfg["run"]["progress_every_units"]),
                      float(cfg["run"]["progress_every_seconds"]), "arm H")
    prog.say("indexes: " + json.dumps({g: s for g, (_i, _c, s) in indexes.items()}, sort_keys=True))
    pilot_n = int(cfg["run"]["pilot_units"])
    for q in queries:
        key = C.canonical_sha({"q": q["stripped_sha256"], "scope": q["scope"], "family": q["family_doc_ids"],
                               "indexes": {g: indexes[g][2] for g in q["scope"]}, "rule": ARM_H_RULE})
        if key in done:
            prog.tick(new=False)
            continue
        if prog.elapsed() > float(cfg["run"]["wall_seconds_max"]):
            raise SystemExit(f"FATAL: arm H crossed run.wall_seconds_max; {prog.done} of {len(queries)} tasks are "
                             f"in {out_path}; re-run the same command to resume")
        try:
            merged = []
            for g in q["scope"]:
                idx, icfg, _s = indexes[g]
                family = set(q["family_doc_ids"].get(g) or [])
                for h in fused_rows(idx, icfg, q["stripped_text"]):
                    if h.doc_id in family:
                        continue
                    merged.append((-h.rrf, g, h.row_id, h.fts_rank, h.dense_rank))
            merged.sort()
            rulings, sections = [], []
            for neg, g, row_id, fr, dr in merged:
                cls, _, node = row_id.partition(":")
                if cls == "Ruling":
                    rulings.append([g, node, -neg, fr, dr])
                elif cls == "Section" and len(sections) < keep_sections:
                    sections.append([g, node, -neg])
                # metadata rows (`<doc>#meta`) compete in the sub-arms and are never candidates
            unknown = [r[1] for r in rulings if r[1] not in catalog[r[0]]["rulings"]]
            if unknown:
                raise ValueError(f"index rows name Rulings the ledger catalog does not hold: {unknown[:3]}")
            row = {"key": key, "rule": ARM_H_RULE, "query_id": q["query_id"], "candidates": rulings,
                   "sections": sections, "rows_fused": len(merged), "error": None}
        except Exception as exc:  # a failed unit is a row, never a crash of the units already landed (15.7)
            row = {"key": key, "rule": ARM_H_RULE, "query_id": q["query_id"], "candidates": [], "sections": [],
                   "error": f"{type(exc).__name__}: {exc}"}
        C.append_row(out_path, row)
        prog.tick(new=True, failed=bool(row["error"]))
        if prog.new == pilot_n:
            per = prog.elapsed() / prog.new
            prog.say(f"pilot: {pilot_n} tasks in {prog.elapsed():.1f}s (encoder load included), {per:.2f}s per "
                     f"task; projected {per * (len(queries) - prog.done):.0f}s for the {len(queries) - prog.done} "
                     f"remaining (measured)")
    prog.say(f"done: {prog.done}/{len(queries)} tasks, {prog.new} this run, failures {prog.failed}")
    return 1 if prog.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
