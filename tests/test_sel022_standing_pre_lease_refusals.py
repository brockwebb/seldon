"""SEL-022: the DD-007 refusal rings the stuck alarm once and stops dirtying the event log.

From 2026-10-31 07:42 to 2026-11-01 00:57 hazbrief-mcp's dispatcher refused every pass on `api_key_present`
(a one-day key in its `.env`). The refusal was right; nothing surfaced it. It was refused before the lease and
outside the stuck streak, so it never reached `dispatch_stuck` or `dispatch.notify`, and it appended a
`dispatch_refused` to the tracked event store on every pass, keeping the tree dirty.

Now it is a standing condition (AD-038-R6's outage-once pattern, FRICTION-001 Part E): one `dispatch_refused` per
outage, one `dispatch_stuck` and one notification when its streak reaches `api_key_present: 1`, the lines committed
the way an MCP write commits its own (`commit_journal_append`: the lease is probed, never taken, so the DD-007 check
stays before any lease and any claim), and the first pass without the key clears the state. A lease whose holder PID
is dead joins the streak the same way, naming `lease reap`; a live holder's lease is unchanged.

Scratch repository, stub `claude`, zero model calls.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
from pathlib import Path

import pytest

from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core.events import read_events
from tests.dispatch_scaffold import git, make_project, run_cli

PLANTED = "sk-ant-sel022-planted-not-a-real-key"


@pytest.fixture
def proj(tmp_path, monkeypatch, neo4j_available, clean_test_db):
    # setenv-then-delenv so monkeypatch's undo deletes whatever `load_dotenv` puts in os.environ later: the pass
    # loads the project's `.env` into THIS process, which a fresh launchd process would not carry to the next test.
    for var in D.API_KEY_VARS:
        monkeypatch.setenv(var, "x")
        monkeypatch.delenv(var)
    p = make_project(tmp_path, dispatch_extra={
        "notify": f"echo \"$SELDON_NOTIFY_OUTCOME $SELDON_NOTIFY_CRITERION $SELDON_NOTIFY_MESSAGE\" "
                  f">> {tmp_path}/notify.log"})
    with (p / ".gitignore").open("a", encoding="utf-8") as fh:
        fh.write(".env\n")
    git(p, "add", ".gitignore")
    git(p, "commit", "-q", "-m", "ignore .env")
    return p


def _notified(tmp_path) -> list:
    f = tmp_path / "notify.log"
    return f.read_text().splitlines() if f.is_file() else []


def _of(p, kind, reason=None) -> list:
    return [e for e in read_events(p) if e["event_type"] == kind
            and (reason is None or (e["payload"].get("reason") or e["payload"].get("criterion")) == reason)]


def _porcelain(p) -> str:
    return git(p, "status", "--porcelain").stdout


def test_the_default_thresholds_ring_api_key_present_on_its_first_pass():
    assert D.STUCK_AFTER_PASSES_BY_CRITERION_DEFAULT["api_key_present"] == 1
    assert D.STUCK_AFTER_PASSES_BY_CRITERION_DEFAULT["dirty_tree"] == 1


def test_a_copied_project_map_still_rings_api_key_present_on_its_first_pass(tmp_path):
    """The consumers carry the kit's `{dirty_tree: 1}` map, copied by `dispatch adopt` before this key existed."""
    (tmp_path / "controls.yaml").write_text("spend:\n  daily_tokens: 1\n", encoding="utf-8")

    def load(by):
        block = {"enabled": False, "branch": "main", "standing_band_ref": "controls.yaml#spend.daily_tokens",
                 "poll_interval_s": 300, "permission_mode": "bypassPermissions", "stop_file": ".seldon/STOP",
                 "log_dir": "logs/dispatch", "lease_file": ".seldon/dispatch.lock"}
        if by is not None:
            block["stuck_after_passes_by_criterion"] = by
        return D.load_dispatch_config(tmp_path, {"dispatch": block})["stuck_after_passes_by_criterion"]

    assert load({"dirty_tree": 1}) == {"dirty_tree": 1, "api_key_present": 1}
    assert load({}) == {"api_key_present": 1}                 # dirty_tree keeps the meaning an empty map gave it
    assert load({"api_key_present": 4}) == {"api_key_present": 4}
    assert load(None) == D.STUCK_AFTER_PASSES_BY_CRITERION_DEFAULT


