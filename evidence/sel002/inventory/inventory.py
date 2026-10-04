"""Decision-backlog probe, read-only. Inventories numbered decisions in squiddy, seldon and arnold,
and reports duplicate ids, unrecorded amendments, near-duplicate text, draft status and enforcement.
Writes only into this probe directory. Zero model calls, no network."""
import json, math, re, collections, subprocess, sys
from pathlib import Path

GH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "mnt/GitHub"
OUT = Path(__file__).parent
AMEND = re.compile(r"\b(amends?|amended|revises?|revised|supersed(?:es|ed|e)|replaces?|replaced|reverses?|reversed|withdraws?|withdrawn|overrides?|retires?|retired|narrows?|rescinds?)\b", re.I)
REF = re.compile(r"\b(?:AD-\d{3}(?:-R\d+)?|DN-\d{3}|R-\d{1,3}|EX-REQ-\d+|DI-\d{3}|ADR-\d{3})\b")
STOP = set("the a an and or of to in is it for on by with as at be this that are from not no its their which when any each every one all must never always only into than then so if but was were has have had do does done can will would should may".split())

def status_of(text):
    m = re.search(r"^\*{0,2}Status:?\*{0,2}:?\s*(.+)$", text, re.M | re.I)
    return m.group(1).strip()[:120] if m else ""

def units_squiddy():
    out = []
    start = re.compile(r"^(?:#+\s*|\s*[-*]\s*\*\*|\*\*)(R-\d{1,3})\b")
    for f in sorted((GH / "squiddy/docs/design").glob("*.md")):
        lines = f.read_text(encoding="utf-8").splitlines()
        st = status_of("\n".join(lines[:30]))
        cur = None
        for i, ln in enumerate(lines):
            m = start.match(ln)
            if m:
                if cur: out.append(cur)
                cur = {"id": m.group(1), "repo": "squiddy", "file": str(f.relative_to(GH)), "line": i + 1, "status": st, "text": [ln]}
                continue
            if cur is not None:
                if ln.startswith("#") or (ln.startswith("- **") and not ln.startswith("  ")) and REF.search(ln[:12] or ""):
                    out.append(cur); cur = None; continue
                if ln.startswith("#"):
                    out.append(cur); cur = None; continue
                cur["text"].append(ln)
        if cur: out.append(cur)
    for name, pat in (("docs/EXTRACTION_DESIGN_SPEC.md", r"^\|\s*(EX-REQ-\d+)"), ("docs/DECISIONS_INHERITED.md", r"^\|\s*(DI-\d{3})")):
        p = GH / "squiddy" / name
        if p.exists():
            for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines()):
                m = re.match(pat, ln)
                if m: out.append({"id": m.group(1), "repo": "squiddy", "file": "squiddy/" + name, "line": i + 1, "status": "", "text": [ln]})
    return out

def units_docs(repo, globs, prefix):
    out = []
    for g in globs:
        for f in sorted((GH / repo).glob(g)):
            txt = f.read_text(encoding="utf-8")
            st = status_of(txt[:3000])
            labeled = list(re.finditer(r"^(?:\s*[-*]\s*)?\*\*((?:AD-\d{3}-)?R\d+)[.:)\s]", txt, re.M))
            if labeled:
                for j, m in enumerate(labeled):
                    end = labeled[j + 1].start() if j + 1 < len(labeled) else min(len(txt), m.start() + 2500)
                    body = txt[m.start():end]
                    body = re.split(r"\n#+ ", body)[0]
                    out.append({"id": m.group(1), "repo": repo, "file": str(f.relative_to(GH)), "line": txt[:m.start()].count("\n") + 1, "status": st, "text": body.splitlines()})
                continue
            sec = re.search(r"^#+\s*(?:\d+\.\s*)?Decision[^\n]*\n(.*?)(?=^#+\s)", txt, re.M | re.S)
            body = sec.group(1) if sec else txt[:1500]
            out.append({"id": f"{prefix}:{f.stem}", "repo": repo, "file": str(f.relative_to(GH)), "line": 1, "status": st, "text": body.splitlines(), "whole_doc": not bool(sec)})
    return out

