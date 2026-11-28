"""SEL-062 Part A: the limits and their controls (REVIEW-001 F-05, F-06, F-22).

`cc_tasks/2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say.md`;
findings in `docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/`;
rulings AD-038 ADDENDUM 17 (amending R43, R44 and R45).

* F-05: a harness error in a planted control is not a limit that let its plant through. It refuses the pass it happens
  on (the limit is not known to hold) and is tried again on the next, instead of latching until `seldon.yaml` changes;
  `seldon dispatch controls` writes the state a pass reads; the fingerprint covers the code that enforces the limits.
* F-06: the session guard resolves the spellings REVIEW-001's probe got past it (a `cd` then a relative path, a
  quote-split path, a search rooted at a parent of the guarded directory), and those spellings are planted controls.
* F-22: a failed mint's stderr never reaches the `session_identity` event, which is committed and pushed.
"""
from __future__ import annotations

import json
import os
import subprocess
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
from tests.dispatch_scaffold import SELDON_REPO, make_project, run_cli


@pytest.fixture(autouse=True)
def _worktree_code(monkeypatch):
    """The launch line's hooks run `python -P -m seldon`; point that at this checkout's code, not an installed one."""
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(
        [str(SELDON_REPO)] + [x for x in os.environ.get("PYTHONPATH", "").split(os.pathsep) if x]))


def _state(p: Path) -> Path:
    return p / ".seldon" / C.STATE_FILE


def _harness_error_once(monkeypatch):
    """The first planted hook call times out (the harness's error, not the limit's); every later call is real."""
    real = C.guard_controls
    calls = {"n": 0}

    def flaky(hook_command, paths, cwd, run=subprocess.run):
        calls["n"] += 1
        if calls["n"] == 1:
            def timeout(*a, **k):
                raise subprocess.TimeoutExpired(cmd="hook", timeout=C.HOOK_TIMEOUT_S)
            return real(hook_command, paths, cwd, run=timeout)
        return real(hook_command, paths, cwd, run=run)
    monkeypatch.setattr(C, "guard_controls", flaky)
    return calls


# ============================================================================ F-05: a harness error is not a failure

def test_part_a_a_harness_error_is_an_untried_control_not_a_limit_that_went_through(tmp_path):
    def timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="hook", timeout=C.HOOK_TIMEOUT_S)
    rows = C.guard_controls("python -m seldon dispatch tool-gate", [str(tmp_path / "secrets")], tmp_path,
                            run=timeout)
    assert rows and all(r["refused"] is None and r["tried"] is False and r["harness_error"] for r in rows), rows
    out = C.try_limits({"hook_command": "python -m seldon dispatch tool-gate", "deny_paths": [str(tmp_path / "s")],
                        "spend_ceiling_factor": 1.2, "code": "x"},
                       Q.load_stations_config({}), tmp_path, run=timeout)
    assert out["failed"] == [] and out["untried"] and out["ok"] is False and out["retry"] is True


def test_part_a_a_harness_error_refuses_its_pass_and_the_next_pass_tries_again(tmp_path, monkeypatch):
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": str(tmp_path / "secrets")}})
    cfg = D.load_dispatch_config(p)
    calls = _harness_error_once(monkeypatch)
    assert S._controls_gate(p, {}, "sess", cfg, False) is False
    state = json.loads(_state(p).read_text())
    assert state["retry"] is True and state["ok"] is False
    assert S._controls_gate(p, {}, "sess", cfg, False) is True, "same fingerprint, tried again, and it held"
    assert calls["n"] == 2
    tried = [e["payload"] for e in read_events(p) if e["event_type"] == C.EVENT_LIMITS_TRIED]
    assert [t["ok"] for t in tried] == [False, True], "one record per fingerprint and outcome"


