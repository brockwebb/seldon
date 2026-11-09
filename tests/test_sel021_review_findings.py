"""SEL-021: review findings are Issues, traced to their fix, their test and the decisions they change.

`cc_tasks/2026-11-01_SEL-021_review_findings_are_issues_traced_to_fix_test_and_decision.md`; factory F-010 and F-011.
SQ-105R fixed 14 of 15 squiddy review findings and rejected one, and none of it was in a graph as finding, fix, test
and changed decision.

A. The Issue type admits review findings: `review_finding`, `review`, `found_in`, `severity`, `disposition`,
   `disposition_evidence`; edges `remediated_by` (existing), `verified_by`, `changes`. Additive only.
B. `seldon issue orphans` (CLI and MCP) lists findings with neither a finished fix plus a test nor an evidenced
   disposition, and the CLI exits nonzero when there is one.
C. The optional `**Found in:**` task header is parsed at registration onto the ResearchTask; an unparsable value
   refuses with the grammar quoted.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.cc import register_task_file
from seldon.commands.issue import issue_group
from seldon.core import dispatch as D
from seldon.core import review_findings as RF
from seldon.core.artifacts import create_artifact, create_link, walk_to_completed
from seldon.core.events import EVENTS_FILENAME, read_events
from seldon.core.issue_utils import ISSUE_ENUMS
from seldon.domain.loader import load_domain_config
from tests.test_sel007_atomic_multi_event import one_append  # noqa: F401  (fixture)
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
FOUND_IN = "factory:reviews/squiddy_code_review_max_findings.md#3"
TEST_FILE = "tests/test_fix.py"
TEST_REF = f"{TEST_FILE}::test_the_fix_holds"
DECISION_ID = "test:AD-900-R1"

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

# The Issue properties every Issue written before SEL-021 carries: the additive check creates one with only these.
PRE_SEL021_ISSUE = {"description": "probe", "issue_type": "citation_gap", "importance": "low", "urgency": "low",
                    "detection_method": "audit", "target": "content"}


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def cli_project(project_dir, monkeypatch):
    """A project whose seldon.yaml points at the test database, with one test file; the CLI reads it from cwd."""
    (project_dir / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n")
    (project_dir / "tests").mkdir()
    (project_dir / TEST_FILE).write_text("def test_the_fix_holds():\n    assert True\n")
    monkeypatch.chdir(project_dir)
    return project_dir


def _make(project_dir, driver, dc, artifact_type, properties):
    return create_artifact(project_dir=project_dir, driver=driver, database=NEO4J_DB, domain_config=dc,
                           artifact_type=artifact_type, properties=properties, actor="human", authority="accepted")


def _task(project_dir, driver, dc, name="2026-11-01_SEL-900_fix", completed=False):
    tid = _make(project_dir, driver, dc, "ResearchTask",
                {"description": "the fix", "name": name, "source_file": f"cc_tasks/{name}.md"})
    if completed:
        walk_to_completed(project_dir=project_dir, driver=driver, database=NEO4J_DB, domain_config=dc,
                          artifact_id=tid, current_state="proposed", session_id=None)
    return tid


def _decision(project_dir, driver, dc):
    return _make(project_dir, driver, dc, "Decision",
                 {"name": DECISION_ID, "decision_id": DECISION_ID, "home_repository": "test"})


def _finding(project_dir, driver, dc, **props):
    """A review finding planted straight into the graph, past the write boundary's checks."""
    return _make(project_dir, driver, dc, "Issue", {
        "description": "a finding", "issue_type": "review_finding", "importance": "medium", "urgency": "medium",
        "detection_method": "review", "target": "code", "found_in": FOUND_IN, **props})


def _link(project_dir, driver, dc, from_id, to_id, to_type, rel):
    create_link(project_dir=project_dir, driver=driver, database=NEO4J_DB, domain_config=dc, from_id=from_id,
                to_id=to_id, from_type="Issue", to_type=to_type, rel_type=rel, actor="human", authority="accepted")


