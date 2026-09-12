"""Governed documents as graph content — AD-030.

Four layers:

1. reading the governed ledger, and the AD-030-R5 admission invariant;
2. the import into Seldon's graph: what it creates, what it skips, and what a changed content
   hash does to the edges that touch it;
3. the ruling match `seldon cc register` runs, including the defect AD-030 exists for — a task
   that reintroduces something a ruling retired WITHOUT naming the ruling;
4. the emitter itself, over a fixture governed document, which is where the extraction rules are
   pinned.

Layer 4 reads `governed/emit.py` directly. That file belongs to a Squiddy graph, but it imports
nothing from Squiddy at module scope (its one kit import is function-local), so its classification
rules can be pinned from Seldon's own suite without Seldon depending on Squiddy at runtime
(AD-030-R10). The tests skip only when this checkout has no governed graph.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.cc import cc_group, enforce_design_reference, render_rulings
from seldon.commands.governed import governed_group, render_report
from seldon.commands.verify import check_governed
from seldon.core import governed
from seldon.core.artifacts import create_artifact
from seldon.domain.loader import load_domain_config

from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
REPO_ROOT = Path(__file__).resolve().parent.parent

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


# ---------------------------------------------------------------------------
# Ledger fixtures
# ---------------------------------------------------------------------------

def _node(cls: str, payload: dict) -> str:
    return json.dumps({"type": cls, "kind": "node", "payload": payload})


def _edge(cls: str, subject: str, obj: str, **props) -> str:
    return json.dumps(
        {"type": cls, "kind": "edge", "payload": {"subject": subject, "object": obj, **props}}
    )


DOC_TEXT = "# AD-900: A Fixture Decision\n\n**AD-900-R1.** Per-set RPE is never recorded.\n"
DOC_HASH = hashlib.sha256(DOC_TEXT.encode()).hexdigest()
RULING_TEXT = "**AD-900-R1.** Per-set RPE is never recorded."


def ledger_lines(*, content_hash: str = DOC_HASH, manifest_state: str = "admitted") -> list[str]:
    """A one-document governed ledger: a Document, a Section, a Ruling, and their edges."""
    return [
        _node("Document", {
            "id": "docs_design_ad_900_fixture", "title": "AD-900: A Fixture Decision",
            "path": "docs/design/AD-900_fixture.md", "doc_kind": "design",
            "manifest_state": manifest_state, "content_hash": content_hash,
            "section_count": 1, "ruling_count": 1, "identifiers": ["AD-900"],
        }),
        _node("Section", {
            "id": "docs_design_ad_900_fixture#ad_900_a_fixture_decision",
            "doc_id": "docs_design_ad_900_fixture", "heading": "AD-900: A Fixture Decision",
            "level": 1, "ordinal": 0, "section_path": "AD-900: A Fixture Decision",
            "text": DOC_TEXT, "span_start": 0, "span_end": len(DOC_TEXT),
            "content_hash": hashlib.sha256(DOC_TEXT.encode()).hexdigest(),
        }),
        _node("Ruling", {
            "id": "docs_design_ad_900_fixture!ad_900_r1",
            "doc_id": "docs_design_ad_900_fixture", "ruling_identifier": "AD-900-R1",
            "force": "prohibition", "matched_pattern": "numbered_ruling",
            "text": RULING_TEXT, "span_start": 27, "span_end": 27 + len(RULING_TEXT),
            "content_hash": hashlib.sha256(RULING_TEXT.encode()).hexdigest(),
        }),
        _edge("Contains", "docs_design_ad_900_fixture",
              "docs_design_ad_900_fixture#ad_900_a_fixture_decision"),
        _edge("Contains", "docs_design_ad_900_fixture", "docs_design_ad_900_fixture!ad_900_r1"),
    ]


@pytest.fixture
def project(project_dir, monkeypatch):
    """A project root with seldon.yaml and a governed ledger."""
    (project_dir / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n"
        "governed:\n  graph_dir: governed\n  ruling_match_threshold: 0.18\n"
    )
    ledger = project_dir / "governed" / "ledger"
    ledger.mkdir(parents=True)
    (ledger / "events.jsonl").write_text("\n".join(ledger_lines()) + "\n")
    monkeypatch.chdir(project_dir)
    return project_dir


def _config(project_dir: Path) -> dict:
    from seldon.config import load_project_config

    return load_project_config(project_dir)


def _sync(project, driver, domain_config, **kwargs):
    return governed.sync(
        project_dir=project, config=_config(project), driver=driver, database=NEO4J_DB,
        domain_config=domain_config, **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. The ledger, and the admission invariant
# ---------------------------------------------------------------------------

def test_reading_an_absent_ledger_is_an_empty_view(tmp_path):
    """A project that never ran the ingest has nothing to sync; that is a state, not a fault."""
    view = governed.read_ledger(tmp_path / "nope.jsonl")
    assert view.nodes == {} and view.edges == {}


def test_a_corrupt_ledger_line_is_fatal(tmp_path):
    """Skipping one line would import a document with pieces missing and report success."""
    path = tmp_path / "events.jsonl"
    path.write_text(ledger_lines()[0] + "\n{not json\n")
    with pytest.raises(ValueError, match="corrupt governed ledger"):
        governed.read_ledger(path)


def test_the_last_write_wins_per_node(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        _node("Document", {"id": "d", "title": "first", "path": "a.md"}) + "\n"
        + _node("Document", {"id": "d", "title": "second"}) + "\n"
    )
    payload = governed.read_ledger(path).nodes[("Document", "d")]
    assert payload["title"] == "second"
    assert payload["path"] == "a.md"


def test_a_retraction_removes_the_node(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        _node("Document", {"id": "d", "title": "x"}) + "\n"
        + json.dumps({"type": "Document", "kind": "retract",
                      "payload": {"type": "Document", "id": "d"}}) + "\n"
    )
    assert governed.read_ledger(path).nodes == {}


def test_the_admission_invariant_holds_for_an_admitted_document(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(ledger_lines()) + "\n")
    assert governed.admission_violations(governed.read_ledger(path)) == []


@pytest.mark.parametrize("state", ["cataloged", "held", "declined"])
def test_a_content_edge_on_a_non_admitted_document_is_a_violation(tmp_path, state):
    """AD-030-R5: the admission invariant is one query, and this is the query."""
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(ledger_lines(manifest_state=state)) + "\n")
    findings = governed.admission_violations(governed.read_ledger(path))
    assert findings
    assert all("AD-030-R5" in f for f in findings)


@neo4j_tests
def test_sync_refuses_a_ledger_that_breaks_the_invariant(project, neo4j_driver, domain_config):
    (project / "governed" / "ledger" / "events.jsonl").write_text(
        "\n".join(ledger_lines(manifest_state="declined")) + "\n"
    )
    with pytest.raises(ValueError, match="AD-030-R5"):
        _sync(project, neo4j_driver, domain_config)


# ---------------------------------------------------------------------------
# 2. The import
# ---------------------------------------------------------------------------

@neo4j_tests
def test_sync_creates_the_document_and_its_children(project, neo4j_driver, domain_config):
    report = _sync(project, neo4j_driver, domain_config)
    assert report.documents_created == 1
    assert report.nodes_created == {"Document": 1, "Section": 1, "Ruling": 1}
    assert report.edges_created.get("contains") == 2

    with neo4j_driver.session(database=NEO4J_DB) as session:
        doc = session.run(
            "MATCH (d:Artifact:Document {name: 'AD-900'}) RETURN d"
        ).single()["d"]
        assert doc["path"] == "docs/design/AD-900_fixture.md"
        assert doc["content_hash"] == DOC_HASH
        assert doc["state"] == "admitted"

        rulings = session.run(
            "MATCH (:Artifact:Document {name: 'AD-900'})-[:CONTAINS]->(r:Artifact:Ruling) "
            "RETURN r.ruling_identifier AS id, r.force AS force, r.text AS text"
        ).data()
    assert [r["id"] for r in rulings] == ["AD-900-R1"]
    assert rulings[0]["force"] == "prohibition"
    assert rulings[0]["text"] == RULING_TEXT


@neo4j_tests
def test_sync_is_idempotent_by_content_hash(project, neo4j_driver, domain_config):
    """An unchanged document produces no events at all — the whole point of R4."""
    _sync(project, neo4j_driver, domain_config)
    again = _sync(project, neo4j_driver, domain_config)
    assert again.documents_unchanged == 1
    assert again.documents_created == 0 and again.documents_updated == 0
    assert again.nodes_created == {} and again.nodes_updated == {}

    with neo4j_driver.session(database=NEO4J_DB) as session:
        n = session.run("MATCH (d:Artifact:Document) RETURN count(d) AS n").single()["n"]
    assert n == 1


@neo4j_tests
def test_a_changed_hash_updates_and_marks_edges_suspect(project, neo4j_driver, domain_config):
    """AD-030 section 4: a hash change on either end flags the edge for review."""
    _sync(project, neo4j_driver, domain_config)
    (project / "governed" / "ledger" / "events.jsonl").write_text(
        "\n".join(ledger_lines(content_hash="f" * 64)) + "\n"
    )
    report = _sync(project, neo4j_driver, domain_config)
    assert report.documents_updated == 1
    assert report.edges_suspect >= 2

    with neo4j_driver.session(database=NEO4J_DB) as session:
        hash_now = session.run(
            "MATCH (d:Artifact:Document {name: 'AD-900'}) RETURN d.content_hash AS h"
        ).single()["h"]
    assert hash_now == "f" * 64


@neo4j_tests
def test_a_dry_run_writes_nothing(project, neo4j_driver, domain_config):
    report = _sync(project, neo4j_driver, domain_config, dry_run=True)
    assert report.dry_run and report.documents_created == 1
    with neo4j_driver.session(database=NEO4J_DB) as session:
        n = session.run("MATCH (d:Artifact:Document) RETURN count(d) AS n").single()["n"]
    assert n == 0


@neo4j_tests
def test_sync_points_at_an_existing_architectural_decision(
    project, neo4j_driver, domain_config
):
    """Do not double-mint: the Document names the decision record already in the graph."""
    legacy = create_artifact(
        project_dir=project, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ArchitecturalDecision",
        properties={"name": "AD-900", "path": "docs/design/AD-900_fixture.md",
                    "title": "A Fixture Decision", "description": "A fixture decision"},
        actor="human", authority="accepted",
    )
    report = _sync(project, neo4j_driver, domain_config)
    assert report.linked_legacy == 1
    with neo4j_driver.session(database=NEO4J_DB) as session:
        pointer = session.run(
            "MATCH (d:Artifact:Document {name: 'AD-900'}) RETURN d.seldon_artifact_id AS aid"
        ).single()["aid"]
    assert pointer == legacy


@neo4j_tests
def test_only_syncs_one_named_document(project, neo4j_driver, domain_config):
    report = _sync(project, neo4j_driver, domain_config,
                   only="docs/design/AD-900_fixture.md")
    assert report.documents_seen == 1


@neo4j_tests
def test_an_unknown_path_is_an_error_not_a_silent_no_op(project, neo4j_driver, domain_config):
    with pytest.raises(ValueError, match="no governed document matches"):
        _sync(project, neo4j_driver, domain_config, only="docs/design/nope.md")


def test_document_name_follows_the_repository_convention():
    """Existing ArchitecturalDecision nodes are named `AD-013`; a Document must match."""
    assert governed.document_name("docs/design/AD-030_governed_documents.md") == "AD-030"
    assert governed.document_name("docs/design/DN-4_thing.md") == "DN-4"
    assert governed.document_name("handoffs/2026-09-12_closeout.md") == "closeout"
    assert governed.document_name("cc_tasks/no_date_here.md") == "no_date_here"


# ---------------------------------------------------------------------------
# 3. Rulings, and the defect AD-030 exists for
# ---------------------------------------------------------------------------

RPE_RULING = {
    "artifact_id": "r1", "name": "arnold!rpe", "ruling_identifier": "AD-900-R1",
    "force": "prohibition",
    "text": "Per-set RPE is never recorded; session RPE is the only intensity construct.",
    "source_document": "docs/ontology/intensity-constructs.md",
}
UNRELATED_RULING = {
    "artifact_id": "r2", "name": "other!r1", "ruling_identifier": "AD-901-R1",
    "force": "obligation",
    "text": "Every export must round-trip into an identical shape before it is published.",
    "source_document": "docs/design/AD-901_export.md",
}


def test_a_task_naming_a_ruling_identifier_matches_it_exactly():
    matches = governed.match_rulings(
        "Implement the thing described in AD-900-R1.", [RPE_RULING, UNRELATED_RULING], 0.18
    )
    assert [m.ruling_identifier for m in matches] == ["AD-900-R1"]
    assert matches[0].match_method == "identifier"
    assert matches[0].match_score is None


def test_the_defect_ad030_exists_for_is_caught_without_naming_the_ruling():
    """2026-09-01: a task reintroduced a retired per-set RPE field, citing nothing.

    The identifier pass cannot catch this — the task names no ruling. That is exactly why the
    concept pass exists, and the concept pass is the half being tested here.
    """
    task = (
        "Add a per-set RPE field to the plan builder so each set records its own RPE "
        "alongside the session intensity construct."
    )
    matches = governed.match_rulings(task, [RPE_RULING, UNRELATED_RULING], 0.18)
    assert matches, "the retired ruling must be surfaced at registration"
    assert matches[0].ruling_identifier == "AD-900-R1"
    assert matches[0].match_method == "concept_overlap"
    assert "rpe" in matches[0].matched_terms


def test_an_unrelated_task_matches_nothing():
    """A gate that fires on everything is not a gate."""
    task = "Rename the colour of the progress bar in the terminal output."
    assert governed.match_rulings(task, [RPE_RULING, UNRELATED_RULING], 0.18) == []


def test_the_threshold_comes_from_config():
    assert governed.ruling_match_threshold({}) == governed.DEFAULT_RULING_MATCH_THRESHOLD
    assert governed.ruling_match_threshold({"governed": {"ruling_match_threshold": 0.5}}) == 0.5


@pytest.mark.parametrize("bad", ["x", -0.1, 1.5])
def test_an_unusable_threshold_is_refused(bad):
    """Out of range, it silently returns everything or nothing."""
    with pytest.raises(ValueError, match="ruling_match_threshold"):
        governed.ruling_match_threshold({"governed": {"ruling_match_threshold": bad}})


def test_overlap_uses_the_smaller_set_as_the_denominator():
    """Jaccard would divide by the task's length and score every real match near zero."""
    score, shared = governed.overlap_score({"alpha", "beta"}, {"alpha", "beta", "gamma"} | {
        f"filler{i}" for i in range(50)
    })
    assert score == 1.0
    assert shared == ["alpha", "beta"]


