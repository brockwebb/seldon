"""SEL-008: a task waits on a task in another project's graph, and a block stores its reason (AD-038-R7..R9).

`cc_tasks/2026-10-24_SEL-008_cross_project_waits_on_and_a_stored_block_reason.md`. The incident: hazbrief HB-20
(`311388f9`) stopped on squiddy SQ-048, and the hazbrief graph said only "HB-19 precedes it"; the dependency lived in a
handoff paragraph, so a dispatcher reading the graph would have launched HB-20 into the same failure. Marking it blocked
took three transitions, one of them recording a claim that was not true, and the block kept no reason.

Three layers, as the task's three Parts:

A. `waits_on` across graphs: `seldon task wait-on <task> <project>:<prefix>` writes one event in the WAITING project's
   ledger and never writes the other graph; the read surfaces print the edge with the other task's state.
B. `blocked` from every open state, with a stored reason; no reason, no block.
C. the dispatcher reads both: an unsatisfied or unreadable cross-project wait is "not ready" (c17), a satisfied one lifts
   a declared block by redrive (AD-038-R2 applied), and `seldon verify` reports a reasonless block and a dead wait.

The "other project" is a second ephemeral test database behind a second `seldon.yaml`, so resolution runs through the
other project's own config exactly as it does between hazbrief and squiddy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.go import _format_project_state
from seldon.commands.session import get_briefing_data
from seldon.commands.task import task_group
from seldon.commands.verify import check_blocks_and_waits
from seldon.core import cross_project as X
from seldon.core import dispatch as D
from seldon.core import redrive as RD
from seldon.core.artifacts import create_artifact, transition_task
from seldon.core.graph import get_artifact
from seldon.core.precedence import precedence_view
from seldon.core.state import InvalidStateTransition
from seldon.domain.loader import load_domain_config
from tests.testdb import TEST_DATABASE, create_database, drop_database, is_ephemeral
from tests.test_dispatch import _commit, _row, _task_file, project  # noqa: F401  (fixture)

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
STORE = "seldon_events.jsonl"
OTHER_DB = f"{TEST_DATABASE}-xproj"
URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _seldon_yaml(path: Path, name: str, database: str, uri: str = URI, extra: dict | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / STORE).touch()
    body = {"project": {"name": name, "domain": "research", "slug": name},
            "neo4j": {"database": database, "uri": uri},
            "event_store": {"path": STORE}}
    body.update(extra or {})
    (path / "seldon.yaml").write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")


@pytest.fixture
def other_db(neo4j_driver):
    """The other project's graph: its own database, emptied before each test."""
    create_database(neo4j_driver, OTHER_DB)
    with neo4j_driver.session(database=OTHER_DB) as s:
        s.run("MATCH (n) DETACH DELETE n")
    yield OTHER_DB
    if is_ephemeral(TEST_DATABASE):
        drop_database(neo4j_driver, OTHER_DB)


@pytest.fixture
def other(tmp_path, other_db):
    """A sibling project named `other`, found by the side-by-side convention (no config entry)."""
    p = tmp_path / "other"
    _seldon_yaml(p, "other", other_db)
    return p


@pytest.fixture
def waiting(tmp_path, monkeypatch, clean_test_db):
    """The waiting project, the current directory of every CLI call."""
    p = tmp_path / "waiting"
    _seldon_yaml(p, "waiting", TEST_DATABASE)
    monkeypatch.chdir(p)
    return p


def _task(project_dir: Path, driver, database: str, domain_config, description: str, state: str = "proposed",
          **props) -> str:
    tid = create_artifact(project_dir=project_dir, driver=driver, database=database, domain_config=domain_config,
                          artifact_type="ResearchTask", properties={"description": description, **props},
                          actor="human", authority="accepted")
    path = {"proposed": [], "accepted": ["accepted"], "in_progress": ["accepted", "in_progress"],
            "completed": ["accepted", "in_progress", "completed"],
            "superseded": ["superseded"]}[state]
    current = "proposed"
    for nxt in path:
        transition_task(project_dir=project_dir, driver=driver, database=database, domain_config=domain_config,
                        artifact_id=tid, current_state=current, new_state=nxt, actor="human",
                        terminal_reason="test" if nxt == "superseded" else None)
        current = nxt
    return tid


