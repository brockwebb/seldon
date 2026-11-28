"""SEL-062 Part C: merge and completion evidence (REVIEW-001 F-08, F-16, F-19, F-21).

`cc_tasks/2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say.md`;
rulings AD-034 ADDENDUM 15 (amending R26, R39 and R41).

* F-08: a Stop gate check that only tests that the task's own RESULT exists is not merge evidence (the finish
  already requires the RESULT), and `seldon cc return` no longer writes one into every return.
* F-16: R41 is a guard on the ResearchTask transition into `completed`, so `seldon task close`, `task update` and
  every other walk meet it, not only the two completion commands; the dispatcher's own merge passes its evidence.
* F-19: a declared pass record scoped by `tree_paths` is not a full gate of the tip: it neither stands under a red
  main's closure nor ends it.
* F-21: R41's evidence also requires that the blocked task's branch reached main (`git cherry`: every commit's patch).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands import cc as CC
from seldon.commands import dispatch as S
from seldon.commands import dispatch_worktree as W
from seldon.config import load_project_config
from seldon.core import gate_plan as GP
from seldon.core import returns as R
from seldon.core.artifacts import R41Refused, transition_task, walk_to_completed
from seldon.core.events import append_event, make_event
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import NEO4J_DB, RESEARCH_YAML, add_task, git, make_project, register


# ============================================================================ F-08: the tautological check

def test_part_c_a_stop_gate_whose_only_check_is_its_own_results_presence_is_not_evidence():
    finish = {"stop_gate": {"verdict": "pass", "checks_run": 1, "checks_evidential": 0}}
    assert W.gate_evidence(finish, None, None) is None
    finish = {"stop_gate": {"verdict": "pass", "checks_run": 2, "checks_evidential": 1}}
    assert W.gate_evidence(finish, None, None) == {"source": "stop_gate", "checks_run": 2, "checks_evidential": 1}


@pytest.mark.parametrize("command,evidential", [
    ("test -f cc_tasks/2026-11-28_X-1_a_thing_RESULT.md", False),
    ("test -e cc_tasks/2026-11-28_X-1_a_thing_RESULT.md", False),
    ("[ -f cc_tasks/2026-11-28_X-1_a_thing_RESULT.md ]", False),
    ("test -s ./cc_tasks/2026-11-28_X-1_a_thing_RESULT.md", False),
    ("python -m pytest tests/test_x.py -q", True),
    ("test -f docs/evidence/x1/table.csv", True),
    ("test -f cc_tasks/2026-11-28_X-1_a_thing_RESULT.md && grep -q 'Recall used' cc_tasks/x_RESULT.md", True),
])
def test_part_c_only_a_check_of_the_tasks_own_result_presence_is_tautological(command, evidential):
    assert W.evidential_check(command, "cc_tasks/2026-11-28_X-1_a_thing.md") is evidential


def test_part_c_the_gate_reading_counts_evidential_checks(tmp_path):
    (tmp_path / "seldon_events.jsonl").write_text("", encoding="utf-8")
    rel = "cc_tasks/2026-11-28_X-1_a_thing.md"
    launch = make_event("dispatch_launched", "dispatcher", "accepted",
                        {"task_id": "t", "child_session_id": "c", "source_file": rel})
    append_event(tmp_path, launch)
    gate = make_event("stop_gate", "dispatcher", "accepted", {
        "task_id": "t", "child_session_id": "c", "verdict": "pass", "failed": [],
        "parts": [{"part": "A", "checks": [{"command": f"test -f {rel[:-3]}_RESULT.md", "outcome": "pass"}]}]})
    append_event(tmp_path, gate)
    reading = S._gate_reading(tmp_path, "t", "c")
    assert reading["passed"] and reading["checks_run"] == 1 and reading["checks_evidential"] == 0


def test_part_c_a_return_writes_no_check_of_its_own_result():
    answered = R.Answered(project="consumer", ref="F-1", root=Path("/tmp/consumer"), artifact_id="a" * 36,
                          source_file="cc_tasks/2026-11-28_F-1_a_filing.md")
    text = R.render(token="X-2", title="t", producer="seldon", task_id="b" * 36, task_token="SEL-9",
                    task_rel="cc_tasks/x.md", result_rel="cc_tasks/x_RESULT.md", commit="c" * 40, where="main",
                    answered=answered, after=None, headers={"Spend": "est. 0.1M", "Network": "none"}, body="apply",
                    date="2026-11-28", task_file_stem="2026-11-28_X-2_t")
    assert "check: test -f" not in text and "## Part A: apply it" in text


# ============================================================================ F-19: a scoped pass record

def _red():
    return {"event_id": "red-1", "event_type": GP.EVENT_GATE_RUN, "timestamp": "2026-11-28T00:00:00Z",
            "payload": {"call_site": GP.CALL_SITE_SCHEDULED, "tier": GP.TIER_FULL, "outcome": "fail",
                        "failed_files": ["tests/test_a.py"]}}


def _merged(evidence):
    return {"event_id": "fin-1", "event_type": "dispatch_finished", "timestamp": "2026-11-28T01:00:00Z",
            "payload": {"outcome": "merged", "merge": {"gate_evidence": evidence}}}


def test_part_c_a_scoped_pass_record_neither_stands_under_the_closure_nor_ends_it():
    scoped = {"source": "gate_record", "record": {"covered": True}, "scoped": ["squiddy/"]}
    assert GP.closure_admits(scoped, _red()) is False
    assert GP.main_red([_red(), _merged(scoped)]) is not None


def test_part_c_a_whole_tree_pass_record_still_stands_and_ends_the_closure():
    whole = {"source": "gate_record", "record": {"covered": True}, "scoped": None}
    assert GP.closure_admits(whole, _red()) is True
    assert GP.main_red([_red(), _merged(whole)]) is None


def test_part_c_the_round_marks_a_record_scoped_by_its_declaration():
    ev = W.gate_evidence({}, None, {"covered": True}, None, gate_record_decl={"tree_paths": ["squiddy/"]})
    assert ev["scoped"] == ["squiddy/"]
    ev = W.gate_evidence({}, None, {"covered": True}, None, gate_record_decl={"tree_paths": []})
    assert ev["scoped"] is None


# ============================================================================ F-16 / F-21: R41 on the transition

@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _blocked_task(p, driver, dc, stem):
    add_task(p, stem)
    tid = register(p, driver, dc, stem, "2026-11-28T00:00:00Z")
    for a, b in (("proposed", "accepted"), ("accepted", "in_progress")):
        transition_task(project_dir=p, driver=driver, database=NEO4J_DB, domain_config=dc, artifact_id=tid,
                        current_state=a, new_state=b, actor="dispatcher", authority="accepted")
    append_event(p, make_event("dispatch_launched", "dispatcher", "accepted",
                               {"task_id": tid, "source_file": f"cc_tasks/{stem}.md", "child_session_id": "c"}))
    transition_task(project_dir=p, driver=driver, database=NEO4J_DB, domain_config=dc, artifact_id=tid,
                    current_state="in_progress", new_state="blocked", actor="dispatcher", authority="accepted",
                    block_reason="merge_blocked: ungated")
    return tid


def _full_gate_of_main(p):
    tree = subprocess.run(["git", "-C", str(p), "rev-parse", "main^{tree}"], capture_output=True, text=True,
                          check=True).stdout.strip()
    append_event(p, make_event(GP.EVENT_GATE_RUN, "dispatcher", "accepted", {
        "tree": tree, "outcome": GP.OUTCOME_PASS, "dirty": False, "tier": GP.TIER_FULL,
        "call_site": GP.CALL_SITE_SCHEDULED}))


@pytest.mark.usefixtures("neo4j_available")
def test_part_c_task_close_meets_r41_on_a_blocked_task(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)
    tid = _blocked_task(p, neo4j_driver, dc, "T-r41close")
    with pytest.raises(R41Refused, match="blocked_ungated"):
        walk_to_completed(project_dir=p, driver=neo4j_driver, database=NEO4J_DB, domain_config=dc,
                          artifact_id=tid, current_state="blocked", actor="cc")
    transition_task(project_dir=p, driver=neo4j_driver, database=NEO4J_DB, domain_config=dc, artifact_id=tid,
                    current_state="blocked", new_state="in_progress", actor="human", authority="accepted")
    with pytest.raises(R41Refused):
        transition_task(project_dir=p, driver=neo4j_driver, database=NEO4J_DB, domain_config=dc, artifact_id=tid,
                        current_state="in_progress", new_state="completed", actor="human", authority="accepted")


@pytest.mark.usefixtures("neo4j_available")
def test_part_c_the_dispatchers_merge_and_the_operators_override_pass_the_guard(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)
    tid = _blocked_task(p, neo4j_driver, dc, "T-r41merge")
    transition_task(project_dir=p, driver=neo4j_driver, database=NEO4J_DB, domain_config=dc, artifact_id=tid,
                    current_state="blocked", new_state="in_progress", actor="dispatcher", authority="accepted")
    walk_to_completed(project_dir=p, driver=neo4j_driver, database=NEO4J_DB, domain_config=dc, artifact_id=tid,
                      current_state="in_progress", actor="dispatcher",
                      completion={"by": "merge", "evidence": {"source": "regate"}})
    other = _blocked_task(p, neo4j_driver, dc, "T-r41override")
    walk_to_completed(project_dir=p, driver=neo4j_driver, database=NEO4J_DB, domain_config=dc, artifact_id=other,
                      current_state="blocked", actor="cc", completion={"by": "ungated", "reason": "landed by hand"})


@pytest.mark.usefixtures("neo4j_available")
def test_part_c_r41_refuses_a_blocked_task_whose_branch_did_not_reach_main(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)
    tid = _blocked_task(p, neo4j_driver, dc, "T-r41branch")
    git(p, "checkout", "-q", "-b", "worktree-r41")
    (p / "work.txt").write_text("the task's work\n", encoding="utf-8")
    git(p, "add", "work.txt")
    git(p, "commit", "-q", "-m", "work", "--", "work.txt")
    git(p, "checkout", "-q", "main")
    append_event(p, make_event("worktree_kept", "dispatcher", "accepted",
                               {"task_id": tid, "worktree": ".claude/worktrees/r41", "branch": "worktree-r41",
                                "outcome": "merge_blocked", "reason": "ungated"}))
    _full_gate_of_main(p)
    config = load_project_config(p)
    props, refusal = CC.r41_completion(p, config, tid, "blocked", None)
    assert refusal and "branch_not_on_main" in refusal and "worktree-r41" in refusal
    git(p, "cherry-pick", "-q", "worktree-r41")
    _full_gate_of_main(p)
    props, refusal = CC.r41_completion(p, config, tid, "blocked", None)
    assert refusal is None and props.get("completion_gate"), refusal
