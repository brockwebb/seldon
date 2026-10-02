"""SEL-001 steps 8 and 9: score both arms on the gold sets, and lay out every miss with its evidence.

Run with Seldon's interpreter, from the Seldon repository root, after both arms:

    python scripts/sel001/score.py

Reads `evidence/sel001/` (gold sets, catalog, queries, `arm_o_runs.jsonl`, `arm_h_runs.jsonl`) and writes
`results.json` and `misses.md` there. Every measure is `evidence/sel001/protocol.md` section 4. The cause signals
for a miss are mechanical and named as such; they say what the evidence shows, never more. Fails loud when a query
has no row in an arm, or a row that failed: a score over a partial run must say so, and this one refuses instead.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

from seldon.core import governed  # noqa: E402

ARMS = ("O", "H")


def latest_rows(path: Path) -> dict[str, dict]:
    rows = {}
    for r in C.read_rows(path):
        rows[r["query_id"]] = r
    return rows


def rank_of(nodes: list, candidates: list) -> int | None:
    """1-based position of the first candidate that IS the gold (protocol section 4), or None."""
    want = {tuple(n) for n in nodes}
    for i, c in enumerate(candidates, 1):
        if (c[0], c[1]) in want:
            return i
    return None


def h_mixed_order(run: dict) -> list[tuple]:
    """Arm H's Ruling and Section rows in the fused order the arm produced them (score, graph, row id)."""
    rows = [(-c[2], c[0], f"Ruling:{c[1]}") for c in run["candidates"]]
    rows += [(-s[2], s[0], f"Section:{s[1]}") for s in run["sections"]]
    return sorted(rows)


def section_hit(gold_nodes: list, run: dict, catalog: dict, k: int) -> list | None:
    """For arm H: a Section row in the top k of Ruling-and-Section rows whose span contains a gold Ruling's span in
    the same document. The granularity signal of protocol section 4."""
    golds = [catalog[g]["rulings"][n] for g, n in gold_nodes]
    for neg, g, row in h_mixed_order(run)[:k]:
        cls, _, node = row.partition(":")
        if cls != "Section":
            continue
        s = catalog[g]["sections"][node]
        for r in golds:
            if (r["graph"] == g and r["doc_id"] == s["doc_id"] and None not in s["span"] and None not in r["span"]
                    and s["span"][0] <= r["span"][0] and r["span"][1] <= s["span"][1]):
                return [g, node]
    return None


def snippet(text: str, n: int = 240) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[:n] + "..."