def _test_script(project_dir, driver, dc):
    return _make(project_dir, driver, dc, "Script", {"name": TEST_REF, "path": TEST_FILE, "test_node": TEST_REF})


def _ledger(project_dir) -> list[str]:
    path = Path(project_dir) / EVENTS_FILENAME
    return path.read_text().splitlines() if path.exists() else []


def _edges(driver, issue_id) -> list[tuple]:
    with driver.session(database=NEO4J_DB) as s:
        return sorted((r["rel"], r["type"]) for r in s.run(
            "MATCH (i:Artifact:Issue {artifact_id: $id})-[r]->(t:Artifact) RETURN type(r) AS rel, "
            "t.artifact_type AS type", id=issue_id).data())


# ══════════════════════════════════════════════════════════════════════════════
# Part A: the schema, additive
# ══════════════════════════════════════════════════════════════════════════════

def test_the_issue_enums_admit_a_review_finding():
    assert "review_finding" in ISSUE_ENUMS["issue_type"]
    assert "review" in ISSUE_ENUMS["detection_method"]
    assert "code" in ISSUE_ENUMS["target"]
    assert ISSUE_ENUMS["disposition"] == ["fixed", "rejected", "duplicate", "wont_fix"]


def test_the_domain_declares_the_trace_edges_and_optional_properties(domain_config):
    rels = domain_config.relationship_types
    # SEL-033 (AD-013-R1) widened the origin to SRS_Requirement; an Issue still verifies only against a Script.
    assert rels["verified_by"].from_types == ["Issue", "SRS_Requirement"] and rels["verified_by"].to_types == ["Script"]
    assert rels["changes"].from_types == ["Issue"]
    assert set(rels["changes"].to_types) == {"Decision", "ArchitecturalDecision"}
    assert "ResearchTask" in rels["remediated_by"].to_types
    # Additive: the required set is what it was before SEL-021, so every existing Issue still loads.
    assert set(domain_config.get_required_properties("Issue")) == set(PRE_SEL021_ISSUE)
    issue_props = domain_config.artifact_types["Issue"].properties
    for new in ("found_in", "severity", "disposition", "disposition_evidence"):
        assert issue_props[new].category == "system", new
    assert domain_config.artifact_types["ResearchTask"].properties["found_in"].category == "system"
    assert domain_config.artifact_types["Script"].properties["test_node"].category == "system"


@neo4j_tests
def test_an_issue_with_only_the_pre_sel021_properties_still_loads(neo4j_driver, project_dir, domain_config):
    iid = _make(project_dir, neo4j_driver, domain_config, "Issue", PRE_SEL021_ISSUE)
    with neo4j_driver.session(database=NEO4J_DB) as s:
        node = s.run("MATCH (i:Artifact:Issue {artifact_id: $id}) RETURN i", id=iid).single()["i"]
    assert node["state"] == "open" and node.get("found_in") is None


@pytest.mark.parametrize("value", [FOUND_IN, f"`{FOUND_IN}`", "hazbrief-mcp:reviews/2026-10-31.md#F-7.",
                                   "squiddy:cc_tasks/2026-10-30_SQ-105R_x_RESULT.md#finding-15"])
def test_the_found_in_grammar_parses(value):
    parsed = RF.parse_found_in(value)
    assert parsed["value"].count(":") == 1 and "#" in parsed["value"]


@pytest.mark.parametrize("bad", ["", "reviews/x.md#3", "factory:reviews/x.md", "factory:reviews/x.md#",
                                 ":reviews/x.md#3", "factory:reviews/a b.md#3", "factory:x.md#3#4"])
def test_a_found_in_that_does_not_parse_is_refused_with_the_grammar(bad):
    with pytest.raises(ValueError, match="<repo>:<path>#<finding id>"):
        RF.parse_found_in(bad)


