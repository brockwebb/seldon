"""The dispatcher commits and pushes the lines it writes to the tracked event store.

`ai-readiness-kg/cc_tasks/2026-09-16_dispatcher_commits_its_record.md` decisions 1 and 2, and
DN-006 ADDENDUM_04, which closes ADDENDUM_03 §4: every completed dispatch used to leave
`seldon_events.jsonl` modified by `dispatch_finished` — a line only the dispatcher wrote — and
the cadence gates creation on a clean tree, so the first period that one line could block was
cycle 5 on 2026-10-05.

**The check is the tree, not the event.** After a pass, `git status --porcelain` on the store is
empty unless a session is in flight. Every test below states its claim that way.

**Push is exercised against a bare repository on local disk.** A `file://`-shaped remote is a
real `git push` with the real ahead/behind bookkeeping and no network, so decision 2's retry is
tested without contacting a host.

These need Neo4j for the reason `test_dispatch_launch.py` gives: the claim is a graph
transition, and a mocked one would test the mock.
"""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core.artifacts import create_artifact
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
SELDON_REPO = Path(__file__).resolve().parents[1]
STORE = "seldon_events.jsonl"

pytestmark = pytest.mark.usefixtures("neo4j_available")

TASK_BODY = textwrap.dedent("""\
    # CC Task — {stem}

    **Date:** 2026-09-16
    **Framework layer served (DN-005 §5 rule 1):** §2.2 Tier M
    **Spend:** zero model calls. **Network:** none.

    ## 1. Do the thing.
    """)

TEMPLATE = textwrap.dedent("""\
    # CC Task — cycle {cycle_name}, created by cadence {cadence_name} for {period}

    **Date:** {created_at}
    **Implements:** DN-006 decision 8.
    **Framework layer served (DN-005 §5 rule 1):** §2.2 Tier M
    **Spend:** zero model calls.
    **Network:** hosts, under cadence {cadence_name}

    ## 1. Run the cycle as `{cycle_name}`.
    """)

#: 2026-10-05 is the first Monday of October 2026 (hand-checked, as `test_cadence_pass.py`
#: does); 2026-09-20 is inside September, before the entry's `start_period`, so nothing is due.
DUE_AT = datetime(2026, 10, 5, 0, 30, tzinfo=timezone.utc)
NOT_DUE_AT = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _git(p: Path, *a, check=True):
    return subprocess.run(["git", *a], cwd=p, check=check, capture_output=True, text=True)


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def project(tmp_path):
    """The real project's shape: a TRACKED event store, a cadence entry, an `origin` to push
    to, and a stub `claude` on the configured path."""
    p = tmp_path / "proj"
    remote = tmp_path / "origin.git"
    (p / "cc_tasks" / "templates").mkdir(parents=True)
    (p / "bin").mkdir()
    _git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    _git(p, "init", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    (p / ".gitignore").write_text(".seldon/\nlogs/\nbin/\n", encoding="utf-8")
    (p / "controls.yaml").write_text(
        yaml.safe_dump({"spend": {"daily_tokens": 55_000_000}}), encoding="utf-8")
    (p / STORE).write_text("", encoding="utf-8")
    (p / "cc_tasks" / "templates" / "scan_cycle.md").write_text(TEMPLATE, encoding="utf-8")
    (p / "cc_tasks" / "t1.md").write_text(TASK_BODY.format(stem="t1"), encoding="utf-8")
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
                     "cadence": [{
                         "name": "scan_cycle",
                         "rule": {"monthly_first_weekday": "monday", "at_utc": "00:00"},
                         "template": "cc_tasks/templates/scan_cycle.md",
                         "instances_dir": "cc_tasks",
                         "cycle_name_format": "scan_{date}",
                         "start_period": "2026-10",
                         "last_instance": "",
                     }]},
    }, sort_keys=False), encoding="utf-8")
    _stub(p)
    _git(p, "add", "-A")
    _git(p, "commit", "-m", "init")
    _git(p, "remote", "add", "origin", str(remote))
    _git(p, "push", "-u", "origin", "main")
    return p


