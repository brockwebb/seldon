"""FRICTION-001 Part D (AD-038-R4): a station inspects the tree the session works in.

Issue 02d52bc4, DESK-002 (2026-10-16): an exclusive task worked on a branch in a git worktree, as the protocol tells
it to; at Part A it ran `seldon dispatch part-complete`, and the milestone station ran the Part's
`check: pytest tests/<new file>` in the PRIMARY checkout, where the new file did not exist yet. pytest exited 4, the
station recorded a failed check, wrote a line stop, and a correct session halted. DESK-002R re-issued the work.

Now `part_complete` records the session's `cwd` and `branch` and is written to the primary checkout's store (where
the dispatcher reads it), and the station runs the checks in `cwd`. A check naming a file absent from the tree it
ran in is `unrunnable` (a huddle) with reason `check_unrunnable_wrong_tree` when the session's branch holds it,
never a failed check. A genuinely failing test still stops the line.

No Neo4j: the stations read and write only the event store.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from seldon.commands.dispatch import dispatch_group
from seldon.commands import dispatch_stations as ST
from seldon.core import dispatch as D
from seldon.core import stations as S
from seldon.core.events import append_event, make_event, read_events
from tests.dispatch_scaffold import git, make_project, run_cli

TASK = """# CC Task — t1

**Framework layer served (DN-005 §5 rule 1):** none
**Spend:** est. 100K tokens. **Network:** none.
**Parts:** A 0.5, B 0.5.

## Part A: the new test

Acceptance:
- `check: pytest tests/test_new.py -q`

## Part B: nothing

Acceptance:
- `judgment: nothing to run`
"""

PASSING = "def test_ok():\n    assert True\n"
FAILING = "def test_bad():\n    assert False, 'a genuine defect'\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    p = make_project(tmp_path)
    (p / "cc_tasks" / "t1.md").write_text(TASK, encoding="utf-8")
    git(p, "add", "--", "cc_tasks/t1.md")
    git(p, "commit", "-q", "-m", "task t1", "--", "cc_tasks/t1.md")
    append_event(p, make_event("dispatch_launched", "dispatcher", "accepted",
                               {"task_id": "aaaaaaaa-0000-0000-0000-000000000001", "source_file": "cc_tasks/t1.md",
                                "child_session_id": "child-1", "launched_at": "2026-10-17T00:00:00Z"}))
    git(p, "commit", "-q", "-m", "launch", "--", "seldon_events.jsonl")
    monkeypatch.setenv("SELDON_SESSION_ID", "child-1")
    return p


def _worktree(p: Path, body: str) -> Path:
    """The session's worktree on branch feat/t1, holding the Part's new test file, committed on the branch only."""
    wt = p.parent / "wt"
    git(p, "worktree", "add", "-q", "-b", "feat/t1", str(wt))
    (wt / "tests").mkdir(exist_ok=True)
    (wt / "tests" / "test_new.py").write_text(body, encoding="utf-8")
    git(wt, "add", "--", "tests/test_new.py")
    git(wt, "commit", "-q", "--no-verify", "-m", "the new test")
    return wt


def _inspect(p: Path) -> dict:
    cfg = D.load_dispatch_config(p, yaml.safe_load((p / "seldon.yaml").read_text()))
    return ST.inspect_in_flight(p, cfg, "aaaaaaaa-0000-0000-0000-000000000001", holder=True)


def test_the_desk002_case_passes(project):
    """part-complete run from the worktree: the record lands in the primary store, the check runs in the worktree."""
    wt = _worktree(project, PASSING)
    out = run_cli(wt, dispatch_group, ["part-complete", "--part", "A"])
    assert out.exit_code == 0, out.output
    rec = [e for e in read_events(project) if e["event_type"] == S.EVENT_PART_COMPLETE]
    assert len(rec) == 1, "part_complete was not written to the primary checkout's store"
    assert Path(rec[0]["payload"]["cwd"]).resolve() == wt.resolve()
    assert rec[0]["payload"]["branch"] == "feat/t1"
    assert not (wt / "seldon_events.jsonl").read_text().count(S.EVENT_PART_COMPLETE)

    got = _inspect(project)
    assert [c["outcome"] for c in got["milestones"][0]["checks"]] == ["pass"], got
    assert got["stops"] == [] and got["huddles"] == []


def test_a_check_run_in_the_wrong_tree_is_a_huddle_not_a_stop(project):
    """A record from before FRICTION-001 carries no `cwd`: the check runs in the primary checkout, where the file
    is absent but the session's branch holds it. That is the dispatcher's defect: a huddle naming it, no stop."""
    _worktree(project, PASSING)
    append_event(project, make_event(S.EVENT_PART_COMPLETE, "cc", "accepted",
                                     {"task_id": "aaaaaaaa-0000-0000-0000-000000000001", "part": "A",
                                      "planned_share": 0.5, "tokens": None, "branch": "feat/t1"}))
    got = _inspect(project)
    check = got["milestones"][0]["checks"][0]
    assert check["outcome"] == "unrunnable" and check["reason"] == S.REASON_WRONG_TREE, check
    assert got["stops"] == []
    assert len(got["huddles"]) == 1 and got["huddles"][0]["reason"] == S.REASON_WRONG_TREE
    assert got["huddles"][0]["missing"] == ["tests/test_new.py"]


def test_a_genuinely_failing_test_still_stops_the_line(project):
    wt = _worktree(project, FAILING)
    out = run_cli(wt, dispatch_group, ["part-complete", "--part", "A"])
    assert out.exit_code == 0, out.output
    got = _inspect(project)
    assert [c["outcome"] for c in got["milestones"][0]["checks"]] == ["fail"], got
    assert len(got["stops"]) == 1 and got["stops"][0]["reason"] == "check_failed"
    # The session's next boundary halts on it.
    halt = run_cli(wt, dispatch_group, ["boundary"])
    assert halt.exit_code == S.HALT_EXIT, halt.output


def test_a_missing_file_no_branch_holds_is_named_as_missing():
    assert S.missing_file_reading("pytest tests/nowhere.py::test_x -q", Path("/"), None) == {
        "missing": ["tests/nowhere.py"], "reason": S.REASON_MISSING_FILE, "branch": None}


def test_an_existence_test_is_its_own_reading():
    """`test -f X` exists to read whether X exists: its exit 1 stays a failed check."""
    assert S.named_paths("test -f tests/x.py") == []
    assert S.named_paths("pytest tests/a.py -k 'b or c' --tb=short") == ["tests/a.py"]
