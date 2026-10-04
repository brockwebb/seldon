"""SEL-002 Part E, last step (Seldon's environment): land the statements as `amend` records (AD-033-R8).

    python scripts/sel002/statements_apply.py [--dry-run]

Reads evidence/sel002/statements/outcome.jsonl (`statements.py report`, run in Squiddy's environment over the
checkpoints). For a record whose statement the validator passed (entailed, complete, standalone): an amend
event changing `statement` and setting `statement_check: passed`. For every other record: an amend event
setting `statement_check: failed`, and the statement stays the verbatim source (R8: "a record that fails keeps
the verbatim text as its statement, flagged"). A passed statement the write path refuses (it points at other
text by position, AD-033-R3) is recorded failed with that reason. Records are never edited. Zero model calls.
Re-running is safe: a record that already carries a statement_check is skipped.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

SELDON = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SELDON))

import yaml  # noqa: E402

from seldon.core import decisions as dr  # noqa: E402

EVID = SELDON / "evidence" / "sel002" / "statements"
DATE = "2026-10-04"
CC = "cc:0636b04a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    u = dr.universe(SELDON, yaml.safe_load((SELDON / "seldon.yaml").read_text()))
    rows = [json.loads(l) for l in (EVID / "outcome.jsonl").read_text().splitlines() if l.strip()]
    tally = collections.Counter()
    refused = []
    for r in rows:
        rec = u.get(r["id"])
        if rec is None or rec.status not in dr.ACTIVE:
            tally["skipped_inactive"] += 1
            continue
        if rec.get("statement_check"):
            tally["already_applied"] += 1
            continue
        v = r.get("verdict") or {}
        receipts = ["evidence/sel002/statements/writer.jsonl", "evidence/sel002/statements/validator.jsonl"]
        if r["check"] == "passed":
            reason = ("AD-033-R8 statement pass (SEL-002 Part E): written by one call from the verbatim source, "
                      "checked by a separate call that saw only the source and the statement: entailed, complete, "
                      "standalone")
            if a.dry_run:
                tally["passed"] += 1
                continue
            try:
                dr.amend(u, r["id"], date=DATE, decided_by=CC, reason=reason, receipts=receipts,
                         changes={"statement": r["statement"], "statement_check": "passed"})
                tally["passed"] += 1
                continue
            except dr.RegisterError as exc:
                refused.append({"id": r["id"], "refusal": str(exc)})
                why = f"the write path refused the passed statement: {exc}"
        elif not r.get("statement"):
            why = "the writer produced no statement (its calls failed)"
        elif not v:
            why = "the validator produced no verdict (its calls failed)"
        else:
            why = ("the validator found it " + ", ".join(k for k in ("entailed", "complete", "standalone") if not v.get(k))
                   .replace("entailed", "not entailed").replace("complete", "incomplete").replace("standalone", "not standalone")
                   + (f"; dropped: {v.get('dropped')}" if v.get("dropped") else "")
                   + (f"; added: {v.get('added')}" if v.get("added") else ""))
        tally["failed"] += 1
        if not a.dry_run:
            dr.amend(u, r["id"], date=DATE, decided_by=CC, receipts=receipts,
                     reason=f"AD-033-R8 statement pass (SEL-002 Part E): check failed, the verbatim statement stays; {why}",
                     changes={"statement_check": "failed"})
    out = {"tally": dict(tally), "refused": refused}
    (EVID / ("apply_dryrun.json" if a.dry_run else "apply.json")).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def reapply_refused() -> dict:
    """Re-land statements the write path refused under its first deictic pattern and passes under the corrected one.

    The record already carries `statement_check: failed` from the first apply; records are never edited, so the
    correction is a new amend event (statement + passed) whose reason names the earlier refusal. A statement the
    corrected pattern still refuses stays failed.
    """
    u = dr.universe(SELDON, yaml.safe_load((SELDON / "seldon.yaml").read_text()))
    first = json.loads((EVID / "apply.json").read_text())
    rows = {r["id"]: r for r in (json.loads(l) for l in (EVID / "outcome.jsonl").read_text().splitlines() if l.strip())}
    landed, still = [], []
    for ref in first["refused"]:
        rec = u.get(ref["id"])
        st = rows[ref["id"]]["statement"]
        if rec is None or rec.get("statement_check") != "failed":
            continue
        try:
            dr.amend(u, ref["id"], date=DATE, decided_by=CC,
                     receipts=["evidence/sel002/statements/writer.jsonl", "evidence/sel002/statements/validator.jsonl",
                               "evidence/sel002/statements/apply.json"],
                     reason=("AD-033-R8 statement pass (SEL-002 Part E): re-landed. The validator passed this statement; "
                             "the write path's first deictic pattern refused it on a comparative ('at or above', 'below "
                             f"the floor'), which is not a pointer to other text. First refusal: {ref['refusal'][:160]}"),
                     changes={"statement": st, "statement_check": "passed"})
            landed.append(ref["id"])
        except dr.RegisterError as exc:
            still.append({"id": ref["id"], "refusal": str(exc)})
    out = {"relanded": landed, "still_refused": still}
    (EVID / "reapply.json").write_text(json.dumps(out, indent=1))
    return out
