"""SEL-052 Part A: the rest of factory's 2026-11-26 prior-art filing, and its spec-check filing's `decision project`.

- item 2: `seldon_req_add` / `seldon_req_update` on seldon-mcp, the CLI's fields and refusals (one core call).
- item 3: a requirement's disposition, first-class, with its grounds, shown in the Status cell.
- item 4: `decision accept --from` of a new record with no `source` is refused before any file is written.
- spec check: `seldon decision project` in a worktree holding pending records raised `KeyError: 'record_hash'`.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from seldon.commands.req import req_group
from seldon.core import decisions as dr
from seldon.core import requirements as RQ
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import RESEARCH_YAML
from tests.test_sel035_authored_once import STATUS_MAP, VIEW, _node, _settings, dc, proj  # noqa: F401
from tests.test_sel042_verify_pending_and_name_limit import _cfg, _record, pending_tree  # noqa: F401
from tests.testdb import TEST_DATABASE

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


# ------------------------------------------------------------------------------------------- item 3, pure

@pytest.mark.parametrize("node, needle", [
    ({"disposition": "planned"}, "disposition_task"),
    ({"disposition": "deferred", "disposition_reason": "after the pilot"}, "disposition_ends_when"),
    ({"disposition": "declined"}, "disposition_reason"),
])
def test_a_disposition_without_its_grounds_is_refused(node, needle):
    with pytest.raises(RQ.RequirementsError, match=needle):
        RQ.check_disposition("SN-1", node)


def test_a_disposition_is_shown_after_the_state_and_its_absence_changes_nothing():
    labels = _settings().labels(VIEW)
    assert RQ.status_cell({"state": "accepted"}, labels, STATUS_MAP) == "open"
    node = {"state": "accepted", "disposition": "deferred", "disposition_reason": "no second consumer",
            "disposition_ends_when": "a second repository asks"}
    assert RQ.status_cell(node, labels, STATUS_MAP) == \
        "open; disposition: deferred (no second consumer; ends when: a second repository asks)"
    assert RQ.status_cell({"state": "accepted", "disposition": "planned", "disposition_task": "FAC-20"}, labels,
                          STATUS_MAP) == "open; disposition: planned (FAC-20)"


# -------------------------------------------------------------------------------------- items 2 and 3, graph

@neo4j_tests
def test_the_cli_records_a_disposition_and_refuses_one_without_grounds(proj, neo4j_driver):
    run = CliRunner()
    r = run.invoke(req_group, ["add", "SN-1", "--statement", "A need is recorded with its disposition.",
                               "--document", VIEW, "--disposition", "declined"])
    assert r.exit_code == 1 and "disposition_reason" in r.output, r.output
    assert _node(neo4j_driver, "SN-1") is None, "a refused add wrote nothing"
    r = run.invoke(req_group, ["add", "SN-1", "--statement", "A need is recorded with its disposition.",
                               "--document", VIEW, "--disposition", "declined",
                               "--disposition-reason", "the kit already does it"])
    assert r.exit_code == 0, r.output
    n = _node(neo4j_driver, "SN-1")
    assert (n["disposition"], n["disposition_reason"]) == ("declined", "the kit already does it")
    # An update reads the node as it would stand: moving to deferred needs the ending condition too.
    r = run.invoke(req_group, ["update", "SN-1", "--disposition", "deferred"])
    assert r.exit_code == 1 and "disposition_ends_when" in r.output, r.output


@neo4j_tests
def test_the_mcp_verbs_are_the_cli_with_the_same_refusals(proj, neo4j_driver):
    from seldon import mcp_server as M
    add, update = M.RAW_TOOLS["seldon_req_add"], M.RAW_TOOLS["seldon_req_update"]
    out = add("SN-2", "A need said in a thread enters the graph in that turn.", project_dir=str(proj),
              document=VIEW, set_by="operator 2026-11-26 08:54", disposition="planned")
    assert out.startswith("Error:") and "disposition_task" in out and "Nothing was written" in out, out
    out = add("SN-2", "A need said in a thread enters the graph in that turn.", project_dir=str(proj),
              document=VIEW, set_by="operator 2026-11-26 08:54", disposition="planned", disposition_task="FAC-17")
    assert out.startswith("Created requirement SN-2"), out
    out = add("SN-2", "again", project_dir=str(proj))
    assert out.startswith("Error:") and "exists" in out, out
    out = update("SN-2", project_dir=str(proj), note="carried by FAC-17", state="accepted")
    assert out.startswith("Updated requirement SN-2"), out
    n = _node(neo4j_driver, "SN-2")
    assert (n["state"], n["note"], n["disposition_task"], n["set_by"]) == \
        ("accepted", "carried by FAC-17", "FAC-17", "operator 2026-11-26 08:54")
    out = update("SN-404", project_dir=str(proj), note="x")
    assert out.startswith("Error:") and "not a requirement" in out, out


# --------------------------------------------------------------------------------------------- item 4

def test_a_new_record_with_no_source_is_refused_and_nothing_is_written(pending_tree):
    root, wt = pending_tree
    before = sorted(p.name for p in dr.Register("proj", wt).pending_files())
    rec = {k: v for k, v in _record("R-9", 3, "x").items() if k != "source"}
    with pytest.raises(dr.RegisterError, match="has no `source`"):
        dr.create(dr.universe(wt, _cfg(wt)), "accept", rec, date="2026-11-26", decided_by="desktop")
    assert sorted(p.name for p in dr.Register("proj", wt).pending_files()) == before
    assert dr.Register("proj", wt).verify() == []


# ------------------------------------------------------------------------------- spec check: decision project

@neo4j_tests
def test_decision_project_in_a_worktree_with_pending_records_projects_the_numbered_ones(pending_tree, neo4j_driver):
    root, wt = pending_tree
    rep = dr.project(project_dir=wt, config=_cfg(wt), driver=neo4j_driver, database=TEST_DATABASE,
                     domain_config=load_domain_config(RESEARCH_YAML))
    assert rep.pending == 3
    assert rep.unchanged == 1 and rep.created == 0, rep
