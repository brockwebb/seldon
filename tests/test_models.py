"""MODEL-001 (AD-035): the registry, the lock, the accessor, refresh, the receipt and the gates.

Each test here failed before the change that introduced it (there was no `seldon.models`, no
lock, no registration check, no receipt). None reads the live lock or makes a model call: the
refresh tests drive a fake CLI and a fake npm through `refresh`'s runner seams.
"""
from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

from seldon import models as M
from seldon.core import dispatch as D
from tests.models_fixture import FIXTURE_IDS, write_models_home


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = write_models_home(tmp_path)
    monkeypatch.setenv(M.MODELS_HOME_ENV, str(h))
    return h


# ------------------------------------------------------------------------------ the accessor

def test_resolve_on_a_missing_role_fails_loudly(home):
    with pytest.raises(M.UnknownRole) as exc:
        M.resolve("no_such_role")
    assert "no_such_role" in str(exc.value) and "primary" in str(exc.value)


def test_resolve_maps_role_to_family_to_the_locked_id(home):
    assert M.resolve("primary") == FIXTURE_IDS["opus"]
    assert M.resolve("extractor") == FIXTURE_IDS["sonnet"]
    assert M.resolve("judge") == FIXTURE_IDS["fable"]
    assert M.resolve("background") == FIXTURE_IDS["haiku"]


def test_registry_holds_the_roles_the_task_names(home):
    roles = set(M.role_names())
    assert {"primary", "extractor", "rater", "adjudicator", "teacher", "judge",
            "background"} <= roles
    reg = M.load_registry()["roles"]
    assert reg["judge"]["family"] == "fable" and reg["background"]["family"] == "haiku"


def test_no_models_home_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv(M.MODELS_HOME_ENV, str(tmp_path / "empty"))
    with pytest.raises(M.ModelsError, match="registry.yaml"):
        M.resolve("primary")


def test_a_missing_lock_fails_loudly_naming_refresh(home):
    (home / M.LOCK_FILE).unlink()
    with pytest.raises(M.ModelsError, match="seldon models refresh"):
        M.resolve("primary")


def test_the_launcher_env_block_carries_all_four_lock_ids(home):
    env = M.launch_env()
    assert env == {"ANTHROPIC_DEFAULT_OPUS_MODEL": FIXTURE_IDS["opus"],
                   "ANTHROPIC_DEFAULT_SONNET_MODEL": FIXTURE_IDS["sonnet"],
                   "ANTHROPIC_DEFAULT_HAIKU_MODEL": FIXTURE_IDS["haiku"],
                   "ANTHROPIC_DEFAULT_FABLE_MODEL": FIXTURE_IDS["fable"]}
    spec = M.launch_spec("extractor")
    assert spec["env"] == {**env, M.EFFORT_ENV: spec["effort"]}
    assert spec["args"][:2] == ["--model", FIXTURE_IDS["sonnet"]]
    assert json.loads(spec["args"][3]) == {"switchModelsOnFlag": False}


def test_every_launch_passes_the_declared_effort_flag_and_env(home):
    """AD-036-R8: effort is a declared input; every role's launch passes it, twice in agreement."""
    spec = M.launch_spec("document_extractor")
    assert spec["args"][-2:] == ["--effort", "high"]
    assert spec["env"][M.EFFORT_ENV] == "high"
    for role in M.role_names():
        s = M.launch_spec(role)
        assert s["args"][-2:] == ["--effort", s["effort"]] and s["effort"] in M.EFFORT_LEVELS
        assert s["env"][M.EFFORT_ENV] == s["effort"]


def test_the_registry_names_the_documented_default_for_each_family(home):
    """AD-036-R8: the levels are the documented defaults of the models the lock serves, except the
    roles whose own pilots measured another level."""
    reg = M.load_registry()
    doc = reg["refresh"]["documented_default_effort"]["families"]
    assert {f: r["effort"] for f, r in doc.items()} == {
        "fable": "high", "opus": "medium", "sonnet": "medium", "haiku": "medium"}
    for name, row in reg["roles"].items():
        measured = {"document_extractor": "high", "demand_judge": "high",
                    "register_statement": "low"}       # SEL-002 pilot 2
        want = measured.get(name, doc[row["family"]]["effort"])
        assert row["effort"] == want, name


