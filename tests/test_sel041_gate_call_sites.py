"""SEL-041 Part C: the gate's call sites go through the planner (AD-034-R35), and a project with no slices gates as it
did before (R37), with its run now recorded (R33).

`cc_tasks/2026-11-21_SEL-041_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points.md`
and its ADDENDUM 01 item 2: the merge round's evidence gate (AD-034-R26's `merge_gate`) is the call site a check-less
task meets, so a documents-only task must merge on a scoped plan without running the full `gate_command`.

The scaffold's gate command here is `false`: any task the round gates in full is red, so a merge proves the round ran
the scoped tier.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from seldon.commands import dispatch_worktree as W
from seldon.core import dispatch as D
from seldon.core import gate_plan as GP
from seldon.core.events import make_event, read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import NEO4J_DB, RESEARCH_YAML, add_task, git, make_project, register, run_cli, \
    write_stub
from seldon.commands.dispatch import dispatch_group

SLICES = {
    "slices": [
        {"name": "records", "paths": ["cc_tasks/**", "seldon_events.jsonl", "docs/**"], "tests": "none"},
        {"name": "lint", "paths": ["lintme/**"], "tests": "none", "commands": ["test -f lintme/ok"]},
    ],
    "test_command": "true {tests}",
}


@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _once(p):
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    return res.output


def _finished(p, stem):
    return [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_FINISHED
            and e["payload"].get("source_file") == f"cc_tasks/{stem}.md"]


def _gate_runs(p):
    return [e["payload"] for e in read_events(p) if e["event_type"] == GP.EVENT_GATE_RUN]


def _on_main(p, rel) -> bool:
    return subprocess.run(["git", "-C", str(p), "cat-file", "-e", f"main:{rel}"],
                          capture_output=True).returncode == 0


def _sliced_project(tmp_path, gate_command="false"):
    """A scaffold project with slices, a gate command, and a recent passing full gate on record (so the cadence does
    not promote the first gate to full)."""
    p = make_project(tmp_path, dispatch_extra={"gate_command": gate_command, "gate": SLICES})
    ev = make_event(GP.EVENT_GATE_RUN, "t", "accepted", {"tier": "full", "outcome": "pass", "seconds": 1.0,
                                                          "tree": "seed", "change_set": "seed"})
    with (p / "seldon_events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev) + "\n")
    git(p, "add", "seldon_events.jsonl")
    git(p, "commit", "-q", "-m", "seed a passing full gate")
    return p


@pytest.mark.usefixtures("neo4j_available")
def test_a_documents_only_task_merges_on_a_scoped_gate_without_the_full_suite(tmp_path, neo4j_driver, dc):
    p = _sliced_project(tmp_path)
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-11-21T00:00:01Z")
    write_stub(p, {"a": {"write": {"docs/slide.md": "one slide\n"}, "worktree_name": "a"}})
    _once(p)
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merged", fin
    ev = fin["merge"]["gate_evidence"]
    assert ev["source"] == "merge_gate" and ev["gate"]["tier"] == "scoped", ev
    assert ev["gate"]["reason"].startswith("declared_none"), ev
    (run,) = [e for e in read_events(p) if e["event_type"] == GP.EVENT_GATE_RUN
              and e["payload"].get("call_site") == "merge_gate"]
    assert run["payload"]["tier"] == "scoped" and run["payload"]["outcome"] == "pass"
    assert run["payload"]["steps"] == [], "nothing selected, nothing run: the full `false` never ran"
    assert ev["gate"]["gate_run"] == run["event_id"], "the evidence names the record (R33)"
    assert _on_main(p, "docs/slide.md")


@pytest.mark.usefixtures("neo4j_available")
def test_a_sliced_command_runs_and_a_red_one_keeps_the_branch_off_main(tmp_path, neo4j_driver, dc):
    p = _sliced_project(tmp_path)
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-11-21T00:00:01Z")
    write_stub(p, {"a": {"write": {"lintme/x.txt": "x\n"}, "worktree_name": "a"}})
    _once(p)
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merge_blocked" and fin["merge"]["reason"] == "regate_red", fin
    (run,) = [r for r in _gate_runs(p) if r.get("call_site") == "merge_gate"]
    assert run["tier"] == "scoped" and run["commands"] == ["test -f lintme/ok"] and run["outcome"] == "fail"


@pytest.mark.usefixtures("neo4j_available")
def test_an_unmatched_path_makes_the_merge_gate_full_and_says_why(tmp_path, neo4j_driver, dc):
    p = _sliced_project(tmp_path)
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-11-21T00:00:01Z")
    write_stub(p, {"a": {"write": {"out/a.txt": "a\n"}, "worktree_name": "a"}})
    _once(p)
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merge_blocked" and fin["merge"]["reason"] == "regate_red", fin
    assert fin["merge"]["gate"]["tier"] == "full" and fin["merge"]["gate"]["reason"] == "unmatched: out/a.txt"
    assert not _on_main(p, "out/a.txt")


@pytest.mark.usefixtures("neo4j_available")
def test_a_project_without_slices_runs_its_gate_command_and_records_it(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)          # `gate_command: true`, no slices
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-11-21T00:00:01Z")
    write_stub(p, {"a": {"write": {"docs/slide.md": "one slide\n"}, "worktree_name": "a"}})
    _once(p)
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merged" and fin["merge"]["gate_evidence"]["source"] == "merge_gate"
    (run,) = _gate_runs(p)
    assert (run["tier"], run["reason"], run["call_site"], run["outcome"]) == ("full", "no_slices", "merge_gate",
                                                                              "pass")
    log = (p / "logs" / "dispatch" / "a.gate.log").read_text()
    assert log.splitlines()[0].endswith("| gate | true"), "the pre-addendum gate log, unchanged"


def test_the_regate_helper_plans_records_and_names_its_call_site(tmp_path):
    """`_gate` at the re-gate call site, on a plain checkout: scoped, recorded, `call_site: regate`."""
    p = tmp_path / "r"
    p.mkdir()
    git(p, "init", "-q", "-b", "main")
    git(p, "config", "user.email", "t@t")
    git(p, "config", "user.name", "t")
    (p / ".gitignore").write_text("logs/\nseldon_events.jsonl\n", encoding="utf-8")
    (p / "docs").mkdir()
    (p / "docs" / "a.md").write_text("a\n", encoding="utf-8")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "init")
    git(p, "checkout", "-q", "-b", "feat")
    (p / "docs" / "a.md").write_text("b\n", encoding="utf-8")
    git(p, "commit", "-q", "-am", "doc")
    seed = make_event(GP.EVENT_GATE_RUN, "t", "accepted", {"tier": "full", "outcome": "pass", "seconds": 1.0})
    (p / "seldon_events.jsonl").write_text(json.dumps(seed) + "\n", encoding="utf-8")
    cfg = {"gate_command": "false", "log_dir": "logs/dispatch", "gate_timeout_s": 60,
           "gate": GP.load_gate_config(SLICES, "false")}
    (p / "logs" / "dispatch").mkdir(parents=True)
    main_sha = git(p, "rev-parse", "main").stdout.strip()
    out = W._gate(p, cfg, p, "t", call_site="regate", base=main_sha, task_id="t1", branch="feat")
    assert out["ok"] and out["tier"] == "scoped", out
    run = _gate_runs(p)[-1]
    assert run["call_site"] == "regate" and run["task_id"] == "t1" and run["tier"] == "scoped"
    assert run["log_path"] == "logs/dispatch/t.gate.log"
