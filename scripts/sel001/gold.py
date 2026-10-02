"""SEL-001 steps 4 to 6: the gold sets, and the stripped query text every arm reads.

Run with Seldon's interpreter, from the Seldon repository root, with the Neo4j credentials loaded:

    python -m dotenv -f .env run -- python scripts/sel001/gold.py

Reads, never writes, the two Seldon databases (the registered CC tasks) and the two governed ledgers (the Ruling,
Section and Document nodes). Writes, under `evidence/sel001/`: `catalog.json`, `queries.jsonl`, `gold_a.jsonl`,
`gold_b.jsonl`, `gold_b_diagnostics.jsonl`, `gold_c.jsonl` and `gold_summary.json`. Every rule it applies is
`evidence/sel001/protocol.md` section 3, through `common.py`. Deterministic: the same ledgers, databases and task
files give byte-identical files.
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

from seldon.config import get_neo4j_driver, load_project_config  # noqa: E402
from seldon.core import governed  # noqa: E402

#: Document kinds that are a ruling's home: where a ruling is stated rather than restated.
HOME_KINDS = ("design", "ontology", "requirements")


# ------------------------------------------------------------------------------------------------
# the governed graphs
# ------------------------------------------------------------------------------------------------

def catalog_of(graph_name: str, ledger: Path) -> dict:
    """Documents, Rulings and Sections of one governed graph, replayed from its ledger by Seldon's own reader."""
    if not ledger.is_file():
        raise SystemExit(f"FATAL: no governed ledger at {ledger}; build the graph first (SEL-001 step 1)")
    view = governed.read_ledger(ledger)
    docs, rulings, sections = {}, {}, {}
    for (cls, nid), p in sorted(view.nodes.items()):
        if cls == "Document":
            docs[nid] = {"path": p.get("path"), "title": p.get("title") or "", "doc_kind": p.get("doc_kind")}
    for (cls, nid), p in sorted(view.nodes.items()):
        if cls == "Ruling":
            d = docs.get(p.get("doc_id"), {})
            rulings[nid] = {"graph": graph_name, "id": nid, "doc_id": p.get("doc_id"), "path": d.get("path"),
                            "doc_kind": d.get("doc_kind"), "label": p.get("ruling_identifier"),
                            "matched_pattern": p.get("matched_pattern"), "text": p.get("text") or "",
                            "span": [p.get("span_start"), p.get("span_end")]}
        elif cls == "Section":
            d = docs.get(p.get("doc_id"), {})
            sections[nid] = {"graph": graph_name, "id": nid, "doc_id": p.get("doc_id"), "path": d.get("path"),
                             "span": [p.get("span_start"), p.get("span_end")]}
    return {"documents": docs, "rulings": rulings, "sections": sections}


def documents_named(cat: dict, ident: str) -> list[str]:
    """Documents whose title or dateless file name opens with `ident` (DN-025, AD-030)."""
    rx = re.compile(rf"^{re.escape(ident)}(?![0-9])")
    return sorted(did for did, d in cat["documents"].items()
                  if rx.match(d["title"].strip()) or rx.match(C.stem_nodate(d["path"] or "")))


def family_docs(cat: dict, key: str) -> set[str]:
    """The task's own file, addenda, errata and RESULT: CC-task documents in the family. A design note named after
    an incident (Squiddy's DN-031 is `INC-001_...`) shares the task's code and is a ruling's home, not the task."""
    return {did for did, d in cat["documents"].items()
            if d["path"] and d["doc_kind"] == "cc_task" and C.in_family(key, d["path"])}


# ------------------------------------------------------------------------------------------------
# resolution (protocol section 3)
# ------------------------------------------------------------------------------------------------

def gold_for_ruling(r: dict, scope: list[str], cats: dict, family: dict[str, set[str]]) -> dict:
    """One gold ruling: its key, and the Ruling nodes that count as retrieving it (none from the family)."""
    if C.is_global_label(r["label"]):
        nodes = [(g, rid) for g in scope for rid, x in cats[g]["rulings"].items()
                 if x["label"] == r["label"] and x["doc_id"] not in family[g]]
        key = f"label:{r['label']}"
    else:
        nodes = [(r["graph"], r["id"])] if r["doc_id"] not in family[r["graph"]] else []
        key = f"node:{r['graph']}:{r['id']}"
    home = [n for n in nodes if cats[n[0]]["rulings"][n[1]]["doc_kind"] in HOME_KINDS]
    return {"key": key, "label": r["label"], "nodes": [list(n) for n in nodes], "home_nodes": [list(n) for n in home],
            "text": r["text"], "graph": r["graph"], "node": r["id"], "path": r["path"]}


