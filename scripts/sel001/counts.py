"""SEL-001 step 2: what each governed graph holds, from its ledger and from the Seldon graph it was synced into.

    python -m dotenv -f .env run -- python scripts/sel001/counts.py

Per repository: documents (by kind), sections, rulings by `matched_pattern`, and the documents that parsed to zero
rulings (by kind, with the list). The ledger is read by `seldon.core.governed.read_ledger`; the Seldon side by
`seldon.core.governed.graph_counts`, so a sync that dropped or duplicated something shows as a disagreement here.
Writes `evidence/sel001/governed_counts.json`.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

from seldon.config import get_neo4j_driver, load_project_config  # noqa: E402
from seldon.core import governed  # noqa: E402


def main() -> int:
    cfg = C.load_config()
    out = {}
    for repo, spec in cfg["repos"].items():
        root = Path(spec["root"])
        view = governed.read_ledger(root / cfg["graph_dir"] / "ledger" / "events.jsonl")
        docs = {nid: p for (cls, nid), p in view.nodes.items() if cls == "Document"}
        rulings = [p for (cls, _n), p in view.nodes.items() if cls == "Ruling"]
        sections = [p for (cls, _n), p in view.nodes.items() if cls == "Section"]
        per_doc = Counter(p.get("doc_id") for p in rulings)
        zero = sorted(docs[d].get("path") for d in docs if per_doc.get(d, 0) == 0)
        pcfg = load_project_config(root)
        driver = get_neo4j_driver(pcfg)
        try:
            seldon_side = governed.graph_counts(driver, pcfg["neo4j"]["database"])
        finally:
            driver.close()
        out[repo] = {
            "ledger": {
                "documents": len(docs),
                "documents_by_kind": dict(sorted(Counter(p.get("doc_kind") for p in docs.values()).items())),
                "sections": len(sections),
                "rulings": len(rulings),
                "rulings_by_matched_pattern": dict(Counter(p.get("matched_pattern") for p in rulings).most_common()),
                "documents_with_zero_rulings": len(zero),
                "documents_with_zero_rulings_by_kind": dict(sorted(
                    Counter(docs[d].get("doc_kind") for d in docs if per_doc.get(d, 0) == 0).items())),
                "documents_with_zero_rulings_list": zero,
            },
            "seldon_graph": {"database": pcfg["neo4j"]["database"], **seldon_side},
        }
        led, sel = out[repo]["ledger"], seldon_side["nodes"]
        agree = (sel.get("Document") == led["documents"] and sel.get("Section") == led["sections"]
                 and sel.get("Ruling") == led["rulings"])
        out[repo]["ledger_and_seldon_graph_agree"] = agree
        print(f"{repo}: {led['documents']} documents {led['documents_by_kind']}, {led['sections']} sections, "
              f"{led['rulings']} rulings {led['rulings_by_matched_pattern']}, "
              f"{led['documents_with_zero_rulings']} with zero rulings {led['documents_with_zero_rulings_by_kind']}; "
              f"Seldon graph {sel} ({'agrees' if agree else 'DISAGREES'})")
    C.evidence(cfg, "governed_counts.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n",
                                                       encoding="utf-8")
    return 0 if all(v["ledger_and_seldon_graph_agree"] for v in out.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
