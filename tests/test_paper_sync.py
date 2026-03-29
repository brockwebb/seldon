"""
Integration tests for seldon paper sync.
Requires Neo4j (skipped if unavailable).
"""
import os
import pytest
from pathlib import Path

from seldon.core.artifacts import create_artifact, transition_state
from seldon.core.events import read_events, event_count
from seldon.core.graph import get_artifact
from seldon.domain.loader import load_domain_config
from seldon.paper.sync import (
    compute_file_hash,
    scan_references,
    get_paper_section_artifacts,
    sync_section,
    sync_all,
    _parse_subsections,
    _sync_subsections,
)

RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
NEO4J_DB = "seldon-test"

# Applied to integration test classes/functions individually — unit tests don't need Neo4j
needs_neo4j = pytest.mark.usefixtures("neo4j_available")


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def paper_dir(tmp_path):
    """Temporary paper directory with a sections/ subdirectory."""
    sections = tmp_path / "paper" / "sections"
    sections.mkdir(parents=True)
    return tmp_path / "paper"


def _make_section(paper_dir: Path, filename: str, content: str) -> Path:
    path = paper_dir / "sections" / filename
    path.write_text(content)
    return path


def _create_paper_section(
    project_dir, neo4j_driver, domain_config, name, title, file_path, content_hash=None
) -> str:
    props = {"name": name, "title": title, "file_path": str(file_path)}
    if content_hash is not None:
        props["content_hash"] = content_hash
    return create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties=props,
        actor="human",
        authority="accepted",
    )


def _create_result(project_dir, neo4j_driver, domain_config, name) -> str:
    return create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="Result",
        properties={"name": name, "value": 0.9, "units": "accuracy", "description": f"test {name}"},
        actor="human",
        authority="accepted",
    )


# ── Unit tests (no Neo4j) ─────────────────────────────────────────────────────

def test_compute_file_hash_is_deterministic(tmp_path):
    f = tmp_path / "test.md"
    f.write_text("hello world")
    h1 = compute_file_hash(f)
    h2 = compute_file_hash(f)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_compute_file_hash_changes_with_content(tmp_path):
    f = tmp_path / "test.md"
    f.write_text("version 1")
    h1 = compute_file_hash(f)
    f.write_text("version 2")
    h2 = compute_file_hash(f)
    assert h1 != h2


def test_scan_references_extracts_result_and_cite():
    text = "See {{result:accuracy:value}} and {{cite:smith_2023:bibtex_key}}."
    refs = scan_references(text)
    assert refs == {"result:accuracy", "cite:smith_2023"}


def test_scan_references_excludes_figure():
    text = "See {{figure:my_fig:path}} and {{result:acc:value}}."
    refs = scan_references(text)
    assert refs == {"result:acc"}
    assert "figure:my_fig" not in refs


def test_scan_references_empty():
    assert scan_references("No references here.") == set()


def test_scan_references_deduplicates():
    text = "{{result:acc:value}} and again {{result:acc:units}}."
    refs = scan_references(text)
    assert refs == {"result:acc"}


def test_parse_subsections_empty_file(tmp_path):
    """File with no ## headings returns empty list."""
    f = tmp_path / "intro.md"
    f.write_text("# Introduction\n\nSome prose without subheadings.")
    result = _parse_subsections(f, "01_introduction", 0)
    assert result == []


def test_parse_subsections_single_heading(tmp_path):
    """Single ## heading produces one subsection."""
    f = tmp_path / "methods.md"
    f.write_text("# Methods\n\n## Experimental Setup\n\nSome content here.")
    result = _parse_subsections(f, "03_methods", 0)
    assert len(result) == 1
    sub = result[0]
    assert sub["name"] == "03_methods:experimental_setup"
    assert sub["title"] == "Experimental Setup"
    assert sub["sequence"] == 1
    assert sub["depth"] == 1
    assert isinstance(sub["content_hash"], str) and len(sub["content_hash"]) == 64


