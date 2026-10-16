"""DESK-002 Part B: registration leaves none of its own event-store lines uncommitted (Issue 70bf1a21).

Registration appends to the TRACKED event store: `artifact_created` for the task (the registering
actor) and, for every ruling the task is constrained by, `link_created` with actor `governed_sync`
(`governed.write_constrained_by`). Before DESK-002 nothing committed those lines. The standing
dispatcher's record step commits only lines of `dispatch.COMMITTABLE_ACTORS` (dispatcher, desktop), so
a `governed_sync` line stayed uncommitted and the next pass refused EVERY task on c7 (squiddy SQ-016R,
2026-10-16 09:42Z).

The issue asked whether the order mattered (a task file already committed by `seldon_commit_governed`,
versus an untracked one that registration commits). Both orders are measured here, on the same
fixture; `docs/evidence/desk002/registration_event_lines.md` records the result on HEAD.

Real git and real Neo4j: what is under test is what the event store holds against HEAD afterwards.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from seldon.core import governed
from seldon.domain.loader import load_domain_config
from seldon.mcp_server import seldon_cc_register
from tests.test_governed import RESEARCH_YAML, ledger_lines
from tests.testdb import TEST_DATABASE

pytestmark = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

TASK = "cc_tasks/2026-10-16_SEL-T_constrained.md"
STORE = "seldon_events.jsonl"


def _git(root, *args, check=True):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(root), *args], check=check, capture_output=True, text=True, env=env)


@pytest.fixture
def project(tmp_path, neo4j_driver):
    """A git project whose event store is tracked, with one ruling (AD-900-R1) synced into the graph and
    every line that sync wrote committed, so the store is clean before registration runs."""
    root = tmp_path / "proj"
    (root / "governed" / "ledger").mkdir(parents=True)
    (root / "governed" / "ledger" / "events.jsonl").write_text("\n".join(ledger_lines()) + "\n")
    (root / "cc_tasks").mkdir()
    (root / "seldon.yaml").write_text(
        "project:\n  name: t\n  domain: research\n"
        f"neo4j:\n  database: {TEST_DATABASE}\n  uri: {os.getenv('NEO4J_URI', 'bolt://localhost:7687')}\n"
        f"event_store:\n  path: {STORE}\n"
        "governed:\n  graph_dir: governed\n  ruling_match_threshold: 0.18\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    from seldon.config import load_project_config
    governed.sync(project_dir=root, config=load_project_config(root), driver=neo4j_driver,
                  database=TEST_DATABASE, domain_config=load_domain_config(RESEARCH_YAML))
    assert governed.read_rulings(neo4j_driver, TEST_DATABASE), "the fixture ruling did not sync"
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init: the ruling, synced; the store committed")
    return root


def _task(root) -> None:
    (root / TASK).write_text("# CC Task: constrained\n\n**Governing:** AD-900-R1 (per-set RPE is never "
                             "recorded).\n**Model:** primary\n\nA task constrained by one ruling.\n")


def _uncommitted_lines(root) -> list[dict]:
    """The store's lines that HEAD does not hold."""
    head = _git(root, "show", f"HEAD:{STORE}", check=False).stdout.splitlines()
    now = (root / STORE).read_text().splitlines()
    assert now[:len(head)] == head, "the store is not append-only against HEAD"
    return [json.loads(x) for x in now[len(head):] if x.strip()]


@pytest.mark.parametrize("order", ["task_committed_first", "task_untracked"])
def test_registration_leaves_no_event_line_uncommitted(project, order):
    _task(project)
    if order == "task_committed_first":           # as `seldon_commit_governed` leaves it (SQ-016R)
        _git(project, "add", TASK)
        _git(project, "commit", "-qm", "desktop: task: constrained")

    out = seldon_cc_register(TASK, project_dir=str(project), allow_untracked=True)

    assert out.startswith("Registered:"), out
    assert "AD-900-R1" in out                       # the ruling was matched, so a link was written
    left = _uncommitted_lines(project)
    assert left == [], [(e["event_type"], e["actor"]) for e in left]
    assert _git(project, "status", "--porcelain", "--untracked-files=all").stdout == ""
    # The store's lines are committed by the registration, after the commit that holds the task: the
    # task's own `artifact_created` line names that commit as its `source_commit`.
    log = _git(project, "log", "--format=%s", "-3").stdout.splitlines()
    assert log[0].startswith("register: record"), log