def resolve(text: str, repo: str, scope: list[str], cats: dict, family: dict[str, set[str]]):
    """`(golds, unresolved)` for one task's text. A gold is keyed once however many identifiers reach it."""
    golds: dict[str, dict] = {}
    unresolved: list[dict] = []

    def add(r: dict, ident: str, kind: str) -> bool:
        g = gold_for_ruling(r, scope, cats, family)
        if not g["nodes"]:
            return False
        cur = golds.setdefault(g["key"], {**g, "via": [], "via_kinds": []})
        if ident not in cur["via"]:
            cur["via"].append(ident)
        if kind not in cur["via_kinds"]:
            cur["via_kinds"].append(kind)
        return True

    compounds = sorted(set(C.COMPOUND_RE.findall(text)))
    rest = C.COMPOUND_RE.sub(" ", text)
    for ident in compounds:
        hits = [x for g in scope for x in cats[g]["rulings"].values() if x["label"] == ident]
        ok = [add(x, ident, "ruling") for x in hits]
        if not any(ok):
            unresolved.append({"identifier": ident, "kind": "compound",
                               "why": "no Ruling in scope carries it" if not hits else "only inside the task's family"})
    for ident in sorted(set(C.RULING_RE.findall(rest))):
        hits = [x for g in scope for x in cats[g]["rulings"].values() if x["label"] == ident]
        ok = [add(x, ident, "ruling") for x in hits]
        if not any(ok):
            unresolved.append({"identifier": ident, "kind": "R",
                               "why": "no Ruling in scope carries it" if not hits else "only inside the task's family"})
    for ident in sorted(set(C.DOC_ID_RE.findall(rest))):
        kind = ident.split("-")[0]
        order = list(scope)
        if repo != "squiddy" and "squiddy" in scope and re.search(rf"Squiddy(?:'s)?\s+{re.escape(ident)}\b", text):
            order = ["squiddy"]
        found = None
        for g in order:
            ds = documents_named(cats[g], ident)
            if ds:
                found = (g, ds)
                break
        if found is None:
            unresolved.append({"identifier": ident, "kind": kind, "why": "no document in scope"})
            continue
        g, ds = found
        rs = [x for x in cats[g]["rulings"].values() if x["doc_id"] in ds]
        ok = [add(x, ident, "document") for x in rs]
        if not rs:
            unresolved.append({"identifier": ident, "kind": kind, "why": f"document in {g} states no Ruling",
                               "documents": ds})
        elif not any(ok):
            unresolved.append({"identifier": ident, "kind": kind, "why": "only inside the task's family"})
    return sorted(golds.values(), key=lambda x: x["key"]), unresolved


# ------------------------------------------------------------------------------------------------
# the registered tasks
# ------------------------------------------------------------------------------------------------

def registered_tasks(repo: str, root: Path) -> list[dict]:
    """Every ResearchTask that `seldon cc register` created (it carries `source_file`), read-only."""
    cfg = load_project_config(root)
    driver = get_neo4j_driver(cfg)
    try:
        with driver.session(database=cfg["neo4j"]["database"]) as s:
            rows = s.run("MATCH (t:Artifact:ResearchTask) WHERE t.source_file IS NOT NULL "
                         "RETURN t.artifact_id AS id, t.name AS name, t.state AS state, "
                         "t.source_file AS file ORDER BY t.source_file, t.artifact_id").data()
    finally:
        driver.close()
    return [{**r, "repo": repo} for r in rows]


def correction_texts(root: Path) -> list[tuple[str, str]]:
    """`(family key, text)` of every addendum or erratum: what it corrects is its own family, and whatever it names."""
    out = []
    for p in sorted(list((root / "cc_tasks").glob("*.md")) + list((root / "docs").glob("*.md"))):
        if re.search(r"(?i)addendum|erratum", p.name):
            out.append((C.family_key(str(p)), p.read_text(encoding="utf-8")))
    return out