def _lines(path: Path) -> list:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _node(driver, database, tid) -> dict:
    with driver.session(database=database) as s:
        return dict(get_artifact(s, tid))


def _invoke(*args):
    return CliRunner().invoke(task_group, list(args))


# ══════════════════════════════════════════════════════════════════════════════
# Part A: the grammar and the project name (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

def test_a_target_is_project_colon_prefix():
    t = X.parse_target("squiddy:abcd1234")
    assert (t.project, t.ref) == ("squiddy", "abcd1234")


@pytest.mark.parametrize("bad", ["abcd1234", ":abcd1234", "squiddy:", "a:b:c", "squ iddy:abcd1234", ""])
def test_a_target_that_is_not_project_colon_prefix_is_refused(bad):
    with pytest.raises(ValueError, match="<project>:<task-prefix>"):
        X.parse_target(bad)


def test_the_project_name_resolves_config_first_then_the_register_then_the_sibling(tmp_path):
    here = tmp_path / "here"
    _seldon_yaml(here, "here", "db")
    for name in ("cfgd", "regd", "sib"):
        _seldon_yaml(tmp_path / "elsewhere" / name, name, "db")
    _seldon_yaml(tmp_path / "sib", "sib", "db")
    config = {"tasks": {"projects": {"cfgd": "../elsewhere/cfgd"}},
              "decisions": {"repositories": {"regd": "../elsewhere/regd"}}}
    assert X.project_root("cfgd", here, config) == (tmp_path / "elsewhere" / "cfgd").resolve()
    assert X.project_root("regd", here, config) == (tmp_path / "elsewhere" / "regd").resolve()
    assert X.project_root("sib", here, config) == (tmp_path / "sib").resolve()


def test_a_project_name_that_resolves_to_no_seldon_project_is_refused_naming_where_it_looked(tmp_path):
    here = tmp_path / "here"
    _seldon_yaml(here, "here", "db")
    with pytest.raises(ValueError, match=r"nowhere.*seldon\.yaml"):
        X.project_root("nowhere", here, {})


def test_short_renders_a_qualified_id_with_its_project():
    from seldon.core.precedence import short
    assert short("squiddy:0123456789abcdef") == "squiddy:01234567"
    assert short("0123456789abcdef") == "01234567"


# ══════════════════════════════════════════════════════════════════════════════
# Part A: the write, read-only on the other graph
# ══════════════════════════════════════════════════════════════════════════════

@neo4j_tests
def test_wait_on_writes_one_event_in_the_waiting_ledger_and_nothing_in_the_other(
        neo4j_driver, waiting, other, domain_config):
    target = _task(other, neo4j_driver, OTHER_DB, domain_config, "SQ-048 the defect")
    hb20 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20 the concept layer")
    other_ledger = (other / STORE).read_bytes()
    other_node = _node(neo4j_driver, OTHER_DB, target)
    before = len(_lines(waiting / STORE))

    result = _invoke("wait-on", hb20[:8], f"other:{target[:8]}")

    assert result.exit_code == 0, result.output
    events = _lines(waiting / STORE)[before:]
    assert [e["event_type"] for e in events] == ["artifact_updated"]
    assert events[0]["payload"]["properties"][X.PROPERTY] == [f"other:{target}"]
    assert _node(neo4j_driver, TEST_DATABASE, hb20)[X.PROPERTY] == [f"other:{target}"]
    assert (other / STORE).read_bytes() == other_ledger
    assert _node(neo4j_driver, OTHER_DB, target) == other_node


@neo4j_tests
def test_a_target_that_resolves_to_no_task_is_refused_before_any_write(neo4j_driver, waiting, other, domain_config):
    hb20 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    before = (waiting / STORE).read_bytes()
    result = _invoke("wait-on", hb20[:8], "other:ffffffff")
    assert result.exit_code == 1
    assert "No artifact found" in result.output
    assert "Nothing was written" in result.output
    assert (waiting / STORE).read_bytes() == before


