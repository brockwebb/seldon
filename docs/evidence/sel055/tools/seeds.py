"""SEL-055 Part B: five seeded breaking changes per repository, and whether the selected gate catches each.

Protocol (written before any run; deviations go in docs/evidence/sel055/README.md):
  For each seed: in a scratch checkout of the base (seldon: this branch's HEAD; hazbrief: its main), on a new branch,
  1. run the seed's named READER test file on the unseeded base: it must pass (else the seed is void, not a result);
  2. apply the seed, commit it;
  3. run the READER again: it must fail (the seed is a break the full suite catches, since the full suite contains the
     reader);
  4. plan the gate with the declaration under test (`--decl`), against the base;
  5. if the plan is scoped, run the scoped gate (the declaration's test_command and commands): CAUGHT if red, MISS if
     green; if the plan is full, CAUGHT (full) by step 3.
Writes /tmp/sel055/seeds_<repo>_<decl>.json and prints one line per seed.

Usage: python seeds.py <seldon|hazbrief> <decl-tag> <decl-yaml-path>
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO, TAG, DECL = sys.argv[1], sys.argv[2], Path(sys.argv[3])
WTSRC = Path("/Users/brock/GitHub/seldon/.claude/worktrees/ethereal-enchanting-valiant")
sys.path.insert(0, str(WTSRC))
from seldon.core import gate_plan as GP  # noqa: E402

PRIMARY = {"seldon": Path("/Users/brock/GitHub/seldon"), "hazbrief": Path("/Users/brock/GitHub/hazbrief-mcp")}[REPO]
CLONE = {"seldon": Path("/tmp/sel055/clone/seldon"), "hazbrief": Path("/tmp/sel055/hzclone/hazbrief-mcp")}[REPO]
SCRATCH = Path(f"/tmp/sel055/clone/seed_{REPO}")   # beside the symlinked siblings, so ../squiddy resolves
HZPY = "/tmp/hb230/root/hazbrief-mcp/.venv/bin/python"
HZBIN = "/tmp/hb230/root/hazbrief-mcp/.venv/bin"


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {args} in {cwd}: {r.stderr}")
    return r.stdout.strip()


def sub(rel, old, new, count=1):
    def f(wt):
        p = wt / rel
        t = p.read_text(encoding="utf-8")
        assert old in t, (rel, old)
        p.write_text(t.replace(old, new, count), encoding="utf-8")
    return f


def drop_lines(rel, needle, keep_first=False):
    def f(wt):
        p = wt / rel
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        out = [ln for ln in lines if needle not in ln]
        assert len(out) < len(lines), (rel, needle)
        p.write_text("".join(out), encoding="utf-8")
    return f


def hz_unheld_issue(wt):
    text = (wt / "tests/test_hb170_cited_sources_held.py").read_text()
    m = re.search(r'^UNHELD\s*=\s*(.+)$', text, re.M)
    return m.group(1) if m else None


SEEDS = {
    "seldon": [
        {"id": "S1", "kind": "task file (cc_tasks)", "reader": "tests/test_criteria_marked.py",
         "edit": drop_lines("cc_tasks/2026-10-11_QC-001_ad037_receipts_records_judge_calibration_mechanism_filing.md",
                            "`check: grep -c FILED`"),
         "what": "one `check:` criterion removed from QC-001's task file"},
        {"id": "S2", "kind": "evidence data (docs)", "reader": "tests/test_qc_chart.py",
         "edit": sub("docs/evidence/qc002/cpi_first_reading.yaml", "actual: 10990000", "actual: 10000000"),
         "what": "one measured actual changed in docs/evidence/qc002/cpi_first_reading.yaml (SQ-010's ratio moves)"},
        {"id": "S3", "kind": "task file header (cc_tasks)", "reader": "tests/test_dispatch_concurrency.py",
         "edit": sub("cc_tasks/2026-10-07_SEL-004_worktree_per_task_dispatch.md", "\n**", "\n**Exclusive:** yes\n**"),
         "what": "SEL-004's task file gains an `**Exclusive:** yes` header"},
        {"id": "S4", "kind": "convention document (docs)", "reader": "tests/test_result_grammar.py",
         "edit": sub("docs/conventions/result_units_vocabulary.md", "RESULT_NAME_PATTERN", "RESULT_NAME_RULE", 99),
         "what": "the result-units convention stops naming RESULT_NAME_PATTERN"},
        {"id": "S5", "kind": "package code (seldon/)", "reader": "tests/test_sel041_gate_plan.py",
         "edit": sub("seldon/core/gate_plan.py", 'out.append("(?:.*/)?")', 'out.append("(?:.*/)")'),
         "what": "the planner's `**/` glob stops matching zero directories"},
    ],
    "hazbrief": [
        {"id": "H1", "kind": "event store (seldon_events.jsonl)", "reader": "tests/test_hb170_cited_sources_held.py",
         "edit": None, "what": "the event store loses every line naming the first unheld work's Issue"},
        {"id": "H2", "kind": "task addendum (cc_tasks)", "reader": "tests/test_hb115_serve_review.py",
         "edit": None, "what": "HB-115 ADDENDUM 01 loses the review question the test quotes from it"},
        {"id": "H3", "kind": "task file (cc_tasks)", "reader": "tests/test_hb212_status_words.py",
         "edit": None, "what": "HB-212's task file loses the quotations the benchmark record cites"},
        {"id": "H4", "kind": "declared script (scripts/gate_ledger.py)", "reader": "tests/test_gate_ledger.py",
         "edit": None, "what": "scripts/gate_ledger.py's upper bound defaults to 90% confidence, not the declared 95%"},
        {"id": "H5", "kind": "package code (src/)", "reader": "tests/test_geo.py", "edit": None,
         "what": "src/hazbrief/geo.py adds a polygon's holes to its area instead of subtracting them"},
    ],
}


def hz_edits(wt):
    """hazbrief's seeds are computed from its files (so the protocol names the mechanism, not a guessed string)."""
    out = {}
    # H1: the unheld list's first issue id, every event-store line that names it removed.
    # The test reads REPO / "docs" / "evidence" / "hb170" / "unheld_sources.yaml" (its EVID and UNHELD).
    unheld_path = wt / "docs/evidence/hb170/unheld_sources.yaml"
    issue = yaml.safe_load(unheld_path.read_text())["unheld"][0]["issue"]
    out["H1"] = drop_lines("seldon_events.jsonl", issue)
    # H2: the question the test quotes, removed from the addendum.
    add01 = next((wt / "cc_tasks").glob("2026-11-04_HB-115_*_ADDENDUM_01_*.md"))
    t115 = (wt / "tests/test_hb115_serve_review.py").read_text()
    out["H2"] = ("addendum", add01)
    # H3: HB-212's task file truncated to its header (the quotations are in its body).
    out["H3"] = ("truncate", wt / "cc_tasks/2026-11-20_HB-212_benchmark_status_by_significance.md")
    # H4: the bound's confidence (the first two seeds of this kind broke nothing: VOID, in the README).
    out["H4"] = sub("scripts/gate_ledger.py", "conf: float = CONFIDENCE", "conf: float = 0.90")
    # H5: holes added, not subtracted (an unclosed ring in geometry.py broke nothing: VOID, in the README).
    out["H5"] = sub("src/hazbrief/geo.py", "_ring_area(p.exterior.coords) - sum(", "_ring_area(p.exterior.coords) + sum(")
    return out, t115


