"""SEL-044: one brief and one handoff read every repository the portfolio project declares (AD-038-R32 to R35).

`cc_tasks/2026-11-21_SEL-044_one_brief_and_one_handoff_read_every_registered_repository_from_the_portfolio_project.md`
and its ADDENDUM 01. factory's filing `6087e4d1`: the operator starts at the factory, and its `go` and handoff read the
factory's graph only; the coordinator gathered every other repository by hand and, on 2026-11-13, missed work seldon
had finished four days earlier.

The fixture is three repositories and the portfolio project that lists them, each with its own `seldon.yaml`:

- `alpha`: a dispatcher whose pass lease is in `gate`, with a gate log; open tasks in three states, a blocked one with
  its stored reason (`ungated`), an open filing, a completed one; gate records with and without `wall_seconds`.
- `beta`: its own graph (a second database); a pass lease held by a holder that records no phase.
- `gamma`: a directory with no `seldon.yaml` (unreadable), and `delta`: a `seldon.yaml` naming a database that does
  not exist (read in part).

The task's three tests: counts equal each repository's own `seldon task list`; an unreadable repository is shown with
its reason; nothing is written outside the portfolio project. ADDENDUM 01's: the gate phase and the gate's last line,
`phase unknown`, and the wall-clock median with its n.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.core import portfolio as PF
from seldon.core.artifacts import create_artifact, transition_task
from seldon.core.events import append_event, make_event
from seldon.domain.loader import load_domain_config
from tests.testdb import TEST_DATABASE, create_database, drop_database, is_ephemeral

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
STORE = "seldon_events.jsonl"
BETA_DB = f"{TEST_DATABASE}-pfbeta"
URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

DISPATCH = {"enabled": True, "branch": "main", "standing_band_ref": "controls.yaml#spend.daily_tokens",
            "poll_interval_s": 300, "permission_mode": "bypassPermissions", "stop_file": ".seldon/DISPATCH_STOP",
            "log_dir": "logs/dispatch", "lease_file": ".seldon/dispatch.lock", "gate_command": "true"}


def _now_iso(delta_s: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_s)).isoformat().replace("+00:00", "Z")


def _seldon_yaml(path: Path, name: str, database: str, dispatch: bool = False, extra: dict | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / STORE).touch()
    body = {"project": {"name": name, "domain": "research", "slug": name},
            "neo4j": {"database": database, "uri": URI}, "event_store": {"path": STORE}}
    if dispatch:
        body["dispatch"] = dict(DISPATCH)
        (path / "controls.yaml").write_text(yaml.safe_dump({"spend": {"daily_tokens": 55_000_000}}), encoding="utf-8")
    body.update(extra or {})
    (path / "seldon.yaml").write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")


def _task(root: Path, driver, database: str, dc, description: str, path: tuple = (), **props) -> str:
    tid = create_artifact(project_dir=root, driver=driver, database=database, domain_config=dc,
                          artifact_type="ResearchTask", properties={"description": description, **props},
                          actor="human", authority="accepted")
    current = "proposed"
    for nxt in path:
        transition_task(project_dir=root, driver=driver, database=database, domain_config=dc, artifact_id=tid,
                        current_state=current, new_state=nxt, actor="human",
                        block_reason="ungated: no gate evidence (AD-034-R26)" if nxt == "blocked" else None)
        current = nxt
    return tid


def _lease(root: Path, body: dict) -> None:
    (root / ".seldon").mkdir(parents=True, exist_ok=True)
    (root / ".seldon" / "dispatch.lock").write_text(json.dumps(body), encoding="utf-8")


def _gate_event(root: Path, event_type: str, payload: dict) -> None:
    append_event(root, make_event(event_type=event_type, actor="dispatcher", authority="accepted", payload=payload))


@pytest.fixture
def beta_db(neo4j_driver):
    create_database(neo4j_driver, BETA_DB)
    with neo4j_driver.session(database=BETA_DB) as s:
        s.run("MATCH (n) DETACH DELETE n")
    yield BETA_DB
    if is_ephemeral(TEST_DATABASE):
        drop_database(neo4j_driver, BETA_DB)


@pytest.fixture
def world(tmp_path, neo4j_driver, clean_test_db, beta_db):
    """The portfolio project and its four listed repositories, built before any portfolio read."""
    dc = load_domain_config(RESEARCH_YAML)
    alpha, beta, gamma, delta = (tmp_path / n for n in ("alpha", "beta", "gamma", "delta"))
    _seldon_yaml(alpha, "alpha", TEST_DATABASE, dispatch=True)
    _seldon_yaml(beta, "beta", BETA_DB, dispatch=True)
    gamma.mkdir()
    _seldon_yaml(delta, "delta", f"{TEST_DATABASE}-pfnone")
    port = tmp_path / "port"
    # The portfolio project's own graph is not read by the brief; it names a database no test creates.
    _seldon_yaml(port, "port", f"{TEST_DATABASE}-pfport", extra={"portfolio": {
        "repositories": {"alpha": "../alpha", "beta": "../beta", "gamma": "../gamma", "delta": "../delta",
                         "nowhere": "../nowhere"},
        "gate_silent_after_s": 600}})

    ids = {
        "a_proposed": _task(alpha, neo4j_driver, TEST_DATABASE, dc, "alpha proposed"),
        "a_accepted": _task(alpha, neo4j_driver, TEST_DATABASE, dc, "alpha accepted", ("accepted",)),
        "a_blocked": _task(alpha, neo4j_driver, TEST_DATABASE, dc, "alpha blocked", ("blocked",)),
        "a_filing": _task(alpha, neo4j_driver, TEST_DATABASE, dc, "Filing from beta: something", task_kind="filing"),
        "a_done": _task(alpha, neo4j_driver, TEST_DATABASE, dc, "alpha finished",
                        ("accepted", "in_progress", "completed")),
        "b_running": _task(beta, neo4j_driver, BETA_DB, dc, "beta running", ("accepted", "in_progress")),
        "b_proposed": _task(beta, neo4j_driver, BETA_DB, dc, "beta proposed"),
    }

    # alpha's pass lease is in `gate`, its gate log has grown just now.
    log = alpha / "logs" / "dispatch" / "task.gate.log"
    log.parent.mkdir(parents=True)
    log.write_text("=== start | gate record | pytest\ncollected 12 items\ntests/test_x.py ....  [ 40%]\n",
                   encoding="utf-8")
    _lease(alpha, {"holder": f"dispatcher:test:{os.getpid()}", "pid": os.getpid(), "task": ids["a_accepted"],
                   "acquired_at": _now_iso(-120), "phase": "gate", "phase_since": _now_iso(-60),
                   "gate": {"call_site": "merge_gate", "log": str(log), "offset": 0, "started_at": _now_iso(-60)}})
    # beta's lease is held by a holder on code from before AD-037-R17: no phase.
    _lease(beta, {"holder": f"dispatcher:test:{os.getpid()}", "pid": os.getpid(), "task": ids["b_running"],
                  "acquired_at": _now_iso(-30)})
    # alpha's gate records: two with wall time (gate_run, gate_recorded), one from before SEL-043 without.
    _gate_event(alpha, "gate_run", {"tier": "full", "outcome": "pass", "seconds": 90.0, "wall_seconds": 100.0})
    _gate_event(alpha, "gate_recorded", {"task_id": ids["a_done"], "outcome": "pass",
                                         "gate": {"seconds": 250.0, "wall_seconds": 300.0}})
    _gate_event(alpha, "gate_run", {"tier": "full", "outcome": "pass", "seconds": 7734.0})
    return {"port": port, "alpha": alpha, "beta": beta, "gamma": gamma, "delta": delta, "ids": ids,
            "log": log, "tmp": tmp_path}


def _row(p: dict, name: str) -> dict:
    return next(r for r in p["repositories"] if r["name"] == name)


def _read(world) -> dict:
    from seldon.config import load_project_config
    return PF.read_portfolio(world["port"], load_project_config(world["port"]))


def _task_list_ids(root: Path, monkeypatch) -> list:
    """The ids `seldon task list` prints in `root`, run as the operator runs it there."""
    from seldon.commands.task import task_group
    monkeypatch.chdir(root)
    out = CliRunner().invoke(task_group, ["list"])
    assert out.exit_code == 0, out.output
    return re.findall(r"^\S*\s+([0-9a-f]{8}) ", out.output, flags=re.M)


def _snapshot(root: Path) -> dict:
    """Every file under `root`: size, mtime and content hash."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Configuration (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

