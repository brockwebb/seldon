"""SEL-042 Parts B and C: a stopped session is never merged or completed, nothing merges without gate evidence, the
disk station leaves a run inside its allowance alone, and the merge round cannot refuse its own fast-forward.

`cc_tasks/2026-11-21_SEL-042_a_stopped_session_is_never_merged_or_completed_the_merge_round_cannot_refuse_itself_and_verify_reads_pending_records.md`
and AD-034 ADDENDUM 11 (AD-034-R25 to R28).

- B (hazbrief `de40f402`): HB-197 and HB-198 were hard-stopped by `disk_ceiling` in their gates; each Stop gate then
  "passed" with no check to run, and the round merged and completed both (`regated: false`, `gate: null`). The fixture
  is cut from hazbrief's store (`tests/fixtures/sel042/hb197_hb198_events.jsonl`, `docs/evidence/sel042/cut_fixture.py`).
- C (hazbrief `6a9c00fa`): the round's `kept_events_deduped` line, appended to main's store between the journal commit
  and the fast-forward, made git refuse the fast-forward three times (`ff_refused`). The branch's own session commit,
  which appended the lines main had already reconciled, restores them on every rebase.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from seldon.commands import dispatch as S
from seldon.commands import dispatch_worktree as W
from seldon.commands.dispatch import dispatch_group
from seldon.config import load_project_config
from seldon.core import dispatch as D
from seldon.core import kept_events as K
from seldon.core.events import make_event, read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    NEO4J_DB, RESEARCH_YAML, SELDON_REPO, add_task, git, make_project, register, run_cli, write_stub,
)

FIXTURE = SELDON_REPO / "tests" / "fixtures" / "sel042" / "hb197_hb198_events.jsonl"
STORE = "seldon_events.jsonl"


@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _fixture(task: str, kind: str) -> dict:
    rows = [json.loads(x) for x in FIXTURE.read_text().splitlines() if x.strip()]
    (row,) = [r for r in rows if r["task"] == task and r["event_type"] == kind]
    return row


def _finished(p, stem=None) -> list:
    return [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_FINISHED
            and (stem is None or e["payload"].get("source_file") == f"cc_tasks/{stem}.md")]


def _state(driver, aid) -> dict:
    with driver.session(database=NEO4J_DB) as s:
        return dict(s.run("MATCH (t:ResearchTask {artifact_id: $id}) RETURN t.state AS state, "
                          "t.block_reason AS reason", id=aid).single())


def _once(p):
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    return res.output


def _on_main(p, rel) -> bool:
    import subprocess
    return subprocess.run(["git", "-C", str(p), "cat-file", "-e", f"main:{rel}"], capture_output=True).returncode == 0


# ======================================================================== the evidence in the fixture (no Neo4j)

@pytest.mark.parametrize("task", ["HB-197", "HB-198"])
def test_the_hazbrief_stop_gates_passed_with_no_check_run_and_are_not_evidence(tmp_path, task):
    """HB-197's three Parts each had `checks: []`; HB-198 declared none. The finish read both as a pass, and nothing
    else stood for a gate (`regated: false`, `gate: null`). A pass that ran no check is not evidence."""
    p = tmp_path / "p"
    p.mkdir()
    gate_row = _fixture(task, "stop_gate")
    (p / STORE).write_text(json.dumps({k: v for k, v in gate_row.items() if k != "task"} | {"authority": "accepted"})
                           + "\n")
    reading = S._gate_reading(p, gate_row["payload"]["task_id"], gate_row["payload"]["child_session_id"])
    assert reading["passed"] is True and reading["checks_run"] == 0, reading
    fin = _fixture(task, "dispatch_finished")["payload"]
    assert fin["outcome"] == "merged" and fin["merge"]["regated"] is False and fin["merge"]["gate"] is None
    assert W.gate_evidence({"stop_gate": reading}, None, None) is None


def test_each_evidence_counts_in_its_order():
    passed = {"verdict": "pass", "checks_run": 2}
    assert W.gate_evidence({"stop_gate": passed}, None, None)["source"] == "stop_gate"
    assert W.gate_evidence({"stop_gate": passed}, {"ok": True}, None)["source"] == "regate"
    assert W.gate_evidence({"stop_gate": passed}, {"ok": True}, {"tree": "t"})["source"] == "gate_record"
    assert W.gate_evidence({"regate": {"regate_id": "r", "checks": ["true"]}}, None, None)["source"] == "kept_regate"
    assert W.gate_evidence({"stop_gate": {"verdict": "pass", "checks_run": 0}}, {"ok": False}, None) is None
    assert W.gate_evidence({"stop_gate": {"verdict": "block", "checks_run": 3}}, None, None) is None


@pytest.mark.parametrize("task", ["HB-197", "HB-198"])
def test_both_hazbrief_runs_used_more_than_their_allowance_so_the_disk_stop_stands(task):
    """Part B's measurement: HB-197 was admitted with 16.87 GB free against a need of 4.98 GB and stopped at 4.07 GB;
    HB-198 with 14.12 GB against 4.99 GB and stopped at 4.56 GB. Each volume lost more than the run's allowance (its
    need), so AD-034-R28 stops both as the station did."""
    launch = _fixture(task, "dispatch_launched")["payload"]["criteria"]["c12"]
    stop = _fixture(task, "session_stop")["payload"]["reading"]
    got = D.disk_in_run(stop, launch)
    assert got["within_allowance"] is False and got["ok"] is False, got
    assert got["consumed_bytes"] == launch["free_bytes"] - stop["free_bytes"] > launch["need_bytes"]


def test_a_run_inside_its_allowance_is_not_stopped_for_its_own_disk():
    """Admitted with 6 GB free against a 5 GB need; its own work then uses 3 GB. Free (3 GB) is below the need, which
    stopped it before; it is inside the 5 GB it was admitted for, so it runs on."""
    launch = {"free_bytes": 6_000_000_000, "need_bytes": 5_000_000_000}
    now = {"free_bytes": 3_000_000_000, "need_bytes": 5_000_000_000, "ok": False}
    got = D.disk_in_run(now, launch)
    assert got["ok"] is True and got["within_allowance"] is True and got["consumed_bytes"] == 3_000_000_000
    # One byte past the allowance, with free below the need: stopped as before.
    assert D.disk_in_run({**now, "free_bytes": 999_999_999}, launch)["ok"] is False
    # Past the allowance but free still above the need: never stopped (the reading was ok).
    assert D.disk_in_run({"free_bytes": 50, "need_bytes": 10, "ok": True}, {"free_bytes": 100, "need_bytes": 1})["ok"]
    # A launch recorded without a c12 reading is read as before the ruling.
    assert D.disk_in_run(now, None)["ok"] is False and "within_allowance" not in D.disk_in_run(now, None)


# ======================================================================== end to end through the dispatcher

def _hard_stop_line(task_id: str) -> str:
    """HB-198's `session_stop`, re-stamped into this run (ten minutes ahead, so after the launch the stub is spec-written before) and pointed at this task."""
    row = _fixture("HB-198", "session_stop")
    ev = make_event("session_stop", "dispatcher", "accepted", {**row["payload"], "task_id": task_id})
    ev["timestamp"] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    return json.dumps(ev) + "\n"