def apply_hz(seed, wt, edits):
    e = edits[seed["id"]]
    if callable(e):
        e(wt)
        return
    kind, path = e
    if kind == "addendum":
        text = path.read_text()
        qs = re.findall(r'"([^"\n]{20,})"', text)
        assert qs, "no quoted question in the addendum"
        for q in qs:
            text = text.replace(f'"{q}"', '"(removed)"')
        path.write_text(text)
    elif kind == "truncate":
        lines = path.read_text().splitlines(keepends=True)
        path.write_text("".join(lines[:12]))
    elif kind == "first_return":
        text = path.read_text()
        m = re.search(r"^(\s+)return (?!None)(.+)$", text, re.M)
        path.write_text(text[:m.start()] + f"{m.group(1)}return None" + text[m.end():])
    elif kind == "src_constant":
        f = sorted(path.rglob("*.py"))[0]
        f.write_text(f.read_text() + "\nSEL055_SEED = 1\n")


def run_reader(wt, reader):
    env = {**os.environ}
    if REPO == "seldon":
        cmd = [sys.executable, "-m", "dotenv", "-f", str(PRIMARY / ".env"), "run", "--", sys.executable, "-m",
               "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "-x", reader]
        env.update({"PYTHONPATH": str(wt), "SELDON_PRIMARY_CHECKOUT": str(PRIMARY)})
    else:
        cmd = [HZPY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "-m", "not slow", reader]
        env.update({"PYTHONPATH": str(wt / "src")})
    t0 = time.monotonic()
    r = subprocess.run(cmd, cwd=wt, env=env, capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]
    return {"rc": r.returncode, "seconds": round(time.monotonic() - t0, 1), "tail": tail[0][-200:]}


def gcfg_for(decl_text):
    doc = yaml.safe_load(decl_text)["dispatch"]
    g = GP.load_gate_config(doc.get("gate"), doc.get("gate_command"))
    if REPO == "hazbrief":
        # Deviation (README): the scratch tree has no `uv` environment; the same pytest arguments run on HB-230's
        # scratch venv (python 3.11, the same lock), with the tree's src first on PYTHONPATH. ruff from that venv.
        g["test_command"] = g["test_command"].replace("uv run pytest", f"{HZPY} -m pytest")
        for s in g["slices"]:
            s["commands"] = [c.replace("uv run ruff", f"{HZBIN}/ruff") for c in s["commands"]]
    return g, doc.get("gate_command")


def main():
    base = git(CLONE, "rev-parse", "HEAD") if REPO == "hazbrief" else git(WTSRC, "rev-parse", "HEAD")
    if REPO == "seldon":
        git(CLONE, "fetch", "-q", str(WTSRC), base)
    if not SCRATCH.exists():
        git(CLONE, "worktree", "add", "-q", "--detach", str(SCRATCH), base)
    gcfg, gate_command = gcfg_for(DECL.read_text())
    results = []
    only = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else None
    for seed in [s for s in SEEDS[REPO] if only is None or s["id"] in only]:
        git(SCRATCH, "checkout", "-q", "--force", "--detach", base)
        git(SCRATCH, "clean", "-qfd")
        row = {"id": seed["id"], "kind": seed["kind"], "what": seed["what"], "reader": seed["reader"]}
        if seed["reader"]:
            row["reader_before"] = run_reader(SCRATCH, seed["reader"])
            if row["reader_before"]["rc"] != 0:
                row["verdict"] = "VOID: the reader fails on the unseeded base"
                results.append(row)
                print(seed["id"], row["verdict"], row["reader_before"]["tail"])
                continue
        if REPO == "seldon":
            seed["edit"](SCRATCH)
        else:
            edits, _ = hz_edits(SCRATCH)
            apply_hz(seed, SCRATCH, edits)
        git(SCRATCH, "add", "-A")
        git(SCRATCH, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", f"SEL-055 seed {seed['id']}")
        if seed["reader"]:
            row["reader_after"] = run_reader(SCRATCH, seed["reader"])
            if row["reader_after"]["rc"] == 0:
                row["verdict"] = "VOID: the reader passes with the seed (not a break)"
                results.append(row)
                print(seed["id"], row["verdict"])
                continue
        p = GP.plan(SCRATCH, gcfg, base=base, gate_command=gate_command, events=[])
        row.update({"changed": p["changed"], "tier": p["tier"], "reason": p["reason"], "selected": p["tests"],
                    "commands": p["commands"], "reader_selected": seed["reader"] in p["tests"]})
        if p["tier"] == "full":
            row["verdict"] = "CAUGHT (full)" if seed["reader"] else "CAUGHT (full; no reader run: plan is full)"
        elif REPO == "hazbrief" and row["reader_selected"]:
            # Deviation (README): under load 130 to 160 one hazbrief scoped gate of the records slice (39 files) ran at
            # about 1% a minute. A selection that holds the reader, which fails alone with the seed (step 3), is red:
            # the scoped gate is not run to its end for such a seed.
            row["verdict"] = "CAUGHT (scoped: the failing reader is selected)"
        else:
            log = Path(f"/tmp/sel055/seedlogs/{REPO}_{TAG}_{seed['id']}.log")
            log.parent.mkdir(parents=True, exist_ok=True)
            res = GP.run(SCRATCH, p, gcfg, gate_command=gate_command, timeout_s=7200, log_path=log, primary=PRIMARY)
            row["scoped_gate"] = {k: res[k] for k in ("outcome", "seconds", "tests_run", "failed_files")}
            row["verdict"] = "CAUGHT (scoped)" if not res["ok"] else "MISS"
        results.append(row)
        print(seed["id"], row["tier"], row["verdict"], row.get("scoped_gate", {}).get("seconds"),
              f"selected={len(row['selected'])}", f"reader_selected={row['reader_selected']}", flush=True)
    git(SCRATCH, "checkout", "-q", "--force", "--detach", base)
    Path(f"/tmp/sel055/seeds_{REPO}_{TAG}.json").write_text(json.dumps(results, indent=1))


main()