def test_a_project_without_a_portfolio_block_is_refused_naming_the_key():
    with pytest.raises(PF.PortfolioConfigError, match="portfolio: {repositories"):
        PF.settings({"project": {"name": "x"}})


@pytest.mark.parametrize("block, match", [
    ({"repositories": {}}, "non-empty mapping"),
    ({"repositories": ["a"]}, "non-empty mapping"),
    ({"repositories": {"a": "../a"}, "gate_silent_s": 5}, "unknown key"),
    ({"repositories": {"a": "../a"}, "gate_silent_after_s": 0}, "positive number"),
    ({"repositories": {"a": "../a"}, "max_workers": 0}, "at least 1"),
])
def test_a_malformed_portfolio_block_is_refused(block, match):
    with pytest.raises(PF.PortfolioConfigError, match=match):
        PF.settings({"portfolio": block})


def test_the_cli_refuses_go_and_handoff_portfolio_in_a_project_that_declares_none(tmp_path, monkeypatch):
    from seldon.commands.go import go_command
    from seldon.commands.handoff import handoff_command
    _seldon_yaml(tmp_path / "p", "p", "unused")
    monkeypatch.chdir(tmp_path / "p")
    out = CliRunner().invoke(go_command, ["--portfolio", "--brief"])
    assert out.exit_code == 1 and "declares no portfolio" in out.output
    out = CliRunner().invoke(handoff_command, ["--portfolio", "--slug", "s", "--summary", "x", "--next", "y"])
    assert out.exit_code == 1 and "declares no portfolio" in out.output
    assert not (tmp_path / "p" / "handoffs").exists()


