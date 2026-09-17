"""`seldon issue create` / `issue update` name the actor that ran them.

`ai-readiness-kg/cc_tasks/2026-09-17_dispatcher_notifies.md` decision 2. Both commands
hard-coded `actor="human"`, so two Issues filed and resolved by headless CC sessions sit on the
record as human acts. The actor now comes from the process environment: Claude Code sets
`CLAUDECODE=1` and `CLAUDE_CODE_SESSION_ID` in every shell it spawns, interactive or headless
(code.claude.com/docs/en/env-vars), so either one means the command ran inside a CC session. A
terminal with neither is still `human`.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.issue import issue_group
from seldon.config import resolve_cli_actor
from seldon.core.events import read_events
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE


@pytest.fixture(autouse=True)
def _no_cc_marker(monkeypatch):
    for var in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)


def test_a_terminal_with_no_session_environment_is_human():
    assert resolve_cli_actor() == "human"


def test_claudecode_marks_a_cc_session(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert resolve_cli_actor() == "cc"


def test_a_claude_code_session_id_marks_a_cc_session(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")
    assert resolve_cli_actor() == "cc"


@pytest.mark.parametrize("var,value", [("CLAUDECODE", ""), ("CLAUDECODE", "0"),
                                       ("CLAUDE_CODE_SESSION_ID", "")])
def test_an_empty_or_false_marker_is_not_a_session(monkeypatch, var, value):
    monkeypatch.setenv(var, value)
    assert resolve_cli_actor() == "human"


def _project(tmp_path: Path) -> Path:
    (tmp_path / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: {os.getenv('NEO4J_URI', 'bolt://localhost:7687')}\n"
        f"event_store:\n  path: seldon_events.jsonl\n", encoding="utf-8")
    return tmp_path


def _invoke(project: Path, argv, env):
    prev = Path.cwd()
    os.chdir(project)
    try:
        return CliRunner().invoke(issue_group, argv, env=env, catch_exceptions=False)
    finally:
        os.chdir(prev)


CREATE = ["create", "--description", "probe", "--type", "citation_gap", "--importance", "low",
          "--urgency", "low", "--detection", "audit", "--target", "citation"]


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
@pytest.mark.parametrize("env,actor", [({"CLAUDECODE": "1"}, "cc"), ({}, "human")])
def test_issue_create_and_update_stamp_the_resolved_actor(tmp_path, env, actor):
    project = _project(tmp_path)
    res = _invoke(project, CREATE, env)
    assert res.exit_code == 0, res.output
    issue_id = res.output.split("Created Issue: ")[1].split()[0]

    res = _invoke(project, ["update", issue_id, "--state", "in_progress",
                            "--resolution-notes", "n"], env)
    assert res.exit_code == 0, res.output

    events = read_events(project)
    assert [e["event_type"] for e in events] == [
        "artifact_created", "artifact_updated", "artifact_state_changed"]
    assert {e["actor"] for e in events} == {actor}