def test_part_a_a_limit_that_went_through_still_latches_until_its_limits_change(tmp_path, monkeypatch):
    """The control of the fix: a real go-through is not retried on the same fingerprint (R45 unchanged)."""
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": str(tmp_path / "secrets")}})
    cfg = D.load_dispatch_config(p)
    real = S._session_settings

    def dropped(project_dir, c):
        s = real(project_dir, c)
        h = s["hooks"]["PreToolUse"][0]["hooks"][0]
        h["command"] = h["command"].split(" --deny-path")[0] + " --deny-path /nonexistent/elsewhere"
        return s
    monkeypatch.setattr(S, "_session_settings", dropped)
    assert S._controls_gate(p, {}, "sess", cfg, False) is False
    monkeypatch.setattr(C, "try_limits", lambda *a, **k: pytest.fail("a go-through is not retried"))
    assert S._controls_gate(p, {}, "sess", cfg, False) is False


def test_part_a_the_controls_command_writes_the_state_a_pass_reads(tmp_path, monkeypatch):
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": str(tmp_path / "secrets")}})
    cfg = D.load_dispatch_config(p)
    spec, _ = S._limits_spec(p, cfg)
    _state(p).parent.mkdir(parents=True, exist_ok=True)
    _state(p).write_text(json.dumps({"fingerprint": C.spec_fingerprint(spec), "ok": False, "failed": [
        {"limit": "guard", "request": "planted", "refused": False}]}), encoding="utf-8")
    res = run_cli(p, dispatch_group, ["controls"])
    assert res.exit_code == 0, res.output
    state = json.loads(_state(p).read_text())
    assert state["ok"] is True and state["fingerprint"] == C.spec_fingerprint(spec) and state["by"] == "controls"
    monkeypatch.setattr(C, "try_limits", lambda *a, **k: pytest.fail("the command's state is read, not re-tried"))
    assert S._controls_gate(p, {}, "sess", cfg, False) is True


def test_part_a_the_fingerprint_covers_the_code_that_enforces_the_limits(tmp_path, monkeypatch):
    spec = C.limits_spec("hook", [], {"spend_ceiling_factor": 1.2})
    assert spec["code"] == C.enforcing_code_digest()
    names = {Path(f).name for f in C.enforcing_files()}
    assert {"controls.py", "dispatch_stations.py", "stations.py"} <= names
    code = tmp_path / "enforcer.py"
    code.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(C, "enforcing_files", lambda: [code])
    before = C.spec_fingerprint(C.limits_spec("hook", [], {"spend_ceiling_factor": 1.2}))
    code.write_text("x = 2\n", encoding="utf-8")
    after = C.spec_fingerprint(C.limits_spec("hook", [], {"spend_ceiling_factor": 1.2}))
    assert before != after


# ============================================================================ F-06: the probe's spellings

@pytest.fixture
def vault(tmp_path):
    v = (tmp_path / "vault").resolve()
    (v / "secrets").mkdir(parents=True)
    (v / "secrets" / "x").write_text("s", encoding="utf-8")
    (v / "notes.txt").write_text("n", encoding="utf-8")
    return v


@pytest.mark.parametrize("tool,tool_input", [
    ("Bash", {"command": "cd {v} && cat secrets/x"}),
    ("Bash", {"command": "cd {v}; cat ./secrets/x"}),
    ("Bash", {"command": 'cat {v}/sec""rets/x'}),
    ("Bash", {"command": "cat {v}/'secrets'/x"}),
    ("Bash", {"command": "cat < {v}/sec''rets/x"}),
    ("Bash", {"command": "grep --file={v}/sec\"\"rets/x ."}),
    ("Grep", {"pattern": "token", "path": "{v}"}),
    ("Glob", {"pattern": "**/*", "path": "{v}"}),
    ("Glob", {"pattern": "{v}/**/*"}),
    ("Read", {"file_path": "secrets/x", "_cwd": "{v}"}),
])
def test_part_a_the_guard_refuses_the_spellings_the_probe_got_past(vault, tool, tool_input):
    ti = {k: v.replace("{v}", str(vault)) for k, v in tool_input.items()}
    cwd = ti.pop("_cwd", str(vault.parent))
    hook = {"tool_name": tool, "tool_input": ti, "cwd": cwd}
    assert C.refusal(hook, [str(vault / "secrets")]), hook


