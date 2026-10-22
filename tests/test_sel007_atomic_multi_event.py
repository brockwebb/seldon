"""SEL-007: a command that writes more than one event line writes all of them or none.

The defect (hazbrief-mcp HB-01e RESULT section 10a): `seldon task create --depends-on
<task>` appended the `artifact_created` line, then the link was refused, and the
command exited as if nothing had been written. The orphan task had to be superseded
by hand.

The fix validates every edge before the first write and appends every line in one
ledger write (`seldon.core.events.append_events`), the all-or-nothing rule AD-029
section 2 already set for `seldon task chain`. Requires Neo4j.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.task import task_group
from seldon.core import events as events_module
from seldon.core.artifacts import create_artifact
from seldon.core.events import EVENTS_FILENAME, append_events, read_events
from seldon.domain.loader import load_domain_config

from tests.testdb import TEST_DATABASE
from tests.test_prune001 import owner  # noqa: F401 — fixture reused by the prune test

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def cli_project(project_dir, monkeypatch):
    """A project whose seldon.yaml points at the test database; the CLI reads it from cwd."""
    (project_dir / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    monkeypatch.chdir(project_dir)
    return project_dir


def _make(project_dir, driver, domain_config, artifact_type, properties):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type=artifact_type,
        properties=properties, actor="human", authority="accepted",
    )


def _task(project_dir, driver, domain_config, description="existing task"):
    return _make(project_dir, driver, domain_config, "ResearchTask",
                 {"description": description})


def _result(project_dir, driver, domain_config):
    return _make(project_dir, driver, domain_config, "Result",
                 {"value": 1.0, "units": "score", "description": "a result"})


def _ledger_lines(project_dir) -> list[str]:
    path = Path(project_dir) / EVENTS_FILENAME
    return path.read_text().splitlines() if path.exists() else []


def _task_count(driver, description: str) -> int:
    with driver.session(database=NEO4J_DB) as session:
        return session.run(
            "MATCH (t:ResearchTask {description: $d}) RETURN count(t) AS n", d=description,
        ).single()["n"]


# ── the ledger primitive ──────────────────────────────────────────────────────

def test_append_events_writes_every_line_in_one_write(tmp_path, monkeypatch):
    """All lines go down in one write call, so a crash cannot land half a batch."""
    writes: list[str] = []
    real_open = open

    class _Spy:
        def __init__(self, handle):
            self._h = handle

        def write(self, data):
            writes.append(data)
            return self._h.write(data)

        def __getattr__(self, name):
            return getattr(self._h, name)

        def __enter__(self):
            self._h.__enter__()
            return self

        def __exit__(self, *exc):
            return self._h.__exit__(*exc)

    def spy_open(path, mode="r", *args, **kwargs):
        handle = real_open(path, mode, *args, **kwargs)
        return _Spy(handle) if "a" in mode else handle

    monkeypatch.setattr(events_module, "open", spy_open, raising=False)
    batch = [
        events_module.make_event("artifact_created", "human", "accepted", {"n": 1}),
        events_module.make_event("link_created", "human", "accepted", {"n": 2}),
    ]
    append_events(tmp_path, batch)

    assert len(writes) == 1
    assert [json.loads(line)["payload"]["n"] for line in writes[0].splitlines()] == [1, 2]
    assert [e["event_id"] for e in read_events(tmp_path)] == [e["event_id"] for e in batch]


def test_append_events_with_nothing_writes_nothing(tmp_path):
    append_events(tmp_path, [])
    assert not (tmp_path / EVENTS_FILENAME).exists()


# ── Part A: task create is atomic ─────────────────────────────────────────────

def test_illegal_depends_on_target_writes_no_event_and_no_artifact(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """The HB-01e case: --depends-on naming another ResearchTask."""
    other = _task(cli_project, neo4j_driver, domain_config)
    before = _ledger_lines(cli_project)

    result = CliRunner().invoke(
        task_group, ["create", "--description", "orphan probe", "--depends-on", other],
    )

    assert result.exit_code == 1
    assert _ledger_lines(cli_project) == before
    assert _task_count(neo4j_driver, "orphan probe") == 0


def test_a_legal_edge_before_an_illegal_one_is_not_written_either(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """Every edge is validated before the first write, not only the first edge."""
    res = _result(cli_project, neo4j_driver, domain_config)
    other = _task(cli_project, neo4j_driver, domain_config)
    before = _ledger_lines(cli_project)

    result = CliRunner().invoke(
        task_group,
        ["create", "--description", "mixed probe", "--depends-on", f"{res},{other}"],
    )

    assert result.exit_code == 1
    assert _ledger_lines(cli_project) == before
    assert _task_count(neo4j_driver, "mixed probe") == 0


def test_an_unknown_target_is_refused_not_skipped(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """Before SEL-007 an unknown id was a warning and the task was created without it."""
    before = _ledger_lines(cli_project)

    for option in ("--depends-on", "--blocks"):
        result = CliRunner().invoke(
            task_group, ["create", "--description", "ghost probe", option, "ffffffff"],
        )
        assert result.exit_code == 1, option
        assert "ffffffff" in result.output
    assert _ledger_lines(cli_project) == before
    assert _task_count(neo4j_driver, "ghost probe") == 0


def test_legal_edges_land_with_the_artifact_in_one_append(
    neo4j_driver, cli_project, domain_config, clean_test_db, monkeypatch,
):
    res = _result(cli_project, neo4j_driver, domain_config)
    before = len(_ledger_lines(cli_project))

    import seldon.core.artifacts as artifacts_module
    calls: list[int] = []
    real = artifacts_module.append_events

    def counting(project_path, batch):
        calls.append(len(batch))
        return real(project_path, batch)

    monkeypatch.setattr(artifacts_module, "append_events", counting)
    result = CliRunner().invoke(
        task_group,
        ["create", "--description", "linked probe",
         "--depends-on", res[:8], "--blocks", res[:8]],
    )

    assert result.exit_code == 0, result.output
    assert calls == [3]
    new = [json.loads(line) for line in _ledger_lines(cli_project)[before:]]
    assert [e["event_type"] for e in new] == ["artifact_created", "link_created", "link_created"]
    task_id = new[0]["payload"]["artifact_id"]
    assert {(e["payload"]["from_id"], e["payload"]["rel_type"]) for e in new[1:]} == {
        (task_id, "depends_on"), (task_id, "blocks"),
    }
    with neo4j_driver.session(database=NEO4J_DB) as session:
        rels = session.run(
            "MATCH (t:ResearchTask {artifact_id: $t})-[r]->(x {artifact_id: $x}) "
            "RETURN type(r) AS t ORDER BY t",
            t=task_id, x=res,
        ).value("t")
    assert rels == ["BLOCKS", "DEPENDS_ON"]


def test_a_failure_while_preparing_the_batch_writes_nothing(
    neo4j_driver, cli_project, domain_config, clean_test_db, monkeypatch,
):
    """Both events or neither: a fault after the first event is built leaves no line."""
    res = _result(cli_project, neo4j_driver, domain_config)
    before = _ledger_lines(cli_project)

    import seldon.core.artifacts as artifacts_module
    real = artifacts_module.make_event
    built: list[str] = []

    def failing(event_type, *args, **kwargs):
        built.append(event_type)
        if event_type == "link_created":
            raise RuntimeError("injected fault while building the link event")
        return real(event_type, *args, **kwargs)

    monkeypatch.setattr(artifacts_module, "make_event", failing)
    result = CliRunner().invoke(
        task_group, ["create", "--description", "fault probe", "--depends-on", res],
    )

    assert built == ["artifact_created", "link_created"]
    assert result.exit_code != 0
    assert _ledger_lines(cli_project) == before
    assert _task_count(neo4j_driver, "fault probe") == 0


def test_mcp_create_with_an_unresolvable_blocks_target_writes_nothing(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """The MCP twin used to create the task and only warn about the missing link."""
    from seldon.mcp_server import seldon_task_create

    before = _ledger_lines(cli_project)
    out = seldon_task_create.__wrapped__(
        description="mcp ghost probe", project_dir=str(cli_project), blocks="ffffffff",
    )

    assert out.startswith("Error:")
    assert "Nothing was written" in out
    assert _ledger_lines(cli_project) == before
    assert _task_count(neo4j_driver, "mcp ghost probe") == 0


def test_mcp_create_with_an_illegal_blocks_target_writes_nothing(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    from seldon.mcp_server import seldon_task_create

    other = _task(cli_project, neo4j_driver, domain_config)
    before = _ledger_lines(cli_project)
    out = seldon_task_create.__wrapped__(
        description="mcp illegal probe", project_dir=str(cli_project), blocks=other,
    )

    assert out.startswith("Error:")
    assert "'blocks'" in out and "precedes" in out
    assert _ledger_lines(cli_project) == before
    assert _task_count(neo4j_driver, "mcp illegal probe") == 0


# ── Part B: the error says what was refused, what is legal, and that nothing was made ──

def test_the_error_names_the_relationship_its_legal_targets_and_precedes(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    other = _task(cli_project, neo4j_driver, domain_config)

    result = CliRunner().invoke(
        task_group, ["create", "--description", "text probe", "--depends-on", other[:8]],
    )

    text = result.output
    assert "'depends_on'" in text
    for legal in domain_config.relationship_types["depends_on"].to_types:
        assert legal in text
    assert "precedes" in text
    assert "seldon task precede" in text
    assert "Nothing was written" in text


def test_the_domain_validator_names_the_relationship_a_pair_is_legal_under(domain_config):
    """Every write path gets the hint, `seldon link create` included."""
    from seldon.domain.loader import validate_relationship

    with pytest.raises(ValueError) as exc:
        validate_relationship(domain_config, "depends_on", "ResearchTask", "ResearchTask")
    text = str(exc.value)
    assert "cannot target" in text
    assert "'precedes'" in text
    for legal in domain_config.relationship_types["depends_on"].to_types:
        assert legal in text


# ── Part C: every other command that writes more than one line ────────────────
#
# Each test asserts the command's lines reach the ledger in ONE append_events call
# (the both-or-neither property), and, where a refusal used to land after a write,
# that the refusal now leaves the ledger untouched.

@pytest.fixture
def one_append(monkeypatch):
    """Record the size of every batch handed to the ledger by seldon.core.artifacts."""
    import seldon.core.artifacts as artifacts_module
    calls: list[list[str]] = []
    real = artifacts_module.append_events

    def counting(project_path, batch):
        calls.append([e["event_type"] for e in batch])
        return real(project_path, batch)

    monkeypatch.setattr(artifacts_module, "append_events", counting)
    return calls


def test_task_supersede_writes_reason_state_and_edge_in_one_append(
    neo4j_driver, cli_project, domain_config, clean_test_db, one_append,
):
    old = _task(cli_project, neo4j_driver, domain_config, "old")
    new = _task(cli_project, neo4j_driver, domain_config, "new")
    one_append.clear()

    result = CliRunner().invoke(
        task_group, ["supersede", old[:8], "--reason", "overtaken", "--superseded-by", new[:8]],
    )

    assert result.exit_code == 0, result.output
    assert one_append == [["artifact_updated", "artifact_state_changed", "link_created"]]


def test_task_claim_writes_the_marker_and_the_state_in_one_append(
    neo4j_driver, cli_project, domain_config, clean_test_db, one_append,
):
    from seldon.core.artifacts import transition_task

    tid = _task(cli_project, neo4j_driver, domain_config)
    transition_task(project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
                    domain_config=domain_config, artifact_id=tid, current_state="proposed",
                    new_state="accepted", actor="human")
    one_append.clear()
    transition_task(project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
                    domain_config=domain_config, artifact_id=tid, current_state="accepted",
                    new_state="in_progress", actor="human")

    assert one_append == [["artifact_updated", "artifact_state_changed"]]


def test_task_close_walks_in_one_append(
    neo4j_driver, cli_project, domain_config, clean_test_db, one_append,
):
    tid = _task(cli_project, neo4j_driver, domain_config)
    one_append.clear()

    result = CliRunner().invoke(task_group, ["close", tid[:8]])

    assert result.exit_code == 0, result.output
    assert one_append == [[
        "artifact_state_changed", "artifact_updated", "artifact_state_changed",
        "artifact_state_changed",
    ]]


def test_a_walk_refused_at_its_start_writes_what_was_planned_before_it_neither(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    """`cc complete` on a superseded task used to stamp completed_at, then raise."""
    from seldon.core.artifacts import plan_update_artifact, walk_to_completed

    tid = _task(cli_project, neo4j_driver, domain_config)
    before = _ledger_lines(cli_project)
    stamp = plan_update_artifact(project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
                                 artifact_id=tid, properties={"completed_at": "now"},
                                 actor="cc", authority="accepted")

    with pytest.raises(ValueError):
        walk_to_completed(project_dir=cli_project, driver=neo4j_driver, database=NEO4J_DB,
                          domain_config=domain_config, artifact_id=tid,
                          current_state="superseded", before=[stamp])
    assert _ledger_lines(cli_project) == before


def test_cc_complete_on_a_superseded_task_writes_nothing(
    neo4j_driver, project_dir, clean_test_db, domain_config, monkeypatch,
):
    import subprocess

    from seldon.commands.cc import cc_group
    from seldon.core.artifacts import transition_task
    from seldon.mcp_server import seldon_cc_register

    rel = "cc_tasks/2026-10-21_sel007_probe.md"
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=project_dir, check=True)
    (project_dir / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n")
    (project_dir / "cc_tasks").mkdir()
    (project_dir / rel).write_text("# CC Task: probe\n\n**Implements:** DN-006\n\nA probe.\n")
    out = seldon_cc_register.__wrapped__(filepath=rel, project_dir=str(project_dir),
                                         allow_untracked=True)
    assert "Registered" in out, out
    with neo4j_driver.session(database=NEO4J_DB) as s:
        tid = s.run("MATCH (t:ResearchTask {source_file: $f}) RETURN t.artifact_id AS id",
                    f=rel).single()["id"]
    transition_task(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                    domain_config=domain_config, artifact_id=tid, current_state="proposed",
                    new_state="superseded", actor="human", terminal_reason="probe")
    before = _ledger_lines(project_dir)

    monkeypatch.chdir(project_dir)
    result = CliRunner().invoke(cc_group, ["complete", rel])

    assert result.exit_code == 1, result.output
    assert "Nothing was written" in result.output
    assert _ledger_lines(project_dir) == before


def test_issue_update_refused_transition_leaves_no_property_update(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    from seldon.commands.issue import issue_group

    iid = _make(cli_project, neo4j_driver, domain_config, "Issue", {
        "description": "probe", "issue_type": "citation_gap", "importance": "low",
        "urgency": "low", "detection_method": "audit", "target": "content",
    })
    before = _ledger_lines(cli_project)

    result = CliRunner().invoke(
        issue_group, ["update", iid, "--urgency", "high", "--state", "verified"],
    )

    assert result.exit_code == 1
    assert _ledger_lines(cli_project) == before


def test_mcp_issue_update_refused_enum_leaves_no_state_change(
    neo4j_driver, cli_project, domain_config, clean_test_db,
):
    from seldon.mcp_server import seldon_issue_update

    iid = _make(cli_project, neo4j_driver, domain_config, "Issue", {
        "description": "probe", "issue_type": "citation_gap", "importance": "low",
        "urgency": "low", "detection_method": "audit", "target": "content",
    })
    before = _ledger_lines(cli_project)

    out = seldon_issue_update.__wrapped__(
        issue_id=iid[:8], project_dir=str(cli_project), state="in_progress", urgency="extreme",
    )

    assert out.startswith("Error:"), out
    assert _ledger_lines(cli_project) == before


def test_redrive_writes_its_three_lines_in_one_append(
    tmp_path, neo4j_driver, clean_test_db, domain_config, one_append, monkeypatch,
):
    from tests.test_friction001_redrive import TIDS, _halt
    from tests.test_friction001_redrive import project as redrive_project
    from seldon.core.redrive import redrive

    p = redrive_project.__wrapped__(tmp_path, neo4j_driver, None, monkeypatch, domain_config)
    tid = _halt(p, neo4j_driver, domain_config, "check_failed")
    one_append.clear()

    redrive(p, neo4j_driver, NEO4J_DB, domain_config, tid, actor="human")

    assert one_append == [["artifact_updated", "dispatch_redrive", "artifact_state_changed"]]


def test_task_chain_writes_every_edge_in_one_append(
    neo4j_driver, cli_project, domain_config, clean_test_db, one_append,
):
    a, b, c = (_task(cli_project, neo4j_driver, domain_config, d) for d in "abc")
    one_append.clear()

    result = CliRunner().invoke(task_group, ["chain", a[:8], b[:8], c[:8]])

    assert result.exit_code == 0, result.output
    assert one_append == [["link_created", "link_created"]]


def test_issue_create_writes_the_issue_and_its_affects_links_in_one_append(
    neo4j_driver, cli_project, domain_config, clean_test_db, one_append,
):
    from seldon.commands.issue import issue_group

    section = _make(cli_project, neo4j_driver, domain_config, "PaperSection",
                    {"name": "sel007_section", "title": "A section"})
    one_append.clear()

    result = CliRunner().invoke(issue_group, [
        "create", "--description", "probe", "--type", "citation_gap", "--importance", "low",
        "--urgency", "low", "--detection", "audit", "--target", "content", "--affects", section,
    ])

    assert result.exit_code == 0, result.output
    assert one_append == [["artifact_created", "link_created"]]


def test_prune_resolves_an_issue_with_its_note_in_one_append(owner, one_append):
    from tests.test_prune001 import NOW, _issue, run_prune

    _issue(owner, "S-099 defect 1, FIXED with its test (tests/test_x.py).")
    one_append.clear()

    run_prune(owner["repo"], now=NOW, echo=lambda s: None)

    assert ["artifact_updated", "artifact_state_changed"] in one_append
