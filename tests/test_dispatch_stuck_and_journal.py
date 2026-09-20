"""A Desktop graph write must not silently stop the queue.

ADDENDUM_01 to `ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence_after.md`,
decision 6, from `logs/airkg_dispatch.log` 2026-09-20T03:00:39Z..09:58:15Z: 84 consecutive
passes over seven hours printed `65e5da0e dirty_tree: c7`, exit 0, no event, no notification,
while one untracked task file sat in `cc_tasks/`.

Two halves, and they are different mechanisms for different halves of the failure:

**(a) A write tool commits its own append.** The event store is tracked, and c7 is a fact about
the CHECKOUT — so one uncommitted line blocks the whole queue, not one task. Registration has
committed its own footprint since `2026-09-18_registration_commits`; nothing in that argument
was special to registration.

**(b) A staleness alarm, separate from the failure alarm.** Prior art: the dead man's switch,
Nagios freshness checks, Prometheus `absent()` with `for:`. A healthy exit code on a pass that
has refused the same candidate 84 times is exactly the case those exist for. One event per
STREAK, never one per pass — which is why this is not the per-pass refusal logging DN-006
decision 7 removed.
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
from seldon.core.events import append_event, make_event
from seldon.domain.loader import load_domain_config
from tests.testdb import TEST_DATABASE

pytestmark = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
STORE = "seldon_events.jsonl"

TASK_BODY = textwrap.dedent("""\
    # CC Task — {stem}

    **Date:** 2026-09-20
    **Implements:** DN-006 decision 2.
    **Framework layer served (DN-005 §5 rule 1):** none.
    **Spend:** zero model calls. **Network:** none.

    ## 1. Do the thing.
    """)


def _git(p: Path, *a, check=True):
    return subprocess.run(["git", *a], cwd=p, check=check, capture_output=True, text=True)


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def project(tmp_path):
    """The real project's shape: a TRACKED event store, an `origin`, a stub `claude`, and a
    notifier that appends one line per call to a file this suite can count."""
    p = tmp_path / "proj"
    remote = tmp_path / "origin.git"
    (p / "cc_tasks").mkdir(parents=True)
    (p / "bin").mkdir()
    _git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    _git(p, "init", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    (p / ".gitignore").write_text(".seldon/\nlogs/\nbin/\nnotify.log\n", encoding="utf-8")
    (p / "controls.yaml").write_text(
        yaml.safe_dump({"spend": {"daily_tokens": 55_000_000}}), encoding="utf-8")
    (p / STORE).write_text("", encoding="utf-8")
    (p / "cc_tasks" / "t1.md").write_text(TASK_BODY.format(stem="t1"), encoding="utf-8")
    stub = p / "bin" / "claude"
    stub.write_text("#!/bin/sh\necho 'stub cc'\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    (p / "seldon.yaml").write_text(yaml.safe_dump({
        "event_store": {"path": STORE},
        "neo4j": {"database": NEO4J_DB,
                  "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687")},
        "project": {"domain": "research", "name": "t", "slug": "t"},
        "dispatch": {"enabled": True, "branch": "main",
                     "standing_band_ref": "controls.yaml#spend.daily_tokens",
                     "poll_interval_s": 300, "permission_mode": "bypassPermissions",
                     "stop_file": ".seldon/DISPATCH_STOP", "log_dir": "logs/dispatch",
                     "lease_file": ".seldon/dispatch.lock",
                     "cli": str(p / "bin" / "claude"),
                     "stuck_after_passes": 3,
                     "notify": f"echo \"$SELDON_NOTIFY_OUTCOME $SELDON_NOTIFY_CRITERION "
                               f"$SELDON_NOTIFY_PASSES $SELDON_NOTIFY_DIRTY_PATHS\" "
                               f">> {p}/notify.log"},
    }, sort_keys=False), encoding="utf-8")
    _git(p, "add", "-A")
    _git(p, "commit", "-m", "init")
    _git(p, "remote", "add", "origin", str(remote))
    _git(p, "push", "-u", "origin", "main")
    return p


def _register(project, driver, domain_config, rel="cc_tasks/t1.md", commit=True) -> str:
    tid = create_artifact(
        project_dir=project, driver=driver, database=NEO4J_DB, domain_config=domain_config,
        artifact_type="ResearchTask",
        properties={"description": "stub task", "name": Path(rel).stem, "source_file": rel,
                    "created_at": "2026-09-20T00:00:00Z"},
        actor="desktop", authority="accepted")
    if commit:
        _git(project, "commit", "-q", "-m", f"register {rel}", "--", STORE)
        _git(project, "push", "-q")
    return tid


def _run(project, argv):
    prev = Path.cwd()
    os.chdir(project)
    try:
        return CliRunner().invoke(dispatch_group, argv, catch_exceptions=False)
    finally:
        os.chdir(prev)


def _events(project, event_type=None):
    out = []
    for ln in (project / STORE).read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        ev = json.loads(ln)
        if event_type is None or ev["event_type"] == event_type:
            out.append(ev)
    return out


def _notifications(project):
    path = project / "notify.log"
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def _porcelain(project):
    return _git(project, "status", "--porcelain").stdout


# ==========================================================================================
# (a) the journal commits itself
# ==========================================================================================

def test_a_pass_commits_an_uncommitted_desktop_line_and_dispatches(project, neo4j_driver,
                                                                   domain_config):
    """Decision 6a's other half: what a tool could not commit, the next pass commits.

    `COMMITTABLE_ACTORS` gained `desktop`. Before it, this line made c7 false for the whole
    queue and the pass refused — forever, with exit 0.
    """
    _register(project, neo4j_driver, domain_config, commit=False)
    assert _porcelain(project).strip(), "the fixture did not leave the store dirty"
    out = _run(project, ["once"])
    assert out.exit_code == 0, out.output
    assert "launching" in out.output, out.output
    assert _porcelain(project).strip() == "", _porcelain(project)


def test_an_uncommitted_cc_line_still_refuses(project, neo4j_driver, domain_config):
    """The DD-019 guard, unchanged. A dispatched session's uncommitted event is not a line to
    launder under a dispatcher message."""
    _register(project, neo4j_driver, domain_config, commit=True)
    append_event(project, make_event(event_type="artifact_updated", actor="cc",
                                     authority="accepted", payload={"note": "mid-session"}))
    out = _run(project, ["once"])
    assert out.exit_code == 0, out.output
    assert "launching" not in out.output
    assert "NOT committed" in out.output
    assert "cc" in out.output


def test_an_mcp_write_tool_commits_its_own_append(project, neo4j_driver):
    """Decision 6a. `seldon_task_create` used to leave the store modified and the queue stuck."""
    from seldon import mcp_server

    before = _git(project, "rev-parse", "HEAD").stdout.strip()
    out = mcp_server.seldon_task_create("a task from Desktop", project_dir=str(project))
    assert "Created ResearchTask" in out, out
    assert "committed" in out, out
    assert _porcelain(project).strip() == "", _porcelain(project)
    after = _git(project, "rev-parse", "HEAD").stdout.strip()
    assert after != before
    message = _git(project, "log", "-1", "--format=%s").stdout
    assert "desktop:" in message and "artifact_created" in message


def test_an_mcp_write_tool_defers_while_a_lease_is_held(project, neo4j_driver):
    """A `git commit` beside a working dispatched session is DD-019's class and an
    `index.lock` collision besides. The next pass commits what this one could not."""
    from seldon import mcp_server

    lease = project / ".seldon" / "dispatch.lock"
    lease.parent.mkdir(parents=True, exist_ok=True)
    lease.write_text(json.dumps({"holder": "dispatcher:h:1", "pid": os.getpid(),
                                 "task": "x"}), encoding="utf-8")
    out = mcp_server.seldon_task_create("a task during a dispatch", project_dir=str(project))
    assert "Created ResearchTask" in out, out
    assert "lease_held" in out, out
    assert _porcelain(project).strip(), "the append was committed under a held lease"


def test_a_project_with_no_dispatch_block_is_left_alone(tmp_path, neo4j_driver):
    """The dispatcher is opt-in per project, and so is its hygiene: a project that never
    installed it does not start making commits because an MCP tool ran."""
    from seldon import mcp_server

    p = tmp_path / "plain"
    p.mkdir()
    (p / STORE).write_text("", encoding="utf-8")
    (p / "seldon.yaml").write_text(yaml.safe_dump({
        "event_store": {"path": STORE},
        "neo4j": {"database": NEO4J_DB,
                  "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687")},
        "project": {"domain": "research", "name": "t", "slug": "t"},
    }), encoding="utf-8")
    out = mcp_server.seldon_task_create("no dispatcher here", project_dir=str(p))
    assert "Created ResearchTask" in out, out
    assert "committed" not in out, out


# ==========================================================================================
# (b) the staleness alarm
# ==========================================================================================

def _make_stuck(project):
    """One untracked stray file: c7 false for the whole queue, which is the real incident's
    shape — the dirt was a task file nobody had registered, not the task being refused."""
    (project / "stray.md").write_text("left behind by a Desktop turn\n", encoding="utf-8")


def test_three_identical_refusals_produce_one_event_and_one_notification(
        project, neo4j_driver, domain_config):
    _register(project, neo4j_driver, domain_config, commit=True)
    _make_stuck(project)
    for _ in range(3):
        out = _run(project, ["once"])
        assert out.exit_code == 0, out.output
    stuck = _events(project, D.EVENT_STUCK)
    assert len(stuck) == 1, [e["payload"] for e in stuck]
    payload = stuck[0]["payload"]
    assert payload["criterion"] == "dirty_tree"
    assert payload["passes"] == 3
    assert payload["threshold"] == 3
    assert "stray.md" in payload["dirty_paths"]
    assert len(_notifications(project)) == 1, _notifications(project)
    assert _notifications(project)[0].startswith("stuck dirty_tree 3")
    assert "stray.md" in _notifications(project)[0]


def test_a_fourth_pass_produces_nothing(project, neo4j_driver, domain_config):
    _register(project, neo4j_driver, domain_config, commit=True)
    _make_stuck(project)
    for _ in range(4):
        _run(project, ["once"])
    assert len(_events(project, D.EVENT_STUCK)) == 1
    assert len(_notifications(project)) == 1


def test_it_is_silent_below_the_threshold(project, neo4j_driver, domain_config):
    _register(project, neo4j_driver, domain_config, commit=True)
    _make_stuck(project)
    for _ in range(2):
        _run(project, ["once"])
    assert _events(project, D.EVENT_STUCK) == []
    assert _notifications(project) == []


def test_a_cleared_then_recurring_refusal_alarms_again(project, neo4j_driver, domain_config):
    """Re-arm. A staleness alarm that fires once per process lifetime is an alarm that stops
    working the first time somebody fixes something."""
    _register(project, neo4j_driver, domain_config, commit=True)
    _make_stuck(project)
    for _ in range(3):
        _run(project, ["once"])
    assert len(_events(project, D.EVENT_STUCK)) == 1

    # Cleared: the task launches, nothing is refused.
    (project / "stray.md").unlink()
    _run(project, ["once"])
    assert len(_events(project, D.EVENT_STUCK)) == 1

    # And it recurs, on a task that is refused again.
    _register(project, neo4j_driver, domain_config, rel="cc_tasks/t2.md", commit=False)
    (project / "cc_tasks" / "t2.md").write_text(TASK_BODY.format(stem="t2"), encoding="utf-8")
    _git(project, "add", "cc_tasks/t2.md")
    _git(project, "commit", "-q", "-m", "t2")
    _make_stuck(project)
    for _ in range(3):
        _run(project, ["once"])
    assert len(_events(project, D.EVENT_STUCK)) == 2, \
        [e["payload"]["passes"] for e in _events(project, D.EVENT_STUCK)]
    # Two STUCK notifications. The pass in the middle launched the task and its stub wrote no
    # RESULT, so there is also one `blocked` finish notification on the same channel — which
    # is the point of `SELDON_NOTIFY_OUTCOME`: one channel, three outcomes a template can tell
    # apart.
    stuck_lines = [ln for ln in _notifications(project) if ln.startswith("stuck ")]
    assert len(stuck_lines) == 2, _notifications(project)


def test_the_refusal_line_names_the_dirty_paths(project, neo4j_driver, domain_config):
    """The log line pointed at the task file for seven hours. The task file was not the dirt."""
    _register(project, neo4j_driver, domain_config, commit=True)
    _make_stuck(project)
    out = _run(project, ["once"])
    assert "dirty_tree" in out.output
    assert "dirty: stray.md" in out.output, out.output


def test_a_dry_run_writes_no_streak_and_no_event(project, neo4j_driver, domain_config):
    _register(project, neo4j_driver, domain_config, commit=True)
    _make_stuck(project)
    for _ in range(5):
        _run(project, ["once", "--dry-run"])
    assert _events(project, D.EVENT_STUCK) == []
    assert not (project / ".seldon" / D.STUCK_STATE_FILE).exists()


def test_the_streak_rule_is_pure_and_re_arms(monkeypatch):
    """`advance_stuck` alone: the whole re-arm rule without a clock, a graph or a notifier."""
    state, alarms = {}, []
    for _ in range(3):
        state, alarms = D.advance_stuck(state, {"t": {"criterion": "dirty_tree"}}, 3, "now")
    assert alarms == ["t"]
    state, alarms = D.advance_stuck(state, {"t": {"criterion": "dirty_tree"}}, 3, "now")
    assert alarms == []
    # The criterion CHANGES: a new streak, and a new alarm at the threshold.
    state, alarms = D.advance_stuck(state, {"t": {"criterion": "above_band"}}, 1, "now")
    assert alarms == ["t"] and state["t"]["passes"] == 1
    # It CLEARS: the entry goes, so the same criterion later alarms again.
    state, alarms = D.advance_stuck(state, {}, 1, "now")
    assert state == {} and alarms == []


def test_the_threshold_comes_from_the_config_and_is_validated(project):
    cfg = D.load_dispatch_config(project)
    assert cfg["stuck_after_passes"] == 3
    text = (project / "seldon.yaml").read_text(encoding="utf-8")
    (project / "seldon.yaml").write_text(
        text.replace("stuck_after_passes: 3", "stuck_after_passes: 0"), encoding="utf-8")
    with pytest.raises(D.DispatchConfigError, match="positive whole number"):
        D.load_dispatch_config(project)


def test_the_default_is_three_when_the_key_is_absent(project):
    text = (project / "seldon.yaml").read_text(encoding="utf-8")
    (project / "seldon.yaml").write_text(
        "\n".join(ln for ln in text.splitlines() if "stuck_after_passes" not in ln) + "\n",
        encoding="utf-8")
    assert D.load_dispatch_config(project)["stuck_after_passes"] == \
        D.STUCK_AFTER_PASSES_DEFAULT
