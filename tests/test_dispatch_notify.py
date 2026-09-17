"""The dispatcher tells the operator when a task finishes.

`ai-readiness-kg/cc_tasks/2026-09-17_dispatcher_notifies.md` decision 1. Prior art: cron's
`MAILTO`, systemd's `OnSuccess=`/`OnFailure=`, a CI runner's status post — in each the runner
owns the notification and configuration names the channel. Here the channel is
`dispatch.notify` in `seldon.yaml`, a command template run after `dispatch_finished` (and after
the walk to `blocked` when the finish is not ok), with the outcome in `SELDON_NOTIFY_*`.

The contract under test:

* the notifier sees the six variables of the task file plus `SELDON_NOTIFY_OUTCOME`;
* it runs once per finish, AFTER `dispatch_finished` is on the log;
* a failing, missing or hanging notifier is ONE `dispatch_notify_failed` event and changes
  nothing else — not the finish record, not the task's state, not the exit code;
* no `notify` key means no notifier and no event.

The stub CC is `test_dispatch_launch`'s, so the spend is zero and nothing leaves the host.
"""
from __future__ import annotations

import json

import pytest
import yaml

from seldon.core import dispatch as D
from tests.testdb import TEST_DATABASE as NEO4J_DB
from tests.test_dispatch_launch import (  # noqa: F401  (fixtures re-exported for pytest)
    _events, _git, _register, _run, _state, _stub, domain_config, project,
)

pytestmark = pytest.mark.usefixtures("neo4j_available")

NOTIFY_VARS = ("SELDON_NOTIFY_TASK_ID", "SELDON_NOTIFY_TASK_NAME", "SELDON_NOTIFY_OK",
               "SELDON_NOTIFY_RESULT_PATH", "SELDON_NOTIFY_LOG_PATH",
               "SELDON_NOTIFY_WALL_SECONDS", "SELDON_NOTIFY_OUTCOME")