def test_effort_default_is_refused(home):
    reg = yaml.safe_load((home / M.REGISTRY_FILE).read_text())
    reg["roles"]["primary"]["effort"] = "default"
    (home / M.REGISTRY_FILE).write_text(yaml.safe_dump(reg, sort_keys=False))
    with pytest.raises(M.ModelsError, match="AD-036-R8"):
        M.load_registry()


def test_a_lock_id_header_launches_at_the_familys_documented_default(home):
    spec = M.launch_spec_for(FIXTURE_IDS["fable"])
    assert spec["role"] is None and spec["effort"] == "high"
    assert spec["args"][-2:] == ["--effort", "high"]
    assert M.launch_spec_for(FIXTURE_IDS["opus"])["effort"] == "medium"


def test_settings_merge_never_lets_a_caller_switch_models_on(home):
    assert json.loads(M.settings_json({"switchModelsOnFlag": True, "x": 1})) == {
        "switchModelsOnFlag": False, "x": 1}


# ------------------------------------------------------------------------------- the receipt

def _envelope(served: str, side: str | None = None) -> dict:
    mu = {served: {"outputTokens": 7, "inputTokens": 10}}
    if side:
        mu = {side: {"outputTokens": 1, "inputTokens": 50}, **mu}
    return {"type": "result", "usage": {"output_tokens": 7}, "modelUsage": mu}


def test_a_matching_receipt_passes_and_records_side_models(home):
    r = M.check_receipt(FIXTURE_IDS["opus"], _envelope(FIXTURE_IDS["opus"],
                                                       side=FIXTURE_IDS["haiku"]))
    assert r == {"requested": FIXTURE_IDS["opus"], "served": FIXTURE_IDS["opus"],
                 "side_models": [FIXTURE_IDS["haiku"]], "ok": True, "effort": None}
    assert M.receipt(FIXTURE_IDS["opus"], _envelope(FIXTURE_IDS["opus"]), effort="medium")[
        "effort"] == "medium"


def test_a_different_served_model_raises_model_substituted(home):
    with pytest.raises(M.ModelSubstituted) as exc:
        M.check_receipt(FIXTURE_IDS["opus"], _envelope("claude-opus-5"))
    assert exc.value.reason == "model_substituted"
    assert exc.value.receipt["served"] == "claude-opus-5"


def test_an_envelope_with_no_model_usage_is_not_a_receipt(home):
    with pytest.raises(M.ModelSubstituted):
        M.check_receipt(FIXTURE_IDS["opus"], {"type": "result"})


def test_the_stream_json_result_is_found_at_the_end_of_a_transcript():
    text = "\n".join([json.dumps({"type": "system"}), "plain line",
                      json.dumps({"type": "assistant", "message": {}}),
                      json.dumps(_envelope("claude-x-1"))])
    assert M.last_result_envelope(text)["modelUsage"] == {"claude-x-1": {"outputTokens": 7,
                                                                         "inputTokens": 10}}


# ------------------------------------------------------------------------------- refresh (R2)

FAKE_CLI = textwrap.dedent('''\
    #!{python}
    import json, sys
    if "--version" in sys.argv:
        print("{version} (Claude Code)"); sys.exit(0)
    alias = sys.argv[sys.argv.index("--model") + 1]
    served = json.load(open({served!r}))[alias]
    print(json.dumps({{"type": "result", "result": "OK", "usage": {{"output_tokens": 1}},
                      "modelUsage": {{served: {{"outputTokens": 1, "inputTokens": 3}}}}}}))
    ''')


def _fake_install(tmp_path, version, served: dict):
    """A runner pair: `npm view` prints `version`; `npm install` writes the fake CLI."""
    import sys
    served_path = tmp_path / f"served_{version}.json"
    served_path.write_text(json.dumps(served))
    calls = {"npm": [], "cli": []}

    def npm(cmd, *, cwd, env, timeout):
        calls["npm"].append(cmd)
        if cmd[:2] == ["npm", "view"]:
            return subprocess.CompletedProcess(cmd, 0, f"{version}\n", "")
        prefix = Path(cmd[cmd.index("--prefix") + 1])
        binp = prefix / "node_modules" / ".bin" / "claude"
        binp.parent.mkdir(parents=True, exist_ok=True)
        binp.write_text(FAKE_CLI.format(python=sys.executable, version=version,
                                        served=str(served_path)))
        binp.chmod(0o755)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def runner(cmd, *, cwd, env, timeout):
        calls["cli"].append(cmd)
        return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=timeout)
    return npm, runner, calls


