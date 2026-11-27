"""SEL-055 Part B (AD-034 ADDENDUM 13, R38 to R40): the full suite runs on main on a schedule, its red closes the merges
that can change a test, and a lane branch is planned like any other.

`cc_tasks/2026-11-27_SEL-055_the_gate_runs_what_a_change_can_break_and_no_queue_waits_an_hour_for_a_one_line_change.md`
and its ADDENDUM 01 (lane merges are a new caller of the merge gate). The first half needs no Neo4j: temporary git
repositories and the planner. The second half drives the dispatcher on scaffold projects: the idle pass runs the
scheduled gate and a red one opens the closure; a merge under the closure runs the red run's failed files, an inert
branch is not closed and a fix merges; a lane branch with no evidence merges on its selected gate and the record says
so.
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from seldon.commands import dispatch_gate as GATE
from seldon.core import gate_plan as GP
from seldon.core.events import make_event, read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import RESEARCH_YAML, add_task, git, make_project, register, run_cli, write_stub
from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _ev(kind: str, payload: dict, at: datetime, eid: str) -> dict:
    return {"event_type": kind, "timestamp": _iso(at), "event_id": eid, "payload": payload}


def _sched(outcome: str, at: datetime, eid: str, failed=()) -> dict:
    return _ev(GP.EVENT_GATE_RUN, {"call_site": "scheduled", "tier": "full", "outcome": outcome,
                                   "failed_files": list(failed), "commit": "c" * 40}, at, eid)


def _full_pass(at: datetime, eid: str = "fp") -> dict:
    return _ev(GP.EVENT_GATE_RUN, {"call_site": "merge_gate", "tier": "full", "outcome": "pass"}, at, eid)


def _merged(at: datetime, eid: str, evidence: dict) -> dict:
    return _ev("dispatch_finished", {"outcome": "merged", "merge": {"gate_evidence": evidence}}, at, eid)


GCFG = GP.load_gate_config({"slices": [{"name": "docs", "paths": ["docs/**"], "tests": "none"}],
                            "test_command": "true {tests}"}, "true")


# ============================================================================================ R38: the schedule

def test_a_project_without_slices_has_no_schedule():
    assert GP.scheduled_due([], GP.load_gate_config(None, "true"), idle=True, now=NOW) is None


def test_with_no_full_gate_on_record_the_schedule_runs_on_an_idle_pass_only():
    assert GP.scheduled_due([], GCFG, idle=True, now=NOW).startswith("never")
    assert GP.scheduled_due([], GCFG, idle=False, now=NOW) is None


def test_after_full_every_s_the_schedule_waits_for_an_idle_pass_and_after_full_overdue_s_it_does_not():
    day = timedelta(seconds=GCFG["full_every_s"])
    fresh = [_full_pass(NOW - timedelta(hours=1))]
    assert GP.scheduled_due(fresh, GCFG, idle=True, now=NOW) is None
    due = [_sched("pass", NOW - day - timedelta(minutes=1), "s1")]
    assert GP.scheduled_due(due, GCFG, idle=True, now=NOW).startswith("due:")
    assert GP.scheduled_due(due, GCFG, idle=False, now=NOW) is None, "a queue with work waits for an idle pass"
    overdue = [_sched("pass", NOW - timedelta(seconds=GCFG["full_overdue_s"] + 60), "s1")]
    assert GP.scheduled_due(overdue, GCFG, idle=False, now=NOW).startswith("overdue:")


def test_the_anchor_is_the_newest_full_gate_scheduled_or_a_tasks_full_pass():
    old = NOW - timedelta(days=3)
    events = [_sched("pass", old, "s1"), _full_pass(NOW - timedelta(hours=2))]
    assert GP.scheduled_due(events, GCFG, idle=True, now=NOW) is None, "a task's full pass on main counts"


def test_a_merge_under_a_red_main_makes_the_schedule_due_at_once():
    red = _sched("fail", NOW - timedelta(hours=1), "r1", ["tests/test_x.py"])
    scoped = {"source": "gate_run", "tier": "scoped", "reason": "scoped: docs"}
    events = [red, _merged(NOW - timedelta(minutes=30), "m1", scoped)]
    assert GP.scheduled_due(events, GCFG, idle=False, now=NOW).startswith("main_red_merged")
    assert GP.scheduled_due([red], GCFG, idle=False, now=NOW) is None


def test_the_cadence_never_promotes_a_plan(tmp_path):
    repo = _repo(tmp_path)
    _change(repo, {"docs/a.md": "x\n"})
    p = GP.plan(repo, GCFG, base="main", gate_command="true", events=[], now=NOW)
    assert p["tier"] == "scoped" and p["reason"].startswith("declared_none"), p


# ============================================================================================ R39: the closure

def test_main_is_red_from_a_red_scheduled_run_until_a_scheduled_pass():
    red = _sched("fail", NOW - timedelta(hours=2), "r1", ["tests/test_x.py"])
    assert GP.main_red([red])["event_id"] == "r1"
    assert GP.main_red([red, _sched("pass", NOW, "s2")]) is None
    assert GP.main_red([red, _sched("timeout", NOW, "s2")])["event_id"] == "s2", "a timeout is red"
    assert GP.main_red([_full_pass(NOW - timedelta(hours=3)), red])["event_id"] == "r1", \
        "a task's failing or passing full gate before it does not clear it"


def test_main_is_green_again_when_a_branch_merges_on_a_passing_full_gate():
    red = _sched("fail", NOW - timedelta(hours=2), "r1", ["tests/test_x.py"])
    full = {"source": "merge_gate", "gate": {"tier": "full", "ok": True}}
    scoped = {"source": "merge_gate", "gate": {"tier": "scoped", "ok": True}}
    assert GP.main_red([red, _merged(NOW, "m1", scoped)])["event_id"] == "r1"
    assert GP.main_red([red, _merged(NOW, "m1", full)]) is None
    assert GP.main_red([red, _merged(NOW, "m1", {"source": "gate_run", "tier": "full"})]) is None


def _repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
        subprocess.run(["git", *args], cwd=r, check=True, capture_output=True)
    files = {"src/a.py": "a = 1\n", "tests/test_a.py": "def test_a():\n    pass\n",
             "tests/test_x.py": "def test_x():\n    pass\n", "docs/g.md": "g\n"}
    _write(r, files)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=r, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feat"], cwd=r, check=True)
    return r


def _write(root: Path, files: dict) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def _change(repo: Path, files: dict) -> None:
    _write(repo, files)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "change"], cwd=repo, check=True)


CODE_GCFG = GP.load_gate_config({"slices": [{"name": "docs", "paths": ["docs/**"], "tests": "none"},
                                            {"name": "a", "paths": ["src/a.py"], "tests": ["tests/test_a.py"]}],
                                 "test_command": "true {tests}"}, "true")


def test_under_the_closure_a_plan_that_selects_tests_also_runs_the_red_runs_failed_files(tmp_path):
    repo = _repo(tmp_path)
    _change(repo, {"src/a.py": "a = 2\n"})
    red = _sched("fail", NOW, "r1", ["tests/test_x.py", "tests/gone.py"])
    p = GP.plan(repo, CODE_GCFG, base="main", gate_command="true", events=[], closure=red)
    assert p["tier"] == "scoped" and p["tests"] == ["tests/test_a.py", "tests/test_x.py"], p
    assert p["always"]["main_red"] == ["tests/test_x.py"], "a failed file the tree no longer has is not selected"
    assert p["main_red"]["applied"] == "failed_files" and p["main_red"]["event_id"] == "r1"
    without = GP.plan(repo, CODE_GCFG, base="main", gate_command="true", events=[])
    assert without["tests"] == ["tests/test_a.py"] and "main_red" not in without, "the Stop gate passes no closure"


def test_under_the_closure_an_inert_plan_is_not_closed(tmp_path):
    repo = _repo(tmp_path)
    _change(repo, {"docs/g.md": "h\n"})
    p = GP.plan(repo, CODE_GCFG, base="main", gate_command="true", events=[],
                closure=_sched("fail", NOW, "r1", ["tests/test_x.py"]))
    assert p["tier"] == "scoped" and p["tests"] == [] and p["reason"].startswith("declared_none"), p
    assert p["main_red"]["applied"] == "inert"


def test_a_red_run_that_named_no_failed_file_closes_a_selecting_plan_in_full(tmp_path):
    repo = _repo(tmp_path)
    _change(repo, {"src/a.py": "a = 3\n"})
    p = GP.plan(repo, CODE_GCFG, base="main", gate_command="true", events=[],
                closure=_sched("timeout", NOW, "r1"))
    assert p["tier"] == "full" and p["reason"].startswith("main_red: the scheduled run r1"), p


def test_evidence_made_without_the_closure_does_not_stand_while_it_holds():
    red = _sched("fail", NOW, "r1", ["tests/test_x.py"])
    assert GP.closure_admits({"source": "stop_gate", "checks_run": 3}, None)
    assert not GP.closure_admits({"source": "stop_gate", "checks_run": 3}, red)
    assert not GP.closure_admits({"source": "kept_regate", "checks": 2}, red)
    assert not GP.closure_admits({"source": "gate_run", "tier": "scoped", "reason": "scoped: a"}, red)
    assert GP.closure_admits({"source": "gate_run", "tier": "scoped", "reason": "scoped: a", "main_red": "r1"}, red)
    assert GP.closure_admits({"source": "gate_run", "tier": "scoped", "reason": "declared_none: x"}, red)
    assert GP.closure_admits({"source": "gate_run", "tier": "full", "reason": "unmatched: x"}, red)
    assert GP.closure_admits({"source": "gate_record", "record": {}}, red)


def test_a_record_carries_main_red_and_lane_only_when_they_hold(tmp_path):
    repo = _repo(tmp_path)
    _change(repo, {"src/a.py": "a = 4\n"})
    result = {"seconds": 1.0, "outcome": "pass", "exit_code": 0, "failed_files": []}
    plain = GP.record_payload(GP.plan(repo, CODE_GCFG, base="main", gate_command="true", events=[]), result,
                              call_site="merge_gate", events=[])
    assert "main_red" not in plain and "lane" not in plain, "a record that uses neither is unchanged"
    closed = GP.plan(repo, CODE_GCFG, base="main", gate_command="true", events=[],
                     closure=_sched("fail", NOW, "r1", ["tests/test_x.py"]))
    rec = GP.record_payload(closed, result, call_site="merge_gate", events=[], lane=True)
    assert rec["main_red"]["event_id"] == "r1" and rec["lane"] is True
    ev = GP.evidence({"event_id": "g1", "payload": rec})
    assert ev["main_red"] == "r1"


# ============================================================================================ R40: the lane warning

def test_a_lane_whose_writes_no_slice_covers_is_warned_about():
    lane = {"writes": ["notes/**", "for_operator/**"]}
    gcfg = GP.load_gate_config({"slices": [{"name": "notes", "paths": ["notes/**"], "tests": "none"}],
                                "test_command": "true {tests}"}, "true")
    assert GP.lane_uncovered(gcfg, lane) == ["for_operator/**"]
    warns = GP.warnings(gcfg, "true", [], lane=lane)
    assert any("for_operator/**" in w and "AD-034-R40" in w for w in warns), warns
    assert GP.lane_uncovered(GP.load_gate_config(None, "true"), lane) == ["notes/**", "for_operator/**"]
    assert not GP.warnings(gcfg, None, [], lane=lane), "no gate command, nothing is gated in full"


# ============================================================================================ the scheduled run

def _cfg(repo: Path, gate_command: str, notify_file: Path) -> dict:
    return {"branch": "main", "gate_command": gate_command, "log_dir": "logs/dispatch", "gate_timeout_s": 120,
            "worktree_links": [], "lease_file": None, "notify_timeout_s": 30,
            "notify": f"echo \"$SELDON_NOTIFY_OUTCOME|$SELDON_NOTIFY_MESSAGE\" >> {notify_file}",
            "gate": GP.load_gate_config({"slices": [{"name": "docs", "paths": ["docs/**"], "tests": "none"}],
                                         "test_command": "true {tests}"}, gate_command)}


def _scheduled_repo(tmp_path) -> Path:
    r = tmp_path / "proj"
    r.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
        subprocess.run(["git", *args], cwd=r, check=True, capture_output=True)
    _write(r, {"tests/test_a.py": "def test_a():\n    pass\n", ".gitignore": ".seldon/\nlogs/\n"})
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=r, check=True)
    return r


def test_the_scheduled_run_checks_out_main_records_it_and_leaves_no_checkout(tmp_path):
    p = _scheduled_repo(tmp_path)
    notes = tmp_path / "notes.txt"
    # The command proves it ran in main's checkout: the tracked test file is there.
    out = GATE.run_scheduled(p, _cfg(p, "test -f tests/test_a.py", notes), "due: test")
    assert out["ok"] and not out["opened"] and not notes.exists()
    (run,) = [e["payload"] for e in read_events(p) if e["event_type"] == GP.EVENT_GATE_RUN]
    assert (run["call_site"], run["tier"], run["outcome"]) == ("scheduled", "full", "pass")
    assert run["reason"] == "scheduled: due: test" and run["files_total"] == 1
    assert run["commit"] == subprocess.run(["git", "rev-parse", "main"], cwd=p, capture_output=True,
                                           text=True).stdout.strip()
    assert not (p / ".seldon" / "gate_main").exists()
    assert "gate_main" not in subprocess.run(["git", "worktree", "list"], cwd=p, capture_output=True,
                                             text=True).stdout
    assert subprocess.run(["git", "status", "--porcelain"], cwd=p, capture_output=True,
                          text=True).stdout.strip() == "?? seldon_events.jsonl"


def test_a_red_scheduled_run_rings_once_per_closure_and_a_pass_lifts_it(tmp_path):
    p = _scheduled_repo(tmp_path)
    notes = tmp_path / "notes.txt"
    red_cmd = "echo 'FAILED tests/test_a.py::test_a - boom'; exit 1"
    first = GATE.run_scheduled(p, _cfg(p, red_cmd, notes), "due: 1")
    assert not first["ok"] and first["opened"] and first["failed_files"] == ["tests/test_a.py"]
    assert GP.main_red(read_events(p))["event_id"] == first["gate_run"]
    second = GATE.run_scheduled(p, _cfg(p, red_cmd, notes), "due: 2")
    assert not second["opened"], "a second red run in the same closure rings nothing new"
    lines = notes.read_text().splitlines()
    assert len(lines) == 1 and lines[0].startswith("main_red|main_red: the scheduled full gate on main")
    assert "tests/test_a.py" in lines[0]
    third = GATE.run_scheduled(p, _cfg(p, "true", notes), "due: 3")
    assert third["closed"] and GP.main_red(read_events(p)) is None
    assert notes.read_text().splitlines()[-1].startswith("main_green|")


def test_a_second_scheduled_run_while_one_holds_the_lock_is_refused(tmp_path):
    import fcntl
    p = _scheduled_repo(tmp_path)
    (p / ".seldon").mkdir()
    with (p / ".seldon" / "gate_main.lock").open("a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(GATE.ScheduledBusy):
            GATE.run_scheduled(p, _cfg(p, "true", tmp_path / "n.txt"), "due")


# ============================================================================================ the dispatcher

@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


#: The scaffold's sliced gate. `test_command` fails when a selected file says RED, so a selection that includes the red
#: run's failed file is red until a branch fixes it; the full `gate_command` is `false`, so a full gate is always red.
SLICES = {
    "slices": [
        {"name": "records", "paths": ["cc_tasks/**", "seldon_events.jsonl", "docs/**", "notes/**"], "tests": "none"},
        {"name": "src", "paths": ["src/**"], "tests": ["tests/test_s.py"]},
    ],
    "test_command": "! grep -l RED {tests}",
}


def _sliced(tmp_path, **extra):
    p = make_project(tmp_path, dispatch_extra={"gate_command": "false", "gate": SLICES, **extra})
    _write(p, {"tests/test_s.py": "ok\n", "tests/test_broken.py": "RED\n", "src/s.txt": "s\n"})
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "sources and tests")
    return p


def _seed(p: Path, payload: dict) -> dict:
    ev = make_event(GP.EVENT_GATE_RUN, "t", "accepted", payload)
    with (p / "seldon_events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev) + "\n")
    git(p, "add", "seldon_events.jsonl")
    git(p, "commit", "-q", "-m", "seed a gate record")
    return ev


def _seed_red(p: Path) -> dict:
    return _seed(p, {"call_site": "scheduled", "tier": "full", "outcome": "fail", "seconds": 1.0,
                     "failed_files": ["tests/test_broken.py"], "commit": "c" * 40, "tree": "seed",
                     "change_set": "seed"})


def _finished(p, stem):
    return [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_FINISHED
            and e["payload"].get("source_file") == f"cc_tasks/{stem}.md"]


def _once(p):
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    return res.output


@pytest.mark.usefixtures("neo4j_available")
def test_an_idle_pass_runs_the_scheduled_gate_and_a_red_one_opens_an_issue(tmp_path, neo4j_driver, dc):
    p = _sliced(tmp_path)
    out = _once(p)
    assert "scheduled gate: fail" in out, out
    runs = [e for e in read_events(p) if e["event_type"] == GP.EVENT_GATE_RUN]
    assert [r["payload"]["call_site"] for r in runs] == ["scheduled"]
    assert runs[0]["payload"]["reason"].startswith("scheduled: never")
    assert GP.main_red(read_events(p))["event_id"] == runs[0]["event_id"]
    with neo4j_driver.session(database=D_DB()) as s:
        rows = s.run("MATCH (i:Issue {issue_type: 'main_red'}) RETURN i.gate_run AS g").data()
    assert [r["g"] for r in rows].count(runs[0]["event_id"]) == 1, rows
    committed = subprocess.run(["git", "status", "--porcelain", "seldon_events.jsonl"], cwd=p, capture_output=True,
                               text=True).stdout.strip()
    assert committed == "", "the pass committed the record"
    _once(p)
    assert len([e for e in read_events(p) if e["event_type"] == GP.EVENT_GATE_RUN]) == 1, \
        "not due again on the next pass: the red run is the anchor"


def D_DB():
    from tests.dispatch_scaffold import NEO4J_DB
    return NEO4J_DB


@pytest.mark.usefixtures("neo4j_available")
def test_under_a_red_main_a_branch_that_selects_tests_is_closed_and_a_fix_merges(tmp_path, neo4j_driver, dc):
    p = _sliced(tmp_path)
    red = _seed_red(p)
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-11-27T00:00:01Z")
    write_stub(p, {"a": {"write": {"src/s.txt": "s2\n"}, "worktree_name": "a"}})
    _once(p)
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merge_blocked" and fin["merge"]["reason"] == "regate_red", fin
    gate = fin["merge"]["gate"]
    assert gate["tier"] == "scoped" and gate["main_red"]["applied"] == "failed_files", gate
    (run,) = [e["payload"] for e in read_events(p) if e["event_type"] == GP.EVENT_GATE_RUN
              and e["payload"].get("call_site") == "merge_gate"]
    assert run["tests"] == ["tests/test_broken.py", "tests/test_s.py"] and run["outcome"] == "fail", run
    assert run["main_red"]["event_id"] == red["event_id"]

    add_task(p, "b")
    register(p, neo4j_driver, dc, "b", "2026-11-27T00:00:02Z")
    write_stub(p, {"b": {"write": {"src/s.txt": "s3\n"}, "replace": {"tests/test_broken.py": ["RED", "fixed"]},
                         "worktree_name": "b"}})
    _once(p)
    fin = _finished(p, "b")[-1]
    assert fin["outcome"] == "merged", fin.get("merge")
    assert fin["merge"]["main_red"] == red["event_id"]
    assert fin["merge"]["gate_evidence"]["gate"]["main_red"]["applied"] == "failed_files"
    # The fix merged on a scoped gate, so the closure stands until the scheduled run says main is green, and that run
    # is due at once (R39). The next pass runs it (gate_command `false` here: still red, and no second Issue).
    assert GP.main_red(read_events(p))["event_id"] == red["event_id"]
    assert GP.scheduled_due(read_events(p), GP.load_gate_config(SLICES, "false"), idle=False).startswith(
        "main_red_merged")


@pytest.mark.usefixtures("neo4j_available")
def test_under_a_red_main_an_inert_branch_merges(tmp_path, neo4j_driver, dc):
    p = _sliced(tmp_path)
    red = _seed_red(p)
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-11-27T00:00:01Z")
    write_stub(p, {"a": {"write": {"docs/a.md": "a\n"}, "worktree_name": "a"}})
    _once(p)
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merged", fin.get("merge")
    ev = fin["merge"]["gate_evidence"]
    assert ev["gate"]["tier"] == "scoped" and ev["gate"]["reason"].startswith("declared_none"), ev
    assert ev["gate"]["main_red"]["applied"] == "inert" and fin["merge"]["main_red"] == red["event_id"]


LANE = {"name_pattern": r"^OODA-\d+", "slots": 1, "writes": ["notes/**"], "merge_wait_s": 120}


def _wait(pred, what, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.mark.usefixtures("neo4j_available")
def test_a_lane_branch_with_no_evidence_merges_on_its_selected_gate_and_the_record_says_so(
        tmp_path, neo4j_driver, dc):
    """ADDENDUM 01 section 1: a lane branch (factory's OODAs) reaches the R26 evidence check like any branch. Its writes
    are declared in a slice here (`notes/**`, `tests: none`), so it merges on a scoped gate that runs nothing, while
    the full `gate_command` is `false`; the `gate_run` and the merge record name the lane (R40)."""
    p = _sliced(tmp_path, coordination_lane=LANE, poll_interval_s=1)
    add_task(p, "OODA-004")
    register(p, neo4j_driver, dc, "OODA-004", "2026-11-27T00:00:01Z")
    write_stub(p, {"OODA-004": {"write": {"notes/ooda4.md": "o\n"}, "complete": True}})
    _once(p)

    def finished():
        return _finished(p, "OODA-004")
    _wait(finished, "OODA-004's finish")
    fin = finished()[-1]
    assert fin["outcome"] == "merged", fin.get("merge")
    assert fin["merge"]["lane"] is True
    ev = fin["merge"]["gate_evidence"]
    assert ev["source"] == "merge_gate" and ev["gate"]["tier"] == "scoped", ev
    assert ev["gate"]["reason"].startswith("declared_none"), ev
    (run,) = [e["payload"] for e in read_events(p) if e["event_type"] == GP.EVENT_GATE_RUN
              and e["payload"].get("call_site") == "merge_gate"]
    assert run["lane"] is True and run["steps"] == [] and run["outcome"] == "pass", run
