"""SEL-002 Part E (AD-033-R8): stand-alone statements, written by one call and checked by another.

Runs in SQUIDDY'S environment (it imports the kit's call layer, model client and spend governor):

    cd /Users/brock/GitHub/squiddy
    .venv/bin/python ../seldon/scripts/sel002/statements.py pilot     # the first N records, measured
    .venv/bin/python ../seldon/scripts/sel002/statements.py run       # the rest, under a measured estimate
    .venv/bin/python ../seldon/scripts/sel002/statements.py report

Input: evidence/sel002/statements/units.jsonl (scripts/sel002/statements_export.py). Numbers:
scripts/sel002/statements.yaml. Output, beside the input: writer.jsonl and validator.jsonl (the call layer's
fsynced checkpoints, one row per finished call: the reply, the parsed result, the usage), pilot.json, run.json.

THE TWO CALLS ARE SEPARATE (R8). The writer sees the record's verbatim source and the rules; the validator sees
the verbatim source and the writer's statement, nothing else (not the writer's prompt, not the record id), and
answers whether the source entails the statement, whether anything of the decision was dropped, and whether the
statement stands alone. A record passes when all three hold.

CONSTITUTION SECTION 15, BY CONSTRUCTION. Unit keys are the call layer's (record id, sha256 of the source or of
source plus statement, the prompt template's sha256, model alias, transport), so a changed prompt or model is a new
key and a re-run of the same command resumes by skip; each finished call is fsynced before the next lands; progress
every 60 s or 10 units; the pilot measures before the bulk and the bulk's estimate is the pilot's measured rate;
the spend governor reserves before every call and refuses past +20% of the estimate; a failed call is a row,
retried once across runs. The SIGKILL test: scripts/sel002/statements_kill_test.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from squiddy import calls, model_client as mc, spend

HERE = Path(__file__).resolve().parent
EVID = HERE.parents[1] / "evidence" / "sel002" / "statements"
CONFIG = HERE / "statements.yaml"

WRITER_SYSTEM = """You write ONE stand-alone statement of a recorded decision, for a decision register.

Rules:
1. If the decision states behavior, use an EARS template (Mavin et al. 2009):
   ubiquitous "The <subject> shall <response>."; event-driven "When <trigger>, the <subject> shall <response>.";
   state-driven "While <state>, the <subject> shall <response>."; unwanted behavior "If <condition>, then the
   <subject> shall <response>."; optional feature "Where <feature>, the <subject> shall <response>."
   If the decision is a choice (a store, a name, a scope, a definition), write one declarative sentence instead.
2. Stand alone: name the subject explicitly. Never point at other text by position ("this", "above", "below",
   "the note", "the following", "the previous"). Do not start with the record's own id. Another record's id may
   appear only where the decision itself depends on it.
3. Keep every part of the decision: each rule, condition, exception, threshold and scope it states. Add nothing
   the source does not say. Leave out evidence, citations, history, rationale and examples.
4. Two or three sentences are allowed only when the decision has that many separate clauses.
5. If the source is a table row of an inherited decision (id | source | statement | tag), the decision is the
   statement column as its tag disposes it: carry the tag's adaptation, or its "does not apply", into the
   statement. Leave out the source column.

Reply with JSON only, no fence: {"statement": "<the statement>", "form": "ubiquitous|event|state|unwanted|optional|declarative"}"""

#: The record itself, the per-call user message. The instructions above are the system prompt: one cacheable prefix
#: for every call (DN-042 R-180's idea; here the CLI's own system prompt is already a cache entry of ~8k tokens, so the
#: combined prefix is far above the 1,024-token minimum that sank SQ-009's smoke run).
WRITER_USER = """Kind of record: <<KIND>>
Verbatim source:
<<<
<<SOURCE>>
>>>"""

VALIDATOR_SYSTEM = """You check a statement that was written from a recorded decision. You see the decision's verbatim source and the statement.

Answer three questions strictly:
1. entailed: is every claim in the statement supported by the source? (false if the statement adds anything)
2. complete: does the statement keep every part of the source's decision: each rule, condition, exception,
   threshold and scope? Evidence, citations, history, rationale and examples may be left out. For a table row of
   an inherited decision (id | source | statement | tag), the source column may be left out and the tag's
   disposition (its adaptation, or "does not apply") is part of the decision.
3. standalone: can the statement be read alone, without pointing at other text by position ("this", "above",
   "below", "the note", "the following")?

