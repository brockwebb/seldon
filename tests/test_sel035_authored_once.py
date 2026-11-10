"""SEL-035 (AD-013 ADDENDUM 02): a requirement is authored once, every other cell is computed, a generated block is
never a second source, and a test declares what it verifies.

C. Computed cells (AD-013-R1, R4): the Status cell is the state's label and the note; Verified-by, Satisfied-by and
   Decision come from the edges; `seldon req migrate` moves SEL-033's verbatim cells to the note, the method or
   nowhere (an edge carries them) and removes them, dropping no word that no edge carries.
D. One direction (AD-013-R2): a hand-edited block is refused with its rows and survives byte for byte;
   `--discard-edits` regenerates; a marked file refuses import; `req update` changes a requirement.
E. Declared coverage (AD-013-R5, R6): `@pytest.mark.verifies` read with ast; function, class and method markers; a
   parametrized test; a removed marker; an unknown id; a file that does not parse; `verify` reads the plan;
   evidence for a non-test method; the marker registered by `project new`.
"""
from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.docs import docs_group
from seldon.commands.req import req_group
from seldon.commands.verify import check_requirements
from seldon.core import project_new as PN
from seldon.core import req_migrate as RM
from seldon.core import req_trace as RT
from seldon.core import req_load as RL
from seldon.core import requirements as RQ
from seldon.core.artifacts import create_artifact, create_link
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.testdb import TEST_DATABASE

DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

STATUS_MAP = {"satisfied": "verified", "changed": "verified", "open": "accepted", "withdrawn": "rejected",
              "met": "verified", "partial": "accepted", "not met": "accepted"}
VIEW, RTM = "docs/VR.md", "docs/RTM.md"
CONFIG = {
    "project": {"name": "t", "domain": "research"},
    "neo4j": {"database": DB, "uri": "bolt://localhost:7687"},
    "event_store": {"path": "seldon_events.jsonl"},
    "requirements": {"status_map": STATUS_MAP, "state_labels": {"verified": "satisfied", "accepted": "open",
                                                                "rejected": "withdrawn"}},
    "docs": {"projections": [
        {"path": VIEW, "kind": "requirements"},
        {"path": RTM, "kind": "rtm", "none_text": "none", "state_labels": {"verified": "met", "accepted": "open"},
         "columns": [{"header": "ID", "source": "requirement_id"}, {"header": "Decision", "source": "@decision"},
                     {"header": "Satisfied by", "source": "@satisfied_by"},
                     {"header": "Checked by", "source": "@verified_by"}, {"header": "State", "source": "@status"}]},
    ]},
}


@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def proj(project_dir, monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    (tmp_path / "gitconfig").write_text("[user]\n\tname = t\n\temail = t@t\n")
    (project_dir / "seldon.yaml").write_text(yaml.safe_dump(CONFIG))
    (project_dir / "tests").mkdir()
    (project_dir / "tests" / "test_map.py").write_text("def test_first():\n    pass\n")
    (project_dir / "docs").mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(project_dir)], check=True)
    _git(project_dir, "add", "-A")
    _git(project_dir, "commit", "-q", "-m", "init")
    monkeypatch.chdir(project_dir)
    return project_dir


def _art(proj, dc, atype, **props):
    return create_artifact(project_dir=proj, driver=_art.driver, database=DB, domain_config=dc, artifact_type=atype,
                           properties=props, actor="human", authority="accepted")


def _req(proj, dc, driver, rid, state, doc=VIEW, **props):
    """A requirement as SEL-033 left it: walked to `state`, with whatever verbatim cells `props` names."""
    _art.driver = driver
    aid = _art(proj, dc, "SRS_Requirement", requirement_id=rid, description=f"{rid} holds.", document=doc,
               section="S", **props)
    walk = RQ.plan_walk(dc, aid, "proposed", state)
    RQ.commit_writes(proj, driver, DB, walk)
    return aid


def _node(driver, rid):
    with driver.session(database=DB) as s:
        return RQ.find_requirement(s, rid)


