"""SEL-037 Part B: the fetch checkpoint as an overlay on SEL-036's catalog. Zero network, zero model calls.

scripts/sel036/build_candidates.py builds the catalog from the seeds and SEL-036's resolver checkpoint, then applies
each file `acquired_overlays` names in scripts/sel036/sel036.yaml. This is that overlay: it reads the CURRENT rows of
scripts/sel037/fetch.py's checkpoint (the keys its config plans now; a row of an older fetcher version or an edited
target is history, never applied) and:

- **acquired, `on_entry`:** the entry's text is the held file under the archive root (`local_path`, `sha256`, the raw
  capture and its digest). `raw_sha256` and `text_sha256` are content fields of the graph's candidates intake
  (graph.yaml), so an entry already admitted metadata-only is re-admitted as a REVISION (squiddy SQ-023, R-213), which
  is the kit's own route for "admitted metadata-only, bytes supplied later". It is `active`, its posture `open`.
- **acquired, `doc_entry`:** a standard's text is a new documentation entry `doc_<standard>_1` documenting it (squiddy's
  acquire gives a `standard` no text), as SEL-036 held the OMG specifications; the standard names it (`text_in`).
- **acquired, `doc_many`:** one documentation entry per page.
- **manual:** the entry keeps `acquisition: pending_manual` with THIS task's evidence: the posture, the host, the
  status and first bytes, the time, and the robots reading where it decided.

Every acquired entry carries the provenance stub squiddy's inbox defines (DN-049 R-212; `squiddy.intake`
INBOX_STUB_FIELDS, held flat under `inbox_`): where the text is published, where this copy came from, the licence it is
held under and who says so.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fetch as F  # noqa: E402

CATALOGED_BY = "scripts/sel037/overlay.py (SEL-037 Part B)"
#: SEL-036's posture vocabulary mapped to squiddy's (squiddy/posture.yaml `postures`), with this fetcher's two
#: additions: robots.txt disallowed the path (`robots_disallowed`, squiddy's own word), and the bytes came but are not
#: the work (`rejected`: no host refused anything, so no posture).
POSTURE_MAP = {"open": "open", "bot_wall": "refused", "login_required": "refused", "javascript_only": "refused",
               "unreachable": "unreachable", "off_allowlist": None, "robots_disallowed": "robots_disallowed",
               "rejected": None, "not_retried": "refused"}
#: Fields a now-held entry no longer carries: they described its being unheld.
UNHELD_FIELDS = ("manual_reason", "metadata_only_reason", "metadata_only_detail", "posture_evidence",
                 "decline_reason")


def current_rows(cfg_path: Path, root: Path) -> list[dict]:
    """The checkpoint rows of the units the config plans now, in the config's order. A planned unit with no row is
    reported, never silently skipped (section 15.6: the overlay states its n)."""
    cfg = F.load_config(cfg_path)
    ck = root / cfg["checkpoint"]
    done = {}
    if ck.is_file():
        for line in ck.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if not r.get("error"):
                    done[r["key"]] = r
    rows = []
    for u in F.plan(cfg):
        if u["key"] not in done:
            raise SystemExit(f"FATAL: {ck} has no row for target {u['entry']} (key {u['key'][:12]}); run "
                             f"scripts/sel037/fetch.py to finish it before the catalog is rebuilt")
        rows.append(done[u["key"]])
    return rows


def stub(target: dict, got: dict) -> dict:
    return {"inbox_source_url": got["page_url"], "inbox_obtained_from": got.get("final_url") or got["page_url"],
            "inbox_licence": target["licence"],
            "inbox_stated_by": f"{target['licence_basis']}; recorded by scripts/sel037/fetch.py (SEL-037), "
                               f"licence URLs in the text: {', '.join(got.get('licence_found') or []) or 'none'}"}


def held_fields(target: dict, got: dict) -> dict:
    p = got.get("posture") or {}
    f = {"disposition": "active", "acquisition": "auto", "acquisition_status": "acquired",
         "local_path": got["text_path"], "sha256": got["text_sha256"], "raw_path": got["raw_path"],
         "raw_sha256": got["raw_sha256"], "bytes": got["bytes"], "retrieved_at": got["retrieved_at"],
         "direct_download_url": got.get("final_url") or got["page_url"], "manual_acquisition": False, "access": "open",
         "posture": "open", "access_posture": "open", "posture_host": p.get("host"), "posture_observed_at": p.get("at"),
         "text_pages": got.get("pages"), "text_chars": got.get("text_chars"), **stub(target, got)}
    if got["text_path"] != got["raw_path"]:
        f["text_sha256"] = got["text_sha256"]          # a derivative's own digest; a held PDF is its own text
    if got.get("licence_found"):
        f["licence_found"] = got["licence_found"]
    if target.get("found_by"):
        f["text_found_by"] = target["found_by"]
    return f


def manual_fields(target: dict, row: dict) -> dict:
    p = row.get("manual_posture") or {}
    kind = p.get("posture") or "unknown"
    robots = p.get("robots") or {}
    ev = f"HTTP {p.get('status')} {p.get('error') or ''} first bytes: {(p.get('first_bytes') or '')!r}"
    if robots.get("decision"):
        ev += f"; robots.txt {robots.get('status')} -> {robots.get('decision')}" + \
              (f", rule {robots['rule']}" if robots.get("rule") else "")
    checks = [s.get("check") for s in row.get("steps") or [] if s.get("check") and s.get("check") != "text taken"]
    f = {"manual_acquisition": True, "acquisition": "pending_manual", "posture": POSTURE_MAP.get(kind),
         "access_posture": kind, "posture_host": p.get("host"), "posture_observed_at": p.get("at"),
         "posture_evidence": ev[:400],
         "manual_reason": f"SEL-037 fetch: {kind} at {p.get('host')}" + (f"; {'; '.join(checks)}" if checks else ""),
         "sel037_urls_tried": [s["url"] for s in row.get("steps") or []]}
    return f


def doc_entry(new_id: str, of: dict, target: dict, got: dict, title: str) -> dict:
    return {"id": new_id, "kind": "work", "entry_kind": "documentation", "work_type": "documentation",
            "stage": "cataloged", "title": title, "source_url": got["page_url"], "documents": of["id"],
            "provenance_flag": "public", "cited_in": of.get("cited_in"),
            "governed_citations": of.get("governed_citations") or [], "cataloged_by": CATALOGED_BY,
            "verification_status": "fetched", **held_fields(target, got)}


def apply(cands: list[dict], cfg_path: Path, root: Path) -> tuple[list[dict], dict]:
    """The catalog with the overlay applied, and what it did (for the counts file)."""
    by_id = {e["id"]: e for e in cands}
    report = {"overlay": str(cfg_path.relative_to(root)), "targets": 0, "acquired_on_entry": [], "doc_entries": [],
              "manual": []}
    added = []
    for row in current_rows(cfg_path, root):
        t = row["target"]
        report["targets"] += 1
        e = by_id.get(t["entry"])
        if e is None:
            raise SystemExit(f"FATAL: overlay target {t['entry']} is not a catalog entry")
        for k in ("note", "label", "check"):
            if t.get(k):
                e[f"sel037_{k}"] = " ".join(str(t[k]).split())
        if row["outcome"] != "acquired" and t.get("no_open_copy"):
            # The check found that the only free location is NOT the work: there is nothing for a browser to fetch,
            # so the entry is metadata-only by a finding, not marked manual. Never declined.
            e.update({**manual_fields(t, row), "manual_acquisition": False, "acquisition": "none",
                      "metadata_only_reason": "no_open_access_text",
                      "metadata_only_detail": " ".join(str(t["no_open_copy"]).split())})
            e.pop("manual_reason", None)
            report.setdefault("no_open_copy", []).append(t["entry"])
            continue
        if row["outcome"] != "acquired":
            e.update(manual_fields(t, row))
            report["manual"].append(t["entry"])
            continue
        if t["mode"] == "on_entry":
            for k in UNHELD_FIELDS:
                e.pop(k, None)
            e.update(held_fields(t, row["got"][0]))
            report["acquired_on_entry"].append(t["entry"])
        elif t["mode"] == "doc_entry":
            new_id = f"doc_{t['entry']}_1"
            got = row["got"][0]
            added.append(doc_entry(new_id, e, t, got, got.get("page_title") or f"{e['title']}: text"))
            for k in ("manual_acquisition", "acquisition", "manual_reason", "posture_evidence"):
                e.pop(k, None)
            e["text_in"] = new_id
            report["doc_entries"].append(new_id)
        else:
            for got in row["got"]:
                rel = got["page_url"].split(t.get("id_below") or "/", 1)[-1]
                added.append(doc_entry(got["new_id"], e, t, got, got.get("page_title") or f"{e['title']}: {rel}"))
                report["doc_entries"].append(got["new_id"])
    clash = sorted({a["id"] for a in added} & set(by_id))
    if clash:
        raise SystemExit(f"FATAL: overlay entries collide with catalog ids: {clash}")
    return cands + added, report
