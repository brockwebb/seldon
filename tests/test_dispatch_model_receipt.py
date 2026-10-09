"""MODEL-001 (AD-035 R3, R6) at the dispatcher: the session is launched from the lock and its
served model is checked against the requested one.

Real passes against a scratch project (`tests/dispatch_scaffold.py`), with the stub CLI named by
a fixture lock. Both tests failed before the change: the dispatcher passed no env block and no
`--model`, and it read no receipt.
"""
from __future__ import annotations

import json

import pytest

from seldon.commands.dispatch import dispatch_group
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, add_task, make_project, register, run_cli, task_states, write_stub,
)
from tests.models_fixture import FIXTURE_IDS

pytestmark = pytest.mark.usefixtures("neo4j_available")


def _finished(p) -> dict:
    events = [json.loads(x) for x in (p / "seldon_events.jsonl").read_text().splitlines() if x]
    return [e for e in events if e["event_type"] == "dispatch_finished"][-1]["payload"]


def test_the_session_gets_the_lock_env_and_model_and_its_receipt_is_recorded(
        tmp_path, neo4j_driver, clean_test_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = make_project(tmp_path)
    add_task(p, "t1")
    seen = tmp_path / "env.json"
    write_stub(p, {"t1": {"complete": True, "dump_env": str(seen)}})
    register(p, neo4j_driver, load_domain_config(RESEARCH_YAML), "t1", "2026-09-15T00:00:01Z")
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    assert json.loads(seen.read_text()) == {
        "ANTHROPIC_DEFAULT_OPUS_MODEL": FIXTURE_IDS["opus"],
        "ANTHROPIC_DEFAULT_SONNET_MODEL": FIXTURE_IDS["sonnet"],
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": FIXTURE_IDS["haiku"],
        "ANTHROPIC_DEFAULT_FABLE_MODEL": FIXTURE_IDS["fable"]}
    fin = _finished(p)
    assert fin["ok"] is True
    assert fin["model_receipt"]["requested"] == FIXTURE_IDS["opus"]
    assert fin["model_receipt"]["served"] == FIXTURE_IDS["opus"]
    assert fin["model_receipt"]["role"] == "primary"
    log = (p / "logs" / "dispatch" / "t1.log").read_text()
    assert f"--model {FIXTURE_IDS['opus']}" in log and "switchModelsOnFlag" in log


def test_a_substituted_model_blocks_the_task_as_model_substituted(
        tmp_path, neo4j_driver, clean_test_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = make_project(tmp_path)
    add_task(p, "t1")
    write_stub(p, {"t1": {"served": "claude-opus-4-8"}})
    register(p, neo4j_driver, load_domain_config(RESEARCH_YAML), "t1", "2026-09-15T00:00:01Z")
    run_cli(p, dispatch_group, ["once"])
    fin = _finished(p)
    assert fin["ok"] is False and fin["failure"] == "model_substituted"
    assert fin["model_receipt"]["served"] == "claude-opus-4-8"
    assert task_states(neo4j_driver)["t1"] == "blocked"


def test_a_task_whose_header_names_a_role_is_launched_as_that_role(
        tmp_path, neo4j_driver, clean_test_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = make_project(tmp_path)
    add_task(p, "t1", extra="**Model:** judge\n")
    write_stub(p, {"t1": {"complete": True}})
    register(p, neo4j_driver, load_domain_config(RESEARCH_YAML), "t1", "2026-09-15T00:00:01Z")
    run_cli(p, dispatch_group, ["once"])
    fin = _finished(p)
    assert fin["model_receipt"]["requested"] == FIXTURE_IDS["fable"]
    assert fin["model_receipt"]["role"] == "judge" and fin["ok"] is True