@pytest.mark.parametrize("tool,tool_input", [
    ("Read", {"file_path": "{v}/notes.txt"}),
    ("Bash", {"command": "cd {v} && cat notes.txt"}),
    ("Bash", {"command": "ls {v}"}),
    ("Grep", {"pattern": "token", "path": "{v}/notes.txt"}),
    ("Bash", {"command": "echo 'unbalanced"}),
])
def test_part_a_the_guard_lets_the_parents_other_files_through(vault, tool, tool_input):
    ti = {k: v.replace("{v}", str(vault)) for k, v in tool_input.items()}
    assert C.refusal({"tool_name": tool, "tool_input": ti, "cwd": str(vault.parent)}, [str(vault / "secrets")]) \
        is None


def test_part_a_the_probe_spellings_are_planted_controls(tmp_path):
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": str(tmp_path / "secrets")}})
    out = S.try_limits(p, D.load_dispatch_config(p))
    assert out["ok"], out["failed"]
    spellings = {r.get("spelling") for r in out["rows"] if r["limit"] == "guard"}
    assert set(C.PLANTED_SPELLINGS) <= spellings
    assert {"canonical_read", "canonical_cat", "cd_relative", "quote_split", "search_parent"} <= set(
        C.PLANTED_SPELLINGS)


def test_part_a_a_guard_that_misses_one_spelling_fails_its_control(tmp_path, monkeypatch):
    """The control of the control: a guard that only matches the canonical text lets the cd spelling through."""
    p = make_project(tmp_path, dispatch_extra={"hive": {"secrets_dir": str(tmp_path / "secrets")}})
    fake = tmp_path / "textonly_gate.py"
    fake.write_text(
        "import json, sys\n"
        "hook = json.load(sys.stdin)\n"
        "roots = [a for i, a in enumerate(sys.argv) if i and sys.argv[i - 1] == '--deny-path']\n"
        "text = json.dumps(hook.get('tool_input') or {})\n"
        "if any(r in text for r in roots):\n"
        "    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',"
        " 'permissionDecision': 'deny'}}))\n", encoding="utf-8")
    real = S._session_settings

    def swapped(project_dir, c):
        s = real(project_dir, c)
        h = s["hooks"]["PreToolUse"][0]["hooks"][0]
        h["command"] = f"{sys.executable} {fake} " + " ".join(
            a for a in h["command"].split(" --deny-path")[1:] for a in ("--deny-path", a.strip()))
        return s
    monkeypatch.setattr(S, "_session_settings", swapped)
    out = S.try_limits(p, D.load_dispatch_config(p))
    assert not out["ok"]
    assert {r.get("spelling") for r in out["failed"]} >= {"cd_relative"}


# ============================================================================ F-22: the mint's stderr

def test_part_a_a_failed_mints_stderr_never_reaches_the_recorded_event(tmp_path):
    script = tmp_path / "mint.py"
    script.write_text("import sys; print('board down: minter token tok-SECRET-abc', file=sys.stderr); sys.exit(3)",
                      encoding="utf-8")
    hive = H.load_hive({"mint_command": f"{sys.executable} {script}"})
    minted = H.mint(hive, project="p", task_id="t", task_name=None, session_id="s", cwd=tmp_path)
    assert not minted["ok"]
    rec = H.record(minted, task_id="t", child_session_id="s")
    assert "SECRET" not in json.dumps(rec) and "board down" not in json.dumps(rec)
    assert rec["error"].startswith("exit 3") and rec["stderr_sha256"] and rec["stderr_chars"] > 0
    assert "board down" in minted["error"], "the dispatcher's own stderr still says why"
