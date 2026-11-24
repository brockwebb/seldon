"""SEL-043 Part C (AD-037-R17, R18): station (a) holds a consumer only across the window in which what it reads from a
producer can change, and every refusal and `seldon dispatch status` say who holds, on which task, in which phase,
since when, and how far its gate has got.

Part A measured the old rule: 52 `environment_in_flight` refusals and 53.3 hours waited (2026-10-17 to 2026-11-24),
50.3 of them while the producer was in its session or its gate, which change nothing in the producer's primary
checkout. Every consumer imports the producers as editable installs of their PRIMARY checkouts, and a producer's
primary changes under its dispatcher only in a pass and in the merge round outside its gate (the fast-forward, the
journal and numbering commits) — and, in any phase, where its session writes another repository by path (a task's
Repo line, DISP-004R).

The two-repository fixture is a consumer project with a scratch Neo4j and a sibling producer whose pass lease this
process holds and marks, as the producer's dispatcher does.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from seldon.core import dispatch as D
from seldon.core import stations as S


def _held_by(bodies: dict):
    """A `lease_held` for `environment_premise`: the body for each repository path named, else None."""
    return lambda repo: bodies.get(Path(repo).name)


def _consumer(tmp_path: Path, names=("prod",)) -> tuple[Path, dict]:
    p = tmp_path / "cons"
    p.mkdir()
    (p / "kit.yaml").write_text(yaml.safe_dump({"environment_packages": list(names)}), encoding="utf-8")
    for n in names:
        (tmp_path / n).mkdir(exist_ok=True)
    return p, {"environment_ref": "kit.yaml#environment_packages"}


def _body(phase=None, **kw):
    b = {"holder": "dispatcher:host:1", "pid": 1, "acquired_at": "2026-11-13T14:12:21Z", "task": "76d0cde1", **kw}
    if phase is not None:
        b["phase"], b["phase_since"] = phase, "2026-11-13T17:38:06Z"
    return b


# ------------------------------------------------------------------------------------------------- the rule

@pytest.mark.parametrize("phase", [D.PHASE_SESSION, D.PHASE_GATE])
def test_a_producer_in_its_session_or_its_gate_holds_nobody(tmp_path, phase):
    p, scfg = _consumer(tmp_path)
    env = S.environment_premise(p, {}, scfg, _held_by({"prod": _body(phase)}))
    assert env["outcome"] == "true" and env["held"] == {}
    seen = env["not_holding"]["prod"]
    assert seen["phase"] == phase and seen["task"] == "76d0cde1" and seen["phase_since"] == "2026-11-13T17:38:06Z"
    assert "changes nothing this project reads" in seen["why"]


@pytest.mark.parametrize("phase", [D.PHASE_PASS, D.PHASE_MERGE])
def test_a_producer_writing_its_primary_holds_and_the_refusal_says_who_what_and_since_when(tmp_path, phase):
    p, scfg = _consumer(tmp_path)
    env = S.environment_premise(p, {}, scfg, _held_by({"prod": _body(phase)}))
    assert env["outcome"] == "false"
    held = env["held"]["prod"]
    assert held["holder"] == "dispatcher:host:1" and held["task"] == "76d0cde1"
    assert held["phase"] == phase and held["phase_since"] == "2026-11-13T17:38:06Z"
    assert held["acquired_at"] == "2026-11-13T14:12:21Z" and held["why"]


def test_a_lease_that_names_no_phase_holds_as_before(tmp_path):
    """A holder running code from before AD-037-R17 writes no phase. Unknown is treated as writing (fail-safe), so the
    narrower rule never lets a consumer through on a lease it cannot read."""
    p, scfg = _consumer(tmp_path)
    env = S.environment_premise(p, {}, scfg, _held_by({"prod": _body(None)}))
    assert env["outcome"] == "false" and env["held"]["prod"]["phase"] is None


def test_a_session_that_writes_a_repository_this_project_reads_or_this_project_itself_holds(tmp_path):
    """DISP-004R: a task whose Repo line names other repositories commits on their main by path, during its session.
    Part A found three refusals of that kind, each a seldon task writing into the very consumer it held."""
    p, scfg = _consumer(tmp_path, names=("prod", "other"))
    writes_other = _body(D.PHASE_SESSION, writes=[str((tmp_path / "other").resolve())])
    env = S.environment_premise(p, {}, scfg, _held_by({"prod": writes_other}))
    assert env["outcome"] == "false" and "other" in env["held"]["prod"]["why"]
    writes_me = _body(D.PHASE_GATE, writes=[str(p.resolve())])
    env = S.environment_premise(p, {}, scfg, _held_by({"prod": writes_me}))
    assert env["outcome"] == "false"
    writes_elsewhere = _body(D.PHASE_SESSION, writes=[str((tmp_path / "unread").resolve())])
    env = S.environment_premise(p, {}, scfg, _held_by({"prod": writes_elsewhere}))
    assert env["outcome"] == "true"


def test_the_review_pins_each_producer_at_the_revision_this_launch_reads(tmp_path):
    """AD-037-R18: the consumer reads the producer's primary working tree live, so it records what that tree was."""
    p, scfg = _consumer(tmp_path)
    prod = tmp_path / "prod"
    subprocess.run(["git", "init", "-q", str(prod)], check=True)
    (prod / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(prod), "add", "f.txt"], check=True)
    subprocess.run(["git", "-C", str(prod), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c"],
                   check=True)
    head = subprocess.run(["git", "-C", str(prod), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    env = S.environment_premise(p, {}, scfg, _held_by({}))
    assert env["pins"]["prod"]["head"] == head and env["pins"]["prod"]["dirty"] is False
    (prod / "f.txt").write_text("y\n", encoding="utf-8")
    assert S.environment_premise(p, {}, scfg, _held_by({}))["pins"]["prod"]["dirty"] is True


# --------------------------------------------------------------------------------------- the holder's phases

def test_mark_phase_rewrites_only_a_lease_this_process_holds(tmp_path):
    path = tmp_path / "dispatch.lock"
    lease = D.Lease(path).__enter__()
    try:
        assert D.read_lease(path)["phase"] == D.PHASE_PASS
        prev = D.mark_phase(path, D.PHASE_GATE, gate={"log": "logs/x.gate.log", "started_at": "t"})
        assert prev == D.PHASE_PASS
        body = D.read_lease(path)
        assert body["phase"] == D.PHASE_GATE and body["gate"]["log"] == "logs/x.gate.log" and body["phase_since"]
        D.mark_phase(path, D.PHASE_MERGE)
        assert D.read_lease(path)["gate"] is None, "a phase change without a gate clears the last one"
    finally:
        lease.__exit__(None, None, None)
    released = D.read_lease(path)
    assert D.mark_phase(path, D.PHASE_GATE) is None, "a released lease is not rewritten"
    assert D.read_lease(path) == released
    with pytest.raises(ValueError):
        D.mark_phase(path, "napping")


def test_gate_progress_reads_the_running_gates_log(tmp_path):
    log = tmp_path / "t.gate.log"
    log.write_text("old run\nEXIT=0\n", encoding="utf-8")
    offset = log.stat().st_size
    with log.open("a", encoding="utf-8") as fh:
        fh.write("=== 2026-11-24T10:00:00Z | gate record | python -m squiddy.kitpass record-pass\n")
        fh.write("seed 1: 1200/2847 tests, 0 failed, eta 00:31:00\n")
    prog = S.gate_progress({"log": str(log), "offset": offset, "started_at": "2026-11-24T10:00:00Z",
                            "call_site": "gate_record"}, now="2026-11-24T10:20:00Z")
    assert prog["elapsed_wall_s"] == 1200.0 and prog["lines"] == 2
    assert prog["last_line"].startswith("seed 1: 1200/2847") and prog["last_output_age_s"] is not None
    assert prog["finished"] is False
    with log.open("a", encoding="utf-8") as fh:
        fh.write("\nEXIT=0\n")
    assert S.gate_progress({"log": str(log), "offset": offset, "started_at": "2026-11-24T10:00:00Z"},
                           now="2026-11-24T10:20:00Z")["finished"] is True
    assert S.gate_progress({"log": str(tmp_path / "none.log"), "offset": 0, "started_at": "x"})["lines"] == 0


# --------------------------------------------------------------- the two-repository fixture, through real passes

neo4j = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


def _events(p, kind=None):
    rows = [json.loads(x) for x in (p / "seldon_events.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if kind is None or r["event_type"] == kind]


def _two_repos(tmp_path):
    from tests.dispatch_scaffold import git, make_project
    p = make_project(tmp_path, dispatch_extra={"stations": {"environment_ref": "kit.yaml#environment_packages"}})
    (p / "kit.yaml").write_text(yaml.safe_dump({"environment_packages": ["sib"]}), encoding="utf-8")
    git(p, "add", "kit.yaml")
    git(p, "commit", "-q", "-m", "kit")
    git(p, "push", "-q")
    sib = tmp_path / "sib"
    sib.mkdir()
    sib_cfg = {k: v for k, v in yaml.safe_load((p / "seldon.yaml").read_text(encoding="utf-8"))["dispatch"].items()
               if k != "stations"}
    (sib / "seldon.yaml").write_text(yaml.safe_dump({"dispatch": sib_cfg}), encoding="utf-8")
    return p, sib, sib / sib_cfg["lease_file"], sib / sib_cfg["log_dir"]


@neo4j
def test_a_consumer_launches_while_its_producer_gates_and_waits_only_across_the_producers_merge(tmp_path,
                                                                                                neo4j_driver):
    from seldon.commands.dispatch import dispatch_group
    from seldon.domain.loader import load_domain_config
    from tests.dispatch_scaffold import RESEARCH_YAML, add_task, register, run_cli, write_stub
    dc = load_domain_config(RESEARCH_YAML)
    p, sib, lease_path, sib_logs = _two_repos(tmp_path)
    add_task(p, "t1")
    add_task(p, "t2")
    write_stub(p, {"t1": {"complete": True}, "t2": {"complete": True}})
    register(p, neo4j_driver, dc, "t1", "2026-10-14T00:00:01Z")
    register(p, neo4j_driver, dc, "t2", "2026-10-14T00:00:02Z")
    sib_logs.mkdir(parents=True, exist_ok=True)
    gate_log = sib_logs / "sq-133r.gate.log"
    gate_log.write_text("=== 2026-11-13T17:38:06Z | gate record | record-pass\nseed 2: 900/2847 tests\n",
                        encoding="utf-8")
    lease = D.Lease(lease_path).__enter__()
    try:
        lease.heartbeat(task="sibling-task")
        D.mark_phase(lease_path, D.PHASE_MERGE)
        res = run_cli(p, dispatch_group, ["once"])
        assert _events(p, "dispatch_launched") == [], res.output
        (ref,) = [e for e in _events(p, "dispatch_refused") if e["payload"]["reason"] == "environment_in_flight"]
        held = ref["payload"]["held"]["sib"]
        assert held["task"] == "sibling-task" and held["phase"] == D.PHASE_MERGE and held["phase_since"]
        assert "phase merge" in res.output and "task sibling-" in res.output

        # The producer's gate: what it does touches nothing the consumer reads, so the consumer launches.
        D.mark_phase(lease_path, D.PHASE_GATE, task="sibling-task",
                     gate={"call_site": "gate_record", "log": str(gate_log), "offset": 0,
                           "started_at": "2026-11-13T17:38:06Z"})
        st = json.loads(run_cli(p, dispatch_group, ["status", "--json"]).output)
        seen = st["environment"]["not_holding"]["sib"]
        assert seen["phase"] == D.PHASE_GATE and seen["task"] == "sibling-task"
        assert seen["gate"]["last_line"] == "seed 2: 900/2847 tests" and seen["gate"]["elapsed_wall_s"] > 0
        text = run_cli(p, dispatch_group, ["status"]).output
        assert "sib" in text and "gate" in text and "seed 2: 900/2847 tests" in text
        res = run_cli(p, dispatch_group, ["once"])
        (launch,) = _events(p, "dispatch_launched")
        env = launch["payload"]["premises"]["environment"]
        assert env["outcome"] == "true" and env["not_holding"]["sib"]["phase"] == D.PHASE_GATE

        # Merge again, a new window: one more refusal, recorded once however many passes see it.
        D.mark_phase(lease_path, D.PHASE_MERGE)
        run_cli(p, dispatch_group, ["once"])
        run_cli(p, dispatch_group, ["once"])
    finally:
        lease.__exit__(None, None, None)
    refusals = [e for e in _events(p, "dispatch_refused") if e["payload"]["reason"] == "environment_in_flight"]
    assert len(refusals) == 2 and len(_events(p, "dispatch_launched")) == 1


@neo4j
def test_the_serial_holder_records_session_gate_and_merge_on_its_lease(tmp_path, neo4j_driver):
    """The producer's side: a serial pass marks `session` while the CLI runs, `gate` while the merge round's gate runs
    (with the gate's log, which is written while it runs), and `merge` when it writes the primary."""
    from seldon.commands.dispatch import dispatch_group
    from seldon.domain.loader import load_domain_config
    from tests.dispatch_scaffold import RESEARCH_YAML, add_task, make_project, register, run_cli, write_stub
    dc = load_domain_config(RESEARCH_YAML)
    snap = tmp_path / "snap"
    snap.mkdir()
    gate = (f"{sys.executable} -c \"import os, shutil; "
            f"shutil.copy(os.environ['SELDON_PRIMARY_CHECKOUT'] + '/.seldon/dispatch.lock', '{snap}/gate.json'); "
            f"print('gate says hello', flush=True)\"")
    p = make_project(tmp_path, dispatch_extra={"gate_command": gate})
    add_task(p, "t1")
    write_stub(p, {"t1": {"complete": True, "snapshot_lease": str(snap / "session.json")}})
    register(p, neo4j_driver, dc, "t1", "2026-10-14T00:00:01Z")
    res = run_cli(p, dispatch_group, ["once"])
    assert len(_events(p, "dispatch_finished")) == 1, res.output
    at_session = json.loads((snap / "session.json").read_text(encoding="utf-8"))
    assert at_session["phase"] == D.PHASE_SESSION and at_session["writes"] == []
    at_gate = json.loads((snap / "gate.json").read_text(encoding="utf-8"))
    assert at_gate["phase"] == D.PHASE_GATE and at_gate["gate"]["call_site"] == "merge_gate"
    assert Path(at_gate["gate"]["log"]).name == "t1.gate.log" and at_gate["gate"]["started_at"]
    finished = _events(p, "dispatch_finished")[0]["payload"]
    assert finished["outcome"] == "merged", finished
    assert D.read_lease(p / ".seldon" / "dispatch.lock")["holder"] is None