Reply with JSON only, no fence. `added` and `dropped`: at most three items each, each at most twelve words; empty
lists when nothing was added or dropped:
{"entailed": true|false, "complete": true|false, "standalone": true|false, "added": ["..."], "dropped": ["..."]}"""

VALIDATOR_USER = """Verbatim source:
<<<
<<SOURCE>>
>>>

Statement:
<<<
<<STATEMENT>>
>>>"""


def cfg() -> dict:
    c = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    need = ("writer", "validator", "transport", "policy", "pilot_records", "guess_output_tokens", "budget",
            "spacing_seconds")
    gaps = [k for k in need if k not in c]
    if gaps:
        raise SystemExit(f"FATAL: {CONFIG} is missing {gaps}; every key is required")
    return c


def units_in(evid: Path) -> list[dict]:
    return [json.loads(l) for l in (evid / "units.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def client_for(role: dict, tr: dict, mock_responder=None, system: str | None = None):
    if mock_responder is not None:
        return mc.MockClient(mock_responder, alias="mock")
    c = mc.ClaudeCLIClient(alias=role["alias"], timeout=int(role["timeout"]), max_turns=int(role["max_turns"]),
                           system_prompt=system,
                           minimal_scaffold=bool(tr["setting_sources_disabled"]),
                           no_nonessential_traffic=bool(tr["nonessential_traffic_disabled"]),
                           cli_path=tr.get("cli_path"), effort=role.get("effort"))
    got = c.cli_version()
    if tr.get("cli_version") and str(tr["cli_version"]) != got:
        raise SystemExit(f"FATAL: the pinned CLI reports {got}, the config declares {tr['cli_version']} (DN-006 R-30)")
    return c


def parse_json(content: str) -> dict:
    text = mc.strip_fence(content or "").strip()
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        raise ValueError(f"no JSON object in the reply: {text[:120]!r}")
    return json.loads(text[a:b + 1])


def writer_prompt(u: dict) -> str:
    return WRITER_USER.replace("<<KIND>>", str(u.get("kind"))).replace("<<SOURCE>>", u["source_text"])


def validator_prompt(u: dict, statement: str) -> str:
    return VALIDATOR_USER.replace("<<SOURCE>>", u["source_text"]).replace("<<STATEMENT>>", statement)


def profile_of(client) -> str:
    return client.spend_profile() if hasattr(client, "spend_profile") else "mock"


def node(role: str) -> str:
    """The spend governor's node for a role, versioned by its prompt template: spend.estimate prices a node from its
    own ledger history, so a changed prompt must be a new node or it would be priced on the old prompt's calls."""
    return f"sel002_{role}_{template_sha(role)[:8]}"


def template_sha(role: str) -> str:
    """The prompt's identity: system prompt and user template together."""
    return calls.sha256_text(WRITER_SYSTEM + "\n" + WRITER_USER if role == "writer" else
                             VALIDATOR_SYSTEM + "\n" + VALIDATOR_USER)


def pilot_sample(units: list[dict], n: int) -> list[dict]:
    """A stride over the export order (squiddy, seldon, arnold; each in id order), so the pilot spans the three
    registers and the range of source lengths rather than the first n rows of one table."""
    if n >= len(units):
        return list(units)
    step = len(units) / n
    return [units[int(i * step)] for i in range(n)]


def writer_units(units: list[dict], client, alias: str, control_sha: str) -> list[calls.Unit]:
    tpl = template_sha("writer")
    return [calls.Unit(key=calls.unit_key("sel002_writer", u["id"], u["source_sha256"], control_sha, role="writer",
                                          prompt_sha256=tpl, model=alias, transport=profile_of(client)),
                       item=u["id"], payload={"u": u}, weight=float(len(u["source_text"]))) for u in units]


def validator_units(units: list[dict], statements: dict[str, str], client, alias: str,
                    control_sha: str) -> list[calls.Unit]:
    tpl = template_sha("validator")
    out = []
    for u in units:
        st = statements.get(u["id"])
        if not st:
            continue
        out.append(calls.Unit(key=calls.unit_key("sel002_validator", u["id"],
                                                 calls.sha256_text(u["source_sha256"] + "\n" + st), control_sha,
                                                 role="validator", prompt_sha256=tpl, model=alias,
                                                 transport=profile_of(client)),
                              item=u["id"], payload={"u": u, "statement": st}))
    return out