def test_parse_subsections_multiple_headings(tmp_path):
    """Multiple ## headings produce correctly sequenced subsections."""
    f = tmp_path / "results.md"
    f.write_text(
        "# Results\n\n"
        "## Discovery Rates\n\nContent A.\n\n"
        "## Wrong-Limit Attractors\n\nContent B.\n\n"
        "## Parsimony Effects\n\nContent C."
    )
    result = _parse_subsections(f, "05_results", 0)
    assert len(result) == 3
    assert result[0]["name"] == "05_results:discovery_rates"
    assert result[1]["name"] == "05_results:wrong_limit_attractors"
    assert result[2]["name"] == "05_results:parsimony_effects"
    assert [s["sequence"] for s in result] == [1, 2, 3]
    assert all(s["depth"] == 1 for s in result)


def test_parse_subsections_extracts_result_tokens(tmp_path):
    """Tokens in each subsection's range are attributed to that subsection."""
    f = tmp_path / "results.md"
    f.write_text(
        "# Results\n\n"
        "## Section A\n\nSee {{result:metric_a:value}} here.\n\n"
        "## Section B\n\nSee {{result:metric_b:value}} here."
    )
    result = _parse_subsections(f, "05_results", 0)
    assert result[0]["tokens"]["results"] == ["metric_a"]
    assert result[1]["tokens"]["results"] == ["metric_b"]


def test_parse_subsections_extracts_xref_tokens(tmp_path):
    """Figure and table tokens are attributed to the correct subsection."""
    f = tmp_path / "results.md"
    f.write_text(
        "# Results\n\n"
        "## Figures Section\n\nSee {{figure:fig2_plot}} and {{table:table_5}}.\n\n"
        "## Other\n\nPlain text."
    )
    result = _parse_subsections(f, "05_results", 0)
    assert result[0]["tokens"]["figures"] == ["fig2_plot"]
    assert result[0]["tokens"]["tables"] == ["table_5"]
    assert result[1]["tokens"]["figures"] == []
    assert result[1]["tokens"]["tables"] == []


def test_parse_subsections_separates_cite_from_result_tokens(tmp_path):
    """Cite tokens are stored under 'cites', not 'results'."""
    f = tmp_path / "methods.md"
    f.write_text(
        "# Methods\n\n## Section A\n\n"
        "See {{result:metric_a:value}} and {{cite:smith_2023:bibtex_key}}."
    )
    result = _parse_subsections(f, "03_methods", 0)
    assert result[0]["tokens"]["results"] == ["metric_a"]
    assert result[0]["tokens"]["cites"] == ["smith_2023"]
    assert "smith_2023" not in result[0]["tokens"]["results"]


def test_parse_subsections_content_hash_differs_per_section(tmp_path):
    """Each subsection has a content hash computed from its own text range."""
    f = tmp_path / "results.md"
    f.write_text(
        "# Results\n\n"
        "## Section A\n\nContent unique to A.\n\n"
        "## Section B\n\nContent unique to B."
    )
    result = _parse_subsections(f, "05_results", 0)
    assert result[0]["content_hash"] != result[1]["content_hash"]


def test_parse_subsections_slugify_special_chars(tmp_path):
    """Heading text with special characters is slugified correctly."""
    f = tmp_path / "methods.md"
    f.write_text("# Methods\n\n## GP-Based Search: Results & Analysis\n\nContent.")
    result = _parse_subsections(f, "03_methods", 0)
    assert result[0]["name"] == "03_methods:gp_based_search_results_analysis"


# ── Integration tests (Neo4j required) ────────────────────────────────────────

