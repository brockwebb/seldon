"""SEL-034 Part B (AD-038-R25): a kept worktree's events reach main's log, or are discarded on record.

hazbrief HB-140's session, kept `session_failed`, wrote Issue 5b737052's creation and Issue 8b992307's move to
`resolved` through the live graph; neither reached main's `seldon_events.jsonl` (SEL-030), so a rebuild and the live
graph disagreed. Each test plants that shape: a git project, a kept worktree on its own branch, and a session's writes
made in the worktree (its store, the live test graph). Every test fails on main before this build, where
`seldon.core.kept_events` and `reconcile_kept_events` do not exist and nothing reads a kept tree's store.

"A rebuild and the live graph agree" is measured here by `kept_events.log_state` over main's store (the projection
rules of `seldon.core.sync._apply_event`) against the live node, for every artifact the session touched.
"""
from __future__ import annotations

import pytest

from seldon.commands import dispatch_worktree as W
from seldon.core import kept_events as K
from seldon.core import worktree as WT
from seldon.core.artifacts import create_artifact, transition_state, transition_task
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import RESEARCH_YAML, git, make_project
from tests.testdb import TEST_DATABASE as DB

STORE = "seldon_events.jsonl"
WT_REL = ".claude/worktrees/kept"
BRANCH = "worktree-kept"
SESSION = "child-kept-1"
ISSUE = {"description": "d", "issue_type": "missing_content", "importance": "low", "urgency": "low",
         "detection_method": "incidental", "target": "content"}


@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


def _issue(p, driver, dc, name, session_id=None):
    return create_artifact(project_dir=p, driver=driver, database=DB, domain_config=dc, artifact_type="Issue",
                           properties={**ISSUE, "name": name}, actor="cc", authority="accepted",
                           session_id=session_id)


def _live(driver, aid):
    with driver.session(database=DB) as s:
        r = s.run("MATCH (a:Artifact {artifact_id: $id}) RETURN a.state AS state, a.resolution_notes AS notes",
                  id=aid).single()
    return dict(r) if r else None


def _setup(tmp_path, driver, dc, task_state):
    """Main: a task and a pre-existing open Issue E, committed. A kept tree whose session created Issue I (linked to
    E) and resolved E, all written to the tree's store and the live graph. The task then ends in `task_state`."""
    p = make_project(tmp_path)
    tid = create_artifact(project_dir=p, driver=driver, database=DB, domain_config=dc, artifact_type="ResearchTask",
                          properties={"description": "t", "name": "sel034-b-task", "source_file": "cc_tasks/kept.md"},
                          actor="desktop", authority="accepted")
    for cur, new, claim in (("proposed", "accepted", None), ("accepted", "in_progress", "dispatcher:h:1")):
        transition_task(project_dir=p, driver=driver, database=DB, domain_config=dc, artifact_id=tid,
                        current_state=cur, new_state=new, actor="dispatcher", claimed_by=claim)
    e = _issue(p, driver, dc, "pre-existing E")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "main state")
    git(p, "worktree", "add", "-q", "-b", BRANCH, WT_REL)
    wt = p / WT_REL
    i = _issue(wt, driver, dc, "created by the session I", session_id=SESSION)
    transition_state(project_dir=wt, driver=driver, database=DB, domain_config=dc, artifact_id=e,
                     artifact_type="Issue", current_state="open", new_state="resolved", actor="cc",
                     authority="accepted", session_id=SESSION)
    git(wt, "commit", "-q", "-m", "session work", "--", STORE)
    if task_state == "withdrawn":
        transition_task(project_dir=p, driver=driver, database=DB, domain_config=dc, artifact_id=tid,
                        current_state="in_progress", new_state="withdrawn", actor="desktop",
                        terminal_reason="premise false")
    else:
        transition_task(project_dir=p, driver=driver, database=DB, domain_config=dc, artifact_id=tid,
                        current_state="in_progress", new_state="blocked", actor="dispatcher",
                        block_reason="dispatcher: session_failed")
    finish = {"task_id": tid, "worktree": WT_REL, "branch": BRANCH, "source_file": "cc_tasks/kept.md"}
    return p, tid, e, i, finish


def _config():
    return {"event_store": {"path": STORE}}


def _agrees(p, driver, ids):
    logged = K.log_state(read_events(p))
    return {aid: ((logged.get(aid) or {}).get("state"), (_live(driver, aid) or {}).get("state")) for aid in ids}


def test_a_kept_tree_of_a_live_task_union_merges_its_events_into_mains_log(tmp_path, neo4j_driver, clean_test_db, dc):
    p, tid, e, i, finish = _setup(tmp_path, neo4j_driver, dc, "blocked")
    before = _agrees(p, neo4j_driver, [e, i])
    assert before[e] == ("open", "resolved") and before[i] == (None, "open"), "the defect: log and graph disagree"
    rec = W.reconcile_kept_events(p, _config(), neo4j_driver, DB, dc, None, finish, "session_failed")
    assert rec["count"] == 2 and rec["task_state"] == "blocked"
    after = _agrees(p, neo4j_driver, [e, i])
    assert after[e] == ("resolved", "resolved") and after[i] == ("open", "open")
    (r,) = [x for x in read_events(p) if x["event_type"] == K.EVENT_RECONCILED]
    assert set(r["payload"]["event_ids"]) == set(rec["event_ids"])
    # Idempotent: the lines are on main now.
    assert W.reconcile_kept_events(p, _config(), neo4j_driver, DB, dc, None, finish, "session_failed") is None