@neo4j_tests
def test_cc_register_returns_the_matched_ruling(project, neo4j_driver, domain_config):
    """The success contract: registering a task about per-set RPE returns the ruling forbidding it."""
    _sync(project, neo4j_driver, domain_config)
    # Replace the fixture ruling's text with the RPE prohibition, so the concept pass has
    # something real to find.
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run(
            "MATCH (r:Artifact:Ruling) SET r.text = $text",
            text=RPE_RULING["text"],
        )

    task = project / "cc_tasks" / "2026-09-12_rpe.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(
        "# CC Task: per-set RPE\n\n**Governing doc:** AD-900\n\n"
        "Add a per-set RPE field so each set records its own RPE alongside the session "
        "intensity construct.\n"
    )
    result = CliRunner().invoke(
        cc_group, ["register", str(task), "--allow-untracked"]
    )
    assert result.exit_code == 0, result.output
    assert "Constrained by" in result.output
    assert "AD-900-R1" in result.output

    with neo4j_driver.session(database=NEO4J_DB) as session:
        edges = session.run(
            "MATCH (t:Artifact:ResearchTask)-[c:CONSTRAINED_BY]->(r:Artifact:Ruling) "
            "RETURN c.match_method AS method, r.ruling_identifier AS id"
        ).data()
    assert edges and edges[0]["id"] == "AD-900-R1"