@neo4j_tests
def test_a_target_that_is_not_a_task_is_refused(neo4j_driver, waiting, other, domain_config):
    res = create_artifact(project_dir=other, driver=neo4j_driver, database=OTHER_DB, domain_config=domain_config,
                          artifact_type="Result", properties={"value": 1.0, "units": "n", "description": "r"},
                          actor="human", authority="accepted")
    hb20 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    result = _invoke("wait-on", hb20[:8], f"other:{res[:8]}")
    assert result.exit_code == 1
    assert "not a ResearchTask" in result.output


@neo4j_tests
def test_a_target_in_an_unknown_project_is_refused(neo4j_driver, waiting, domain_config):
    hb20 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    before = (waiting / STORE).read_bytes()
    result = _invoke("wait-on", hb20[:8], "nosuchproject:abcd1234")
    assert result.exit_code == 1
    assert (waiting / STORE).read_bytes() == before


@neo4j_tests
def test_re_recording_a_wait_is_a_no_op_and_unwait_removes_it(neo4j_driver, waiting, other, domain_config):
    target = _task(other, neo4j_driver, OTHER_DB, domain_config, "SQ-048")
    hb20 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    assert _invoke("wait-on", hb20[:8], f"other:{target[:8]}").exit_code == 0
    n = len(_lines(waiting / STORE))
    again = _invoke("wait-on", hb20[:8], f"other:{target}")
    assert again.exit_code == 0 and "already recorded" in again.output
    assert len(_lines(waiting / STORE)) == n

    gone = _invoke("unwait", hb20[:8], f"other:{target[:8]}")
    assert gone.exit_code == 0, gone.output
    assert not _node(neo4j_driver, TEST_DATABASE, hb20).get(X.PROPERTY)
    assert _invoke("unwait", hb20[:8], f"other:{target[:8]}").exit_code == 1


# ══════════════════════════════════════════════════════════════════════════════
# Part A: the read surfaces print the edge with the other task's state as of the call
# ══════════════════════════════════════════════════════════════════════════════

@neo4j_tests
def test_task_show_prints_the_edge_with_the_other_tasks_state_and_the_precedes_edges(
        neo4j_driver, waiting, other, domain_config):
    target = _task(other, neo4j_driver, OTHER_DB, domain_config, "SQ-048 the defect")
    hb19 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-19")
    hb20 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    assert _invoke("precede", hb19[:8], hb20[:8]).exit_code == 0
    assert _invoke("wait-on", hb20[:8], f"other:{target[:8]}").exit_code == 0

    out = _invoke("show", hb20[:8]).output
    assert f"other:{target[:8]}" in out and "proposed" in out
    assert "as of" in out
    assert f"Preceded by" in out and hb19[:8] in out


@neo4j_tests
def test_the_briefing_holds_a_waiting_task_back_until_the_other_task_completes(
        neo4j_driver, waiting, other, domain_config):
    target = _task(other, neo4j_driver, OTHER_DB, domain_config, "SQ-048")
    hb20 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    assert _invoke("wait-on", hb20[:8], f"other:{target[:8]}").exit_code == 0

    data = get_briefing_data(neo4j_driver, TEST_DATABASE, domain_config, project_dir=waiting)
    assert hb20 not in data["precedence"]["ready"]
    text = _format_project_state(data)
    assert f"other:{target[:8]} [proposed]" in text

    for nxt in ("accepted", "in_progress", "completed"):
        cur = _node(neo4j_driver, OTHER_DB, target)["state"]
        transition_task(project_dir=other, driver=neo4j_driver, database=OTHER_DB, domain_config=domain_config,
                        artifact_id=target, current_state=cur, new_state=nxt, actor="human")
    data = get_briefing_data(neo4j_driver, TEST_DATABASE, domain_config, project_dir=waiting)
    assert hb20 in data["precedence"]["ready"]


