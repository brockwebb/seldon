"""TRIAGE-001 Part B: the `Moving:` status line and the dispatcher's exclusion of FUTURE tasks.

`cc_tasks/2026-10-15_TRIAGE-001_open_proposals_closed_as_history.md` asks for tests with a fake
graph: a FUTURE task is not a candidate and is not counted, and the line's numbers match a hand
count. The fake graph here is a driver whose sessions return fixed rows, so no Neo4j is needed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.core import dispatch as D
from seldon.core import moving as M

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
OPEN = ["accepted", "blocked", "in_progress", "proposed"]
FUT = "FUTURE (not scheduled; trigger: x): an idea"

#: The fake graph: one row per ResearchTask, every kind the line distinguishes. The hand count is
#: written beside each row and summed in EXPECTED.
ROWS = [
    {"artifact_id": "t01", "state": "in_progress", "source_file": "cc_tasks/a.md", "description": "run"},  # in progress
    {"artifact_id": "t02", "state": "in_progress", "source_file": None, "description": FUT},             # future
    {"artifact_id": "t03", "state": "proposed", "source_file": "cc_tasks/b.md", "description": "x"},      # proposed+src
    {"artifact_id": "t04", "state": "accepted", "source_file": "cc_tasks/c.md", "description": "x"},      # proposed+src
    {"artifact_id": "t05", "state": "proposed", "source_file": "cc_tasks/d.md", "description": FUT},      # future
    {"artifact_id": "t06", "state": "proposed", "source_file": None, "description": "no file"},           # none
    {"artifact_id": "t07", "state": "proposed", "source_file": None, "description": FUT},                 # future
    {"artifact_id": "t08", "state": "blocked", "source_file": "cc_tasks/e.md", "description": "x"},       # none
    {"artifact_id": "t09", "state": "completed", "completed_at": "2026-10-14T00:00:00Z",
     "updated_at": "2026-10-14T00:00:00Z", "description": "x"},                                           # closed
    {"artifact_id": "t10", "state": "superseded", "updated_at": "2026-10-09T13:00:00+00:00",
     "description": "x"},                                                                                 # closed
    {"artifact_id": "t11", "state": "withdrawn", "updated_at": "2026-10-01T00:00:00+00:00",
     "description": "x"},                                                                                 # too old
    {"artifact_id": "t12", "state": "completed", "completed_at": "2026-09-30T00:00:00Z",
     "updated_at": "2026-10-15T00:00:00Z", "description": "x"},                                           # completed_at wins: old
]
EXPECTED = {"in_progress": 1, "proposed_with_source": 2, "future": 3, "closed_this_week": 2}


class _FakeResult(list):
    def single(self):
        return self[0] if self else None

    def data(self):
        return list(self)


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        return _FakeResult(self.rows)


class _FakeDriver:
    def __init__(self, rows):
        self.rows = rows

    def session(self, database=None):
        return _FakeSession(self.rows)

    def close(self):
        pass


# ======================================================================== the FUTURE marker

@pytest.mark.parametrize("text,expect", [
    (FUT, True), ("  FUTURE: later", True), ("FUTURE", True),
    ("FUTUREPROOF the cache", False), ("Not FUTURE yet", False), ("future (lowercase)", False),
    ("", False), (None, False),
])
def test_future_is_the_word_at_the_start_of_the_description(text, expect):
    assert M.is_future(text) is expect


# ============================================================================== the counts

def test_the_line_numbers_match_the_hand_count():
    counts = M.moving_counts(ROWS, OPEN, NOW, 7)
    assert counts == EXPECTED
    assert M.moving_line(counts) == ("Moving: 1 in progress, 2 proposed with a source file; "
                                     "3 future ideas; 2 closed this week.")


def test_a_future_task_is_counted_only_as_future():
    """A FUTURE task with a source file is still a parked idea, not moving work."""
    only = [r for r in ROWS if r["artifact_id"] == "t05"]
    assert M.moving_counts(only, OPEN, NOW, 7) == {
        "in_progress": 0, "proposed_with_source": 0, "future": 1, "closed_this_week": 0}


def test_the_window_is_configured_and_validated():
    assert M.closed_window_days({}) == M.CLOSED_WINDOW_DAYS_DEFAULT
    assert M.closed_window_days({"status": {"closed_window_days": 30}}) == 30
    assert M.moving_counts(ROWS, OPEN, NOW, 30)["closed_this_week"] == 4
    for bad in (0, -1, "7", True, 1.5):
        with pytest.raises(ValueError, match="closed_window_days"):
            M.closed_window_days({"status": {"closed_window_days": bad}})


def test_a_closed_task_without_a_timestamp_fails_loud():
    with pytest.raises(ValueError, match="t99"):
        M.moving_counts([{"artifact_id": "t99", "state": "completed"}], OPEN, NOW, 7)


def test_project_moving_reads_the_fake_graph(tmp_path, monkeypatch):
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: t\n  domain: research\nneo4j:\n  database: fake\n  uri: bolt://x\n")
    import seldon.config
    monkeypatch.setattr(seldon.config, "get_neo4j_driver", lambda cfg: _FakeDriver(ROWS))
    assert M.project_moving(str(tmp_path), now=NOW) == EXPECTED


# ==================================================================== the dispatcher's side

def test_tasks_leaves_future_out_unless_asked(monkeypatch):
    """`_tasks` feeds every count and log line of a pass; a FUTURE row never reaches them. The
    registration commit asks for it, so a FUTURE task file is still committed."""
    from seldon.commands import dispatch as S
    rows = [dict(r, predecessors=[]) for r in ROWS if r["state"] in D.DISPATCHABLE_STATES]
    driver = _FakeDriver(rows)
    assert [r["artifact_id"] for r in S._tasks(driver, "fake")] == ["t03", "t04", "t06"]
    assert [r["artifact_id"] for r in S._tasks(driver, "fake", include_future=True)] == [
        "t03", "t04", "t05", "t06", "t07"]


def test_a_future_task_with_a_valid_file_is_not_a_candidate(tmp_path):
    """The same task file is a candidate until the description says FUTURE."""
    f = tmp_path / "cc_tasks" / "x.md"
    f.parent.mkdir()
    f.write_text("# t\n\n**Framework layer served:** none\n**Spend:** zero **Network:** none\n",
                 encoding="utf-8")
    assert D.candidacy(f)["candidate"]
    row = {"artifact_id": "t05", "name": "x", "state": "proposed",
           "source_file": "cc_tasks/x.md", "created_at": "2026-10-15", "predecessors": [],
           "description": FUT}
    out = D.evaluate(tmp_path, row, {}, 0, {}, None, {})
    assert out["candidate"] is False and out["not_a_candidate_reason"] == "future"
    assert out["eligible"] is False


# ======================================================================= printed first

def test_go_prints_the_line_first_in_both_forms(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "project_moving", lambda project_dir, now=None: EXPECTED)
    from seldon.commands import go as G
    text = G.assemble_go_context(project_dir=str(tmp_path), brief=True)
    assert text.splitlines()[0] == M.moving_line(EXPECTED)
    data = G.assemble_go_context_as_dict(project_dir=str(tmp_path), brief=True)
    assert next(iter(data)) == "moving" and data["moving"] == M.moving_line(EXPECTED)


def test_go_says_unavailable_rather_than_failing(tmp_path, monkeypatch):
    def boom(project_dir, now=None):
        raise RuntimeError("graph down")
    monkeypatch.setattr(M, "project_moving", boom)
    from seldon.commands import go as G
    assert G._get_moving_line(str(tmp_path)) == "Moving: unavailable (RuntimeError: graph down)."


def test_status_prints_the_line_first(tmp_path, monkeypatch):
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: t\n  domain: research\nneo4j:\n  database: fake\n  uri: bolt://x\n")
    monkeypatch.chdir(tmp_path)
    from seldon.commands import status as St
    monkeypatch.setattr(St, "project_moving", lambda project_dir, now=None: EXPECTED)
    monkeypatch.setattr(St, "get_neo4j_driver", lambda cfg: _FakeDriver([]))
    monkeypatch.setattr(St, "graph_stats", lambda s: {"total_nodes": 0, "total_relationships": 0,
                                                      "by_type": {}, "by_state": {}})
    monkeypatch.setattr(St, "get_stale_artifacts", lambda s: [])
    monkeypatch.setattr(St, "event_count", lambda p: 0)
    result = CliRunner().invoke(St.status_command, [])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0] == M.moving_line(EXPECTED)
