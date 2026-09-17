"""An event's `session_id` names the process that wrote it, not a file nobody closed.

`ai-readiness-kg/cc_tasks/2026-09-16_session_id_names_the_process.md` decisions 1, 3 and 4.
Decision 2 (the dispatcher propagates and records the child's id) is tested beside the rest of
the launch path in `tests/test_dispatch_launch.py`.

The defect: `.seldon/current_session.json` was written by `seldon briefing`, removed only by
`seldon closeout`, and read by every writer. One project's file held the same id for three
weeks, and 34,137 of 34,777 events carried it across three actors. Prior art for the shape
below: a trace identity is created at the root process and propagated to children through the
environment (W3C Trace Context; OpenTelemetry context propagation), and a file standing in for a
live holder has bounded authority (Chubby, Burrows OSDI 2006).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

import seldon.config as config
from seldon.config import (
    SESSION_FILE_MAX_AGE,
    bind_process_session,
    get_current_session,
    get_current_session_data,
    start_session,
)
from seldon.core.events import make_event, read_events
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE


def _write_session_file(project_dir: Path, session_id: str, started_at: datetime) -> Path:
    path = project_dir / ".seldon" / "current_session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "session_id": session_id,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
    }))
    return path


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ================================================================ decision 1: resolution order

def test_the_bound_is_one_working_day():
    assert SESSION_FILE_MAX_AGE == timedelta(hours=24)


def test_seldon_session_id_wins_over_everything(tmp_path, monkeypatch):
    _write_session_file(tmp_path, "file-id", _now())
    bind_process_session("process-id")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "cc-id")
    monkeypatch.setenv("SELDON_SESSION_ID", "seldon-id")
    assert get_current_session(tmp_path) == "seldon-id"


def test_claude_code_session_id_wins_over_the_process_and_the_file(tmp_path, monkeypatch):
    _write_session_file(tmp_path, "file-id", _now())
    bind_process_session("process-id")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "cc-id")
    assert get_current_session(tmp_path) == "cc-id"


def test_an_empty_environment_value_is_not_an_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SELDON_SESSION_ID", "")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "cc-id")
    assert get_current_session(tmp_path) == "cc-id"


def test_the_process_id_wins_over_the_file(tmp_path):
    _write_session_file(tmp_path, "file-id", _now())
    bind_process_session("process-id")
    assert get_current_session(tmp_path) == "process-id"


def test_bind_generates_once_and_is_stable():
    first = bind_process_session()
    assert first
    assert bind_process_session() == first
    assert config.process_session_id() == first


def test_a_fresh_file_is_honoured(tmp_path):
    _write_session_file(tmp_path, "file-id", _now() - timedelta(hours=23))
    assert get_current_session(tmp_path) == "file-id"


def test_a_stale_file_is_not_evidence_of_a_live_session(tmp_path):
    path = _write_session_file(tmp_path, "87ea77ee-stale", _now() - timedelta(hours=25))
    sid = get_current_session(tmp_path)
    assert sid != "87ea77ee-stale"
    # The fresh id is written, so the next call in the same working day agrees with this one.
    assert json.loads(path.read_text())["session_id"] == sid
    assert get_current_session(tmp_path) == sid


def test_a_file_with_no_usable_started_at_is_stale(tmp_path):
    path = tmp_path / ".seldon" / "current_session.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"session_id": "no-date"}))
    assert get_current_session(tmp_path) != "no-date"


def test_no_file_yields_a_fresh_id_written_to_the_file(tmp_path):
    assert get_current_session_data(tmp_path) is None
    sid = get_current_session(tmp_path)
    assert sid
    assert get_current_session_data(tmp_path)["session_id"] == sid


def test_start_session_replaces_a_stale_file(tmp_path):
    _write_session_file(tmp_path, "stale", _now() - timedelta(days=25))
    assert start_session(tmp_path) != "stale"


def test_start_session_keeps_a_fresh_file(tmp_path):
    _write_session_file(tmp_path, "fresh", _now())
    assert start_session(tmp_path) == "fresh"


def test_make_event_without_an_id_takes_the_environment(monkeypatch):
    monkeypatch.setenv("SELDON_SESSION_ID", "seldon-id")
    assert make_event("x", "cc", "accepted", {})["session_id"] == "seldon-id"


def test_make_event_without_an_id_takes_the_process_id():
    bind_process_session("process-id")
    assert make_event("x", "desktop", "accepted", {})["session_id"] == "process-id"


def test_make_event_keeps_an_explicit_id(monkeypatch):
    monkeypatch.setenv("SELDON_SESSION_ID", "seldon-id")
    assert make_event("x", "cc", "accepted", {}, session_id="given")["session_id"] == "given"


def test_the_mcp_server_binds_one_id_for_its_lifetime(monkeypatch):
    """Case (c): calls arriving over MCP share the server process's id."""
    from seldon import mcp_server

    monkeypatch.setattr(mcp_server.mcp, "run", lambda **kw: None)
    mcp_server.main()
    bound = config.process_session_id()
    assert bound
    first = make_event("a", "desktop", "accepted", {})["session_id"]
    second = make_event("b", "desktop", "accepted", {})["session_id"]
    assert first == second == bound


# ================================================================ decision 3: handoff ends it

class _FakeDriver:
    def close(self):
        pass


