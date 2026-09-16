"""The dispatcher's claim → launch → finish path, end to end, with a stub CC.

`ai-readiness-kg/cc_tasks/2026-09-15_standing_dispatcher.md` §1's second test set, against
DN-006 decisions 4, 5, 6 and 7.

**The stub `claude` is a shell script and the spend is zero.** The launch path is a
`subprocess.run` of whatever `dispatch.cli` names, so a script that writes a RESULT and walks
the task to `completed` exercises the claim, the lease heartbeat, the log, the exit code, the
RESULT check, the graph check and the event pair — with no model call, no network, and nothing
that could contact a host.

These need Neo4j because the claim IS a graph transition: DN-006 decision 4's whole point is
that the claim is a compare-and-set and not a message, and a mocked transition would test the
mock.
"""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core.artifacts import create_artifact
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
SELDON_REPO = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.usefixtures("neo4j_available")


TASK_BODY = textwrap.dedent("""\
    # CC Task — {stem}

    **Date:** 2026-09-15
    **Framework layer served (DN-005 §5 rule 1):** §2.2 Tier M
    **Spend:** zero model calls. **Network:** none.

    ## 1. Do the thing.
    """)


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _git(p: Path, *a):
    return subprocess.run(["git", *a], cwd=p, check=True, capture_output=True, text=True)