def _tests_of(driver, rid):
    with driver.session(database=DB) as s:
        return s.run("MATCH (:SRS_Requirement {requirement_id: $r})-[e:VERIFIED_BY]->(t) "
                     "RETURN coalesce(t.test_node, t.name) AS t, e.declared_by AS by ORDER BY t", r=rid).data()


def _settings():
    return RQ.settings(CONFIG)


# ─────────────────────────────────────────────────────────── C. computed cells (pure)


class TestComputedCells:
    def test_status_is_the_label_then_the_note(self):
        s = _settings()
        labels = s.labels(VIEW)
        assert RQ.status_cell({"state": "verified", "note": "HB-131R"}, labels, STATUS_MAP) == "satisfied: HB-131R"
        assert RQ.status_cell({"state": "accepted"}, labels, STATUS_MAP) == "open"
        assert RQ.status_cell({"state": "implemented", "note": "x"}, labels, STATUS_MAP) == "implemented: x", \
            "a state with no label renders its name"
        # the RTM's own vocabulary (per projection)
        assert RQ.status_cell({"state": "verified"}, s.labels(RTM), STATUS_MAP) == "met"

    def test_a_qualifier_that_names_the_state_stands_alone_and_a_stale_one_shows(self):
        labels = _settings().labels(VIEW)
        changed = {"state": "verified", "note": "changed: HB-140R reworded it"}
        assert RQ.status_cell(changed, labels, STATUS_MAP) == "changed: HB-140R reworded it"
        # the state moved under it: the word no longer maps to the state, so the label is prefixed
        assert RQ.status_cell({**changed, "state": "accepted"}, labels, STATUS_MAP) == \
            "open: changed: HB-140R reworded it"

    def test_verified_by_is_the_edges_or_the_none_text_by_method(self):
        v = RQ.View.of(_settings(), None)
        assert RQ.cell_value({"_tests": ["tests/b.py::t", "tests/a.py::t"]}, "@verified_by", v) == \
            "tests/b.py::t; tests/a.py::t"
        assert RQ.cell_value({"_tests": []}, "@verified_by", v) == "none yet"
        assert RQ.cell_value({"_tests": [], "verification_method": "inspection"}, "@verified_by", v) == \
            "inspection: none yet"
        assert RQ.cell_value({"_decisions": ["HBD-012", "HBD-025"]}, "@decision", v) == "HBD-012, HBD-025"

    def test_a_column_the_graph_cannot_compute_is_refused(self):
        bad = {"docs": {"projections": [{"path": VIEW, "columns": [{"header": "Validated by",
                                                                     "source": "validated_by"}]}]}}
        with pytest.raises(RQ.RequirementsError, match="not a projection column"):
            RQ.settings(bad)

    def test_counts_open_on_the_rendered_status(self):
        v = RQ.View.of(_settings(), _settings().projection_for(VIEW))
        nodes = [{"state": "verified", "note": "HB-1", "_tests": ["t"]}, {"state": "verified", "note": "changed",
                                                                         "_tests": ["t"]},
                 {"state": "implemented", "note": "satisfied"}, {"state": "accepted"}]
        assert RQ.render_counts(nodes, "{status:satisfied} s, {status:changed} c, {status:open} o, {unverified} u",
                                v) == "1 s, 1 c, 1 o, 2 u"