@needs_neo4j
def test_sync_all_untracked_no_artifacts(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """All sections are untracked when no PaperSection artifacts exist."""
    _make_section(paper_dir, "01_intro.md", "# Introduction\n\nHello.")
    _make_section(paper_dir, "02_methods.md", "# Methods\n\nSee {{result:acc:value}}.")

    results = sync_all(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        paper_dir=paper_dir,
    )

    assert len(results) == 2
    assert all(r.status == "untracked" for r in results)
    assert event_count(project_dir) == 0


def test_sync_all_unchanged_when_hash_matches(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """Sections skip when content hash matches stored hash."""
    content = "# Introduction\n\nHello world."
    path = _make_section(paper_dir, "01_intro.md", content)
    current_hash = compute_file_hash(path)

    _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="01_intro", title="Introduction",
        file_path=path, content_hash=current_hash,
    )

    results = sync_all(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        paper_dir=paper_dir,
    )

    assert len(results) == 1
    assert results[0].status == "unchanged"


def test_sync_section_hash_changed_updates_artifact(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """When file content changes, sync updates content_hash on the artifact."""
    path = _make_section(paper_dir, "01_intro.md", "# Introduction\n\nOriginal content.")
    old_hash = compute_file_hash(path)

    artifact_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="01_intro", title="Introduction",
        file_path=path, content_hash=old_hash,
    )

    # Edit the file
    path.write_text("# Introduction\n\nEdited content.")
    new_hash = compute_file_hash(path)
    assert new_hash != old_hash

    artifact = {"artifact_id": artifact_id, "name": "01_intro", "content_hash": old_hash, "state": "draft"}
    result = sync_section(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        section_path=path,
        artifact=artifact,
    )

    assert result.status == "updated"
    node = get_artifact(neo4j_driver.session(database=NEO4J_DB), artifact_id)
    assert node["content_hash"] == new_hash


def test_sync_section_added_reference_creates_edge(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """Adding a {{result:...}} reference creates a new CITES edge."""
    path = _make_section(paper_dir, "02_results.md", "# Results\n\nOriginal text.")
    old_hash = compute_file_hash(path)

    section_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="02_results", title="Results",
        file_path=path, content_hash=old_hash,
    )
    result_id = _create_result(project_dir, neo4j_driver, domain_config, "accuracy")

    # Edit file to add a reference
    path.write_text("# Results\n\nSee {{result:accuracy:value}} for details.")

    artifact = {"artifact_id": section_id, "name": "02_results", "content_hash": old_hash, "state": "draft"}
    sync_result = sync_section(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        section_path=path,
        artifact=artifact,
    )

    assert sync_result.status == "updated"
    assert "result:accuracy" in sync_result.refs_added

    # Verify CITES edge exists in graph
    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (s:Artifact {artifact_id: $sid})-[r:CITES]->(t:Artifact {artifact_id: $tid}) RETURN r",
            sid=section_id, tid=result_id,
        ).single()
    assert rel is not None

    # Verify link_created event
    events = read_events(project_dir)
    link_events = [e for e in events if e["event_type"] == "link_created"]
    assert len(link_events) == 1


def test_sync_section_removed_reference_deletes_edge(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """Removing a {{result:...}} reference deletes the corresponding CITES edge."""
    from seldon.core.artifacts import create_link

    path = _make_section(
        paper_dir, "02_results.md",
        "# Results\n\nSee {{result:precision:value}}."
    )
    old_hash = compute_file_hash(path)

    section_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="02_results", title="Results",
        file_path=path, content_hash=old_hash,
    )
    result_id = _create_result(project_dir, neo4j_driver, domain_config, "precision")

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id,
        to_id=result_id,
        from_type="PaperSection",
        to_type="Result",
        rel_type="cites",
        actor="human",
        authority="accepted",
    )

    # Edit file to remove the reference
    path.write_text("# Results\n\nNo references anymore.")

    artifact = {"artifact_id": section_id, "name": "02_results", "content_hash": old_hash, "state": "draft"}
    sync_result = sync_section(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        section_path=path,
        artifact=artifact,
    )

    assert sync_result.status == "updated"
    assert "result:precision" in sync_result.refs_removed

    # Verify CITES edge was removed
    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (s:Artifact {artifact_id: $sid})-[r:CITES]->(t:Artifact {artifact_id: $tid}) RETURN r",
            sid=section_id, tid=result_id,
        ).single()
    assert rel is None

    link_removed_events = [e for e in read_events(project_dir) if e["event_type"] == "link_removed"]
    assert len(link_removed_events) == 1