@pytest.fixture
def project(tmp_path):
    """A git project with a dispatch block, a task file, a stub `claude` on PATH."""
    p = tmp_path / "proj"
    (p / "cc_tasks").mkdir(parents=True)
    (p / "bin").mkdir()
    _git(p, "init", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    (p / ".gitignore").write_text(".seldon/\nlogs/\nbin/\nseldon_events.jsonl\n",
                                  encoding="utf-8")
    (p / "controls.yaml").write_text(
        yaml.safe_dump({"spend": {"daily_tokens": 55_000_000}}), encoding="utf-8")
    (p / "seldon.yaml").write_text(yaml.safe_dump({
        "event_store": {"path": "seldon_events.jsonl"},
        "neo4j": {"database": NEO4J_DB, "uri": os.getenv("NEO4J_URI",
                                                         "bolt://localhost:7687")},
        "project": {"domain": "research", "name": "t", "slug": "t"},
        "dispatch": {"enabled": True, "branch": "main",
                     "standing_band_ref": "controls.yaml#spend.daily_tokens",
                     "poll_interval_s": 300, "permission_mode": "bypassPermissions",
                     "stop_file": ".seldon/DISPATCH_STOP", "log_dir": "logs/dispatch",
                     "lease_file": ".seldon/dispatch.lock",
                     "cli": str(p / "bin" / "claude")},
    }), encoding="utf-8")
    (p / "cc_tasks" / "t1.md").write_text(TASK_BODY.format(stem="t1"), encoding="utf-8")
    _git(p, "add", "-A")
    _git(p, "commit", "-m", "init")
    return p


def _stub(project: Path, *, exit_code=0, write_result=True, complete=True, task_id=None):
    """A shell script standing in for `claude -p`. Writes what a real CC session writes."""
    lines = ["#!/bin/sh", 'echo "stub cc: $*"']
    if write_result:
        lines.append(f'printf "# RESULT\\n" > {project}/cc_tasks/t1_RESULT.md')
    if complete and task_id:
        lines.append(
            f'{sys_executable()} -c "'
            f"import sys; sys.path.insert(0, {str(SELDON_REPO)!r}); "
            f"from pathlib import Path; "
            f"from seldon.core.artifacts import walk_to_completed; "
            f"from seldon.domain.loader import load_domain_config; "
            f"from seldon.config import get_neo4j_driver; "
            f"cfg={{'neo4j': {{'uri': {os.getenv('NEO4J_URI', 'bolt://localhost:7687')!r}, "
            f"'database': {NEO4J_DB!r}}}}}; "
            f"d=get_neo4j_driver(cfg); "
            f"walk_to_completed(project_dir=Path({str(project)!r}), driver=d, "
            f"database={NEO4J_DB!r}, "
            f"domain_config=load_domain_config(Path({str(RESEARCH_YAML)!r})), "
            f"artifact_id={task_id!r}, current_state='in_progress', actor='cc'); "
            f'd.close()"')
    lines.append(f"exit {exit_code}")
    path = project / "bin" / "claude"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def sys_executable() -> str:
    import sys
    return sys.executable


def _register(project, driver, domain_config, rel="cc_tasks/t1.md") -> str:
    return create_artifact(
        project_dir=project, driver=driver, database=NEO4J_DB, domain_config=domain_config,
        artifact_type="ResearchTask",
        properties={"description": "stub task", "name": "t1", "source_file": rel,
                    "created_at": "2026-09-15T00:00:00Z"},
        actor="desktop", authority="accepted")


def _run(project, argv):
    """Invoke the CLI with cwd at the project, as launchd would."""
    prev = Path.cwd()
    os.chdir(project)
    try:
        return CliRunner().invoke(dispatch_group, argv, catch_exceptions=False)
    finally:
        os.chdir(prev)


def _state(driver, task_id):
    with driver.session(database=NEO4J_DB) as s:
        r = s.run("MATCH (t:ResearchTask {artifact_id:$i}) RETURN t.state AS s, "
                  "t.claimed_by AS by", i=task_id).single()
    return (r["s"], r["by"]) if r else (None, None)


def _events(project, kind=None):
    evs = read_events(project)
    return [e for e in evs if kind is None or e["event_type"] == kind]


# ================================================================ the whole path, once, green

def test_a_clean_task_is_claimed_launched_and_finished(project, neo4j_driver, domain_config,
                                                       clean_test_db, monkeypatch):
    """DN-006 decisions 4, 5 and 7 in one pass: the claim walks `proposed → accepted →
    in_progress` with `claimed_by = dispatcher:<host>:<pid>`, the launch writes the log with
    `EXIT=`, and the finish records exit code, wall clock, RESULT presence and graph state."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)

    res = _run(project, ["once"])
    assert res.exit_code == 0, res.output

    state, by = _state(neo4j_driver, tid)
    assert state == "completed"
    assert by.startswith("dispatcher:")

    launched = _events(project, D.EVENT_LAUNCHED)
    assert len(launched) == 1
    pl = launched[0]["payload"]
    assert pl["task_id"] == tid
    assert pl["transitions"] == ["proposed -> accepted", "accepted -> in_progress"]
    assert pl["framework_layer"].startswith("§2.2")
    assert pl["permission_mode"] == "bypassPermissions"
    assert set(pl["criteria"]) == {f"c{i}" for i in range(1, 10)}
    assert all(c["ok"] for c in pl["criteria"].values())
    assert "--permission-mode bypassPermissions" in pl["command"]

    finished = _events(project, D.EVENT_FINISHED)
    assert len(finished) == 1
    fl = finished[0]["payload"]
    assert fl["exit_code"] == 0 and fl["result_present"] is True
    assert fl["graph_state_observed"] == "completed" and fl["ok"] is True
    assert isinstance(fl["wall_clock_s"], float)

    log = project / "logs" / "dispatch" / "t1.log"
    assert log.is_file()
    text = log.read_text(encoding="utf-8")
    assert "EXIT=0" in text and "stub cc:" in text
    assert "Read CLAUDE.md, then execute cc_tasks/t1.md" in text


def test_the_launch_runs_from_the_project_root_so_claude_md_loads(project, neo4j_driver,
                                                                  domain_config,
                                                                  clean_test_db, monkeypatch):
    """The inverse of `kg/extraction/model_stub.py`'s hermetic cwd (DN-006 decision 5). That
    one exists so a JSON-only call does not narrate; here the narration is the point, and a
    session started outside the project root would not load the protocol it is being told to
    follow."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    stub = _stub(project, task_id=tid)
    stub.write_text("#!/bin/sh\npwd\nprintf '# R\\n' > cc_tasks/t1_RESULT.md\nexit 1\n",
                    encoding="utf-8")
    stub.chmod(0o755)
    _run(project, ["once"])
    log = (project / "logs" / "dispatch" / "t1.log").read_text(encoding="utf-8")
    assert str(project.resolve()) in log


# ================================================================== the blocked path, no retry

def test_a_failing_session_blocks_the_task_and_is_never_retried(project, neo4j_driver,
                                                                domain_config, clean_test_db,
                                                                monkeypatch):
    """DN-006 decision 4's last clause, and the assertion the task file asks for by name: run
    the failing stub twice and see ONE launch.

    A retry is a decision. A loop that cannot see why the last attempt failed cannot make it,
    and would spend a full CC session on each guess.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, exit_code=3, write_result=False, complete=False)

    first = _run(project, ["once"])
    assert first.exit_code == 0
    assert _state(neo4j_driver, tid)[0] == "blocked"
    fl = _events(project, D.EVENT_FINISHED)[0]["payload"]
    assert fl["exit_code"] == 3 and fl["result_present"] is False
    assert fl["graph_state_observed"] == "in_progress" and fl["ok"] is False
    assert fl["log_path"] == "logs/dispatch/t1.log"

    second = _run(project, ["once"])
    assert second.exit_code == 0
    assert len(_events(project, D.EVENT_LAUNCHED)) == 1, "the dispatcher retried"
    assert len(_events(project, D.EVENT_FINISHED)) == 1
    assert _state(neo4j_driver, tid)[0] == "blocked"


def test_a_zero_exit_with_no_result_file_still_blocks(project, neo4j_driver, domain_config,
                                                      clean_test_db, monkeypatch):
    """Exit 0 is not completion. A session that returned cleanly and wrote no RESULT has left
    no execution record, which is the state CLAUDE.md's "the RESULT waits for the suite" rule
    exists to make impossible."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, exit_code=0, write_result=False, complete=False)
    _run(project, ["once"])
    assert _state(neo4j_driver, tid)[0] == "blocked"
    assert _events(project, D.EVENT_FINISHED)[0]["payload"]["result_present"] is False


def test_a_result_without_a_completed_graph_state_still_blocks(project, neo4j_driver,
                                                               domain_config, clean_test_db,
                                                               monkeypatch):
    """The CC session runs `seldon cc complete` itself, per protocol. A RESULT on disk with the
    task still `in_progress` is a session that wrote its record and never closed the task."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, exit_code=0, write_result=True, complete=False)
    _run(project, ["once"])
    assert _state(neo4j_driver, tid)[0] == "blocked"
    fl = _events(project, D.EVENT_FINISHED)[0]["payload"]
    assert fl["result_present"] is True and fl["graph_state_observed"] == "in_progress"


# ============================================================ the kill switches and the lease

def test_disabled_writes_no_event_and_launches_nothing(project, neo4j_driver, domain_config,
                                                       clean_test_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _register(project, neo4j_driver, domain_config)
    _stub(project)
    doc = yaml.safe_load((project / "seldon.yaml").read_text())
    doc["dispatch"]["enabled"] = False
    (project / "seldon.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    before = (project / "seldon_events.jsonl").read_bytes() if (
        project / "seldon_events.jsonl").exists() else b""
    res = _run(project, ["once"])
    assert res.exit_code == 0 and "disabled" in res.output
    after = (project / "seldon_events.jsonl").read_bytes() if (
        project / "seldon_events.jsonl").exists() else b""
    assert after == before
    assert not (project / "logs" / "dispatch").exists()


def test_a_stop_file_is_observed_once_per_appearance(project, neo4j_driver, domain_config,
                                                     clean_test_db, monkeypatch):
    """The burn's STOP idiom. One event per APPEARANCE, not one per pass: a five-minute poll
    that logged its own silence would bury every assertion in it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _register(project, neo4j_driver, domain_config)
    _stub(project)
    (project / ".seldon").mkdir(exist_ok=True)
    stop = project / ".seldon" / "DISPATCH_STOP"
    stop.write_text("operator", encoding="utf-8")
    _run(project, ["once"])
    _run(project, ["once"])
    assert len(_events(project, D.EVENT_OBSERVED_STOP)) == 1
    assert not _events(project, D.EVENT_LAUNCHED)


def test_a_second_pass_refuses_on_the_lease_and_exits_zero(project, neo4j_driver,
                                                           domain_config, clean_test_db,
                                                           monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _register(project, neo4j_driver, domain_config)
    _stub(project)
    with D.Lease(project / ".seldon" / "dispatch.lock"):
        res = _run(project, ["once"])
    assert res.exit_code == 0
    refused = _events(project, D.EVENT_REFUSED)
    assert [r["payload"]["reason"] for r in refused] == ["lease_held"]
    assert not _events(project, D.EVENT_LAUNCHED)


def test_an_api_key_refuses_before_any_claim(project, neo4j_driver, domain_config,
                                             clean_test_db, monkeypatch):
    """DD-007. Before the lease and before the claim, so a refusal leaves no state change at
    all — the task is still `proposed` when the operator unsets the variable."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-not-a-real-key")
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project)
    res = _run(project, ["once"])
    assert res.exit_code == 0
    assert _state(neo4j_driver, tid)[0] == "proposed"
    assert [r["payload"]["reason"] for r in _events(project, D.EVENT_REFUSED)] == \
        ["api_key_present"]
    assert not (project / ".seldon" / "dispatch.lock").exists()


def test_a_pass_with_nothing_eligible_writes_no_event(project, neo4j_driver, domain_config,
                                                      clean_test_db, monkeypatch):
    """DN-006 decision 7, asserted by BYTE comparison as the task file asks. The log records
    assertions; "nothing to do" is not one."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Registered, but its file is not a candidate: no headers at all. The companion case — a
    # real CANDIDATE blocked by a standing condition — is
    # `test_a_dirty_tree_refuses_the_candidate_names_the_paths_and_writes_no_event`, and it is
    # the case this test alone did not cover, which is how the defect it now guards survived.
    (project / "cc_tasks" / "bare.md").write_text("# bare task\n\nno headers here\n",
                                                  encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-m", "bare")
    _register(project, neo4j_driver, domain_config, rel="cc_tasks/bare.md")
    _stub(project)
    log = project / "seldon_events.jsonl"
    before = log.read_bytes() if log.exists() else b""
    res = _run(project, ["once"])
    assert res.exit_code == 0 and "nothing eligible" in res.output
    after = log.read_bytes() if log.exists() else b""
    assert after == before, "a pass with nothing eligible wrote to the log"


def test_a_dirty_tree_refuses_the_candidate_names_the_paths_and_writes_no_event(
        project, neo4j_driver, domain_config, clean_test_db, monkeypatch):
    """A refusal on a STANDING CONDITION is reported, not logged.

    `dirty_tree` is true for as long as a session is working in the checkout, and a pass fires
    every five minutes. One event per blocked candidate per pass is the poll logging its own
    silence — which decision 7 forbids — and here it feeds itself: the event store is a tracked
    file, so writing to it keeps the tree dirty, which keeps the refusal true.

    Nothing is lost. The reason and its whole criteria vector are live properties that
    `status` computes on demand, and this pass names them on stdout, which is what the launchd
    wrapper's log carries."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project)
    (project / "scratch.txt").write_text("x", encoding="utf-8")
    log = project / "seldon_events.jsonl"
    before = log.read_bytes() if log.exists() else b""

    res = _run(project, ["once"])
    assert res.exit_code == 0
    assert _state(neo4j_driver, tid)[0] == "proposed"
    assert "nothing eligible" in res.output
    assert "dirty_tree" in res.output and "cc_tasks/t1.md" in res.output

    after = log.read_bytes() if log.exists() else b""
    assert after == before, "a standing-condition refusal was written to the log"
    assert not _events(project, D.EVENT_REFUSED)

    # `status` still has the whole vector, values and all.
    out = _run(project, ["status"]).output
    assert '"dirty_paths": ["scratch.txt"]' in out


def test_ten_passes_over_a_dirty_tree_leave_the_log_byte_identical(
        project, neo4j_driver, domain_config, clean_test_db, monkeypatch):
    """The condition that made the old behaviour a defect, at the scale it happens on: a
    five-minute poll across a two-hour session is twenty-four passes. The log must be the same
    bytes after all of them."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _register(project, neo4j_driver, domain_config)
    _stub(project)
    (project / "scratch.txt").write_text("x", encoding="utf-8")
    log = project / "seldon_events.jsonl"
    before = log.read_bytes() if log.exists() else b""
    for _ in range(10):
        assert _run(project, ["once"]).exit_code == 0
    after = log.read_bytes() if log.exists() else b""
    assert after == before


# ==================================================================================== status

def test_status_writes_no_event_and_reports_the_vector(project, neo4j_driver, domain_config,
                                                       clean_test_db, monkeypatch):
    """`status` is the operator's eye. Looking is not an assertion, so it writes nothing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    log = project / "seldon_events.jsonl"
    before = log.read_bytes() if log.exists() else b""
    res = _run(project, ["status", "--json"])
    assert res.exit_code == 0
    after = log.read_bytes() if log.exists() else b""
    assert after == before
    payload = json.loads(res.output)
    assert payload["standing_band"] == 55_000_000
    assert payload["eligible"] == [tid]
    assert payload["tasks"][0]["criteria"]["c4"]["declared_tokens"] == 0


def test_status_renders_a_non_candidate_without_a_criteria_vector(project, neo4j_driver,
                                                                  domain_config,
                                                                  clean_test_db):
    (project / "cc_tasks" / "bare.md").write_text("# bare\n", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-m", "bare")
    _register(project, neo4j_driver, domain_config, rel="cc_tasks/bare.md")
    res = _run(project, ["status"])
    assert "NOT A CANDIDATE" in res.output
    assert "no_header:Spend,Network,Framework layer served" in res.output


def test_lease_reap_refuses_a_live_holder_through_the_cli(project, neo4j_driver, domain_config,
                                                          clean_test_db):
    lock = project / ".seldon" / "dispatch.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"holder": f"dispatcher:h:{os.getpid()}", "pid": os.getpid()}),
                    encoding="utf-8")
    prev = Path.cwd()
    os.chdir(project)
    try:
        res = CliRunner().invoke(dispatch_group, ["lease", "reap"])
    finally:
        os.chdir(prev)
    assert res.exit_code == 1
    assert "holder_alive" in res.output
    assert lock.is_file()