# ---------------------------------------------------------------------------
# AD-030-R9, the task-registration half
# ---------------------------------------------------------------------------

def test_a_task_that_cites_a_decision_passes(tmp_path):
    task = tmp_path / "t.md"
    task.write_text("# CC Task\n\n**Governing doc:** AD-030, ruling AD-030-R9\n")
    assert enforce_design_reference(task, {}, "desktop") is None


def test_a_task_that_cites_nothing_is_refused(tmp_path):
    task = tmp_path / "t.md"
    task.write_text("# CC Task\n\nDo the thing.\n")
    message = enforce_design_reference(task, {}, "desktop")
    assert message is not None and "AD-030-R9" in message
    assert not message.startswith("WARNING")


def test_the_refusal_downgrades_to_a_warning_when_configured(tmp_path):
    task = tmp_path / "t.md"
    task.write_text("# CC Task\n\nDo the thing.\n")
    message = enforce_design_reference(
        task, {"handoff": {"require_design_note": False}}, "desktop"
    )
    assert message is not None and message.startswith("WARNING")


# ---------------------------------------------------------------------------
# AD-030-R11: the allow-list of one
# ---------------------------------------------------------------------------

def test_cc_is_the_only_exempt_actor():
    from seldon.core.handoff import EXEMPT_ACTORS, actor_is_gated

    assert EXEMPT_ACTORS == frozenset({"cc"})
    assert actor_is_gated("cc") is False