def test_sync_section_renamed_references(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """Renaming a reference removes the old edge and creates a new one."""
    from seldon.core.artifacts import create_link

    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\nSee {{result:old_metric:value}}."
    )
    old_hash = compute_file_hash(path)

    section_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=old_hash,
    )
    old_result_id = _create_result(project_dir, neo4j_driver, domain_config, "old_metric")
    new_result_id = _create_result(project_dir, neo4j_driver, domain_config, "new_metric")

    create_link(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id,
        to_id=old_result_id,
        from_type="PaperSection",
        to_type="Result",
        rel_type="cites",
        actor="human",
        authority="accepted",
    )

    # Rename the reference in the file
    path.write_text("# Methods\n\nSee {{result:new_metric:value}}.")

    artifact = {"artifact_id": section_id, "name": "03_methods", "content_hash": old_hash, "state": "draft"}
    sync_result = sync_section(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        section_path=path,
        artifact=artifact,
    )

    assert sync_result.status == "updated"
    assert "result:old_metric" in sync_result.refs_removed
    assert "result:new_metric" in sync_result.refs_added

    with neo4j_driver.session(database=NEO4J_DB) as session:
        old_rel = session.run(
            "MATCH (s {artifact_id: $sid})-[r:CITES]->(t {artifact_id: $tid}) RETURN r",
            sid=section_id, tid=old_result_id,
        ).single()
        new_rel = session.run(
            "MATCH (s {artifact_id: $sid})-[r:CITES]->(t {artifact_id: $tid}) RETURN r",
            sid=section_id, tid=new_result_id,
        ).single()
    assert old_rel is None
    assert new_rel is not None


def test_sync_section_dry_run_no_events(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """dry_run=True reports changes without writing any events or mutations."""
    path = _make_section(paper_dir, "01_intro.md", "# Introduction\n\nOriginal.")
    old_hash = compute_file_hash(path)

    artifact_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="01_intro", title="Introduction",
        file_path=path, content_hash=old_hash,
    )
    initial_events = event_count(project_dir)

    # Edit the file
    path.write_text("# Introduction\n\nEdited content with {{result:acc:value}}.")

    artifact = {"artifact_id": artifact_id, "name": "01_intro", "content_hash": old_hash, "state": "draft"}
    result = sync_section(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        section_path=path,
        artifact=artifact,
        dry_run=True,
    )

    assert result.status == "updated"
    # No new events written
    assert event_count(project_dir) == initial_events
    # Hash not updated in graph
    node = get_artifact(neo4j_driver.session(database=NEO4J_DB), artifact_id)
    assert node.get("content_hash") == old_hash