class TestPlaceCells:
    """AD-013 ADDENDUM 02 section 4.1, one rule at a time."""

    def place(self, cells, state="verified", label="satisfied", **carried):
        return RL.place_cells(cells, state, label, STATUS_MAP, "none yet", RL.Carried(**carried))

    def test_the_label_word_is_dropped_and_the_rest_becomes_the_note(self):
        assert self.place({"status": "satisfied: HB-131R"}) == ("HB-131R", None, [])
        assert self.place({"status": "satisfied"}) == (None, None, [])
        assert self.place({"status": "met. Each rule's modes"}, label="met")[0] == "Each rule's modes"

    def test_a_qualifier_stays_and_a_disagreeing_word_is_kept_and_listed(self):
        assert self.place({"status": "changed: reworded"}) == ("changed: reworded", None, [])
        note, _, listed = self.place({"status": "satisfied: `live.js`"}, state="implemented", label="implemented")
        assert note == "satisfied: `live.js`" and "maps to verified, the state is implemented" in listed[0]

    def test_a_verification_cell_the_edges_carry_is_dropped(self):
        cell = "`tests/test_a.py` `test_x`, `test_y`"
        assert self.place({"verified_by": cell}, tests={"tests/test_a.py::test_x", "tests/test_a.py::test_y"}) \
            == (None, None, [])
        assert self.place({"verified_by": "none yet"}) == (None, None, [])

    def test_a_method_is_set_and_its_words_kept(self):
        assert self.place({"verified_by": "inspection only; no test asserts it"}) == \
            ("verified by: inspection only; no test asserts it", "inspection", [])
        assert self.place({"verified_by": "judged, not tested"})[1] == "inspection"

    def test_text_no_edge_carries_is_kept_whole_and_listed(self):
        mixed = "`tests/test_a.py` `test_x`; harness A part 4"
        note, method, listed = self.place({"verified_by": mixed, "validated_by": "`90ac45af` (operator review)"},
                                          tests={"tests/test_a.py::test_x"})
        assert note == f"verified by: {mixed}; validated by: `90ac45af` (operator review)" and method is None
        assert len(listed) == 2

    def test_satisfied_by_and_decision_dropped_only_when_carried(self):
        assert self.place({"decision": "HBD-012, HBD-025"}, decisions={"HBD-012", "HBD-025"}) == (None, None, [])
        note, _, listed = self.place({"decision": "HBD-012, HBD-404"}, decisions={"HBD-012"})
        assert note == "decision: HBD-012, HBD-404" and listed
        note, _, _ = self.place({"satisfied_by": "`packs/erg.json`; `incident.py`"})
        assert note == "satisfied by: `packs/erg.json`; `incident.py`"


# ─────────────────────────────────────────────────────────── C. the migration


