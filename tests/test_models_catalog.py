"""MODEL-003 (AD-035-R9 to R12): a role names a family or a specific model; the catalog is each model's profile.

Each test drives the fixture registry and lock, or `refresh` through its fake-CLI runner seam: zero model calls.
`author` is the registry's first role naming a model (claude-opus-4-8, MODEL-003 Part C).
"""
from __future__ import annotations

import json
import subprocess

import pytest
import yaml

from seldon import models as M
from seldon.core import dispatch as D
from tests.models_fixture import FIXTURE_IDS, write_models_home
from tests.test_models import STALE_TASK, _fake_install, refresh_home  # noqa: F401  (the refresh fixture)

PIN = "claude-opus-4-8"


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = write_models_home(tmp_path)
    monkeypatch.setenv(M.MODELS_HOME_ENV, str(h))
    return h


def _edit(home, path_name: str, fn) -> None:
    path = home / path_name
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _mark(home, available: bool, served: str | None = None) -> None:
    def f(lock):
        lock["models"][PIN] = {"served": served or (PIN if available else FIXTURE_IDS["opus"]),
                               "available": available, "evidence": "docs/evidence/fixture.json"}
    _edit(home, M.LOCK_FILE, f)


# ------------------------------------------------------------------------------ resolution (R9, R12)

def test_an_available_named_model_resolves_to_itself_with_its_declared_effort(home):
    r = M.resolve_role("author")
    assert (r.model, r.family, r.effort, r.named) == (PIN, "opus", "high", True)
    spec = M.launch_spec("author")
    # R12: --model carries the named id; the four family variables still carry the heads.
    assert spec["args"][:2] == ["--model", PIN] and spec["args"][-2:] == ["--effort", "high"]
    assert spec["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"] == FIXTURE_IDS["opus"]
    assert spec["env"][M.EFFORT_ENV] == "high"


def test_an_unavailable_named_model_fails_as_model_unavailable_and_never_falls_back(home):
    _mark(home, available=False)
    with pytest.raises(M.ModelUnavailable) as exc:
        M.resolve("author")
    assert exc.value.reason == "model_unavailable"
    assert "author" in str(exc.value) and PIN in str(exc.value)
    with pytest.raises(M.ModelUnavailable):
        M.launch_spec("author")


def test_a_named_model_missing_from_the_lock_is_unavailable(home):
    _edit(home, M.LOCK_FILE, lambda lock: lock.pop("models"))
    with pytest.raises(M.ModelUnavailable, match="seldon models refresh"):
        M.resolve("author")
    assert M.resolve("primary") == FIXTURE_IDS["opus"], "a lock with no `models:` still loads"


def test_the_checker_over_a_named_opus_model_is_fable(home):
    assert M.resolve("checker", generator="author") == FIXTURE_IDS["fable"]
    _mark(home, available=False)
    # AD-037-R2 maps by the catalog family: the checker is defined whether or not the generator is served.
    assert M.resolve("checker", generator="author") == FIXTURE_IDS["fable"]


def test_a_task_naming_an_available_model_id_launches_at_its_documented_default(home):
    spec = M.launch_spec_for(PIN)
    assert spec["role"] is None and spec["model"] == PIN and spec["effort"] == "high"


# ------------------------------------------------------------------------------- the gate (R5, R12)

def test_r5_accepts_the_named_role_while_available_and_refuses_it_quoting_the_lock(home):
    ok = M.check_task_models("**Model:** author\n")
    assert ok["ok"] and ok["model"] == PIN and ok["role"] == "author"
    assert M.check_task_models(f"**Model:** {PIN}\n")["ok"]
    _mark(home, available=False)
    bad = M.check_task_models("**Model:** author\n")
    text = " ".join(bad["errors"])
    assert not bad["ok"] and "model_unavailable" in text
    assert f"{PIN} available=False" in text and FIXTURE_IDS["opus"] in text
    assert not M.check_task_models(f"**Model:** {PIN}\n")["ok"]


def test_dispatcher_candidacy_refuses_a_task_on_an_unavailable_named_model(home, tmp_path):
    task = tmp_path / "t.md"
    task.write_text(STALE_TASK.replace("claude-opus-5\n", "author\n"))
    assert D.candidacy(task)["candidate"] is True
    _mark(home, available=False)
    cand = D.candidacy(task)
    assert cand["candidate"] is False and cand["reason"] == "model_not_in_lock"


# ------------------------------------------------------------------------------ the catalog (R10, R11)

@pytest.mark.parametrize("mid,family", [("claude-sonnet-4-6", "opus"), ("gpt-5", "opus"),
                                        ("openrouter/claude-opus-4-8", "opus")])
def test_a_catalog_id_outside_claude_family_is_refused_at_load(home, mid, family):
    def f(reg):
        reg["models"][mid] = {"family": family, "supported_params": {"effort": ["high"]}}
    _edit(home, M.REGISTRY_FILE, f)
    with pytest.raises(M.ModelsError, match=r"does not start with claude-opus-"):
        M.load_registry()


def test_a_role_naming_a_model_outside_the_catalog_is_refused(home):
    _edit(home, M.REGISTRY_FILE, lambda reg: reg["roles"]["author"].update(model="claude-opus-4-7"))
    with pytest.raises(M.ModelsError, match="no entry in the `models:` catalog"):
        M.load_registry()


def test_a_role_naming_both_a_family_and_a_model_is_refused(home):
    _edit(home, M.REGISTRY_FILE, lambda reg: reg["roles"]["author"].update(family="opus"))
    with pytest.raises(M.ModelsError, match="exactly one of `family` or `model`"):
        M.load_registry()


