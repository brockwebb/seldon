"""FRICTION-002 Part D: dispatched sessions run in auto mode, and the classifier's breaker is a line stop.

`cc_tasks/2026-10-17_FRICTION-002_vendor_isolation_replaces_hand_built_plumbing.md` Part D. Seldon's dispatched
sessions launch with `--permission-mode auto`, not `bypassPermissions`. Each action the auto-mode classifier blocks
reaches the launch's `PermissionDenied` hook, `seldon dispatch classifier-denied`, which records a
`classifier_block`; the finish records the count, and `seldon qc chart` reports it per launch. When the CLI's breaker
(3 consecutive or 20 total blocks) aborts a headless session with its own text, the dispatcher writes a
`session_stop` of kind `line` from station `classifier` with the classifier's reason, and the task waits for a
redrive (AD-038-R2).
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from seldon.commands import dispatch as S
from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core import stations as Q
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, SELDON_REPO, add_task, make_project, register, run_cli, task_states, write_stub,
)

BREAKER = "Error: Agent aborted: too many classifier denials in headless mode"


@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _payloads(p, kind):
    return [e["payload"] for e in read_events(p) if e["event_type"] == kind]


def test_seldon_launches_its_sessions_in_auto_mode():
    cfg = D.load_dispatch_config(SELDON_REPO)
    assert cfg["permission_mode"] == "auto"
    spec = {"cli_path": "/x/claude", "args": ["--model", "m", "--settings", "{}"]}
    cmd = S._launch_cmd(cfg, "p", spec, worktree="t", settings=S._session_settings(SELDON_REPO, cfg))
    assert cmd[cmd.index("--permission-mode") + 1] == "auto"
    assert "bypassPermissions" not in cmd


def test_the_launch_installs_the_classifier_hook(tmp_path):
    p = make_project(tmp_path)
    hook = S._session_settings(p, D.load_dispatch_config(p))["hooks"]["PermissionDenied"][0]["hooks"][0]
    assert "dispatch classifier-denied --project" in hook["command"]


@pytest.mark.usefixtures("neo4j_available")
def test_a_classifier_breaker_becomes_a_line_stop_with_the_classifiers_reason(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path, dispatch_extra={"permission_mode": "auto"})
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-10-17T00:00:00Z")
    write_stub(p, {"a": {"classifier_blocks": 3, "print": BREAKER, "exit": 1, "result": False}})
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output

    launch = _payloads(p, D.EVENT_LAUNCHED)[-1]
    assert "--permission-mode auto" in launch["command"]
    blocks = _payloads(p, Q.EVENT_CLASSIFIER_BLOCK)
    assert [b["reason"] for b in blocks] == ["blocked 0", "blocked 1", "blocked 2"]
    assert {b["child_session_id"] for b in blocks} == {launch["child_session_id"]}
    stop = [s for s in _payloads(p, Q.EVENT_SESSION_STOP) if s.get("station") == "classifier"]
    assert len(stop) == 1, _payloads(p, Q.EVENT_SESSION_STOP)
    assert stop[0]["kind"] == "line" and stop[0]["reason"] == "classifier_breaker"
    assert stop[0]["classifier_reason"] == "blocked 2" and stop[0]["blocks"] == 3
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "classifier_breaker" and fin["classifier_blocks"] == 3
    assert task_states(neo4j_driver)["a"] == "blocked"

    chart = Q.chart(read_events(p), "t")
    (row,) = chart["classifier"]
    assert row["permission_mode"] == "auto" and row["blocks"] == 3 and row["breaker"] is True


@pytest.mark.usefixtures("neo4j_available")
def test_a_session_with_no_blocks_records_zero_and_is_not_stopped(tmp_path, neo4j_driver, dc):
    """The negative control: auto mode with nothing blocked finishes as before."""
    p = make_project(tmp_path, dispatch_extra={"permission_mode": "auto"})
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-10-17T00:00:00Z")
    write_stub(p, {"a": {}})
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    fin = _payloads(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merged" and fin["classifier_blocks"] == 0
    assert not [s for s in _payloads(p, Q.EVENT_SESSION_STOP) if s.get("station") == "classifier"]


def test_qc_chart_prints_classifier_blocks_per_launch(tmp_path, monkeypatch):
    p = make_project(tmp_path)
    (p / "seldon.yaml").write_text((p / "seldon.yaml").read_text() + "qc:\n  chart_min_points: 10\n")
    from seldon.core.events import append_event, make_event
    append_event(p, make_event(D.EVENT_LAUNCHED, "dispatcher", "accepted",
                               {"task_id": "abcdef1234", "child_session_id": "c1", "permission_mode": "auto",
                                "launched_at": "2026-10-17T01:02:03Z"}))
    for n in range(2):
        append_event(p, make_event(Q.EVENT_CLASSIFIER_BLOCK, "cc", "accepted",
                                   {"task_id": "abcdef1234", "child_session_id": "c1", "reason": f"r{n}"}))
    from seldon.commands.qc import qc_group
    monkeypatch.chdir(p)
    res = CliRunner().invoke(qc_group, ["chart"], catch_exceptions=False)
    assert res.exit_code == 0, res.output
    assert "classifier blocks per launch" in res.output
    assert "abcdef12" in res.output and "blocks   2" in res.output, res.output
