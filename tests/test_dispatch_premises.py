"""QC-002 Part B (AD-037-R6 a): pre-dispatch premise review, run by real passes against a scratch repository.

A task declares premises in a `**Premises:**` block (`premise: <statement> | check: <command>` or `| judgment: <why>`).
The dispatcher runs every `check:` premise before the claim; a false one refuses the launch as `premise_false`, files an
Issue naming it, and the task waits while that Issue is open (c13). The dispatcher adds one premise of its own to every
task: no other project's dispatcher holds a lease on a repository this project's environment names
(`environment_in_flight`, from SQ-015's kit pass). A task with no premises block launches: premises are optional.

The plants are the tests named `test_plant_*`; each fails on the HEAD before QC-002
(docs/evidence/qc002/plants_fail_on_head.txt).
"""
from __future__ import annotations

import json
import sys

import pytest
import yaml

from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    NEO4J_DB, RESEARCH_YAML, add_task, git, make_project, register, run_cli, task_states, write_stub,
)

pytestmark = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

FALSE = f"{sys.executable} -c \"import sys; sys.exit(1)\""
TRUE = f"{sys.executable} -c pass"


def _events(p, kind=None):
    rows = [json.loads(x) for x in (p / "seldon_events.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if kind is None or r["event_type"] == kind]


def _premises(*lines):
    return "**Premises:**\n" + "\n".join(f"- premise: {s} | {k}: `{c}`" for s, k, c in lines) + "\n"


def test_plant_a_false_check_premise_refuses_the_launch_and_files_an_issue(tmp_path, neo4j_driver):
    dc = load_domain_config(RESEARCH_YAML)
    p = make_project(tmp_path)
    add_task(p, "t1", extra=_premises(("the count is 5", "check", FALSE),
                                     ("the prose is the operator's", "judgment", "no command reads voice")))
    write_stub(p, {"t1": {"complete": True}})
    tid = register(p, neo4j_driver, dc, "t1", "2026-10-14T00:00:01Z")
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    assert _events(p, "dispatch_launched") == [], res.output
    (ref,) = [e for e in _events(p, "dispatch_refused") if e["payload"]["reason"] == "premise_false"]
    assert ref["payload"]["task_id"] == tid and ref["payload"]["false"][0]["statement"] == "the count is 5"
    with neo4j_driver.session(database=NEO4J_DB) as s:
        issue = s.run("MATCH (i:Issue {artifact_id: $id}) RETURN i.state AS st, i.description AS d",
                      id=ref["payload"]["issue_id"]).single()
    assert issue["st"] == "open" and "the count is 5" in issue["d"]
    assert task_states(neo4j_driver)["t1"] == "proposed", "a refused task is never claimed"

    # The open Issue holds the task (c13): the next pass neither launches nor files a second Issue.
    res = run_cli(p, dispatch_group, ["once"])
    assert _events(p, "dispatch_launched") == []
    assert len([e for e in _events(p, "dispatch_refused") if e["payload"]["reason"] == "premise_false"]) == 1
    st = json.loads(run_cli(p, dispatch_group, ["status", "--json"]).output)
    row = next(r for r in st["tasks"] if r["task_id"] == tid)
    assert row["criteria"]["c13"]["ok"] is False and row["criteria"]["c13"]["issue_state"] == "open"
    # `status --json` shows the premise outcomes of the last pass that reviewed them.
    review = st["last_premise_review"]
    assert review["task_id"] == tid and review["ok"] is False
    assert [x["outcome"] for x in review["premises"]] == ["false", "not_evaluated"]


def test_plant_a_held_lease_in_a_named_sibling_repository_refuses(tmp_path, neo4j_driver):
    dc = load_domain_config(RESEARCH_YAML)
    p = make_project(tmp_path, dispatch_extra={"stations": {"environment_ref": "kit.yaml#environment_packages"}})
    (p / "kit.yaml").write_text(yaml.safe_dump({"environment_packages": ["sib"]}), encoding="utf-8")
    git(p, "add", "kit.yaml")
    git(p, "commit", "-q", "-m", "kit")
    git(p, "push", "-q")
    sib = tmp_path / "sib"
    sib.mkdir()
    sib_cfg = {k: v for k, v in yaml.safe_load((p / "seldon.yaml").read_text(encoding="utf-8"))["dispatch"].items()
               if k != "stations"}
    (sib / "seldon.yaml").write_text(yaml.safe_dump({"dispatch": sib_cfg}), encoding="utf-8")
    add_task(p, "t1")
    write_stub(p, {"t1": {"complete": True}})
    register(p, neo4j_driver, dc, "t1", "2026-10-14T00:00:01Z")
    lease = D.Lease(sib / sib_cfg["lease_file"]).__enter__()
    try:
        lease.heartbeat(task="sibling-task")
        res = run_cli(p, dispatch_group, ["once"])
        run_cli(p, dispatch_group, ["once"])          # the standing condition is recorded once, not per pass
    finally:
        lease.__exit__(None, None, None)
    assert _events(p, "dispatch_launched") == [], res.output
    (ref,) = [e for e in _events(p, "dispatch_refused") if e["payload"]["reason"] == "environment_in_flight"]
    assert ref["payload"]["held"]["sib"]["task"] == "sibling-task"
    # Released: the next pass launches.
    run_cli(p, dispatch_group, ["once"])
    assert len(_events(p, "dispatch_launched")) == 1


def test_a_task_with_no_premises_block_launches_and_its_launch_lists_the_review(tmp_path, neo4j_driver):
    dc = load_domain_config(RESEARCH_YAML)
    p = make_project(tmp_path)
    add_task(p, "t1")
    add_task(p, "t2", extra=_premises(("the path exists", "check", TRUE),
                                     ("the reading is fair", "judgment", "a reader decides")))
    write_stub(p, {"t1": {"complete": True}, "t2": {"complete": True}})
    register(p, neo4j_driver, dc, "t1", "2026-10-14T00:00:01Z")
    register(p, neo4j_driver, dc, "t2", "2026-10-14T00:00:02Z")
    run_cli(p, dispatch_group, ["once"])
    run_cli(p, dispatch_group, ["once"])
    l1, l2 = _events(p, "dispatch_launched")
    assert l1["payload"]["premises"]["declared"] is False and l1["payload"]["premises"]["ok"] is True
    assert [x["outcome"] for x in l2["payload"]["premises"]["premises"]] == ["true", "not_evaluated"]
    assert l2["payload"]["premises"]["judgment"][0]["evaluated_by"].startswith("R2 checker")
    assert l2["payload"]["inspection_reserve"]["share"] == 0.1


def test_an_unreadable_premise_line_is_a_false_premise():
    from seldon.core import stations as S
    text = "**Premises:**\n- premise: the count is 5 | check: `true`\n- the count is 6 with no form\n\n## Part A: x\n"
    r = S.review_premises(".", text, S.load_stations_config({}), run=lambda *a, **k: {"outcome": "pass"})
    assert r["ok"] is False and r["false"][0]["outcome"] == "unreadable"
