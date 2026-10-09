"""PA-001 Part F: register AD-035-R1 to R8 and AD-036-R1 to R9 through the one write path.

AD-035's rulings were committed as `## AD-035-Rn.` headings, which no configured label pattern
read, so the register held no record for any of them and `seldon verify` could not notice
(AD-036 section 6.1). AD-036 itself was committed without records for its nine labeled rulings
(found by this task's own `seldon decision check`). Each ruling is registered here with its full
body as the verbatim source: for AD-035 the heading's whole section; for AD-036 the bulleted
ruling from its label line to the line before the next ruling or heading. The stand-alone statement
is written afterwards by AD-033-R8's two-call pass (scripts/pa001/statements_ad035_036.py), which
lands as amend records. Zero model calls here.

    python scripts/pa001/register_rulings.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SELDON = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SELDON))
sys.path.insert(0, str(SELDON / "scripts" / "sel002"))

import seed_db1 as sd  # noqa: E402  (SEL-002's span, receipt, consumer and date helpers)
from seldon.core import decisions as dr  # noqa: E402

NOTES = {
    "AD-035": "docs/design/AD-035_config_driven_model_selection.md",
    "AD-036": "docs/design/AD-036_prior_art_receipts_gate.md",
}
OUT = SELDON / "docs" / "evidence" / "pa001" / "registered_rulings.json"
REASON = ("PA-001 Part F (AD-036 section 6.1): a labeled ruling the register could not see "
          "(AD-035, heading form) or that was committed without a record (AD-036)")


def spans(note: str, rel: str) -> list[tuple[str, int, int]]:
    ls = sd.lines_of("seldon", rel)
    out = []
    if note == "AD-035":
        for i, ln in enumerate(ls, 1):
            m = re.match(r"^##\s+(AD-035-R\d+)\.", ln)
            if m:
                head = ln.lstrip("#").strip()
                s, e = sd.section_span("seldon", rel, lambda h, w=head: h == w)
                out.append((m.group(1), s, e))
        return out
    starts = [(i, m.group(1)) for i, ln in enumerate(ls, 1)
              if (m := re.match(r"^\s*-\s+\*\*(AD-036-R\d+)\.", ln))]
    for k, (i, label) in enumerate(starts):
        e = len(ls)
        for j in range(i + 1, len(ls) + 1):
            if (k + 1 < len(starts) and j == starts[k + 1][0]) or ls[j - 1].startswith("#"):
                e = j - 1
                break
        while e > i and not ls[e - 1].strip():
            e -= 1
        out.append((label, i, e))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    u = sd.universe()
    have = u.records("seldon")
    written = []
    for note, rel in NOTES.items():
        sl_n, sl = sd.status_line("seldon", rel)
        for label, s, e in spans(note, rel):
            qid = f"seldon:{label}"
            if qid in have:
                print("exists", qid)
                continue
            text = sd.text_of("seldon", rel, s, e)
            receipts = sd.receipts_in("seldon", rel, s, e, (sl_n,) if sl_n else ())
            rec = {"id": qid, "kind": "decision", "statement": text,
                   "source": {"path": rel, "lines": [s, e], "sha256": sd.sha_of("seldon", rel),
                              "text": text},
                   "scope": ["seldon"], "rationale": {"path": rel, "anchor": label}}
            cons = sd.consumers("seldon", label)
            if cons:
                rec["consumer"] = cons
            else:
                rec["review_only"] = sd.review_only("seldon", rel, s, text)[0]
            row = {"id": qid, "lines": [s, e], "operator_stated": bool(receipts), "status_line": sl,
                   "consumer": cons}
            written.append(row)
            print(qid, s, e, "operator" if receipts else "desktop", len(cons), "consumer(s)")
            if not a.dry_run:
                dr.create(u, "accept", rec, date=sd.doc_date("seldon", rel, s),
                          decided_by="operator" if receipts else "desktop",
                          operator_stated=bool(receipts), receipts=receipts or None, reason=REASON)
    if not a.dry_run:
        OUT.write_text(json.dumps(written, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