def test_sync_register_untracked_creates_artifact(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """--register-untracked creates PaperSection artifacts for untracked files."""
    _make_section(paper_dir, "01_intro.md", "# Introduction\n\nHello.")
    _make_section(paper_dir, "02_methods.md", "# Methods\n\nSee {{result:acc:value}}.")

    _create_result(project_dir, neo4j_driver, domain_config, "acc")

    results = sync_all(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        paper_dir=paper_dir,
        register_untracked=True,
    )

    assert len(results) == 2
    assert all(r.status == "registered" for r in results)

    # Verify artifacts exist in graph
    artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    assert "01_intro" in artifacts
    assert "02_methods" in artifacts

    # Verify content_hash stored
    assert artifacts["01_intro"].get("content_hash") is not None

    # Verify cites edge created for the reference in 02_methods
    section_id = artifacts["02_methods"]["artifact_id"]
    with neo4j_driver.session(database=NEO4J_DB) as session:
        rels = session.run(
            "MATCH (s:Artifact {artifact_id: $id})-[:CITES]->(t) RETURN t.name AS name",
            id=section_id,
        ).data()
    assert any(r["name"] == "acc" for r in rels)


def test_sync_auto_stale_transitions_published_section(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """--auto-stale transitions a published section to stale when content changes."""
    path = _make_section(paper_dir, "05_discussion.md", "# Discussion\n\nOriginal.")
    old_hash = compute_file_hash(path)

    artifact_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="05_discussion", title="Discussion",
        file_path=path, content_hash=old_hash,
    )

    # Transition artifact to published state: proposed → draft → review → published
    for from_s, to_s in [("proposed", "draft"), ("draft", "review"), ("review", "published")]:
        transition_state(
            project_dir=project_dir,
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
            artifact_id=artifact_id,
            artifact_type="PaperSection",
            current_state=from_s,
            new_state=to_s,
            actor="human",
            authority="accepted",
        )

    # Edit file
    path.write_text("# Discussion\n\nEdited and expanded.")

    artifact = {
        "artifact_id": artifact_id,
        "name": "05_discussion",
        "content_hash": old_hash,
        "state": "published",
    }
    result = sync_section(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        section_path=path,
        artifact=artifact,
        auto_stale=True,
    )

    assert result.status == "updated"
    assert result.state_changed is True

    node = get_artifact(neo4j_driver.session(database=NEO4J_DB), artifact_id)
    assert node["state"] == "stale"


# ---------------------------------------------------------------------------
# OOB (out-of-band) edit detection — integration tests, require Neo4j
# ---------------------------------------------------------------------------

@needs_neo4j
class TestSuspectedOOB:
    """SyncResult.suspected_oob is set when a review/published section changes
    without --auto-stale, indicating the edit may have happened outside a CC task."""

    def _create_section_at_state(
        self, project_dir, driver, domain_config, name, target_state, file_path, old_hash
    ) -> str:
        artifact_id = _create_paper_section(
            project_dir, driver, domain_config,
            name=name, title=name.replace("_", " ").title(),
            file_path=file_path, content_hash=old_hash,
        )
        state_path = {
            "draft": [("proposed", "draft")],
            "review": [("proposed", "draft"), ("draft", "review")],
            "published": [("proposed", "draft"), ("draft", "review"), ("review", "published")],
        }
        for from_s, to_s in state_path.get(target_state, []):
            transition_state(
                project_dir=project_dir, driver=driver, database=NEO4J_DB,
                domain_config=domain_config, artifact_id=artifact_id,
                artifact_type="PaperSection", current_state=from_s,
                new_state=to_s, actor="human", authority="accepted",
            )
        return artifact_id

    def test_review_section_changed_sets_suspected_oob(
        self, neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
    ):
        path = _make_section(paper_dir, "01_intro.md", "# Intro\n\nOriginal content.")
        old_hash = compute_file_hash(path)
        artifact_id = self._create_section_at_state(
            project_dir, neo4j_driver, domain_config, "01_intro", "review", path, old_hash
        )
        path.write_text("# Intro\n\nEdited content here.")
        artifact = {"artifact_id": artifact_id, "name": "01_intro",
                    "content_hash": old_hash, "state": "review"}

        result = sync_section(
            driver=neo4j_driver, database=NEO4J_DB,
            project_dir=project_dir, domain_config=domain_config,
            section_path=path, artifact=artifact,
            dry_run=True, auto_stale=False,
        )

        assert result.suspected_oob is True
        assert result.prior_state == "review"

    def test_published_section_changed_sets_suspected_oob(
        self, neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
    ):
        path = _make_section(paper_dir, "02_methods.md", "# Methods\n\nOriginal methods.")
        old_hash = compute_file_hash(path)
        artifact_id = self._create_section_at_state(
            project_dir, neo4j_driver, domain_config, "02_methods", "published", path, old_hash
        )
        path.write_text("# Methods\n\nModified methods.")
        artifact = {"artifact_id": artifact_id, "name": "02_methods",
                    "content_hash": old_hash, "state": "published"}

        result = sync_section(
            driver=neo4j_driver, database=NEO4J_DB,
            project_dir=project_dir, domain_config=domain_config,
            section_path=path, artifact=artifact,
            dry_run=True, auto_stale=False,
        )

        assert result.suspected_oob is True
        assert result.prior_state == "published"

    def test_auto_stale_suppresses_suspected_oob(
        self, neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
    ):
        path = _make_section(paper_dir, "03_results.md", "# Results\n\nOriginal.")
        old_hash = compute_file_hash(path)
        artifact_id = self._create_section_at_state(
            project_dir, neo4j_driver, domain_config, "03_results", "review", path, old_hash
        )
        path.write_text("# Results\n\nModified results.")
        artifact = {"artifact_id": artifact_id, "name": "03_results",
                    "content_hash": old_hash, "state": "review"}

        result = sync_section(
            driver=neo4j_driver, database=NEO4J_DB,
            project_dir=project_dir, domain_config=domain_config,
            section_path=path, artifact=artifact,
            dry_run=True, auto_stale=True,
        )

        assert result.suspected_oob is False

    def test_draft_section_changed_does_not_set_oob(
        self, neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
    ):
        path = _make_section(paper_dir, "04_discussion.md", "# Discussion\n\nOriginal.")
        old_hash = compute_file_hash(path)
        artifact_id = self._create_section_at_state(
            project_dir, neo4j_driver, domain_config, "04_discussion", "draft", path, old_hash
        )
        path.write_text("# Discussion\n\nModified draft content.")
        artifact = {"artifact_id": artifact_id, "name": "04_discussion",
                    "content_hash": old_hash, "state": "draft"}

        result = sync_section(
            driver=neo4j_driver, database=NEO4J_DB,
            project_dir=project_dir, domain_config=domain_config,
            section_path=path, artifact=artifact,
            dry_run=True, auto_stale=False,
        )

        assert result.suspected_oob is False

    def test_unchanged_section_never_sets_oob(
        self, neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
    ):
        path = _make_section(paper_dir, "05_conclusion.md", "# Conclusion\n\nFinal thoughts.")
        current_hash = compute_file_hash(path)
        artifact_id = self._create_section_at_state(
            project_dir, neo4j_driver, domain_config, "05_conclusion", "published",
            path, current_hash
        )
        artifact = {"artifact_id": artifact_id, "name": "05_conclusion",
                    "content_hash": current_hash, "state": "published"}

        result = sync_section(
            driver=neo4j_driver, database=NEO4J_DB,
            project_dir=project_dir, domain_config=domain_config,
            section_path=path, artifact=artifact,
            dry_run=True, auto_stale=False,
        )

        assert result.status == "unchanged"
        assert result.suspected_oob is False


# ── Subsection sync integration tests ────────────────────────────────────────

@needs_neo4j
def test_sync_subsections_creates_nodes(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """_sync_subsections creates PaperSection nodes for each parsed subsection."""
    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\n## Experimental Setup\n\nContent A.\n\n## Data Collection\n\nContent B."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=compute_file_hash(path),
    )
    from seldon.core.artifacts import update_artifact
    update_artifact(project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                    artifact_id=parent_id, properties={"depth": 0}, actor="human", authority="accepted")

    parent_artifact = {"artifact_id": parent_id, "name": "03_methods",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}
    subsections = _parse_subsections(path, "03_methods", 0)

    _sync_subsections(
        driver=neo4j_driver,
        database=NEO4J_DB,
        project_dir=project_dir,
        domain_config=domain_config,
        parent_artifact=parent_artifact,
        subsections=subsections,
        dry_run=False,
        actor="human",
    )

    artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    assert "03_methods:experimental_setup" in artifacts
    assert "03_methods:data_collection" in artifacts

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rels = session.run(
            "MATCH (p:Artifact {artifact_id: $pid})-[:CONTAINS_SECTION]->(c:Artifact) "
            "RETURN c.name AS name ORDER BY c.sequence",
            pid=parent_id,
        ).data()
    names = [r["name"] for r in rels]
    assert names == ["03_methods:experimental_setup", "03_methods:data_collection"]


@needs_neo4j
def test_sync_subsections_unchanged_is_noop(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """Calling _sync_subsections twice with same content creates no duplicate artifacts."""
    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\n## Setup\n\nContent here."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=compute_file_hash(path),
    )
    parent_artifact = {"artifact_id": parent_id, "name": "03_methods",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}
    subsections = _parse_subsections(path, "03_methods", 0)

    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=subsections, dry_run=False, actor="human")

    events_after_first = event_count(project_dir)

    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=subsections, dry_run=False, actor="human")

    assert event_count(project_dir) == events_after_first


