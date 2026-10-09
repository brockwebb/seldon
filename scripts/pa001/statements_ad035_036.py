"""PA-001 Part F: AD-033-R8's stand-alone statements for AD-035-R1..R8 and AD-036-R1..R9.

Runs in SQUIDDY'S environment (the call layer, the model client, the spend governor), exactly as
SEL-002 Part E did, reusing scripts/sel002/statements.py whole: the writer and validator prompts,
the unit keys, the fsynced checkpoints, the pilot, the measured estimate and the governor. Two
things differ: the config is scripts/pa001/statements.yaml, and each client launches from the model
lock by registry role (SEL-002's `client_for` predates MODEL-001 and names an alias and a binary,
which AD-035 R4 now refuses). The SIGKILL test of this loop is SEL-002's
(scripts/sel002/statements_kill_test.py): the loop is the same code.

    cd /Users/brock/GitHub/squiddy
    .venv/bin/python ../seldon/scripts/pa001/statements_ad035_036.py export
    .venv/bin/python ../seldon/scripts/pa001/statements_ad035_036.py pilot
    .venv/bin/python ../seldon/scripts/pa001/statements_ad035_036.py run
    .venv/bin/python ../seldon/scripts/pa001/statements_ad035_036.py report
    .venv/bin/python ../seldon/scripts/pa001/statements_ad035_036.py apply [--dry-run]
"""
from __future__ import annotations

import collections
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELDON = HERE.parents[1]
sys.path.insert(0, str(SELDON))
sys.path.insert(0, str(SELDON / "scripts" / "sel002"))

import yaml  # noqa: E402

import statements as st  # noqa: E402  (SEL-002's pass, reused whole)
from squiddy import model_client as mc  # noqa: E402

EVID = SELDON / "docs" / "evidence" / "pa001" / "statements"
REGISTERED = SELDON / "docs" / "evidence" / "pa001" / "registered_rulings.json"
DATE = "2026-10-09"
CC = "cc:459f463e"
st.CONFIG = HERE / "statements.yaml"


def client_for(role: dict, tr: dict, mock_responder=None, system: str | None = None):
    """SEL-002's client factory, launching from the lock by role (AD-035 R3, AD-036-R8)."""
    if mock_responder is not None:
        return mc.MockClient(mock_responder, alias="mock")
    return mc.ClaudeCLIClient(role=role["role"], timeout=int(role["timeout"]),
                              max_turns=int(role["max_turns"]), system_prompt=system,
                              minimal_scaffold=bool(tr["setting_sources_disabled"]),
                              no_nonessential_traffic=bool(tr["nonessential_traffic_disabled"]))


st.client_for = client_for


def _universe():
    from seldon.core import decisions as dr
    return dr, dr.universe(SELDON, yaml.safe_load((SELDON / "seldon.yaml").read_text()))


def export() -> int:
    dr, u = _universe()
    ids = [r["id"] for r in json.loads(REGISTERED.read_text())]
    rows = []
    for qid in ids:
        rec = u.get(qid)
        text = (rec.get("source") or {}).get("text") or ""
        rows.append({"id": rec.id, "kind": rec.get("kind"), "status": rec.status, "source_text": text,
                     "source_sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text)})
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "units.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"{len(rows)} records -> {EVID / 'units.jsonl'}")
    return 0


def apply(dry_run: bool) -> int:
    """SEL-002's apply rule: a passed statement lands as an amend (statement, statement_check
    passed); any other outcome keeps the verbatim statement, flagged failed (AD-033-R8)."""
    dr, u = _universe()
    rows = [json.loads(x) for x in (EVID / "outcome.jsonl").read_text().splitlines() if x.strip()]
    receipts = ["docs/evidence/pa001/statements/writer.jsonl",
                "docs/evidence/pa001/statements/validator.jsonl"]
    tally, refused = collections.Counter(), []
    for r in rows:
        rec = u.get(r["id"])
        if rec is None or rec.status not in dr.ACTIVE or rec.get("statement_check"):
            tally["skipped"] += 1
            continue
        v = r.get("verdict") or {}
        if r["check"] == "passed":
            if dry_run:
                tally["passed"] += 1
                continue
            try:
                dr.amend(u, r["id"], date=DATE, decided_by=CC, receipts=receipts,
                         reason=("AD-033-R8 statement pass (PA-001 Part F): written by one call from "
                                 "the verbatim source, checked by a separate call that saw only the "
                                 "source and the statement: entailed, complete, standalone"),
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
            why = "the validator found it " + ", ".join(
                {"entailed": "not entailed", "complete": "incomplete",
                 "standalone": "not standalone"}[k] for k in ("entailed", "complete", "standalone")
                if not v.get(k)) + (f"; dropped: {v.get('dropped')}" if v.get("dropped") else "")
        tally["failed"] += 1
        if not dry_run:
            dr.amend(u, r["id"], date=DATE, decided_by=CC, receipts=receipts,
                     reason=f"AD-033-R8 statement pass (PA-001 Part F): check failed, the verbatim "
                            f"statement stays; {why}", changes={"statement_check": "failed"})
    out = {"tally": dict(tally), "refused": refused}
    (EVID / ("apply_dryrun.json" if dry_run else "apply.json")).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == "export":
        return export()
    if argv[0] == "apply":
        return apply("--dry-run" in argv)
    return st.main([*argv, "--evid", str(EVID)])


if __name__ == "__main__":
    raise SystemExit(main())