def _set_notify(project, command, timeout_s=None):
    cfg = yaml.safe_load((project / "seldon.yaml").read_text(encoding="utf-8"))
    cfg["dispatch"]["notify"] = command
    if timeout_s is not None:
        cfg["dispatch"]["notify_timeout_s"] = timeout_s
    (project / "seldon.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    # Committed, or c7 (clean tree) refuses every candidate and nothing is launched to notify on.
    _git(project, "commit", "-qam", "notify")


def _recording_notifier(project):
    """A notifier that writes its SELDON_NOTIFY_* environment, and the events on the log at the
    moment it ran, to a file — so a test can see both what it was told and when."""
    out = project / "logs" / "notified.json"
    script = project / "bin" / "notify.py"
    script.write_text(
        "import json, os, sys\n"
        f"store = {str(project / 'seldon_events.jsonl')!r}\n"
        "types = [json.loads(l)['event_type'] for l in open(store) if l.strip()]\n"
        f"with open({str(out)!r}, 'a') as fh:\n"
        "    fh.write(json.dumps({'env': {k: v for k, v in os.environ.items()\n"
        "                                 if k.startswith('SELDON_NOTIFY_')},\n"
        "                         'types': types}) + '\\n')\n",
        encoding="utf-8")
    import sys
    return f"{sys.executable} {script}", out


def _calls(out):
    if not out.is_file():
        return []
    return [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_a_finished_task_runs_the_notifier_once_with_the_outcome(project, neo4j_driver,
                                                                 domain_config, clean_test_db,
                                                                 monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    command, out = _recording_notifier(project)
    _set_notify(project, command)
    tid = _register(project, neo4j_driver, domain_config)
    # A name that differs from the file stem, so the assertion below can tell which one it got.
    with neo4j_driver.session(database=NEO4J_DB) as s:
        s.run("MATCH (t:ResearchTask {artifact_id: $i}) SET t.name = 'notify probe'", i=tid)
    _stub(project, task_id=tid)

    assert _run(project, ["once"]).exit_code == 0

    calls = _calls(out)
    assert len(calls) == 1
    env = calls[0]["env"]
    assert set(NOTIFY_VARS) <= set(env)
    assert env["SELDON_NOTIFY_TASK_ID"] == tid
    assert env["SELDON_NOTIFY_TASK_NAME"] == "notify probe"
    assert env["SELDON_NOTIFY_OK"] == "true"
    assert env["SELDON_NOTIFY_OUTCOME"] == "ok"
    assert env["SELDON_NOTIFY_RESULT_PATH"] == "cc_tasks/t1_RESULT.md"
    assert env["SELDON_NOTIFY_LOG_PATH"] == "logs/dispatch/t1.log"
    assert float(env["SELDON_NOTIFY_WALL_SECONDS"]) >= 0
    # AFTER the finish record, never before it: the notification reports a recorded fact.
    assert D.EVENT_FINISHED in calls[0]["types"]
    assert not _events(project, D.EVENT_NOTIFY_FAILED)


def test_a_blocked_task_notifies_once_after_the_walk_to_blocked(project, neo4j_driver,
                                                                domain_config, clean_test_db,
                                                                monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    command, out = _recording_notifier(project)
    _set_notify(project, command)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, exit_code=3, write_result=False, complete=False)

    assert _run(project, ["once"]).exit_code == 0
    assert _state(neo4j_driver, tid)[0] == "blocked"

    calls = _calls(out)
    assert len(calls) == 1, "one notification per finish, not one per record"
    env = calls[0]["env"]
    assert env["SELDON_NOTIFY_OK"] == "false"
    assert env["SELDON_NOTIFY_OUTCOME"] == "blocked"
    # The walk to `blocked` is on the log before the notifier runs.
    types = calls[0]["types"]
    assert types.index(D.EVENT_FINISHED) < len(types) - 1
    assert types[-1] == "artifact_state_changed"


@pytest.mark.parametrize("command,reason", [
    ("exit 7", "nonzero_exit"),
    ("/nonexistent/notifier --flag", "nonzero_exit"),
    ("sleep 30", "timeout"),
])
def test_a_failing_notifier_is_one_event_and_alters_nothing(project, neo4j_driver,
                                                            domain_config, clean_test_db,
                                                            monkeypatch, command, reason):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _set_notify(project, command, timeout_s=1)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)

    res = _run(project, ["once"])
    assert res.exit_code == 0, res.output

    assert _state(neo4j_driver, tid)[0] == "completed"
    finished = _events(project, D.EVENT_FINISHED)
    assert len(finished) == 1 and finished[0]["payload"]["ok"] is True
    failed = _events(project, D.EVENT_NOTIFY_FAILED)
    assert len(failed) == 1
    pl = failed[0]["payload"]
    assert pl["task_id"] == tid and pl["reason"] == reason
    assert pl["command"] == command
    assert failed[0]["actor"] == "dispatcher"


def test_no_notify_key_runs_nothing_and_writes_no_event(project, neo4j_driver, domain_config,
                                                        clean_test_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)
    res = _run(project, ["once"])
    assert res.exit_code == 0
    assert not _events(project, D.EVENT_NOTIFY_FAILED)
    assert "notif" not in res.output.lower()


@pytest.mark.parametrize("value", [["osascript"], 5, True, ""])
def test_a_notify_value_that_is_not_a_command_string_refuses_at_config_load(tmp_path, value):
    """An unreadable notifier refuses when the config is loaded, not after a task has run for an
    hour and there is nobody to tell."""
    block = {"enabled": True, "branch": "main", "standing_band_ref": "c.yaml#a",
             "poll_interval_s": 300, "permission_mode": "bypassPermissions",
             "stop_file": "s", "log_dir": "l", "lease_file": "x", "notify": value}
    with pytest.raises(D.DispatchConfigError, match="notify"):
        D.load_dispatch_config(tmp_path, {"dispatch": block})


@pytest.mark.parametrize("value", [0, -1, "30", True])
def test_a_notify_timeout_that_is_not_a_positive_number_refuses(tmp_path, value):
    block = {"enabled": True, "branch": "main", "standing_band_ref": "c.yaml#a",
             "poll_interval_s": 300, "permission_mode": "bypassPermissions",
             "stop_file": "s", "log_dir": "l", "lease_file": "x", "notify": "true",
             "notify_timeout_s": value}
    with pytest.raises(D.DispatchConfigError, match="notify_timeout_s"):
        D.load_dispatch_config(tmp_path, {"dispatch": block})


def test_the_notify_timeout_defaults_to_thirty_seconds(tmp_path):
    block = {"enabled": True, "branch": "main", "standing_band_ref": "c.yaml#a",
             "poll_interval_s": 300, "permission_mode": "bypassPermissions",
             "stop_file": "s", "log_dir": "l", "lease_file": "x"}
    cfg = D.load_dispatch_config(tmp_path, {"dispatch": block})
    assert cfg["notify"] is None
    assert cfg["notify_timeout_s"] == D.NOTIFY_TIMEOUT_S_DEFAULT == 30