class _FakeDocument:
    def __init__(self, path: Path):
        self.path = path
        self.text = "# handoff\n"
        self.resume = "resume"
        self.dispatch = "dispatch"
        self.warnings = []


@pytest.fixture
def handoff_project(tmp_path, monkeypatch):
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: t\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n")
    (tmp_path / "handoffs").mkdir()
    monkeypatch.chdir(tmp_path)
    from seldon.commands import handoff as H

    monkeypatch.setattr(H, "get_neo4j_driver", lambda cfg: _FakeDriver())
    monkeypatch.setattr(H, "build_handoff",
                        lambda **kw: _FakeDocument(tmp_path / "handoffs" / "2026-09-16_x.md"))
    return tmp_path


def _invoke_handoff(*extra):
    from seldon.commands.handoff import handoff_command
    return CliRunner().invoke(
        handoff_command, ["--slug", "x", "--summary", "y", "--next", "z", *extra])


def test_handoff_ends_the_session_file(handoff_project):
    start_session(handoff_project)
    result = _invoke_handoff()
    assert result.exit_code == 0, result.output
    assert get_current_session_data(handoff_project) is None


def test_a_dry_run_handoff_leaves_the_session_alone(handoff_project):
    sid = start_session(handoff_project)
    result = _invoke_handoff("--dry-run")
    assert result.exit_code == 0, result.output
    assert get_current_session_data(handoff_project)["session_id"] == sid


def test_a_refused_handoff_leaves_the_session_alone(handoff_project):
    sid = start_session(handoff_project)
    (handoff_project / "handoffs" / "2026-09-16_x.md").write_text("already\n")
    result = _invoke_handoff()
    assert result.exit_code == 1
    assert get_current_session_data(handoff_project)["session_id"] == sid


def test_the_mcp_handoff_ends_the_session_file(handoff_project, monkeypatch):
    from seldon import mcp_server
    import seldon.core.handoff as core_handoff

    monkeypatch.setattr(mcp_server, "_resolve_project",
                        lambda p: ({}, _FakeDriver(), NEO4J_DB, None, str(handoff_project)))
    monkeypatch.setattr(core_handoff, "build_handoff",
                        lambda **kw: _FakeDocument(handoff_project / "handoffs" / "h.md"))
    start_session(handoff_project)
    out = mcp_server.seldon_handoff(slug="x", summary="y", next="z",
                                    project_dir=str(handoff_project))
    assert "Wrote" in out, out
    assert get_current_session_data(handoff_project) is None


# ================================================================ decision 4: issue create is atomic

@pytest.fixture
def issue_project(tmp_path, monkeypatch):
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: t\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _issue_args(affects: str) -> list:
    return ["create", "--description", "d", "--type", "citation_gap", "--importance", "high",
            "--urgency", "low", "--detection", "audit", "--target", "citation",
            "--affects", affects]


def _seed(project: Path, driver, artifact_type: str, name: str) -> str:
    from seldon.core.artifacts import create_artifact
    from seldon.domain.loader import load_domain_config

    domain = load_domain_config(
        Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml")
    props = {"name": name}
    if artifact_type == "PaperSection":
        props["title"] = name
    else:
        props["description"] = name
    return create_artifact(project_dir=project, driver=driver, database=NEO4J_DB,
                           domain_config=domain, artifact_type=artifact_type,
                           properties=props, actor="human", authority="accepted")


def _store_bytes(project: Path) -> bytes:
    path = project / "seldon_events.jsonl"
    return path.read_bytes() if path.exists() else b""


def _issue_count(driver) -> int:
    with driver.session(database=NEO4J_DB) as s:
        return s.run("MATCH (i:Issue) RETURN count(i) AS n").single()["n"]


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_an_unresolvable_link_writes_nothing(issue_project, neo4j_driver):
    from seldon.commands.issue import issue_group

    section = _seed(issue_project, neo4j_driver, "PaperSection", "sec")
    before = _store_bytes(issue_project)
    result = CliRunner().invoke(issue_group, _issue_args(f"{section},no-such-artifact"))
    assert result.exit_code == 1, result.output
    assert "no-such-artifact" in result.output
    assert _store_bytes(issue_project) == before
    assert _issue_count(neo4j_driver) == 0


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_an_illegal_link_type_writes_nothing(issue_project, neo4j_driver):
    """`affects` accepts only PaperSection; a ResearchTask target is refused before any write."""
    from seldon.commands.issue import issue_group

    task = _seed(issue_project, neo4j_driver, "ResearchTask", "task")
    before = _store_bytes(issue_project)
    result = CliRunner().invoke(issue_group, _issue_args(task))
    assert result.exit_code == 1, result.output
    assert _store_bytes(issue_project) == before
    assert _issue_count(neo4j_driver) == 0


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_valid_links_are_all_written(issue_project, neo4j_driver):
    from seldon.commands.issue import issue_group

    a = _seed(issue_project, neo4j_driver, "PaperSection", "a")
    b = _seed(issue_project, neo4j_driver, "PaperSection", "b")
    result = CliRunner().invoke(issue_group, _issue_args(f"{a},{b}"))
    assert result.exit_code == 0, result.output
    links = [e for e in read_events(issue_project) if e["event_type"] == "link_created"]
    assert sorted(e["payload"]["to_id"] for e in links) == sorted([a, b])
    assert _issue_count(neo4j_driver) == 1
