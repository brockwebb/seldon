"""HOOK-001 Part B: AD-033-R8's statements for the three records the deictic check refused.

PA-001 Part F wrote and validated statements for 17 records; three passed the validator and were
then refused by the write path's AD-033-R3 check, because each said "this decision" or "the note"
(`docs/evidence/pa001/statements/apply.json`). The writer had been given the verbatim source and
nothing else, so it had no name for what the source points at. This re-run supplies the referent:
the note's id, title and path, and the record's own id, in the writer's context. The verbatim
source is unchanged.

The validator gets the same referent line. It still sees only the source and the statement (and
now the referent), never the writer's prompt. Without the referent, naming the note would read as
something the statement added that the source does not say, so a correct statement would fail as
not entailed.

Everything else is PA-001's pass, which is SEL-002's, reused whole: the call layer, the fsynced
checkpoints, the unit keys, the pilot and the spend governor. The changed templates change the
unit keys, so nothing from PA-001's checkpoints is reused. The SIGKILL test of this loop is
SEL-002's (`scripts/sel002/statements_kill_test.py`), because the loop is the same code. It runs
in squiddy's environment:

    cd /Users/brock/GitHub/squiddy
    .venv/bin/python ../seldon/scripts/hook001/statements_referent.py export
    .venv/bin/python ../seldon/scripts/hook001/statements_referent.py pilot     # all three
    .venv/bin/python ../seldon/scripts/hook001/statements_referent.py report
    .venv/bin/python ../seldon/scripts/hook001/statements_referent.py apply [--dry-run]
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELDON = HERE.parents[1]
sys.path.insert(0, str(SELDON / "scripts" / "pa001"))

import statements_ad035_036 as pa001  # noqa: E402  (PA-001's lock-launched client, reused)

st = pa001.st
st.CONFIG = HERE / "statements.yaml"

PA001_UNITS = SELDON / "docs" / "evidence" / "pa001" / "statements" / "units.jsonl"
EVID = SELDON / "docs" / "evidence" / "hook001" / "statements"
DATE = "2026-10-09"
CC = "cc:2ebfb15e"

#: The three records and the design note each is a ruling of. Titles are each note's H1, verbatim.
REFERENTS = {
    "seldon:AD-035-R8": ("AD-035", "docs/design/AD-035_config_driven_model_selection.md"),
    "seldon:AD-036-R4": ("AD-036", "docs/design/AD-036_prior_art_receipts_gate.md"),
    "seldon:AD-036-R7": ("AD-036", "docs/design/AD-036_prior_art_receipts_gate.md"),
}

REFERENT_LINE = ("Record: <<ID>>, a ruling of design note <<NOTE>> \"<<TITLE>>\" (<<PATH>>). Where "
                 "the source points at \"this decision\", \"this AD\", \"this note\", \"the note\" or "
                 "\"this file\", it means that design note or that ruling.")

st.WRITER_USER = "Kind of record: <<KIND>>\n" + REFERENT_LINE + """
Verbatim source:
<<<
<<SOURCE>>
>>>"""

st.VALIDATOR_USER = REFERENT_LINE + """
Verbatim source:
<<<
<<SOURCE>>
>>>

Statement:
<<<
<<STATEMENT>>
>>>"""


def _referent(text: str, u: dict) -> str:
    return (text.replace("<<ID>>", u["id"]).replace("<<NOTE>>", u["note_id"])
            .replace("<<TITLE>>", u["note_title"]).replace("<<PATH>>", u["note_path"]))


def writer_prompt(u: dict) -> str:
    return _referent(st.WRITER_USER, u).replace("<<KIND>>", str(u.get("kind"))).replace(
        "<<SOURCE>>", u["source_text"])


def validator_prompt(u: dict, statement: str) -> str:
    return _referent(st.VALIDATOR_USER, u).replace("<<SOURCE>>", u["source_text"]).replace(
        "<<STATEMENT>>", statement)


st.writer_prompt = writer_prompt
st.validator_prompt = validator_prompt


def export() -> int:
    """The three PA-001 units, verbatim, plus the referent fields."""
    rows = []
    for line in PA001_UNITS.read_text(encoding="utf-8").splitlines():
        u = json.loads(line)
        if u["id"] not in REFERENTS:
            continue
        note_id, path = REFERENTS[u["id"]]
        h1 = (SELDON / path).read_text(encoding="utf-8").splitlines()[0]
        title = h1.lstrip("# ").split(": ", 1)[1]
        rows.append({**u, "note_id": note_id, "note_title": title, "note_path": path})
    if len(rows) != len(REFERENTS):
        raise SystemExit(f"FATAL: found {len(rows)} of {len(REFERENTS)} units in {PA001_UNITS}")
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "units.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                              for r in rows), encoding="utf-8")
    print(f"{len(rows)} records -> {EVID / 'units.jsonl'}")
    return 0


def apply(dry_run: bool) -> int:
    """PA-001's apply rule for records already flagged: a passed statement lands as an amend
    (statement, statement_check passed) through the one write path, whose AD-033-R3 check runs
    again; any other outcome is reported, the record stays flagged, and nothing is hand-written."""
    dr, u = pa001._universe()
    rows = [json.loads(x) for x in (EVID / "outcome.jsonl").read_text().splitlines() if x.strip()]
    receipts = ["docs/evidence/hook001/statements/writer.jsonl",
                "docs/evidence/hook001/statements/validator.jsonl"]
    tally, report = collections.Counter(), []
    for r in rows:
        rec = u.get(r["id"])
        if rec is None or rec.status not in dr.ACTIVE or rec.get("statement_check") == "passed":
            tally["skipped"] += 1
            report.append({"id": r["id"], "outcome": "skipped"})
            continue
        v = r.get("verdict") or {}
        if r["check"] != "passed":
            tally["failed"] += 1
            report.append({"id": r["id"], "outcome": "validator_failed", "statement": r["statement"],
                           "verdict": v})
            continue
        if dry_run:
            tally["passed"] += 1
            report.append({"id": r["id"], "outcome": "would_land", "statement": r["statement"]})
            continue
        try:
            path = dr.amend(u, r["id"], date=DATE, decided_by=CC, receipts=receipts,
                            reason=("AD-033-R8 statement pass re-run with the referent supplied "
                                    "(HOOK-001 Part B): the note's id and title in the writer's "
                                    "context, the source verbatim; written by one call, checked "
                                    "by a separate call: entailed, complete, standalone"),
                            changes={"statement": r["statement"], "statement_check": "passed"})
            tally["passed"] += 1
            report.append({"id": r["id"], "outcome": "landed", "statement": r["statement"],
                           "record": str(path)})
        except dr.RegisterError as exc:
            tally["refused"] += 1
            report.append({"id": r["id"], "outcome": "refused", "statement": r["statement"],
                           "reason": str(exc)})
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