def test_relative_paths_resolve_against_the_project_and_keep_the_declared_order(tmp_path):
    scfg = PF.settings({"portfolio": {"repositories": {"z": "../z", "a": "../a"}}})
    (tmp_path / "port").mkdir()
    got = PF.repositories(tmp_path / "port", scfg)
    assert list(got) == ["z", "a"]
    assert got["z"] == (tmp_path / "z").resolve()


def test_one_reader_that_raises_is_a_row_and_never_stops_the_others(tmp_path):
    (tmp_path / "port").mkdir()
    config = {"project": {"name": "port"}, "portfolio": {"repositories": {"ok": "../ok", "boom": "../boom"}}}

    def reader(name, root, since, scfg):
        if name == "boom":
            raise RuntimeError("graph went away")
        return {"name": name, "path": str(root), "readable": True, "reason": None, "errors": {}, "tasks": None,
                "completed": None, "dispatch": None, "huddles": [], "gate": None}

    p = PF.read_portfolio(tmp_path / "port", config, reader=reader)
    assert [r["name"] for r in p["repositories"]] == ["ok", "boom"]
    boom = _row(p, "boom")
    assert boom["readable"] is False and "graph went away" in boom["reason"]
    assert "UNREADABLE" in PF.render_brief(p)


# ══════════════════════════════════════════════════════════════════════════════
# The fixture of three repositories (Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

@neo4j_tests
def test_counts_equal_each_repositorys_own_task_list(world, monkeypatch):
    p = _read(world)
    for name in ("alpha", "beta"):
        row = _row(p, name)
        listed = _task_list_ids(world[name], monkeypatch)
        assert row["tasks"]["open_count"] == len(listed), (name, row["tasks"], listed)
        assert sorted(t["id"][:8] for t in row["tasks"]["open"]) == sorted(listed)
    a = _row(p, "alpha")["tasks"]["by_state"]
    assert a == {"proposed": 2, "accepted": 1, "blocked": 1}
    assert _row(p, "beta")["tasks"]["by_state"] == {"proposed": 1, "in_progress": 1}
    brief = PF.render_brief(p)
    assert "| alpha | 4 (accepted 1, blocked 1, proposed 2) |" in brief
    assert "| beta | 2 (in_progress 1, proposed 1) |" in brief


