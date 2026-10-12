"""QC-001 Part B: register AD-037-R1 to R10 through the one write path.

Each ruling is registered accepted (AD-033-R4: a Desktop decision under L4 is accepted at registration), decided by
`desktop`, with its verbatim source from its bold label line to the line before the next ruling or heading: PA-001's
span rule for bulleted rulings (`scripts/pa001/register_rulings.py`). The stand-alone statement is written afterwards
by AD-033-R8's two-call pass (`scripts/qc001/statements_qc001.py`), which lands as amend records. Zero model calls.

    python scripts/qc001/register_rulings.py [--dry-run]
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

import seed_db1 as sd  # noqa: E402  (SEL-002's span, consumer and date helpers)
from seldon.core import decisions as dr  # noqa: E402

NOTE = "AD-037"
REL = "docs/design/AD-037_in_process_quality_control_for_dispatched_sessions.md"
OUT = SELDON / "docs" / "evidence" / "qc001" / "registered_rulings.json"
REASON = ("QC-001 Part B: AD-037's labeled rulings recorded with the note's first commit (AD-033-R2); decided by "
          "the squiddy/seldon Desktop session (AD-037 Status line), accepted at registration under L4 (AD-033-R4)")


def spans() -> list[tuple[str, int, int]]:
    """PA-001's bulleted-ruling spans (`scripts/pa001/register_rulings.py`), for this note's label."""
    ls = sd.lines_of("seldon", REL)
    starts = [(i, m.group(1)) for i, ln in enumerate(ls, 1) if (m := re.match(rf"^\s*-\s+\*\*({NOTE}-R\d+)\.", ln))]
    out = []
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
    found = spans()
    if [lb for lb, _s, _e in found] != [f"{NOTE}-R{i}" for i in range(1, 11)]:
        raise SystemExit(f"FATAL: expected {NOTE}-R1 to R10 in order, found {[lb for lb, _s, _e in found]}")
    written = []
    for label, s, e in found:
        qid = f"seldon:{label}"
        if qid in have:
            print("exists", qid)
            continue
        text = sd.text_of("seldon", REL, s, e)
        rec = {"id": qid, "kind": "decision", "statement": text,
               "source": {"path": REL, "lines": [s, e], "sha256": sd.sha_of("seldon", REL), "text": text},
               "scope": ["seldon"], "rationale": {"path": REL, "anchor": label}}
        cons = sd.consumers("seldon", label)
        if cons:
            rec["consumer"] = cons
        else:
            rec["review_only"] = sd.review_only("seldon", REL, s, text)[0]
        written.append({"id": qid, "lines": [s, e], "consumer": cons})
        print(qid, s, e, len(cons), "consumer(s)")
        if not a.dry_run:
            dr.create(u, "accept", rec, date="2026-10-11", decided_by="desktop", reason=REASON)
    if not a.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(written, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
