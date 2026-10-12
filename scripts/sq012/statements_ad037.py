"""SQ-012 Part G (AD-033-R8): stand-alone statements for the eight AD-037 records QC-001 Part B left verbatim
(AD-037-R2 to R5, R7 to R10). QC-001 measured its pilot (R1, R6) and its governor refused the bulk: the projection,
50.3k weighted, passed the 48k stop line of QC-001's declared 40k. SQ-012 declares about 50k for these eight.

QC-001's pass, reused whole (`scripts/qc001/statements_qc001.py`, itself SQ-010's): same templates, roles, transport,
call layer and governor. What changes: the eight ids, this evidence directory, the job suffix `:sq012` (the governor
refuses a job name declared with a different unit set), the budget (`scripts/sq012/statements.yaml`) and the decider.

Checkpoint plan (constitution 15): unit = one call (writer, then validator) per record; checkpoint =
docs/evidence/sq012/statements_ad037/{writer,validator}.jsonl, fsynced per finished call; resume = re-run the same
command (skip by unit key); pilot = the whole pass (8 records); ceiling = 50k weighted, stop at +20%. The SIGKILL test
is SEL-002's (`scripts/sel002/statements_kill_test.py`): same code. It runs in squiddy's environment:

    cd /Users/brock/GitHub/squiddy
    .venv/bin/python ../seldon/scripts/sq012/statements_ad037.py export
    .venv/bin/python ../seldon/scripts/sq012/statements_ad037.py pilot
    .venv/bin/python ../seldon/scripts/sq012/statements_ad037.py report
    .venv/bin/python ../seldon/scripts/sq012/statements_ad037.py apply [--dry-run]
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELDON = HERE.parents[1]
sys.path.insert(0, str(SELDON / "scripts" / "qc001"))

import statements_qc001 as qc  # noqa: E402  (QC-001's pass: SQ-010's templates, the referent, keep-reasons)

st = qc.st
st.CONFIG = HERE / "statements.yaml"
qc.EVID = SELDON / "docs" / "evidence" / "sq012" / "statements_ad037"
qc.DATE = "2026-10-12"
qc.CC = "cc:0ba6d722"
qc.IDS = [f"seldon:AD-037-R{i}" for i in (2, 3, 4, 5, 7, 8, 9, 10)]
RECEIPTS = ["docs/evidence/sq012/statements_ad037/writer.jsonl", "docs/evidence/sq012/statements_ad037/validator.jsonl"]

_job_spec = qc.sq010._job_spec


def job_spec(name: str, *a, **k) -> dict:
    return _job_spec(name + ":sq012", *a, **k)


st.job_spec = job_spec


def apply(dry_run: bool) -> int:
    """QC-001's apply, with this pass's receipts and reason (its own names those of QC-001's evidence directory)."""
    import json
    dr, u = qc.pa001._universe()
    amend = dr.amend

    def amend_here(u_, qid, *, date, decided_by, receipts, reason, changes):
        return amend(u_, qid, date=date, decided_by=decided_by, receipts=RECEIPTS,
                     reason="AD-033-R8 statement pass (SQ-012 Part G, QC-001 Part B's bulk): written by one call, "
                            "checked by a separate call: entailed, complete, standalone", changes=changes)

    dr.amend = amend_here
    try:
        return qc.apply(dry_run)
    finally:
        dr.amend = amend


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == "export":
        return qc.export()
    if argv[0] == "apply":
        return apply("--dry-run" in argv)
    return st.main([*argv, "--evid", str(qc.EVID)])


if __name__ == "__main__":
    raise SystemExit(main())