@pytest.mark.parametrize(
    "actor",
    ["desktop", "human", "hermes", "autonomous-agent-7", "CC", " cc", "cc ", "", None],
)
def test_every_other_actor_is_gated(actor):
    """A deny-list on `desktop` waves an unknown actor through in silence.

    The list is stated as what is EXEMPT so a new actor is gated by default and somebody has to
    decide to exempt it. `CC` and `cc ` are in here on purpose: a near-miss must not pass.
    """
    from seldon.core.handoff import actor_is_gated

    assert actor_is_gated(actor) is True


@pytest.mark.parametrize("actor", ["desktop", "hermes", "autonomous-agent-7", "human"])
def test_an_unknown_actor_string_is_gated_at_registration(tmp_path, actor):
    """AD-030-R11 at the surface that enforces it, not only at the predicate."""
    task = tmp_path / "t.md"
    task.write_text("# CC Task\n\nDo the thing.\n")
    message = enforce_design_reference(task, {}, actor)
    assert message is not None and "AD-030-R9" in message


def test_cc_is_waved_through_even_with_no_reference(tmp_path):
    """CC executes decisions someone else made; it is not the one deciding."""
    task = tmp_path / "t.md"
    task.write_text("# CC Task\n\nDo the thing.\n")
    assert enforce_design_reference(task, {}, "cc") is None


@neo4j_tests
def test_cc_register_refuses_a_gated_actor_citing_no_decision(
    project, neo4j_driver, domain_config
):
    task = project / "cc_tasks" / "2026-09-12_uncited.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text("# CC Task: uncited\n\nDo the thing.\n")
    result = CliRunner().invoke(
        cc_group, ["register", str(task), "--allow-untracked", "--actor", "hermes"]
    )
    assert result.exit_code == 1
    assert "AD-030-R9" in result.output
    with neo4j_driver.session(database=NEO4J_DB) as session:
        n = session.run("MATCH (t:Artifact:ResearchTask) RETURN count(t) AS n").single()["n"]
    assert n == 0, "a refused task must not reach the graph"


@neo4j_tests
def test_cc_register_records_the_declared_actor(project, neo4j_driver, domain_config):
    """`--actor` is not only a gate switch: it is what `created_by` records."""
    task = project / "cc_tasks" / "2026-09-12_declared.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text("# CC Task\n\n**Governing doc:** AD-030\n\nDo the thing.\n")
    result = CliRunner().invoke(
        cc_group, ["register", str(task), "--allow-untracked", "--actor", "hermes"]
    )
    assert result.exit_code == 0, result.output
    with neo4j_driver.session(database=NEO4J_DB) as session:
        by = session.run(
            "MATCH (t:Artifact:ResearchTask) RETURN t.created_by AS by"
        ).single()["by"]
    assert by == "hermes"


# ---------------------------------------------------------------------------
# The verify hook and the CLI
# ---------------------------------------------------------------------------

@neo4j_tests
def test_verify_fails_on_an_unsynced_governed_document(project, neo4j_driver, domain_config):
    result = check_governed(neo4j_driver, NEO4J_DB, project, _config(project))
    assert result.symbol == "fail"
    assert result.fixable
    assert "docs/design/AD-900_fixture.md" in " ".join(result.details)


@neo4j_tests
def test_verify_passes_once_synced(project, neo4j_driver, domain_config):
    _sync(project, neo4j_driver, domain_config)
    result = check_governed(neo4j_driver, NEO4J_DB, project, _config(project))
    assert result.symbol == "pass"


@neo4j_tests
def test_verify_skips_a_project_with_no_governed_graph(
    project_dir, neo4j_driver, monkeypatch
):
    """AD-030 is opt-in per project; a check that failed on its absence would force adoption."""
    (project_dir / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
    )
    from seldon.config import load_project_config

    result = check_governed(
        neo4j_driver, NEO4J_DB, project_dir, load_project_config(project_dir)
    )
    assert result.symbol == "pass"
    assert "opt-in" in result.summary


@neo4j_tests
def test_cli_sync_reports_what_it_did(project, neo4j_driver, domain_config):
    result = CliRunner().invoke(governed_group, ["sync"])
    assert result.exit_code == 0, result.output
    assert "1 document(s) in the ledger" in result.output
    assert "Document 1" in result.output


