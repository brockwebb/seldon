"""SEL-054 Part B: one board identity per session minted at launch, and every limit tried by a planted request.

`cc_tasks/2026-11-27_SEL-054_four_things_the_factory_needs_from_the_dispatcher_are_built.md`, answering factory's
filings `2026-11-27_filing_from_factory_the_dispatcher_mints_one_hive_identity_per_session_at_launch.md` and
`2026-11-27_filing_from_factory_every_limit_the_dispatcher_sets_is_tried_by_a_planted_control.md`; AD-038 ADDENDUM 16,
R43 to R45.

The guard and the controls run the REAL hook command the launch line installs (`python -P -m seldon dispatch
tool-gate ...`), so a guard whose path never reaches the hook fails its control here as it would at a launch.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.cli import main
from seldon.commands import dispatch as S
from seldon.commands.dispatch import dispatch_group
from seldon.core import controls as C
from seldon.core import dispatch as D
from seldon.core import hive as H
from seldon.core import stations as Q
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, SELDON_REPO, add_task, make_project, register, run_cli, task_states, write_stub,
)


@pytest.fixture(autouse=True)
def _worktree_code(monkeypatch):
    """The launch line's hooks run `python -P -m seldon`; point that at this checkout's code, not an installed one."""
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(
        [str(SELDON_REPO)] + [x for x in os.environ.get("PYTHONPATH", "").split(os.pathsep) if x]))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _mint_script(tmp_path, body: str) -> str:
    script = tmp_path / "mint.py"
    script.write_text(body, encoding="utf-8")
    return f"{sys.executable} {script}"


GOOD_MINT = """\
import json, os
print(json.dumps({"token": "tok-" + os.environ["SELDON_SESSION_ID"][:8],
                  "identity": os.environ["HIVE_PROJECT"] + "." + os.environ["SELDON_SESSION_ID"][:8]}))