def test_an_effort_the_models_profile_excludes_is_refused_at_load(home):
    def f(reg):
        reg["models"][PIN]["supported_params"]["effort"] = ["low", "medium", "high"]
        reg["roles"]["author"]["effort"] = "max"
    _edit(home, M.REGISTRY_FILE, f)
    with pytest.raises(M.ModelsError) as exc:
        M.load_registry()
    assert "author" in str(exc.value) and "effort" in str(exc.value) and PIN in str(exc.value)
    assert "AD-035-R11" in str(exc.value)


def test_a_parameter_the_model_does_not_support_is_refused_not_dropped(home):
    _edit(home, M.REGISTRY_FILE, lambda reg: reg["roles"]["author"].update(temperature=0))
    with pytest.raises(M.ModelsError, match="parameter 'temperature', which model claude-opus-4-8 does not support"):
        M.load_registry()


def test_a_model_that_takes_no_effort_launches_with_no_flag_and_no_env(home):
    def f(reg):
        reg["models"][PIN]["supported_params"]["effort"] = []
        reg["models"][PIN].pop("default_effort")
        reg["roles"]["author"].pop("effort")
    _edit(home, M.REGISTRY_FILE, f)
    spec = M.launch_spec("author")
    assert spec["effort"] is None and "--effort" not in spec["args"]
    assert M.EFFORT_ENV not in spec["env"]
    # ...and a role declaring an effort on it is refused at load.
    _edit(home, M.REGISTRY_FILE, lambda reg: reg["roles"]["author"].update(effort="high"))
    with pytest.raises(M.ModelsError, match="AD-035-R11"):
        M.load_registry()


def test_a_role_on_a_model_with_effort_levels_must_name_one(home):
    _edit(home, M.REGISTRY_FILE, lambda reg: reg["roles"]["author"].pop("effort"))
    with pytest.raises(M.ModelsError, match="AD-036-R8"):
        M.load_registry()


def test_every_family_head_has_a_catalog_entry(home):
    _edit(home, M.REGISTRY_FILE, lambda reg: reg["models"].pop(FIXTURE_IDS["haiku"]))
    with pytest.raises(M.ModelsError, match="family heads"):
        M.load_registry()


# ----------------------------------------------------------------------------------- refresh (R10)

def test_a_named_model_served_exactly_is_available_and_resolves(refresh_home, tmp_path):  # noqa: F811
    npm, runner, _ = _fake_install(tmp_path, "3.0.1", {**FIXTURE_IDS, PIN: PIN})
    out = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-09")
    entry = M.load_lock()["models"][PIN]
    assert entry == {"served": PIN, "available": True, "evidence": out.evidence}
    assert M.resolve("author") == PIN


def test_a_named_model_served_another_id_is_unavailable_and_the_lock_still_writes(refresh_home, tmp_path):  # noqa: F811
    npm, runner, _ = _fake_install(tmp_path, "3.0.1", {**FIXTURE_IDS, PIN: FIXTURE_IDS["opus"]})
    out = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-09")
    lock = M.load_lock()
    assert {f: r["model"] for f, r in lock["families"].items()} == FIXTURE_IDS
    assert lock["models"][PIN]["available"] is False
    assert lock["models"][PIN]["served"] == FIXTURE_IDS["opus"]
    evidence = json.loads((refresh_home.parent / out.evidence).read_text())
    assert evidence["model_probes"][PIN]["error"] == f"served {FIXTURE_IDS['opus']!r}, not {PIN!r}"
    with pytest.raises(M.ModelUnavailable) as exc:
        M.resolve("author")
    assert exc.value.reason == "model_unavailable"


def test_a_named_probe_that_times_out_is_a_row_not_a_crash(refresh_home, tmp_path):  # noqa: F811
    npm, runner, _ = _fake_install(tmp_path, "3.0.1", FIXTURE_IDS)

    def flaky(cmd, *, cwd, env, timeout):
        if PIN in cmd:
            raise subprocess.TimeoutExpired(cmd, timeout)
        return runner(cmd, cwd=cwd, env=env, timeout=timeout)
    M.refresh(commit=False, npm=npm, runner=flaky, today="2026-10-09")
    entry = M.load_lock()["models"][PIN]
    assert entry["available"] is False and entry["error"].startswith("TimeoutExpired")


def test_the_days_cache_does_not_cover_a_model_the_lock_never_probed(refresh_home, tmp_path):  # noqa: F811
    npm, runner, calls = _fake_install(tmp_path, "3.0.1", {**FIXTURE_IDS, PIN: PIN})
    M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-09")
    _edit(refresh_home, M.LOCK_FILE, lambda lock: lock.pop("models"))
    n = len(calls["cli"])
    out = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-09")
    assert out.status != "cached" and len(calls["cli"]) > n
    assert M.load_lock()["models"][PIN]["available"] is True


def test_a_named_model_turning_unavailable_is_a_bump_naming_it(refresh_home, tmp_path):  # noqa: F811
    npm, runner, _ = _fake_install(tmp_path, "3.0.1", {**FIXTURE_IDS, PIN: PIN})
    M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-09")
    npm2, runner2, _ = _fake_install(tmp_path, "3.0.1", {**FIXTURE_IDS, PIN: FIXTURE_IDS["opus"]})
    out = M.refresh(commit=False, npm=npm2, runner=runner2, today="2026-10-10")
    assert out.status == "bumped"
    p = out.event["payload"]
    assert p["old_models"][PIN]["available"] is True and p["new_models"][PIN]["available"] is False
    assert p["profile_missing"] == []