@pytest.fixture
def refresh_home(tmp_path, monkeypatch):
    """A models home inside a scratch 'seldon repo' (for the event store), with no lock yet,
    and an install root under tmp_path."""
    repo = tmp_path / "repo"
    home = write_models_home(repo)
    (home / M.LOCK_FILE).unlink()
    reg = yaml.safe_load((home / M.REGISTRY_FILE).read_text())
    reg["refresh"]["install_root"] = str(tmp_path / "cli")
    (home / M.REGISTRY_FILE).write_text(yaml.safe_dump(reg, sort_keys=False))
    (repo / "seldon_events.jsonl").write_text("")
    monkeypatch.setenv(M.MODELS_HOME_ENV, str(home))
    return home


def _bumped_events(repo: Path) -> list:
    lines = [json.loads(x) for x in (repo / "seldon_events.jsonl").read_text().splitlines() if x]
    return [e for e in lines if e["event_type"] == M.EVENT_LOCK_BUMPED]


def test_refresh_writes_the_lock_and_one_event_and_is_idempotent(refresh_home, tmp_path):
    repo = refresh_home.parent
    npm, runner, calls = _fake_install(tmp_path, "3.0.1", FIXTURE_IDS)
    out = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-09")
    assert out.status == "bumped"
    lock = M.load_lock()
    assert {f: r["model"] for f, r in lock["families"].items()} == FIXTURE_IDS
    assert lock["cli"]["version"] == "3.0.1" and lock["resolved_on"] == "2026-10-09"
    assert len(_bumped_events(repo)) == 1
    evidence = json.loads((repo / out.evidence).read_text())
    assert set(evidence["probes"]) == set(FIXTURE_IDS)
    probes = [c for c in calls["cli"] if "-p" in c]
    assert len(probes) == 4
    assert all('{"switchModelsOnFlag":false}' in c for c in probes)
    lock_bytes = (refresh_home / M.LOCK_FILE).read_bytes()

    # Same day, not forced: cached, no call at all.
    n = len(calls["cli"])
    again = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-09")
    assert again.status == "cached" and len(calls["cli"]) == n
    # Same day, forced, same answers: probes run, nothing is written, no second event.
    forced = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-09", force=True)
    assert forced.status == "unchanged"
    assert (refresh_home / M.LOCK_FILE).read_bytes() == lock_bytes
    assert len(_bumped_events(repo)) == 1


def test_refresh_bumps_when_a_family_moves_and_names_old_and_new(refresh_home, tmp_path):
    repo = refresh_home.parent
    npm, runner, _ = _fake_install(tmp_path, "3.0.1", FIXTURE_IDS)
    M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-09")
    moved = {**FIXTURE_IDS, "haiku": "claude-haiku-6-0"}
    npm2, runner2, _ = _fake_install(tmp_path, "3.0.2", moved)
    out = M.refresh(commit=False, npm=npm2, runner=runner2, today="2026-10-10")
    assert out.status == "bumped"
    events = _bumped_events(repo)
    assert len(events) == 2
    p = events[-1]["payload"]
    assert p["old"]["families"]["haiku"] == FIXTURE_IDS["haiku"]
    assert p["new"]["families"]["haiku"] == "claude-haiku-6-0"
    assert p["old"]["cli_version"] == "3.0.1" and p["new"]["cli_version"] == "3.0.2"
    # AD-036-R8: the bump records each family's documented default effort, and names the family
    # whose new model the table was not read for.
    assert p["new"]["documented_default_effort"]["families"]["haiku"] == {
        "effort": "medium", "documented_for": FIXTURE_IDS["haiku"], "current": False}
    assert p["documented_default_effort_unverified"] == ["haiku"]
    assert M.load_lock()["documented_default_effort"]["families"]["opus"]["current"] is True