@needs_neo4j
def test_sync_subsections_updated_content_changes_hash(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """When subsection text changes, its content_hash is updated in the graph."""
    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\n## Setup\n\nOriginal content."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=compute_file_hash(path),
    )
    parent_artifact = {"artifact_id": parent_id, "name": "03_methods",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}

    subsections_v1 = _parse_subsections(path, "03_methods", 0)
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=subsections_v1, dry_run=False, actor="human")
    old_hash = subsections_v1[0]["content_hash"]

    path.write_text("# Methods\n\n## Setup\n\nEdited content.")
    subsections_v2 = _parse_subsections(path, "03_methods", 0)
    new_hash = subsections_v2[0]["content_hash"]
    assert old_hash != new_hash

    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=subsections_v2, dry_run=False, actor="human")

    artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    assert artifacts["03_methods:setup"]["content_hash"] == new_hash


@needs_neo4j
def test_sync_subsections_removed_heading_deprecated(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """A ## heading removed from a file marks its subsection artifact as deprecated."""
    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\n## Setup\n\nContent.\n\n## Teardown\n\nContent."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=compute_file_hash(path),
    )
    parent_artifact = {"artifact_id": parent_id, "name": "03_methods",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}

    # First sync — creates both subsections
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=_parse_subsections(path, "03_methods", 0),
                      dry_run=False, actor="human")

    # Remove "## Teardown" from file
    path.write_text("# Methods\n\n## Setup\n\nContent.")

    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=_parse_subsections(path, "03_methods", 0),
                      dry_run=False, actor="human")

    artifacts = get_paper_section_artifacts(neo4j_driver, NEO4J_DB)
    # Setup still present
    assert "03_methods:setup" in artifacts
    # Teardown deprecated
    teardown = artifacts.get("03_methods:teardown")
    assert teardown is not None
    assert teardown.get("deprecated") is True