def test_a_test_reference_must_parse_and_name_a_file_in_the_project(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / TEST_FILE).write_text("")
    assert RF.parse_test_ref(TEST_REF, tmp_path)["node"] == "test_the_fix_holds"
    assert RF.parse_test_ref(f"{TEST_FILE}::TestX::test_y[a-b]", tmp_path)["path"] == TEST_FILE
    for bad, match in [(TEST_FILE, "path>::<node id"), ("tests/missing.py::test_x", "not a file"),
                       ("../x.py::test_x", "relative to the project root")]:
        with pytest.raises(ValueError, match=match):
            RF.parse_test_ref(bad, tmp_path)


def test_the_review_property_rules():
    rp = RF.review_properties
    with pytest.raises(ValueError, match="needs found_in"):
        rp(issue_type="review_finding", found_in=None, severity=None, disposition=None, disposition_evidence=None)
    with pytest.raises(ValueError, match="needs disposition_evidence"):
        rp(issue_type="review_finding", found_in=FOUND_IN, severity=None, disposition="rejected",
           disposition_evidence="  ")
    with pytest.raises(ValueError, match="Invalid disposition"):
        rp(issue_type="review_finding", found_in=FOUND_IN, severity=None, disposition="ignored",
           disposition_evidence="x")
    with pytest.raises(ValueError, match="no disposition"):
        rp(issue_type="review_finding", found_in=FOUND_IN, severity=None, disposition=None,
           disposition_evidence="because")
    assert rp(issue_type="review_finding", found_in=FOUND_IN, severity="P1", disposition="fixed",
              disposition_evidence=None) == {"found_in": FOUND_IN, "severity": "P1", "disposition": "fixed"}
    # An update that adds evidence to a disposition already on the Issue is enough.
    assert rp(issue_type="review_finding", found_in=None, severity=None, disposition=None,
              disposition_evidence="RESULT section 4", existing={"found_in": FOUND_IN, "disposition": "rejected"}
              ) == {"disposition_evidence": "RESULT section 4"}
    # A document Issue needs none of it.
    assert rp(issue_type="citation_gap", found_in=None, severity=None, disposition=None,
              disposition_evidence=None) == {}


@neo4j_tests
def test_cli_create_files_a_finding_with_its_fix_test_and_decision_in_one_append(
        neo4j_driver, cli_project, domain_config, one_append):
    tid = _task(cli_project, neo4j_driver, domain_config)
    _decision(cli_project, neo4j_driver, domain_config)
    one_append.clear()

    result = CliRunner().invoke(issue_group, [
        "create", "--description", "the parser drops a row", "--type", "review_finding", "--importance", "high",
        "--urgency", "medium", "--detection", "review", "--target", "code", "--found-in", FOUND_IN,
        "--severity", "P1", "--disposition", "fixed", "--remediated-by", tid[:8], "--verified-by", TEST_REF,
        "--changes", DECISION_ID])

    assert result.exit_code == 0, result.output
    assert f"found_in: {FOUND_IN}" in result.output
    # The Issue, the Script standing for the test, and three links: one ledger write.
    assert one_append == [["artifact_created", "link_created", "artifact_created", "link_created", "link_created"]]
    issue_id = result.output.split("Created Issue: ")[1].split()[0]
    assert _edges(neo4j_driver, issue_id) == [("CHANGES", "Decision"), ("REMEDIATED_BY", "ResearchTask"),
                                              ("VERIFIED_BY", "Script")]
    # A second finding verified by the same test reuses its Script.
    again = CliRunner().invoke(issue_group, [
        "create", "--description", "another", "--type", "review_finding", "--importance", "low", "--urgency", "low",
        "--detection", "review", "--target", "code", "--found-in", FOUND_IN.replace("#3", "#4"),
        "--verified-by", TEST_REF])
    assert again.exit_code == 0, again.output
    with neo4j_driver.session(database=NEO4J_DB) as s:
        assert s.run("MATCH (s:Artifact:Script {test_node: $t}) RETURN count(s) AS n", t=TEST_REF).single()["n"] == 1
    shown = CliRunner().invoke(issue_group, ["show", issue_id])
    assert "VERIFIED_BY [Script] " + TEST_REF in shown.output and "found_in:" in shown.output


