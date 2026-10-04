"""SEL-002 Part F: AD-033 section 7's exit checks, ADDENDUM 02's prose check, and the counts the report needs.

    python scripts/sel002/exit_checks.py

Every planted control runs on a COPY of a real register in a temporary directory (the three registers are never
touched), except check 3, which writes one new note into a temporary clone of Squiddy. Zero model calls.
Writes evidence/sel002/exit_checks.json.
"""
from __future__ import annotations

import collections
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SELDON = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SELDON))

import yaml  # noqa: E402

from seldon.core import decisions as dr  # noqa: E402
from seldon.core.governed import ruling_match_threshold  # noqa: E402

GH = SELDON.parent
REPOS = ("squiddy", "seldon", "arnold")
OUT = SELDON / "evidence" / "sel002" / "exit_checks.json"
PROBE_UNITS = GH / "squiddy/docs/findings/2026-10-03_operator_audit/probe/units.jsonl"
SQ009 = GH / "squiddy/cc_tasks/2026-10-04_SQ-009_kit_dn042_spend_governor.md"


def cfg(repo: str) -> dict:
    return yaml.safe_load((GH / repo / "seldon.yaml").read_text())


def uni(repo: str) -> dr.Universe:
    return dr.universe(GH / repo, cfg(repo))


def copy_repo_register(repo: str, tmp: Path) -> Path:
    root = tmp / repo
    (root / "docs/decisions").mkdir(parents=True)
    shutil.copytree(GH / repo / "docs/decisions/register", root / "docs/decisions/register")
    return root


def check1_hand_edit(tmp: Path) -> dict:
    root = copy_repo_register("squiddy", tmp / "c1")
    reg = dr.Register("squiddy", root)
    before = reg.verify()
    f = reg.files()[100]
    f.write_text(f.read_text().replace("decided_by: ", "decided_by: x", 1), encoding="utf-8")
    after = reg.verify()
    return {"check": "a planted hand-edited record file fails verify (hash chain)", "file": f.name,
            "findings_before": len(before), "findings_after": after[:3], "pass": not before and bool(after)}


def check2_fork(tmp: Path) -> dict:
    root = copy_repo_register("squiddy", tmp / "c2")
    (root / "docs/design").mkdir(parents=True)
    shutil.copy(GH / "squiddy/docs/design/2026-09-18_after_h005_order_gate_version.md", root / "docs/design/")
    s = dr.Settings(repository="squiddy", root=root, register_dir=dr.DEFAULT_REGISTER_DIR, rendered=dr.DEFAULT_RENDERED,
                    imports=[], repositories={"squiddy": root, "seldon": GH / "seldon", "arnold": GH / "arnold"},
                    baseline_name=None, baseline_commit=None, design_notes=[], consumer_roots=[], binding_limit=8)
    u = dr.Universe(s)
    rec = {"id": "squiddy:R-999", "kind": "decision", "statement": "A planted rival to R-29's successor.",
           "source": {"path": "docs/design/2026-09-18_after_h005_order_gate_version.md", "lines": [1, 1],
                      "sha256": "0" * 64, "text": "planted"},
           "scope": ["squiddy"], "rationale": {"path": "docs/design/2026-09-18_after_h005_order_gate_version.md"},
           "review_only": "none", "supersedes": ["squiddy:R-29"]}
    try:
        dr.create(u, "supersede", rec, date="2026-10-04", decided_by="cc:planted")
        return {"check": "a planted forked supersession is refused, naming the live head", "pass": False,
                "refusal": None}
    except dr.RegisterError as exc:
        return {"check": "a planted forked supersession is refused, naming the live head",
                "refusal": str(exc), "pass": "live head of its chain is" in str(exc)}