@neo4j_tests
def test_cli_sync_without_a_ledger_says_how_to_build_one(project_dir, monkeypatch):
    (project_dir / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
    )
    monkeypatch.chdir(project_dir)
    result = CliRunner().invoke(governed_group, ["sync"])
    assert result.exit_code == 1
    assert "make -C governed" in result.output


@neo4j_tests
def test_search_finds_a_ruling_by_its_words(project, neo4j_driver, domain_config):
    _sync(project, neo4j_driver, domain_config)
    hits = governed.search(neo4j_driver, NEO4J_DB, "RPE", artifact_type="Ruling")
    assert any("RPE" in (h.get("text") or "") for h in hits)


def test_render_report_names_the_abstentions():
    report = governed.SyncReport(documents_seen=1, abstained={"DI-005": 3})
    rendered = render_report(report)
    assert "Abstained" in rendered and "DI-005" in rendered


def test_render_rulings_says_what_to_do_when_nothing_matched():
    assert "seldon governed sync" in render_rulings([], 0)


# ---------------------------------------------------------------------------
# 4. The emitter, over a fixture governed document
# ---------------------------------------------------------------------------

GOVERNED_DIR = REPO_ROOT / "governed"

needs_governed_graph = pytest.mark.skipif(
    not (GOVERNED_DIR / "emit.py").is_file(),
    reason="this checkout has no governed graph",
)


@pytest.fixture
def domain_block():
    """The governed graph's `domain:` block — every classification rule lives there."""
    import yaml

    return yaml.safe_load((GOVERNED_DIR / "config.yaml").read_text())["domain"]


@pytest.fixture
def emitter():
    """Import `governed/emit.py` from this repository's governed graph."""
    import importlib.util

    path = REPO_ROOT / "governed" / "emit.py"
    if not path.is_file():
        pytest.skip("no governed graph in this checkout")
    spec = importlib.util.spec_from_file_location("governed_emit_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AD030 = REPO_ROOT / "docs" / "design" / "AD-030_governed_documents_as_graph_content.md"


@needs_governed_graph
def test_the_ruling_patterns_find_every_numbered_ruling_in_ad030(emitter, domain_block):
    """>= 10: AD-030 declares AD-030-R1 through R10, and each must be its own Ruling.

    Blocks are split on blank lines rather than through the markdown reader, so this pins the
    RULES rather than the parser, and runs wherever Seldon runs.
    """
    if not AD030.is_file():
        pytest.skip("AD-030 is not in this checkout")
    rules = emitter.compiled_rules(domain_block, "ruling_patterns")
    blocks = AD030.read_text(encoding="utf-8").split("\n\n")

    identifiers = set()
    for block in blocks:
        if emitter.classify_ruling(block, rules):
            identifier = emitter.ruling_identifier(block)
            if identifier:
                identifiers.add(identifier)
    assert len(identifiers) >= 10
    assert {"AD-030-R1", "AD-030-R9", "AD-030-R10"} <= identifiers


@needs_governed_graph
def test_a_numbered_ruling_beats_a_bare_modal(emitter, domain_block):
    """Declaration order is precedence order: the specific form wins."""
    rules = emitter.compiled_rules(domain_block, "ruling_patterns")
    match = emitter.classify_ruling("**AD-030-R9.** A session MUST never do the thing.", rules)
    assert match["name"] == "numbered_ruling"
    assert match["force"] == "binding"


@needs_governed_graph
def test_header_fields_are_read_only_from_the_header(emitter):
    """`Extends:` in prose is a sentence, not a declaration."""
    text = (
        "# AD-1\n\n**Extends:** AD-002, AD-004\n\n---\n\n## Body\n\n"
        "**Extends:** AD-999 in this sentence is prose.\n"
    )
    fields = emitter.header_fields(text, ["Extends"])
    assert fields["Extends"] == "AD-002, AD-004"


@needs_governed_graph
def test_identifier_references_are_counted_not_just_found(emitter, domain_block):
    rules = emitter.compiled_rules(domain_block, "identifier_patterns")
    refs = {r["identifier"]: r for r in
            emitter.identifier_references("AD-030 and AD-030 and AD-013", rules)}
    assert refs["AD-030"]["occurrences"] == 2
    assert refs["AD-013"]["kind"] == "AD"


@needs_governed_graph
def test_a_cito_marker_carries_its_reason(emitter, domain_block):
    line = ("DOORS and ReqIF. `disagrees_with` on manual linking as the primary link source, "
            "reason: link authoring cost is no longer the binding constraint.")
    found = emitter.cito_in_line(line, domain_block["cito_markers"])
    assert found["cito_type"] == "disagrees_with"
    assert "binding constraint" in found["reason"]


@needs_governed_graph
def test_a_bullet_without_citation_shape_is_not_a_citation(emitter):
    assert emitter.looks_like_reference("Gotel, O. and Finkelstein, A. (1994). RE 1994.")
    assert not emitter.looks_like_reference("Does not require anyone to author in the graph.")


@needs_governed_graph
@needs_governed_graph
def test_the_section_key_is_stable_across_ordinals(emitter):
    """A citation survives every edit that leaves the heading alone."""
    first = emitter.section_id_for("doc", "A > B", 3)
    again = emitter.section_id_for("doc", "A > B", 41)
    assert first == again == "doc#a_b"


@needs_governed_graph
def test_a_declined_document_maps_to_the_declined_state(emitter):
    assert emitter.manifest_state_for(
        {"stage": "cataloged", "disposition": "excluded:out_of_scope"}
    ) == "declined"


@needs_governed_graph
def test_an_admitting_entry_is_already_admitted(emitter):
    """The stage flips on the FAR side of the append; `held` here would make the gate lie."""
    assert emitter.manifest_state_for({"stage": "admitting", "disposition": "active"}) == "admitted"
    assert emitter.manifest_state_for({"stage": "in_graph", "disposition": "active"}) == "admitted"


# ---------------------------------------------------------------------------
# MCP parity: the success contract names `seldon_cc_register`, not the CLI
# ---------------------------------------------------------------------------

@neo4j_tests
def test_mcp_cc_register_returns_the_matched_ruling(project, neo4j_driver, domain_config):
    """A task about per-set RPE, registered through MCP, comes back holding the ruling."""
    from seldon.mcp_server import seldon_cc_register

    _sync(project, neo4j_driver, domain_config)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run("MATCH (r:Artifact:Ruling) SET r.text = $text", text=RPE_RULING["text"])

    task = project / "cc_tasks" / "2026-09-12_mcp_rpe.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(
        "# CC Task: per-set RPE\n\n**Governing doc:** AD-900\n\n"
        "Add a per-set RPE field so each set records its own RPE alongside the session "
        "intensity construct.\n"
    )
    result = seldon_cc_register(
        filepath="cc_tasks/2026-09-12_mcp_rpe.md",
        project_dir=str(project),
        allow_untracked=True,
    )
    assert "Registered" in result
    assert "Constrained by" in result
    assert "AD-900-R1" in result


