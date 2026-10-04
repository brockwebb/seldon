"""SEL-002 Part B: seed baseline DB-1 (AD-033-R5) through the register's one write path.

Every record is written by `seldon.core.decisions.create` / `transition` / `amend`, the functions
the `seldon decision` CLI and the `seldon_decision_*` MCP tools call; nothing here writes a
register file any other way. Zero model calls, no network.

    python scripts/sel002/seed_db1.py [--dry-run]

Inputs, all read at the DB-1 baseline (the three main HEADs recorded in docs/decisions/BASELINE_DB-1.md):
  - evidence/sel002/inventory/units_full.jsonl: the probe's own parser (inventory.py, byte for
    byte) run with its two truncation caps lifted (scripts/sel002/inventory_uncapped.py);
  - DN-037's decision bullets, AD-032's FC blocks, Arnold's ADR Decision sections and the
    Arnold ontology decisions located by span (evidence/sel002/arnold_ontology_decisions.json,
    every span checked here against the file);
  - Arnold DN-001 and DN-002's labeled decisions (beyond R5's list: AD-033-R7 stops positional
    rulings binding, and DN-001-R2 is the per-set RPE ruling SEL-001 gold set B rests on).

Outputs: the register files in each repository; evidence/sel002/seed_manifest.json (one row per
record: probe id, record id, status rule applied, receipts, consumer rule); evidence/sel002/
roundtrip.json (every one of the probe's 485 units resolved to a record with a status).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

SELDON = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SELDON))

from seldon.core import decisions as dr  # noqa: E402

GH = SELDON.parent
ROOTS = {"squiddy": GH / "squiddy", "seldon": GH / "seldon", "arnold": GH / "arnold"}
EVID = SELDON / "evidence" / "sel002"
PROBE_UNITS = GH / "squiddy/docs/findings/2026-10-03_operator_audit/probe/units.jsonl"
SEED_DATE = "2026-10-04"
SEED_BY = "cc:0636b04a"           # SEL-002's registered task id

#: R5: "a decision a dispatched task has executed under is accepted, with that task as the
#: receipt". A task file in the repository's cc_tasks/ that names the id is that receipt.
TASK_DIRS = {"squiddy": "cc_tasks", "seldon": "cc_tasks", "arnold": "cc_tasks"}

#: Consumer search roots (AD-033-R6): conformance items, tests and code that cite the id.
CONSUMER_ROOTS = {
    "squiddy": ["squiddy/conformance.yaml", "tests", "squiddy"],
    "seldon": ["tests", "seldon"],
    "arnold": ["tests", "src"],
}

#: Seldon design documents with no `Decision` section: the section that carries the decision,
#: named by heading (the inventory took their first 1,500 characters).
SELDON_DOC_SECTIONS = {
    "AD-011": "AD-011: Database-Driven Paper Assembly",
    "AD-012": "1. Design Principle",
    "AD-013": "1. Design Principle",
    "AD-014": "1. Design Principle",
    "AD-019": "2. Design Principles",
    "AD-020": "2. Pipeline Architecture",
}

#: Probe units that are not decisions of their own and resolve to a record of their family.
FAMILY = {
    "seldon:AD-020_calibration_001_leibniz_pi": ["seldon:AD-020"],
    "seldon:AD-020_calibration_002_ch04": ["seldon:AD-020"],
    "seldon:AD-020_calibration_003_ch05": ["seldon:AD-020"],
    "arnold:AALL-006-unified-workout-schema": ["arnold:ADR-006"],
}
FAMILY_REASON = {
    "seldon:AD-020_calibration_001_leibniz_pi": "AD-020 calibration run data, not a decision (probe Limits)",
    "seldon:AD-020_calibration_002_ch04": "AD-020 calibration run data, not a decision (probe Limits)",
    "seldon:AD-020_calibration_003_ch05": "AD-020 calibration run data, not a decision (probe Limits)",
    "arnold:AALL-006-unified-workout-schema": "after-action lessons on ADR-006, which ADR-007 superseded",
}

OPERATOR_DECIDER = re.compile(
    r"(operator(?:'s)?\s+(?:decision|decided|decides|ruled|ruling|rule|choice|chose|directive|"
    r"instruction|stated|said|asked|wants|requirement)\b|decided by the operator|"
    r"(?:accepted|ruled|ratified|decided)\s*\((?:operator|Brock)|\((?:operator|Brock),\s*20\d\d|"
    r"Ruled by Brock|Ratified by Brock|Brock(?:'s)?\s+(?:decision|ruling|rule|decided|ruled|asked|said)\b|"
    r"Records an operator decision|Deciders?:\*{0,2}\s*(?:Brock|the operator)|Brock\s+(?:then\s+)?ruled)", re.I)
#: A note's header (its first lines) states who decided for the whole note ("**Deciders:** Brock Webb",
#: "Status: accepted (operator decisions of ...)"); every decision in the note carries that receipt.
HEADER_LINES = 12
DISPATCH = re.compile(r"\b(dispatch(?:ed|es|ing)?|waits on|held behind|is held|hold(?:s)? (?:on|behind))\b", re.I)
RATIONALE_HEAD = re.compile(r"\b(rationale|why|background|prior art|context|motivation)\b", re.I)
PREREG_HEAD = re.compile(r"pre-?regist", re.I)


# ---------------------------------------------------------------------------
# files, hashes, dates
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def lines_of(repo: str, rel: str) -> tuple[str, ...]:
    return tuple((ROOTS[repo] / rel).read_text(encoding="utf-8").splitlines())


@lru_cache(maxsize=None)
def sha_of(repo: str, rel: str) -> str:
    return hashlib.sha256((ROOTS[repo] / rel).read_bytes()).hexdigest()


@lru_cache(maxsize=None)
def blame_dates(repo: str, rel: str) -> tuple[str, ...]:
    r = subprocess.run(["git", "-C", str(ROOTS[repo]), "blame", "--line-porcelain", "--", rel],
                       capture_output=True, text=True)
    if r.returncode != 0:          # not committed yet (AD-033 at seed time is committed; safety)
        return ()
    out, cur = [], None
    import datetime as _dt
    for ln in r.stdout.splitlines():
        if ln.startswith("author-time "):
            cur = _dt.datetime.fromtimestamp(int(ln.split()[1]), _dt.timezone.utc).date().isoformat()
        elif ln.startswith("\t"):
            out.append(cur)
    return tuple(out)


_DATE = re.compile(r"(20\d\d-\d\d-\d\d)")


def doc_date(repo: str, rel: str, line: int) -> str:
    m = _DATE.match(Path(rel).name)
    if m:
        return m.group(1)
    for ln in lines_of(repo, rel)[:15]:
        if re.search(r"\bdate\b", ln, re.I):
            m = _DATE.search(ln)
            if m:
                return m.group(1)
    b = blame_dates(repo, rel)
    if b and 0 < line <= len(b):
        return b[line - 1]
    return SEED_DATE


def row_date(repo: str, rel: str, line: int) -> str:
    b = blame_dates(repo, rel)
    return b[line - 1] if b and 0 < line <= len(b) else doc_date(repo, rel, line)


def span(repo: str, rel: str, start: int, text: str) -> tuple[int, int]:
    """The inclusive line range whose text, stripped, is `text` exactly."""
    ls = lines_of(repo, rel)
    n = len(text.splitlines())
    for end in [start + n - 1] + [start + n - 1 + d for d in (1, -1, 2, -2, 3, 4, 5)]:
        if start <= end <= len(ls) and "\n".join(ls[start - 1:end]).strip() == text.strip():
            return start, end
    raise SystemExit(f"FATAL: {repo}:{rel}:{start} span does not reproduce the unit text")


def text_of(repo: str, rel: str, start: int, end: int) -> str:
    return "\n".join(lines_of(repo, rel)[start - 1:end]).strip()


def heading_above(repo: str, rel: str, line: int) -> str:
    for ln in reversed(lines_of(repo, rel)[:line - 1]):
        if ln.startswith("#"):
            return ln.lstrip("#").strip()
    return ""


def section_span(repo: str, rel: str, heading_pred) -> tuple[int, int] | None:
    """From a heading that satisfies `heading_pred` to the line before the next heading of the
    same or a higher level, trailing blank lines dropped."""
    ls = lines_of(repo, rel)
    for i, ln in enumerate(ls):
        m = re.match(r"^(#+)\s+(.*)$", ln)
        if m and heading_pred(m.group(2).strip()):
            level = len(m.group(1))
            end = len(ls)
            for j in range(i + 1, len(ls)):
                mm = re.match(r"^(#+)\s", ls[j])
                if mm and len(mm.group(1)) <= level:
                    end = j
                    break
            while end > i + 1 and not ls[end - 1].strip():
                end -= 1
            return i + 1, end
    return None


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------

def receipts_in(repo: str, rel: str, start: int, end: int, extra_lines: tuple[int, ...] = (),
                header: bool = True) -> list[str]:
    out = []
    ls = lines_of(repo, rel)
    head = set(range(1, min(HEADER_LINES, len(ls)) + 1)) if header else set()
    for n in sorted(set(range(start, end + 1)) | set(extra_lines) | head):
        ln = ls[n - 1]
        m = OPERATOR_DECIDER.search(ln)
        if m:
            excerpt = ln.strip()
            if len(excerpt) > 220:
                a = max(0, m.start() - 100)
                excerpt = ("..." if a else "") + ln[a:m.end() + 100].strip() + "..."
            out.append(f"{rel}:{n}: \"{excerpt}\"")
    return out


@lru_cache(maxsize=None)
def task_texts(repo: str) -> tuple[tuple[str, str], ...]:
    d = ROOTS[repo] / TASK_DIRS[repo]
    return tuple((p.relative_to(ROOTS[repo]).as_posix(), p.read_text(encoding="utf-8", errors="replace"))
                 for p in sorted(d.glob("*.md")))


def executing_tasks(repo: str, local: str, exclude: str = "") -> list[str]:
    pat = re.compile(r"(?<![\w-])" + re.escape(local) + r"(?![\w]|-\d)")
    return [p for p, t in task_texts(repo) if p != exclude and pat.search(t)][:3]


def consumers(repo: str, local: str, everywhere: bool = False) -> list[str]:
    if everywhere:
        out = []
        for r in ROOTS:
            out += [f"{r}:{p}" for p in dr.cited_by(local, ROOTS[r], CONSUMER_ROOTS[r])]
        return out
    return dr.cited_by(local, ROOTS[repo], CONSUMER_ROOTS[repo])


def review_only(repo: str, rel: str, start: int, text: str, fc: bool = False) -> tuple[str, str]:
    head = heading_above(repo, rel, start)
    if rel.endswith("S-008_rules.md") or PREREG_HEAD.search(head):
        return "pre_registration", f"under heading '{head}'"
    if fc or DISPATCH.search(text):
        return "dispatch", "FC label" if fc else "names dispatch or a hold"
    if RATIONALE_HEAD.search(head):
        return "rationale", f"under heading '{head}'"
    return "none", "no consumer and no rule applies"


# ---------------------------------------------------------------------------
# building the records
# ---------------------------------------------------------------------------

class Seed:
    def __init__(self):
        self.records: list[dict] = []          # dicts with 'record', 'event', meta
        self.transitions: list[dict] = []
        self.probe_map: dict[str, list[str]] = {}

    def add(self, *, repo, local, kind, rel, start, end, text, stated_status="", probe_id=None,
            decided_by=None, operator_receipts=None, extra=None, force_status=None, waits_on=None,
            fc=False, date=None, scope=None, anchor=None, consumers_everywhere=False):
        qid = f"{repo}:{local}"
        receipts = list(operator_receipts or [])
        op = bool(receipts)
        status_rule = "source states no status: accepted (R5)"
        status = "accepted"
        task_receipts: list[str] = []
        sup = re.search(r"superseded by (ADR-\d{3})", stated_status or "", re.I)
        if force_status:
            status, status_rule = force_status, f"SEL-002 Part B: {force_status}"
        elif re.search(r"\b(proposed|draft)\b", stated_status or "", re.I):
            task_receipts = executing_tasks(repo, local, exclude=rel)
            doc = re.match(r"((?:AD|DN)-\d{3})-", local)
            if not task_receipts and doc:
                # A task that names the note executes under its decisions (SEL-001 under AD-031,
                # SEL-002 under AD-033): the note's id is the receipt.
                task_receipts = executing_tasks(repo, doc.group(1), exclude=rel)
            if task_receipts:
                status, status_rule = "accepted", (f"source says '{stated_status[:60]}'; a dispatched "
                                                   f"task executed under it (R5): {', '.join(task_receipts)}")
            else:
                status = "proposed"
                status_rule = f"source says '{stated_status[:60]}' and no task names it"
                waits_on = waits_on or (f"acceptance: the source's status reads '{stated_status[:80]}' "
                                        f"and names no measurement")
        elif stated_status:
            status_rule = f"source says '{stated_status[:60]}': accepted"
        rec = {"id": qid, "kind": kind,
               "source": {"path": rel, "lines": [start, end], "sha256": sha_of(repo, rel), "text": text},
               "scope": scope or [repo],
               "rationale": {"path": rel, "anchor": anchor or local}}
        if kind != "mirror":
            rec["statement"] = text
        if status == "proposed":
            rec["waits_on"] = waits_on
            rec["status"] = "proposed"
        cons = consumers(repo, local, everywhere=consumers_everywhere)
        if cons:
            rec["consumer"] = cons
            ro, ro_why = None, None
        else:
            ro, ro_why = review_only(repo, rel, start, text, fc=fc)
            rec["review_only"] = ro
        if extra:
            rec.update(extra)
        self.records.append({
            "record": rec, "event": "propose" if status == "proposed" else "accept",
            "decided_by": decided_by or ("operator" if op else "desktop"),
            "operator_stated": op, "receipts": receipts + task_receipts,
            "date": date or doc_date(repo, rel, start),
            "meta": {"probe_id": probe_id, "status_rule": status_rule, "consumer_rule": ro_why,
                     "operator_receipts": receipts},
        })
        if sup:
            self.transitions.append({"kind": "supersede", "id": qid,
                                     "by": f"{repo}:{sup.group(1)}",
                                     "reason": f"the source's status line reads '{stated_status}' (R5: the "
                                               f"source's stated status)",
                                     "receipts": [f"{rel}: status line '{stated_status}'"]})
        if probe_id:
            self.probe_map.setdefault(probe_id, []).append(qid)
        return qid


def status_line(repo: str, rel: str) -> tuple[int, str]:
    for i, ln in enumerate(lines_of(repo, rel)[:30], 1):
        m = re.search(r"^\*{0,2}Status[^:]*:?\*{0,2}:?\s*(.+)$", ln.strip(), re.I)
        if m:
            return i, m.group(1).strip().strip("*").strip()
    return 0, ""


def build(seed: Seed) -> None:
    units = [json.loads(l) for l in (EVID / "inventory" / "units_full.jsonl").open()]
    di_r = re.compile(r"\bR-(\d{1,3})\b")
    labeled_squiddy = {u["id"] for u in units if u["repo"] == "squiddy" and u["id"].startswith("R-")}
    deferred_mirrors = []
    for u in units:
        repo = u["repo"]
        rel = u["file"].split("/", 1)[1]
        pid = u["id"] if u["id"].startswith(repo + ":") else f"{repo}:{u['id']}"
        if repo == "squiddy" and u["id"].startswith("R-"):
            s, e = span(repo, rel, u["line"], u["text"])
            sl = status_line(repo, rel)
            seed.add(repo=repo, local=u["id"], kind="decision", rel=rel, start=s, end=e,
                     text=u["text"], stated_status=u["status"], probe_id=pid,
                     operator_receipts=receipts_in(repo, rel, s, e))
        elif repo == "squiddy" and u["id"].startswith("EX-REQ"):
            seed.add(repo=repo, local=u["id"], kind="requirement", rel=rel, start=u["line"],
                     end=u["line"], text=u["text"], probe_id=pid,
                     operator_receipts=receipts_in(repo, rel, u["line"], u["line"], header=False),
                     date=row_date(repo, rel, u["line"]))
        elif repo == "squiddy" and u["id"].startswith("DI-"):
            cols = [c.strip() for c in u["text"].strip("|").split("|")]
            src_col = cols[1] if len(cols) > 1 else ""
            # "DI rows that cite an R become kind: mirror pointing at it" (SEL-002 Part B): the R the
            # source column names, else the first R the row cites anywhere.
            m = di_r.search(src_col) or di_r.search(u["text"])
            origin = inherited_from(src_col)
            common = dict(repo=repo, local=u["id"], rel=rel, start=u["line"], end=u["line"],
                          text=u["text"], probe_id=pid, decided_by=f"inherited:{origin}",
                          operator_receipts=receipts_in(repo, rel, u["line"], u["line"], header=False),
                          date=row_date(repo, rel, u["line"]))
            target = None
            if m:
                cand = [f"R-{m.group(1).zfill(2)}", f"R-{m.group(1)}"]
                target = next((c for c in cand if c in labeled_squiddy), None)
            if target:
                deferred_mirrors.append((common, f"squiddy:{target}"))
            else:
                seed.add(kind="decision", **common)
        elif repo == "seldon" and re.match(r"AD-\d{3}-R\d+$", u["id"]):
            if u["id"] in ("AD-033-R10", "AD-033-R11"):
                continue      # written by supersede below (ADDENDUM 01 item 3, ADDENDUM 02 item 1)
            s, e = span(repo, rel, u["line"], u["text"])
            seed.add(repo=repo, local=u["id"], kind="decision", rel=rel, start=s, end=e,
                     text=u["text"], stated_status=u["status"], probe_id=pid,
                     operator_receipts=receipts_in(repo, rel, s, e),
                     scope=["seldon", "squiddy", "arnold"] if u["id"].startswith("AD-033") else None)
        elif repo == "seldon":
            doc = re.match(r"seldon:(AD-\d{3})", pid).group(1)
            if pid in FAMILY:
                seed.probe_map[pid] = FAMILY[pid]
                continue
            if doc == "AD-032":
                seed.probe_map[pid] = []          # filled by the FC records
                continue
            want = SELDON_DOC_SECTIONS.get(doc)
            sp = section_span(repo, rel, (lambda h, w=want: h.startswith(w)) if want else
                              (lambda h: bool(re.match(r"(?:\d+\.\s*)?Decision\b", h, re.I))))
            if sp is None:
                raise SystemExit(f"FATAL: no decision section in {rel}")
            sl_n, sl = status_line(repo, rel)
            seed.add(repo=repo, local=doc, kind="decision", rel=rel, start=sp[0], end=sp[1],
                     text=text_of(repo, rel, *sp), stated_status=sl, probe_id=pid,
                     operator_receipts=receipts_in(repo, rel, sp[0], sp[1], (sl_n,) if sl_n else ()))
        elif repo == "arnold" and "/adr/" in u["file"]:
            if pid in FAMILY:
                seed.probe_map[pid] = FAMILY[pid]
                continue
            stem = Path(rel).stem
            num = stem[:3]
            local = f"ADR-{num}" + ("-A01" if "addendum-01" in stem else "")
            pred = (lambda h: h == "Rulings") if "addendum-01" in stem else \
                   (lambda h: bool(re.match(r"(?:\d+\.\s*)?Decision$", h, re.I)))
            sp = section_span(repo, rel, pred)
            sl_n, sl = status_line(repo, rel)
            seed.add(repo=repo, local=local, kind="decision", rel=rel, start=sp[0], end=sp[1],
                     text=text_of(repo, rel, *sp), stated_status=sl, probe_id=pid,
                     operator_receipts=receipts_in(repo, rel, sp[0], sp[1], (sl_n,) if sl_n else ()))
        elif repo == "arnold" and "/ontology/" in u["file"]:
            seed.probe_map[pid] = []              # filled by the ontology records
    for common, target in deferred_mirrors:
        seed.add(kind="mirror", extra={"mirrors": target}, **common)


def inherited_from(src_col: str) -> str:
    low = src_col.lower()
    for key, name in (("icsp_notebook", "fss-policy-kg"), ("fss-policy-kg", "fss-policy-kg"),
                      ("ai-readiness-kg", "ai-readiness-kg"), ("wintermute", "wintermute"),
                      ("arnold", "arnold"), ("sfv-paper", "sfv-paper"), ("seldon", "seldon")):
        if key in low:
            return name
    return "squiddy"


def build_dn037(seed: Seed) -> None:
    repo, rel = "squiddy", "docs/design/2026-10-02_DN-037_harvest_is_its_own_component_tentacle_deferred.md"
    ls = lines_of(repo, rel)
    bullets = []
    for i, ln in enumerate(ls, 1):
        if ln.startswith("- "):
            j = i
            while j < len(ls) and (ls[j].startswith("  ") and ls[j].strip()):
                j += 1
            bullets.append((i, j))
    hdr = 3
    for n, (s, e) in enumerate(bullets, 1):
        in_decision = heading_above(repo, rel, s) == "Decision"
        rec_receipts = [f"{rel}:{hdr}: \"{ls[hdr - 1].strip()} {ls[hdr].strip()}\""] if in_decision else []
        seed.add(repo=repo, local=f"DN-037-R{n}", kind="decision", rel=rel, start=s, end=e,
                 text=text_of(repo, rel, s, e), operator_receipts=rec_receipts,
                 probe_id=None, anchor=f"bullet {n} ({heading_above(repo, rel, s)})")


def build_fc(seed: Seed) -> None:
    repo, rel = "seldon", "docs/design/AD-032_factory_control_design.md"
    ls = lines_of(repo, rel)
    starts = [(i, re.match(r"^\*\*(FC-\d{2})\.", ln).group(1)) for i, ln in enumerate(ls, 1)
              if re.match(r"^\*\*FC-\d{2}\.", ln)]
    for k, (s, label) in enumerate(starts):
        nxt = starts[k + 1][0] if k + 1 < len(starts) else len(ls) + 1
        e = s
        for j in range(s + 1, nxt):
            if ls[j - 1].startswith("#"):
                break
            e = j
        while e > s and not ls[e - 1].strip():
            e -= 1
        n = int(label[3:])
        text = text_of(repo, rel, s, e)
        if n <= 7:
            st_line = next(j for j in range(s, e + 1) if "Status:" in ls[j - 1])
            receipts = [f"{rel}:1: \"{ls[0].strip()}\"", f"{rel}:{st_line}: \"{ls[st_line - 1].strip()}\""]
            seed.add(repo=repo, local=f"AD-032-{label}", kind="decision", rel=rel, start=s, end=e,
                     text=text, operator_receipts=receipts, fc=True, probe_id=None,
                     scope=["squiddy", "seldon", "arnold"], anchor=label, consumers_everywhere=True,
                     force_status="accepted")
        else:
            seed.add(repo=repo, local=f"AD-032-{label}", kind="decision", rel=rel, start=s, end=e,
                     text=text, fc=True, probe_id=None, scope=["squiddy", "seldon", "arnold"],
                     anchor=label, consumers_everywhere=True, force_status="proposed",
                     waits_on="P1 to P6 per AD-032 section 8")
        seed.probe_map.setdefault("seldon:AD-032_factory_control_design", []).append(
            f"seldon:AD-032-{label}")


def build_arnold_ontology(seed: Seed) -> None:
    data = json.loads((EVID / "arnold_ontology_decisions.json").read_text())
    for doc in data["documents"]:
        rel = f"docs/ontology/{doc['file']}"
        slug = Path(doc["file"]).stem
        repo = "arnold"
        sl_n = doc["status_line"]["line"] if doc.get("status_line") else 0
        b = 0
        for d in sorted(doc["decisions"], key=lambda x: x["start"]):
            s, e = d["start"], d["end"]
            text = text_of(repo, rel, s, e)
            if not text:
                raise SystemExit(f"FATAL: empty span {rel}:{s}-{e}")
            if d.get("label"):
                local = f"{slug}-{d['label']}"
            else:
                b += 1
                local = f"{slug}-B{b}"
            stated = "proposed" if d.get("ruled_status") == "open" else ""
            # The document's status line and decider line name Brock as decider of its RULED items;
            # an item the document marks open was not decided, so it carries no such receipt.
            extra_lines = () if stated else (
                tuple(r["line"] for r in doc.get("decider_receipts") or []) + ((sl_n,) if sl_n else ()))
            receipts = receipts_in(repo, rel, s, e, extra_lines, header=not stated)
            qid = seed.add(repo=repo, local=local, kind="decision", rel=rel, start=s, end=e, text=text,
                           operator_receipts=receipts, probe_id=f"arnold:{slug}", stated_status=stated,
                           waits_on=f"the operator's ruling: {rel} marks it open" if stated else None,
                           anchor=f"{d.get('label') or 'B' + str(b)}: {d.get('gist', '')[:80]}")
            if d.get("ruled_status") == "superseded" and d.get("label") in ("D1", "D2"):
                rev = "arnold:2026-06-27_vocab-decision-block-cycle-reversal-" + {"D1": "R1", "D2": "R2"}[d["label"]]
                seed.transitions.append({
                    "kind": "supersede", "id": qid, "by": rev,
                    "reason": (f"the source states it superseded: {rel} D-table and "
                               f"docs/ontology/2026-06-27_vocab-decision-block-cycle-reversal.md lines 6-8 "
                               f"('Supersedes: D1 (segment) and D2 (block=mesocycle)'); R5: the source's stated status"),
                    "receipts": [f"{rel}:{s}", "docs/ontology/2026-06-27_vocab-decision-block-cycle-reversal.md:6"]})


def build_arnold_dns(seed: Seed) -> None:
    repo = "arnold"
    for p in sorted((ROOTS[repo] / "docs/design").glob("DN-*.md")):
        rel = p.relative_to(ROOTS[repo]).as_posix()
        ls = lines_of(repo, rel)
        starts = [(i, re.match(r"^\*\*(DN-\d{3}-R\d+)\b", ln).group(1)) for i, ln in enumerate(ls, 1)
                  if re.match(r"^\*\*DN-\d{3}-R\d+\b", ln)]
        for k, (s, label) in enumerate(starts):
            nxt = starts[k + 1][0] if k + 1 < len(starts) else len(ls) + 1
            e = s
            for j in range(s + 1, nxt):
                if ls[j - 1].startswith("#"):
                    break
                e = j
            while e > s and not ls[e - 1].strip():
                e -= 1
            sl_n, sl = status_line(repo, rel)
            seed.add(repo=repo, local=label, kind="decision", rel=rel, start=s, end=e,
                     text=text_of(repo, rel, s, e), stated_status=sl,
                     operator_receipts=receipts_in(repo, rel, s, e, (sl_n,) if sl_n else ()))


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

def universe() -> dr.Universe:
    import yaml
    cfg = yaml.safe_load((SELDON / "seldon.yaml").read_text())
    return dr.universe(SELDON, cfg)


def write(seed: Seed, dry: bool) -> dict:
    u = universe()
    order = {"squiddy": 0, "seldon": 1, "arnold": 2}
    recs = sorted(seed.records, key=lambda r: (order[dr.split_id(r["record"]["id"])[0]],
                                               r["record"]["kind"] == "mirror"))
    written = 0
    for r in recs:
        if dry:
            dr._check_shape_or_refuse(dict(r["record"], event=r["event"], date=r["date"],
                                           decided_by=r["decided_by"],
                                           operator_stated=r["operator_stated"],
                                           status=r["record"].get("status", "accepted"),
                                           **({"receipts": r["receipts"]} if r["receipts"] else {})))
            continue
        dr.create(u, r["event"], r["record"], date=r["date"], decided_by=r["decided_by"],
                  operator_stated=r["operator_stated"], receipts=r["receipts"] or None,
                  reason="DB-1 seed (AD-033-R5)")
        written += 1
    if not dry:
        for t in seed.transitions:
            dr.transition(u, "supersede", t["id"], date=SEED_DATE, decided_by=SEED_BY,
                          reason=t["reason"], receipts=t["receipts"], superseded_by=t["by"])
        write_addenda(u)
    return {"records": written, "transitions": len(seed.transitions)}


def write_addenda(u: dr.Universe) -> None:
    """ADDENDUM 01 item 3 and ADDENDUM 02 item 1: AD-033-R10 and R11, through the command."""
    rel = "docs/design/AD-033_decision_register.md"
    units = {x["id"]: x for x in map(json.loads, (EVID / "inventory" / "units_full.jsonl").open())
             if x["repo"] == "seldon"}
    for local, sup, amends, op, receipts in (
        ("AD-033-R10", ["seldon:AD-030-R14"], [], False,
         ["seldon/cc_tasks/2026-10-04_SEL-002_ADDENDUM_01_decision_label_and_r14.md item 3",
          f"{rel}: AD-033-R10 'Supersedes AD-030-R14.'"]),
        ("AD-033-R11", ["squiddy:R-04"],
         [("squiddy:R-08", "the manifest's primacy: the manifest is the stream of catalog, assess, admit, "
                           "decline and supersede events in the graph's ledger (AD-033-R11)"),
          ("squiddy:DI-070", "'no other record': the record is the ledger's manifest events (AD-033-R11)"),
          ("squiddy:DI-163", "the event-backed manifest reads as the ledger of record (AD-033-R11)"),
          ("squiddy:DI-242", "direction: decisions.jsonl and the manifest YAML are projections of the "
                             "ledger's events, not the reverse (AD-033-R11)"),
          ("seldon:AD-030-R5", "reading: 'the manifest lives in the graph' means the graph's ledger "
                               "(AD-033-R11)")], True,
         ["seldon/cc_tasks/2026-10-04_SEL-002_ADDENDUM_02_store_of_truth_settled.md item 1",
          f"{rel}: AD-033-R11 'Operator decision 2026-10-04, ending the question.'"]),
    ):
        x = units[local]
        s, e = span("seldon", rel, x["line"], x["text"])
        rec = {"id": f"seldon:{local}", "kind": "decision", "statement": x["text"],
               "source": {"path": rel, "lines": [s, e], "sha256": sha_of("seldon", rel), "text": x["text"]},
               "scope": ["seldon", "squiddy", "arnold"], "rationale": {"path": rel, "anchor": local},
               "supersedes": sup}
        cons = consumers("seldon", local)
        if cons:
            rec["consumer"] = cons
        else:
            rec["review_only"] = review_only("seldon", rel, s, x["text"])[0]
        dr.create(u, "supersede", rec, date=SEED_DATE, decided_by="operator" if op else "desktop",
                  operator_stated=op, receipts=receipts,
                  reason="DB-1 seed: " + ("SEL-002 ADDENDUM 02 item 1" if op else "SEL-002 ADDENDUM 01 item 3"))
        for target, clause in amends:
            dr.amend(u, target, date=SEED_DATE, decided_by="operator", operator_stated=True,
                     receipts=receipts, reason="SEL-002 ADDENDUM 02 item 1",
                     amendment={"clause": clause, "text": f"Amended by seldon:{local}: " + clause,
                                "by": f"seldon:{local}"})


def roundtrip(seed: Seed) -> dict:
    probe = [json.loads(l) for l in PROBE_UNITS.open()]
    u = universe()
    rows, missing = [], []
    for x in probe:
        pid = x["id"] if x["id"].startswith(x["repo"] + ":") else f"{x['repo']}:{x['id']}"
        ids = seed.probe_map.get(pid)
        if pid in ("seldon:AD-033-R10", "seldon:AD-033-R11"):
            ids = [pid]
        statuses = {}
        for q in ids or []:
            rec = u.get(q)
            statuses[q] = rec.status if rec else None
        ok = bool(statuses) and all(statuses.values())
        rows.append({"probe_id": pid, "records": statuses, "resolved": ok,
                     "note": FAMILY_REASON.get(pid)})
        if not ok:
            missing.append(pid)
    return {"probe_units": len(probe), "resolved": len(probe) - len(missing), "missing": missing,
            "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    seed = Seed()
    build(seed)
    build_dn037(seed)
    build_fc(seed)
    build_arnold_ontology(seed)
    build_arnold_dns(seed)
    ids = [r["record"]["id"] for r in seed.records]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise SystemExit(f"FATAL: duplicate record ids {sorted(dup)}")
    out = write(seed, args.dry_run)
    manifest = [{"id": r["record"]["id"], "event": r["event"], "decided_by": r["decided_by"],
                 "operator_stated": r["operator_stated"], "receipts": r["receipts"],
                 "date": r["date"], "kind": r["record"]["kind"],
                 "consumer": r["record"].get("consumer"), "review_only": r["record"].get("review_only"),
                 **r["meta"]} for r in seed.records]
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / ("seed_manifest_dryrun.json" if args.dry_run else "seed_manifest.json")).write_text(
        json.dumps({"summary": out, "records": manifest, "transitions": seed.transitions,
                    "probe_map": seed.probe_map}, indent=1, ensure_ascii=False))
    print(json.dumps(out))
    if not args.dry_run:
        rt = roundtrip(seed)
        (EVID / "roundtrip.json").write_text(json.dumps(rt, indent=1, ensure_ascii=False))
        print(f"round trip: {rt['resolved']}/{rt['probe_units']} probe units resolve; missing {rt['missing']}")
        return 0 if not rt["missing"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