@neo4j_tests
def test_an_unreadable_repository_is_shown_with_its_reason_and_never_dropped(world):
    p = _read(world)
    assert [r["name"] for r in p["repositories"]] == ["alpha", "beta", "gamma", "delta", "nowhere"]
    gamma, nowhere, delta = _row(p, "gamma"), _row(p, "nowhere"), _row(p, "delta")
    assert gamma["readable"] is False and gamma["reason"] == f"no seldon.yaml at {world['gamma'].resolve()}"
    assert nowhere["readable"] is False and nowhere["reason"].startswith("no directory at ")
    # delta's graph refuses (no such database) but its event store reads: a partial row, the failed reading named.
    assert delta["readable"] is True and "graph" in delta["errors"]
    assert any(a.startswith("reading graph failed") for a in delta["alarms"])
    brief = PF.render_brief(p)
    assert "| gamma | UNREADABLE |" in brief and "| nowhere | UNREADABLE |" in brief
    assert f"- UNREADABLE: no seldon.yaml at {world['gamma'].resolve()}" in brief
    assert "2 unreadable" in brief


@neo4j_tests
def test_nothing_is_written_outside_the_portfolio_project(world, monkeypatch):
    from seldon.commands.go import go_command
    from seldon.commands.handoff import handoff_command
    from seldon.mcp_server import seldon_go

    listed = [world[n] for n in ("alpha", "beta", "gamma", "delta")]
    before = {str(r): _snapshot(r) for r in listed}
    port_before = _snapshot(world["port"])
    monkeypatch.chdir(world["port"])
    out = CliRunner().invoke(go_command, ["--portfolio", "--brief"])
    assert out.exit_code == 0, out.output
    out = CliRunner().invoke(go_command, ["--portfolio", "--json"])
    assert out.exit_code == 0, out.output
    assert "Error" not in seldon_go(project_dir=str(world["port"]), brief=True, portfolio=True)[:20]
    out = CliRunner().invoke(handoff_command, ["--portfolio", "--slug", "portfolio", "--summary", "s",
                                               "--next", "n"])
    assert out.exit_code == 0, out.output
    after = {str(r): _snapshot(r) for r in listed}
    assert after == before
    # The only change anywhere is the one handoff in the portfolio project.
    added = set(_snapshot(world["port"])) - set(port_before)
    assert [a for a in added if not a.startswith("handoffs/")] == []
    assert len(added) == 1 and next(iter(added)).endswith("_portfolio.md")
    assert not (world["tmp"] / "nowhere").exists()


@neo4j_tests
def test_the_gate_phase_shows_its_gates_last_line_and_a_phaseless_lease_is_phase_unknown(world):
    p = _read(world)
    alpha, beta = _row(p, "alpha"), _row(p, "beta")
    assert PF.running(alpha) == [(world["ids"]["a_accepted"][:8], "gate")]
    assert PF.running(beta) == [(world["ids"]["b_running"][:8], PF.PHASE_UNKNOWN)]
    g = alpha["dispatch"]["lease"]["gate"]
    assert g["last_line"] == "tests/test_x.py ....  [ 40%]" and g["finished"] is False
    brief = PF.render_brief(p)
    assert f"{world['ids']['a_accepted'][:8]} gate" in brief
    assert f"{world['ids']['b_running'][:8]} phase unknown" in brief
    # alpha has something wrong (a blocked task), so its detail prints the gate's progress as `dispatch status` does.
    assert "last output" in brief and "tests/test_x.py ....  [ 40%]" in brief