def check3_unregistered_label(tmp: Path) -> dict:
    clone = tmp / "c3" / "squiddy"
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(GH / "squiddy"), str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "checkout", "-q", subprocess.run(
        ["git", "-C", str(GH / "squiddy"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()],
        check=True)
    c = cfg("squiddy")
    c["decisions"]["repositories"] = {"seldon": str(GH / "seldon"), "arnold": str(GH / "arnold")}
    c["decisions"].pop("probe", None)
    before = [f for f in dr.check(clone, c) if "has no record" in f]
    (clone / "docs/design/2026-10-05_DN-099_planted.md").write_text(
        "# DN-099 planted\n\n## Decisions\n\n- **R-990 (planted).** Every planted rule owes a record.\n")
    after = [f for f in dr.check(clone, c) if "has no record" in f]
    return {"check": "a planted labeled decision in a new note with no record fails verify",
            "findings_before": before, "findings_after": after, "pass": not before and any("R-990" in f for f in after)}


def check4_roundtrip() -> dict:
    u = uni("seldon")
    rt = json.loads((SELDON / "evidence/sel002/roundtrip.json").read_text())
    missing = []
    statuses = collections.Counter()
    for row in rt["rows"]:
        for q in row["records"]:
            rec = u.get(q)
            if rec is None:
                missing.append(q)
            else:
                statuses[rec.status] += 1
        if not row["records"]:
            missing.append(row["probe_id"])
    n = sum(1 for _ in PROBE_UNITS.open())
    return {"check": "round trip: every one of the 485 probe units resolves to a record with a status",
            "probe_units": n, "rows": len(rt["rows"]), "unresolved": missing,
            "record_statuses_now": dict(statuses), "pass": n == len(rt["rows"]) == 485 and not missing}


def check5_arnold_resolves() -> dict:
    u = uni("arnold")
    out = {}
    for text in ("KG-004 step 6 plans extraction under squiddy:R-112 and R-113.",
                 "KG-004 step 6 plans extraction under R-112."):
        got = dr.bind(u, text, ruling_match_threshold(cfg("arnold")))
        out[text] = [(m.id, m.match_method) for m in got if m.match_method == "identifier"]
    ok = all(any(i == "squiddy:R-112" for i, _ in v) for v in out.values())
    return {"check": "Seldon resolves squiddy:R-112 from an Arnold registration", "identifier_matches": out,
            "pass": ok}


def check6_probe() -> dict:
    u = uni("seldon")
    rep = dr.conflicts_probe(u, u.s.probe_findings, u.s.probe_exclusions)
    return {"check": "the probe re-run on the register: zero open contradictions, zero silent supersessions among "
                     "active records", "findings": rep.findings_total, "resolved": len(rep.resolved),
            "open_contradictions": rep.open_contradictions,
            "open_silent_supersessions": rep.open_silent_supersessions + [
                f"{p['record']} {p['verb']} {p['cites']}" for p in rep.unrecorded_pairs],
            "reviewed_exclusions": rep.excluded_pairs, "active_records": rep.active_records, "pass": rep.clean}


def check7_sq009() -> dict:
    u = uni("squiddy")
    text = SQ009.read_text(encoding="utf-8")
    got = dr.bind(u, text, ruling_match_threshold(cfg("squiddy")))
    bound = [{"id": m.id, "status": u.get(m.id).status, "method": m.match_method, "score": m.match_score}
             for m in got]
    r29 = u.get("squiddy:R-29")
    return {"check": "registration of SQ-009's text against the register binds no superseded record (the R-29 case)",
            "task": str(SQ009.relative_to(GH)), "bound": bound,
            "r29_status": r29.status, "r29_superseded_by": r29.superseded_by,
            "pass": all(b["status"] == "accepted" for b in bound) and "squiddy:R-29" not in [b["id"] for b in bound]}


AGENT_READ = re.compile(r"(?:^|/)(CLAUDE\.md|AGENTS\.md|README\.md)$")
STORE_CLAIM = re.compile(
    r"(?:neo4j|manifest(?:\.yaml)?|yaml manifest|the graph|the database)[^.]{0,60}\b(?:is|are|as|remains)\s+(?:the\s+)?"
    r"(?:authoritative|record\b|record of truth|truth|source of truth|system of record|live authoritative)|"
    r"graph-as-truth|does not mandate which store", re.I)


def check_addendum02() -> dict:
    hits = []
    for repo in REPOS:
        root = GH / repo
        files = [p for p in root.rglob("*.md") if AGENT_READ.search(p.as_posix())
                 and not any(x in p.parts for x in (".venv", "node_modules", ".pytest_cache", ".worktrees", "graphs"))]
        files += list((root / "docs/conventions").glob("*.md")) if (root / "docs/conventions").is_dir() else []
        for p in files:
            # Sentence by sentence, not line by line: a claim wraps across lines, and a sentence that names the
            # ledger as the authoritative record is the decision itself, not a contradiction of it.
            text = p.read_text(encoding="utf-8", errors="replace")
            for sent in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
                if STORE_CLAIM.search(sent) and not re.search(r"\bledger\b", sent, re.I):
                    hits.append(f"{p.relative_to(GH)}: {sent[:200]}")
    # Positive control (methodology 7.6): the sentences this check exists to catch must be caught, and a
    # vocabulary file's "Authoritative list:" must not be.
    planted = {"It does NOT mandate which store is called \"truth\": fss-policy-kg runs ledger-as-truth; an Arnold "
               "graph may run graph-as-truth.": True,
               "Neo4j is the live authoritative store and JSONL the archive projection.": True,
               "The manifest is the record, with no other entry point and no other record.": True,
               "Authoritative list: seldon/domain/result_units_vocabulary.yaml for every project graph": False}
    control = {t: bool(STORE_CLAIM.search(t)) == want for t, want in planted.items()}
    return {"check": "ADDENDUM 02: no agent-read file (CLAUDE.md, docs/conventions/, READMEs) names a store other "
                     "than the ledger as the record of truth", "hits": hits, "positive_control": control,
            "pass": not hits and all(control.values())}


def counts() -> dict:
    out = {"by_repo_status": {}, "none_consumers": {}, "statement_check": {}}
    for repo in REPOS:
        recs = uni(repo).records(repo)
        out["by_repo_status"][repo] = dict(collections.Counter(r.status for r in recs.values()))
        acc = [r for r in recs.values() if r.status == "accepted"]
        out["none_consumers"][repo] = sum(1 for r in acc if not r.get("consumer") and r.get("review_only") == "none")
        out["statement_check"][repo] = dict(collections.Counter(str(r.get("statement_check")) for r in recs.values()
                                                                if r.status in dr.ACTIVE and r.get("kind") != "mirror"))
    return out


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        checks = [check1_hand_edit(tmp), check2_fork(tmp), check3_unregistered_label(tmp), check4_roundtrip(),
                  check5_arnold_resolves(), check6_probe(), check7_sq009(), check_addendum02()]
    res = {"checks": checks, "all_pass": all(c["pass"] for c in checks), "counts": counts()}
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    for c in checks:
        print(("PASS " if c["pass"] else "FAIL ") + c["check"])
    print(json.dumps(res["counts"], indent=1))
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
