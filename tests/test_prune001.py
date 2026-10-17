"""PRUNE-001 Part B: the weekly prune's rules, its record and its notification.

The rule tests are pure. The three Part B acceptance tests run `run_prune` against the Neo4j test
database and a scratch git repository: a planted FIXED issue is resolved, a planted stale FUTURE
proposal is withdrawn and one with an edge from an open task is re-dated, and a run with nothing
to do writes one `prune_pass` record and no notification.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from seldon.commands.prune import run_prune
from seldon.core import prune as P
from seldon.core.artifacts import create_artifact, create_link
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.testdb import TEST_DATABASE

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
REPO_ROOT = Path(__file__).parent.parent

#: The rules exactly as seldon.yaml declares them, so the tests exercise the shipped config.
CFG = P.load_prune_config(yaml.safe_load((REPO_ROOT / "seldon.yaml").read_text(encoding="utf-8")))
NOW = datetime(2026, 10, 18, 3, 30, tzinfo=timezone.utc)


# ── rule 1, pure ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("S-008 defect 1, FIXED with its test (tests/test_repodocs.py)", "FIXED"),
    ("K-001 defect 11, FIXED in graphs/library/graph.yaml.", "FIXED"),
    ("K-001 finding 2, NOT FIXED: a graph's schema imports core.yaml", None),
    ("K-001 finding 5, MEASURED not fixed: squiddy/schema/base.yaml was", None),
    # squiddy dc636a65: the first marker is negated; a later one in the lead does not override it.
    ("HV-002 finding 2, NOT FIXED and specifying the blocker for Part D's release: the kit has no path "
     "to attach a RESOLVED CANDIDATE", None),
    # A marker past the lead describes a sub-finding, not the Issue (squiddy 8e888b61).
    ("Near-miss, operator-caught. " + "x " * 80 + "R-23's PROVENANCE DEFECT, CLOSED.", None),
    ("AD-037-R6 stations run for serial sessions only.", None),
])
def test_fixed_marker_reads_the_status_lead(text, expected):
    assert P.fixed_marker(text, CFG) == expected


def test_a_commit_counts_only_in_a_fix_phrase():
    assert P.fixed_commit_named("Fixed in abc1234def with its test.", CFG) == "abc1234def"
    assert P.fixed_commit_named("resolved by commit `0123abcd`", CFG) == "0123abcd"
    assert P.fixed_commit_named("Found at abc1234def; predates that task.", CFG) is None
    assert P.fixed_commit_named("not fixed in abc1234def", CFG) is None


class _PlantedGit:
    def __init__(self, on_main=(), head="feedfacecafe"):
        self.on_main, self.head = set(on_main), head

    def on_branch(self, sha, branch):
        return sha in self.on_main

    def head_at(self, branch, when):
        return self.head


def test_issue_decision_prefers_the_named_commit_and_needs_it_on_main():
    issue = {"artifact_id": "i1", "state": "open", "created_at": "2026-10-01T00:00:00Z",
             "description": "Pin drift. Fixed in abc1234def by the repin."}
    d = P.issue_decision(issue, CFG, _PlantedGit(on_main={"abc1234def"}))
    assert d["rule"] == "fixed_commit" and d["commit"] == "abc1234def"
    assert P.issue_decision(issue, CFG, _PlantedGit()) is None      # named fix not on main: open, whatever the lead says
    assert P.issue_decision({**issue, "state": "blocked"}, CFG, _PlantedGit(on_main={"abc1234def"})) is None


def test_proposal_decision_clock_runs_from_redated_at():
    base = {"artifact_id": "t1", "state": "proposed", "description": "FUTURE (trigger: x): y",
            "created_at": "2026-04-01T00:00:00Z", "redated_at": None, "open_neighbours": []}
    assert P.proposal_decision(base, CFG, NOW)["action"] == "withdraw"
    assert P.proposal_decision({**base, "redated_at": "2026-10-17T00:00:00Z"}, CFG, NOW) is None
    assert P.proposal_decision({**base, "open_neighbours": ["abcdef12-x"]}, CFG, NOW)["action"] == "redate"
    assert P.proposal_decision({**base, "description": "Not a future idea"}, CFG, NOW) is None
    young = {**base, "created_at": (NOW - timedelta(days=CFG["stale_days"] - 1)).isoformat()}
    assert P.proposal_decision(young, CFG, NOW) is None


def test_spend_guard_stops_past_twenty_percent_over():
    g = P.SpendGuard(100, 1.2)
    g.charge(120)                                                   # at +20 percent: runs
    with pytest.raises(P.PruneCeiling):
        g.charge(1)
    zero = P.SpendGuard(0, 1.2)                                     # the shipped cap
    zero.check()
    with pytest.raises(P.PruneCeiling):
        zero.charge(1)


def test_config_refuses_a_missing_key():
    block = yaml.safe_load((REPO_ROOT / "seldon.yaml").read_text(encoding="utf-8"))["prune"]
    del block["stale_days"]
    with pytest.raises(P.PruneConfigError, match="stale_days"):
        P.load_prune_config({"prune": block})


# ── Part B acceptance, against the test database ────────────────────────────────────────────────

def _git(repo: Path, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "core.hooksPath=/dev/null", "-c", "user.name=t",
                    "-c", "user.email=t@t", *args], check=True, capture_output=True)


@pytest.fixture
def owner(tmp_path, neo4j_driver, clean_test_db):
    """A scratch lane owner: git repo on main, the shipped prune rules over itself, a notifier
    that appends to a file, and the Neo4j test database."""
    repo = tmp_path / "owner"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "README").write_text("x\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-q", "-m", "init")
    prune = yaml.safe_load((REPO_ROOT / "seldon.yaml").read_text(encoding="utf-8"))["prune"]
    prune["repositories"] = ["."]
    notified = tmp_path / "notified.txt"
    (repo / "seldon.yaml").write_text(yaml.safe_dump({
        "project": {"name": "t", "domain": "research"},
        "neo4j": {"database": TEST_DATABASE, "uri": "bolt://localhost:7687"},
        "event_store": {"path": "seldon_events.jsonl"},
        "dispatch": {"enabled": False, "branch": "main", "standing_band_ref": "x",
                     "poll_interval_s": 300, "permission_mode": "bypassPermissions",
                     "stop_file": ".seldon/DISPATCH_STOP", "log_dir": "logs/dispatch",
                     "lease_file": ".seldon/dispatch.lock",
                     "notify": f'echo "$SELDON_NOTIFY_MESSAGE" >> {notified}'},
        "prune": prune,
    }))
    return {"repo": repo, "driver": neo4j_driver, "notified": notified,
            "domain": load_domain_config(RESEARCH_YAML)}


def _create(o, artifact_type, props):
    return create_artifact(project_dir=o["repo"], driver=o["driver"], database=TEST_DATABASE,
                           domain_config=o["domain"], artifact_type=artifact_type, properties=props,
                           actor="cc", authority="accepted")


def _issue(o, description):
    return _create(o, "Issue", {"description": description, "issue_type": "factual_error",
                                "importance": "low", "urgency": "low",
                                "detection_method": "incidental", "target": "content"})


def _backdate(o, artifact_id, days):
    with o["driver"].session(database=TEST_DATABASE) as s:
        s.run("MATCH (a:Artifact {artifact_id: $id}) SET a.created_at = $c", id=artifact_id,
              c=(NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z"))


def _node(o, artifact_id):
    with o["driver"].session(database=TEST_DATABASE) as s:
        return dict(s.run("MATCH (a:Artifact {artifact_id: $id}) RETURN a", id=artifact_id).single()["a"])


def _passes(o):
    return [e for e in read_events(o["repo"]) if e["event_type"] == P.EVENT_PRUNE_PASS]


def test_the_fixed_marker_rule_closes_a_planted_issue(owner):
    fixed = _issue(owner, "S-099 defect 1, FIXED with its test (tests/test_x.py).")
    still_open = _issue(owner, "S-099 finding 2, NOT FIXED: no path yet.")
    payload = run_prune(owner["repo"], now=NOW, echo=lambda s: None)
    assert _node(owner, fixed)["state"] == "resolved"
    assert "fixed_marker" in _node(owner, fixed)["resolution_notes"]
    assert _node(owner, still_open)["state"] == "open"
    r = payload["repositories"][0]
    assert [d["artifact_id"] for d in r["resolved"]] == [fixed]
    assert r["before"]["open_issues"] == 2 and r["after"]["open_issues"] == 1
    assert owner["notified"].read_text().count("1 resolved") == 1


def test_the_sixty_day_rule_withdraws_one_and_redates_one_with_an_edge(owner):
    lonely = _create(owner, "ResearchTask", {"description": "FUTURE (not scheduled; trigger: x): lonely"})
    linked = _create(owner, "ResearchTask", {"description": "FUTURE (not scheduled; trigger: y): linked"})
    young = _create(owner, "ResearchTask", {"description": "FUTURE (not scheduled; trigger: z): young"})
    work = _create(owner, "ResearchTask", {"description": "open work that needs the linked idea"})
    create_link(project_dir=owner["repo"], driver=owner["driver"], database=TEST_DATABASE,
                domain_config=owner["domain"], from_id=linked, to_id=work, from_type="ResearchTask",
                to_type="ResearchTask", rel_type="precedes", actor="cc", authority="accepted")
    for t in (lonely, linked, work):
        _backdate(owner, t, CFG["stale_days"] + 5)
    _backdate(owner, young, CFG["stale_days"] - 5)

    run_prune(owner["repo"], now=NOW, echo=lambda s: None)

    assert _node(owner, lonely)["state"] == "withdrawn"
    assert _node(owner, lonely)["terminal_reason"] == "stale 60 days, no trigger seen"
    assert _node(owner, linked)["state"] == "proposed"
    assert _node(owner, linked)["redated_at"].startswith("2026-10-18")
    assert work[:8] in _node(owner, linked)["redate_reason"]
    assert _node(owner, young)["state"] == "proposed" and "redated_at" not in _node(owner, young)
    # A re-dated proposal is not stale on the next run.
    second = run_prune(owner["repo"], now=NOW + timedelta(days=1), echo=lambda s: None)
    assert second["actions"] == 0


def test_a_run_with_nothing_to_do_writes_one_record_and_no_notification(owner):
    _issue(owner, "An open defect with no fix claim.")
    payload = run_prune(owner["repo"], now=NOW, echo=lambda s: None)
    assert payload["actions"] == 0
    passes = _passes(owner)
    assert len(passes) == 1
    assert passes[0]["payload"]["repositories"][0]["before"]["open_issues"] == 1
    assert not owner["notified"].exists()


def test_a_dry_run_writes_nothing(owner):
    fixed = _issue(owner, "S-099 defect 3, FIXED.")
    payload = run_prune(owner["repo"], dry_run=True, now=NOW, echo=lambda s: None)
    assert payload["actions"] == 1
    assert _node(owner, fixed)["state"] == "open"
    assert _passes(owner) == [] and not owner["notified"].exists()
