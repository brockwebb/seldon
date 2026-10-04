"""SEL-002: register the 14 labeled decisions that positional parsing bound and DB-1's list did not hold.

AD-033-R7 stops positional Rulings binding once a repository has a register. Measured before this ran
(evidence/sel002/positional_rulings_without_record.json): 42 positional Rulings had no record. 28 are not decisions
(Squiddy task-file H1 headings, the SEL-001 finding; Arnold docs/requirements FR headings) and are reported, not
registered. The other 14 are labeled decisions that registration bound until now and would silently stop binding:
Seldon's Addendum 029-A (which SEL-002 ADDENDUM 01 names as kept) and the phase-C retirement rulings R1 to R5, and
Arnold's eight labeled rulings in dispatched task addenda (among them plan-builder addendum-02 R2, "Per-set RPE is
gone from planning too", which bears on SEL-001's gold set B). Each is registered here, through the one write path,
with its full body as the source (a heading-form ruling's source is its whole section). Zero model calls.

    python scripts/sel002/register_labeled_rulings.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SELDON = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SELDON))
sys.path.insert(0, str(SELDON / "scripts" / "sel002"))

import seed_db1 as sd  # noqa: E402  (the seed's own span, receipt and consumer helpers)
from seldon.core import decisions as dr  # noqa: E402

ROWS = SELDON / "evidence" / "sel002" / "extra_labeled_rulings.json"


def main() -> int:
    rows = json.loads(ROWS.read_text())
    u = sd.universe()
    written = []
    for r in rows:
        repo, rel, rid = r["repo"], r["doc"], r["rid"]
        ls = sd.lines_of(repo, rel)
        txt = (sd.ROOTS[repo] / rel).read_text(encoding="utf-8")
        start = txt[:r["a"]].count("\n") + 1
        if r["pat"] in ("addendum_heading", "bare_ruling_heading"):
            head = ls[start - 1].lstrip("#").strip()
            s, e = sd.section_span(repo, rel, lambda h, w=head: h == w)
        else:
            s = start
            e = txt[:r["b"]].count("\n") + 1
            while e > s and not ls[e - 1].strip():
                e -= 1
        text = sd.text_of(repo, rel, s, e)
        if r["text"].strip().splitlines()[0] not in text:
            raise SystemExit(f"FATAL: {rel}:{s}-{e} does not hold the ruling's first line")
        if rid.startswith("Addendum "):
            local = "AD-029-A"
        else:
            local = f"{Path(rel).stem}-{rid}"
        sl_n, sl = sd.status_line(repo, rel)
        receipts = sd.receipts_in(repo, rel, s, e, (sl_n,) if sl_n else ())
        task_receipt = [f"{rel} (a dispatched task file; its rulings were executed under it)"] if rel.startswith("cc_tasks/") else []
        rec = {"id": f"{repo}:{local}", "kind": "decision", "statement": text,
               "source": {"path": rel, "lines": [s, e], "sha256": sd.sha_of(repo, rel), "text": text},
               "scope": [repo], "rationale": {"path": rel, "anchor": rid}}
        cons = sd.consumers(repo, local)
        if cons:
            rec["consumer"] = cons
        else:
            rec["review_only"] = sd.review_only(repo, rel, s, text)[0]
        paths = dr.create(u, "accept", rec, date=sd.doc_date(repo, rel, s),
                          decided_by="operator" if receipts else "desktop", operator_stated=bool(receipts),
                          receipts=(receipts + task_receipt) or None,
                          reason=("SEL-002: a labeled decision positional parsing bound, which AD-033-R7 would "
                                  "otherwise stop binding (evidence/sel002/positional_rulings_without_record.json)"))
        written.append({"id": rec["id"], "lines": [s, e], "operator_stated": bool(receipts), "status_line": sl})
        print(rec["id"], s, e, bool(receipts))
    (SELDON / "evidence" / "sel002" / "extra_labeled_rulings_registered.json").write_text(json.dumps(written, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
