"""SEL-002 Part C: the probe's 45 findings and 12 drifted mirrors, applied as register records.

Every disposition becomes a transition, superseding or amending record written through
`seldon.core.decisions` (the one write path), citing its finding id and the probe's verbatim quotes
(`squiddy/docs/findings/2026-10-03_operator_audit/probe/conflicts.jsonl`). The dispositions apply as
the probe wrote them, except where it offered a choice: those follow AD-033 section 5. No source
document is edited (SEL-002 Part C); the two CLAUDE.md corrections ADDENDUM 02 item 3 orders are
separate commits. Zero model calls.

    python scripts/sel002/part_c_dispositions.py [--dry-run]

Writes evidence/sel002/part_c_events.json (one row per event: finding, op, target, by, clause,
decided_by, whether the target is operator-stated) from which the override list is drawn.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SELDON = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SELDON))

import yaml  # noqa: E402

from seldon.core import decisions as dr  # noqa: E402

GH = SELDON.parent
EVID = SELDON / "evidence" / "sel002"
CONFLICTS = GH / "squiddy/docs/findings/2026-10-03_operator_audit/probe/conflicts.jsonl"
DATE = "2026-10-04"
CC = "cc:0636b04a"                 # SEL-002, applying a probe disposition under L4 (AD-033-R5)
DESKTOP = "desktop"                # AD-033 section 5's choices are the Desktop design session's
S5 = "seldon/docs/design/AD-033_decision_register.md section 5"


def S(i): return f"squiddy:{i}"
def L(i): return f"seldon:{i}"
def A(i): return f"arnold:{i}"


# op: amend (clause, text, by=None, changes=None) | supersede (by) | deprecate | accept | kind (mirror -> decision)
# Every entry: (finding, op, target, kwargs). Ordered so an amending record is active when it amends.
EVENTS: list[tuple[str, str, str, dict]] = []


def amend(f, target, clause, text, by=None, changes=None, decided_by=CC, extra_receipts=()):
    EVENTS.append((f, "amend", target, dict(clause=clause, text=text, by=by, changes=changes,
                                           decided_by=decided_by, extra_receipts=list(extra_receipts))))


def supersede(f, target, by, decided_by=CC, extra_receipts=()):
    EVENTS.append((f, "supersede", target, dict(by=by, decided_by=decided_by,
                                               extra_receipts=list(extra_receipts))))


def deprecate(f, target, decided_by=CC, extra_receipts=()):
    EVENTS.append((f, "deprecate", target, dict(decided_by=decided_by, extra_receipts=list(extra_receipts))))


def accept(f, target, decided_by=CC, extra_receipts=()):
    EVENTS.append((f, "accept", target, dict(decided_by=decided_by, extra_receipts=list(extra_receipts))))


def to_decision(f, target, why):
    """A drifted mirror carries a decision its R does not: it becomes a decision with its own
    verbatim statement and stops pointing at the R (FC-16 holds for faithful mirrors only)."""
    EVENTS.append((f, "kind", target, dict(why=why, decided_by=CC)))


# ---------------------------------------------------------------------------
# The 12 drifted mirrors first: several findings amend BY a drifted row, which must stand as a
# decision of its own before it can amend anything (probe "DI mirror summary").
# ---------------------------------------------------------------------------
M = "MIRROR"
to_decision(M, S("DI-240"), "reverses R-134: a fixed padding width costs 20.7x and is not batch-invariant, so `pad_to: longest`")
to_decision(M, S("DI-242"), "adds the acquire key without the kit version, which no R records (probe F19: give it a decision id)")
to_decision(M, S("DI-246"), "adds the unproxied model transport as a named gap R-142 does not allow (probe F18: keep DI-246 as the record of the gap)")
to_decision(M, S("DI-252"), "adds pinned question sets (`test.question_set`) that bypass R-131's log draw, and an n/a branch")
to_decision(M, S("DI-178"), "states the CLI cache measurement and an attribution to R-11; its source column's R-20 is not what it says")
to_decision(M, S("DI-211"), "cites R-90 for identifier-grammar validation at the write path; R-90 is the OpenAlex administrative layer (probable mis-citation)")
to_decision(M, S("DI-263"), "adds `reused_from_key` adoption of verdicts recorded under an older key; R-166 says only that an unchanged excerpt keeps its verdict")
to_decision(M, S("DI-260"), "adds an arXiv-copy exception to the public allowlist at release")
to_decision(M, S("DI-201"), "reads R-74's 'tool unchanged' as 'scoring unchanged, verb plans extended'")
amend(M, S("R-134"), "the fixed padding width", "Replaced by `pad_to: longest`: a fixed width costs 20.7x and is still not batch-invariant (DI-240's measured reversal).", by=S("DI-240"))
amend(M, S("R-131"), "the question draw", "A graph may pin its question set (`test.question_set`), which bypasses the log draw; an n/a branch exists (DI-252).", by=S("DI-252"))
amend(M, S("R-150"), "question sets", "DI-252 adds pinned question sets and an n/a branch that R-150 and R-151 do not state.", by=S("DI-252"))
amend(M, S("R-166"), "verdict reuse", "A verdict recorded under an older key is adopted with no call when its recorded prompt hash equals the prompt now sent (`reused_from_key`, DI-263).", by=S("DI-263"))
amend(M, S("R-158"), "the public allowlist at release", "An arXiv copy of a work is an allowed public source at release (DI-260).", by=S("DI-260"))
amend(M, S("R-74"), "'tool unchanged'", "Read as 'scoring unchanged, verb plans extended' (DI-201, documented).", by=S("DI-201"))
# DI-163 (R-08): amended by AD-033-R11 at the seed (ADDENDUM 02 item 1); DI-258 (F03), DI-204 (F12) below.

# ---------------------------------------------------------------------------
# The 45 findings
# ---------------------------------------------------------------------------
MODEL_NODES = ("model calls are confined to declared model-bucket nodes (extract, seed_select, seed_propose, "
               "seed_reselect, shelf_screen, questions, test.judge), each on the call layer; serving stays model-free")
amend("F01", S("DI-020"), "'extraction is the only stage that calls a model'", MODEL_NODES[0].upper() + MODEL_NODES[1:] + ".")
amend("F01", S("DI-118"), "'extraction is the only model call'", MODEL_NODES[0].upper() + MODEL_NODES[1:] + ".")

PURPOSE = "The operator's input block is `scope:` (R-129); `purpose:` is the former name, which init refuses (DI-238)."
amend("F02", S("R-102"), "'what it exists to answer, as a class' (the purpose: wording)", PURPOSE, by=S("R-129"))
amend("F02", S("R-115"), "the `purpose:` label", PURPOSE, by=S("R-129"))
amend("F02", S("R-121"), "item 3's wording", PURPOSE, by=S("R-129"))
amend("F02", S("R-124"), "'its purpose: block is the operator's one input'", PURPOSE, by=S("R-129"))
amend("F02", S("DI-237"), "'purpose:, which init now requires'", PURPOSE, by=S("DI-238"))

amend("F03", S("R-162"), "the gate clause", "A recall-control file passes when the model judged it (a call was made) and did not exclude it: `include` or `unsure` passes (R-164; also probe F09).", by=S("R-164"))
supersede("F03", S("DI-258"), S("DI-261"))

amend("F04", S("DI-006"), "which store is truth", "Settled for every graph by AD-033-R11: the append-only, hash-chained ledger is the record of truth; Neo4j is the live working store written only by ledger replay (R-15 stands).", by=L("AD-033-R11"), decided_by="operator", extra_receipts=["seldon/cc_tasks/2026-10-04_SEL-002_ADDENDUM_02_store_of_truth_settled.md item 2"])

amend("F05", L("AD-030-R16"), "its binding role", "In a repository with a decision register, positional Rulings stop binding; registration binds accepted `Decision` records (AD-033-R7: 'Supersedes the binding role of AD-030-R16'). R16 stays in force for prose readers.", by=L("AD-033-R7"))

amend("F06", S("R-15"), "the table of four things", "The table gains the manifest: the stream of catalog, assess, admit, decline and supersede events in the graph's ledger (AD-033-R11; AD-033 section 5).", by=L("AD-033-R11"), decided_by="operator", extra_receipts=["seldon/cc_tasks/2026-10-04_SEL-002_ADDENDUM_02_store_of_truth_settled.md item 2", S5 + " F06"])

amend("F07", S("R-14"), "the premise 'extraction is the critical path to the second consumer'", "Overtaken: the second consumer is built from the cheap layers only (R-113) and its extraction valve stays closed (R-172). The rest of R-14 (grounding, stamp, pilot) stands for any graph that opens extraction.", by=S("R-172"))
amend("F07", S("R-91"), "the Arnold repeat clause", "Arnold does not repeat the long-works comparison: its extraction valve stays closed (R-172).", by=S("R-172"))
amend("F07", S("DI-227"), "the Arnold repeat clause", "Arnold does not repeat the long-works comparison: its extraction valve stays closed (R-172).", by=S("R-172"))

G4 = "True of G4 alone; overtaken as a kit default: the claims paradigm failed on a second corpus (DI-230) and the extraction valve of every future graph is closed by default (R-112)."
amend("F08", S("DI-035"), "'not a standing constraint on extraction anywhere'", G4, by=S("R-112"))
amend("F08", S("DI-037"), "the scope of the G4 kill", G4, by=S("R-112"))

amend("F09", S("R-152"), "lookup labels", "The model may propose lookup labels; it still chooses only returned descriptors (R-160 revises R-152).", by=S("R-160"))
amend("F09", S("R-153"), "the revised clause", "Revised by R-161.", by=S("R-161"))
amend("F09", S("DI-253"), "lookup labels", "The model may propose lookup labels; it still chooses only returned descriptors (R-160).", by=S("R-160"))
amend("F09", S("DI-254"), "the revised clause", "Revised by R-161.", by=S("R-161"))

supersede("F10", S("DI-152"), S("R-168"))

# F11 and F39: settled by DN-042 (squiddy/docs/design/2026-10-04_DN-042_...): 'Supersedes: DN-039 R-169
# (reservation) and R-170 (cacheable prefix)'; SQ-009 built R-176 to R-181 (merge 7076eae).
DN042 = "squiddy/docs/design/2026-10-04_DN-042_spend_governor_reserve_bands_measured_estimates.md:3"
supersede("F11", S("R-169"), S("R-176"), extra_receipts=[f"{DN042} 'Supersedes: DN-039 R-169 (reservation)'", "probe F39 (R-169 duplicates DI-214): R-176 adopts DI-214's shared-ledger form"])
supersede("F11", S("R-170"), S("R-180"), extra_receipts=[f"{DN042} 'Supersedes: ... R-170 (cacheable prefix)'"])
amend("F11", S("R-171"), "its disposition", "Stands, unbuilt: it binds whenever a graph opens extraction and reads its grounding gate. R-172 does not defer it (R-172 records DN-039's two kit defects, the ceiling and the prefix, which DN-042 has since built); nothing supersedes it.", by=S("R-172"))
for fc in ("FC-11", "FC-12", "FC-13", "FC-14", "FC-15"):
    accept("F11", L(f"AD-032-{fc}"), extra_receipts=[f"{DN042} 'Status: accepted (operator decisions of 2026-10-03, recorded in ... FC-04 and FC-11 to FC-15)'", "seldon:AD-032-FC-04 (accepted, operator) 'Check: FC-11 to FC-15'", "squiddy merge 7076eae (SQ-009 built DN-042 R-176 to R-181)"])
amend("F39", S("DI-214"), "implementation", "Built by R-176 (DN-042, SQ-009): one machine-wide, flock-guarded spend ledger, reserve then settle; R-169, which restated this row, is superseded by R-176.", by=S("R-176"))

amend("F12", S("R-64"), "the judge clause", "The judge is pinned claude-fable-5-1 (R-109); the paste round was removed by ADDENDUM 07 (R-102).", by=S("R-109"))
amend("F12", S("R-64"), "the requirement class", "Applies to library only unless R-130 (all questions machine-generated from scope) is extended.", by=S("R-130"))
amend("F12", S("DI-188"), "'The judge is Gemini'", "The judge is pinned claude-fable-5-1 (R-109).", by=S("R-109"))
amend("F12", S("DI-185"), "the requirement class", "Applies to library only unless R-130 is extended.", by=S("R-130"))
supersede("F12", S("DI-204"), S("R-102"))

amend("F13", L("AD-030-R10"), "the pyproject.toml clause", "Superseded by AD-030-R17 (Squiddy is a build-time dependency pinned by commit in the governed graph, absent from pyproject.toml); R10's acyclicity and no-awareness clauses stand.", by=L("AD-030-R17"))

PUBLIC = "The public-only switch is one spec key, `visibility: public | private` (default public); recording refuses nothing and enforcement is at attachment and distribution (R-157, R-158)."
amend("F14", S("R-08"), "the public-only clause", PUBLIC, by=S("R-158"))
amend("F14", S("DI-080"), "the public-only policy", PUBLIC, by=S("R-158"))

# F15: the S-010 holds. R-113 released R-97's hold; M-002 merged green and named Arnold ready
# (squiddy 32aacb6, 'Arnold ready (DN-030 R-137 to R-141)'); KG-001 began S-010 (arnold 781e867).
HOLD_DONE = ("Discharged: M-002 merged green with Arnold named ready (squiddy 32aacb6, DN-030 R-137 to R-141) "
             "and S-010 began with KG-001 (arnold 781e867); the Arnold build has run KG-001 to KG-008 (arnold f31a4c3).")
F15R = ["squiddy merge 32aacb6 'Arnold ready (DN-030 R-137 to R-141)'", "arnold 781e867 'KG-001 A: arnold-evidence initialized'"]
amend("F15", S("R-97"), "the S-010 hold", "Released by R-113 ('the precedes hold from DN-022 R-97 is released by it'). The kill's scope (no library claims-graph extraction) stands.", by=S("R-113"))
amend("F15", S("R-107"), "'DN-022 R-97's hold on Arnold stays until R-109 resolves'", "Released by R-113.", by=S("R-113"))
amend("F15", S("R-124"), "the S-010 hold (waits on F-001)", HOLD_DONE, extra_receipts=F15R)
amend("F15", S("R-133"), "'S-010 waits on both'", HOLD_DONE, extra_receipts=F15R)
amend("F15", S("R-136"), "the readiness test", HOLD_DONE, extra_receipts=F15R)
amend("F15", S("R-141"), "'S-010 waits on M-002'", HOLD_DONE, extra_receipts=F15R)

# F16 (AD-033 section 5): DN-037 numbered at the seed (DN-037-R1 to R7); R-147 to R-166 marked under review.
for n in range(147, 167):
    amend("F16", S(f"R-{n}"), "whole record", "Under review per DN-037 (squiddy:DN-037-R7), binding until the review; no new intake rules until Arnold passes end to end (DN-037-R6).", by=S("DN-037-R7"), decided_by=DESKTOP, extra_receipts=[S5 + " F16"])

amend("F17", S("DI-132"), "'never a checkpoint for the operator'", "Inside the walls DI-132 holds; the candidate plan at the input wall is the operator's (R-102 'human at the walls'; R-127, R-154, R-155 touchpoint 3).", by=S("R-102"))

GAP = "Named exception: a model node's transport (the claude CLI) is not proxied and its hosts are unmeasured; DI-246 is the record of that gap until the CLI is proxied."
amend("F18", S("R-142"), "'real network for those hosts only'", GAP, by=S("DI-246"))
amend("F18", S("EX-REQ-15"), "'where undeclared, PROVEN ABSENT by a closed-network run'", GAP, by=S("DI-246"))

amend("F19", S("R-116"), "'the ONLY resume test the factory makes'", "The key is per unit and names the inputs that unit reads; DI-242 (acquire key without the kit version), R-166 (screen keyed on the excerpt) and DI-263 (verdicts adopted under an older key) are cases.", by=S("DI-242"))

CONTRACT = "The served contract is R-114's (hybrid search plus navigation verbs); question-driven verbs are a test of the contract, not its specification."
amend("F20", S("R-71"), "a verb for every path a written question walks", CONTRACT, by=S("R-114"))
amend("F20", S("DI-198"), "'A VERB FOR EVERY PATH A WRITTEN QUESTION WALKS'", CONTRACT, by=S("R-114"))
amend("F20", S("R-83"), "item 4 (the verb gate)", CONTRACT, by=S("R-114"))

amend("F21", A("ADR-017"), "scope", "Scoped to Arnold's served components at runtime; Squiddy's build-time model nodes (seed_select, seed_propose, shelf_screen) run outside it (AD-033 section 5).",
      changes={"scope_note": "Arnold's served components at runtime; Squiddy build-time model nodes are outside it (AD-033 section 5, probe F21)"},
      decided_by=DESKTOP, extra_receipts=[S5 + " F21"])

BAR = "Extraction is shown before commit when the extract valve is open; the preview is a recorded sidecar, not a wait (R-121)."
amend("F22", S("DI-135"), "'extraction shown for a nod before commit'", BAR, by=S("R-121"))
amend("F22", S("R-105"), "the acceptance bar's extraction clause", BAR, by=S("R-121"))

amend("F23", S("DI-235"), "'a Result read from the graph's Seldon event log'", "The demand-gate verdict moves into the graph's own register (R-126) and the valve reads that; AD-030-R10 stands (Squiddy has no knowledge of Seldon). The code change is a Squiddy task, not built.",
      decided_by=DESKTOP, extra_receipts=[S5 + " F23"])

amend("F24", S("DI-170"), "the title precedence", "The registration agency's title (Crossref, DataCite) is the title of record; an aggregator's (OpenAlex) display_name is a hint (R-139).", by=S("R-139"))

amend("F25", S("R-46"), "'every future harness use it'", "Restated by R-125: a register of exempt frozen instruments and to_fix loops; the extraction family keeps its daemon (F-001 B.3, EX-REQ-15, DI-236).", by=S("R-125"))
amend("F25", S("R-47"), "the check on calls outside the runner", "Restated by R-125 with the named exemption register (conformance item 26 `call_layer.exempt`).", by=S("R-125"))

amend("F26", S("DI-157"), "'the kit must not ship one'", "No central or federated control plane; the per-graph control file of R-117 is the kit's.", by=S("R-117"))

amend("F27", S("R-115"), "the DAG drawing", "Parse follows write (R-128's correction); the input block's label is `scope:` (R-129).", by=S("R-128"))

deprecate("F28", L("AD-023"), decided_by=DESKTOP, extra_receipts=[S5 + " F28, F44: 'AD-023 is deprecated (Wintermute mothballed 2026-09-10)'"])

amend("F29", S("R-33"), "the premise 'each attempt burns its tokens'", "H-007 measured the 12 restarts at zero tokens lost (EX-REQ-10); the requirement stands on the bound it buys.", by=S("EX-REQ-10"))

DOI = "The cited ChemRxiv 10.26434/chemrxiv.10001546 is recorded as nonexistent; the decision stands on Edge et al. 2024 and the internal measurements (DI-177, H-009)."
amend("F30", S("R-41"), "the prior-art citation", DOI)
amend("F30", S("DI-031"), "the source citation (methodology 6.1)", DOI)

supersede("F31", S("R-26"), S("R-28"))
supersede("F31", S("DI-181"), S("DI-182"))

supersede("F32", S("R-29"), S("R-32"), extra_receipts=["probe F32: R-32 'The control chart of R-29 is withdrawn'"])
supersede("F32", S("R-27"), S("R-81"), extra_receipts=["probe F32: the live cost gate is R-81's pilot multiple plus the ceiling"])
supersede("F32", S("DI-183"), S("R-81"), extra_receipts=["probe F32: DI-183 mirrors R-29 ('cost is gated today by the ceiling alone'); the live gate is R-81's pilot multiple plus the ceiling"])

amend("F33", S("R-89"), "the drop rule (share under 0.002)", "Retired: `tier0.claim_share_floor` gives way to a corpus budget (R-94, R-95); DI-228 records R-89 as a misreading of R-38.", by=S("R-94"))

DECON = "The decontextualization dimension was withdrawn (R-49) and the judge stopped as NOT VALIDATED, ranking nothing (R-60)."
amend("F34", S("EX-REQ-02"), "'instrument PENDING H-009 Part A'", DECON, by=S("R-60"))
amend("F34", S("R-44"), "the ranking clause (usable claims per million tokens)", DECON, by=S("R-60"))
amend("F34", S("R-43"), "the decontextualization dimension", "Withdrawn by R-49.", by=S("R-49"))
amend("F34", S("R-50"), "amended clauses", "Amended by R-56 to R-58; the chain is closed by R-60 and R-62.", by=S("R-56"))
amend("F34", S("R-51"), "amended clauses", "Amended by R-56 to R-58; the chain is closed by R-60 and R-62.", by=S("R-57"))

amend("F35", S("R-80"), "re-extraction of the 525 as the first spend (library)", "Superseded for library: no extraction is dispatched for the library claims graph (R-97); the extraction is complete (R-107).", by=S("R-107"))
amend("F35", S("R-81"), "the daemon runs arm C as its protocol (library)", "Superseded for library (R-97, R-107); R-81's cascade stands as the template for a graph whose extraction valve opens.", by=S("R-97"))

amend("F36", S("DI-176"), "the extraction unit", "Superseded by R-79 for the protocol (arm C on packs); the measurement stands.", by=S("R-79"))
amend("F36", S("DI-177"), "'the extraction unit stays the paragraph'", "Superseded by R-79 for the protocol (arm C on packs); the measurement stands.", by=S("R-79"))
amend("F36", S("DI-031"), "overlap in the standard", "R-41's packs omit overlap on purpose (an exception for the extraction protocol).", by=S("R-41"))

supersede("F37", S("R-31"), S("R-34"), extra_receipts=["probe F37: R-34 'R-31 closes there'"])

amend("F38", S("R-180"), "the check (cache reads on calls 2 to 5)", "Measured by SQ-009: 0 of 4 calls read the cache on the library's prefix, which is under the 1,024-token minimum cacheable length; the split saves nothing until a prefix of 1,024 tokens or more is shown to read (Result SQ009_r180_cache_read_calls = 0).",
      extra_receipts=["squiddy/docs/findings/2026-10-04_SQ-009_spend_governor.md section 5"])
amend("F38", S("DI-178"), "'prefix cache-read is an API feature R-11 forbids'", "Attribution corrected: R-11 governs credentials, not transports. Re-measured by SQ-009 on the pinned CLI: 0 of 4 cache reads on a sub-1,024-token prefix; prefix-granular reads on a longer prefix remain unmeasured.",
      extra_receipts=["squiddy/docs/findings/2026-10-04_SQ-009_spend_governor.md section 5"])

amend("F40", S("R-63"), "precedent", "R-63 restates R-17 T-1 and DI-034 (a gate is checked for reachability before it is registered); they are its precedent.", by=S("R-17"))
amend("F41", S("R-105"), "precedent", "R-105 extends R-10 (maintenance is scheduled stages with gates, never unbounded agents).", by=S("R-10"))

amend("F42", A("ADR-013"), "R2's wording 'microcycle = ~1 wk scheduling unit'", "Overridden by ADR-013 Addendum 01: cycle duration is data, not a 7-day convention.", by=A("ADR-013-A01"),
      extra_receipts=["arnold/docs/adr/013-addendum-01-cycle-duration-is-data.md:4 (Accepted, Brock, 2026-09-28)"])

amend("F43", S("R-127"), "the touchpoint 3 pause for maintenance admission", "The pick rule is an operator input set once in the spec; admit-one under that rule needs no pause (R-135, DI-241). First builds still pause (R-137).",
      decided_by=DESKTOP, extra_receipts=[S5 + " F43: 'Operator 2026-10-02: admission by written rule, stops only for disasters; Issue 45ca92d2'"])

amend("F44", L("AD-024"), "scope", "Scoped to Seldon and Wintermute; Squiddy does not adopt it (it forbids a central control plane, DI-157).",
      changes={"scope": ["seldon"], "scope_note": "Seldon and Wintermute only (AD-033 section 5, probe F44)"},
      decided_by=DESKTOP, extra_receipts=[S5 + " F28, F44: 'AD-024 is scoped to Seldon and Wintermute'"])

# F45: the week-template records that assume a 7-day week are scoped to strength training.
F45_TEXT = "Strength-only convention: cycle duration is data, not a 7-day grid (ADR-013 Addendum 01); endurance planning does not share it."


def f45_targets(u: dr.Universe) -> list[str]:
    out = []
    for rec in u.records("arnold").values():
        if rec.id.startswith("arnold:week-template-") and rec.status in dr.ACTIVE and \
                re.search(r"\b(week|weekday|Monday)\b", (rec.get("source") or {}).get("text", ""), re.I):
            out.append(rec.id)
    return sorted(out, key=dr._sort_key)


# ---------------------------------------------------------------------------
# applying
# ---------------------------------------------------------------------------

def findings() -> dict[str, dict]:
    return {x["finding"]: x for x in map(json.loads, CONFLICTS.open())}


def receipts_for(f: str, fx: dict) -> tuple[str, list[str]]:
    if f == M:
        return ("Probe DI mirror summary: wording drifted from its own R in meaning",
                ["squiddy/docs/findings/2026-10-03_operator_audit/probe/conflicts.md 'DI mirror summary'"])
    x = fx[f]
    reason = f"Probe {f} ({x['class']}): {x['disposition']}"
    rec = [f"probe {f}: {e['id']} ({e['where']}): \"{e['quote']}\"" for e in x.get("evidence", [])]
    return reason, rec


def run(dry: bool) -> list[dict]:
    u = dr.universe(SELDON, yaml.safe_load((SELDON / "seldon.yaml").read_text()))
    fx = findings()
    for t in f45_targets(u):
        amend("F45", t, "scope (the 7-day week)", F45_TEXT, by=A("ADR-013-A01"))
    rows = []
    for f, op, target, kw in EVENTS:
        reason, rec = receipts_for(f, fx)
        receipts = rec + kw.get("extra_receipts", [])
        tgt = u.get(target)
        if tgt is None:
            raise SystemExit(f"FATAL: {f} names {target}, which the register does not hold")
        row = {"finding": f, "op": op, "target": target, "by": kw.get("by"), "clause": kw.get("clause"),
               "decided_by": kw.get("decided_by", CC), "target_operator_stated": bool(tgt.get("operator_stated")),
               "target_operator_receipts": (tgt.get("receipts") or [])[:2] if tgt.get("operator_stated") else []}
        rows.append(row)
        if dry:
            continue
        common = dict(date=DATE, decided_by=row["decided_by"], reason=reason, receipts=receipts,
                      operator_stated=row["decided_by"] == "operator")
        if op == "amend":
            amendment = {"clause": kw["clause"], "text": kw["text"], "by": kw.get("by")}
            dr.amend(u, target, amendment=amendment, changes=kw.get("changes"), **common)
        elif op == "supersede":
            dr.transition(u, "supersede", target, superseded_by=kw["by"], **common)
        elif op in ("deprecate", "accept"):
            dr.transition(u, op, target, **common)
        elif op == "kind":
            dr.amend(u, target, changes={"kind": "decision", "statement": (tgt.get("source") or {})["text"],
                                         "mirrors": None},
                     amendment={"clause": "kind", "text": f"A drifted mirror becomes a decision of its own: {kw['why']}."},
                     **common)
    return rows


def mirror_pass(dry: bool) -> list[dict]:
    """A faithful mirror of a superseded R would still read as an active pointer to a dead
    decision: it is superseded by the R's live head's mirror where one exists, else by the head."""
    u = dr.universe(SELDON, yaml.safe_load((SELDON / "seldon.yaml").read_text()))
    recs = u.records("squiddy")
    mirrors_of: dict[str, list[str]] = {}
    for r in recs.values():
        if r.get("kind") == "mirror" and r.status in dr.ACTIVE:
            mirrors_of.setdefault(r.get("mirrors"), []).append(r.id)
    rows = []
    for target, ms in sorted(mirrors_of.items()):
        t = u.get(target)
        if t is None or t.status != "superseded":
            continue
        head = u.live_head(target)
        head_mirrors = [m for m in mirrors_of.get(head, [])]
        by = head_mirrors[0] if head_mirrors else head
        for m in ms:
            rows.append({"finding": "MIRROR-OF-SUPERSEDED", "op": "supersede", "target": m, "by": by,
                         "clause": None, "decided_by": CC, "target_operator_stated": bool(recs[m].get("operator_stated")),
                         "target_operator_receipts": []})
            if not dry:
                dr.transition(u, "supersede", m, superseded_by=by, date=DATE, decided_by=CC,
                              reason=(f"FC-16: {m} mirrors {target}, which is superseded by {t.superseded_by} "
                                      f"(live head {head}); the mirror follows its record"),
                              receipts=[f"register: {target} superseded_by {t.superseded_by}"])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rows = run(args.dry_run)
    rows += mirror_pass(args.dry_run)
    out = EVID / ("part_c_events_dryrun.json" if args.dry_run else "part_c_events.json")
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    covered = sorted({r["finding"] for r in rows if r["finding"].startswith("F")}, key=lambda s: int(s[1:]))
    print(f"{len(rows)} events; findings with an event: {len(covered)}; "
          f"missing: {[f for f in findings() if f not in covered]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
