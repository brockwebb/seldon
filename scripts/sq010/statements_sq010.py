"""SQ-010 Part 8 (carried from HOOK-001): AD-033-R8's statements for seldon:AD-036-R4 and seldon:AD-035-R8.

HOOK-001 left two records flagged (cc_tasks/2026-10-09_HOOK-001_..._RESULT.md):

- AD-036-R4: its statement PASSED the separate validator and was refused only by the write path's AD-033-R3
  deictic check, on "the note" whose antecedent ("a design note") is in the same statement. SQ-010 narrowed that
  check (`decisions.deictic_reference`: a definite reference counts only without an antecedent in the statement).
  The writer and validator calls are unchanged, so their unit keys are unchanged: re-running HOOK-001's pass would
  resume both by skip and call nothing. `apply` therefore lands HOOK-001's validator-passed statement through the one
  write path, whose (narrowed) AD-033-R3 check runs again. Zero model calls.
- AD-035-R8: the validator failed it, complete=false, because the writer dropped the two reasons the decision states
  (an allowlist would bind interactive sessions; denying superseded models disables fallback targets). The writer's
  rule 3 says to leave out rationale; here the reasons are part of the decision ("evaluated, not deployed" is a
  refusal whose reasons are what it decides). This pass adds one instruction to HOOK-001's referent template: keep
  the reasons the decision itself states. The validator's template is HOOK-001's, unchanged.

Everything else is HOOK-001's pass (and so PA-001's and SEL-002's): the call layer, the fsynced checkpoints, the
unit keys, the pilot and the spend governor. The changed writer template changes its unit key, so nothing is reused
for AD-035-R8. The SIGKILL test of this loop is SEL-002's (`scripts/sel002/statements_kill_test.py`): the loop is
the same code. Checkpoint plan (constitution 15): unit = one call (writer, then validator) per record; checkpoint =
docs/evidence/sq010/statements/{writer,validator}.jsonl, fsynced per finished call; resume = re-run the same command
(skip by unit key: record id, source sha256 [+ statement], template sha256, model, transport); pilot = the whole
pass (one record); ceiling = scripts/sq010/statements.yaml budget (10k weighted, stop at +20%). It runs in squiddy's
environment:

    cd /Users/brock/GitHub/squiddy
    .venv/bin/python ../seldon-sq010-hook/scripts/sq010/statements_sq010.py export
    .venv/bin/python ../seldon-sq010-hook/scripts/sq010/statements_sq010.py pilot
    .venv/bin/python ../seldon-sq010-hook/scripts/sq010/statements_sq010.py report
    .venv/bin/python ../seldon-sq010-hook/scripts/sq010/statements_sq010.py apply [--dry-run]
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELDON = HERE.parents[1]
sys.path.insert(0, str(SELDON / "scripts" / "hook001"))

import statements_referent as hook001  # noqa: E402  (HOOK-001's referent pass, reused whole)

pa001, st = hook001.pa001, hook001.st
st.CONFIG = HERE / "statements.yaml"

HOOK001_EVID = SELDON / "docs" / "evidence" / "hook001" / "statements"
EVID = SELDON / "docs" / "evidence" / "sq010" / "statements"
DATE = "2026-10-11"
CC = "cc:00682405"

#: The record re-written by a model call, and the record re-applied from HOOK-001's validator-passed outcome.
REWRITE = "seldon:AD-035-R8"
REAPPLY = "seldon:AD-036-R4"

KEEP_REASONS = ("Keep stated reasons: where the source gives the reasons for its decision (why an option is "
                "refused, what the alternative would break, when it is revisited), the statement keeps each "
                "reason, briefly, as part of the decision. Rule 3's \"leave out rationale\" does not cover a "
                "reason the decision itself states.")

st.WRITER_USER = ("Kind of record: <<KIND>>\n" + hook001.REFERENT_LINE + "\n" + KEEP_REASONS + """
Verbatim source:
<<<
<<SOURCE>>
>>>""")


#: The spend governor names a job from the control and template hashes. The validator's are HOOK-001's, unchanged,
#: so its pilot job id was HOOK-001's and the governor refused it as "already declared with a different spec" (a
#: different unit set). This pass's validator jobs carry the task's name; the writer's template is new, so its job
#: id is already its own and is left as it ran.
_job_spec = st.job_spec


def job_spec(name: str, *a, **k) -> dict:
    return _job_spec(name + ":sq010" if name.startswith("sel002_validator") else name, *a, **k)


st.job_spec = job_spec


def export() -> int:
    """AD-035-R8's HOOK-001 unit, verbatim (source and referent fields unchanged)."""
    rows = [json.loads(x) for x in (HOOK001_EVID / "units.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()]
    rows = [r for r in rows if r["id"] == REWRITE]
    if len(rows) != 1:
        raise SystemExit(f"FATAL: {REWRITE} is not in {HOOK001_EVID / 'units.jsonl'}")
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "units.jsonl").write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"1 record -> {EVID / 'units.jsonl'}")
    return 0