@pytest.mark.usefixtures("neo4j_available")
def test_a_hard_stopped_session_is_blocked_with_the_stops_reason_and_never_merged(tmp_path, neo4j_driver, dc):
    """HB-198 reproduced: the dispatcher's `disk_ceiling` stop lands in the store while the session runs; the session
    still exits 0 with its RESULT committed, and its Stop gate (none declared) lets it go. Before this task the round
    merged and completed it. Now: blocked `hard_stopped: disk_ceiling`, nothing on main, worktree kept."""
    p = make_project(tmp_path)
    add_task(p, "a")
    tid = register(p, neo4j_driver, dc, "a", "2026-11-21T00:00:01Z")
    write_stub(p, {"a": {"write": {"out/a.txt": "a\n"}, "worktree_name": "a",
                         "primary_append": {STORE: _hard_stop_line(tid)}}})
    _once(p)
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == W.HARD_STOPPED and fin["ok"] is False, fin
    assert fin["hard_stop"]["reasons"] == ["disk_ceiling"]
    st = _state(neo4j_driver, tid)
    assert st["state"] == "blocked" and "hard_stopped: disk_ceiling" in st["reason"], st
    assert not _on_main(p, "out/a.txt") and (p / ".claude" / "worktrees" / "a").is_dir()


@pytest.mark.usefixtures("neo4j_available")
def test_a_branch_with_no_gate_evidence_in_a_project_with_no_gate_is_ungated(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path, dispatch_extra={"gate_command": None})
    add_task(p, "a")
    tid = register(p, neo4j_driver, dc, "a", "2026-11-21T00:00:01Z")
    write_stub(p, {"a": {"write": {"out/a.txt": "a\n"}, "worktree_name": "a"}})
    _once(p)
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merge_blocked" and fin["merge"]["reason"] == W.UNGATED, fin
    assert _state(neo4j_driver, tid)["state"] == "blocked"
    assert not _on_main(p, "out/a.txt")