def make_do(client, build_prompt, parse_retries: int, check):
    def do(unit: calls.Unit) -> dict:
        prompt = build_prompt(unit)
        last = None
        for attempt in range(1 + int(parse_retries)):
            inv = calls.invoke(client, prompt)
            usage = {k: inv.usage.get(k) for k in mc.USAGE_KEYS} if inv.usage else {}
            try:
                parsed = parse_json(inv.content)
                check(parsed)
                return {"status": "ok", "parsed": parsed, "reply": inv.content, "usage": usage,
                        "resolved_model": inv.resolved_model, "attempts": attempt + 1}
            except (ValueError, KeyError, TypeError) as exc:
                last = f"{type(exc).__name__}: {exc}"
        raise ValueError(f"unparseable reply after {1 + int(parse_retries)} attempt(s): {last}")
    return do


def check_writer(p: dict) -> None:
    if not isinstance(p.get("statement"), str) or not p["statement"].strip():
        raise ValueError("the writer's reply carries no statement")


def check_validator(p: dict) -> None:
    for k in ("entailed", "complete", "standalone"):
        if not isinstance(p.get(k), bool):
            raise ValueError(f"the validator's reply has no boolean {k}")


def policy_of(c: dict, pilot: bool = False) -> calls.Policy:
    p = c["policy"]
    return calls.Policy(in_flight=int(p["pilot_in_flight"] if pilot else p["in_flight"]), retry_attempts=int(p["retry_attempts"]),
                        retry_backoff_seconds=float(p["retry_backoff_seconds"]),
                        progress_every_seconds=float(p["progress_every_seconds"]),
                        progress_every_units=int(p["progress_every_units"]), pilot_units=0,
                        eta_window=int(p["eta_window"]), buckets=())


def statements_from(ck: calls.Checkpoint, units: list[calls.Unit]) -> dict[str, str]:
    out = {}
    for u in units:
        r = ck.completed(u.key)
        if r:
            out[u.item] = r["parsed"]["statement"].strip()
    return out


def guess(units: list[dict], prompt_of, c: dict) -> float:
    """A pilot's estimate with no measured basis: a GUESS, labelled one (constitution 15.4)."""
    s = spend.config()
    w = s["weights"]
    cpt = float(s["estimate"]["guess_chars_per_token"])
    tok = sum(len(prompt_of(u)) / cpt for u in units)
    return tok * float(w["cache_write"]) + len(units) * float(c["guess_output_tokens"]) * float(w["output"])


def job_spec(name: str, node: str, client, alias: str, n: int, token_cap: float, evid: Path, c: dict) -> dict:
    return {"job": name, "lane": "sel002_statements", "model": alias, "profile": profile_of(client), "node": node,
            "units": n, "token_cap": float(token_cap), "call_cap": n * (1 + int(c["policy"]["parse_retries"])),
            "approval_dir": str(evid), "spacing_seconds": c["spacing_seconds"]}


def pass_(role: str, units: list[calls.Unit], do, ck: calls.Checkpoint, spec: dict | None, pilot: bool,
          guessed: float, pol: calls.Policy) -> dict:
    if spec is None:                          # the mock path (kill test): no spend job
        return calls.run_units(f"sel002_{role}", units, do, ck, policy=pol)
    rec = spend.declare_or_pilot(spec, guessed) if pilot else spend.declare(spec)
    with spend.job(rec) as job:
        summary = calls.run_units(f"sel002_{role}", units, do, ck, policy=pol)
    end = [r for r in spend.Ledger().records() if r.get("record") == "job_end" and r["job"] == job["job"]][-1]
    return {"summary": summary, "job": job["job"], "estimate": end["estimate"], "actual": end["actual"],
            "ratio": end["ratio"], "by_class": end.get("by_class"), "basis": rec.get("basis")}