@neo4j_tests
def test_the_raw_view_counts_an_unread_cross_project_wait_as_unsatisfied(
        neo4j_driver, waiting, other, domain_config):
    """Fail closed: a surface that did not read the other graph never reports the task ready."""
    target = _task(other, neo4j_driver, OTHER_DB, domain_config, "SQ-048", state="completed")
    hb20 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    assert _invoke("wait-on", hb20[:8], f"other:{target[:8]}").exit_code == 0
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        view = precedence_view(s, ["proposed", "accepted", "in_progress", "blocked"])
    assert hb20 not in view["ready"]
    assert view["waits_on"][hb20] == [f"other:{target}"]


@neo4j_tests
def test_task_list_shows_the_cross_project_wait(neo4j_driver, waiting, other, domain_config):
    target = _task(other, neo4j_driver, OTHER_DB, domain_config, "SQ-048")
    hb20 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    assert _invoke("wait-on", hb20[:8], f"other:{target[:8]}").exit_code == 0
    out = _invoke("list").output
    row = next(line for line in out.splitlines() if hb20[:8] in line)
    assert "other:" in row
    assert not row.startswith("▸")


# ══════════════════════════════════════════════════════════════════════════════
# Part A: recordable at registration (`**After:** <project>:<ref>`)
# ══════════════════════════════════════════════════════════════════════════════

def test_the_after_grammar_takes_a_project_qualified_ref():
    parsed = D.parse_after("`local_stem`, squiddy:abcd1234")
    assert parsed["kind"] == "refs"
    assert parsed["refs"] == ["local_stem", "squiddy:abcd1234"]


def _register_body(after: str) -> str:
    return ("# CC Task — x\n\n**Spend:** zero model calls. **Network:** none.\n"
            f"**After:** {after}\n\n## 1. Do the thing.\n")


@neo4j_tests
def test_registration_records_a_cross_project_after_ref_on_the_created_task(
        neo4j_driver, waiting, other, domain_config):
    from seldon.commands.cc import register_task_file
    target = _task(other, neo4j_driver, OTHER_DB, domain_config, "SQ-048")
    (waiting / "cc_tasks").mkdir()
    f = waiting / "cc_tasks" / "2026-10-24_HB-20_x.md"
    f.write_text(_register_body(f"other:{target[:8]}"), encoding="utf-8")
    out = register_task_file(project_dir=waiting, task_path=f, driver=neo4j_driver, database=TEST_DATABASE,
                                domain_config=domain_config, actor="cc", session_id=None, config=yaml.safe_load(
                                    (waiting / "seldon.yaml").read_text()), allow_untracked=True)
    created = [e for e in _lines(waiting / STORE) if e["event_type"] == "artifact_created"
               and e["payload"]["artifact_id"] == out["artifact_id"]]
    assert created[0]["payload"]["properties"][X.PROPERTY] == [f"other:{target}"]


@neo4j_tests
def test_registration_refuses_an_unresolvable_cross_project_ref_and_writes_nothing(
        neo4j_driver, waiting, other, domain_config):
    from seldon.commands.cc import register_task_file
    (waiting / "cc_tasks").mkdir()
    f = waiting / "cc_tasks" / "2026-10-24_HB-20_y.md"
    f.write_text(_register_body("other:ffffffff"), encoding="utf-8")
    before = (waiting / STORE).read_bytes()
    with pytest.raises(ValueError, match="after_unresolved"):
        register_task_file(project_dir=waiting, task_path=f, driver=neo4j_driver, database=TEST_DATABASE,
                              domain_config=domain_config, actor="cc", session_id=None, config=yaml.safe_load(
                                  (waiting / "seldon.yaml").read_text()), allow_untracked=True)
    assert (waiting / STORE).read_bytes() == before


# ══════════════════════════════════════════════════════════════════════════════
# Part B: `blocked` from every open state, with a stored reason
# ══════════════════════════════════════════════════════════════════════════════

