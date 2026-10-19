"""FRICTION-002 Part B: every dispatched task runs in a Claude Code worktree; worktree is the only mode.

`cc_tasks/2026-10-17_FRICTION-002_vendor_isolation_replaces_hand_built_plumbing.md` Part B and AD-034 ADDENDUM 01.
The dispatcher launches the CLI with `--worktree` and no name (DISP-001R Part A): the CLI names and cuts
`.claude/worktrees/<name>` on `worktree-<name>` from main, enters it and turns on its hard isolation. The session's work reaches main only by
the dispatcher's merge on green (AD-034-R5); a task that ends unmerged keeps its worktree and branch with a
`worktree_kept` record; a merged task's worktree is removed by the sweep and its branch kept.

The stub `claude` (tests/dispatch_scaffold.py) enters the worktree as the CLI does. Whether the CLI itself refuses a
write to the primary is a property of the vendor's binary: it is held here by the recorded probes of CLI 2.1.302
(`docs/evidence/friction002/isolation_probe_*.jsonl`) and, with `SELDON_LIVE_CLI_TESTS=1`, by a live probe of the
locked CLI (one small model call).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from seldon.commands import dispatch as S
from seldon.commands import dispatch_worktree as W
from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core.events import append_event, make_event, read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, SELDON_REPO, add_task, git, make_project, register, run_cli, task_states, write_stub,
)

EVIDENCE = SELDON_REPO / "docs" / "evidence" / "friction002"
REFUSAL = "This session is isolated in the worktree"
#: The live probe's model role: `background` is the registry's cheapest standing role (a haiku-family id).
LIVE_PROBE_ROLE = "background"


@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _events(p, kind):
    return [e["payload"] for e in read_events(p) if e["event_type"] == kind]


def _once(p):
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    return res.output


@pytest.mark.usefixtures("neo4j_available")
def test_a_launched_task_runs_in_its_cli_worktree_and_merges_on_green(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-10-17T00:00:00Z")
    # DISP-001R Part A: the CLI names the worktree; the stub is told which name to generate.
    write_stub(p, {"a": {"write": {"out/a.txt": "a\n"}, "worktree_name": "a"}})
    out = _once(p)

    launch = _events(p, D.EVENT_LAUNCHED)[-1]
    assert launch["mode"] == "worktree" and launch["worktree_named_by"] == "cli"
    named = _events(p, W.EVENT_WORKTREE_NAMED)[-1]
    assert named["worktree"] == ".claude/worktrees/a" and named["branch"] == "worktree-a"
    assert launch["command"].endswith(" --worktree"), launch["command"]
    log = (p / "logs" / "dispatch" / "a.log").read_text()
    assert "stub cwd: worktree" in log, log
    # The dispatcher merged the branch and completed the task; the session did neither.
    fin = _events(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merged" and fin["ok"] is True, (fin, out)
    assert task_states(neo4j_driver)["a"] == "completed"
    assert git(p, "show", "main:out/a.txt").stdout == "a\n"
    assert git(p, "show", "main:cc_tasks/a_RESULT.md").stdout
    assert git(p, "status", "--porcelain").stdout == ""


@pytest.mark.usefixtures("neo4j_available")
def test_a_merged_tasks_worktree_is_removed_by_the_sweep_and_its_branch_kept(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-10-17T00:00:00Z")
    write_stub(p, {"a": {"worktree_name": "a"}})
    _once(p)
    assert not (p / ".claude" / "worktrees" / "a").exists()
    removed = _events(p, D.EVENT_WORKTREE_REMOVED)
    assert [r["worktree"] for r in removed] == [".claude/worktrees/a"]
    assert removed[0]["branch_kept"] is True
    assert git(p, "branch", "--list", "worktree-a", "--format=%(refname:short)").stdout.strip() == "worktree-a"

    # A merged task whose worktree is still on disk (a removal that did not happen) is removed by the next sweep;
    # a worktree with no merged task is never touched.
    git(p, "worktree", "add", "-q", ".claude/worktrees/again", "-b", "worktree-again", "main")
    git(p, "worktree", "add", "-q", ".claude/worktrees/foreign", "-b", "worktree-foreign", "main")
    append_event(p, make_event(D.EVENT_FINISHED, "dispatcher", "accepted",
                               {"task_id": "t-again", "outcome": "merged", "ok": True,
                                "worktree": ".claude/worktrees/again", "branch": "worktree-again"}))
    swept = W.sweep(p)
    assert [r["worktree"] for r in swept] == [".claude/worktrees/again"]
    assert not (p / ".claude" / "worktrees" / "again").exists()
    assert (p / ".claude" / "worktrees" / "foreign").is_dir()
    assert git(p, "rev-parse", "--verify", "--quiet", "worktree-again").returncode == 0


@pytest.mark.usefixtures("neo4j_available")
def test_an_unmerged_task_keeps_its_worktree_and_branch_with_a_worktree_kept_record(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)
    add_task(p, "a")
    register(p, neo4j_driver, dc, "a", "2026-10-17T00:00:00Z")
    write_stub(p, {"a": {"write": {"out/a.txt": "partial\n"}, "exit": 1, "worktree_name": "a"}})
    _once(p)

    assert task_states(neo4j_driver)["a"] == "blocked"
    kept = _events(p, D.EVENT_WORKTREE_KEPT)
    assert len(kept) == 1, kept
    assert kept[0]["branch"] == "worktree-a" and kept[0]["worktree"] == ".claude/worktrees/a"
    assert kept[0]["outcome"] == "session_failed" and kept[0]["reason"] == "session_failed"
    wt = p / ".claude" / "worktrees" / "a"
    assert (wt / "out" / "a.txt").read_text() == "partial\n"
    assert git(p, "show", "worktree-a:out/a.txt").stdout == "partial\n"
    assert git(p, "show", "main:out/a.txt", check=False).returncode != 0
    # The next pass's sweep leaves it: only merged tasks' worktrees are removed, and no branch ever is.
    _once(p)
    assert wt.is_dir() and not _events(p, D.EVENT_WORKTREE_REMOVED)
    assert git(p, "rev-parse", "--verify", "--quiet", "worktree-a").returncode == 0


def _tool_results(path: Path) -> list:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("type") == "user":
            for c in o["message"]["content"]:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    out.append(str(c.get("content")))
    return out


def test_a_write_to_the_primary_from_inside_the_session_is_refused_recorded_probe():
    """CLI 2.1.302, `--worktree`, bypassPermissions (the strongest mode): Write to the primary and `git -C <primary>`
    are refused. A worktree the dispatcher cut beforehand (`precut2`) is entered and isolated the same way."""
    write = _tool_results(EVIDENCE / "isolation_probe_bypass.jsonl")
    assert any(REFUSAL in r and "Edit the worktree copy" in r for r in write), write
    precut = _tool_results(EVIDENCE / "isolation_probe_precut2.jsonl")
    assert any(REFUSAL in r for r in precut), precut
    git_c = _tool_results(EVIDENCE / "isolation_probe_git.jsonl")
    assert any("redirects git to the shared checkout via -C. Refusing to run it" in r for r in git_c), git_c


def test_the_launch_enters_the_cut_worktree_with_the_cli_flag(tmp_path):
    """The mechanism the recorded refusal depends on: `--worktree` (DISP-001R: with no name, last, so the CLI names
    it), and `worktree.baseRef: head` so the CLI never cuts its own tree from origin instead."""
    spec = {"cli_path": "/x/claude", "args": ["--model", "m", "--settings", '{"switchModelsOnFlag":false}',
                                              "--effort", "medium"]}
    cfg = {"permission_mode": "auto", "stations": {}}
    cmd = S._launch_cmd(cfg, "p", spec, worktree=True, settings=S._session_settings(tmp_path, cfg))
    assert cmd[-1] == "--worktree"
    settings = json.loads(cmd[cmd.index("--settings") + 1])
    assert settings["worktree"] == {"baseRef": "head"} and settings["switchModelsOnFlag"] is False
    assert cmd.count("--settings") == 1
    st = D.worktree_state(tmp_path, {})
    assert st["worktree_dir"] == ".claude/worktrees" and st["named_by"] == "cli"


def test_a_configured_worktree_dir_or_branch_prefix_is_refused():
    base = {"enabled": True, "branch": "main", "standing_band_ref": "x#y", "poll_interval_s": 300,
            "permission_mode": "auto", "stop_file": "s", "log_dir": "l", "lease_file": "f"}
    for key in ("worktree_dir", "branch_prefix"):
        with pytest.raises(D.DispatchConfigError, match="no longer read"):
            D.load_dispatch_config(Path("."), {"dispatch": {**base, key: "x"}})


@pytest.mark.skipif(os.getenv("SELDON_LIVE_CLI_TESTS") != "1",
                    reason="live CLI probe: one small model call; set SELDON_LIVE_CLI_TESTS=1")
def test_live_cli_refuses_a_write_to_the_primary(tmp_path):
    from seldon import models
    p = tmp_path / "repo"
    p.mkdir()
    for args in (["init", "-q", "-b", "main"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
                                                  "--allow-empty", "-m", "init"]):
        subprocess.run(["git", *args], cwd=p, check=True)
    subprocess.run(["git", "worktree", "add", "-q", ".claude/worktrees/probe", "-b", "worktree-probe", "main"],
                   cwd=p, check=True)
    spec = models.launch_spec_for(LIVE_PROBE_ROLE)
    target = p / "PROBE.txt"
    prompt = (f"Isolation probe. Use the Write tool once to create {target} (that absolute path) containing x. "
              f"Report the tool result verbatim; do not retry.")
    cmd = S._launch_cmd({"permission_mode": "bypassPermissions", "stations": {}}, prompt, spec, worktree="probe")
    env = {k: v for k, v in os.environ.items() if k not in D.API_KEY_VARS}
    r = subprocess.run(cmd, cwd=p, env={**env, **spec["env"]}, capture_output=True, text=True, timeout=600)
    log = tmp_path / "probe.jsonl"
    log.write_text(r.stdout, encoding="utf-8")
    assert not target.exists()
    assert any(REFUSAL in t for t in _tool_results(log)), r.stdout[-2000:]
