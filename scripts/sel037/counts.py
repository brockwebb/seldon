"""SEL-037 Part C: the counts table and the manual list, from the release's manifest and the catalog. Reads only.

    <squiddy venv>/bin/python scripts/sel037/counts.py     # writes graphs/seldon-biblio/evidence/sel037/part_c_counts.json

The MANIFEST (corpus/manifest.yaml, what the release admitted) says what is held; the CATALOG (the candidates file)
says what this task found about the rest. They differ for an entry admitted earlier whose catalog row moved in a field
that is not declared content: squiddy does not refresh an entry already in the graph from its candidates row (a
correction is a revision, SQ-023 R-213). So a standard whose text SEL-037 holds in its own documentation entry
(`text_in`) still reads `manual_acquisition: true` in the manifest, and a refusal SEL-037 re-observed carries
SEL-036's posture there. The manual list therefore takes the catalog's word and says so: an entry is manual when its
text is not held, its catalog row does not say otherwise (`manual_acquisition: false`, or `text_in`), and the catalog
or the manifest marks it manual.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
G = ROOT / "graphs/seldon-biblio"
OUT = G / "evidence/sel037/part_c_counts.json"


def main() -> int:
    from squiddy import manifest as mf          # squiddy's own reader of its manifest (run with squiddy's venv)
    entries = [e for e in mf.load_manifest(G / "corpus/manifest.yaml")[2] if not e.get("retired_at")]
    cands = {c["id"]: c for c in yaml.safe_load((G / "corpus/candidates/seldon_biblio_candidates.yaml")
                                                .read_text(encoding="utf-8"))["candidates"]}
    held = [e for e in entries if e.get("acquisition_status") == "acquired" and e.get("local_path")]
    refused_parse = [e["id"] for e in held if e.get("parse_refused")]
    manual = []
    for e in entries:
        c = cands.get(e["id"], {})
        if e in held or c.get("manual_acquisition") is False or c.get("text_in"):
            continue
        if c.get("manual_acquisition") or e.get("manual_acquisition"):
            manual.append({"id": e["id"], "kind": c.get("entry_kind") or e.get("kind"),
                           "url": (c.get("sel037_urls_tried") or [None])[-1] or c.get("source_url") or e.get("source_url"),
                           "posture": c.get("access_posture") or e.get("access_posture") or e.get("posture"),
                           "host": c.get("posture_host") or e.get("posture_host"),
                           "evidence": c.get("posture_evidence") or e.get("posture_evidence"),
                           "observed_at": c.get("posture_observed_at") or e.get("posture_observed_at"),
                           "label": c.get("sel037_label")})
    counts = {"cataloged": len(entries),
              "admitted_in_graph": sum(1 for e in entries if e.get("stage") == "in_graph"),
              "acquired_with_text": len(held),
              "text_held_not_indexed": len(refused_parse),
              "metadata_only": sum(1 for e in entries if e.get("disposition") == "metadata_only"),
              "manual": len(manual),
              "declined": sum(1 for e in entries if str(e.get("disposition", "")).startswith("excluded:declined"))}
    out = {"counts": counts, "text_held_not_indexed": refused_parse, "manual": manual,
           "metadata_only_by_reason": {}}
    for e in entries:
        if e.get("disposition") == "metadata_only":
            r = cands.get(e["id"], {}).get("metadata_only_reason") or e.get("metadata_only_reason") or "unstated"
            out["metadata_only_by_reason"][r] = out["metadata_only_by_reason"].get(r, 0) + 1
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(counts, indent=1))
    for m in manual:
        print(f"  manual {m['id']}: {m['posture']} at {m['host']} {m['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
