"""SEL-036 Part B: the catalog, from the seeds and the resolver's checkpoint. Zero model calls, zero network.

    python scripts/sel036/build_candidates.py            # writes the candidates file and the counts
    python scripts/sel036/build_candidates.py --check    # exit 1 when the written file differs from a rebuild

Writes graphs/seldon-biblio/corpus/candidates/seldon_biblio_candidates.yaml (squiddy's `candidates` intake, which
graph.yaml declares) and graphs/seldon-biblio/evidence/sel036/catalog_counts.json. Reads whatever the checkpoint
holds and states its n (~/GitHub/CLAUDE.md section 15.6): a seed whose chain has not finished is cataloged as
`unresolved_pending`, never silently dropped.

**One entry per seed.** `kind` is squiddy's (work, standard, software); a grey-literature seed is a `work` with
`entry_kind: grey`. The fields the task asks for (Part B) are carried from the CONFIRMING authority's answer, never
from an unconfirmed near miss; where no authority confirmed, from the seed (what the citing note states), marked
`verification_status: declared`. `resolution` keeps every attempt with its answer (the operator's rule of 2026-09-15).

**One more entry per documentation snapshot** (Part C): a `work` with `entry_kind: documentation`, whose text is the
held derivative under the archive root and whose `documents` names the software or grey entry it documents. A page
the host refused is an entry too, `manual_acquisition: true`, with its posture and evidence, for the Desktop thread.

**Declines.** A work or grey seed no authority confirmed, after every authority was tried, is `excluded:declined`
with every attempt kept. A standard is never declined: unconfirmed, it is a metadata-only record of what the note
cites (Part B).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import resolve as R  # noqa: E402  (the same config, keys and plan as the resolver)

OUT = "graphs/seldon-biblio/corpus/candidates/seldon_biblio_candidates.yaml"
COUNTS = "graphs/seldon-biblio/evidence/sel036/catalog_counts.json"
CATALOGED_BY = "scripts/sel036/build_candidates.py (SEL-036 Part B)"

#: Who sells a standard's text, so its entry is `access: purchase` (metadata only, never declined). Every other
#: standard's text is published free by its body (W3C, IETF, NIST, OMG, the CFR, WHO, LoC, NDSA, OpenSSF).
PURCHASE_PUBLISHERS = ("ISO", "IEEE", "SAE", "RTCA", "Project Management Institute")
#: The resolver's postures (resolve.posture) in squiddy's vocabulary (squiddy/posture.yaml `postures`); a host this
#: task may not ask (`off_allowlist`) is the kit's own refusal, which squiddy records with no posture.
POSTURE_MAP = {"open": "open", "bot_wall": "refused", "login_required": "refused", "javascript_only": "refused",
               "unreachable": "unreachable", "off_allowlist": None}


def cited_in(seed: dict) -> str:
    return "; ".join(str(x) for x in seed.get("cited_in") or [])


def governed_of(gov: dict) -> dict:
    out: dict = {}
    for key, g in (gov or {}).items():
        for sid in g.get("seeds") or []:
            out.setdefault(sid, []).append(key)
    return out


def chain(seed: dict, units: list[dict], done: dict) -> list[dict]:
    return [done[u["key"]] for u in units if u["phase"] == "resolve" and u["seed"] == seed["id"] and u["key"] in done]


def access_of(seed: dict, ans: dict, docs: list[dict]) -> str:
    if seed["kind"] == "standard":
        pub = str(seed.get("publisher") or "")
        return "purchase" if any(p in pub for p in PURCHASE_PUBLISHERS) else "open"
    if seed["kind"] == "software":
        return "open"
    if ans.get("is_oa") or ans.get("oa_pdf_url") or any(d.get("acquisition") == "auto" for d in docs):
        return "open"
    return "restricted_or_unknown"


def seed_entry(seed: dict, rows: list[dict], n_auth: int, gov_keys: list[str], docs: list[dict]) -> dict:
    conf = next((r for r in rows if r.get("confirmed")), None)
    ans = (conf or {}).get("answer") or {}
    finished = conf is not None or len(rows) >= n_auth
    kind = "work" if seed["kind"] == "grey" else seed["kind"]
    e = {"id": seed["id"], "kind": kind, "entry_kind": seed["kind"], "stage": "cataloged",
         "title": (ans.get("title") if conf and seed["kind"] in ("work", "grey") and not
                   str(seed.get("title", "")).lower().startswith(("arxiv:", "doi:")) else None) or seed.get("title"),
         "title_cited": seed.get("title"), "provenance_flag": "public", "cited_in": cited_in(seed),
         "governed_citations": gov_keys, "cataloged_by": CATALOGED_BY}
    if str(seed.get("title", "")).lower().startswith(("arxiv:", "doi:")) and ans.get("title"):
        e["title"] = ans["title"]
    authors = ans.get("authors") or seed.get("authors")
    for k, v in (("authors", authors), ("year", ans.get("year") or seed.get("year")),
                 ("venue", ans.get("venue") or seed.get("venue")), ("publisher", ans.get("publisher") or seed.get("publisher")),
                 ("edition", seed.get("edition")), ("doi", ans.get("doi") or R.norm_doi(seed.get("doi"))),
                 ("openalex_id", ans.get("openalex_id")), ("arxiv_id", ans.get("arxiv_id") or seed.get("arxiv")),
                 ("isbn", ans.get("isbn") or ([seed["isbn"]] if seed.get("isbn") else None)),
                 ("standard_number", seed.get("standard_number")),
                 ("repository", seed.get("url") if seed["kind"] == "software" else None),
                 ("version", ans.get("version") or seed.get("edition") if seed["kind"] == "software" else None),
                 ("release_date", ans.get("release_date")), ("pypi", ans.get("pypi")),
                 ("licence", ans.get("licence")), ("licence_url", ans.get("licence_url")),
                 ("licence_file", ans.get("licence_file")), ("licence_file_first_line", ans.get("licence_file_first_line")),
                 ("oa_url", ans.get("oa_pdf_url") or ans.get("oa_landing_url"))):
        if v not in (None, "", []):
            e[k] = v
    if e.get("licence_file") and not ans.get("pypi"):
        e["licence_basis"] = "LICENSE file first line (scripts/sel036/resolve.py spdx_guess)"
    if str(e.get("doi") or "").startswith("10.48550/") and not e.get("openalex_id"):
        # An arXiv DOI is DataCite's, and squiddy's acquire asks DataCite only when Crossref fails; this task's Network
        # line does not name api.datacite.org, so the forwarder refuses it. With no OpenAlex record either, the DOI
        # leaves acquire nothing to resolve and it halts (first build, li2024kgllm). The arXiv id is the identifier
        # the note gives; the DOI is kept beside it, and the text comes from arXiv itself (arxiv.org is allowed).
        e["arxiv_doi"] = e.pop("doi")
        e["direct_download_url"] = f"https://arxiv.org/pdf/{e['arxiv_id']}"
    url = seed.get("url") or ans.get("url") or (f"https://doi.org/{e['doi']}" if e.get("doi") else None) \
        or (f"https://arxiv.org/abs/{e['arxiv_id']}" if e.get("arxiv_id") else None)
    if url:
        e["source_url"] = url
    e["access"] = access_of(seed, ans, docs)
    e["resolved_by"] = conf["authority"] if conf else None
    # Where the confirmed record and the citing note disagree: the note is corrected by the record, never silently.
    disc = []
    if conf:
        sd = R.norm_doi(seed.get("doi"))
        if sd and ans.get("doi") and sd != ans["doi"]:
            disc.append(f"the note cites doi {sd}; the record is {ans['doi']}")
        if seed.get("year") and ans.get("year") and int(seed["year"]) != int(ans["year"]):
            disc.append(f"the note cites {seed['year']}; the record is {ans['year']}")
        if R.surnames_agree(seed, ans) is False:
            disc.append(f"the note cites {seed.get('authors')}; the record's authors are {ans.get('authors')}")
        if seed.get("arxiv") and ans.get("doi") and "arxiv" not in ans["doi"]:
            disc.append(f"the note cites the preprint arXiv:{seed['arxiv']}; the record is its published version")
    if disc:
        e["citation_discrepancies"] = disc
    e["resolution"] = [{"authority": r["authority"], "confirmed": bool(r.get("confirmed")), "why": r.get("why") or r.get("error"),
                        "similarity": r.get("similarity"),
                        "queries": [{k: q.get(k) for k in ("url", "status", "final_url", "error", "at") if q.get(k) is not None}
                                    for q in r.get("queries") or []],
                        "answer": {k: v for k, v in (r.get("answer") or {}).items() if k in
                                   ("title", "year", "doi", "openalex_id", "arxiv_id", "venue", "version", "licence")
                                   and v not in (None, "", [])} or None}
                       for r in rows]
    page = next((r for r in rows if r.get("authority") == "page" and r.get("posture")), None)
    if page:
        p = page["posture"]
        e.update({"posture": POSTURE_MAP.get(p["posture"], None), "access_posture": p["posture"],
                  "posture_host": p.get("host"), "posture_observed_at": p.get("at"),
                  "posture_evidence": f"HTTP {p.get('status')} {p.get('error') or ''} first bytes: {p.get('first_bytes')!r}"[:400]})
    # The disposition, the verification status and what the text route is.
    if not finished:
        e.update({"disposition": "excluded:deferred", "verification_status": "unresolved_pending",
                  "decline_reason": f"resolution unfinished: {len(rows)} of {n_auth} authorities asked"})
    elif conf is None and seed["kind"] in ("work", "grey") and not any(d.get("acquisition") == "auto" for d in docs) \
            and (e.get("access_posture") in ("off_allowlist", "bot_wall", "login_required", "javascript_only")
                 or (seed.get("publisher_host") and not seed.get("url"))):
        # Not every authority could be ASKED: the publisher's own page is a host this task's Network line forbids, or
        # one that refused a script. That is a posture, not a decline (the operator's rule: such a host is recorded
        # and marked for manual acquisition). The Desktop thread confirms it with the operator's browser.
        host = e.get("posture_host") or seed.get("publisher_host")
        e.update({"disposition": "metadata_only", "verification_status": "declared",
                  "metadata_only_reason": "publisher_page_not_reachable_by_script",
                  "manual_acquisition": True, "acquisition": "pending_manual",
                  "manual_reason": f"no index holds it, and its publisher's page ({host}) is "
                                   f"{e.get('access_posture') or 'off the Network line, URL unknown to the note'}"})
    elif conf is None and seed["kind"] in ("work", "grey") and not any(d.get("acquisition") == "auto" for d in docs):
        e.update({"disposition": "excluded:declined", "verification_status": "unconfirmed",
                  "decline_reason": "no authority confirmed the citation after all were tried: "
                                    + "; ".join(f"{r['authority']}: {r.get('why') or r.get('error')}" for r in rows)[:600]})
    else:
        e["verification_status"] = "resolved" if conf else "declared"
        if seed["kind"] == "standard":
            e.update({"disposition": "metadata_only",
                      "metadata_only_reason": "purchase" if e["access"] == "purchase" else "standard_no_doi"})
        elif seed["kind"] == "software":
            e["disposition"] = "metadata_only"
        else:
            e["disposition"] = "active"
    # Manual acquisition: an open text this task's Network line or the host would not let a script take.
    wants_text = e["access"] == "open" and seed["kind"] in ("standard", "grey") and not docs
    if wants_text and e["disposition"] != "excluded:declined":
        e["manual_acquisition"] = True
        e["acquisition"] = "pending_manual"
        e["manual_reason"] = (f"the text is published free and was not fetched: {e.get('access_posture') or 'no fetch route'} "
                              f"at {e.get('posture_host') or url}")
    elif seed["kind"] in ("work",) and not e.get("doi") and not e.get("openalex_id") and e["disposition"] == "active":
        e["acquisition"] = "none"
    return e


def doc_entries(seed: dict, units: list[dict], done: dict, gov_keys: list[str]) -> list[dict]:
    out = []
    for i, u in enumerate([u for u in units if u["phase"] == "fetch" and u["seed"] == seed["id"]], 1):
        r = done.get(u["key"])
        if r is None:
            continue
        p = r.get("posture") or {}
        e = {"id": f"doc_{seed['id']}_{i}", "kind": "work", "entry_kind": "documentation", "work_type": "documentation",
             "stage": "cataloged", "title": r.get("page_title") or f"{seed.get('title')}: {u['url'].rsplit('/', 1)[-1] or 'documentation'}",
             "source_url": u["url"], "documents": seed["id"], "provenance_flag": "public", "cited_in": cited_in(seed),
             "governed_citations": gov_keys, "cataloged_by": CATALOGED_BY,
             "posture": POSTURE_MAP.get(p.get("posture")), "access_posture": p.get("posture"),
             "posture_host": p.get("host"), "posture_observed_at": p.get("at")}
        if r.get("acquisition") == "auto":
            e.update({"disposition": "active", "acquisition": "auto", "acquisition_status": "acquired",
                      "local_path": r["text_path"], "sha256": r["text_sha256"],
                      "raw_path": r["raw_path"],
                      "raw_sha256": r["raw_sha256"], "bytes": r["bytes"], "retrieved_at": r["retrieved_at"],
                      "direct_download_url": r["final_url"], "verification_status": "fetched",
                      "manual_acquisition": False, "access": "open"})
            if r["text_path"] != r["raw_path"]:
                e["text_sha256"] = r["text_sha256"]      # a derivative's own digest; a held PDF is its own text
        else:
            e.update({"disposition": "metadata_only", "metadata_only_reason": "oa_text_not_retrievable",
                      "acquisition": "pending_manual", "manual_acquisition": True, "access": "open",
                      "verification_status": "declared",
                      "posture_evidence": f"HTTP {p.get('status')} {p.get('error') or ''} first bytes: {p.get('first_bytes')!r}"[:400],
                      "manual_reason": f"{p.get('posture')} at {p.get('host')}"})
        out.append(e)
    return out


def build(cfg: dict, seeds_doc: dict, done: dict) -> tuple[dict, dict]:
    seeds = seeds_doc["seeds"]
    units = R.plan(seeds, cfg)
    gov = governed_of(seeds_doc.get("governed"))
    n_auth = len(cfg["authorities"])
    cands = []
    for s in seeds:
        docs = doc_entries(s, units, done, gov.get(s["id"], []))
        cands.append(seed_entry(s, chain(s, units, done), n_auth, gov.get(s["id"], []), docs))
        cands += docs
    # SEL-037: later tasks' fetch checkpoints, applied in the order the config names them (scripts/sel037/overlay.py)
    overlays = []
    for ov in cfg.get("acquired_overlays") or []:
        sys.path.insert(0, str((ROOT / ov).parent))
        import overlay as OV  # noqa: E402  (the overlay module beside its config)
        cands, rep = OV.apply(cands, ROOT / ov, ROOT)
        overlays.append(rep)
    c = {"seeds": len(seeds), "entries": len(cands), "checkpoint_rows": len(done), "overlays": overlays}
    for key in ("entry_kind", "disposition", "verification_status", "access", "resolved_by"):
        c[f"by_{key}"] = {}
        for e in cands:
            v = str(e.get(key))
            c[f"by_{key}"][v] = c[f"by_{key}"].get(v, 0) + 1
    c["manual_acquisition"] = sorted(e["id"] for e in cands if e.get("manual_acquisition"))
    c["declined"] = sorted(e["id"] for e in cands if e.get("disposition") == "excluded:declined")
    c["governed_artifacts"] = len(seeds_doc.get("governed") or {})
    c["governed_artifacts_naming_no_work"] = sorted(k for k, g in (seeds_doc.get("governed") or {}).items()
                                                     if not g.get("seeds"))
    doc = {"candidates": cands}
    return doc, c


def render(doc: dict) -> str:
    head = ("# GENERATED by scripts/sel036/build_candidates.py from graphs/seldon-biblio/intake/seeds.yaml and the\n"
            "# resolver's checkpoint (graphs/seldon-biblio/evidence/sel036/units.jsonl). Do not edit: change a seed or\n"
            "# re-run the resolver, then rebuild. squiddy's `candidates` intake reads this file (graph.yaml).\n")
    return head + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=HERE / "sel036.yaml")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    cfg = R.load_config(a.config)
    seeds_doc = yaml.safe_load((ROOT / cfg["seeds"]).read_text(encoding="utf-8"))
    done = R.load_done(ROOT / cfg["checkpoint"])
    doc, counts = build(cfg, seeds_doc, done)
    text = render(doc)
    out = ROOT / OUT
    if a.check:
        same = out.is_file() and out.read_text(encoding="utf-8") == text
        print("candidates match a rebuild" if same else f"{OUT} differs from a rebuild")
        return 0 if same else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    (ROOT / COUNTS).write_text(json.dumps(counts, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in counts.items() if not isinstance(v, list)}, indent=1))
    print("manual:", counts["manual_acquisition"])
    print("declined:", counts["declined"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