@neo4j_tests
def test_mcp_cc_register_refuses_a_task_that_cites_no_decision(
    project, neo4j_driver, domain_config
):
    """AD-030-R9: `seldon_cc_register` checks the reference lexically and refuses otherwise."""
    from seldon.mcp_server import seldon_cc_register

    task = project / "cc_tasks" / "2026-09-12_mcp_uncited.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text("# CC Task: uncited\n\nDo the thing.\n")
    result = seldon_cc_register(
        filepath="cc_tasks/2026-09-12_mcp_uncited.md",
        project_dir=str(project),
        allow_untracked=True,
    )
    assert result.startswith("Error:")
    assert "AD-030-R9" in result
    with neo4j_driver.session(database=NEO4J_DB) as session:
        n = session.run("MATCH (t:Artifact:ResearchTask) RETURN count(t) AS n").single()["n"]
    assert n == 0


# ---------------------------------------------------------------------------
# A governed file the ledger has never heard of (AD-030-R1)
# ---------------------------------------------------------------------------

@pytest.fixture
def project_with_graph_config(project):
    """The `project` fixture plus a governed `config.yaml` declaring one governed directory."""
    (project / "governed" / "config.yaml").write_text(
        "engine: {}\n"
        "domain:\n"
        "  governed_directories:\n"
        "    - {path: docs/design, doc_kind: design}\n"
    )
    (project / "docs" / "design").mkdir(parents=True)
    return project


def test_a_file_the_ledger_never_heard_of_is_reported(project_with_graph_config):
    """The hash check cannot see it: it is in neither the ledger nor the graph."""
    project = project_with_graph_config
    (project / "docs" / "design" / "AD-901_new.md").write_text("# AD-901\n\nProse.\n")
    assert governed.uncataloged(project, _config(project)) == ["docs/design/AD-901_new.md"]


def test_a_cataloged_file_is_not_reported(project_with_graph_config):
    project = project_with_graph_config
    (project / "docs" / "design" / "AD-900_fixture.md").write_text("x")
    assert governed.uncataloged(project, _config(project)) == []


def test_readmes_are_not_governed_documents(project_with_graph_config):
    project = project_with_graph_config
    (project / "docs" / "design" / "README.md").write_text("# Index\n")
    assert governed.uncataloged(project, _config(project)) == []


def test_a_project_with_no_governed_config_reports_nothing(project):
    """The directory list is read from the governed graph, never restated."""
    assert governed.governed_directories(project, _config(project)) == []
    assert governed.uncataloged(project, _config(project)) == []


@neo4j_tests
def test_verify_fails_on_an_uncataloged_file_and_says_what_to_run(
    project_with_graph_config, neo4j_driver, domain_config
):
    project = project_with_graph_config
    _sync(project, neo4j_driver, domain_config)
    (project / "docs" / "design" / "AD-901_new.md").write_text("# AD-901\n\nProse.\n")

    result = check_governed(neo4j_driver, NEO4J_DB, project, _config(project))
    assert result.symbol == "fail"
    assert "never cataloged" in result.summary
    assert "make -C governed catalog" in " ".join(result.details)
    # Not fixable by `--fix`: cataloging runs another repository's pipeline, and a fix that
    # silently invoked it would erase the boundary AD-030-R10 draws.
    assert result.fixable is False


# ---------------------------------------------------------------------------
# AD-030-R16: classification is positional; force is read separately
# ---------------------------------------------------------------------------

@needs_governed_graph
@pytest.mark.parametrize("text", [
    "**AD-030-R1.** Every governed document is graph content.",
    "AD-030-R1. Every governed document is graph content.",
    "## AD-030-R9 The design-note gate",
    "**DN-4-R2.** A thing is decided.",
    "**FR-001.** The system shall do the thing.",
    "## FR-012 Something required",
    "**BINDING.** This paragraph opens with the banner.",
    "## A heading that says BINDING",
])
def test_a_ruling_identifier_or_banner_at_the_front_classifies(emitter, domain_block, text):
    rules = emitter.compiled_rules(domain_block, "ruling_patterns")
    assert emitter.classify_ruling(text, rules) is not None, text