@neo4j_tests
class TestMigrate:
    def test_migrate_places_every_cell_removes_them_and_is_idempotent(self, proj, neo4j_driver, dc):
        _art.driver = neo4j_driver
        test = _art(proj, dc, "Script", name="tests/test_map.py::test_first", path="tests/test_map.py",
                    test_node="tests/test_map.py::test_first")
        task = _art(proj, dc, "ResearchTask", name="HB-131R the panels", description="t")
        rec = _art(proj, dc, "Decision", name="HBD-012", decision_id="hb:HBD-012", home_repository="hb")
        a = _req(proj, dc, neo4j_driver, "VR-001", "verified", status_text="satisfied: HB-131R",
                 verified_by_text="tests/test_map.py::test_first", validated_by="—")
        create_link(proj, neo4j_driver, DB, dc, a, test, "SRS_Requirement", "Script", "verified_by", "human",
                    "accepted")
        create_link(proj, neo4j_driver, DB, dc, task, a, "ResearchTask", "SRS_Requirement", "satisfies", "human",
                    "accepted")
        _req(proj, dc, neo4j_driver, "VR-002", "verified", status_text="changed: reworded",
             verified_by_text="none yet", validated_by="`90ac45af` (operator review, 2026-11-07)")
        _req(proj, dc, neo4j_driver, "VR-003", "implemented", status_text="satisfied", verified_by_text="none yet")
        t2 = _req(proj, dc, neo4j_driver, "T-2", "implemented", doc=RTM, status_text="met",
                  verified_by_text="inspection", satisfied_by_text="`packs/x.json`", decision_text="HBD-012")
        create_link(proj, neo4j_driver, DB, dc, t2, rec, "SRS_Requirement", "Decision", "derived_from", "human",
                    "accepted")

        m = RM.migrate(proj, neo4j_driver, DB, CONFIG)
        assert sorted(m.migrated) == ["T-2", "VR-001", "VR-002", "VR-003"]
        gone = set(RM.VERBATIM.values())
        for rid in m.migrated:
            assert not gone & set(_node(neo4j_driver, rid)), f"{rid} still carries a verbatim cell"
        assert _node(neo4j_driver, "VR-001").get("note") == "HB-131R"
        assert _node(neo4j_driver, "VR-002")["note"] == "changed: reworded; validated by: `90ac45af` (operator " \
                                                         "review, 2026-11-07)"
        assert _node(neo4j_driver, "VR-003")["note"] == "satisfied"
        t = _node(neo4j_driver, "T-2")
        assert t["verification_method"] == "inspection"
        assert t["note"] == "met; verified by: inspection; satisfied by: `packs/x.json`"
        assert m.methods == {"T-2": "inspection"}
        assert any(x.startswith("VR-003: status 'satisfied'") for x in m.listed)

        before = len(read_events(proj))
        again = RM.migrate(proj, neo4j_driver, DB, CONFIG)
        assert again.migrated == [] and again.skipped == 4 and len(read_events(proj)) == before

        # every cell is computed now: the RTM shows the decision, the task, and the method's missing evidence
        nodes = RQ.load_requirements(neo4j_driver, DB)
        r = RQ.render_projection(proj, _settings().projection_for(RTM), nodes, _settings())
        assert "| T-2 | HBD-012 | — | inspection: none | implemented: met; verified by: inspection; satisfied by: " \
               "`packs/x.json` |" in r.text
        v = RQ.render_projection(proj, _settings().projection_for(VIEW), nodes, _settings())
        assert "| VR-001 | VR-001 holds. | — | tests/test_map.py::test_first | satisfied: HB-131R |" in v.text
        assert "| VR-002 | VR-002 holds. | — | none yet | changed: reworded; validated by:" in v.text
        assert "| VR-003 | VR-003 holds. | — | none yet | implemented: satisfied |" in v.text

    def test_a_later_satisfies_edge_and_state_move_show_in_the_cells(self, proj, neo4j_driver, dc):
        """SEL-035 Part B: a task close adds a satisfies edge, and the RTM's text cell never showed it. Now the cell
        is the edge."""
        _art.driver = neo4j_driver
        a = _req(proj, dc, neo4j_driver, "S3-2", "accepted", doc=RTM, status_text="partial: 26 rules dormant")
        RM.migrate(proj, neo4j_driver, DB, CONFIG)
        task = _art(proj, dc, "ResearchTask", name="HB-142R nearby services", description="t")
        create_link(proj, neo4j_driver, DB, dc, task, a, "ResearchTask", "SRS_Requirement", "satisfies", "human",
                    "accepted")
        r = RQ.render_projection(proj, _settings().projection_for(RTM), RQ.load_requirements(neo4j_driver, DB),
                                 _settings())
        assert "| S3-2 | — | HB-142R nearby services | none | partial: 26 rules dormant |" in r.text


# ─────────────────────────────────────────────────────────── D. one direction


def _rendered_view(proj, neo4j_driver, dc):
    """A marked VIEW file rendered and committed from two requirements."""
    _req(proj, dc, neo4j_driver, "VR-001", "accepted", note="the panel shares the row")
    _req(proj, dc, neo4j_driver, "VR-002", "accepted")
    (proj / VIEW).write_text('# V\n\nProse.\n\n<!-- seldon:projection view="table" section="S" -->\n'
                             '<!-- /seldon:projection -->\n')
    out = RQ.write_and_commit(proj, RQ.render_all(proj, neo4j_driver, DB, CONFIG, kind="requirements"))
    assert out["committed"] is True, out
    return (proj / VIEW).read_bytes()


