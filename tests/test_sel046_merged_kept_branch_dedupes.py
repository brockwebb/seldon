"""SEL-046 (AD-038-R25): the merge round drops a line main already holds, whichever task it was reconciled for.

SEL-045R merged SEL-045's kept branch. SEL-045's 14 lines were already on main under a `kept_events_reconciled` record
naming SEL-045's task id, and the round looked the reconciled ids up by the FINISHING task (SEL-045R's), found none,
and the union check refused 14 byte-identical pairs (`union_invalid`). The rule is about the event id, so the lookup
reads every task's records.

Shape: task X is kept and its lines reconciled into main under X's id; task Y's branch merges X's branch; main moves;
Y rebases. Built on the fixtures of `tests/test_sel034_kept_worktree_events.py`.
"""
from __future__ import annotations

import json

from seldon.commands import dispatch_worktree as W
from seldon.core import kept_events as K
from seldon.core import worktree as WT
from seldon.core.events import read_events
from tests.dispatch_scaffold import git
from tests.testdb import TEST_DATABASE as DB
from tests.test_sel034_kept_worktree_events import STORE, _config, _issue, _setup, dc  # noqa: F401 (fixture)

Y_REL = ".claude/worktrees/merger"
Y_BRANCH = "worktree-merger"
Y_TASK = "y-task-never-reconciled"


def _y_merges_x(p, driver, dc, x_branch):
    """Y branches from main, writes a line of its own, then merges X's kept branch (the union driver keeps both)."""
    git(p, "worktree", "add", "-q", "-b", Y_BRANCH, Y_REL)
    y = p / Y_REL
    _issue(y, driver, dc, "Y's own work", session_id="child-y-1")
    git(y, "commit", "-q", "-m", "Y's work", "--", STORE)
    git(y, "merge", "-q", "--no-edit", x_branch)
    return y


def _build(tmp_path, driver, dc):
    p, tid, e, i, finish = _setup(tmp_path, driver, dc, "blocked")
    y = _y_merges_x(p, driver, dc, finish["branch"])
    rec = W.reconcile_kept_events(p, _config(), driver, DB, dc, None, finish, "session_failed")
    assert rec and rec["event_ids"], "X's lines were reconciled into main under X's task id"
    _issue(p, driver, dc, "main moved on")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "main records")
    assert WT.rebase(y, "main")["ok"]
    return p, tid, y, rec


def test_a_branch_that_merged_another_tasks_kept_branch_drops_the_reconciled_copies(tmp_path, neo4j_driver,
                                                                                    clean_test_db, dc):
    p, x_tid, y, rec = _build(tmp_path, neo4j_driver, dc)
    x_ids = set(rec["event_ids"])
    # The defect: looked up by the finishing task, Y has nothing reconciled.
    assert K.reconciled_ids(p, STORE, Y_TASK) == set()
    tip = WT.rev(y, "HEAD")
    before = WT.check_union_text(WT.show(y, tip, STORE), "event_id", base=WT.show(y, "main", STORE))
    assert not before["ok"] and set(before["duplicates"]) == x_ids, before
    # The fix: the all-task lookup holds X's ids, and the per-task lookup is unchanged.
    every = K.reconciled_ids(p, STORE)
    assert x_ids <= every
    assert K.reconciled_ids(p, STORE, x_tid) == x_ids
    out = K.drop_reconciled(y, STORE, every, "y-task")
    assert set(out["dropped"]) == x_ids and out["commit"], out
    tip = WT.rev(y, "HEAD")
    check = WT.check_union_text(WT.show(y, tip, STORE), "event_id", base=WT.show(y, "main", STORE))
    assert check["ok"], (out, check)
    assert git(y, "status", "--porcelain").stdout.strip() == ""
    git(p, "merge", "--ff-only", "-q", Y_BRANCH)
    ids = [x["event_id"] for x in read_events(p)]
    assert len(ids) == len(set(ids)), "main holds each id once"
    assert x_ids <= set(ids)


def test_a_pair_under_one_id_that_differs_is_not_dropped_and_is_still_named(tmp_path, neo4j_driver,
                                                                            clean_test_db, dc):
    p, _x_tid, y, rec = _build(tmp_path, neo4j_driver, dc)
    x_ids = list(rec["event_ids"])
    changed = x_ids[0]
    # Alter Y's (later) copy of one of X's lines: same id, different record.
    path = y / STORE
    lines = path.read_text(encoding="utf-8").splitlines()
    seen, out = set(), []
    for raw in lines:
        ev = json.loads(raw) if raw.strip() else {}
        if ev.get("event_id") == changed:
            if changed in seen:
                ev["actor"] = "someone-else"
                raw = json.dumps(ev)
            seen.add(changed)
        out.append(raw)
    path.write_text("".join(r + "\n" for r in out), encoding="utf-8")
    git(y, "commit", "-q", "-m", "a differing copy", "--", STORE)
    res = K.drop_reconciled(y, STORE, K.reconciled_ids(p, STORE), "y-task")
    assert changed not in res["dropped"] and set(res["dropped"]) == set(x_ids) - {changed}, res
    tip = WT.rev(y, "HEAD")
    check = WT.check_union_text(WT.show(y, tip, STORE), "event_id", base=WT.show(y, "main", STORE))
    assert not check["ok"] and check["duplicates"] == [changed], check