def test_a_planted_key_rings_once_writes_nothing_more_and_clears_when_removed(proj, tmp_path):
    p = proj
    (p / ".env").write_text(f"ANTHROPIC_API_KEY={PLANTED}\n", encoding="utf-8")

    first = run_cli(p, dispatch_group, ["once"])
    assert first.exit_code == 0, first.output
    assert "ANTHROPIC_API_KEY is set" in first.output
    stuck = _of(p, D.EVENT_STUCK, "api_key_present")
    assert len(stuck) == 1, stuck
    assert stuck[0]["payload"]["variable"] == "ANTHROPIC_API_KEY"
    assert stuck[0]["payload"]["task_id"] is None
    assert len(_of(p, D.EVENT_REFUSED, "api_key_present")) == 1
    assert len(_notified(tmp_path)) == 1 and _notified(tmp_path)[0].startswith("stuck api_key_present")
    assert PLANTED not in (p / "seldon_events.jsonl").read_text()          # the name, never the value
    assert PLANTED not in (tmp_path / "notify.log").read_text()
    state_file = p / ".seldon" / D.API_KEY_STATE_FILE
    assert state_file.is_file()
    assert _porcelain(p) == "", _porcelain(p)                              # its lines were committed
    assert "api_key_present" in git(p, "log", "-1", "--pretty=%s").stdout

    log_bytes = (p / "seldon_events.jsonl").read_bytes()
    head = git(p, "rev-parse", "HEAD").stdout
    for n in range(10):
        again = run_cli(p, dispatch_group, ["once"])
        assert again.exit_code == 0, again.output
        assert "ANTHROPIC_API_KEY is set" in again.output
    assert (p / "seldon_events.jsonl").read_bytes() == log_bytes
    assert git(p, "rev-parse", "HEAD").stdout == head
    assert _porcelain(p) == ""
    assert len(_notified(tmp_path)) == 1
    assert json.loads(state_file.read_text())["passes"] == 11
    assert not (p / ".seldon" / "dispatch.lock").exists()                 # no pass took the lease

    (p / ".env").write_text("# key removed\n", encoding="utf-8")
    os.environ.pop("ANTHROPIC_API_KEY", None)        # a launchd pass is a fresh process; this one loaded `.env`
    back = run_cli(p, dispatch_group, ["once"])
    assert back.exit_code == 0, back.output
    assert "is set" not in back.output
    assert "api_key_present cleared after 11 refused pass(es)" in back.output, back.output
    assert not state_file.exists()
    stuck_state = p / ".seldon" / D.STUCK_STATE_FILE
    assert not stuck_state.exists() or D.standing_key("api_key_present") not in json.loads(stuck_state.read_text())

    (p / ".env").write_text(f"ANTHROPIC_API_KEY={PLANTED}\n", encoding="utf-8")   # a new outage rings afresh
    run_cli(p, dispatch_group, ["once"])
    assert len(_of(p, D.EVENT_STUCK, "api_key_present")) == 2
    assert len(_notified(tmp_path)) == 2


def test_a_dry_run_under_a_planted_key_writes_nothing(proj, tmp_path):
    p = proj
    (p / ".env").write_text(f"ANTHROPIC_API_KEY={PLANTED}\n", encoding="utf-8")
    out = run_cli(p, dispatch_group, ["once", "--dry-run"])
    assert out.exit_code == 0 and "ANTHROPIC_API_KEY is set" in out.output
    assert (p / "seldon_events.jsonl").read_text() == ""
    assert not (p / ".seldon" / D.API_KEY_STATE_FILE).exists()
    assert _notified(tmp_path) == []


def _dead_pid() -> int:
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


class _HeldLease:
    """The flock held on a separate open file (as an orphaned child that inherited it would hold it), with a body
    naming `pid` as the holder."""

    def __init__(self, path: Path, pid: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = path.open("a+", encoding="utf-8")
        fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.fh.seek(0)
        self.fh.truncate()
        self.fh.write(json.dumps({"holder": f"dispatcher:test:{pid}", "pid": pid,
                                  "acquired_at": "2026-11-01T00:00:00Z", "heartbeat_at": "2026-11-01T00:00:00Z",
                                  "task": None}) + "\n")
        self.fh.flush()

    def close(self):
        fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        self.fh.close()


def test_a_dead_holder_lease_rings_once_naming_lease_reap(proj, tmp_path):
    p = proj
    held = _HeldLease(p / ".seldon" / "dispatch.lock", _dead_pid())
    try:
        threshold = D.STUCK_AFTER_PASSES_DEFAULT
        for _ in range(threshold + 4):
            out = run_cli(p, dispatch_group, ["once"])
            assert out.exit_code == 0, out.output
    finally:
        held.close()
    stuck = _of(p, D.EVENT_STUCK, "lease_held")
    assert len(stuck) == 1, stuck
    assert stuck[0]["payload"]["passes"] == threshold
    assert "seldon dispatch lease reap" in stuck[0]["payload"]["remedy"]
    assert len(_of(p, D.EVENT_REFUSED, "lease_held")) == 1                 # once per acquisition, as before
    notes = _notified(tmp_path)
    assert len(notes) == 1 and notes[0].startswith("stuck lease_held") and "lease reap" in notes[0], notes


def test_a_live_holder_lease_raises_no_stuck_event(proj, tmp_path):
    p = proj
    held = _HeldLease(p / ".seldon" / "dispatch.lock", os.getpid())
    try:
        for _ in range(D.STUCK_AFTER_PASSES_DEFAULT + 2):
            assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    finally:
        held.close()
    assert _of(p, D.EVENT_STUCK) == []
    assert _notified(tmp_path) == []
    assert len(_of(p, D.EVENT_REFUSED, "lease_held")) == 1