@neo4j_tests
class TestOneDirection:
    def test_a_hand_edited_block_is_refused_with_its_rows_and_survives(self, proj, neo4j_driver, dc):
        _rendered_view(proj, neo4j_driver, dc)
        p = proj / VIEW
        edited = p.read_text().replace("VR-001 holds.", "VR-001 holds, edited by hand.")
        p.write_text(edited)
        assert RQ.hand_edited(edited)
        result = CliRunner().invoke(docs_group, ["generate", "requirements"])
        assert result.exit_code == 1
        assert "REFUSED" in result.output and "edited by hand" in result.output
        assert "VR-001 holds, edited by hand." in result.output, "the differing row is printed"
        assert p.read_text() == edited, "nothing was written: the edit survives byte for byte"
        stale = RQ.stale_projections(proj, neo4j_driver, DB, CONFIG)
        assert any("edited by hand" in f for f in stale)

    def test_discard_edits_regenerates(self, proj, neo4j_driver, dc):
        clean = _rendered_view(proj, neo4j_driver, dc)
        p = proj / VIEW
        p.write_text(p.read_text().replace("VR-001 holds.", "VR-001 holds, edited by hand."))
        result = CliRunner().invoke(docs_group, ["generate", "requirements", "--discard-edits"])
        assert result.exit_code == 0, result.output
        assert p.read_bytes() == clean

    def test_a_file_the_graph_moved_under_is_rendered(self, proj, neo4j_driver, dc):
        _rendered_view(proj, neo4j_driver, dc)
        RQ.write_one(proj, neo4j_driver, DB, dc, CONFIG, "VR-002", create=False, fields={"note": "Issue fb8fa3fb"})
        assert not RQ.hand_edited((proj / VIEW).read_text()), "the blocks still hash to the stamp"
        result = CliRunner().invoke(docs_group, ["generate", "requirements"])
        assert result.exit_code == 0, result.output
        assert "| VR-002 | VR-002 holds. | — | none yet | open: Issue fb8fa3fb |" in (proj / VIEW).read_text()

    def test_a_marked_file_refuses_import_and_an_unmarked_one_imports(self, proj, neo4j_driver, dc):
        _rendered_view(proj, neo4j_driver, dc)
        result = CliRunner().invoke(req_group, ["import", VIEW])
        assert result.exit_code == 1
        assert "seldon req update" in result.output and "seldon req add" in result.output
        (proj / "docs" / "new.md").write_text("| ID | Requirement | Status |\n|---|---|---|\n| N-1 | It holds. | open |\n")
        ok = CliRunner().invoke(req_group, ["import", "docs/new.md"])
        assert ok.exit_code == 0, ok.output
        assert _node(neo4j_driver, "N-1")["state"] == "accepted"

    def test_req_update_cli_changes_the_authored_fields(self, proj, neo4j_driver, dc):
        _req(proj, dc, neo4j_driver, "VR-001", "accepted")
        r = CliRunner().invoke(req_group, ["update", "VR-001", "--note", "Issue a539174c", "--method", "inspection"])
        assert r.exit_code == 0, r.output
        n = _node(neo4j_driver, "VR-001")
        assert n["note"] == "Issue a539174c" and n["verification_method"] == "inspection"
        refused = CliRunner().invoke(req_group, ["update", "VR-404", "--note", "x"])
        assert refused.exit_code == 1 and "seldon req add VR-404" in refused.output


# ─────────────────────────────────────────────────────────── E. declared coverage


MARKED = '''import pytest
from pytest import mark


@pytest.mark.verifies("VR-001")
def test_function():
    pass


@pytest.mark.verifies("VR-002", "VR-003")
class TestPanel:
    def test_a(self):
        pass

    @mark.verifies("VR-004")
    def test_b(self):
        pass


@pytest.mark.parametrize("x", [1, 2])
@pytest.mark.verifies("VR-005", "VR-404")
def test_cases(x):
    pass


@pytest.mark.verifies(ID)
def test_not_literal():
    pass
'''