@neo4j_tests
def test_a_gate_whose_log_stopped_growing_is_an_alarm(world):
    old = time.time() - 3600
    os.utime(world["log"], (old, old))
    p = _read(world)
    silent = [a for a in _row(p, "alpha")["alarms"] if a.startswith("gate output silent")]
    assert len(silent) == 1 and "portfolio.gate_silent_after_s 600" in silent[0]
    # Grown again: no alarm.
    os.utime(world["log"], None)
    p = _read(world)
    assert not [a for a in _row(p, "alpha")["alarms"] if a.startswith("gate output silent")]


@neo4j_tests
def test_the_gate_median_is_wall_time_only_with_its_n(world):
    p = _read(world)
    g = _row(p, "alpha")["gate"]
    # 100 and 300 carry wall time; the pre-SEL-043 record (7,734 monotonic s) is left out, not filled in.
    assert g == {"median_wall_s": 200.0, "n": 2, "without_wall": 1}
    assert "200 s wall (n=2)" in PF.render_brief(p)
    assert _row(p, "beta")["gate"]["n"] == 0
    assert "| beta |" in PF.render_brief(p) and PF.NO_WALL_GATES in PF.render_brief(p)


@neo4j_tests
def test_alarms_filings_and_completions(world):
    p = _read(world)
    alpha = _row(p, "alpha")
    blocked = [a for a in alpha["alarms"] if a.startswith("blocked:")]
    assert blocked == [f"blocked: {world['ids']['a_blocked'][:8]} ungated: no gate evidence (AD-034-R26)"]
    assert [t["id"] for t in PF._filings(alpha)] == [world["ids"]["a_filing"]]
    assert [c["id"] for c in alpha["completed"]] == [world["ids"]["a_done"]]
    assert _row(p, "beta")["alarms"] == []
    # A stop file is an alarm.
    (world["beta"] / ".seldon" / "DISPATCH_STOP").write_text("", encoding="utf-8")
    assert "stop file present" in " ".join(_row(_read(world), "beta")["alarms"])


@neo4j_tests
def test_the_portfolio_handoff_has_a_section_per_repository_one_resume_line_and_starts_the_next_window(
        world, monkeypatch):
    from seldon.commands.handoff import handoff_command
    monkeypatch.chdir(world["port"])
    out = CliRunner().invoke(handoff_command, ["--portfolio", "--slug", "portfolio_close", "--summary",
                                               "closed the week", "--next", "read alpha's blocked task"])
    assert out.exit_code == 0, out.output
    written = next((world["port"] / "handoffs").glob("*_portfolio_close.md"))
    text = written.read_text(encoding="utf-8")
    for name in ("alpha", "beta", "gamma", "delta", "nowhere"):
        assert f"\n## {name}\n" in text
    resume = text.split("## Resume\n\n", 1)[1].strip().splitlines()
    assert len(resume) == 1 and "seldon go --portfolio --brief" in resume[0] and str(written.resolve()) in resume[0]
    assert "First action: read alpha's blocked task" in resume[0]
    assert resume[0] in out.output
    marker = PF.last_portfolio_handoff(world["port"])
    assert marker is not None and marker[0] == written
    # The next brief counts completions from the handoff's time: alpha's finish was before it.
    p = _read(world)
    assert p["since_source"].startswith("the last portfolio handoff")
    assert _row(p, "alpha")["completed"] == []
    # A second handoff at the same path is refused, never silently replaced.
    out = CliRunner().invoke(handoff_command, ["--portfolio", "--slug", "portfolio_close", "--summary", "x",
                                               "--next", "y"])
    assert out.exit_code == 1 and "already exists" in out.output


@neo4j_tests
def test_go_portfolio_without_brief_puts_the_brief_before_the_projects_own_orientation(world):
    from seldon.commands.go import assemble_portfolio_context
    text = assemble_portfolio_context(project_dir=str(world["port"]), brief=False, in_claude_code=True)
    assert text.startswith("## Portfolio: port, 5 repositories")
    assert "Moving:" in text and text.index("## Portfolio") < text.index("Moving:")
