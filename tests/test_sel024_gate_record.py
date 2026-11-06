"""SEL-024: the merge gate requires the project's declared pass record for the tip it merges, and "environmental" is
not green (AD-034 ADDENDUM 08, AD-034-R16 to R18).

`cc_tasks/2026-11-03_SEL-024_the_merge_gate_requires_the_projects_declared_pass_record_for_the_tip_it_merges.md` and its
ADDENDUM 01. squiddy merged four tasks and then SQ-101 at `67cde2da` with no kit pass record; SQ-101's RESULT called 17
failures worktree-environmental and ran no lint because ruff was not installed. The merge round now reads the
project's ledger (`dispatch.gate_record`) for the tip's tree, runs the declared command in the worktree when no line
covers it, and refuses `pass_unrecorded`; a gate that cannot run is `gate_unrunnable`, a block with a huddle naming the
tool, never a pass. The command never runs under the pass's filing lock (ADDENDUM 01 section 1).

Fixtures run against a scratch ledger: a JSONL file a stub recorder appends `{"payload": {"commit", "passed"}}` to,
the shape of squiddy's `kit/ledger/passes.jsonl`. Driven end to end through `seldon dispatch once` with the stub CLI
of `tests/dispatch_scaffold.py`.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
import yaml

from seldon.commands import dispatch_worktree as W
from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core import filing as F
from seldon.core import gate_record as GR
from seldon.core import stations as Q
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import NEO4J_DB, RESEARCH_YAML, add_task, git, make_project, register, run_cli, write_stub

LEDGER = "ledger/passes.jsonl"

RECORDER = textwrap.dedent('''\
    """A stand-in for a project's record-pass: judges HEAD and appends one ledger line."""
    import argparse, json, subprocess, time
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome", choices=["pass", "fail", "none"], default="pass")
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--mark", default=None)
    a = ap.parse_args()
    if a.mark:
        Path(a.mark).write_text("started\\n")
    time.sleep(a.sleep)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    if a.outcome != "none":
        led = Path("ledger/passes.jsonl")
        led.parent.mkdir(parents=True, exist_ok=True)
        with led.open("a") as fh:
            fh.write(json.dumps({"type": "pass_recorded", "payload": {"commit": head,
                                                                      "passed": a.outcome == "pass"}}) + "\\n")
    if a.mark:
        Path(a.mark).write_text("ended\\n")
    raise SystemExit(0 if a.outcome == "pass" else 1)
    ''')


def _recorder(tmp_path: Path, *args: str) -> str:
    script = tmp_path / "recorder.py"
    script.write_text(RECORDER, encoding="utf-8")
    return " ".join(shlex.quote(x) for x in (sys.executable, str(script), *args))


def _decl(command: str, **extra) -> dict:
    return {"command": command, "ledger": LEDGER, "commit_field": "payload.commit", "pass_field": "payload.passed",
            "timeout_s": 120, **extra}


# ══════════════════════════════════════════════════════════════════════════════
# The declaration (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

def test_absent_or_none_asks_for_no_record():
    assert GR.parse(None) is None
    assert GR.parse("none") is None


@pytest.mark.parametrize("bad, match", [
    ("yes", "mapping"),
    ({"command": "x"}, "missing"),
    ({**_decl("x"), "ledger": "/abs.jsonl"}, "repository-relative"),
    ({**_decl("x"), "timeout_s": 0}, "positive"),
    ({**_decl("x"), "requires": "ruff"}, "requires"),
    ({**_decl("x"), "unrunnable_exits": [0]}, "unrunnable_exits"),
    ({**_decl("x"), "colour": "red"}, "unknown"),
])
def test_a_malformed_declaration_refuses_at_load(tmp_path, bad, match):
    with pytest.raises(GR.GateRecordError, match=match):
        GR.parse(bad)
    p = make_project(tmp_path, dispatch_extra={"gate_record": bad})
    with pytest.raises(D.DispatchConfigError, match=match):
        D.load_dispatch_config(p)


def test_a_declaration_loads_and_parses_again_unchanged(tmp_path):
    p = make_project(tmp_path, dispatch_extra={"gate_record": _decl("python -m kit record-pass",
                                                                    requires=["ruff"])})
    cfg = D.load_dispatch_config(p)
    assert cfg["gate_record"]["requires"] == ["ruff"] and cfg["gate_record"]["unrunnable_exits"] == []
    assert GR.parse(cfg["gate_record"]) == cfg["gate_record"]


# ══════════════════════════════════════════════════════════════════════════════
# The ledger read: a record for the exact tip (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

def _repo(tmp_path: Path) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / ".gitattributes").write_text("events.jsonl merge=union\n")
    (r / "code.py").write_text("x = 1\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "code")
    return r


def _append_line(r: Path, commit: str, passed: bool) -> str:
    (r / "ledger").mkdir(exist_ok=True)
    with (r / LEDGER).open("a") as fh:
        fh.write(json.dumps({"payload": {"commit": commit, "passed": passed}}) + "\n")
    git(r, "add", LEDGER)
    git(r, "commit", "-q", "-m", "record")
    return git(r, "rev-parse", "HEAD").stdout.strip()


def _commit(r: Path, rel: str, text: str) -> str:
    with (r / rel).open("a") as fh:
        fh.write(text)
    git(r, "add", rel)
    git(r, "commit", "-q", "-m", rel)
    return git(r, "rev-parse", "HEAD").stdout.strip()


def _hk(r):
    return lambda paths: set(W.WT.union_files(r, paths))


def test_a_pass_line_covers_the_commit_it_names_and_the_ledger_commit_on_top(tmp_path):
    r = _repo(tmp_path)
    code = git(r, "rev-parse", "HEAD").stdout.strip()
    decl = _decl("x")
    assert GR.coverage(r, code, decl, _hk(r)) == {"covered": False, "tip": code, "recorded": None, "lines": 0,
                                                  "reason": "no_line"}
    tip = _append_line(r, code, True)
    cov = GR.coverage(r, tip, decl, _hk(r))
    assert cov["covered"] and cov["recorded"] == code, cov
    # housekeeping after the record (a merge=union file) keeps the tree identity
    tip2 = _commit(r, "events.jsonl", '{"event_id": "e1"}\n')
    assert GR.coverage(r, tip2, decl, _hk(r))["covered"]


def test_a_code_change_after_the_record_is_a_tree_nobody_recorded(tmp_path):
    r = _repo(tmp_path)
    code = git(r, "rev-parse", "HEAD").stdout.strip()
    _append_line(r, code, True)
    tip = _commit(r, "code.py", "y = 2\n")
    cov = GR.coverage(r, tip, _decl("x"), _hk(r))
    assert cov["covered"] is False and cov["reason"] == "no_line", cov


def test_declared_tree_paths_scope_what_a_pass_covers(tmp_path):
    """squiddy's rule (kitpass.pass_for): a later commit that left the kit package unchanged is covered."""
    r = _repo(tmp_path)
    (r / "pkg").mkdir()
    code = _commit(r, "pkg/m.py", "k = 1\n")
    _append_line(r, code, True)
    tip = _commit(r, "notes.md", "a filed task file\n")
    scoped = GR.parse(_decl("x", tree_paths=["pkg"]))
    assert GR.coverage(r, tip, scoped, _hk(r))["covered"], "outside the declared paths"
    assert not GR.coverage(r, tip, GR.parse(_decl("x")), _hk(r))["covered"], "the default is the whole tree"
    tip = _commit(r, "pkg/m.py", "k = 2\n")
    assert GR.coverage(r, tip, scoped, _hk(r))["reason"] == "no_line", "inside them"


def test_a_newer_fail_for_the_same_tree_is_not_a_pass(tmp_path):
    r = _repo(tmp_path)
    code = git(r, "rev-parse", "HEAD").stdout.strip()
    _append_line(r, code, True)
    tip = _append_line(r, code, False)
    cov = GR.coverage(r, tip, _decl("x"), _hk(r))
    assert cov["covered"] is False and cov["reason"] == "recorded_fail", cov


def test_a_line_naming_an_unknown_commit_covers_nothing(tmp_path):
    r = _repo(tmp_path)
    tip = _append_line(r, "0" * 40, True)
    assert GR.coverage(r, tip, _decl("x"), _hk(r))["reason"] == "no_line"


# ══════════════════════════════════════════════════════════════════════════════
# Part B: "environmental" is a refusal (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

def _no_ruff_env() -> dict:
    path = f"{Path(sys.executable).parent}:/usr/bin:/bin"
    import shutil
    if shutil.which("ruff", path=path):
        pytest.skip("ruff is installed on the minimal PATH; the fixture needs it absent")
    return {**os.environ, "PATH": path}


def test_a_gate_with_ruff_absent_is_unrunnable_and_names_it(tmp_path):
    env = _no_ruff_env()
    row = GR.run(tmp_path, GR.parse(_decl("ruff check .", requires=["ruff"])), env=env)
    assert row["outcome"] == "unrunnable" and row["missing"] == ["ruff"], row
    # undeclared, the shell's not-found still reads as unrunnable, never fail and never pass
    row = GR.run(tmp_path, GR.parse(_decl("ruff check .")), env=env)
    assert row["outcome"] == "unrunnable" and row["exit"] == 127 and row["missing"] == ["ruff"], row


def test_a_missing_module_and_a_declared_exit_are_unrunnable(tmp_path):
    row = GR.run(tmp_path, GR.parse(_decl(f"{shlex.quote(sys.executable)} -m sel024_no_such_kit record-pass")))
    assert row["outcome"] == "unrunnable" and row["missing"] == ["sel024_no_such_kit"], row
    row = GR.run(tmp_path, GR.parse(_decl(f"{shlex.quote(sys.executable)} -c 'raise SystemExit(5)'", unrunnable_exits=[5])))
    assert row["outcome"] == "unrunnable", row
    row = GR.run(tmp_path, GR.parse(_decl(f"{shlex.quote(sys.executable)} -c 'raise SystemExit(1)'")))
    assert row["outcome"] == "fail", "a gate that ran and failed is a fail, not unrunnable"


# ══════════════════════════════════════════════════════════════════════════════
# A and B in a dispatched project (Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _payloads(p, kind):
    return [e["payload"] for e in read_events(p) if e["event_type"] == kind]


def _state(neo4j_driver, task_id):
    with neo4j_driver.session(database=NEO4J_DB) as s:
        return s.run("MATCH (t:ResearchTask {artifact_id: $i}) RETURN t.state AS s", i=task_id).single()["s"]


def _once(p):
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    return res.output


def _session(p, neo4j_driver, dc, stem):
    add_task(p, stem)
    tid = register(p, neo4j_driver, dc, stem, "2026-11-06T00:00:00Z")
    write_stub(p, {stem: {"write": {"out/a.txt": "a\n"}, "worktree_name": stem}})
    return tid


@pytest.mark.usefixtures("neo4j_available")
def test_fixture_a_tip_with_a_record_merges(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path, dispatch_extra={"gate_record": _decl(_recorder(tmp_path, "--outcome", "pass"))})
    tid = _session(p, neo4j_driver, dc, "sel024_recorded")
    out = _once(p)
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merged", (fin, out)
    rec = fin["merge"]["gate_record"]
    assert rec["ran"] is True and rec["coverage"]["covered"] and rec["gate"]["outcome"] == "pass", rec
    assert _state(neo4j_driver, tid) == "completed"
    # main carries the line, and the commit it names has main's tree apart from the ledger and the event store (the
    # merge=union housekeeping the finish appends to)
    line = json.loads(git(p, "show", f"main:{LEDGER}").stdout.splitlines()[-1])
    assert git(p, "diff", "--name-only", line["payload"]["commit"], "main").stdout.split() == [
        LEDGER, "seldon_events.jsonl"]
    (got,) = _payloads(p, GR.EVENT_RECORDED)
    assert got["outcome"] == "pass" and got["ledger_commit"] == rec["ledger_commit"]


@pytest.mark.usefixtures("neo4j_available")
@pytest.mark.parametrize("outcome, reason", [("fail", "recorded_fail"), ("none", "no_line")])
def test_fixture_a_tip_without_a_record_is_refused(tmp_path, neo4j_driver, dc, outcome, reason):
    p = make_project(tmp_path, dispatch_extra={"gate_record": _decl(_recorder(tmp_path, "--outcome", outcome))})
    tid = _session(p, neo4j_driver, dc, f"sel024_unrecorded_{outcome}")
    out = _once(p)
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merge_blocked", (fin, out)
    assert fin["merge"]["reason"] == GR.PASS_UNRECORDED and fin["merge"]["files"] == [LEDGER], fin["merge"]
    assert fin["merge"]["record"]["reason"] == reason
    assert _state(neo4j_driver, tid) == "blocked"
    assert git(p, "show", "main:out/a.txt", check=False).returncode != 0, "nothing merged"
    assert f"MERGE BLOCKED {tid[:8]} ({GR.PASS_UNRECORDED})" in out


@pytest.mark.usefixtures("neo4j_available")
def test_fixture_a_gate_with_ruff_absent_is_gate_unrunnable_and_opens_a_huddle(tmp_path, neo4j_driver, dc,
                                                                             monkeypatch):
    monkeypatch.setenv("PATH", _no_ruff_env()["PATH"])
    p = make_project(tmp_path, dispatch_extra={"gate_record": _decl("ruff check .", requires=["ruff"])})
    tid = _session(p, neo4j_driver, dc, "sel024_no_ruff")
    out = _once(p)
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merge_blocked" and fin["merge"]["reason"] == GR.GATE_UNRUNNABLE, (fin, out)
    assert fin["merge"]["gate"]["missing"] == ["ruff"]
    (h,) = [h for h in _payloads(p, Q.EVENT_HUDDLE) if h.get("reason") == GR.GATE_UNRUNNABLE]
    assert h["task_id"] == tid and h["tools"] == ["ruff"] and "ruff" in h["reading"]
    assert Q.open_huddles(read_events(p)), "open until someone names its gate"
    (got,) = _payloads(p, GR.EVENT_RECORDED)
    assert got["outcome"] == "unrunnable" and got["ledger_commit"] is None, "never recorded as a pass"
    assert git(p, "show", f"{fin['branch']}:{LEDGER}", check=False).returncode != 0, "no ledger line on the branch"
    assert _state(neo4j_driver, tid) == "blocked"


@pytest.mark.usefixtures("neo4j_available")
def test_no_declaration_merges_as_today(tmp_path, neo4j_driver, dc):
    """The negative control: a project with no `gate_record` (or `none`) is not asked for a record."""
    p = make_project(tmp_path, dispatch_extra={"gate_record": "none"})
    _session(p, neo4j_driver, dc, "sel024_undeclared")
    _once(p)
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merged" and "gate_record" not in fin["merge"], fin
    assert _payloads(p, GR.EVENT_RECORDED) == []


# ── ADDENDUM 01 section 1: the gate command never runs while the pass holds the filing lock ──────────────────────

PARTS = "**Parts:** A 1.0.\n\n## Part A: the work\n\nAcceptance:\n- `check: test -f fix/landed.txt`\n"
HAND_TASK = """# CC Task — {stem}

**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Spend:** zero model calls.
**Network:** none.
**Dispatch:** hand (the operator, from the primary checkout; it fast-forwards main)
**Parts:** A 1.00.

## 1. Do the thing.
"""
#: The gate sleeps past the filer's wait: were it run under the pass's filing lock, the filer would be refused.
LOCK_WAIT_S = 1
GATE_SLEEP_S = 6


@pytest.mark.usefixtures("neo4j_available")
def test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing(tmp_path, neo4j_driver,
                                                                                            dc):
    mark = tmp_path / "gate.mark"
    # The pass covers the work's paths (squiddy's `tree_paths` shape): the task file the filer lands on main mid-gate
    # is outside them, so the record the gate makes still covers the tip the next pass merges.
    p = make_project(tmp_path, dispatch_extra={"gate_record": _decl(
        _recorder(tmp_path, "--outcome", "pass", "--sleep", str(GATE_SLEEP_S), "--mark", str(mark)),
        tree_paths=["out", "fix"])})
    cfg = yaml.safe_load((p / "seldon.yaml").read_text())
    cfg["filings"] = {"lock_wait_s": LOCK_WAIT_S}
    (p / "seldon.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    git(p, "commit", "-q", "-am", f"filings wait {LOCK_WAIT_S}s")

    # A task blocked `stop_gate_unpassed` with its work kept (DISP-003R's case), whose check a later main fix passes.
    stem = "sel024_regate_lock"
    add_task(p, stem, PARTS)
    tid = register(p, neo4j_driver, dc, stem, "2026-11-06T00:00:00Z")
    write_stub(p, {stem: {"write": {"out/work.txt": "work\n"}, "part_complete": ["A"], "stop_hook": True,
                          "exit": 0, "worktree_name": stem}})
    _once(p)
    assert _payloads(p, D.EVENT_FINISHED)[-1]["outcome"] == "stop_gate_unpassed"
    assert not mark.exists(), "the post-session path never reached the merge round"
    (p / "fix").mkdir()
    (p / "fix" / "landed.txt").write_text("fixed\n")
    git(p, "add", "fix/landed.txt")
    git(p, "commit", "-q", "-m", "fix lands on main", "--", "fix/landed.txt")

    seen = {}

    def filer():
        deadline = time.monotonic() + 120
        while not mark.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        seen["gate_running_at_start"] = mark.exists() and mark.read_text() == "started\n"
        try:
            seen["filed"] = F.file_task(p, HAND_TASK.format(stem="filed during the gate"),
                                        name="2026-11-06_filed_during_the_gate.md")
        except F.FilingError as exc:
            seen["refused"] = str(exc)
        seen["gate_running_at_end"] = mark.read_text() == "started\n"

    t = threading.Thread(target=filer)
    t.start()
    out = _once(p)                                      # the regate defers; the record step runs the gate unlocked
    t.join(timeout=180)
    assert "refused" not in seen, seen
    assert seen["gate_running_at_start"] and seen["gate_running_at_end"], (seen, "the filing landed mid-gate")
    assert seen["filed"]["artifact_id"]
    (pending,) = _payloads(p, GR.EVENT_PENDING)
    assert pending["task_id"] == tid and pending["by"] == "regate", out
    (got,) = _payloads(p, GR.EVENT_RECORDED)
    assert got["outcome"] == "pass" and got["ledger_commit"], got
    assert _state(neo4j_driver, tid) == "blocked", "left as it was until the next pass"

    out = _once(p)                                      # the next pass merges on the record, running nothing
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merged", (fin, out)
    assert fin["merge"]["gate_record"]["ran"] is False and fin["merge"]["gate_record"]["coverage"]["covered"]
    assert len(_payloads(p, GR.EVENT_RECORDED)) == 1, "the gate ran once"
    assert _state(neo4j_driver, tid) == "completed"
    assert git(p, "show", "main:out/work.txt").stdout == "work\n"