class TestScan:
    def test_function_class_method_and_parametrized_markers_bind_to_node_ids(self, tmp_path):
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_panel.py").write_text(MARKED)
        (tmp_path / "tests" / "test_broken.py").write_text("def test_x(:\n")
        (tmp_path / "tests" / "helper.py").write_text('@pytest.mark.verifies("VR-009")\ndef test_h(): pass\n')
        sc = RT.scan(tmp_path, ["tests"])
        assert sc.markers == {
            "tests/test_panel.py::test_function": ["VR-001"],
            "tests/test_panel.py::TestPanel": ["VR-002", "VR-003"],
            "tests/test_panel.py::TestPanel::test_b": ["VR-004"],
            "tests/test_panel.py::test_cases": ["VR-005", "VR-404"],
        }, "helper.py is not a test file; a parametrized test binds its function"
        assert len(sc.unparsable) == 1 and sc.unparsable[0].startswith("tests/test_broken.py: SyntaxError")
        assert len(sc.malformed) == 1 and "test_not_literal" in sc.malformed[0]
        assert sc.files == 2


@neo4j_tests
class TestTrace:
    def test_trace_makes_marker_edges_replaces_imported_ones_and_lists_findings(self, proj, neo4j_driver, dc):
        _art.driver = neo4j_driver
        for rid in ("VR-001", "VR-002", "VR-003", "VR-004", "VR-005"):
            _req(proj, dc, neo4j_driver, rid, "accepted")
        # SEL-033's imported edge on VR-001 (replaced by the marker) and on VR-006 (no marker: kept)
        old = _art(proj, dc, "Script", name="tests/test_map.py::test_first", path="tests/test_map.py",
                   test_node="tests/test_map.py::test_first")
        for rid in ("VR-001", "VR-006"):
            aid = _node(neo4j_driver, rid)["artifact_id"] if rid == "VR-001" else \
                _req(proj, dc, neo4j_driver, rid, "accepted")
            create_link(proj, neo4j_driver, DB, dc, aid, old, "SRS_Requirement", "Script", "verified_by", "human",
                        "accepted")
        (proj / "tests" / "test_panel.py").write_text(MARKED)
        (proj / "tests" / "test_broken.py").write_text("def test_x(:\n")

        tr = RT.trace(proj, neo4j_driver, DB, dc, CONFIG)
        assert sorted(tr.added) == [("VR-001", "tests/test_panel.py::test_function"),
                                    ("VR-002", "tests/test_panel.py::TestPanel"),
                                    ("VR-003", "tests/test_panel.py::TestPanel"),
                                    ("VR-004", "tests/test_panel.py::TestPanel::test_b"),
                                    ("VR-005", "tests/test_panel.py::test_cases")]
        assert tr.removed == [("VR-001", "tests/test_map.py::test_first")]
        assert tr.unknown == ["tests/test_panel.py::test_cases: VR-404"]
        assert any(f.startswith("does not parse: tests/test_broken.py") for f in tr.findings)
        assert _tests_of(neo4j_driver, "VR-001") == [{"t": "tests/test_panel.py::test_function", "by": "marker"}]
        assert _tests_of(neo4j_driver, "VR-006") == [{"t": "tests/test_map.py::test_first", "by": None}]

        before = len(read_events(proj))
        again = RT.trace(proj, neo4j_driver, DB, dc, CONFIG)
        assert again.writes == [] and len(read_events(proj)) == before, "a second trace writes nothing"

        # a removed marker removes its edge
        (proj / "tests" / "test_panel.py").write_text(MARKED.replace('@mark.verifies("VR-004")\n    ', ""))
        tr = RT.trace(proj, neo4j_driver, DB, dc, CONFIG)
        assert tr.removed == [("VR-004", "tests/test_panel.py::TestPanel::test_b")] and tr.added == []
        assert _tests_of(neo4j_driver, "VR-004") == []

    def test_verify_reports_the_plan_and_the_cli_writes_it(self, proj, neo4j_driver, dc):
        _req(proj, dc, neo4j_driver, "VR-001", "accepted")
        (proj / "tests" / "test_panel.py").write_text('import pytest\n\n@pytest.mark.verifies("VR-001", "VR-9")\n'
                                                      'def test_f():\n    pass\n')
        r = check_requirements(neo4j_driver, DB, proj, CONFIG)
        assert any("1 edge(s) to add" in d and "seldon req trace" in d for d in r.details), r.details
        assert any("marker names no requirement: tests/test_panel.py::test_f: VR-9" in d for d in r.details)
        assert _tests_of(neo4j_driver, "VR-001") == [], "verify reads; it does not write"
        out = CliRunner().invoke(req_group, ["trace"])
        assert out.exit_code == 0, out.output
        assert "1 edge(s) added" in out.output and "VR-9" in out.output
        assert _tests_of(neo4j_driver, "VR-001") == [{"t": "tests/test_panel.py::test_f", "by": "marker"}]
        r = check_requirements(neo4j_driver, DB, proj, CONFIG)
        assert not any("to add" in d for d in r.details)