@neo4j_tests
@pytest.mark.parametrize("extra, match", [
    ([], "needs found_in"),
    (["--found-in", FOUND_IN, "--verified-by", "tests/missing.py::test_x"], "not a file"),
    (["--found-in", FOUND_IN, "--remediated-by", "no-such-task"], "names no ResearchTask"),
    (["--found-in", FOUND_IN, "--changes", "test:AD-999"], "names no decision record"),
    (["--found-in", FOUND_IN, "--disposition", "rejected"], "needs disposition_evidence"),
])
def test_cli_create_refuses_a_bad_finding_and_writes_nothing(neo4j_driver, cli_project, domain_config, extra, match):
    before = _ledger(cli_project)
    result = CliRunner().invoke(issue_group, [
        "create", "--description", "x", "--type", "review_finding", "--importance", "low", "--urgency", "low",
        "--detection", "review", "--target", "code", *extra])
    assert result.exit_code == 1 and match in result.output, result.output
    assert _ledger(cli_project) == before


@neo4j_tests
def test_cli_update_records_a_disposition_and_links_after_the_fact(neo4j_driver, cli_project, domain_config):
    iid = _finding(cli_project, neo4j_driver, domain_config)
    tid = _task(cli_project, neo4j_driver, domain_config)
    refused = CliRunner().invoke(issue_group, ["update", iid, "--disposition", "wont_fix"])
    assert refused.exit_code == 1 and "needs disposition_evidence" in refused.output

    ok = CliRunner().invoke(issue_group, ["update", iid, "--disposition", "fixed", "--remediated-by", tid,
                                          "--verified-by", TEST_REF])
    assert ok.exit_code == 0, ok.output
    assert _edges(neo4j_driver, iid) == [("REMEDIATED_BY", "ResearchTask"), ("VERIFIED_BY", "Script")]


@neo4j_tests
def test_mcp_create_files_a_finding_and_says_review_findings_are_issues(neo4j_driver, cli_project, domain_config):
    from seldon.mcp_server import RAW_TOOLS, seldon_issue_create

    doc = RAW_TOOLS["seldon_issue_create"].__doc__
    assert "NOT for software bugs" not in doc and "review finding" in doc
    tid = _task(cli_project, neo4j_driver, domain_config)
    out = seldon_issue_create.__wrapped__(
        name="F-3", description="the parser drops a row", issue_type="review_finding", detection_method="review",
        target="code", project_dir=str(cli_project), found_in=FOUND_IN, severity="high", disposition="fixed",
        remediated_by=[tid[:8]], verified_by=[TEST_REF])
    assert out.startswith("Created Issue"), out
    with neo4j_driver.session(database=NEO4J_DB) as s:
        node = s.run("MATCH (i:Artifact:Issue {name: 'F-3'}) RETURN i").single()["i"]
    assert node["found_in"] == FOUND_IN and node["severity"] == "high"
    assert _edges(neo4j_driver, node["artifact_id"]) == [("REMEDIATED_BY", "ResearchTask"),
                                                         ("VERIFIED_BY", "Script")]
    before = _ledger(cli_project)
    refused = seldon_issue_create.__wrapped__(
        name="F-4", description="x", issue_type="review_finding", detection_method="review", target="code",
        project_dir=str(cli_project), found_in=FOUND_IN, verified_by=["tests/missing.py::test_x"])
    assert refused.startswith("Error:") and "Nothing was written" in refused
    assert _ledger(cli_project) == before