def _outcomes() -> list[dict]:
    """AD-035-R8 from this pass's report; AD-036-R4 from HOOK-001's (its calls are unchanged)."""
    mine = [json.loads(x) for x in (EVID / "outcome.jsonl").read_text().splitlines() if x.strip()]
    theirs = [json.loads(x) for x in (HOOK001_EVID / "outcome.jsonl").read_text().splitlines() if x.strip()]
    rows = [r for r in mine if r["id"] == REWRITE] + [r for r in theirs if r["id"] == REAPPLY]
    if {r["id"] for r in rows} != {REWRITE, REAPPLY}:
        raise SystemExit(f"FATAL: outcomes found for {sorted(r['id'] for r in rows)}; run `report` first")
    return rows


def apply(dry_run: bool) -> int:
    """HOOK-001's apply rule: a passed statement lands as an amend (statement, statement_check passed) through the
    one write path, whose AD-033-R3 check runs again; any other outcome is reported and nothing is hand-written."""
    dr, u = pa001._universe()
    receipts = {REWRITE: ["docs/evidence/sq010/statements/writer.jsonl",
                          "docs/evidence/sq010/statements/validator.jsonl"],
                REAPPLY: ["docs/evidence/hook001/statements/writer.jsonl",
                          "docs/evidence/hook001/statements/validator.jsonl"]}
    reasons = {REWRITE: ("AD-033-R8 statement pass re-run with the writer told to keep the reasons the decision "
                         "states (SQ-010 Part 8, carried from HOOK-001): written by one call, checked by a "
                         "separate call: entailed, complete, standalone"),
               REAPPLY: ("AD-033-R8: HOOK-001's validator-passed statement (entailed, complete, standalone), "
                         "landed after SQ-010 narrowed the AD-033-R3 check to definite references with no "
                         "antecedent in the statement; its calls are unchanged and were not re-made")}
    tally, report = collections.Counter(), []
    for r in _outcomes():
        rec = u.get(r["id"])
        if rec is None or rec.status not in dr.ACTIVE or rec.get("statement_check") == "passed":
            tally["skipped"] += 1
            report.append({"id": r["id"], "outcome": "skipped"})
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
            path = dr.amend(u, r["id"], date=DATE, decided_by=CC, receipts=receipts[r["id"]],
                            reason=reasons[r["id"]],
                            changes={"statement": r["statement"], "statement_check": "passed"})
            tally["passed"] += 1
            report.append({"id": r["id"], "outcome": "landed", "statement": r["statement"],
                           "record": [str(p) for p in path]})
        except dr.RegisterError as exc:
            tally["refused"] += 1
            report.append({"id": r["id"], "outcome": "refused", "statement": r["statement"], "reason": str(exc)})
    out = {"tally": dict(tally), "records": report}
    EVID.mkdir(parents=True, exist_ok=True)
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