"""


# ============================================================================ configuration

def test_hive_and_guard_are_absent_unless_declared(tmp_path):
    cfg = D.load_dispatch_config(make_project(tmp_path))
    assert cfg["hive"] is None and cfg["guard"] == {"deny_paths": []}


def test_a_relative_secrets_dir_is_refused_at_load(tmp_path):
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": "secrets"}})
    with pytest.raises(D.DispatchConfigError, match="absolute"):
        D.load_dispatch_config(p)


# ============================================================================ the mint

def test_the_mint_runs_outside_the_session_and_its_token_is_never_recorded(tmp_path):
    hive = H.load_hive({"mint_command": _mint_script(tmp_path, GOOD_MINT)})
    minted = H.mint(hive, project="factory", task_id="t-1", task_name="OODA-1", session_id="abcdef0123456789",
                    cwd=tmp_path)
    assert minted["ok"] and minted["token"] == "tok-abcdef01" and minted["identity"] == "factory.abcdef01"
    env = H.session_env(minted, project="factory", task_id="t-1")
    assert env == {"HIVE_TOKEN": "tok-abcdef01", "HIVE_PROJECT": "factory", "HIVE_TASK": "t-1"}
    rec = H.record(minted, task_id="t-1", child_session_id="abcdef0123456789")
    assert "tok-abcdef01" not in json.dumps(rec) and rec["token_sha256"] == H.fingerprint("tok-abcdef01")


def test_a_failed_mint_is_recorded_and_gives_the_session_no_token(tmp_path):
    hive = H.load_hive({"mint_command": _mint_script(tmp_path, "import sys; print('board down', file=sys.stderr); "
                                                               "sys.exit(3)")})
    minted = H.mint(hive, project="p", task_id="t", task_name=None, session_id="s", cwd=tmp_path)
    assert not minted["ok"] and "board down" in minted["error"]
    assert H.session_env(minted, project="p", task_id="t") == {}


def test_a_mint_that_prints_more_than_a_token_is_refused_not_guessed(tmp_path):
    hive = H.load_hive({"mint_command": _mint_script(tmp_path, "print('minting...'); print('tok')")})
    assert not H.mint(hive, project="p", task_id="t", task_name=None, session_id="s", cwd=tmp_path)["ok"]


def test_no_mint_configured_mints_nothing(tmp_path):
    assert H.mint(None, project="p", task_id="t", task_name=None, session_id="s", cwd=tmp_path) is None


@pytest.mark.usefixtures("neo4j_available")
def test_a_dispatched_session_gets_its_minted_token_in_its_environment_and_nowhere_else(tmp_path, neo4j_driver):
    dc = load_domain_config(RESEARCH_YAML)
    p = make_project(tmp_path, dispatch_extra={"hive": {"mint_command": _mint_script(tmp_path, GOOD_MINT)}})
    add_task(p, "T-hive")
    register(p, neo4j_driver, dc, "T-hive", "2026-11-26T01:00:00Z")
    dump = tmp_path / "env.json"
    write_stub(p, {"T-hive": {"complete": True, "dump_env": str(dump), "dump_env_prefix": "HIVE_"}})
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    env = json.loads(dump.read_text())
    assert env["HIVE_TOKEN"].startswith("tok-") and env["HIVE_PROJECT"] and env["HIVE_TASK"]
    (ident,) = [e["payload"] for e in read_events(p) if e["event_type"] == H.EVENT_SESSION_IDENTITY]
    assert ident["minted"] and ident["token_sha256"] == H.fingerprint(env["HIVE_TOKEN"])
    store = (p / "seldon_events.jsonl").read_text()
    assert env["HIVE_TOKEN"] not in store, "the token is in no event"
    assert env["HIVE_TOKEN"] not in (p / "logs" / "dispatch" / "T-hive.log").read_text(), "nor on the launch line"
    assert task_states(neo4j_driver)["T-hive"] == "completed"


# ============================================================================ the launch line

def test_the_notices_hook_goes_on_every_launch_line_as_a_post_tool_use_hook(tmp_path):
    p = make_project(tmp_path, dispatch_extra={"hive": {"notices_hook": "/opt/py /x/hive.py notices --hook"}})
    settings = S._session_settings(p, D.load_dispatch_config(p))
    (entry,) = settings["hooks"]["PostToolUse"]
    assert entry["hooks"][0]["command"] == "/opt/py /x/hive.py notices --hook"


def test_the_tool_gate_carries_every_guarded_path_on_its_own_command_line(tmp_path):
    secrets = tmp_path / "hive" / "secrets"
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": str(secrets)},
                                               "guard": {"deny_paths": [str(tmp_path / "check")]}})
    cmd = S._session_settings(p, D.load_dispatch_config(p))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert f"--deny-path {(tmp_path / 'check').resolve()}" in cmd and f"--deny-path {secrets.resolve()}" in cmd


# ============================================================================ the guard

def _gate(p, deny, tool, tool_input, monkeypatch):
    monkeypatch.chdir(p)
    monkeypatch.delenv("SELDON_SESSION_ID", raising=False)
    argv = ["dispatch", "tool-gate", "--project", str(p)] + [a for d in deny for a in ("--deny-path", str(d))]
    return CliRunner().invoke(main, argv, input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                                                           "tool_input": tool_input, "cwd": str(p)}))


@pytest.mark.parametrize("tool,tool_input", [
    ("Read", {"file_path": "{s}/minter.token"}),
    ("Bash", {"command": "cat {s}/minter.token"}),
    ("Grep", {"pattern": "x", "path": "{s}"}),
    ("Edit", {"file_path": "{s}/../secrets/minter.token", "old_string": "a", "new_string": "b"}),
])
def test_the_guard_refuses_a_call_that_names_a_guarded_path(tmp_path, monkeypatch, tool, tool_input):
    p = make_project(tmp_path)
    secrets = (tmp_path / "secrets").resolve()
    secrets.mkdir()
    planted = {k: v.replace("{s}", str(secrets)) for k, v in tool_input.items()}
    r = _gate(p, [secrets], tool, planted, monkeypatch)
    assert r.exit_code == 0, r.output
    body = json.loads(r.output)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny" and "GUARD" in r.output


def test_the_guard_lets_every_other_call_through(tmp_path, monkeypatch):
    p = make_project(tmp_path)
    r = _gate(p, [tmp_path / "secrets"], "Read", {"file_path": str(p / "seldon.yaml")}, monkeypatch)
    assert r.exit_code == 0 and r.output.strip() == ""


def test_a_home_relative_spelling_is_refused_too():
    home = str(Path.home().resolve())
    root = f"{home}/.factory/hive/secrets"
    hook = {"tool_name": "Bash", "tool_input": {"command": "cat ~/.factory/hive/secrets/minter.token"}}
    assert C.refusal(hook, [root])
    hook = {"tool_name": "Bash", "tool_input": {"command": "cat $HOME/.factory/hive/secrets/minter.token"}}
    assert C.refusal(hook, [root])


# ============================================================================ the controls

def test_the_launch_line_writes_no_file_path_rule_so_fac31s_syntax_failure_cannot_reach_it(tmp_path):
    """FAC-31 control C5's rule, `Write(/private/tmp/.../check/**)`, matched nothing. seldon's launch line writes only
    `dispatch.allow`, which refuses a non-Bash rule at load: its one path limit is the guard, tried by plants."""
    p = make_project(tmp_path, dispatch_extra={"allow": [
        {"rule": "Write(/private/tmp/x/check/**)", "instruction": "planted: the FAC-31 C5 rule"}]})
    with pytest.raises(D.DispatchConfigError, match="Bash"):
        D.load_dispatch_config(p)


def test_the_spend_ceiling_stops_its_planted_session():
    row = C.spend_control(Q.load_stations_config({}))
    assert row["refused"] is True, row


def test_every_installed_limit_refuses_its_planted_request(tmp_path):
    secrets = tmp_path / "secrets"
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": str(secrets)}})
    cfg = D.load_dispatch_config(p)
    out = S.try_limits(p, cfg)
    assert out["ok"], out["failed"]
    kinds = {(r["limit"], (r.get("request") or {}).get("tool_name") if isinstance(r.get("request"), dict) else None)
             for r in out["rows"]}
    assert ("guard", "Read") in kinds and ("guard", "Bash") in kinds and ("spend_ceiling", None) in kinds
    assert any(r["limit"] == "network" and r["tried"] is False and r["why"] for r in out["rows"])


def test_a_guard_whose_path_never_reaches_the_hook_fails_its_control(tmp_path, monkeypatch):
    """The planted control of the control: a launch line that drops its `--deny-path` lets the plant through."""
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": str(tmp_path / "secrets")}})
    cfg = D.load_dispatch_config(p)
    _drop_deny_paths(monkeypatch)
    out = S.try_limits(p, cfg)
    assert not out["ok"] and {r["limit"] for r in out["failed"]} == {"guard"}


def _drop_deny_paths(monkeypatch):
    real = S._session_settings

    def dropped(project_dir, c):
        s = real(project_dir, c)
        h = s["hooks"]["PreToolUse"][0]["hooks"][0]
        h["command"] = h["command"].split(" --deny-path")[0]
        return s
    monkeypatch.setattr(S, "_session_settings", dropped)
    return real


@pytest.mark.usefixtures("neo4j_available")
def test_a_failed_control_refuses_every_launch_and_is_recorded_once(tmp_path, neo4j_driver, monkeypatch):
    dc = load_domain_config(RESEARCH_YAML)
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": str(tmp_path / "secrets")}})
    add_task(p, "T-ctl")
    register(p, neo4j_driver, dc, "T-ctl", "2026-11-26T01:00:00Z")
    write_stub(p, {"T-ctl": {"complete": True}})
    real = _drop_deny_paths(monkeypatch)
    for _ in range(2):
        res = run_cli(p, dispatch_group, ["once"])
        assert res.exit_code == 0, res.output
        assert C.REFUSED_CONTROL_FAILED in res.output
    tried = [e["payload"] for e in read_events(p) if e["event_type"] == C.EVENT_LIMITS_TRIED]
    assert len(tried) == 1 and not tried[0]["ok"]
    assert task_states(neo4j_driver)["T-ctl"] in ("proposed", "accepted")
    monkeypatch.setattr(S, "_session_settings", real)
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    assert task_states(neo4j_driver)["T-ctl"] == "completed", "the limits changed and held: launches resume"


def test_the_controls_command_prints_each_limit_and_exits_nonzero_on_a_failure(tmp_path, monkeypatch):
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": str(tmp_path / "secrets")}})
    res = run_cli(p, dispatch_group, ["controls"])
    assert res.exit_code == 0, res.output
    assert "guard" in res.output and "spend_ceiling" in res.output and "network" in res.output
    _drop_deny_paths(monkeypatch)
    res = run_cli(p, dispatch_group, ["controls"])
    assert res.exit_code == 2 and "FAILED" in res.output, res.output