@neo4j_tests
def test_mcp_update_records_a_rejection_with_its_evidence(neo4j_driver, cli_project, domain_config):
    from seldon.mcp_server import seldon_issue_update

    iid = _finding(cli_project, neo4j_driver, domain_config)
    refused = seldon_issue_update.__wrapped__(issue_id=iid[:8], project_dir=str(cli_project), disposition="rejected")
    assert refused.startswith("Error:") and "disposition_evidence" in refused
    ok = seldon_issue_update.__wrapped__(issue_id=iid[:8], project_dir=str(cli_project), disposition="rejected",
                                         disposition_evidence="SQ-105R RESULT section 6: the reviewer misread R-88")
    assert "disposition: rejected" in ok, ok


# ══════════════════════════════════════════════════════════════════════════════
# Part B: seldon issue orphans
# ══════════════════════════════════════════════════════════════════════════════

def _passing_pair(p, driver, dc):
    """A fixed finding with a completed task and a test, and a rejected finding with evidence."""
    fixed = _finding(p, driver, dc, disposition="fixed")
    _link(p, driver, dc, fixed, _task(p, driver, dc, completed=True), "ResearchTask", "remediated_by")
    _link(p, driver, dc, fixed, _test_script(p, driver, dc), "Script", "verified_by")
    _finding(p, driver, dc, disposition="rejected", disposition_evidence="SQ-105R RESULT section 6")
    return fixed


@neo4j_tests
def test_a_fixed_finding_with_task_and_test_and_a_rejected_one_with_evidence_pass(
        neo4j_driver, cli_project, domain_config):
    _passing_pair(cli_project, neo4j_driver, domain_config)
    # A document Issue is not a review finding and is never an orphan.
    _make(cli_project, neo4j_driver, domain_config, "Issue", PRE_SEL021_ISSUE)

    assert RF.orphans(neo4j_driver, NEO4J_DB) == []
    result = CliRunner().invoke(issue_group, ["orphans"])
    assert result.exit_code == 0, result.output
    assert result.output.strip().endswith("orphans: 0")


@neo4j_tests
def test_a_planted_finding_with_only_a_task_fails(neo4j_driver, cli_project, domain_config):
    _passing_pair(cli_project, neo4j_driver, domain_config)
    planted = _finding(cli_project, neo4j_driver, domain_config, disposition="fixed")
    _link(cli_project, neo4j_driver, domain_config, planted,
          _task(cli_project, neo4j_driver, domain_config, name="2026-11-01_SEL-901_fix", completed=True),
          "ResearchTask", "remediated_by")

    rows = RF.orphans(neo4j_driver, NEO4J_DB)
    assert [r["id"] for r in rows] == [planted] and rows[0]["reasons"] == ["no VERIFIED_BY test"]
    result = CliRunner().invoke(issue_group, ["orphans"])
    assert result.exit_code == 1 and "orphans: 1" in result.output
    as_json = CliRunner().invoke(issue_group, ["orphans", "--json"])
    assert as_json.exit_code == 1 and json.loads(as_json.output)[0]["id"] == planted


@neo4j_tests
def test_a_planted_rejected_finding_with_empty_evidence_fails(neo4j_driver, cli_project, domain_config):
    _passing_pair(cli_project, neo4j_driver, domain_config)
    planted = _finding(cli_project, neo4j_driver, domain_config, disposition="rejected", disposition_evidence=" ")

    rows = RF.orphans(neo4j_driver, NEO4J_DB)
    assert [r["id"] for r in rows] == [planted]
    assert rows[0]["reasons"] == ["disposition rejected has no evidence"]
    assert CliRunner().invoke(issue_group, ["orphans"]).exit_code == 1