@neo4j_tests
@pytest.mark.parametrize("start", ["proposed", "accepted", "in_progress"])
def test_blocked_is_reachable_from_every_open_state_and_stores_its_reason(
        neo4j_driver, waiting, domain_config, start):
    tid = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20", state=start)
    before = len(_lines(waiting / STORE))
    result = _invoke("update", tid[:8], "--state", "blocked", "--reason", "waits on squiddy SQ-048")
    assert result.exit_code == 0, result.output
    node = _node(neo4j_driver, TEST_DATABASE, tid)
    assert node["state"] == "blocked"
    assert node["block_reason"] == "waits on squiddy SQ-048"
    events = _lines(waiting / STORE)[before:]
    assert any(e["event_type"] == "artifact_updated"
               and e["payload"]["properties"].get("block_reason") == "waits on squiddy SQ-048" for e in events)
    assert not node.get("claimed_by") or start == "in_progress"


@neo4j_tests
@pytest.mark.parametrize("reason", [None, "   "])
def test_blocked_with_no_reason_is_refused_and_writes_nothing(neo4j_driver, waiting, domain_config, reason):
    tid = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    before = (waiting / STORE).read_bytes()
    with pytest.raises(ValueError, match="needs a reason"):
        transition_task(project_dir=waiting, driver=neo4j_driver, database=TEST_DATABASE,
                        domain_config=domain_config, artifact_id=tid, current_state="proposed",
                        new_state="blocked", actor="human", block_reason=reason)
    result = _invoke("update", tid[:8], "--state", "blocked")
    assert result.exit_code == 1
    assert (waiting / STORE).read_bytes() == before
    assert _node(neo4j_driver, TEST_DATABASE, tid)["state"] == "proposed"


@neo4j_tests
def test_a_block_reason_is_refused_on_a_transition_that_is_not_a_block(neo4j_driver, waiting, domain_config):
    tid = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    with pytest.raises(ValueError, match="block reason"):
        transition_task(project_dir=waiting, driver=neo4j_driver, database=TEST_DATABASE,
                        domain_config=domain_config, artifact_id=tid, current_state="proposed",
                        new_state="accepted", actor="human", block_reason="x")


@neo4j_tests
def test_a_blocked_task_takes_a_new_reason_without_a_state_change(neo4j_driver, waiting, domain_config):
    """The backfill path for a task blocked before reasons existed (hazbrief HB-20)."""
    tid = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    assert _invoke("update", tid[:8], "--state", "blocked", "--reason", "first").exit_code == 0
    before = len(_lines(waiting / STORE))
    result = _invoke("update", tid[:8], "--state", "blocked", "--reason", "second")
    assert result.exit_code == 0, result.output
    events = _lines(waiting / STORE)[before:]
    assert [e["event_type"] for e in events] == ["artifact_updated"]
    assert _node(neo4j_driver, TEST_DATABASE, tid)["block_reason"] == "second"


@neo4j_tests
def test_leaving_blocked_clears_the_reason(neo4j_driver, waiting, domain_config):
    tid = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    assert _invoke("update", tid[:8], "--state", "blocked", "--reason", "waits").exit_code == 0
    RD.redrive(waiting, neo4j_driver, TEST_DATABASE, domain_config, tid, actor="desktop")
    node = _node(neo4j_driver, TEST_DATABASE, tid)
    assert node["state"] == "accepted"
    assert not node.get("block_reason")


@neo4j_tests
def test_the_mcp_update_takes_the_same_reason(neo4j_driver, waiting, domain_config):
    from seldon.mcp_server import seldon_task_update
    tid = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    refused = seldon_task_update(task_id=tid[:8], state="blocked", project_dir=str(waiting))
    assert refused.startswith("Error") and "needs a reason" in refused
    out = seldon_task_update(task_id=tid[:8], state="blocked", project_dir=str(waiting),
                             reason="waits on squiddy SQ-048")
    assert "Error" not in out, out
    assert _node(neo4j_driver, TEST_DATABASE, tid)["block_reason"] == "waits on squiddy SQ-048"