units = units_squiddy()
units += units_docs("seldon", ["docs/design/AD-0*.md"], "seldon")
units += units_docs("arnold", ["docs/adr/*.md", "docs/ontology/*.md"], "arnold")
for u in units:
    u["text"] = "\n".join(u["text"]).strip()[:2500]
    u["refs"] = sorted(set(REF.findall(u["text"])) - {u["id"]})
    u["amend_words"] = sorted(set(w.lower() for w in AMEND.findall(u["text"])))
    u["chars"] = len(u["text"])

# enforcement: squiddy R-ids referenced by code, tests, conformance
code = ""
for p in list((GH / "squiddy/squiddy").rglob("*.py")) + list((GH / "squiddy/tests").rglob("*.py")) + list((GH / "squiddy/squiddy").rglob("*.yaml")):
    try: code += p.read_text(encoding="utf-8") + "\n"
    except Exception: pass
cited = collections.Counter(re.findall(r"\bR-\d{1,3}\b", code))
for u in units:
    if u["repo"] == "squiddy" and u["id"].startswith("R-"):
        u["code_refs"] = cited.get(u["id"], 0)

(OUT / "units.jsonl").write_text("".join(json.dumps(u, ensure_ascii=False) + "\n" for u in units), encoding="utf-8")

# near-duplicates by tf-idf cosine
def toks(t): return [w for w in re.findall(r"[a-z][a-z0-9_-]{2,}", t.lower()) if w not in STOP]
docs = [collections.Counter(toks(u["text"])) for u in units]
df = collections.Counter(w for d in docs for w in d)
N = len(docs)
vecs = []
for d in docs:
    v = {w: c * math.log(N / df[w]) for w, c in d.items() if df[w] < N}
    n = math.sqrt(sum(x * x for x in v.values())) or 1
    vecs.append({w: x / n for w, x in v.items()})
pairs = []
for i in range(N):
    for j in range(i + 1, N):
        a, b = vecs[i], vecs[j]
        if len(a) > len(b): a, b = b, a
        s = sum(x * b.get(w, 0) for w, x in a.items())
        if s >= 0.35 and units[i]["id"] != units[j]["id"]:
            pairs.append((round(s, 3), i, j))
pairs.sort(reverse=True)

ids = collections.Counter((u["repo"], u["id"]) for u in units)
rep = {
    "counts": dict(collections.Counter(u["repo"] for u in units)),
    "duplicate_ids": [{"repo": r, "id": i, "n": n, "where": [f"{u['file']}:{u['line']}" for u in units if u["repo"] == r and u["id"] == i]} for (r, i), n in ids.items() if n > 1],
    "heading_only": [f"{u['repo']} {u['id']} {u['file']}:{u['line']}" for u in units if u["chars"] < 120],
    "draft_status": sorted({f"{u['file']} :: {u['status']}" for u in units if re.search(r"draft|proposed", u["status"], re.I)}),
    "amending_units": [{"id": u["id"], "repo": u["repo"], "where": f"{u['file']}:{u['line']}", "words": u["amend_words"], "refs": u["refs"]} for u in units if u["amend_words"] and u["refs"]],
    "squiddy_R_without_code_ref": sorted({u["id"] for u in units if u.get("code_refs") == 0}, key=lambda s: int(s[2:])),
    "near_duplicate_pairs": [{"sim": s, "a": f"{units[i]['repo']} {units[i]['id']} {units[i]['file']}:{units[i]['line']}", "b": f"{units[j]['repo']} {units[j]['id']} {units[j]['file']}:{units[j]['line']}"} for s, i, j in pairs[:80]],
    "whole_doc_units": [f"{u['repo']} {u['id']}" for u in units if u.get("whole_doc")],
}
(OUT / "inventory_report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in rep.items()}, indent=1))
