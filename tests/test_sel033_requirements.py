"""SEL-033 Parts B and C (AD-013-R1 to R3): requirements live in the graph; the table and the RTM are projections.

hazbrief-mcp kept 149 view requirements and its RTM as markdown the graph knew only by hash, and a "four-place
ratchet" kept one counts sentence identical by hand (its filing SEL-032). Here:

B. `seldon req import` loads a markdown table into `SRS_Requirement` nodes, idempotent on the id, with
   `derived_from` (its source), `verified_by` (a test Script) and `satisfies` (the task its status names), and lists
   what did not resolve; `seldon req add` writes one.
C. `seldon docs generate requirements|rtm` renders the declared projections into their marker blocks from the graph,
   stamps the graph revision and commits; `docs check` and `verify` report unverified requirements and stale
   projections.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.docs import docs_group
from seldon.commands.req import req_group
from seldon.commands.verify import TIER_A_CHECKS, check_requirements
from seldon.core import requirements as RQ
from seldon.core.artifacts import create_artifact
from seldon.core.events import EVENTS_FILENAME, read_events
from seldon.domain.loader import load_domain_config
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

STATUS_MAP = {"satisfied": "verified", "changed": "verified", "open": "accepted", "withdrawn": "rejected"}
TASK_FILE = "cc_tasks/2026-11-01_HB-900_the_map.md"

SOURCE = """# View requirements

Prose the projection must keep: the TEVV reading.

## Set-by keys

| Key | File |
|---|---|
| DN-019 | `docs/design/DN-019.md` |
| HB-900 | `cc_tasks/2026-11-01_HB-900_the_map.md` |

## The views

### The map

| ID | Requirement | Set by | Verified by | Validated by | Status |
|---|---|---|---|---|---|
| VR-001 | The map is first. | DN-019 §1 | tests/test_map.py::test_first; tests/test_map.py::test_order | — | satisfied: HB-900 |
| VR-002 | The map spans the page. | DN-019 §1; DN-404 §2 | none yet | — | open: the panel shares the row |

More prose between the tables.

### The legend

| ID | Requirement | Set by | Verified by | Validated by | Status |
|---|---|---|---|---|---|
| VR-003 | The legend names the wind. | HB-900 §A | none yet | — | satisfied |
| VR-004 | The legend floats. | DN-019 §4 | none yet | — | withdrawn: VR-003 replaces it |

