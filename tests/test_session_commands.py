"""
Session briefing/closeout tests. Requires Neo4j.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact, get_artifacts_by_type
from seldon.core.events import read_events
from seldon.config import start_session, end_session, get_current_session
from seldon.commands.session import get_briefing_data
from seldon.commands.init import _BOOTSTRAP_TASKS, _create_bootstrap_tasks

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_task(project_dir, driver, domain_config, desc="test"):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": desc}, actor="human", authority="accepted",
    )


def _make_result(project_dir, driver, domain_config, value=0.5):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": value, "units": "score", "description": "test result"},
        actor="human", authority="accepted",
    )


def _make_script(project_dir, driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties={"name": "test_script", "path": "scripts/test.py"},
        actor="human", authority="accepted",
    )


# ── briefing queries ──────────────────────────────────────────────────────────

def test_briefing_open_tasks_query(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Briefing should find all tasks in open states."""
    _make_task(project_dir, neo4j_driver, domain_config, "task 1")
    _make_task(project_dir, neo4j_driver, domain_config, "task 2")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        records = session.run(
            "MATCH (t:ResearchTask) WHERE t.state IN ['proposed','accepted','in_progress','blocked'] RETURN t"
        ).data()
    assert len(records) == 2


def test_briefing_stale_results_query(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Briefing should find stale results."""
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="verified", new_state="stale",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        from seldon.core.graph import get_stale_artifacts
        stale = get_stale_artifacts(session)
    assert any(a["artifact_id"] == result_id for a in stale)


def test_briefing_incomplete_provenance_query(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Briefing should find Results with no GENERATED_BY Script."""
    result_with_script = _make_result(project_dir, neo4j_driver, domain_config, 0.8)
    result_no_script = _make_result(project_dir, neo4j_driver, domain_config, 0.9)
    script_id = _make_script(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_with_script, to_id=script_id,
        from_type="Result", to_type="Script",
        rel_type="generated_by", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        records = session.run(
            "MATCH (r:Result) WHERE NOT (r)-[:GENERATED_BY]->(:Script) "
            "AND NOT (r)-[:DERIVED_FROM]->() RETURN r"
        ).data()

    no_script_ids = {dict(r["r"])["artifact_id"] for r in records}
    assert result_no_script in no_script_ids
    assert result_with_script not in no_script_ids


def test_briefing_derived_from_satisfies_provenance(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """A Result with DERIVED_FROM link is NOT flagged as incomplete provenance."""
    result_id = _make_result(project_dir, neo4j_driver, domain_config, 3.32)
    notebook_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="LabNotebookEntry",
        properties={"summary": "analytical derivation"}, actor="human", authority="accepted",
    )

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_id, to_id=notebook_id,
        from_type="Result", to_type="LabNotebookEntry",
        rel_type="derived_from", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        records = session.run(
            "MATCH (r:Result) WHERE NOT (r)-[:GENERATED_BY]->(:Script) "
            "AND NOT (r)-[:DERIVED_FROM]->() RETURN r"
        ).data()

    incomplete_ids = {dict(r["r"])["artifact_id"] for r in records}
    assert result_id not in incomplete_ids


# ── closeout ──────────────────────────────────────────────────────────────────

def test_closeout_creates_lab_notebook_entry(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """closeout should create a LabNotebookEntry artifact."""
    session_id = start_session(project_dir)

    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 0.5, "units": "score", "description": "test result"},
        actor="human", authority="accepted",
        session_id=session_id,
    )

    entry_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="LabNotebookEntry",
        properties={"summary": "test session", "session_id": session_id},
        actor="human", authority="accepted",
        session_id=session_id,
    )

    end_session(project_dir)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        entries = get_artifacts_by_type(session, "LabNotebookEntry")
    assert len(entries) == 1
    assert entries[0]["artifact_id"] == entry_id


def test_closeout_session_event_count(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Events tagged with session_id should be countable."""
    session_id = start_session(project_dir)

    for _ in range(3):
        create_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="Result",
            properties={"value": 0.1, "units": "score", "description": "test result"},
            actor="human", authority="accepted",
            session_id=session_id,
        )

    end_session(project_dir)

    all_events = read_events(project_dir)
    session_events = [e for e in all_events if e.get("session_id") == session_id]
    created = [e for e in session_events if e["event_type"] == "artifact_created"]

    assert len(created) == 3


def test_start_session_sets_current_session(project_dir):
    """start_session sets the active session ID."""
    sid = start_session(project_dir)
    assert get_current_session(project_dir) == sid
    end_session(project_dir)


def test_events_tagged_with_session_id(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Events created while a session is active carry the session_id."""
    session_id = start_session(project_dir)

    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 0.5, "units": "score", "description": "test result"},
        actor="human", authority="accepted",
        session_id=session_id,
    )

    end_session(project_dir)

    all_events = read_events(project_dir)
    assert all_events[0]["session_id"] == session_id


# ── init bootstrap tasks ──────────────────────────────────────────────────────