def _stub(project: Path, *, task_id=None, stem="t1", commit=True):
    """`claude -p`, as a script that does what a real dispatched session does at its end:
    writes the RESULT, walks the task to `completed`, and commits and pushes its own work —
    including the event store, as `CLAUDE.md` §10 requires of a session."""
    lines = ["#!/bin/sh", 'echo "stub cc: $*"', f"cd {project}"]
    if task_id:
        lines.append(f'printf "# RESULT\\n" > cc_tasks/{stem}_RESULT.md')
        lines.append(
            f'{_python()} -c "'
            f"import sys; sys.path.insert(0, {str(SELDON_REPO)!r}); "
            f"from pathlib import Path; "
            f"from seldon.core.artifacts import walk_to_completed; "
            f"from seldon.domain.loader import load_domain_config; "
            f"from seldon.config import get_neo4j_driver; "
            f"cfg={{'neo4j': {{'uri': {os.getenv('NEO4J_URI', 'bolt://localhost:7687')!r}, "
            f"'database': {NEO4J_DB!r}}}}}; "
            f"d=get_neo4j_driver(cfg); "
            f"walk_to_completed(project_dir=Path({str(project)!r}), driver=d, "
            f"database={NEO4J_DB!r}, "
            f"domain_config=load_domain_config(Path({str(RESEARCH_YAML)!r})), "
            f"artifact_id={task_id!r}, current_state='in_progress', actor='cc'); "
            f'd.close()"')
        if commit:
            lines.append(f"git add cc_tasks/{stem}_RESULT.md {STORE}")
            lines.append(f"git commit -q -m 'session: {stem}'")
            lines.append("git push -q")
    lines.append("exit 0")
    path = project / "bin" / "claude"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)


def _python() -> str:
    import sys
    return sys.executable


def _register(project, driver, domain_config, rel="cc_tasks/t1.md") -> str:
    """Register a task that is already committed, and commit the registration line too — the
    state a pass finds after decision 3 of the previous task has run."""
    tid = create_artifact(
        project_dir=project, driver=driver, database=NEO4J_DB, domain_config=domain_config,
        artifact_type="ResearchTask",
        properties={"description": "stub task", "name": Path(rel).stem, "source_file": rel,
                    "created_at": "2026-09-16T00:00:00Z"},
        actor="desktop", authority="accepted")
    _git(project, "commit", "-q", "-m", f"register {rel}", "--", STORE)
    _git(project, "push", "-q")
    return tid


@pytest.fixture
def clock(monkeypatch):
    import seldon.commands.dispatch as dispatch_cmd

    def _set(when):
        monkeypatch.setattr(dispatch_cmd, "_utcnow", lambda: when)
        return when

    _set(NOT_DUE_AT)
    return _set


def _run(project, argv):
    prev = Path.cwd()
    os.chdir(project)
    try:
        return CliRunner().invoke(dispatch_group, argv, catch_exceptions=False)
    finally:
        os.chdir(prev)


def _events(project, kind=None):
    return [e for e in read_events(project) if kind is None or e["event_type"] == kind]


def _store_status(project) -> str:
    return _git(project, "status", "--porcelain", "--", STORE).stdout


def _ahead(project) -> int:
    return int(_git(project, "rev-list", "--count", "@{u}..HEAD").stdout.strip())


def _messages(project, n=10) -> list:
    return _git(project, "log", f"-{n}", "--pretty=%s").stdout.splitlines()


# ================================================= decision 1: the finish leaves the tree clean