@needs_governed_graph
@pytest.mark.parametrize("text", [
    "Nothing was lost; nothing was bound, and the ruling was never addressable.",
    "Node types: `Ruling` (a Section whose text is deontic: BINDING, MUST, never).",
    "The file MUST be committed alongside its RESULT.",
    "A periodic sweep is the backstop, never the primary path.",
    "This should be reviewed at some point.",
    "Every write SHALL go through one path.",
    "See AD-030-R9 for the gate.",
    "The rule in **AD-030-R9** is quoted here mid-sentence.",
])
def test_deontic_words_in_body_prose_do_not_classify(emitter, domain_block, text):
    """The first backfill classified 161 paragraphs this way; 154 of them on the word `never`."""
    rules = emitter.compiled_rules(domain_block, "ruling_patterns")
    assert emitter.classify_ruling(text, rules) is None, text


@needs_governed_graph
def test_exactly_ten_rulings_in_ad030_after_r16(emitter, domain_block):
    """The success contract, at the pattern level rather than through the graph."""
    if not AD030.is_file():
        pytest.skip("AD-030 is not in this checkout")
    rules = emitter.compiled_rules(domain_block, "ruling_patterns")
    blocks = AD030.read_text(encoding="utf-8").split("\n\n")
    identifiers = {
        emitter.ruling_identifier(b)
        for b in blocks if emitter.classify_ruling(b, rules)
    }
    assert identifiers == {f"AD-030-R{n}" for n in range(1, 11)}


@needs_governed_graph
@pytest.mark.parametrize("text,expected", [
    ("**AD-1-R1.** A thing MUST NOT happen.", "prohibition"),
    ("**AD-1-R1.** A thing is never recorded.", "prohibition"),
    ("**AD-1-R1.** A thing MUST happen.", "obligation"),
    ("**AD-1-R1.** A thing SHOULD happen.", "recommendation"),
    ("**AD-1-R1.** A thing is the case.", "binding"),
])
def test_force_is_still_read_from_the_text(emitter, domain_block, text, expected):
    """R16 governs whether a block IS a ruling, not what force a ruling carries.

    Collapsing every Ruling to `binding` would throw away the only axis that distinguishes a
    prohibition from a recommendation.
    """
    rules = emitter.compiled_rules(domain_block, "ruling_patterns")
    forces = emitter.compiled_rules(domain_block, "force_patterns")
    match = emitter.classify_ruling(text, rules, forces, domain_block["default_force"])
    assert match["force"] == expected


@needs_governed_graph
def test_a_header_field_resolves_paths_as_well_as_identifiers(emitter):
    """The findings note's `Depends on:` names two RESULT files by path, not by identifier."""
    assert emitter.path_references(
        "`cc_tasks/a_RESULT.md`, `cc_tasks/b_RESULT.md`"
    ) == ["cc_tasks/a_RESULT.md", "cc_tasks/b_RESULT.md"]
    assert emitter.path_references("AD-030 and AD-028") == []


# ---------------------------------------------------------------------------
# Names must be unique
# ---------------------------------------------------------------------------

def test_two_documents_sharing_a_leading_identifier_get_distinct_names():
    """`AD-030_governed_*.md` and `AD-030_implementation_findings_001.md` are not the same doc."""
    names = governed.assign_names([
        "docs/design/AD-030_implementation_findings_001.md",
        "docs/design/AD-030_governed_documents_as_graph_content.md",
    ])
    assert names["docs/design/AD-030_governed_documents_as_graph_content.md"] == "AD-030"
    assert names["docs/design/AD-030_implementation_findings_001.md"] == (
        "AD-030_implementation_findings_001"
    )
    assert len(set(names.values())) == 2


def test_name_assignment_does_not_depend_on_input_order():
    paths = [
        "docs/design/AD-030_implementation_findings_001.md",
        "docs/design/AD-030_governed_documents_as_graph_content.md",
        "docs/design/AD-013_documentation_as_traceability.md",
    ]
    assert governed.assign_names(paths) == governed.assign_names(list(reversed(paths)))


@neo4j_tests
def test_a_name_derivation_change_reaches_the_graph(project, neo4j_driver, domain_config):
    """The hash covers the FILE; a name is derived, so it can move without the hash moving."""
    _sync(project, neo4j_driver, domain_config)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run("MATCH (d:Artifact:Document) SET d.name = 'STALE'")
    report = _sync(project, neo4j_driver, domain_config)
    assert report.documents_updated == 1
    with neo4j_driver.session(database=NEO4J_DB) as session:
        name = session.run("MATCH (d:Artifact:Document) RETURN d.name AS n").single()["n"]
    assert name == "AD-900"


@neo4j_tests
def test_a_name_only_change_does_not_flag_edges_suspect(
    project, neo4j_driver, domain_config
):
    """A suspect flag that fires on non-events is one people learn to clear without reading."""
    _sync(project, neo4j_driver, domain_config)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run("MATCH (d:Artifact:Document) SET d.name = 'STALE'")
    report = _sync(project, neo4j_driver, domain_config)
    assert report.documents_updated == 1
    assert report.edges_suspect == 0


# ---------------------------------------------------------------------------
# Retirement, and what a retired ruling may no longer do
# ---------------------------------------------------------------------------