def test_refresh_refuses_a_probe_served_outside_its_family(refresh_home, tmp_path):
    npm, runner, _ = _fake_install(tmp_path, "3.0.1", {**FIXTURE_IDS, "opus": "claude-sonnet-5-5"})
    with pytest.raises(M.ModelsError, match="not a opus model"):
        M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-09")
    assert not (refresh_home / M.LOCK_FILE).exists()


def test_probe_env_drops_credentials_and_family_pins(monkeypatch):
    base = {"ANTHROPIC_API_KEY": "k", "ANTHROPIC_DEFAULT_OPUS_MODEL": "x", "CLAUDECODE": "1",
            "CLAUDE_CODE_ENTRYPOINT": "cli", "PATH": "/bin"}
    assert M.probe_env(base) == {"PATH": "/bin"}


def test_ensure_fresh_is_off_when_the_registry_says_so(home):
    assert M.ensure_fresh("register") is None


# --------------------------------------------------------------------------- the gates (R5)

STALE_TASK = textwrap.dedent("""\
    # CC Task: planted stale id

    **Model:** claude-opus-5
    **Spend:** zero model calls. **Network:** none.
    **Framework layer served (DN-005 §5 rule 1):** none.
    Governing: AD-035.
    """)


def test_a_stale_id_in_a_task_header_is_refused_quoting_the_lock(home):
    check = M.check_task_models(STALE_TASK)
    assert not check["ok"]
    text = " ".join(check["errors"])
    assert "claude-opus-5" in text and "claude-opus-5-5" in text and "AD-035 R5" in text


def test_a_role_or_a_current_id_in_the_header_passes(home):
    assert M.check_task_models("**Model:** judge\n")["model"] == FIXTURE_IDS["fable"]
    assert M.check_task_models(f"**Model:** {FIXTURE_IDS['opus']}\n")["ok"]


def test_an_alias_in_the_header_is_refused(home):
    assert not M.check_task_models("**Model:** opus\n")["ok"]


def test_a_stale_code_block_model_is_refused_but_prose_is_not(home):
    prose = "Rated by `claude -p --model claude-sonnet-5` in S-007 (history).\n"
    assert M.check_task_models(prose)["ok"]
    block = "```bash\nclaude -p --model claude-sonnet-5 'x'\n```\n"
    assert not M.check_task_models(block)["ok"]
    placeholder = "```bash\nclaude -p --model <id> 'x'\n```\n"
    assert M.check_task_models(placeholder)["ok"]


def test_a_task_naming_no_model_never_reads_the_lock(tmp_path, monkeypatch):
    monkeypatch.setenv(M.MODELS_HOME_ENV, str(tmp_path / "nowhere"))
    assert M.check_task_models("# a task\n**Spend:** zero.\n")["ok"]


def test_cc_register_refuses_a_planted_stale_id_before_creating_anything(home, tmp_path):
    from seldon.commands.cc import enforce_task_models
    task = tmp_path / "t.md"
    task.write_text(STALE_TASK)
    refusal = enforce_task_models(task)
    assert refusal.startswith("model_not_in_lock") and "claude-opus-5-5" in refusal


def test_dispatcher_candidacy_refuses_a_planted_stale_id(home, tmp_path):
    task = tmp_path / "t.md"
    task.write_text(STALE_TASK)
    cand = D.candidacy(task)
    assert cand["candidate"] is False and cand["reason"] == "model_not_in_lock"
    task.write_text(STALE_TASK.replace("claude-opus-5\n", "primary\n"))
    assert D.candidacy(task)["candidate"] is True


@pytest.mark.parametrize("key", ["cli", "model"])
def test_dispatch_config_refuses_cli_and_model_keys(tmp_path, key):
    block = {"enabled": True, "branch": "main", "standing_band_ref": "c.yaml#x",
             "poll_interval_s": 300, "permission_mode": "bypassPermissions",
             "stop_file": "S", "log_dir": "l", "lease_file": "f", key: "claude"}
    with pytest.raises(D.DispatchConfigError, match="AD-035"):
        D.load_dispatch_config(tmp_path, {"dispatch": block})
