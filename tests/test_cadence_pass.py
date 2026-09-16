"""The cadence inside a real pass: render, register, commit, and then flow through the queue.

`ai-readiness-kg/cc_tasks/2026-09-16_cadence_and_enable.md` §1's second test set, against
DN-006 decision 8 — "the pass renders the template, registers it, and lets it flow through
decisions 2 to 5 like any other task".

These need Neo4j because **registration is a graph write**, and the point of decision 8 is that
a cadence instance is registered by the same code path a hand-written task is (`seldon cc
register`'s own `register_task_file`). A mocked registration would test the mock and would not
notice the one thing that matters here: that the created task is a candidate, is eligible, and
is picked up by the very pass that created it.

**Zero spend, zero network.** The `claude` the config names is a shell script.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.dispatch import dispatch_group
from seldon.core import cadence as C
from seldon.core import dispatch as D
from seldon.core.events import read_events
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
pytestmark = pytest.mark.usefixtures("neo4j_available")

#: A template in the shape the real one has: the three headers, a design-note reference (the
#: dispatcher is a gated actor under AD-030-R11 and owes one), and the four placeholders.
TEMPLATE = textwrap.dedent("""\
    # CC Task — cycle {cycle_name}, created by cadence {cadence_name} for {period}

    **Date:** {created_at}
    **Implements:** DN-006 decision 8.
    **Framework layer served (DN-005 §5 rule 1):** §2.2 Tier M
    **Spend:** zero model calls.
    **Network:** hosts, under cadence {cadence_name}

    ## 1. Run the cycle as `{cycle_name}`.
    """)


def _git(p: Path, *a):
    return subprocess.run(["git", *a], cwd=p, check=True, capture_output=True, text=True)


def _yaml(p: Path, *, cadence=True, enabled=True) -> None:
    doc = {
        "event_store": {"path": "seldon_events.jsonl"},
        "neo4j": {"database": NEO4J_DB,
                  "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687")},
        "project": {"domain": "research", "name": "t", "slug": "t"},
        "dispatch": {"enabled": enabled, "branch": "main",
                     "standing_band_ref": "controls.yaml#spend.daily_tokens",
                     "poll_interval_s": 300, "permission_mode": "bypassPermissions",
                     "stop_file": ".seldon/DISPATCH_STOP", "log_dir": "logs/dispatch",
                     "lease_file": ".seldon/dispatch.lock",
                     "cli": str(p / "bin" / "claude")},
    }
    if cadence:
        doc["dispatch"]["cadence"] = [{
            "name": "scan_cycle",
            "rule": {"monthly_first_weekday": "monday", "at_utc": "00:00"},
            "template": "cc_tasks/templates/scan_cycle.md",
            "instances_dir": "cc_tasks",
            "cycle_name_format": "scan_{date}",
            "start_period": "2026-10",
            "last_instance": "",
        }]
    (p / "seldon.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    """A git project whose cadence is due today, with a stub `claude` that does nothing."""
    p = tmp_path / "proj"
    (p / "cc_tasks" / "templates").mkdir(parents=True)
    (p / "bin").mkdir()
    _git(p, "init", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    # The event store is TRACKED here, as it is in the real project: the cadence's commit has
    # to carry the `cadence_created` line, and a fixture that ignored it would not show that.
    (p / ".gitignore").write_text(".seldon/\nlogs/\nbin/\n", encoding="utf-8")
    (p / "controls.yaml").write_text(
        yaml.safe_dump({"spend": {"daily_tokens": 55_000_000}}), encoding="utf-8")
    (p / "seldon_events.jsonl").write_text("", encoding="utf-8")
    (p / "cc_tasks" / "templates" / "scan_cycle.md").write_text(TEMPLATE, encoding="utf-8")
    _yaml(p)
    stub = p / "bin" / "claude"
    stub.write_text('#!/bin/sh\necho "stub cc: $*"\nexit 0\n', encoding="utf-8")
    stub.chmod(0o755)
    _git(p, "add", "-A")
    _git(p, "commit", "-m", "init")
    return p


def _run(project, argv):
    prev = Path.cwd()
    os.chdir(project)
    try:
        return CliRunner().invoke(dispatch_group, argv, catch_exceptions=False)
    finally:
        os.chdir(prev)


def _events(project, kind):
    return [e for e in read_events(project) if e["event_type"] == kind]


#: A hand-checked instant: 2026-10-05 is the first Monday of October 2026, so a pass at
#: 00:30Z that day is due for period `2026-10`. Frozen rather than relative, so the same test
#: runs the same way in any week of any month — a schedule that can only be tested in the first
#: week of a month is untested for three weeks out of four.
DUE_AT = datetime(2026, 10, 5, 0, 30, tzinfo=timezone.utc)
NOT_DUE_AT = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
PERIOD = "2026-10"
INSTANCE = "cc_tasks/2026-10-05_scan_cycle_2026-10.md"


@pytest.fixture
def clock(monkeypatch):
    """Freeze the pass's clock. The default is the due instant; a test that wants the other
    side of the boundary sets it."""
    import seldon.commands.dispatch as dispatch_cmd

    def _set(when):
        monkeypatch.setattr(dispatch_cmd, "_utcnow", lambda: when)
        return when

    _set(DUE_AT)
    return _set


# ===================================================== a due period produces one task, once

def test_a_due_period_renders_registers_commits_and_the_task_is_then_eligible(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    """The whole of decision 8 in one pass. The instance is written, staged, registered through
    `seldon cc register`'s own code path, committed, and then — because it is a task file with
    the three headers on a clean tree — it is the task this same pass launches."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = _run(project, ["once"])
    assert res.exit_code == 0, res.output

    rel = INSTANCE
    inst = project / rel
    assert inst.is_file(), res.output
    body = inst.read_text(encoding="utf-8")
    assert f"cadence scan_cycle for {PERIOD}" in body
    assert "scan_2026-10-05" in body
    assert "{cycle_name}" not in body and "{period}" not in body

    created = _events(project, D.EVENT_CADENCE_CREATED)
    assert len(created) == 1
    pl = created[0]["payload"]
    assert pl["cadence"] == "scan_cycle" and pl["period"] == PERIOD
    assert pl["task_file"] == rel and pl["task_id"]
    assert pl["last_instance_written"] is True
    assert pl["unknown_placeholders"] == []

    # Registered, and registered as a task the dispatcher can read headers from.
    with neo4j_driver.session(database=NEO4J_DB) as s:
        row = s.run("MATCH (t:ResearchTask {source_file: $f}) RETURN t.artifact_id AS id, "
                    "t.state AS state, t.created_by AS by", f=rel).single()
    assert row is not None and row["id"] == pl["task_id"]
    assert row["by"] == "dispatcher"

    # Committed, by the pass, pathspec-limited — and `last_instance` recorded in place.
    assert D.is_tracked(project, inst)
    log = subprocess.run(["git", "log", "-1", "--pretty=%s"], cwd=project,
                         capture_output=True, text=True).stdout.strip()
    assert log.startswith("chore(cadence): scan_cycle ")
    assert yaml.safe_load((project / "seldon.yaml").read_text())[
        "dispatch"]["cadence"][0]["last_instance"] == rel

    # And it flowed through decision 2: launched by the same pass that created it.
    launched = _events(project, D.EVENT_LAUNCHED)
    assert len(launched) == 1 and launched[0]["payload"]["source_file"] == rel