@needs_neo4j
def test_sync_subsections_deprecated_not_double_deprecated(
    neo4j_driver, project_dir, domain_config, clean_test_db, paper_dir
):
    """A subsection already deprecated is not re-deprecated on subsequent syncs."""
    path = _make_section(
        paper_dir, "03_methods.md",
        "# Methods\n\n## Setup\n\nContent.\n\n## Teardown\n\nContent."
    )
    parent_id = _create_paper_section(
        project_dir, neo4j_driver, domain_config,
        name="03_methods", title="Methods",
        file_path=path, content_hash=compute_file_hash(path),
    )
    parent_artifact = {"artifact_id": parent_id, "name": "03_methods",
                       "content_hash": compute_file_hash(path), "state": "draft", "depth": 0}

    # First sync
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=_parse_subsections(path, "03_methods", 0),
                      dry_run=False, actor="human")

    # Remove Teardown
    path.write_text("# Methods\n\n## Setup\n\nContent.")
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=_parse_subsections(path, "03_methods", 0),
                      dry_run=False, actor="human")
    events_after_first_deprecation = event_count(project_dir)

    # Third sync — teardown still absent, should not produce new events
    _sync_subsections(driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
                      domain_config=domain_config, parent_artifact=parent_artifact,
                      subsections=_parse_subsections(path, "03_methods", 0),
                      dry_run=False, actor="human")

    assert event_count(project_dir) == events_after_first_deprecation