def test_a_kept_tree_of_a_withdrawn_task_is_discarded_on_record_and_the_graph_agrees(tmp_path, neo4j_driver,
                                                                                    clean_test_db, dc):
    p, tid, e, i, finish = _setup(tmp_path, neo4j_driver, dc, "withdrawn")
    rec = W.reconcile_kept_events(p, _config(), neo4j_driver, DB, dc, None, finish, "session_failed")
    assert rec["task_state"] == "withdrawn"
    # E's move to resolved is discarded to evidence and compensated in the live graph.
    assert rec["count"] == 1 and rec["evidence"] == "docs/evidence/kept/discarded_events.jsonl"
    lines = (p / rec["evidence"]).read_text().splitlines()
    assert len(lines) == 1 and e in lines[0] and '"resolved"' in lines[0]
    assert [c["kind"] for c in rec["compensations"]] == ["transition"]
    # I's creation is carried (a node cannot be removed by an event) and I is closed premise_false naming the task.
    assert rec["created"] == [i] and len(rec["carried_ids"]) == 1
    (closed,) = rec["issues_closed"]
    assert closed["artifact_id"] == i and closed["path"] == ["open -> wont_fix"]
    assert _live(neo4j_driver, i)["notes"].startswith("premise_false:") and "sel034-b-task" in _live(
        neo4j_driver, i)["notes"]
    assert rec["unreconciled"] == []
    agree = _agrees(p, neo4j_driver, [e, i])
    assert agree[e] == ("open", "open") and agree[i] == ("wont_fix", "wont_fix")
    (d,) = [x for x in read_events(p) if x["event_type"] == K.EVENT_DISCARDED]
    assert d["payload"]["count"] == 1 and d["payload"]["event_ids"] == rec["event_ids"]
    # The evidence is committed on main, and a second run discards nothing again.
    assert git(p, "status", "--porcelain", "--", rec["evidence"]).stdout.strip() == ""
    assert W.reconcile_kept_events(p, _config(), neo4j_driver, DB, dc, None, finish, "session_failed") is None


def test_an_effect_another_hand_changed_since_is_left_as_that_hand_set_it(tmp_path, neo4j_driver, clean_test_db, dc):
    """HB-140R re-opened 8b992307 on main before the reconcile: no compensation, the Issue stays as it set it."""
    p, tid, e, i, finish = _setup(tmp_path, neo4j_driver, dc, "withdrawn")
    transition_state(project_dir=p, driver=neo4j_driver, database=DB, domain_config=dc, artifact_id=e,
                     artifact_type="Issue", current_state="resolved", new_state="open", actor="cc",
                     authority="accepted", session_id="hb140r")
    rec = W.reconcile_kept_events(p, _config(), neo4j_driver, DB, dc, None, finish, "session_failed")
    assert rec["count"] == 1 and rec["compensations"] == []
    assert _agrees(p, neo4j_driver, [e])[e] == ("open", "open")


def test_a_reconciled_branch_still_merges_its_copies_dropped(tmp_path, neo4j_driver, clean_test_db, dc):
    """The union path puts the branch's lines on main; a later merge of the same branch (regate, re-merge) must not
    bring them twice (`read_events` refuses a duplicate id). Main moves meanwhile, so the rebase keeps both copies."""
    p, tid, e, i, finish = _setup(tmp_path, neo4j_driver, dc, "blocked")
    rec = W.reconcile_kept_events(p, _config(), neo4j_driver, DB, dc, None, finish, "session_failed")
    _issue(p, neo4j_driver, dc, "main moved on")
    git(p, "commit", "-q", "-m", "main records", "--", STORE)
    wt = p / WT_REL
    assert WT.rebase(wt, "main")["ok"]
    ids = K.reconciled_ids(p, STORE, tid)
    assert ids == set(rec["event_ids"])
    out = K.drop_reconciled(wt, STORE, ids, "sel034-b-task")
    assert out["dropped"], "the rebase kept both copies, as the union driver does when main appended after them"
    tip = WT.rev(wt, "HEAD")
    check = WT.check_union_text(WT.show(wt, tip, STORE), "event_id", base=WT.show(wt, "main", STORE))
    assert check["ok"], (out, check)
    assert git(wt, "status", "--porcelain").stdout.strip() == ""
    # Fast-forward main to the branch: one line per id, readable.
    git(p, "merge", "--ff-only", "-q", BRANCH)
    assert len({x["event_id"] for x in read_events(p)}) == len(read_events(p))
