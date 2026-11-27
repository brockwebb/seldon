"""SEL-058 Part A: the two hazbrief filings, each part that still held at HEAD, red first.

Filing `2026-11-24_filing_from_hazbrief_a_parts_check_line_is_not_read_...`:
  1. a Part's bare `check:` line (HB-221's form, directly under `## Part A:`) was not read, so the Stop gate recorded
     `checks: []` and the merge round ran the full gate as its evidence (AD-037-R22);
  2. `seldon cc complete` completed a task the merge round had blocked, with no gate evidence for the tree that reached
     main (AD-034-R41);
  3. a consumer's wait on a producer's lease rang nobody (AD-037-R23).
Filing `2026-11-27_filing_from_hazbrief_mcp_from_a_worktree_the_decision_register_reads_i...`:
  1. from a worktree the register resolved its sibling registers against the worktree, read zero records and said
     nothing (AD-034-R8, applied as SEL-018 applied it);
  2. records an imported repository adds were never projected by anything automatic (AD-033-R15);
  3. a `constrained_by` edge to a Decision no longer accepted failed verify with no fix (AD-033-R16).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.core import decisions as dr
from seldon.core import dispatch as D
from seldon.core import gate_plan as GP
from seldon.core import stations as Q
from seldon.core.events import append_event, make_event, read_events
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE

# HB-221's shape, as filed (hazbrief-mcp/cc_tasks/2026-11-23_HB-221_forecast_rain_no_longer_refuses_the_cloud.md).
HB221 = """# HB-221: forecast rain no longer refuses the cloud

**Parts:** A 0.6, B 0.4.

## Part A: the cloud is drawn, and the person is told

check: uv run pytest tests/test_hb221_rain_does_not_refuse.py -q -p no:cacheprovider

1. `src/hazbrief/brief/scichem.py` `check_dry`: forecast precipitation is no longer a refusal.

```
check: this fenced line is an example, not a check
```

## Part B: the requirement, the backlog

`check: uv run pytest tests/test_hb221_b.py -q`
judgment: the TEVV page reads as the operator wants