@neo4j_tests
def test_task_list_prints_the_reason_beside_blocked(neo4j_driver, waiting, domain_config):
    tid = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    assert _invoke("update", tid[:8], "--state", "blocked", "--reason", "waits on SQ-048").exit_code == 0
    row = next(line for line in _invoke("list").output.splitlines() if tid[:8] in line)
    assert "blocked" in row and "waits on SQ-048" in row


@neo4j_tests
def test_the_dispatchers_own_block_records_a_reason(neo4j_driver, waiting, domain_config):
    from seldon.commands import dispatch as S
    tid = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "t", state="in_progress")
    S._block(waiting, neo4j_driver, TEST_DATABASE, domain_config, None, tid, "in_progress", 1,
             "logs/x.log", reason="dispatcher: session_failed (exit 1; log logs/x.log)")
    node = _node(neo4j_driver, TEST_DATABASE, tid)
    assert node["state"] == "blocked"
    assert node["block_reason"].startswith("dispatcher: session_failed")


# ══════════════════════════════════════════════════════════════════════════════
# Part C: the dispatcher reads both graphs
# ══════════════════════════════════════════════════════════════════════════════

def test_c17_holds_a_task_whose_cross_project_wait_is_unsatisfied(project):  # noqa: F811
    f = _task_file(project, "waiter")
    _commit(project)
    cfg = D.load_dispatch_config(project)
    band = D.resolve_standing_band(project, cfg["standing_band_ref"])
    row = _row(project, f)
    waits = {row["artifact_id"]: [{"target": "squiddy:abcd", "state": "proposed", "error": None}]}
    out = D.evaluate(project, row, cfg, band, D.tree_state(project), None, {}, cross_waits=waits)
    assert out["failed"] == ["c17"]
    assert D.first_refusal_reason(out) == "waits_on_unsatisfied"

    unreachable = {row["artifact_id"]: [{"target": "squiddy:abcd", "state": None, "error": "connection refused"}]}
    out = D.evaluate(project, row, cfg, band, D.tree_state(project), None, {}, cross_waits=unreachable)
    assert out["failed"] == ["c17"]
    assert D.first_refusal_reason(out) == "waits_on_unreachable"

    clear = D.evaluate(project, row, cfg, band, D.tree_state(project), None, {}, cross_waits={})
    assert "c17" not in clear["criteria"]
    assert {"waits_on_unsatisfied", "waits_on_unreachable"} <= set(D.REFUSAL_REASONS)


@neo4j_tests
def test_the_cross_waits_read_is_ready_only_on_terminal_success_and_unreachable_is_not_ready(
        neo4j_driver, waiting, other, domain_config, tmp_path):
    done = _task(other, neo4j_driver, OTHER_DB, domain_config, "done", state="completed")
    open_ = _task(other, neo4j_driver, OTHER_DB, domain_config, "open")
    gone = _task(other, neo4j_driver, OTHER_DB, domain_config, "gone", state="superseded")
    tasks = [{"artifact_id": "t1", X.PROPERTY: [f"other:{done}"]},
             {"artifact_id": "t2", X.PROPERTY: [f"other:{open_}"]},
             {"artifact_id": "t3", X.PROPERTY: [f"other:{gone}"]},
             {"artifact_id": "t4", X.PROPERTY: None}]
    logged = []
    waits = X.unsatisfied_waits(waiting, tasks, on_error=logged.append)
    assert set(waits) == {"t2", "t3"}
    assert waits["t2"][0]["state"] == "proposed"
    assert not logged

    _seldon_yaml(tmp_path / "dark", "dark", OTHER_DB, uri="bolt://127.0.0.1:1")
    waits = X.unsatisfied_waits(waiting, [{"artifact_id": "t5", X.PROPERTY: [f"dark:{done}"]}],
                                on_error=logged.append)
    assert waits["t5"][0]["error"]
    assert logged and "not ready" in logged[0]