@neo4j_tests
def test_an_unfinished_fix_task_and_a_bare_finding_are_orphans(neo4j_driver, cli_project, domain_config):
    open_fix = _finding(cli_project, neo4j_driver, domain_config)
    _link(cli_project, neo4j_driver, domain_config, open_fix, _task(cli_project, neo4j_driver, domain_config),
          "ResearchTask", "remediated_by")
    _link(cli_project, neo4j_driver, domain_config, open_fix, _test_script(cli_project, neo4j_driver, domain_config),
          "Script", "verified_by")
    bare = _finding(cli_project, neo4j_driver, domain_config)

    reasons = {r["id"]: r["reasons"] for r in RF.orphans(neo4j_driver, NEO4J_DB)}
    assert reasons == {open_fix: ["fix task not completed (proposed)"],
                       bare: ["no REMEDIATED_BY task", "no VERIFIED_BY test"]}


@neo4j_tests
def test_mcp_orphans_reports_the_count(neo4j_driver, cli_project, domain_config):
    from seldon.mcp_server import seldon_issue_orphans

    _finding(cli_project, neo4j_driver, domain_config)
    out = seldon_issue_orphans.__wrapped__(project_dir=str(cli_project))
    assert out.strip().endswith("orphans: 1") and FOUND_IN in out


# ══════════════════════════════════════════════════════════════════════════════
# Part C: the **Found in:** task header
# ══════════════════════════════════════════════════════════════════════════════

def _task_body(found_in: str | None) -> str:
    header = f"**Found in:** {found_in}\n" if found_in is not None else ""
    return (f"# SEL-902: fix a review finding\n\n**Spend:** zero.\n**Network:** none.\n**After:** none\n{header}\n"
            f"## 1. Fix it.\n")


def test_the_static_checks_read_the_found_in_header(tmp_path):
    f = tmp_path / "t.md"
    f.write_text(_task_body(f"`{FOUND_IN}`"), encoding="utf-8")
    assert D.static_checks(f, None)["failures"] == []
    f.write_text(_task_body(None), encoding="utf-8")
    assert D.static_checks(f, None)["failures"] == []
    f.write_text(_task_body("squiddy review finding 3"), encoding="utf-8")
    failures = D.static_checks(f, None)["failures"]
    assert [x["code"] for x in failures] == [RF.FOUND_IN_UNPARSABLE]
    assert RF.FOUND_IN_GRAMMAR in failures[0]["message"]


@neo4j_tests
def test_registration_records_a_valid_found_in_and_refuses_an_invalid_one(
        neo4j_driver, tmp_path, monkeypatch, domain_config):
    from tests.test_sel013r_answers_files_its_return import _config, _repo

    p = _repo(tmp_path / "producer", "producer", TEST_DATABASE)
    monkeypatch.chdir(p)
    good = p / "cc_tasks" / "2026-11-01_SEL-902_fix_a_review_finding.md"
    good.write_text(_task_body(FOUND_IN), encoding="utf-8")
    out = register_task_file(project_dir=p, config=_config(p), driver=neo4j_driver, database=TEST_DATABASE,
                             domain_config=domain_config, session_id=None, task_path=good, actor="cc",
                             allow_untracked=True)
    created = [e for e in read_events(p) if e["event_type"] == "artifact_created"
               and e["payload"]["artifact_id"] == out["artifact_id"]]
    assert created[0]["payload"]["properties"]["found_in"] == FOUND_IN

    bad = p / "cc_tasks" / "2026-11-01_SEL-903_fix_another_finding.md"
    bad.write_text(_task_body("factory:reviews/x.md"), encoding="utf-8")
    before = (p / "seldon_events.jsonl").read_bytes()
    with pytest.raises(ValueError, match=RF.FOUND_IN_UNPARSABLE) as exc:
        register_task_file(project_dir=p, config=_config(p), driver=neo4j_driver, database=TEST_DATABASE,
                           domain_config=domain_config, session_id=None, task_path=bad, actor="cc",
                           allow_untracked=True)
    assert "<repo>:<path>#<finding id>" in str(exc.value)
    assert (p / "seldon_events.jsonl").read_bytes() == before