def corrected(task_file: str, corrections: list[tuple[str, str]]) -> bool:
    """Protocol section 3: a later addendum or erratum names the task, by its code or its slug. Its own family's
    corrections count by file name; any other correction counts when its text names the task's key."""
    key = C.family_key(task_file)
    rx = re.compile(rf"(?<![A-Za-z0-9]){re.escape(key)}(?![0-9])")
    return any(C.in_family(k, task_file) or rx.search(text) for k, text in corrections)


def main() -> int:
    cfg = C.load_config()
    graphs = sorted({g for r in cfg["repos"].values() for g in r["scope"]})
    cats = {g: catalog_of(g, Path(cfg["repos"][g]["root"]) / cfg["graph_dir"] / "ledger" / "events.jsonl")
            for g in graphs}
    C.evidence(cfg, "catalog.json").write_text(json.dumps(cats, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                                               encoding="utf-8")

    queries: dict[str, dict] = {}
    missing_files: list[str] = []

    def query_for(repo: str, rel: str, task: dict | None = None) -> dict | None:
        root = Path(cfg["repos"][repo]["root"])
        qid = f"{repo}:{rel}"
        if qid in queries:
            return queries[qid]
        path = root / rel
        if not path.is_file():
            missing_files.append(qid)
            return None
        text = path.read_text(encoding="utf-8")
        scope = cfg["repos"][repo]["scope"]
        key = C.family_key(rel)
        fam = {g: family_docs(cats[g], key) for g in scope}
        stripped = C.strip_identifiers(text)
        queries[qid] = {"query_id": qid, "repo": repo, "task_file": rel, "scope": scope,
                        "task_state": (task or {}).get("state"), "task_name": (task or {}).get("name"),
                        "family_key": key, "family_doc_ids": {g: sorted(v) for g, v in fam.items()},
                        "text": text, "stripped_text": stripped, "stripped_sha256": C.sha256_text(stripped)}
        return queries[qid]

    # ---- set A (step 4) --------------------------------------------------------------------------
    gold_a, unresolved_all, tasks_all = [], [], []
    for repo in cfg["repos"]:
        root = Path(cfg["repos"][repo]["root"])
        for t in registered_tasks(repo, root):
            tasks_all.append(t)
            q = query_for(repo, t["file"], t)
            if q is None:
                continue
            fam = {g: set(v) for g, v in q["family_doc_ids"].items()}
            golds, unresolved = resolve(q["text"], repo, q["scope"], cats, fam)
            for u in unresolved:
                unresolved_all.append({"query_id": q["query_id"], **u})
            for g in golds:
                gold_a.append({"pair_id": f"{q['query_id']}|{g['key']}", "query_id": q["query_id"], "repo": repo,
                               "task_file": t["file"], "task_state": t["state"], "gold": g})

    # ---- set B (step 5) and its diagnostics -------------------------------------------------------
    def b_rows(specs: list[dict]) -> list[dict]:
        out = []
        for spec in specs:
            q = query_for(spec["repo"], spec["task_file"])
            if q is None:
                raise SystemExit(f"FATAL: set B task {spec['task_file']} is not on disk")
            fam = {g: set(v) for g, v in q["family_doc_ids"].items()}
            row = {"label": spec["label"], "query_id": q["query_id"], "repo": spec["repo"],
                   "task_file": spec["task_file"]}
            if spec.get("ruling"):
                rs = [x for g in q["scope"] for x in cats[g]["rulings"].values() if x["label"] == spec["ruling"]]
                if not rs:
                    raise SystemExit(f"FATAL: set B ruling {spec['ruling']} is not a Ruling in scope")
                row["gold"] = gold_for_ruling(rs[0], q["scope"], cats, fam)
                row["status"] = "ruling node exists"
            else:
                g = spec["repo"]
                doc = next((did for did, d in cats[g]["documents"].items() if d["path"] == spec["ruling_document"]),
                           None)
                row["ruling_document"] = spec["ruling_document"]
                row["ruling_anchor"] = spec["ruling_anchor"]
                if doc is None:
                    row["gold"] = None
                    row["status"] = "the ruling's document is not in a governed directory"
                else:
                    rs = [x for x in cats[g]["rulings"].values()
                          if x["doc_id"] == doc and spec["ruling_anchor"] in x["text"]]
                    if rs:
                        row["gold"] = gold_for_ruling(rs[0], q["scope"], cats, fam)
                        row["status"] = "ruling node exists"
                    else:
                        root = Path(cfg["repos"][g]["root"])
                        body = (root / spec["ruling_document"]).read_text(encoding="utf-8")
                        at = body.find(spec["ruling_anchor"])
                        holders = sorted(
                            (sid for sid, s in cats[g]["sections"].items()
                             if s["doc_id"] == doc and s["span"][0] is not None and s["span"][0] <= at < s["span"][1]),
                            key=lambda sid: cats[g]["sections"][sid]["span"][1] - cats[g]["sections"][sid]["span"][0])
                        row["gold"] = None
                        row["status"] = "parse gap: no Ruling node carries the ruling's text"
                        row["anchor_offset"] = at
                        row["sections_containing_anchor"] = [[g, sid] for sid in holders]
            out.append(row)
        return out

    gold_b = b_rows(cfg["set_b"])
    gold_b_diag = b_rows(cfg["diagnostics_b"])

    # ---- set C (step 6) ---------------------------------------------------------------------------
    pool = []
    for repo in cfg["repos"]:
        root = Path(cfg["repos"][repo]["root"])
        corrections = correction_texts(root)
        for t in tasks_all:
            if t["repo"] != repo or t["state"] != "completed":
                continue
            if not (root / t["file"]).is_file() or C.CORRECTION_NAME_RE.search(Path(t["file"]).name):
                continue
            if corrected(t["file"], corrections):
                continue
            pool.append(f"{repo}:{t['file']}")
    pool = sorted(set(pool))
    sample = random.Random(int(cfg["set_c"]["seed"])).sample(pool, int(cfg["set_c"]["n"]))
    gold_c = []
    by_qid = {f"{t['repo']}:{t['file']}": t for t in tasks_all}
    for qid in sample:
        t = by_qid[qid]
        q = query_for(t["repo"], t["file"], t)
        gold_c.append({"query_id": q["query_id"], "repo": t["repo"], "task_file": t["file"], "task_state": t["state"]})

    # ---- write ------------------------------------------------------------------------------------
    def write_jsonl(name: str, rows: list[dict]) -> None:
        C.evidence(cfg, name).write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n"
                                                 for r in rows), encoding="utf-8")

    write_jsonl("gold_a.jsonl", gold_a)
    write_jsonl("gold_b.jsonl", gold_b)
    write_jsonl("gold_b_diagnostics.jsonl", gold_b_diag)
    write_jsonl("gold_c.jsonl", gold_c)
    write_jsonl("queries.jsonl", [{k: v for k, v in q.items() if k != "text"}
                                  for _id, q in sorted(queries.items())])
    write_jsonl("gold_a_unresolved.jsonl", unresolved_all)

    tasks_with_pairs = {r["query_id"] for r in gold_a}
    summary = {
        "graphs": {g: {"documents": len(c["documents"]), "rulings": len(c["rulings"]), "sections": len(c["sections"])}
                   for g, c in cats.items()},
        "registered_tasks": dict(Counter(t["repo"] for t in tasks_all)),
        "registered_task_files_missing": sorted(missing_files),
        "set_a": {"pairs": len(gold_a), "tasks": len(tasks_with_pairs),
                  "pairs_by_repo": dict(Counter(r["repo"] for r in gold_a)),
                  "tasks_by_repo": dict(Counter(q.split(":", 1)[0] for q in tasks_with_pairs)),
                  "pairs_by_via_kind": dict(Counter("+".join(sorted(r["gold"]["via_kinds"])) for r in gold_a)),
                  "unresolved_identifiers": len(unresolved_all),
                  "unresolved_by_kind_and_why": dict(Counter(f"{u['kind']}: {u['why']}" for u in unresolved_all)),
                  "unresolved_distinct": dict(Counter(u["identifier"] for u in unresolved_all).most_common())},
        "set_b": [{"label": r["label"], "status": r["status"]} for r in gold_b],
        "set_c": {"pool": len(pool), "seed": cfg["set_c"]["seed"], "n": len(gold_c),
                  "sample": [r["query_id"] for r in gold_c]},
        "queries": len(queries),
    }
    C.evidence(cfg, "gold_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n",
                                                    encoding="utf-8")
    print(json.dumps(summary, indent=1, sort_keys=True)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