def test_the_rendered_instance_is_a_candidate_and_passes_c5_by_its_cadence_declaration(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    """c5 admits `**Network:** none` **or** a task created by the cadence rule (DN-006 decision
    2's c5, second limb). The rendered header says `hosts, under cadence scan_cycle` — a cycle
    contacts federal hosts and may not claim otherwise — and that is what makes it eligible."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _run(project, ["once"])
    rel = INSTANCE

    cand = D.candidacy(project / rel)
    assert cand["candidate"] is True and cand["reason"] is None
    assert "under cadence scan_cycle" in cand["headers"][D.HEADER_NETWORK]
    assert D.network_declared_none(cand["headers"][D.HEADER_NETWORK]) is True
    assert D.spend_tokens(cand["headers"][D.HEADER_SPEND]) == 0

    criteria = _events(project, D.EVENT_LAUNCHED)[0]["payload"]["criteria"]
    assert criteria["c5"]["ok"] is True
    assert "under cadence" in criteria["c5"]["network_header"]


def test_a_second_pass_in_the_same_period_creates_nothing(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _run(project, ["once"])
    assert len(_events(project, D.EVENT_CADENCE_CREATED)) == 1
    before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True,
                            text=True).stdout
    _run(project, ["once"])
    assert len(_events(project, D.EVENT_CADENCE_CREATED)) == 1
    after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True,
                           text=True).stdout
    assert before == after


def test_a_hand_cleared_last_instance_still_creates_nothing(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    """The check is the FILE. Clearing the config line is exactly the accident that would
    create a second cycle for a month that already has one — two measurements of the same
    period under two names, which is the one thing a dated measurement may not be."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _run(project, ["once"])
    doc = yaml.safe_load((project / "seldon.yaml").read_text())
    doc["dispatch"]["cadence"][0]["last_instance"] = ""
    (project / "seldon.yaml").write_text(yaml.safe_dump(doc, sort_keys=False),
                                         encoding="utf-8")
    _git(project, "add", "seldon.yaml")
    _git(project, "commit", "-m", "cleared")

    _run(project, ["once"])
    assert len(_events(project, D.EVENT_CADENCE_CREATED)) == 1


def test_a_period_that_is_not_due_creates_nothing_and_writes_no_event(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    """A pass that finds nothing due writes NO event (DN-006 decision 7): a five-minute poll
    that logged its own silence would bury the assertions in it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    clock(NOT_DUE_AT)
    before = len(read_events(project))
    _run(project, ["once"])
    assert _events(project, D.EVENT_CADENCE_CREATED) == []
    assert len(read_events(project)) == before
    assert not list((project / "cc_tasks").glob("*_scan_cycle_*.md"))


# ================================================================== it refuses to write into

def test_a_dirty_tree_is_due_and_creates_nothing(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    """The dispatcher does not add a file and a commit to a checkout something else is editing.
    That is DD-019's batch-identity class in the one place this design can still reach it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (project / "controls.yaml").write_text(
        yaml.safe_dump({"spend": {"daily_tokens": 55_000_001}}), encoding="utf-8")
    res = _run(project, ["once"])
    assert res.exit_code == 0
    assert _events(project, D.EVENT_CADENCE_CREATED) == []
    assert not list((project / "cc_tasks").glob("*_scan_cycle_*.md"))
    assert "is due and NOT created (dirty_tree)" in res.output


def test_a_disabled_dispatcher_evaluates_no_cadence_at_all(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    """`enabled` is the kill switch for the whole pass, cadence included. A schedule that kept
    creating task files while the dispatcher was switched off would be a kill switch that
    stopped only half the machine."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _yaml(project, enabled=False)
    res = _run(project, ["once"])
    assert "dispatch is disabled" in res.output
    assert _events(project, D.EVENT_CADENCE_CREATED) == []
    assert not list((project / "cc_tasks").glob("*_scan_cycle_*.md"))


def test_a_stop_file_stops_the_cadence_too(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    stop = project / ".seldon" / "DISPATCH_STOP"
    stop.parent.mkdir(parents=True, exist_ok=True)
    stop.write_text("halt\n", encoding="utf-8")
    res = _run(project, ["once"])
    assert "dispatch is stop_file" in res.output
    assert _events(project, D.EVENT_CADENCE_CREATED) == []
    assert not list((project / "cc_tasks").glob("*_scan_cycle_*.md"))


def test_a_template_that_cites_no_design_note_is_refused_and_the_instance_is_removed(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    """AD-030-R11: the dispatcher is a gated actor, so a task it files owes a design-note
    reference. The registration refuses — and the rendered file must go with it, because a
    rendered file that is not in the graph is a task nothing will ever run AND a file the next
    pass would read as "this period is already served"."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (project / "cc_tasks" / "templates" / "scan_cycle.md").write_text(
        TEMPLATE.replace("**Implements:** DN-006 decision 8.\n", "")
                .replace("(DN-005 §5 rule 1)", ""), encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-m", "no design note")

    res = _run(project, ["once"])
    assert res.exit_code == 0
    assert "registration failed, instance removed" in res.output
    assert not list((project / "cc_tasks").glob("*_scan_cycle_*.md"))
    assert _events(project, D.EVENT_CADENCE_CREATED) == []
    assert D.tree_state(project)["dirty"] is False


def test_a_missing_template_creates_nothing_and_says_so(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (project / "cc_tasks" / "templates" / "scan_cycle.md").unlink()
    _git(project, "add", "-A")
    _git(project, "commit", "-m", "rm template")
    res = _run(project, ["once"])
    assert "does not exist; nothing created" in res.output
    assert _events(project, D.EVENT_CADENCE_CREATED) == []


# ============================================================================ status reports

def test_status_reports_the_cadence_and_writes_nothing(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    before = (project / "seldon_events.jsonl").read_bytes()
    res = _run(project, ["status"])
    assert res.exit_code == 0
    assert f"cadence      : scan_cycle {PERIOD} due 2026-10-05T00:00:00Z" in res.output
    assert "DUE, no instance" in res.output
    assert "next:" in res.output
    assert (project / "seldon_events.jsonl").read_bytes() == before


def test_a_period_before_the_start_boundary_creates_nothing(
        project, neo4j_driver, clean_test_db, monkeypatch, clock):
    """`start_period` is Airflow's `start_date`, and this is the condition it exists for: a
    monthly schedule switched on partway through a month that has already been served finds the
    CURRENT period due and no instance on disk. `catchup=False` does not cover it — the
    offending period is not an earlier one, it is this one. Installing this cadence on
    2026-09-16 without the boundary would create a second September cycle for a month cycle 4
    already measured."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    clock(datetime(2026, 9, 16, 3, 25, tzinfo=timezone.utc))
    res = _run(project, ["once"])
    assert res.exit_code == 0
    assert _events(project, D.EVENT_CADENCE_CREATED) == []
    assert not list((project / "cc_tasks").glob("*_scan_cycle_*.md"))

    # And `status` says so as a value, not as silence.
    out = _run(project, ["status"]).output
    assert "before start_period 2026-10" in out
