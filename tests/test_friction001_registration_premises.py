"""FRICTION-001 Part E (AD-038-R5 and R6): registration runs premises; an outage is a refusal; toil is charted.

* **R5.** Registration validated headers and criterion marks but ran no `check:` premise, so the first evaluation
  was at dispatch: SQ-016's mistyped path waited 19 hours to be found. Now a false premise refuses registration with
  the command's output, before anything is created.
* **R6, Issue 59b2db84.** On 2026-10-15 a Neo4j outage made every dispatcher pass crash with a `DatabaseUnavailable`
  traceback (rc=1) for five hours and nothing reached the operator. Now a pass that cannot reach the database is a
  handled refusal (exit 0) with ONE `dispatch_refused` and ONE stuck notification per outage.
* **R6, the toil measure.** `seldon qc chart` reports per week the passes refused on machine dirt and the operator's
  interventions (redrives, Desktop restarts inferred from `server_stale` refusals, tasks superseded unlaunched).

Each test fails on main 92f491b, where none of the three exists.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.cc import cc_group
from seldon.commands.dispatch import dispatch_group
from seldon.core import stations as S
from seldon.core.events import make_event, read_events
from tests.dispatch_scaffold import make_project, run_cli
from tests.testdb import TEST_DATABASE

TASK = """# CC Task: premise probe

**Implements:** DN-006
**Premises:**
- premise: the predecessor's module exists | check: `test -f seldon/core/reconcile.py`
- premise: the README is there | check: `test -f README.md`

A task registered with premises.
"""


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(tmp_path, *args)
    (tmp_path / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {TEST_DATABASE}\n  uri: {os.getenv('NEO4J_URI', 'bolt://localhost:7687')}\n"
        f"event_store:\n  path: seldon_events.jsonl\n", encoding="utf-8")
    (tmp_path / "cc_tasks").mkdir()
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    (tmp_path / "cc_tasks" / "probe.md").write_text(TASK, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _register(repo: Path):
    prev = Path.cwd()
    os.chdir(repo)
    try:
        return CliRunner().invoke(cc_group, ["register", "cc_tasks/probe.md"], catch_exceptions=False)
    finally:
        os.chdir(prev)


# ================================================================================ R5: premises at registration

@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_a_false_premise_refuses_registration_with_its_output(repo, neo4j_driver):
    out = _register(repo)
    assert out.exit_code != 0, out.output
    assert "premise_false" in out.output, out.output
    assert "`test -f seldon/core/reconcile.py` is false (exit 1)" in out.output, out.output
    assert "the predecessor's module exists" in out.output
    assert "README" not in out.output.split("premise_false", 1)[1].split("File:")[0]   # only the false one is named
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        assert s.run("MATCH (t:ResearchTask) RETURN count(t) AS n").single()["n"] == 0


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_true_premises_register(repo, neo4j_driver):
    (repo / "seldon" / "core").mkdir(parents=True)
    (repo / "seldon" / "core" / "reconcile.py").write_text("", encoding="utf-8")
    out = _register(repo)
    assert out.exit_code == 0, out.output
    assert "Registered" in out.output, out.output


def test_an_unrunnable_premise_refuses_too(tmp_path):
    task = tmp_path / "t.md"
    task.write_text("**Premises:**\n- premise: a tool | check: `no-such-binary-anywhere --x`\n", encoding="utf-8")
    why = S.premises_registration_refusal(task, tmp_path, {})
    assert why and "is unrunnable (exit 127)" in why, why
    task.write_text("# no premises\n", encoding="utf-8")
    assert S.premises_registration_refusal(task, tmp_path, {}) is None


# ======================================================================== R6: a database outage is a refusal

@pytest.fixture
def dispatch_project(tmp_path, monkeypatch, neo4j_available):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    p = tmp_path / "x"
    p = make_project(tmp_path, dispatch_extra={
        "notify": f"echo \"$SELDON_NOTIFY_OUTCOME $SELDON_NOTIFY_CRITERION\" >> {tmp_path}/notify.log"})
    return p


def _outage(monkeypatch, on: bool):
    import seldon.commands.dispatch as dispatch_cmd
    from neo4j.exceptions import DatabaseUnavailable

    def down(*_a, **_k):
        raise DatabaseUnavailable("{code: Neo.TransientError.General.DatabaseUnavailable} "
                                  "{message: The database is not currently available to serve your request}")
    if on:
        monkeypatch.setattr(dispatch_cmd, "_claim_in_flight", down)
    else:
        monkeypatch.undo()


def test_an_outage_is_one_refusal_and_one_notification_not_a_traceback(dispatch_project, monkeypatch, tmp_path):
    p = dispatch_project
    _outage(monkeypatch, True)
    first = run_cli(p, dispatch_group, ["once"])
    second = run_cli(p, dispatch_group, ["once"])
    assert first.exit_code == 0 and second.exit_code == 0, first.output + second.output
    assert "Traceback" not in first.output + second.output
    assert "database_unavailable" in second.output and "pass 2 of this outage" in second.output
    refused = [e for e in read_events(p) if e["event_type"] == "dispatch_refused"
               and e["payload"]["reason"] == "database_unavailable"]
    assert len(refused) == 1, refused
    assert (tmp_path / "notify.log").read_text().splitlines() == ["stuck database_unavailable"]

    _outage(monkeypatch, False)
    back = run_cli(p, dispatch_group, ["once"])
    assert back.exit_code == 0, back.output
    assert "database available again after 2 refused pass(es)" in back.output, back.output

    _outage(monkeypatch, True)                                   # a new outage alarms afresh
    run_cli(p, dispatch_group, ["once"])
    assert len([e for e in read_events(p) if e["event_type"] == "dispatch_refused"
                and e["payload"]["reason"] == "database_unavailable"]) == 2
    assert len((tmp_path / "notify.log").read_text().splitlines()) == 2


# ================================================================================== R6: the toil measure

LOG = """=== 2026-10-12T10:00:00Z | seldon-dispatch fire
nothing eligible (2 open, 1 candidate(s))
  0db82f70 dirty_tree: c7  cc_tasks/t1.md
      dirty: seldon_events.jsonl, state/prior_art_queries.jsonl