@neo4j_tests
def test_a_child_the_ledger_no_longer_holds_is_retired_not_deleted(
    project, neo4j_driver, domain_config
):
    """161 rulings left the corpus in one pattern change. Deleting them would lose the record."""
    _sync(project, neo4j_driver, domain_config)
    ledger = project / "governed" / "ledger" / "events.jsonl"
    ledger.write_text("\n".join(l for l in ledger_lines() if '"Ruling"' not in l) + "\n")

    report = _sync(project, neo4j_driver, domain_config)
    assert report.nodes_retired.get("Ruling") == 1
    with neo4j_driver.session(database=NEO4J_DB) as session:
        row = session.run(
            "MATCH (r:Artifact:Ruling) RETURN r.state AS state, count(r) AS n"
        ).single()
    assert row["state"] == "retired" and row["n"] == 1


@neo4j_tests
def test_a_retired_ruling_cannot_constrain_a_new_task(
    project, neo4j_driver, domain_config
):
    """It binds nothing; returning it would assert an obligation no document imposes."""
    _sync(project, neo4j_driver, domain_config)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run("MATCH (r:Artifact:Ruling) SET r.state = 'retired'")
    assert governed.read_rulings(neo4j_driver, NEO4J_DB) == []
    assert len(governed.read_rulings(neo4j_driver, NEO4J_DB, include_non_binding=True)) == 1


@neo4j_tests
def test_a_partial_sync_never_retires(project, neo4j_driver, domain_config):
    """A `--only` run has seen one document and knows nothing about the rest of the corpus."""
    _sync(project, neo4j_driver, domain_config)
    ledger = project / "governed" / "ledger" / "events.jsonl"
    ledger.write_text("\n".join(l for l in ledger_lines() if '"Ruling"' not in l) + "\n")
    report = _sync(project, neo4j_driver, domain_config,
                   only="docs/design/AD-900_fixture.md")
    assert report.nodes_retired == {}


# ---------------------------------------------------------------------------
# `seldon cc constrain`: the backfill for tasks registered before the gate
# ---------------------------------------------------------------------------

@neo4j_tests
def test_cc_constrain_writes_edges_for_an_already_registered_task(
    project, neo4j_driver, domain_config
):
    """eb359760 was registered through a stale MCP server and got zero edges."""
    _sync(project, neo4j_driver, domain_config)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        session.run("MATCH (r:Artifact:Ruling) SET r.text = $t", t=RPE_RULING["text"])

    task = project / "cc_tasks" / "2026-09-12_already.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(
        "# CC Task\n\n**Governing doc:** AD-900\n\nAdd a per-set RPE field so each set records "
        "its own RPE alongside the session intensity construct.\n"
    )
    task_id = create_artifact(
        project_dir=project, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": "already registered",
                    "source_file": "cc_tasks/2026-09-12_already.md"},
        actor="desktop", authority="accepted",
    )

    result = CliRunner().invoke(cc_group, ["constrain", task_id[:8]])
    assert result.exit_code == 0, result.output
    assert "AD-900-R1" in result.output
    with neo4j_driver.session(database=NEO4J_DB) as session:
        n = session.run(
            "MATCH (t:Artifact:ResearchTask)-[c:CONSTRAINED_BY]->() RETURN count(c) AS n"
        ).single()["n"]
    assert n == 1


@neo4j_tests
def test_cc_constrain_dry_run_writes_nothing(project, neo4j_driver, domain_config):
    _sync(project, neo4j_driver, domain_config)
    task = project / "cc_tasks" / "2026-09-12_already.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text("# CC Task\n\n**Governing doc:** AD-900\n\nAD-900-R1 applies here.\n")
    task_id = create_artifact(
        project_dir=project, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": "x", "source_file": "cc_tasks/2026-09-12_already.md"},
        actor="desktop", authority="accepted",
    )
    result = CliRunner().invoke(cc_group, ["constrain", task_id[:8], "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "AD-900-R1" in result.output
    with neo4j_driver.session(database=NEO4J_DB) as session:
        n = session.run(
            "MATCH ()-[c:CONSTRAINED_BY]->() RETURN count(c) AS n"
        ).single()["n"]
    assert n == 0


def test_cc_constrain_refuses_both_or_neither():
    for args in (["constrain"], ["constrain", "abc", "--all"]):
        result = CliRunner().invoke(cc_group, args)
        assert result.exit_code == 1
        assert "not both and not neither" in result.output


# ---------------------------------------------------------------------------
# AD-030-R17: the Squiddy pin
# ---------------------------------------------------------------------------

def test_pyproject_declares_no_squiddy_dependency():
    """R17 supersedes the pyproject clause of R10: Squiddy is build-time for `governed/` only."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "squiddy" not in text.lower()


@needs_governed_graph
def test_the_pin_names_a_commit():
    import sys as _sys

    _sys.path.insert(0, str(GOVERNED_DIR))
    import check_pin

    pin = check_pin.read_pin(GOVERNED_DIR)
    assert len(pin["SQUIDDY_COMMIT"]) == 40
    assert all(ch in "0123456789abcdef" for ch in pin["SQUIDDY_COMMIT"])


@needs_governed_graph
def test_an_absent_pin_is_fatal(tmp_path):
    """An absent pin is not 'unpinned by default'; it is a build nobody has stated."""
    import sys as _sys

    _sys.path.insert(0, str(GOVERNED_DIR))
    import check_pin

    with pytest.raises(SystemExit, match="no squiddy.pin"):
        check_pin.read_pin(tmp_path)


@needs_governed_graph
def test_every_build_target_depends_on_the_pin_check():
    """A graph built against an unpinned kit is not reproducible, and the ledger is append-only."""
    makefile = (GOVERNED_DIR / "Makefile").read_text(encoding="utf-8")
    for target in ("catalog", "admit", "plan", "sweep", "schema"):
        assert f"\n{target}: check-squiddy" in makefile, target