class TestInitBootstrapTasks:
    def test_bootstrap_tasks_list_has_five_entries(self):
        assert len(_BOOTSTRAP_TASKS) == 5

    def test_bootstrap_task_ids_are_unique(self):
        prefixes = [t.split(":")[0] for t in _BOOTSTRAP_TASKS]
        assert len(set(prefixes)) == 5

    def test_bootstrap_task_descriptions_cover_expected_topics(self):
        combined = " ".join(_BOOTSTRAP_TASKS).lower()
        assert "bib" in combined         # bibliography
        assert "structure" in combined   # structure lock
        assert "pipeline" in combined    # build pipeline
        assert "deploy" in combined      # deploy verification
        assert "artifact" in combined    # artifact tracking

    def test_create_bootstrap_tasks_creates_five_research_tasks(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        _create_bootstrap_tasks(neo4j_driver, NEO4J_DB, project_dir)

        with neo4j_driver.session(database=NEO4J_DB) as session:
            records = session.run(
                "MATCH (t:Artifact:ResearchTask) RETURN t"
            ).data()

        assert len(records) == 5

    def test_create_bootstrap_tasks_descriptions_start_with_setup_prefix(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        _create_bootstrap_tasks(neo4j_driver, NEO4J_DB, project_dir)

        with neo4j_driver.session(database=NEO4J_DB) as session:
            descriptions = [
                r["t"]["description"]
                for r in session.run(
                    "MATCH (t:Artifact:ResearchTask) RETURN t ORDER BY t.description"
                ).data()
            ]

        setup_prefixed = [d for d in descriptions if d.startswith("SETUP-")]
        assert len(setup_prefixed) == 5

    def test_create_bootstrap_tasks_are_in_proposed_state(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        _create_bootstrap_tasks(neo4j_driver, NEO4J_DB, project_dir)

        with neo4j_driver.session(database=NEO4J_DB) as session:
            states = [
                r["t"]["state"]
                for r in session.run(
                    "MATCH (t:Artifact:ResearchTask) RETURN t"
                ).data()
            ]

        assert all(s == "proposed" for s in states)


# ── citation health briefing ──────────────────────────────────────────────────

class TestCitationHealthBriefing:
    def test_no_paper_sections_returns_zero_counts(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        data = get_briefing_data(neo4j_driver, NEO4J_DB, domain_config)
        assert data["citation_health"]["total_sections"] == 0
        assert data["citation_health"]["cited_sections"] == 0

    def test_uncited_sections_counted(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        # Create 2 PaperSection artifacts with no CITES edges
        for name in ("01_intro", "02_methods"):
            create_artifact(
                project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
                domain_config=domain_config, artifact_type="PaperSection",
                properties={"name": name, "title": name, "file_path": f"paper/sections/{name}.md"},
                actor="human", authority="accepted",
            )

        data = get_briefing_data(neo4j_driver, NEO4J_DB, domain_config)
        ch = data["citation_health"]
        assert ch["total_sections"] == 2
        assert ch["cited_sections"] == 0

    def test_cited_section_counted(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        section_id = create_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="PaperSection",
            properties={"name": "01_intro", "title": "Introduction",
                        "file_path": "paper/sections/01_intro.md"},
            actor="human", authority="accepted",
        )
        citation_id = create_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="Citation",
            properties={"name": "Smith2020", "key": "Smith2020", "title": "A Paper"},
            actor="human", authority="accepted",
        )
        # Add CITES edge manually
        with neo4j_driver.session(database=NEO4J_DB) as session:
            session.run(
                "MATCH (s:Artifact {artifact_id: $sid}), (c:Artifact {artifact_id: $cid}) "
                "MERGE (s)-[:CITES]->(c)",
                sid=section_id, cid=citation_id,
            )

        data = get_briefing_data(neo4j_driver, NEO4J_DB, domain_config)
        ch = data["citation_health"]
        assert ch["total_sections"] == 1
        assert ch["cited_sections"] == 1

    def test_partial_citation_coverage(
        self, neo4j_driver, project_dir, domain_config, clean_test_db
    ):
        """2 sections, 1 cited → total=2, cited=1."""
        s1_id = create_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="PaperSection",
            properties={"name": "01_intro", "title": "Intro",
                        "file_path": "paper/sections/01_intro.md"},
            actor="human", authority="accepted",
        )
        create_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="PaperSection",
            properties={"name": "02_methods", "title": "Methods",
                        "file_path": "paper/sections/02_methods.md"},
            actor="human", authority="accepted",
        )
        citation_id = create_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="Citation",
            properties={"name": "Jones2019", "key": "Jones2019", "title": "Work"},
            actor="human", authority="accepted",
        )
        with neo4j_driver.session(database=NEO4J_DB) as session:
            session.run(
                "MATCH (s:Artifact {artifact_id: $sid}), (c:Artifact {artifact_id: $cid}) "
                "MERGE (s)-[:CITES]->(c)",
                sid=s1_id, cid=citation_id,
            )

        data = get_briefing_data(neo4j_driver, NEO4J_DB, domain_config)
        ch = data["citation_health"]
        assert ch["total_sections"] == 2
        assert ch["cited_sections"] == 1