@pytest.mark.usefixtures("neo4j_available")
def test_a_normal_green_finish_merges_on_the_rounds_own_gate(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)          # the scaffold declares `gate_command: true`
    add_task(p, "a")
    tid = register(p, neo4j_driver, dc, "a", "2026-11-21T00:00:01Z")
    write_stub(p, {"a": {"write": {"out/a.txt": "a\n"}, "worktree_name": "a"}})
    _once(p)
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merged", fin
    assert fin["merge"]["gate_evidence"]["source"] == "merge_gate" and fin["merge"]["regated"] is False
    assert _state(neo4j_driver, tid)["state"] == "completed" and _on_main(p, "out/a.txt")


@pytest.mark.usefixtures("neo4j_available")
def test_the_rounds_own_gate_red_keeps_the_branch_off_main(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path, dispatch_extra={"gate_command": "false"})
    add_task(p, "a")
    tid = register(p, neo4j_driver, dc, "a", "2026-11-21T00:00:01Z")
    write_stub(p, {"a": {"write": {"out/a.txt": "a\n"}, "worktree_name": "a"}})
    _once(p)
    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merge_blocked" and fin["merge"]["reason"] == "regate_red", fin
    assert fin["merge"]["evidence_gate"] is True
    assert _state(neo4j_driver, tid)["state"] == "blocked" and not _on_main(p, "out/a.txt")


# ======================================================================== C: the round that refused itself

def _session_lines(n: int) -> str:
    out = []
    for i in range(n):
        ev = make_event("note_recorded", "cc", "accepted", {"note": f"the session's own line {i}"})
        out.append(json.dumps(ev) + "\n")
    return "".join(out)


@pytest.mark.usefixtures("neo4j_available")
def test_a_branch_whose_rebase_restores_reconciled_lines_merges_in_one_attempt(tmp_path, neo4j_driver, dc):
    """hazbrief HB-189, reproduced. The session's own commit appended three event lines; its first finish was kept,
    and the kept-events reconcile put those lines on main (AD-038-R25). Every rebase replays that commit, so the
    branch holds each id twice until the round drops its copy. With a journal line waiting in main (what a station
    wrote during the run), the round commits the journals, rebases over that housekeeping commit, drops again, and
    fast-forwards. Before this task the drop's record was appended to main's store in between, so git refused the
    fast-forward on every attempt (`ff_refused` after three). Now: one attempt, merged, each id once on main."""
    p = make_project(tmp_path, dispatch_extra={"merge_attempts": 3})
    add_task(p, "a")
    tid = register(p, neo4j_driver, dc, "a", "2026-11-21T00:00:01Z")
    lines = _session_lines(3)
    ids = [json.loads(x)["event_id"] for x in lines.splitlines()]
    write_stub(p, {"a": {"write": {"out/a.txt": "a\n", STORE: lines}, "worktree_name": "a", "exit": 1}})
    _once(p)
    kept = _finished(p, "a")[-1]
    assert kept["outcome"] == "session_failed", kept
    assert set(ids) <= K.reconciled_ids(p, STORE, tid), "the first finish reconciled the branch's lines into main"
    # HB-189's second session, merged into the first's branch: lines of its own that main does not hold yet, so the
    # fast-forward changes main's store (without them it would not touch the store, and git would not refuse).
    wt = p / kept["worktree"]
    second = _session_lines(2)
    with (wt / STORE).open("a", encoding="utf-8") as fh:
        fh.write(second)
    git(wt, "commit", "-q", "-m", "the second session's work", "--", STORE)

    # A station's line in main's store, uncommitted, as the round finds it.
    with (p / STORE).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(make_event("stop_gate", "cc", "accepted", {"task_id": tid, "verdict": "pass"})) + "\n")
    S.transition_task(project_dir=p, driver=neo4j_driver, database=NEO4J_DB, domain_config=dc, artifact_id=tid,
                      current_state="blocked", new_state="in_progress", actor=S.ACTOR, authority="accepted")
    extra = {"stem": "a", "branch": kept["branch"], "source_file": kept["source_file"],
             "worktree": kept["worktree"], "linked": kept.get("linked") or []}
    config = load_project_config(p)
    W._merge(p, config, neo4j_driver, NEO4J_DB, dc, None, D.load_dispatch_config(p, config), kept, "a", extra)

    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merged" and fin["merge"]["attempts"] == 1, fin.get("merge")
    main_ids = [e["event_id"] for e in read_events(p)]
    assert all(main_ids.count(i) == 1 for i in ids), [main_ids.count(i) for i in ids]
    dedupes = [e for e in read_events(p) if e["event_type"] == "kept_events_deduped"]
    assert dedupes and all(set(d["payload"]["event_ids"]) <= set(ids) for d in dedupes)
    assert git(p, "status", "--porcelain", "--", STORE).stdout == "", "the round's own lines were committed"
    assert _on_main(p, "out/a.txt")