def test_a_finished_dispatch_leaves_the_event_store_clean(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    """ADDENDUM_03 §4, closed. The session commits and pushes its work; the dispatcher then
    writes `dispatch_finished`, and before this task nothing committed that line."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)

    res = _run(project, ["once"])
    assert res.exit_code == 0, res.output
    assert len(_events(project, D.EVENT_FINISHED)) == 1

    assert _store_status(project) == "", (
        f"the store is dirty after a finished dispatch:\n{res.output}")
    assert D.tree_state(project)["dirty"] is False


def test_the_record_commit_names_the_event_type_and_the_task(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)
    _run(project, ["once"])

    head = _messages(project, 1)[0]
    assert "dispatch_finished" in head and tid[:8] in head, head
    assert _git(project, "show", "--name-only", "--pretty=", "HEAD").stdout.split() == [STORE]


def test_the_launch_lines_are_committed_before_the_session_starts(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    """The claim's transitions and `dispatch_launched` are written BEFORE the launch. Left
    uncommitted, the session opens on a dirty tree made only of the dispatcher's lines — which
    is the state this very task's session opened in. The stub records what it saw."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)
    seen = project / "logs" / "seen_status.txt"
    stub = project / "bin" / "claude"
    body = stub.read_text(encoding="utf-8").replace(
        f"cd {project}\n",
        f"cd {project}\nmkdir -p logs\ngit status --porcelain > {seen}\n"
        f"git rev-list --count @{{u}}..HEAD >> {seen}\n", 1)
    stub.write_text(body, encoding="utf-8")

    assert _run(project, ["once"]).exit_code == 0
    lines = seen.read_text(encoding="utf-8").splitlines()
    assert lines == ["0"], f"the session started on a dirty or unpushed tree: {lines}"
    launched_msgs = [m for m in _messages(project) if "dispatch_launched" in m]
    assert launched_msgs and tid[:8] in launched_msgs[0]


def test_a_pass_after_a_finished_dispatch_creates_the_due_cadence_instance(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    """The failure the task exists for, end to end: a dispatch finishes in September, and the
    first October pass must CREATE cycle 5 rather than report `dirty_tree`."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)
    assert _run(project, ["once"]).exit_code == 0            # September: finish, nothing due

    _stub(project)                                            # October's session does nothing
    clock(DUE_AT)
    res = _run(project, ["once"])
    assert res.exit_code == 0
    assert "dirty_tree" not in res.output, res.output
    created = _events(project, D.EVENT_CADENCE_CREATED)
    assert len(created) == 1 and created[0]["payload"]["period"] == "2026-10"


def test_a_line_left_by_an_earlier_pass_is_committed_by_the_next(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    """Recovery. A pass that died between its append and its commit — or a dispatcher process
    that was still running the code from before this change — leaves dispatcher-only lines
    behind. The next pass that holds the lease commits them before it evaluates anything."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from seldon.core.events import append_event, make_event
    append_event(project, make_event(
        event_type=D.EVENT_FINISHED, actor="dispatcher", authority="accepted",
        payload={"task_id": "deadbeef-0000", "exit_code": 0, "ok": True}))
    assert _store_status(project) != ""

    res = _run(project, ["once"])
    assert res.exit_code == 0, res.output
    assert _store_status(project) == ""
    assert "deadbeef" in _messages(project, 1)[0]
    assert _ahead(project) == 0


# ============================================ what the dispatcher must never commit or stage

def test_a_line_somebody_else_wrote_is_never_committed_by_the_dispatcher(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    """The pathspec limits WHICH FILE; the actor check limits WHOSE LINES. A session that
    wrote to the store and failed to commit is a finding for the OODA, not a line for the
    dispatcher to launder under its own message — and a dirty tree is how c7 surfaces it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from seldon.core.events import append_event, make_event
    append_event(project, make_event(
        event_type="artifact_updated", actor="cc", authority="accepted",
        payload={"artifact_id": "x", "properties": {}}))
    append_event(project, make_event(
        event_type=D.EVENT_FINISHED, actor="dispatcher", authority="accepted",
        payload={"task_id": "deadbeef-0000"}))
    head = _git(project, "rev-parse", "HEAD").stdout.strip()

    res = _run(project, ["once"])
    assert res.exit_code == 0
    assert _git(project, "rev-parse", "HEAD").stdout.strip() == head
    assert _store_status(project) != ""
    assert "not dispatcher-only" in res.output


def test_nothing_outside_the_store_is_ever_staged_or_committed(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)
    (project / "operator_wip.py").write_text("x = 1\n", encoding="utf-8")
    (project / "controls.yaml").write_text(
        yaml.safe_dump({"spend": {"daily_tokens": 55_000_000}}) + "# edited\n",
        encoding="utf-8")
    staged_before = _git(project, "diff", "--cached", "--name-only").stdout

    # Operator work in the tree fails c7, so nothing launches; plant a dispatcher-only line so
    # the record commit has something to do in the same dirty checkout.
    from seldon.core.events import append_event, make_event
    append_event(project, make_event(
        event_type=D.EVENT_FINISHED, actor="dispatcher", authority="accepted",
        payload={"task_id": "deadbeef-0000"}))
    res = _run(project, ["once"])
    assert res.exit_code == 0

    assert "dispatch_finished" in _messages(project, 1)[0], res.output
    committed = _git(project, "show", "--name-only", "--pretty=", "HEAD").stdout.split()
    assert committed == [STORE], committed
    assert _git(project, "diff", "--cached", "--name-only").stdout == staged_before
    porcelain = _git(project, "status", "--porcelain").stdout
    assert "operator_wip.py" in porcelain and "controls.yaml" in porcelain


def test_a_rewritten_store_is_not_committed(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    """Append-only is the store's contract. A working copy that does not begin with HEAD's
    bytes has been edited in place, and the dispatcher does not put its name on that."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from seldon.core.events import append_event, make_event
    append_event(project, make_event(
        event_type=D.EVENT_FINISHED, actor="dispatcher", authority="accepted",
        payload={"task_id": "a"}))
    _git(project, "commit", "-q", "-m", "one line", "--", STORE)
    (project / STORE).write_text("", encoding="utf-8")
    append_event(project, make_event(
        event_type=D.EVENT_FINISHED, actor="dispatcher", authority="accepted",
        payload={"task_id": "b"}))
    head = _git(project, "rev-parse", "HEAD").stdout.strip()
    res = _run(project, ["once"])
    assert _git(project, "rev-parse", "HEAD").stdout.strip() == head
    assert "not append-only" in res.output


def test_no_commit_is_made_while_another_process_holds_the_lease(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    """A held lease means a dispatched session owns the checkout. The `lease_held` refusal is
    written (once per acquisition) and left for that session's own commit to carry: a second
    process running `git commit` beside a working session is DD-019's class and an
    `index.lock` collision besides."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lock = project / ".seldon" / "dispatch.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"holder": D.holder_id(os.getpid()), "pid": os.getpid(),
                                "acquired_at": "2026-09-16T00:00:00Z"}), encoding="utf-8")
    import fcntl
    with open(lock, "r+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        head = _git(project, "rev-parse", "HEAD").stdout.strip()
        res = _run(project, ["once"])
        assert res.exit_code == 0
        assert _events(project, D.EVENT_REFUSED)
        assert _git(project, "rev-parse", "HEAD").stdout.strip() == head
        assert _store_status(project) != ""


# ==================================================== decision 2: push, and retry a failed one

def test_the_dispatcher_pushes_what_it_commits(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)
    assert _run(project, ["once"]).exit_code == 0
    assert _ahead(project) == 0
    assert "## main...origin/main" == _git(project, "status", "-sb").stdout.splitlines()[0]


def test_a_failed_push_is_reported_is_not_a_refusal_and_is_retried_next_pass(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    good = _git(project, "remote", "get-url", "origin").stdout.strip()
    _git(project, "remote", "set-url", "origin", str(tmp_path / "offline.git"))
    from seldon.core.events import append_event, make_event
    append_event(project, make_event(
        event_type=D.EVENT_FINISHED, actor="dispatcher", authority="accepted",
        payload={"task_id": "deadbeef-0000"}))
    before = len(_events(project))

    res = _run(project, ["once"])
    assert res.exit_code == 0
    assert "push FAILED" in res.output, res.output
    assert _store_status(project) == ""                  # committed all the same
    assert _ahead(project) == 1
    after = _events(project)
    assert len(after) == before, "a push, failed or not, wrote an event"

    _git(project, "remote", "set-url", "origin", good)
    res = _run(project, ["once"])                         # nothing to commit; still ahead
    assert res.exit_code == 0
    assert "pushed" in res.output, res.output
    assert _ahead(project) == 0
    assert len(_events(project)) == before


def test_a_branch_with_no_upstream_is_reported_and_not_an_error(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _git(project, "branch", "--unset-upstream")
    from seldon.core.events import append_event, make_event
    append_event(project, make_event(
        event_type=D.EVENT_FINISHED, actor="dispatcher", authority="accepted",
        payload={"task_id": "deadbeef-0000"}))
    res = _run(project, ["once"])
    assert res.exit_code == 0
    assert _store_status(project) == ""
    assert "no upstream" in res.output


def test_two_quiet_passes_make_no_commit_and_no_event(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    """Decision 7's idempotence, extended to git: a clean, pushed checkout with nothing
    eligible is left exactly as it was — no empty commit, no push, no line."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    head = _git(project, "rev-parse", "HEAD").stdout.strip()
    store = (project / STORE).read_bytes()
    for _ in range(2):
        assert _run(project, ["once"]).exit_code == 0
    assert _git(project, "rev-parse", "HEAD").stdout.strip() == head
    assert (project / STORE).read_bytes() == store


# =========================================== decision 3: the cadence says why it is blocked

def test_a_blocked_cadence_names_the_paths_that_dirty_the_tree(
        project, neo4j_driver, domain_config, clean_test_db, clock, monkeypatch):
    """October's first pass must be readable from its log. `dirty_tree` alone is not
    actionable; `dirty_tree` with the paths is."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    clock(DUE_AT)
    (project / "operator_wip.py").write_text("x = 1\n", encoding="utf-8")
    res = _run(project, ["once"])
    assert "is due and NOT created (dirty_tree)" in res.output
    assert "operator_wip.py" in res.output