@neo4j_tests
class TestMethod:
    def test_a_non_test_method_is_verified_on_evidence_and_counted_apart(self, proj, neo4j_driver, dc):
        _art.driver = neo4j_driver
        _req(proj, dc, neo4j_driver, "T-2", "implemented", doc=RTM, verification_method="inspection")
        _req(proj, dc, neo4j_driver, "VR-001", "accepted")
        r = check_requirements(neo4j_driver, DB, proj, CONFIG)
        assert any(d.startswith("1 of method test with no test (first: VR-001)") for d in r.details), r.details
        assert any(d.startswith("1 of method inspection with no evidence (first: T-2)") for d in r.details)
        with pytest.raises(RQ.RequirementsError, match="cannot be verified"):
            RQ.write_one(proj, neo4j_driver, DB, dc, CONFIG, "T-2", create=False, fields={}, state="verified")
        script = _art(proj, dc, "Script", name="s", path="x.py")
        with pytest.raises(RQ.RequirementsError, match="not a Result or Issue"):
            RQ.write_one(proj, neo4j_driver, DB, dc, CONFIG, "T-2", create=False, fields={}, evidence=[script])
        issue = _art(proj, dc, "Issue", name="review: T-2 inspected", description="the inspection record",
                     issue_type="review_finding", importance="low", urgency="low", detection_method="review",
                     target=RTM)
        RQ.write_one(proj, neo4j_driver, DB, dc, CONFIG, "T-2", create=False, fields={}, evidence=[issue],
                     state="verified")
        assert _node(neo4j_driver, "T-2")["state"] == "verified"
        assert [x["id"] for x in RQ.unverified(neo4j_driver, DB)] == ["VR-001"]


# ─────────────────────────────────────────────────────────── E. the marker in a new project


class TestMarkerStep:
    def _markers(self, p: Path) -> list:
        return tomllib.loads((p / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]["markers"]

    @pytest.mark.parametrize("pyproject", [
        '[project]\nname = "x"\n',
        '[project]\nname = "x"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
        '[tool.pytest.ini_options]\nmarkers = ["slow: slow tests"]\n',
        '[tool.pytest.ini_options]\nmarkers = [\n    "slow: slow tests",\n]\n\n[tool.other]\nx = 1\n',
    ])
    def test_pyproject_gets_the_marker_once(self, tmp_path, pyproject):
        (tmp_path / "pyproject.toml").write_text(pyproject)
        step = PN.marker_step(tmp_path)
        assert step.status == "changed" and step.wrote == ["pyproject.toml"]
        assert RT.MARKER_LINE in self._markers(tmp_path)
        if "slow" in pyproject:
            assert "slow: slow tests" in self._markers(tmp_path)
        assert PN.marker_step(tmp_path).status == "ok"

    def test_no_pyproject_writes_a_pytest_ini_and_never_beside_a_pyproject(self, tmp_path):
        step = PN.marker_step(tmp_path)
        assert step.status == "changed" and step.wrote == ["pytest.ini"]
        text = (tmp_path / "pytest.ini").read_text()
        assert text.startswith("[pytest]\nmarkers =\n    verifies(")
        assert PN.marker_step(tmp_path).status == "ok"
