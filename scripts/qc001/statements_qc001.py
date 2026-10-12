"""QC-001 Part B (AD-033-R8): stand-alone statements for AD-037-R1 to R10, written by one call and checked by another.

SQ-010's pass, reused whole (`scripts/sq010/statements_sq010.py`): HOOK-001's referent line names the note, and
SQ-010's instruction keeps the reasons a decision states. The call layer, fsynced checkpoints, unit keys, pilot and
spend governor are SEL-002's; its SIGKILL test (`scripts/sel002/statements_kill_test.py`) covers this loop, which is
the same code. Every job name carries `:qc001`: the templates equal SQ-010's, so SQ-010's job names would be reused
and the governor refuses a name declared with a different unit set.

Checkpoint plan (constitution 15): unit = one call (writer, then validator) per record; checkpoint =
docs/evidence/qc001/statements/{writer,validator}.jsonl, fsynced per finished call; resume = re-run the same command
(skip by unit key: record id, source sha256 [+ statement], template sha256, model, transport); pilot = 2 records;
ceiling = scripts/qc001/statements.yaml budget (40k weighted, stop at +20%). It runs in squiddy's environment:

    cd /Users/brock/GitHub/squiddy
    .venv/bin/python ../seldon/scripts/qc001/statements_qc001.py export
    .venv/bin/python ../seldon/scripts/qc001/statements_qc001.py pilot
    .venv/bin/python ../seldon/scripts/qc001/statements_qc001.py run
    .venv/bin/python ../seldon/scripts/qc001/statements_qc001.py report
    .venv/bin/python ../seldon/scripts/qc001/statements_qc001.py apply [--dry-run]
"""
from __future__ import annotations

import collections
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELDON = HERE.parents[1]
sys.path.insert(0, str(SELDON / "scripts" / "sq010"))

import statements_sq010 as sq010  # noqa: E402  (SQ-010's templates: referent line and keep-reasons)

hook001, pa001, st = sq010.hook001, sq010.pa001, sq010.st
st.CONFIG = HERE / "statements.yaml"

EVID = SELDON / "docs" / "evidence" / "qc001" / "statements"
DATE = "2026-10-12"
CC = "cc:00e22dd9"
NOTE_ID = "AD-037"
NOTE_PATH = "docs/design/AD-037_in_process_quality_control_for_dispatched_sessions.md"
IDS = [f"seldon:AD-037-R{i}" for i in range(1, 11)]

_job_spec = sq010._job_spec


def job_spec(name: str, *a, **k) -> dict:
    return _job_spec(name + ":qc001", *a, **k)


st.job_spec = job_spec


def export() -> int:
    """The ten records' verbatim sources from the register, plus the referent fields."""
    dr, u = pa001._universe()
    h1 = (SELDON / NOTE_PATH).read_text(encoding="utf-8").splitlines()[0]
    title = h1.lstrip("# ").split(": ", 1)[1]
    rows = []
    for qid in IDS:
        rec = u.get(qid)
        if rec is None:
            raise SystemExit(f"FATAL: {qid} has no record; run scripts/qc001/register_rulings.py first")
        text = (rec.get("source") or {}).get("text") or ""
        rows.append({"id": qid, "kind": rec.get("kind"), "status": rec.status, "source_text": text,
                     "source_sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text),
                     "note_id": NOTE_ID, "note_title": title, "note_path": NOTE_PATH})
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "units.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                      encoding="utf-8")
    print(f"{len(rows)} records -> {EVID / 'units.jsonl'}")
    return 0


def apply(dry_run: bool) -> int:
    """SQ-010's apply rule: a passed statement lands as an amend (statement, statement_check passed) through the one
    write path, whose AD-033-R3 check runs again; any other outcome is reported and nothing is hand-written."""
    dr, u = pa001._universe()
    rows = [json.loads(x) for x in (EVID / "outcome.jsonl").read_text().splitlines() if x.strip()]
    receipts = ["docs/evidence/qc001/statements/writer.jsonl", "docs/evidence/qc001/statements/validator.jsonl"]
    reason = ("AD-033-R8 statement pass (QC-001 Part B): written by one call, checked by a separate call: "
              "entailed, complete, standalone")
    tally, report = collections.Counter(), []
    for r in rows:
        rec = u.get(r["id"])
        if rec is None or rec.status not in dr.ACTIVE or rec.get("statement_check") == "passed":
            tally["skipped"] += 1
            report.append({"id": r["id"], "outcome": "skipped"})
            continue
        if not r.get("statement"):
            tally["not_written"] += 1
            report.append({"id": r["id"], "outcome": "not_written",
                           "why": "no writer call yet: the bulk run stopped at the declared budget's stop line"})
            continue
        if r["check"] != "passed":
            tally["failed"] += 1
            report.append({"id": r["id"], "outcome": "validator_failed", "statement": r["statement"],
                           "verdict": r.get("verdict")})
            continue
        if dry_run:
            tally["passed"] += 1
            report.append({"id": r["id"], "outcome": "would_land", "statement": r["statement"],
                           "deictic": dr.deictic_reference(r["statement"])})
            continue
        try:
            path = dr.amend(u, r["id"], date=DATE, decided_by=CC, receipts=receipts, reason=reason,
                            changes={"statement": r["statement"], "statement_check": "passed"})
            tally["passed"] += 1
            report.append({"id": r["id"], "outcome": "landed", "statement": r["statement"],
                           "record": [str(p) for p in path] if isinstance(path, (list, tuple)) else str(path)})
        except dr.RegisterError as exc:
            tally["refused"] += 1
            report.append({"id": r["id"], "outcome": "refused", "statement": r["statement"], "reason": str(exc)})
    out = {"tally": dict(tally), "records": report}
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