@neo4j_tests
def test_a_declared_block_is_lifted_when_every_cross_project_wait_is_satisfied(
        neo4j_driver, waiting, other, domain_config):
    target = _task(other, neo4j_driver, OTHER_DB, domain_config, "SQ-048", state="in_progress")
    hb20 = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "HB-20")
    assert _invoke("wait-on", hb20[:8], f"other:{target[:8]}").exit_code == 0
    assert _invoke("update", hb20[:8], "--state", "blocked", "--reason", "waits on SQ-048").exit_code == 0

    assert RD.auto_redrive(waiting, neo4j_driver, TEST_DATABASE, domain_config) == []
    assert _node(neo4j_driver, TEST_DATABASE, hb20)["state"] == "blocked"

    transition_task(project_dir=other, driver=neo4j_driver, database=OTHER_DB, domain_config=domain_config,
                    artifact_id=target, current_state="in_progress", new_state="completed", actor="human")
    done = RD.auto_redrive(waiting, neo4j_driver, TEST_DATABASE, domain_config)
    assert [d["task_id"] for d in done] == [hb20]
    assert done[0]["stop_reason"] == "waits_on_satisfied"
    assert _node(neo4j_driver, TEST_DATABASE, hb20)["state"] == "accepted"


@neo4j_tests
def test_a_dispatcher_halt_is_not_lifted_by_a_satisfied_wait(neo4j_driver, waiting, other, domain_config):
    """A session the dispatcher stopped keeps AD-038-R2's rule: only its own defects redrive it."""
    target = _task(other, neo4j_driver, OTHER_DB, domain_config, "SQ-048", state="completed")
    tid = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "t")
    assert _invoke("wait-on", tid[:8], f"other:{target[:8]}").exit_code == 0
    transition_task(project_dir=waiting, driver=neo4j_driver, database=TEST_DATABASE, domain_config=domain_config,
                    artifact_id=tid, current_state="proposed", new_state="accepted", actor="dispatcher")
    transition_task(project_dir=waiting, driver=neo4j_driver, database=TEST_DATABASE, domain_config=domain_config,
                    artifact_id=tid, current_state="accepted", new_state="in_progress", actor="dispatcher",
                    claimed_by="dispatcher:host:1")
    transition_task(project_dir=waiting, driver=neo4j_driver, database=TEST_DATABASE, domain_config=domain_config,
                    artifact_id=tid, current_state="in_progress", new_state="blocked", actor="dispatcher",
                    block_reason="dispatcher: session_failed")
    assert RD.auto_redrive(waiting, neo4j_driver, TEST_DATABASE, domain_config) == []
    assert _node(neo4j_driver, TEST_DATABASE, tid)["state"] == "blocked"


@neo4j_tests
def test_verify_reports_a_reasonless_block_a_dead_wait_and_a_target_that_no_longer_resolves(
        neo4j_driver, waiting, other, domain_config):
    config = yaml.safe_load((waiting / "seldon.yaml").read_text())
    assert check_blocks_and_waits(neo4j_driver, TEST_DATABASE, waiting, config).symbol == "pass"

    legacy = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "legacy", state="in_progress")
    with neo4j_driver.session(database=TEST_DATABASE) as s:      # a block written before reasons existed
        s.run("MATCH (t:Artifact {artifact_id: $id}) SET t.state = 'blocked'", id=legacy)
    r = check_blocks_and_waits(neo4j_driver, TEST_DATABASE, waiting, config)
    assert r.symbol == "warn"
    assert any(legacy[:8] in d and "--reason" in d for d in r.details)

    target = _task(other, neo4j_driver, OTHER_DB, domain_config, "SQ-048", state="superseded")
    waiter = _task(waiting, neo4j_driver, TEST_DATABASE, domain_config, "waiter")
    assert _invoke("wait-on", waiter[:8], f"other:{target[:8]}").exit_code == 0
    r = check_blocks_and_waits(neo4j_driver, TEST_DATABASE, waiting, config)
    assert any("superseded" in d for d in r.details)

    with neo4j_driver.session(database=OTHER_DB) as s:
        s.run("MATCH (n) DETACH DELETE n")
    r = check_blocks_and_waits(neo4j_driver, TEST_DATABASE, waiting, config)
    assert r.symbol == "fail"
    assert any("no longer resolves" in d for d in r.details)