def run_phase(phase: str, evid: Path, mock=None) -> dict:
    c = cfg()
    units = units_in(evid)
    n_pilot = int(c["pilot_records"])
    chosen = pilot_sample(units, n_pilot) if phase == "pilot" else units
    wcl = client_for(c["writer"], c["transport"], mock, WRITER_SYSTEM)
    vcl = client_for(c["validator"], c["transport"], mock, VALIDATOR_SYSTEM)
    walias, valias = (c["writer"]["alias"], c["validator"]["alias"]) if mock is None else ("mock", "mock")
    control_sha = calls.sha256_obj({k: c[k] for k in ("writer", "validator", "transport")})
    pol = policy_of(c, pilot=(phase == "pilot" and mock is None))
    wck, vck = calls.Checkpoint(evid / "writer.jsonl"), calls.Checkpoint(evid / "validator.jsonl")
    wunits = writer_units(chosen, wcl, walias, control_sha)
    wdo = make_do(wcl, lambda u: writer_prompt(u.payload["u"]), c["policy"]["parse_retries"], check_writer)
    out: dict = {"phase": phase, "records": len(chosen)}
    if mock is not None:
        out["writer"] = pass_("writer", wunits, wdo, wck, None, False, 0, pol)
        st = statements_from(wck, wunits)
        vunits = validator_units(chosen, st, vcl, valias, control_sha)
        vdo = make_do(vcl, lambda u: validator_prompt(u.payload["u"], u.payload["statement"]),
                      c["policy"]["parse_retries"], check_validator)
        out["validator"] = pass_("validator", vunits, vdo, vck, None, False, 0, pol)
        return out
    todo_w = [u for u in wunits if not wck.completed(u.key)]
    if phase == "validate":
        # The validator pass alone: a writer job stopped at its ceiling (DN-042 R-178) stays stopped until the
        # operator's dated approval; the statements already written still get their separate check.
        out["writer"] = {"skipped": f"validator-only run; {len(todo_w)} writer unit(s) not run"}
    elif phase == "run":
        # THE ESTIMATE FOR THE REST, MEASURED ON THE PILOT (spend.estimate over the ledger's history for this node),
        # checked against the declared budget BEFORE any call of the bulk.
        ew = spend.estimate(walias, profile_of(wcl), node("writer"), max(1, len(todo_w)),
                            spacing_seconds=c["spacing_seconds"])
        ev = spend.estimate(valias, profile_of(vcl), node("validator"), max(1, len(todo_w)),
                            spacing_seconds=c["spacing_seconds"])
        if ew["estimate"] is None or ev["estimate"] is None:
            raise SystemExit("FATAL: no measured basis for the bulk; run `pilot` first")
        # EVERY pilot's spend counts against the budget, not only the last one's (stricter than the first draft of
        # this check; the earlier pilots' files are kept as pilot_v*.json).
        spent = 0.0
        for pf in sorted(evid.glob("pilot*.json")) + sorted(evid.glob("run_*.json")):   # pilots and earlier runs
            pj = json.loads(pf.read_text())
            spent += sum(float(pj[r]["actual"]) for r in ("writer", "validator") if "actual" in (pj.get(r) or {}))
        projected = spent + float(ew["estimate"]) + float(ev["estimate"])
        cap = float(c["budget"]["declared_weighted_tokens"]) * (1 + float(c["budget"]["band_stop"]))
        out["projection"] = {"spent_before_this_run": spent, "writer_estimate": ew["estimate"],
                             "validator_estimate": ev["estimate"], "projected_total": round(projected, 1),
                             "declared_budget": c["budget"]["declared_weighted_tokens"], "stop_line": cap,
                             "writer_basis": ew["basis"], "validator_basis": ev["basis"]}
        print(json.dumps(out["projection"], indent=1))
        if projected > cap:
            (evid / "run_refused.json").write_text(json.dumps(out, indent=1))
            raise SystemExit(f"STOP: the pilot-measured projection {projected:,.0f} passes the declared budget's stop "
                             f"line {cap:,.0f}; spend above the declared cap waits for the operator")
        # The job id names the pending set: a re-run of the same pending units resumes under the same job, a later
        # run over a different set (retries, new records) is a new job (the governor refuses a changed spec).
        wset = calls.sha256_text("\n".join(sorted(u.key for u in todo_w)))[:10]
        wspec = job_spec(f"sel002_writer:run:{control_sha[:12]}:{node('writer')}:{wset}", node("writer"), wcl, walias, max(1, len(todo_w)),
                         1.25 * float(ew["estimate"]), evid, c)
        out["writer"] = pass_("writer", wunits, wdo, wck, wspec, False, 0, pol) if todo_w else {"skipped": "all done"}
    else:
        g = guess(chosen, writer_prompt, c)
        wspec = job_spec(f"sel002_writer:pilot:{control_sha[:12]}:{node('writer')}", node("writer"), wcl, walias, len(chosen),
                         10 * g, evid, c)
        out["writer"] = pass_("writer", wunits, wdo, wck, wspec, True, g, pol)
    st = statements_from(wck, wunits)
    vunits = validator_units(chosen, st, vcl, valias, control_sha)
    vdo = make_do(vcl, lambda u: validator_prompt(u.payload["u"], u.payload["statement"]),
                  c["policy"]["parse_retries"], check_validator)
    todo_v = [u for u in vunits if not vck.completed(u.key)]
    if phase in ("run", "validate"):
        ev2 = spend.estimate(valias, profile_of(vcl), node("validator"), max(1, len(todo_v)),
                             spacing_seconds=c["spacing_seconds"])
        vset = calls.sha256_text("\n".join(sorted(u.key for u in todo_v)))[:10]
        vspec = job_spec(f"sel002_validator:run:{control_sha[:12]}:{node('validator')}:{vset}", node("validator"), vcl, valias,
                         max(1, len(todo_v)), 1.25 * float(ev2["estimate"]), evid, c)
        out["validator"] = pass_("validator", vunits, vdo, vck, vspec, False, 0, pol) if todo_v else {"skipped": "all done"}
    else:
        g = guess([u.payload["u"] | {"_st": u.payload["statement"]} for u in vunits],
                  lambda x: validator_prompt(x, x["_st"]), c)
        vspec = job_spec(f"sel002_validator:pilot:{control_sha[:12]}:{node('validator')}", node("validator"), vcl, valias,
                         len(vunits), 10 * g, evid, c)
        out["validator"] = pass_("validator", vunits, vdo, vck, vspec, True, g, pol)
    (evid / f"{phase}.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


def report(evid: Path) -> dict:
    c = cfg()
    units = units_in(evid)
    control_sha = calls.sha256_obj({k: c[k] for k in ("writer", "validator", "transport")})

    # The keys are built exactly as the run built them: from the configured clients' transport profiles (the CLI is
    # probed for its version, no model is called). Rows under older prompts or profiles are kept in the checkpoints as
    # history and match no current key.
    wcl = client_for(c["writer"], c["transport"], None, WRITER_SYSTEM)
    vcl = client_for(c["validator"], c["transport"], None, VALIDATOR_SYSTEM)
    wck, vck = calls.Checkpoint(evid / "writer.jsonl"), calls.Checkpoint(evid / "validator.jsonl")
    wunits = writer_units(units, wcl, c["writer"]["alias"], control_sha)
    st = statements_from(wck, wunits)
    vunits = validator_units(units, st, vcl, c["validator"]["alias"], control_sha)
    verdicts = {}
    for u in vunits:
        r = vck.completed(u.key)
        if r:
            p = r["parsed"]
            verdicts[u.item] = {"passed": bool(p["entailed"] and p["complete"] and p["standalone"]), **p}
    rows = []
    for u in units:
        v = verdicts.get(u["id"])
        rows.append({"id": u["id"], "statement": st.get(u["id"]), "verdict": v,
                     "check": ("passed" if v and v["passed"] else "failed")})
    (evid / "outcome.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    by_repo: dict = {}
    for r in rows:
        repo = r["id"].split(":")[0]
        b = by_repo.setdefault(repo, {"records": 0, "passed": 0, "failed": 0, "no_statement": 0, "no_verdict": 0})
        b["records"] += 1
        b[r["check"]] += 1
        if not r["statement"]:
            b["no_statement"] += 1
        elif not r["verdict"]:
            b["no_verdict"] += 1
    total = len(rows)
    passed = sum(1 for r in rows if r["check"] == "passed")
    rep = {"records": total, "passed": passed, "pass_rate": round(passed / total, 4) if total else None,
           "by_repo": by_repo}
    print(json.dumps(rep, indent=1))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=["pilot", "run", "validate", "report"])
    ap.add_argument("--evid", default=str(EVID))
    ap.add_argument("--mock", action="store_true", help="the kill test's offline client (no spend, no network)")
    a = ap.parse_args(argv)
    evid = Path(a.evid)
    if a.phase == "report":
        report(evid)
        return 0
    mock = None
    if a.mock:
        import time

        delay = float(os.environ.get("SEL002_MOCK_DELAY", "0.2"))
        log = evid / "mock_calls.log"

        def responder(prompt: str):
            time.sleep(delay)
            with open(log, "a") as fh:
                fh.write(calls.sha256_text(prompt) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            if "Statement:\n<<<" in prompt:
                return '{"entailed": true, "complete": true, "standalone": true, "added": [], "dropped": []}'
            src = prompt.split("Verbatim source:\n<<<\n", 1)[1].rsplit("\n>>>", 1)[0]
            return json.dumps({"statement": "The kit shall " + src[:40].replace('"', "'"), "form": "ubiquitous"})
        mock = responder
    out = run_phase(a.phase, evid, mock)
    print(json.dumps({k: v for k, v in out.items() if k != "projection"}, indent=1, default=str)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