The table at HB-900: COUNTS.
"""
COUNTS = '4 rows: 2 satisfied, 1 open, 0 changed, 1 withdrawn; 3 verified by "none yet"'
TEMPLATE = ('{total} rows: {status:satisfied} satisfied, {status:open} open, {status:changed} changed, '
            '{status:withdrawn} withdrawn; {unverified} verified by "none yet"')


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _config(projections=None) -> dict:
    cfg = {"project": {"name": "test", "domain": "research"},
           "neo4j": {"database": NEO4J_DB, "uri": "bolt://localhost:7687"},
           "event_store": {"path": "seldon_events.jsonl"},
           "requirements": {"status_map": STATUS_MAP, "counts_template": TEMPLATE}}
    if projections is not None:
        cfg["docs"] = {"projections": projections}
    return cfg


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def req_project(project_dir, monkeypatch, tmp_path):
    """A git repository with seldon.yaml, a test file, a design note and the source table, committed."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    (tmp_path / "gitconfig").write_text("[user]\n\tname = t\n\temail = t@t\n")
    (project_dir / "seldon.yaml").write_text(yaml.safe_dump(_config([{"path": "docs/VR.md",
                                                                       "kind": "requirements"}])))
    (project_dir / "tests").mkdir()
    (project_dir / "tests" / "test_map.py").write_text("def test_first():\n    pass\n\ndef test_order():\n    pass\n")
    (project_dir / "docs" / "design").mkdir(parents=True)
    (project_dir / "docs" / "design" / "DN-019.md").write_text("# DN-019\n")
    (project_dir / "docs" / "VR.md").write_text(SOURCE)
    (project_dir / "cc_tasks").mkdir()
    (project_dir / TASK_FILE).write_text("# HB-900\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(project_dir)], check=True)
    _git(project_dir, "add", "-A")
    _git(project_dir, "commit", "-q", "-m", "init")
    monkeypatch.chdir(project_dir)
    return project_dir


def _task(project_dir, driver, dc):
    return create_artifact(project_dir=project_dir, driver=driver, database=NEO4J_DB, domain_config=dc,
                           artifact_type="ResearchTask",
                           properties={"description": "the map", "name": "HB-900 the map", "source_file": TASK_FILE},
                           actor="human", authority="accepted")


def _note(project_dir, driver, dc):
    return create_artifact(project_dir=project_dir, driver=driver, database=NEO4J_DB, domain_config=dc,
                           artifact_type="Document", properties={"name": "DN-019", "path": "docs/design/DN-019.md", "content_hash": "0" * 64},
                           actor="human", authority="accepted")


def _import(project_dir, driver, dc, rel="docs/VR.md", **kw):
    cfg = yaml.safe_load((project_dir / "seldon.yaml").read_text())
    return RQ.import_file(project_dir, driver, NEO4J_DB, dc, cfg, rel, **kw)


def _node(driver, rid):
    with driver.session(database=NEO4J_DB) as s:
        return RQ.find_requirement(s, rid)


def _edges(driver, rid):
    with driver.session(database=NEO4J_DB) as s:
        return s.run("MATCH (r:SRS_Requirement {requirement_id: $r})-[e]-(o) "
                     "RETURN type(e) AS t, coalesce(o.test_node, o.name, o.path) AS o ORDER BY t, o", r=rid).data()


# ─────────────────────────────────────────────────────────── pure readers


class TestReaders:
    def test_the_source_parses_its_tables_sections_and_key_map(self, tmp_path):
        (tmp_path / "VR.md").write_text(SOURCE)
        src = RQ.read_source(tmp_path, "VR.md", RQ.settings({}).columns)
        assert [r.requirement_id for r in src.rows] == ["VR-001", "VR-002", "VR-003", "VR-004"]
        assert [r.section for r in src.rows] == ["The map", "The map", "The legend", "The legend"]
        assert src.keys == {"DN-019": "docs/design/DN-019.md", "HB-900": TASK_FILE}
        assert len(src.req_tables) == 2, "the key table is not a requirements table"
        assert src.rows[1].fields["status"] == "open: the panel shares the row"

    def test_a_repeated_id_is_refused(self, tmp_path):
        (tmp_path / "VR.md").write_text(SOURCE.replace("VR-002", "VR-001"))
        with pytest.raises(RQ.RequirementsError, match="repeated"):
            RQ.read_source(tmp_path, "VR.md", RQ.settings({}).columns)

    def test_a_file_with_no_requirements_table_is_refused(self, tmp_path):
        (tmp_path / "x.md").write_text("| a | b |\n|---|---|\n| 1 | 2 |\n")
        with pytest.raises(RQ.RequirementsError, match="no requirements table"):
            RQ.read_source(tmp_path, "x.md", RQ.settings({}).columns)

    def test_the_status_word_is_the_longest_whole_word_prefix(self):
        m = {"met": "verified", "not met": "accepted", "not met (ruled out)": "rejected", "partial": "accepted"}
        assert RQ.status_word("not met (ruled out): DN-002", m) == "not met (ruled out)"
        assert RQ.status_word("not met: no base rate", m) == "not met"
        assert RQ.status_word("met (HB-34; was partial)", m) == "met"
        assert RQ.status_word("metadata only", m) is None
        assert RQ.status_word("Partial (HB-95)", m) == "partial"

    def test_the_three_test_reference_forms(self, tmp_path):
        (tmp_path / "tests").mkdir()
        for f in ("test_a.py", "test_b.py", "test_c.py"):
            (tmp_path / "tests" / f).write_text("")
        cell = ("tests/test_a.py::test_x; `tests/test_b.py` `test_y`, `test_z`; `tests/test_c.py` (round trip); "
                "harness A part 4; tests/test_gone.py::test_q")
        refs, missing = RQ.test_refs(cell, tmp_path)
        assert refs == ["tests/test_a.py::test_x", "tests/test_b.py::test_y", "tests/test_b.py::test_z",
                        "tests/test_c.py"]
        assert missing == ["tests/test_gone.py::test_q"]
        assert RQ.test_refs("none yet", tmp_path) == ([], [])

    def test_a_rendered_row_reproduces_its_source_cells(self):
        s = RQ.settings({})
        nodes = [{"a": "x \\| y", "b": "`p|q`"}]
        out = RQ.render_table(nodes, [{"header": "A", "source": "a"}, {"header": "B", "source": "b"}], s)
        assert out.splitlines()[2] == "| x \\| y | `p\\|q` |"

    def test_a_block_selects_its_columns_by_header_label(self):
        """One RTM file whose tables differ in columns (HB-144's Decision column on the design-note tables only):
        the start marker's `headers` pick the projection's columns by label, in the table's order."""
        cols = [{"header": "ID", "source": "requirement_id"}, {"header": "Decision", "source": "decision_text"},
                {"header": "Requirement", "source": "description"}, {"header": "Criterion", "source": "description"}]
        got = RQ.block_columns("RTM.md", "GSA", "ID|Criterion", cols)
        assert got == [{"header": "ID", "source": "requirement_id"}, {"header": "Criterion", "source": "description"}]
        assert RQ.block_columns("RTM.md", "x", None, cols) == cols
        with pytest.raises(RQ.RequirementsError, match="'Owner' the projection declares no source"):
            RQ.block_columns("RTM.md", "x", "ID|Owner", cols)

    def test_settings_refuse_an_unknown_key(self):
        with pytest.raises(RQ.RequirementsError, match="unknown key"):
            RQ.settings({"requirements": {"status_mapp": {}}})
        with pytest.raises(RQ.RequirementsError, match="kind"):
            RQ.settings({"docs": {"projections": [{"path": "x.md", "kind": "matrix"}]}})

    def test_the_state_walk_is_the_machine(self, domain_config):
        m = domain_config.state_machines["SRS_Requirement"]
        assert RQ.state_path(m, "proposed", "verified") == ["accepted", "implemented", "verified"]
        assert RQ.state_path(m, "verified", "accepted") == ["stale", "accepted"]
        assert RQ.state_path(m, "accepted", "rejected") == ["rejected"]
        assert RQ.state_path(m, "rejected", "accepted") is None


# ─────────────────────────────────────────────────────────── Part B: the load


@neo4j_tests
class TestImport:
    def test_the_import_creates_each_requirement_with_its_trace_and_state(self, req_project, neo4j_driver,
                                                                          domain_config):
        _task(req_project, neo4j_driver, domain_config)
        _note(req_project, neo4j_driver, domain_config)
        plan, _ = _import(req_project, neo4j_driver, domain_config)
        assert sorted(plan.created) == ["VR-001", "VR-002", "VR-003", "VR-004"]
        assert plan.tests_created == 2
        # VR-002's second source names no artifact, and is listed, not dropped (AD-013-R1)
        assert len(plan.unresolved) == 1 and "DN-404" in plan.unresolved[0] and "VR-002" in plan.unresolved[0]

        n1 = _node(neo4j_driver, "VR-001")
        assert n1["state"] == "verified"
        assert n1["description"] == "The map is first."
        assert n1["document"] == "docs/VR.md" and n1["section"] == "The map"
        assert _edges(neo4j_driver, "VR-001") == [
            {"t": "DERIVED_FROM", "o": "DN-019"},
            {"t": "SATISFIES", "o": "HB-900 the map"},
            {"t": "VERIFIED_BY", "o": "tests/test_map.py::test_first"},
            {"t": "VERIFIED_BY", "o": "tests/test_map.py::test_order"},
        ], "its source, the task its status names, and its two tests"
        assert _node(neo4j_driver, "VR-002")["state"] == "accepted"
        # satisfied with no test is held at implemented: verified needs a verified_by edge (AD-013-R1)
        assert _node(neo4j_driver, "VR-003")["state"] == "implemented"
        assert [e["t"] for e in _edges(neo4j_driver, "VR-003")] == ["DERIVED_FROM"], "HB-900 is VR-003's source"
        assert _node(neo4j_driver, "VR-004")["state"] == "rejected"

    def test_a_decision_column_links_each_projected_record(self, req_project, neo4j_driver, domain_config):
        """hazbrief-mcp HB-144 adds a `Decision` column of register ids to its RTM: each id that names a projected
        `Decision` is a `derived_from` edge, so the graph answers "which requirements does decision Y constrain"
        (SEL-032); an id with no projected record is listed."""
        create_artifact(project_dir=req_project, driver=neo4j_driver, database=NEO4J_DB, domain_config=domain_config,
                        artifact_type="Decision", properties={"name": "HBD-002", "decision_id": "hb:HBD-002",
                                                              "home_repository": "hb"},
                        actor="human", authority="accepted")
        (req_project / "docs" / "RTM.md").write_text(
            "## DN-001 section 3\n\n| ID | Decision | Requirement | Satisfied by | Checked by | State |\n"
            "|---|---|---|---|---|---|\n"
            "| S3-1 | HBD-002, HBD-404 | Four classes | `packs/x.json` | `tests/test_map.py` `test_first` | met |\n")
        plan, _ = _import(req_project, neo4j_driver, domain_config, rel="docs/RTM.md")
        assert [u for u in plan.unresolved if "decision" in u] == [
            "docs/RTM.md:5 S3-1: decision 'HBD-404' names no projected register record (run `seldon decision "
            "project`)"]
        n = _node(neo4j_driver, "S3-1")
        assert n["decision_text"] == "HBD-002, HBD-404" and n["satisfied_by_text"] == "`packs/x.json`"
        assert {"t": "DERIVED_FROM", "o": "HBD-002"} in _edges(neo4j_driver, "S3-1")
        assert {"t": "VERIFIED_BY", "o": "tests/test_map.py::test_first"} in _edges(neo4j_driver, "S3-1")
        cols = [{"header": h, "source": s} for h, s in (("ID", "requirement_id"), ("Decision", "decision_text"),
                ("Requirement", "description"), ("Satisfied by", "satisfied_by_text"),
                ("Checked by", "verified_by_text"), ("State", "status_text"))]
        nodes = RQ.load_requirements(neo4j_driver, NEO4J_DB)
        assert RQ.render_table(nodes, cols, RQ.settings({})).splitlines()[2] == (
            "| S3-1 | HBD-002, HBD-404 | Four classes | `packs/x.json` | `tests/test_map.py` `test_first` | met |")

    def test_a_source_with_no_artifact_is_listed_per_row(self, req_project, neo4j_driver, domain_config):
        plan, _ = _import(req_project, neo4j_driver, domain_config)
        listed = [u.split(": ", 1)[0].split()[-1] + " " + u.split("set_by ")[1].split()[0] for u in plan.unresolved]
        assert listed == ["VR-001 'DN-019'", "VR-002 'DN-019'", "VR-002 'DN-404'", "VR-003 'HB-900'",
                          "VR-004 'DN-019'"]
        assert _node(neo4j_driver, "VR-004")["state"] == "rejected", "an unresolved source does not stop the row"

    def test_the_import_is_idempotent_on_the_id(self, req_project, neo4j_driver, domain_config):
        _task(req_project, neo4j_driver, domain_config)
        _import(req_project, neo4j_driver, domain_config)
        before = len(read_events(req_project))
        plan, _ = _import(req_project, neo4j_driver, domain_config)
        assert plan.writes == [] and plan.created == [] and sorted(plan.unchanged) == [
            "VR-001", "VR-002", "VR-003", "VR-004"]
        assert len(read_events(req_project)) == before

    def test_a_reimport_moves_the_state_and_prunes_a_dropped_test(self, req_project, neo4j_driver, domain_config):
        _task(req_project, neo4j_driver, domain_config)
        _import(req_project, neo4j_driver, domain_config)
        p = req_project / "docs" / "VR.md"
        p.write_text(p.read_text().replace(
            "tests/test_map.py::test_first; tests/test_map.py::test_order | — | satisfied: HB-900",
            "tests/test_map.py::test_first | — | open: a review found it wrong"))
        plan, _ = _import(req_project, neo4j_driver, domain_config)
        assert plan.updated == ["VR-001"] and plan.links_removed == 2   # one test, and the task's satisfies
        assert _node(neo4j_driver, "VR-001")["state"] == "accepted"
        assert [e["o"] for e in _edges(neo4j_driver, "VR-001") if e["t"] == "VERIFIED_BY"] == [
            "tests/test_map.py::test_first"]
        types = [e["event_type"] for e in read_events(req_project)]
        assert "link_removed" in types

    def test_a_dry_run_writes_nothing(self, req_project, neo4j_driver, domain_config):
        before = len(read_events(req_project))
        plan, _ = _import(req_project, neo4j_driver, domain_config, dry_run=True)
        assert plan.writes and len(read_events(req_project)) == before
        assert _node(neo4j_driver, "VR-001") is None

    def test_req_add_creates_then_updates_one(self, req_project, neo4j_driver, domain_config):
        cfg = yaml.safe_load((req_project / "seldon.yaml").read_text())
        with pytest.raises(RQ.RequirementsError, match="statement"):
            RQ.add_one(req_project, neo4j_driver, NEO4J_DB, domain_config, cfg, "VR-010", statement=None,
                       set_by=None, verified_by=[], validated_by=None, status=None, section=None, document=None)
        RQ.add_one(req_project, neo4j_driver, NEO4J_DB, domain_config, cfg, "VR-010", statement="It holds.",
                   set_by="DN-019 §2", verified_by=[], validated_by=None, status="open", section="The map",
                   document="docs/VR.md")
        assert _node(neo4j_driver, "VR-010")["state"] == "accepted"
        RQ.add_one(req_project, neo4j_driver, NEO4J_DB, domain_config, cfg, "VR-010", statement=None,
                   set_by=None, verified_by=["tests/test_map.py::test_first"], validated_by=None,
                   status="satisfied", section=None, document=None)
        n = _node(neo4j_driver, "VR-010")
        assert n["state"] == "verified" and n["description"] == "It holds." and n["section"] == "The map"
        assert n["verified_by_text"] == "tests/test_map.py::test_first"
        with pytest.raises(RQ.RequirementsError, match="not a test"):
            RQ.add_one(req_project, neo4j_driver, NEO4J_DB, domain_config, cfg, "VR-010", statement=None,
                       set_by=None, verified_by=["tests/test_gone.py::test_x"], validated_by=None, status=None,
                       section=None, document=None)

    def test_the_cli_import_reports_and_marks(self, req_project, neo4j_driver, domain_config):
        result = CliRunner().invoke(req_group, ["import", "docs/VR.md", "--mark"])
        assert result.exit_code == 0, result.output
        assert "4 requirement(s) in 2 table(s)" in result.output
        assert "did not resolve" in result.output and "DN-404" in result.output
        text = (req_project / "docs" / "VR.md").read_text()
        assert text.count("<!-- seldon:projection ") == 2 and text.count(RQ.END_MARK) == 2
        listed = CliRunner().invoke(req_group, ["list", "--json"])
        assert [r["id"] for r in json.loads(listed.output)] == ["VR-001", "VR-002", "VR-003", "VR-004"]


# ─────────────────────────────────────────────────────────── Part C: the projection


def _mark_and_count(project_dir):
    """Mark the source as `req import --mark` does, and put a counts block where the hand sentence was."""
    src = RQ.read_source(project_dir, "docs/VR.md", RQ.settings({}).columns)
    RQ.mark_source(project_dir, src)
    p = project_dir / "docs" / "VR.md"
    p.write_text(p.read_text().replace(
        "COUNTS.", '<!-- seldon:projection view="counts" -->COUNTS<!-- /seldon:projection -->.'))


@neo4j_tests
class TestProjection:
    def test_generate_reproduces_the_hand_tables_keeps_the_prose_and_commits(self, req_project, neo4j_driver,
                                                                             domain_config):
        _task(req_project, neo4j_driver, domain_config)
        _import(req_project, neo4j_driver, domain_config)
        _mark_and_count(req_project)
        marked = (req_project / "docs" / "VR.md").read_text()
        _git(req_project, "commit", "-qam", "mark")
        cfg = yaml.safe_load((req_project / "seldon.yaml").read_text())
        rendered = RQ.render_all(req_project, neo4j_driver, NEO4J_DB, cfg, kind="requirements")
        out = RQ.write_and_commit(req_project, rendered)
        assert out["committed"] is True, out
        text = (req_project / "docs" / "VR.md").read_text()
        first, rest = text.split("\n", 1)
        assert RQ.HEADER_RE.match(first) and rendered[0].revision in first
        # the tables come back byte for byte; only the counts sentence is new
        assert rest == marked.replace("-->COUNTS<!--", f"-->{COUNTS}<!--")
        assert "Prose the projection must keep" in rest and "More prose between the tables." in rest
        assert _git(req_project, "log", "-1", "--format=%s").startswith("docs: render requirements projection")
        assert "VR.md" not in _git(req_project, "status", "--porcelain"), "the projection is committed"

        again = RQ.render_all(req_project, neo4j_driver, NEO4J_DB, cfg, kind="requirements")
        assert not again[0].changed and again[0].revision == rendered[0].revision
        assert RQ.write_and_commit(req_project, again)["reason"] == "nothing_to_commit"

    def test_a_graph_change_and_a_hand_edit_are_each_reported(self, req_project, neo4j_driver, domain_config):
        _import(req_project, neo4j_driver, domain_config)
        _mark_and_count(req_project)
        cfg = yaml.safe_load((req_project / "seldon.yaml").read_text())
        RQ.write_and_commit(req_project, RQ.render_all(req_project, neo4j_driver, NEO4J_DB, cfg), commit=False)
        assert RQ.stale_projections(req_project, neo4j_driver, NEO4J_DB, cfg) == []

        RQ.add_one(req_project, neo4j_driver, NEO4J_DB, domain_config, cfg, "VR-002", statement=None, set_by=None,
                   verified_by=["tests/test_map.py::test_order"], validated_by=None, status="satisfied",
                   section=None, document=None)
        stale = RQ.stale_projections(req_project, neo4j_driver, NEO4J_DB, cfg)
        assert len(stale) == 1 and "the graph moved since revision" in stale[0]
        RQ.write_and_commit(req_project, RQ.render_all(req_project, neo4j_driver, NEO4J_DB, cfg), commit=False)
        text = (req_project / "docs" / "VR.md").read_text()
        assert "| VR-002 | The map spans the page. | DN-019 §1; DN-404 §2 | tests/test_map.py::test_order |" in text
        assert '1 open' not in text and "3 satisfied" in text

        p = req_project / "docs" / "VR.md"
        p.write_text(p.read_text().replace("The legend floats.", "The legend floats, edited by hand."))
        stale = RQ.stale_projections(req_project, neo4j_driver, NEO4J_DB, cfg)
        assert len(stale) == 1 and "edited outside the graph" in stale[0]

    def test_an_unmarked_hand_file_is_never_overwritten(self, req_project, neo4j_driver, domain_config):
        _import(req_project, neo4j_driver, domain_config)
        cfg = yaml.safe_load((req_project / "seldon.yaml").read_text())
        with pytest.raises(RQ.RequirementsError, match="no seldon:projection markers"):
            RQ.render_all(req_project, neo4j_driver, NEO4J_DB, cfg)
        assert (req_project / "docs" / "VR.md").read_text() == SOURCE

    def test_an_absent_rtm_is_rendered_whole_from_the_edges(self, req_project, neo4j_driver, domain_config):
        _task(req_project, neo4j_driver, domain_config)
        _import(req_project, neo4j_driver, domain_config, document="docs/RTM.md")
        cfg = _config([{"path": "docs/RTM.md", "kind": "rtm"}])
        [r] = RQ.render_all(req_project, neo4j_driver, NEO4J_DB, cfg, kind="rtm")
        assert r.current is None and r.text.startswith("<!-- seldon:projection-revision ")
        assert "# Requirements traceability matrix" in r.text
        assert "## The map" in r.text and "## The legend" in r.text
        assert "| VR-001 | The map is first. | — | HB-900 the map | tests/test_map.py::test_first; " \
               "tests/test_map.py::test_order | verified |" in r.text
        assert "| VR-003 | The legend names the wind. | HB-900 the map | — | none yet | implemented |" in r.text

    def test_a_requirement_with_no_block_is_appended_in_its_section(self, req_project, neo4j_driver,
                                                                   domain_config):
        _import(req_project, neo4j_driver, domain_config)
        _mark_and_count(req_project)
        cfg = yaml.safe_load((req_project / "seldon.yaml").read_text())
        RQ.add_one(req_project, neo4j_driver, NEO4J_DB, domain_config, cfg, "VR-005", statement="Stream it.",
                   set_by=None, verified_by=[], validated_by=None, status="open", section="The stream",
                   document="docs/VR.md")
        [r] = RQ.render_all(req_project, neo4j_driver, NEO4J_DB, cfg)
        assert r.unplaced == ["VR-005"]
        assert r.text.rstrip().endswith(RQ.END_MARK) and "## The stream" in r.text and "| VR-005 | Stream it." in r.text

    def test_the_generate_cli_renders_commits_and_checks(self, req_project, neo4j_driver, domain_config):
        _import(req_project, neo4j_driver, domain_config)
        _mark_and_count(req_project)
        _git(req_project, "commit", "-qam", "mark")
        check = CliRunner().invoke(docs_group, ["generate", "requirements", "--check"])
        assert check.exit_code == 1 and "differs" in check.output
        result = CliRunner().invoke(docs_group, ["generate", "requirements"])
        assert result.exit_code == 0, result.output
        assert "committed" in result.output
        assert CliRunner().invoke(docs_group, ["generate", "requirements", "--check"]).exit_code == 0
        refused = CliRunner().invoke(docs_group, ["generate", "rtm"])
        assert refused.exit_code == 1 and "no `docs.projections` entry of kind rtm" in refused.output


# ─────────────────────────────────────────────────────────── AD-013-R3: the checks


@neo4j_tests
class TestChecks:
    def test_verify_warns_on_unverified_requirements_and_a_stale_projection(self, req_project, neo4j_driver,
                                                                           domain_config):
        cfg = yaml.safe_load((req_project / "seldon.yaml").read_text())
        assert check_requirements(neo4j_driver, NEO4J_DB, req_project, _config()).symbol == "pass"
        _import(req_project, neo4j_driver, domain_config)
        r = check_requirements(neo4j_driver, NEO4J_DB, req_project, cfg)
        assert r.symbol == "warn"
        # VR-002 and VR-003 have no test; VR-004 is rejected, so it binds nothing
        assert "2 with no verified_by test" in r.details[0] and "VR-002, VR-003" in r.details[0]
        assert any("no seldon:projection markers" in d for d in r.details)
        assert "Requirements" not in TIER_A_CHECKS

    def test_docs_check_reports_the_requirements(self, req_project, neo4j_driver, domain_config):
        _import(req_project, neo4j_driver, domain_config)
        result = CliRunner().invoke(docs_group, ["check", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["requirements"]["total"] == 4
        assert data["requirements"]["unverified"] == ["VR-002", "VR-003"]
        strict = CliRunner().invoke(docs_group, ["check", "--type", "SRS_Requirement", "--strict"])
        assert strict.exit_code == 1 and "with no verified_by test" in strict.output

    def test_the_load_appends_one_batch(self, req_project, neo4j_driver, domain_config):
        before = len(read_events(req_project))
        _import(req_project, neo4j_driver, domain_config)
        lines = (req_project / EVENTS_FILENAME).read_text().splitlines()[before:]
        types = {json.loads(l)["event_type"] for l in lines}
        assert types == {"artifact_created", "artifact_state_changed", "link_created"}