Acceptance:
- `check: uv run pytest tests/test_hb221_b.py -q` passes.
- check: grep -q rain docs/tevv.md
"""


# ------------------------------------------------------------------------------- filing 1, item 1: the check form

def test_a_parts_bare_check_line_is_read_as_its_check():
    a = Q.part_criteria(HB221, "A")
    assert a["section_found"] is True
    assert a["checks"] == ["uv run pytest tests/test_hb221_rain_does_not_refuse.py -q -p no:cacheprovider"]


def test_bare_and_acceptance_checks_are_read_once_each_and_a_bare_judgment_too():
    b = Q.part_criteria(HB221, "B")
    assert b["checks"] == ["uv run pytest tests/test_hb221_b.py -q", "grep -q rain docs/tevv.md"]
    assert b["judgments"] == ["the TEVV page reads as the operator wants"]


def test_the_regate_runs_a_bare_check_line_too():
    from seldon.commands.dispatch_worktree import task_checks
    assert task_checks(HB221)[0] == ("A", "uv run pytest tests/test_hb221_rain_does_not_refuse.py -q "
                                          "-p no:cacheprovider")


# ---------------------------------------------------------------------- filing 1, item 2: completion of a blocked task

def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _gate_run(tree: str, outcome: str = "pass", dirty: bool = False) -> dict:
    return make_event("gate_run", "cli", "accepted", {"tree": tree, "outcome": outcome, "dirty": dirty,
                                                      "tier": "full", "reason": "requested", "call_site": "cli",
                                                      "seconds": 1.0})


def test_completion_evidence_is_a_passing_clean_gate_of_the_branch_tip(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "f.txt").write_text("x\n")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-q", "-m", "one")
    tree = _git(root, "rev-parse", "main^{tree}")
    assert GP.completion_evidence(root, "main", []) is None
    assert GP.completion_evidence(root, "main", [_gate_run(tree, "fail")]) is None
    assert GP.completion_evidence(root, "main", [_gate_run(tree, dirty=True)]) is None
    assert GP.completion_evidence(root, "main", [_gate_run("0" * 40)]) is None
    ok = _gate_run(tree)
    assert GP.completion_evidence(root, "main", [ok])["event_id"] == ok["event_id"]


REL = "cc_tasks/2026-11-24_HB-221_probe.md"


@pytest.fixture
def repo(tmp_path: Path, neo4j_available, clean_test_db) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "seldon.yaml").write_text(yaml.safe_dump({
        "project": {"name": "test", "domain": "research"},
        "neo4j": {"database": NEO4J_DB, "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687")},
        "event_store": {"path": "seldon_events.jsonl"},
        "dispatch": {"enabled": False, "branch": "main", "standing_band_ref": "controls.yaml#spend.daily_tokens",
                     "lease_file": ".seldon/dispatch.lock", "log_dir": "logs/dispatch", "gate_command": "true",
                     "poll_interval_s": 300, "permission_mode": "bypassPermissions",
                     "stop_file": ".seldon/DISPATCH_STOP"}}))
    (root / "controls.yaml").write_text(yaml.safe_dump({"spend": {"daily_tokens": 1_000_000}}))
    (root / ".gitignore").write_text(".seldon/\nlogs/\n")
    (root / "cc_tasks").mkdir()
    (root / REL).write_text("# HB-221 probe\n\n**Implements:** AD-034\n\nA task the round blocked.\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "scaffold")
    return root


def _in(root: Path, group, args: list):
    prev = Path.cwd()
    os.chdir(root)
    try:
        return CliRunner().invoke(group, args, catch_exceptions=False)
    finally:
        os.chdir(prev)


def _block(root: Path, neo4j_driver) -> str:
    from seldon.commands.task import task_group
    from seldon.core.artifacts import create_artifact
    from seldon.domain.loader import load_domain_config
    domain = load_domain_config(Path(dr.__file__).parent.parent / "domain" / "research.yaml")
    tid = create_artifact(project_dir=root, driver=neo4j_driver, database=NEO4J_DB, domain_config=domain,
                          artifact_type="ResearchTask",
                          properties={"name": "HB-221 probe", "description": "a task the round blocked",
                                      "source_file": REL},
                          actor="cc", authority="accepted")
    res = _in(root, task_group, ["update", tid, "--state", "blocked", "--reason", "merge_blocked: regate_red"])
    assert res.exit_code == 0, res.output
    return tid


def _state(neo4j_driver, tid: str) -> dict:
    with neo4j_driver.session(database=NEO4J_DB) as s:
        return dict(s.run("MATCH (t:ResearchTask {artifact_id: $id}) RETURN t.state AS state, "
                          "t.completion_gate AS gate, t.completed_ungated AS ungated", id=tid).single())


def test_cc_complete_refuses_a_blocked_task_with_no_gate_on_main_then_completes_on_one(repo, neo4j_driver):
    from seldon.commands.cc import cc_group
    tid = _block(repo, neo4j_driver)
    refused = _in(repo, cc_group, ["complete", REL])
    assert refused.exit_code == 1, refused.output
    assert "blocked" in refused.output and "seldon gate main" in refused.output, refused.output
    assert _state(neo4j_driver, tid)["state"] == "blocked"

    ok = _gate_run(_git(repo, "rev-parse", "main^{tree}"))
    append_event(repo, ok)
    done = _in(repo, cc_group, ["complete", REL])
    assert done.exit_code == 0, done.output
    st = _state(neo4j_driver, tid)
    assert st["state"] == "completed" and st["gate"] == ok["event_id"]


def test_cc_complete_of_a_blocked_task_is_overridden_only_with_a_recorded_reason(repo, neo4j_driver):
    from seldon.commands.cc import cc_group
    tid = _block(repo, neo4j_driver)
    done = _in(repo, cc_group, ["complete", REL, "--ungated", "operator: merged by hand, main gated by HB-223"])
    assert done.exit_code == 0, done.output
    st = _state(neo4j_driver, tid)
    assert st["state"] == "completed" and st["ungated"].startswith("operator: merged by hand")


# ------------------------------------------------------------------------ filing 1, item 3: a lease wait rings once

def test_a_lease_wait_rings_once_at_its_threshold_and_clears(tmp_path, neo4j_available, clean_test_db):
    from seldon.commands import dispatch as S
    from tests.dispatch_scaffold import make_project
    p = make_project(tmp_path, dispatch_extra={
        "notify": f"echo \"$SELDON_NOTIFY_OUTCOME $SELDON_NOTIFY_CRITERION\" >> {tmp_path}/notify.log"})
    from seldon.config import load_project_config
    cfg = D.load_dispatch_config(p, load_project_config(p))
    need = D.stuck_threshold(cfg, "environment_in_flight")
    assert need > cfg["stuck_after_passes"], "a producer's merge window is longer than the default streak"
    held = {"seldon": {"holder": "seldon dispatch", "task": "09520bb0", "phase": "merge",
                       "phase_since": "2026-11-24T15:30:00Z", "acquired_at": "2026-11-24T15:00:00Z"}}
    prev = Path.cwd()
    os.chdir(p)
    try:
        rang = [S._environment_wait(p, None, cfg, held) for _ in range(need + 3)]
        assert rang == [False] * (need - 1) + [True] + [False] * 3
        stuck = [e for e in read_events(p) if e["event_type"] == D.EVENT_STUCK]
        assert len(stuck) == 1 and stuck[0]["payload"]["criterion"] == "environment_in_flight"
        assert "seldon" in json.dumps(stuck[0]["payload"]["held"])
        assert (tmp_path / "notify.log").read_text().splitlines() == ["stuck environment_in_flight"]
        S._environment_cleared(p, cfg)
        state = D.read_stuck_state(p, cfg)
        assert D.standing_key("environment_in_flight") not in state
        # A new holding window is a new wait, and rings again at its own threshold.
        held2 = {"seldon": {**held["seldon"], "phase_since": "2026-11-24T17:00:00Z"}}
        assert [S._environment_wait(p, None, cfg, held2) for _ in range(need)][-1] is True
    finally:
        os.chdir(prev)


# ---------------------------------------------------------- filing 2, item 1: a worktree reads the sibling registers

def _register_repo(base: Path, name: str, imports=()) -> Path:
    root = base / name
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    block = {"repository": name}
    if imports:
        block["import"] = list(imports)
    (root / "seldon.yaml").write_text(yaml.safe_dump({"project": {"name": name}, "decisions": block}))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_a_worktree_resolves_imported_registers_against_the_primary_checkout(tmp_path):
    _register_repo(tmp_path, "seldon")
    hb = _register_repo(tmp_path, "hazbrief", imports=["seldon"])
    wt = hb / ".claude" / "worktrees" / "probe"
    _git(hb, "worktree", "add", "-q", "-b", "worktree-probe", str(wt))
    cfg = yaml.safe_load((wt / "seldon.yaml").read_text())
    s = dr.settings(wt, cfg)
    assert s.repositories["seldon"] == (tmp_path / "seldon").resolve()
    assert s.repositories["hazbrief"] == wt.resolve()                     # its own register stays the worktree's
    cfg["decisions"]["repositories"] = {"squiddy": "../squiddy"}
    assert dr.settings(wt, cfg).repositories["squiddy"] == (tmp_path / "squiddy").resolve()


# ------------------------------------------------------ filing 2, item 2: an import's new records reach the graph

def test_the_imports_fingerprint_changes_when_an_import_adds_a_record_and_ignores_pending(tmp_path):
    sel = _register_repo(tmp_path, "seldon")
    hb = _register_repo(tmp_path, "hazbrief", imports=["seldon"])
    cfg = yaml.safe_load((hb / "seldon.yaml").read_text())
    before = dr.imports_fingerprint(hb, cfg)
    assert set(before) == {"seldon"}
    reg = sel / dr.DEFAULT_REGISTER_DIR
    (reg / dr.PENDING_DIR).mkdir(parents=True)
    (reg / dr.PENDING_DIR / "00001_x.yaml").write_text("id: seldon:X\n")
    assert dr.imports_fingerprint(hb, cfg) == before                       # a pending record is not projected
    (reg / "00001_seldon-x_accept.yaml").write_text("id: seldon:X\n")
    assert dr.imports_fingerprint(hb, cfg) != before
    assert dr.imports_fingerprint(sel, yaml.safe_load((sel / "seldon.yaml").read_text())) == {}


def test_the_pass_projects_once_per_change_of_an_import(tmp_path, monkeypatch):
    from seldon.commands import dispatch_worktree as W
    sel = _register_repo(tmp_path, "seldon")
    hb = _register_repo(tmp_path, "hazbrief", imports=["seldon"])
    config = yaml.safe_load((hb / "seldon.yaml").read_text())
    cfg = {"lease_file": ".seldon/dispatch.lock"}
    calls = []

    def fake(project_dir, config, driver, database, domain_config, session_id):
        calls.append(project_dir)
        return {"error": None, "created": 1, "updated": 0, "unchanged": 0, "transitions": 0}
    monkeypatch.setattr(W, "_project_register", fake)
    monkeypatch.setattr(W.S, "_emit", lambda *a, **k: None)
    first = W.project_imports(hb, config, cfg, driver=object(), database="db", domain_config=None, session_id=None)
    assert first is not None and first["changed"] == ["seldon"] and len(calls) == 1
    assert W.project_imports(hb, config, cfg, driver=object(), database="db", domain_config=None,
                             session_id=None) is None
    (sel / dr.DEFAULT_REGISTER_DIR).mkdir(parents=True)
    (sel / dr.DEFAULT_REGISTER_DIR / "00002_seldon-y_accept.yaml").write_text("id: seldon:Y\n")
    assert W.project_imports(hb, config, cfg, driver=object(), database="db", domain_config=None,
                             session_id=None)["changed"] == ["seldon"]
    assert len(calls) == 2


def test_a_failed_import_projection_is_retried_on_the_next_pass(tmp_path, monkeypatch):
    from seldon.commands import dispatch_worktree as W
    _register_repo(tmp_path, "seldon")
    hb = _register_repo(tmp_path, "hazbrief", imports=["seldon"])
    config = yaml.safe_load((hb / "seldon.yaml").read_text())
    cfg = {"lease_file": ".seldon/dispatch.lock"}
    outcomes = [{"error": "ServiceUnavailable: down", "created": 0, "updated": 0},
                {"error": None, "created": 0, "updated": 2, "unchanged": 0, "transitions": 0}]
    monkeypatch.setattr(W, "_project_register", lambda *a, **k: outcomes.pop(0))
    monkeypatch.setattr(W.S, "_emit", lambda *a, **k: None)
    assert W.project_imports(hb, config, cfg, driver=object(), database="db", domain_config=None,
                             session_id=None)["error"]
    assert W.project_imports(hb, config, cfg, driver=object(), database="db", domain_config=None,
                             session_id=None)["updated"] == 2
    assert W.project_imports(hb, config, cfg, driver=object(), database="db", domain_config=None,
                             session_id=None) is None


# ------------------------------------------- filing 2, the stale binding route: `verify --fix` ends the edge

def test_verify_fix_ends_a_binding_to_a_decision_no_longer_accepted(tmp_path, neo4j_driver, neo4j_available,
                                                                       clean_test_db):
    from seldon.core.artifacts import create_artifact, create_link
    from seldon.domain.loader import load_domain_config
    domain = load_domain_config(Path(dr.__file__).parent.parent / "domain" / "research.yaml")
    root = tmp_path / "p"
    root.mkdir()

    def node(t, props):
        req = domain.get_required_properties(t)
        return create_artifact(project_dir=root, driver=neo4j_driver, database=NEO4J_DB, domain_config=domain,
                               artifact_type=t, properties={**{k: "x" for k in req}, **props},
                               actor="human", authority="accepted")
    task = node("ResearchTask", {"name": "HB-214"})
    old = node("Decision", {"name": "hazbrief-mcp:HBD-474", "decision_id": "hazbrief-mcp:HBD-474"})
    live = node("Decision", {"name": "hazbrief-mcp:HBD-500", "decision_id": "hazbrief-mcp:HBD-500"})
    with neo4j_driver.session(database=NEO4J_DB) as s:
        s.run("MATCH (d:Decision {artifact_id: $a}) SET d.state = 'superseded'", a=old)
        s.run("MATCH (d:Decision {artifact_id: $a}) SET d.state = 'accepted'", a=live)
    for d in (old, live):
        create_link(project_dir=root, driver=neo4j_driver, database=NEO4J_DB, domain_config=domain, from_id=task,
                    to_id=d, from_type="ResearchTask", to_type="Decision", rel_type="constrained_by",
                    actor="human", authority="accepted")
    rows = dr.non_binding_decision_edges(neo4j_driver, NEO4J_DB)
    assert [(r["task"], r["decision"]) for r in rows] == [(task, old)]
    removed = dr.prune_non_binding_decision_edges(project_dir=root, driver=neo4j_driver, database=NEO4J_DB)
    assert [r["decision_id"] for r in removed] == ["hazbrief-mcp:HBD-474"]
    assert dr.non_binding_decision_edges(neo4j_driver, NEO4J_DB) == []
    with neo4j_driver.session(database=NEO4J_DB) as s:
        left = s.run("MATCH (:ResearchTask {artifact_id: $t})-[:CONSTRAINED_BY]->(d:Decision) "
                     "RETURN d.decision_id AS q", t=task).data()
    assert left == [{"q": "hazbrief-mcp:HBD-500"}]
    assert [e["event_type"] for e in read_events(root)].count("link_removed") == 1


def test_the_task_streak_pass_keeps_the_standing_streaks(tmp_path, neo4j_available, clean_test_db):
    """`_stuck` runs before station (a) on every pass and rewrote the streak file from task refusals alone, so a
    standing streak counted after it (this wait, SEL-054's `project_premise_false`) restarted at 1 on every pass."""
    from seldon.commands import dispatch as S
    from seldon.config import load_project_config
    from tests.dispatch_scaffold import make_project
    p = make_project(tmp_path)
    cfg = D.load_dispatch_config(p, load_project_config(p))
    key = D.standing_key("environment_in_flight")
    D.write_stuck_state(p, cfg, {key: {"criterion": "environment_in_flight", "passes": 5, "notified": False,
                                       "first_seen": "2026-11-24T15:30:00Z", "identity": "{}"}})
    S._stuck(p, None, cfg, [], {"dirty": False}, None, False)
    assert D.read_stuck_state(p, cfg)[key]["passes"] == 5
