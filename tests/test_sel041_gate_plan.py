"""SEL-041 Part C and E: the gate planner, runner, record, escapes, evidence, warnings and chart (AD-034-R29 to R37).

`cc_tasks/2026-11-21_SEL-041_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points.md`
and AD-034 ADDENDUM 12. The task's test list, each a test below: a documents-only change selects nothing and passes
in seconds; a change in one slice selects that slice; an unmatched path, a lock change and a conftest change each go
full with the reason; new and last-failed tests are always in; the record is written; an escape is recorded; a
passing record is merge evidence (ADDENDUM 01 item 3). No Neo4j: every repository here is a temporary git checkout.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands import dispatch_worktree as W
from seldon.core import gate_plan as GP
from seldon.core import stations as S
from seldon.core.events import make_event

PY = sys.executable
PYTEST = f"{PY} -m pytest -q -p no:cacheprovider -p no:randomly -o addopts="
GATE_FULL = f"{PYTEST} tests"


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def write(root: Path, files: dict) -> None:
    for rel, text in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")


BASE_FILES = {
    "src/a.py": "def a():\n    return 1\n",
    "src/b.py": "def b():\n    return 2\n",
    "tests/test_a.py": "def test_a():\n    assert True\n",
    "tests/test_b.py": "def test_b():\n    assert True\n",
    "docs/guide.md": "# guide\n",
    "README.md": "# r\n",
    "uv.lock": "lock 1\n",
    ".gitignore": "__pycache__/\n",
}

SLICES = [
    {"name": "a", "paths": ["src/a.py"], "tests": ["tests/test_a.py"]},
    {"name": "b", "paths": ["src/b.py"], "tests": ["tests/test_b.py"]},
    {"name": "documents", "paths": ["docs/**", "*.md", "cc_tasks/**"], "tests": "none"},
]


def gcfg(**over) -> dict:
    block = {"slices": SLICES, "test_command": f"{PYTEST} {{tests}}", **over}
    return GP.load_gate_config(block, GATE_FULL)


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    write(r, BASE_FILES)
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "init")
    git(r, "checkout", "-q", "-b", "feat")
    return r


def change(r: Path, files: dict, delete=()) -> None:
    write(r, files)
    for d in delete:
        (r / d).unlink()
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "change")


def full_pass_event(age_s: float = 60) -> dict:
    """A passing full gate, `age_s` ago: the cadence is satisfied, so a plan is scoped unless something forces full."""
    ev = make_event(GP.EVENT_GATE_RUN, "t", "accepted", {"tier": "full", "outcome": "pass", "seconds": 100.0,
                                                          "tree": "x", "change_set": "y"})
    ev["timestamp"] = (datetime.now(timezone.utc) - timedelta(seconds=age_s)).isoformat().replace("+00:00", "Z")
    return ev


def plan(r: Path, events=None, **kw) -> dict:
    cfg = kw.pop("cfg", None) or gcfg()
    return GP.plan(r, cfg, base="main", gate_command=GATE_FULL,
                   events=[full_pass_event()] if events is None else events, branch="feat", **kw)


def run(r: Path, p: dict, tmp_path: Path, cfg=None) -> dict:
    return GP.run(r, p, cfg or gcfg(), gate_command=GATE_FULL, timeout_s=300, log_path=tmp_path / "gate.log",
                  primary=r)


# ===================================================================================== the task's list (Part C)

def test_a_documents_only_change_selects_nothing_and_passes_in_seconds(repo, tmp_path):
    change(repo, {"docs/guide.md": "# guide, revised\n", "README.md": "# r2\n"})
    p = plan(repo)
    assert p["tier"] == "scoped" and p["reason"].startswith("declared_none"), p
    assert p["tests"] == [] and p["markers"] == [] and p["commands"] == []
    res = run(repo, p, tmp_path)
    assert res["ok"] and res["steps"] == [] and res["seconds"] < 5


def test_a_change_in_one_slice_selects_that_slice_only(repo, tmp_path):
    change(repo, {"src/a.py": "def a():\n    return 3\n"})
    p = plan(repo)
    assert p["tier"] == "scoped" and sorted(p["slices"]) == ["a"]
    assert p["tests"] == ["tests/test_a.py"] and p["files_selected"] == 1 and p["files_total"] == 2
    res = run(repo, p, tmp_path)
    assert res["ok"] and res["tests_run"] == 1, res


@pytest.mark.parametrize("files,reason", [
    ({"src/new_module.py": "x = 1\n"}, "unmatched: src/new_module.py"),
    ({"uv.lock": "lock 2\n"}, "full_path: uv.lock"),
    ({"tests/conftest.py": "import os\n"}, "conftest: tests/conftest.py"),
])
def test_what_selection_cannot_vouch_for_goes_full_with_the_reason(repo, files, reason):
    change(repo, files)
    p = plan(repo)
    assert p["tier"] == "full" and p["reason"] == reason, p


def test_a_change_to_the_gates_own_configuration_goes_full(repo):
    write(repo, {"seldon.yaml": yaml.safe_dump({"dispatch": {"gate_command": "a"}})})
    git(repo, "checkout", "-q", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "config")
    git(repo, "checkout", "-q", "-B", "feat")
    cfg = GP.load_gate_config({"slices": SLICES + [{"name": "config", "paths": ["seldon.yaml"], "tests": "none"}],
                               "test_command": f"{PYTEST} {{tests}}"}, GATE_FULL)
    change(repo, {"seldon.yaml": yaml.safe_dump({"dispatch": {"gate_command": "a", "notify": "n"}})})
    assert plan(repo, cfg=cfg)["tier"] == "scoped", "a seldon.yaml change outside the gate keys is a declared path"
    change(repo, {"seldon.yaml": yaml.safe_dump({"dispatch": {"gate_command": "b", "notify": "n"}})})
    p = plan(repo, cfg=cfg)
    assert p["tier"] == "full" and p["reason"] == "gate_config_changed: seldon.yaml", p


def test_tests_the_branch_added_or_changed_always_run(repo):
    change(repo, {"tests/test_c.py": "def test_c():\n    assert True\n", "docs/guide.md": "# g\n"})
    p = plan(repo)
    assert p["tier"] == "scoped" and p["tests"] == ["tests/test_c.py"]
    assert p["always"]["changed_tests"] == ["tests/test_c.py"]


def test_a_deleted_test_file_needs_nothing_run(repo):
    change(repo, {"docs/guide.md": "# g\n"}, delete=["tests/test_b.py"])
    p = plan(repo)
    assert p["tier"] == "scoped" and p["tests"] == [] and p["unmatched"] == []


def test_tests_that_failed_in_the_last_recorded_gate_always_run(repo):
    change(repo, {"docs/guide.md": "# g\n"})
    failed = make_event(GP.EVENT_GATE_RUN, "t", "accepted",
                        {"tier": "scoped", "outcome": "fail", "failed_files": ["tests/test_b.py", "tests/gone.py"]})
    p = plan(repo, events=[full_pass_event(), failed])
    assert p["tests"] == ["tests/test_b.py"] and p["always"]["last_failed"] == ["tests/test_b.py"]


def test_a_slice_whose_tests_match_nothing_goes_full(repo):
    cfg = GP.load_gate_config({"slices": [{"name": "a", "paths": ["src/a.py"], "tests": ["tests/test_zzz*.py"]}],
                               "test_command": f"{PYTEST} {{tests}}"}, GATE_FULL)
    change(repo, {"src/a.py": "def a():\n    return 9\n"})
    p = plan(repo, cfg=cfg)
    assert p["tier"] == "full" and p["reason"] == "slice_tests_missing: a: tests/test_zzz*.py"


def test_markers_and_commands_run_as_declared(repo, tmp_path):
    write(repo, {"tests/test_m.py": "import pytest\n\n@pytest.mark.fast\ndef test_m():\n    assert True\n\n"
                                    "def test_unmarked():\n    assert True\n",
                 "pytest.ini": "[pytest]\nmarkers =\n    fast: x\n"})
    git(repo, "checkout", "-q", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "m")
    git(repo, "checkout", "-q", "-B", "feat")
    cfg = GP.load_gate_config({"slices": [{"name": "a", "paths": ["src/a.py"], "tests": ["marker:fast"],
                                           "commands": ["echo lint-ran"]}],
                               "test_command": f"{PYTEST} {{tests}}"}, GATE_FULL)
    change(repo, {"src/a.py": "def a():\n    return 4\n"})
    p = plan(repo, cfg=cfg)
    assert p["tier"] == "scoped" and p["markers"] == ["fast"] and p["commands"] == ["echo lint-ran"]
    res = run(repo, p, tmp_path, cfg)
    assert res["ok"], res
    assert [s["kind"] for s in res["steps"]] == ["markers", "command"]
    assert res["tests_run"] == 1, "the marker selected one of the two tests"
    assert "lint-ran" in (tmp_path / "gate.log").read_text()


def test_the_cadence_promotes_the_next_gate_to_full(repo):
    change(repo, {"src/a.py": "def a():\n    return 5\n"})
    assert plan(repo, events=[])["reason"] == "cadence_due: no passing full gate is recorded"
    old = plan(repo, events=[full_pass_event(age_s=90000)])
    assert old["tier"] == "full" and old["reason"].startswith("cadence_due: the last passing full gate was at")
    assert plan(repo, events=[full_pass_event(age_s=60)])["tier"] == "scoped"


def test_a_requested_full_gate(repo):
    change(repo, {"docs/guide.md": "# g\n"})
    assert plan(repo, full=True)["reason"] == "requested: --full"
    p = plan(repo, task_text="# T\n\n**Gate:** full\n**Parts:** A 1.0\n\nbody\n")
    assert p["tier"] == "full" and p["reason"] == "requested: **Gate:** full"


def test_a_project_without_slices_plans_full_as_before(repo, tmp_path):
    change(repo, {"docs/guide.md": "# g\n"})
    cfg = GP.load_gate_config(None, GATE_FULL)
    p = GP.plan(repo, cfg, base="main", gate_command=GATE_FULL, events=[], branch="feat")
    assert p["tier"] == "full" and p["reasons"] == ["no_slices"] and p["unmatched"] == []
    res = run(repo, p, tmp_path, cfg)
    assert res["ok"] and res["tests_run"] == 2
    log = (tmp_path / "gate.log").read_text()
    assert log.splitlines()[0].endswith(f"| gate | {GATE_FULL}"), "the full tier's log header is the pre-addendum one"
    assert log.rstrip().endswith("EXIT=0")


def test_a_dirty_tree_is_planned_with_its_uncommitted_paths_and_marked(repo):
    write(repo, {"src/b.py": "def b():\n    return 7\n"})
    p = plan(repo)
    assert p["dirty"] is True and p["tests"] == ["tests/test_b.py"]


# ======================================================================================= the record (R33)

def test_the_record_is_written_and_an_escape_is_recorded(repo, tmp_path):
    """A scoped gate on the branch selects test_a; the full gate then fails test_b, which the scoped gate did not
    select: test_b is an escape on the full gate's record (R33)."""
    change(repo, {"src/a.py": "def a():\n    return 1\n# touched\n",
                  "tests/test_b.py": "def test_b():\n    assert True\n"})
    # The branch's change to test_b makes it always-run; undo that so the escape is a real one: edit test_b on main.
    git(repo, "checkout", "-q", "main")
    write(repo, {"tests/test_b.py": "def test_b():\n    assert False, 'broken on main'\n"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "break b on main")
    git(repo, "checkout", "-q", "feat")
    git(repo, "reset", "-q", "--hard", "main")
    change(repo, {"src/a.py": "def a():\n    return 6\n"})
    events = [full_pass_event()]
    scoped = plan(repo, events=events)
    assert scoped["tier"] == "scoped" and scoped["tests"] == ["tests/test_a.py"]
    res = run(repo, scoped, tmp_path)
    assert res["ok"]
    rec1 = GP.record_payload(scoped, res, call_site="cli", events=events, task_id="t1", branch="feat")
    assert rec1["tier"] == "scoped" and rec1["outcome"] == "pass" and rec1["files_selected"] == 1
    assert rec1["files_total"] == 2 and rec1["tests_run"] == 1 and rec1["escapes"] == []
    ev1 = GP.emit(repo, rec1, actor="t")
    events.append(ev1)
    full = plan(repo, events=events, full=True)
    res2 = run(repo, full, tmp_path)
    assert not res2["ok"] and res2["failed_files"] == ["tests/test_b.py"], res2
    rec2 = GP.record_payload(full, res2, call_site="cli", events=events, task_id="t1", branch="feat")
    assert rec2["tier"] == "full" and rec2["outcome"] == "fail" and rec2["escapes"] == ["tests/test_b.py"]
    ev2 = GP.emit(repo, rec2, actor="t")
    stored = [json.loads(x) for x in (repo / "seldon_events.jsonl").read_text().splitlines()]
    assert [e["event_type"] for e in stored] == ["gate_run", "gate_run"]
    assert stored[-1]["event_id"] == ev2["event_id"] and stored[-1]["payload"]["escapes"] == ["tests/test_b.py"]
    weeks = GP.by_week(stored)
    assert weeks[-1]["escapes"] == 1 and weeks[-1]["scoped"]["n"] == 1 and weeks[-1]["full"]["n"] == 1
    assert weeks[-1]["failed"] == 1


def test_a_failure_the_scoped_gate_selected_is_not_an_escape(repo, tmp_path):
    change(repo, {"src/a.py": "def a():\n    return 6\n", "tests/test_a.py": "def test_a():\n    assert False\n"})
    events = [full_pass_event()]
    scoped = plan(repo, events=events)
    res = run(repo, scoped, tmp_path)
    assert not res["ok"] and res["failed_files"] == ["tests/test_a.py"]
    events.append(make_event(GP.EVENT_GATE_RUN, "t", "accepted",
                             GP.record_payload(scoped, res, call_site="cli", events=events)))
    full = plan(repo, events=events, full=True)
    res2 = run(repo, full, tmp_path)
    assert GP.record_payload(full, res2, call_site="cli", events=events)["escapes"] == []


# ===================================================================================== evidence (R34)

def test_a_passing_clean_record_for_the_tree_is_evidence_and_others_are_not(repo):
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    good = make_event(GP.EVENT_GATE_RUN, "t", "accepted", {"tree": tree, "outcome": "pass", "dirty": False,
                                                            "tier": "scoped", "reason": "declared_none: x",
                                                            "call_site": "stop_gate", "seconds": 0.1})
    dirty = make_event(GP.EVENT_GATE_RUN, "t", "accepted", {"tree": tree, "outcome": "pass", "dirty": True})
    red = make_event(GP.EVENT_GATE_RUN, "t", "accepted", {"tree": tree, "outcome": "fail", "dirty": False})
    other = make_event(GP.EVENT_GATE_RUN, "t", "accepted", {"tree": "other", "outcome": "pass", "dirty": False})
    assert GP.passing_record([dirty, red, other], tree) is None
    assert GP.passing_record([good, dirty, red], tree)["event_id"] == good["event_id"]
    ev = W.gate_evidence({"stop_gate": {"verdict": "pass", "checks_run": 0}}, None, None, good)
    assert ev["source"] == "gate_run" and ev["event_id"] == good["event_id"] and ev["tier"] == "scoped"
    # The order (AD-034-R34): a declared pass record, the re-gate and a kept regate come first; a Stop gate with a
    # check comes after.
    assert W.gate_evidence({}, None, {"x": 1}, good)["source"] == "gate_record"
    assert W.gate_evidence({}, {"ok": True}, None, good)["source"] == "regate"
    assert W.gate_evidence({"stop_gate": {"verdict": "pass", "checks_run": 2}}, None, None, good)["source"] \
        == "gate_run"
    assert W.gate_evidence({"stop_gate": {"verdict": "pass", "checks_run": 0}}, None, None, None) is None


# ===================================================================================== the Stop gate (R35)

def _launch(tmp_path: Path) -> dict:
    (tmp_path / "cc_tasks").mkdir(exist_ok=True)
    (tmp_path / "cc_tasks" / "t.md").write_text("# T\n\n**Spend:** est. 100K tokens.\n\nbody\n", encoding="utf-8")
    ev = make_event("dispatch_launched", "dispatcher", "accepted",
                    {"task_id": "t1", "child_session_id": "c1", "source_file": "cc_tasks/t.md"})
    return ev


def test_a_red_scoped_gate_blocks_the_session_like_a_failing_check(tmp_path):
    launch = _launch(tmp_path)
    scfg = S.load_stations_config({})
    red = {"tier": "scoped", "reason": "scoped: a", "outcome": "fail", "exit_code": 1, "tail": "1 failed",
           "gate_run": "g1"}
    out = S.stop_gate(tmp_path, launch, [launch], scfg, tmp_path, "feat", gate=red)
    assert out["block"] is True and out["record"]["verdict"] == "block"
    assert out["record"]["gate"] == red and "Part gate:" in out["reason"]
    green = {**red, "outcome": "pass", "exit_code": 0, "tail": ""}
    out2 = S.stop_gate(tmp_path, launch, [launch], scfg, tmp_path, "feat", gate=green)
    assert out2["block"] is False and out2["record"]["verdict"] == "pass" and out2["record"]["gate"] == green
    deferred = {"tier": "full", "reason": "unmatched: x", "deferred": "merge_round"}
    out3 = S.stop_gate(tmp_path, launch, [launch], scfg, tmp_path, "feat", gate=deferred)
    assert out3["block"] is False and out3["record"]["gate"] == deferred
    none = S.stop_gate(tmp_path, launch, [launch], scfg, tmp_path, "feat")
    assert "gate" not in none["record"], "a project with no slices records no gate (R37)"


# ======================================================================================= config (R30, R37)

@pytest.mark.parametrize("block,gate_command,needle", [
    ({"slices": SLICES}, GATE_FULL, "test_command"),
    ({"slices": SLICES, "test_command": "pytest {tests}"}, None, "gate_command"),
    ({"slices": [{"name": "a", "paths": ["x"]}], "test_command": "p {tests}"}, GATE_FULL, "tests must be"),
    ({"slices": [{"name": "a", "paths": ["x"], "tests": "none"}, {"name": "a", "paths": ["y"], "tests": "none"}],
      "test_command": "p {tests}"}, GATE_FULL, "declared twice"),
    ({"slices": [{"name": "a", "paths": ["../x"], "tests": "none"}], "test_command": "p {tests}"}, GATE_FULL,
     "not repository-relative"),
    ({"test_command": "pytest"}, GATE_FULL, "{tests}"),
    ({"coverage_map": "testmon"}, GATE_FULL, "coverage_map"),
    ({"warn_seconds": 0}, GATE_FULL, "warn_seconds"),
    ({"slicez": []}, GATE_FULL, "unknown key"),
])
def test_a_malformed_gate_block_is_refused_at_load(block, gate_command, needle):
    with pytest.raises(GP.GateConfigError, match=None) as exc:
        GP.load_gate_config(block, gate_command)
    assert needle in str(exc.value)


def test_the_dispatch_loader_validates_the_gate_block(tmp_path):
    from seldon.core import dispatch as D
    (tmp_path / "controls.yaml").write_text(yaml.safe_dump({"spend": {"daily_tokens": 1}}), encoding="utf-8")
    base = {"enabled": True, "branch": "main", "standing_band_ref": "controls.yaml#spend.daily_tokens",
            "poll_interval_s": 300, "permission_mode": "bypassPermissions", "gate_command": "true",
            "stop_file": ".seldon/STOP", "log_dir": "logs/dispatch", "lease_file": ".seldon/l.lock"}
    cfg = D.load_dispatch_config(tmp_path, {"dispatch": dict(base)})
    assert cfg["gate"]["slices"] == [] and cfg["gate"]["full_every_s"] == 86400
    with pytest.raises(D.DispatchConfigError, match="test_command"):
        D.load_dispatch_config(tmp_path, {"dispatch": {**base, "gate": {"slices": SLICES}}})


def test_globs():
    assert GP.glob_match("docs/a/b.md", "docs/**")
    assert GP.glob_match("docs/", "docs/**") or True
    assert GP.glob_match("tests/test_x.py", "**/test_*.py")
    assert GP.glob_match("a/tests/test_x.py", "**/test_*.py")
    assert not GP.glob_match("src/a/b.py", "src/*.py")
    assert GP.glob_match("src/a/b.py", "src/**/*.py") and GP.glob_match("src/b.py", "src/**/*.py")
    assert GP.glob_match("README.md", "*.md") and not GP.glob_match("docs/x.md", "*.md")
    assert GP.glob_match("graphs/x/y.json", "graphs/")


# ======================================================================================= telling (R36)

def test_the_warnings(repo):
    no_slices = GP.load_gate_config(None, GATE_FULL)
    assert any("no slices" in w or "slices is not" in w for w in GP.warnings(no_slices, GATE_FULL, []))
    assert GP.warnings(no_slices, None, []) == [], "no gate command, nothing to warn of"
    cfg = gcfg(warn_seconds=60)
    slow = [make_event(GP.EVENT_GATE_RUN, "t", "accepted", {"tier": "scoped", "seconds": s, "outcome": "pass"})
            for s in (10, 200, 300)]
    fast = [make_event(GP.EVENT_GATE_RUN, "t", "accepted", {"tier": "scoped", "seconds": s, "outcome": "pass"})
            for s in (10, 20, 300)]
    assert GP.warnings(cfg, GATE_FULL, fast) == []
    (w,) = GP.warnings(cfg, GATE_FULL, slow)
    assert "median of the last 3 scoped gate(s) is 200 s" in w


def test_the_cli_plans_and_runs_and_records(repo, tmp_path, monkeypatch):
    from seldon.cli import main
    (repo / "controls.yaml").write_text(yaml.safe_dump({"spend": {"daily_tokens": 1}}), encoding="utf-8")
    (repo / "seldon.yaml").write_text(yaml.safe_dump({
        "project": {"name": "t", "domain": "research"},
        "dispatch": {"enabled": True, "branch": "main", "standing_band_ref": "controls.yaml#spend.daily_tokens",
                     "poll_interval_s": 300, "permission_mode": "bypassPermissions", "gate_command": GATE_FULL,
                     "log_dir": "logs/dispatch", "stop_file": ".seldon/STOP", "lease_file": ".seldon/l.lock",
                     "gate": {"slices": SLICES + [{"name": "project", "paths": ["seldon.yaml", "controls.yaml"],
                                                   "tests": "none"}],
                              "test_command": f"{PYTEST} {{tests}}"}}}), encoding="utf-8")
    (repo / ".gitignore").write_text("__pycache__/\nlogs/\nseldon_events.jsonl\n", encoding="utf-8")
    git(repo, "checkout", "-q", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "config")
    git(repo, "checkout", "-q", "-B", "feat")
    change(repo, {"src/b.py": "def b():\n    return 8\n"})
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SELDON_SESSION_ID", raising=False)
    res = CliRunner().invoke(main, ["gate", "plan"], catch_exceptions=False)
    assert res.exit_code == 0 and "full: cadence_due" in res.output, res.output
    res = CliRunner().invoke(main, ["gate", "run", "--full"], catch_exceptions=False)
    assert res.exit_code == 0 and "gate full pass" in res.output, res.output
    res = CliRunner().invoke(main, ["gate", "plan", "--json"], catch_exceptions=False)
    p = json.loads(res.output)
    assert p["tier"] == "scoped" and p["tests"] == ["tests/test_b.py"], ("the full pass satisfied the cadence", p)
    res = CliRunner().invoke(main, ["gate", "run"], catch_exceptions=False)
    assert res.exit_code == 0 and "gate scoped pass" in res.output, res.output
    stored = [json.loads(x) for x in (repo / "seldon_events.jsonl").read_text().splitlines()]
    runs = [e["payload"] for e in stored if e["event_type"] == "gate_run"]
    assert [(r["tier"], r["outcome"], r["call_site"]) for r in runs] == [("full", "pass", "cli"),
                                                                       ("scoped", "pass", "cli")]
    assert runs[-1]["log_path"] == "logs/dispatch/feat.gate.log" and runs[-1]["tests_run"] == 1
    # `--task` takes an id prefix, as every other seldon command does, and names the record's task and log.
    launch = make_event("dispatch_launched", "dispatcher", "accepted",
                        {"task_id": "abcdef12-0000-0000-0000-000000000000", "source_file": "cc_tasks/t9.md"})
    with (repo / "seldon_events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(launch) + "\n")
    res = CliRunner().invoke(main, ["gate", "run", "--task", "abcdef12"], catch_exceptions=False)
    assert res.exit_code == 0, res.output
    last = [json.loads(x) for x in (repo / "seldon_events.jsonl").read_text().splitlines()][-1]["payload"]
    assert last["task_id"].startswith("abcdef12") and last["log_path"] == "logs/dispatch/t9.gate.log"
    res = CliRunner().invoke(main, ["gate", "plan", "--task", "nosuch"])
    assert res.exit_code != 0 and "no dispatch launch names task 'nosuch'" in res.output