def main() -> int:
    cfg = C.load_config()
    k, k5, z = int(cfg["k"]), int(cfg["k_small"]), float(cfg["wilson_z"])
    ev = lambda name: C.evidence(cfg, name)  # noqa: E731
    catalog = json.loads(ev("catalog.json").read_text(encoding="utf-8"))
    queries = {q["query_id"]: q for q in C.read_rows(ev("queries.jsonl"))}
    gold_a, gold_b = C.read_rows(ev("gold_a.jsonl")), C.read_rows(ev("gold_b.jsonl"))
    gold_bd, gold_c = C.read_rows(ev("gold_b_diagnostics.jsonl")), C.read_rows(ev("gold_c.jsonl"))
    runs = {"O": latest_rows(ev("arm_o_runs.jsonl")), "H": latest_rows(ev("arm_h_runs.jsonl"))}
    for arm in ARMS:
        missing = sorted(set(queries) - set(runs[arm]))
        failed = sorted(q for q, r in runs[arm].items() if r.get("error"))
        if missing or failed:
            raise SystemExit(f"FATAL: arm {arm}: {len(missing)} queries with no row ({missing[:3]}), {len(failed)} "
                             f"failed ({failed[:3]}); re-run the arm before scoring")

    def ruling_text(g: str, n: str) -> str:
        return catalog[g]["rulings"][n]["text"]

    def overlap(qid: str, text: str):
        return governed.overlap_score(governed.concept_terms(queries[qid]["stripped_text"]),
                                      governed.concept_terms(text))

    def top3(arm: str, qid: str) -> list[dict]:
        return [{"graph": c[0], "node": c[1], "score": c[2], "path": catalog[c[0]]["rulings"][c[1]]["path"],
                 "label": catalog[c[0]]["rulings"][c[1]]["label"], "text": snippet(ruling_text(c[0], c[1]))}
                for c in runs[arm][qid]["candidates"][:3]]

    def signals(arm: str, qid: str, gold: dict, rank: int | None) -> dict:
        """What the evidence shows about one miss. Mechanical; the report names causes only from these."""
        run = runs[arm][qid]
        out = {"rank": rank, "candidates": len(run["candidates"])}
        o_score, o_terms = overlap(qid, gold["text"])
        out["overlap_with_gold"] = round(o_score, 3)
        out["shared_terms"] = o_terms[:12]
        gold_docs = {(g, catalog[g]["rulings"][n]["doc_id"]) for g, n in gold["nodes"]}
        out["top3_from_gold_document"] = sum(
            1 for c in run["candidates"][:3] if (c[0], catalog[c[0]]["rulings"][c[1]]["doc_id"]) in gold_docs)
        if arm == "H":
            hit = next((c for c in run["candidates"] if (c[0], c[1]) in {tuple(n) for n in gold["nodes"]}), None)
            out["gold_fts_rank"] = hit[3] if hit else None
            out["gold_dense_rank"] = hit[4] if hit else None
            out["in_neither_subarm_top_200"] = hit is None
            out["containing_section_in_top_k"] = section_hit(gold["nodes"], run, catalog, k)
        cause = []
        if out["overlap_with_gold"] == 0.0:
            cause.append("vocabulary: the stripped task shares no content term with the ruling")
        if arm == "H" and out["in_neither_subarm_top_200"]:
            cause.append("retrieval depth: in neither sub-arm's 200 candidates")
        if arm == "H" and out["containing_section_in_top_k"]:
            cause.append("granularity: a Section containing the ruling ranked in the top k")
        if out["top3_from_gold_document"]:
            cause.append("granularity: a sibling ruling of the same document outranked it")
        if not cause:
            cause.append("outranked: shares terms with the task and was ranked below k")
        out["cause_signals"] = cause
        return out

    results: dict = {"k": k, "k_small": k5, "wilson_z": z, "arms": {}}
    miss_rows: list[dict] = []
    for arm in ARMS:
        pairs = []
        for p in gold_a:
            r = rank_of(p["gold"]["nodes"], runs[arm][p["query_id"]]["candidates"])
            rh = rank_of(p["gold"]["home_nodes"], runs[arm][p["query_id"]]["candidates"]) if p["gold"]["home_nodes"] else None
            pairs.append({"pair_id": p["pair_id"], "query_id": p["query_id"], "repo": p["repo"], "rank": r,
                          "home_rank": rh, "via": "+".join(sorted(p["gold"]["via_kinds"]))})
        n = len(pairs)
        h10 = sum(1 for x in pairs if x["rank"] and x["rank"] <= k)
        h5 = sum(1 for x in pairs if x["rank"] and x["rank"] <= k5)
        mrr = sum(1.0 / x["rank"] for x in pairs if x["rank"] and x["rank"] <= k) / n if n else 0.0
        hh10 = sum(1 for x in pairs if x["home_rank"] and x["home_rank"] <= k)
        nh = sum(1 for p in gold_a if p["gold"]["home_nodes"])
        per_task = defaultdict(list)
        for x in pairs:
            per_task[x["query_id"]].append(bool(x["rank"] and x["rank"] <= k))
        macro = sum(sum(v) / len(v) for v in per_task.values()) / len(per_task) if per_task else 0.0

        def split(keyf):
            out = {}
            for key in sorted({keyf(x) for x in pairs}):
                sub = [x for x in pairs if keyf(x) == key]
                s10 = sum(1 for x in sub if x["rank"] and x["rank"] <= k)
                out[key] = {"pairs": len(sub), "recall_at_k": round(s10 / len(sub), 4),
                            "wilson": [round(v, 4) for v in C.wilson(s10, len(sub), z)]}
            return out

        a = {"pairs": n, "tasks": len(per_task),
             "recall_at_5": round(h5 / n, 4) if n else None, "recall_at_5_wilson": [round(v, 4) for v in C.wilson(h5, n, z)],
             "recall_at_10": round(h10 / n, 4) if n else None, "recall_at_10_wilson": [round(v, 4) for v in C.wilson(h10, n, z)],
             "hits_at_5": h5, "hits_at_10": h10, "mrr_at_10": round(mrr, 4),
             "macro_recall_at_10_over_tasks": round(macro, 4),
             "home_node_recall_at_10": {"pairs_with_home": nh, "hits": hh10,
                                        "recall": round(hh10 / nh, 4) if nh else None},
             "by_repo": split(lambda x: x["repo"]), "by_identifier_kind": split(lambda x: x["via"])}

        b = []
        for spec in gold_b + gold_bd:
            row = {"label": spec["label"], "diagnostic": spec in gold_bd, "status": spec["status"]}
            if spec["gold"] is None:
                row.update({"hit": False, "rank": None, "why": spec["status"]})
                if arm == "H" and spec.get("sections_containing_anchor"):
                    order = [row_id for _n, g, row_id in h_mixed_order(runs["H"][spec["query_id"]])]
                    holders = [f"Section:{s[1]}" for s in spec["sections_containing_anchor"]]
                    pos = [order.index(h) + 1 for h in holders if h in order]
                    row["containing_section_rank_among_rulings_and_sections"] = min(pos) if pos else None
            else:
                rk = rank_of(spec["gold"]["nodes"], runs[arm][spec["query_id"]]["candidates"])
                row.update({"hit": bool(rk and rk <= k), "rank": rk})
            b.append(row)

        c_rows = []
        for spec in gold_c:
            run = runs[arm][spec["query_id"]]
            top = run["candidates"][:k]
            row = {"query_id": spec["query_id"], "candidates_at_k": len(top),
                   "distinct_documents_at_k": len({(c[0], catalog[c[0]]["rulings"][c[1]]["doc_id"]) for c in top})}
            if arm == "O":
                row.update({"nonzero": run["nonzero"], "above_threshold": run["above_threshold"],
                            "threshold": run["threshold"], "registration_would_bind": run["registration_would_bind"]})
            c_rows.append(row)

        bar_a = a["recall_at_10"] is not None and a["recall_at_10"] >= 0.80
        bar_b = all(x["hit"] for x in b if not x["diagnostic"])
        results["arms"][arm] = {"A": a, "B": b, "C": c_rows,
                                "bar": {"recall_at_10_ge_0_80": bar_a, "every_B_pair_at_k": bar_b,
                                        "pass": bar_a and bar_b}}

        for p, x in zip(gold_a, pairs):
            if x["rank"] and x["rank"] <= k:
                continue
            miss_rows.append({"arm": arm, "set": "A", "pair_id": p["pair_id"], "query_id": p["query_id"],
                              "gold": {"key": p["gold"]["key"], "label": p["gold"]["label"], "path": p["gold"]["path"],
                                       "text": snippet(p["gold"]["text"], 400)},
                              "top3": top3(arm, p["query_id"]), "signals": signals(arm, p["query_id"], p["gold"], x["rank"])})
        for spec, row in zip(gold_b + gold_bd, b):
            if row["hit"]:
                continue
            m = {"arm": arm, "set": "B" if not row["diagnostic"] else "B-diagnostic", "pair_id": spec["label"],
                 "query_id": spec["query_id"], "top3": top3(arm, spec["query_id"])}
            if spec["gold"] is None:
                m["gold"] = {"key": None, "label": None, "path": spec.get("ruling_document"),
                             "text": f"(no Ruling node) anchor: {spec.get('ruling_anchor')!r}"}
                m["signals"] = {"rank": None, "cause_signals": [f"parse gap: {spec['status']}"],
                                **({"containing_section_rank": row.get("containing_section_rank_among_rulings_and_sections")}
                                   if arm == "H" else {})}
            else:
                m["gold"] = {"key": spec["gold"]["key"], "label": spec["gold"]["label"], "path": spec["gold"]["path"],
                             "text": snippet(spec["gold"]["text"], 400)}
                m["signals"] = signals(arm, spec["query_id"], spec["gold"], row["rank"])
            miss_rows.append(m)

    results["misses"] = {arm: {"A": sum(1 for m in miss_rows if m["arm"] == arm and m["set"] == "A"),
                               "B": sum(1 for m in miss_rows if m["arm"] == arm and m["set"] == "B"),
                               "A_cause_signals": dict(Counter(c for m in miss_rows if m["arm"] == arm and m["set"] == "A"
                                                               for c in m["signals"]["cause_signals"]))}
                         for arm in ARMS}
    ev("results.json").write_text(json.dumps(results, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    ev("misses.jsonl").write_text("".join(json.dumps(m, sort_keys=True, ensure_ascii=False) + "\n" for m in miss_rows),
                                  encoding="utf-8")

    lines = ["# SEL-001 misses: every A and B miss, per arm, with the task's top 3 and the missed ruling's text", "",
             "Generated by `scripts/sel001/score.py` from `evidence/sel001/`. Cause signals are mechanical "
             "(`score.py` `signals`); the delivery report names a cause only where they show one.", ""]
    for arm in ARMS:
        for st in ("B", "B-diagnostic", "A"):
            rows = [m for m in miss_rows if m["arm"] == arm and m["set"] == st]
            if not rows:
                continue
            lines += [f"## Arm {arm}, set {st}: {len(rows)} miss(es)", ""]
            for m in rows:
                g = m["gold"]
                lines += [f"### {m['pair_id']}", "",
                          f"- Missed: `{g['label'] or g['key'] or '(none)'}` in `{g['path']}`, rank "
                          f"{m['signals'].get('rank') or 'beyond the list'}",
                          f"- Ruling text: {g['text']}",
                          f"- Signals: {'; '.join(m['signals']['cause_signals'])}"
                          + (f" (overlap {m['signals'].get('overlap_with_gold')}, shared: "
                             f"{', '.join(m['signals'].get('shared_terms') or []) or 'none'})"
                             if 'overlap_with_gold' in m['signals'] else ""),
                          "- Top 3:"]
                for i, t in enumerate(m["top3"], 1):
                    lines.append(f"  {i}. `{t['label'] or t['node']}` ({t['path']}, {t['score']:.4g}): {t['text']}")
                lines.append("")
    ev("misses.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({arm: {"A": {k2: results["arms"][arm]["A"][k2] for k2 in
                                  ("pairs", "tasks", "recall_at_5", "recall_at_10", "recall_at_10_wilson", "mrr_at_10")},
                            "B": [(x["label"], x["hit"], x["rank"]) for x in results["arms"][arm]["B"]],
                            "bar": results["arms"][arm]["bar"]} for arm in ARMS}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