=== rc=0
=== 2026-10-12T10:05:00Z | seldon-dispatch fire
nothing eligible (2 open, 1 candidate(s))
  0db82f70 dirty_tree: c7  cc_tasks/t1.md
      dirty: seldon/core/dispatch.py
=== rc=0
=== 2026-10-19T10:00:00Z | seldon-dispatch fire
nothing eligible (2 open, 1 candidate(s))
  0db82f70 dirty_tree: c7  cc_tasks/t1.md
      dirty: seldon_events.jsonl
      unreconciled: seldon_events.jsonl: not append-only against HEAD (edited in place)
=== rc=0
=== 2026-10-19T10:05:00Z | seldon-dispatch fire
nothing eligible (2 open, 0 candidate(s))
=== rc=0
"""


def _ev(kind, actor, ts, **payload):
    e = make_event(kind, actor, "accepted", payload)
    e["timestamp"] = ts
    return e


def test_the_toil_measure_counts_each_week(tmp_path):
    from seldon.core import toil as T
    log = tmp_path / "seldon_dispatch.log"
    log.write_text(LOG, encoding="utf-8")
    stale = tmp_path / "mcp_stale.jsonl"
    stale.write_text("\n".join(json.dumps(r) for r in [
        {"at": "2026-10-13T01:00:00Z", "pid": 1, "loaded_head": "a", "loaded_at": "x"},
        {"at": "2026-10-13T01:05:00Z", "pid": 1, "loaded_head": "a", "loaded_at": "x"},   # same server: one restart
        {"at": "2026-10-14T09:00:00Z", "pid": 2, "loaded_head": "b", "loaded_at": "y"},
    ]) + "\n", encoding="utf-8")
    events = [
        _ev("dispatch_launched", "dispatcher", "2026-10-12T09:00:00Z", task_id="launched-1"),
        _ev("artifact_state_changed", "desktop", "2026-10-16T00:00:00Z", artifact_id="never-1",
            artifact_type="ResearchTask", to_state="superseded"),
        _ev("artifact_state_changed", "desktop", "2026-10-16T00:00:00Z", artifact_id="launched-1",
            artifact_type="ResearchTask", to_state="superseded"),
        _ev("dispatch_redrive", "desktop", "2026-10-20T00:00:00Z", task_id="z"),
        _ev("dispatch_redrive", "dispatcher", "2026-10-20T00:00:00Z", task_id="z"),
    ]
    gp = {"event_store": "seldon_events.jsonl", "query_log": "state/prior_art_queries.jsonl",
          "verdict_ledger": "governed/ledger/events.jsonl", "register_dir": "docs/decisions/register",
          "rendered": "docs/decisions/REGISTER.md"}
    got = {w["week"]: w for w in T.toil(events, [log], gp, stale)["weeks"]}
    assert got["2026-W42"] == {"week": "2026-W42", "refused_machine_dirt": 1, "refused_other_dirt": 1,
                               "redrives_by_operator": 0, "desktop_restarts": 2, "reissued_tasks": 1,
                               "interventions": 3}
    assert got["2026-W43"] == {"week": "2026-W43", "refused_machine_dirt": 0, "refused_other_dirt": 1,
                               "redrives_by_operator": 1, "desktop_restarts": 0, "reissued_tasks": 0,
                               "interventions": 1}


def test_qc_chart_prints_the_toil_reading(tmp_path, monkeypatch):
    from seldon.commands.qc import qc_group
    p = tmp_path / "proj"
    (p / "logs").mkdir(parents=True)
    (p / "logs" / "seldon_dispatch.log").write_text(LOG, encoding="utf-8")
    (p / "seldon_events.jsonl").write_text("", encoding="utf-8")
    (p / "seldon.yaml").write_text(yaml.safe_dump({
        "project": {"name": "t", "domain": "research"}, "event_store": {"path": "seldon_events.jsonl"},
        "neo4j": {"database": TEST_DATABASE, "uri": "bolt://localhost:7687"},
        "qc": {"chart_min_points": 10, "toil": {"dispatch_log": "logs/seldon_dispatch.log"}}}), encoding="utf-8")
    out = run_cli(p, qc_group, ["chart"])
    assert out.exit_code == 0, out.output
    assert "toil per week" in out.output, out.output
    # No `prior_art:` block here, so the query log is not a governed path and both W42 refusals are other dirt.
    rows = {ln.split()[0]: ln.split()[1:] for ln in out.output.splitlines() if ln.strip().startswith("2026-W")}
    assert rows == {"2026-W42": ["0", "2", "0", "0", "0", "0"], "2026-W43": ["0", "1", "0", "0", "0", "0"]}, rows
