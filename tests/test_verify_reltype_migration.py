"""Tests for scripts/migrations/2026-09-04_migrate_rel_type_case.py.

The migration is a *rename*: it must preserve the edge set exactly while
changing only its spelling, and it must record both halves as events so that a
full replay reproduces the post-migration graph.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from seldon.core.events import read_events
from seldon.core.graph import (
    create_artifact,
    create_link,
    find_noncanonical_rel_types,
    get_relationships_of_type,
)

from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE

SCRIPT = (
    Path(__file__).parent.parent
    / "scripts"
    / "migrations"
    / "2026-09-04_migrate_rel_type_case.py"
)

pytestmark = pytest.mark.usefixtures("neo4j_available")


def _load_script():
    """Import the date-prefixed migration script, whose filename is not a
    legal module name."""
    spec = importlib.util.spec_from_file_location("_reltype_migration", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    return _load_script()


def _seed(session, from_id="a", to_id="b"):
    create_artifact(session, "DesignNote", {"artifact_id": from_id, "state": "proposed"})
    create_artifact(
        session, "ArchitecturalDecision", {"artifact_id": to_id, "state": "proposed"}
    )


class TestBuildPlan:
    def test_clean_graph_yields_empty_plan(self, migration, test_db_session):
        _seed(test_db_session)
        create_link(test_db_session, "a", "b", "INFORMS", {})
        assert migration.build_plan(test_db_session) == []

    def test_noncanonical_edge_is_planned_as_a_rename(
        self, migration, test_db_session
    ):
        _seed(test_db_session)
        create_link(test_db_session, "a", "b", "informs", {})

        plan = migration.build_plan(test_db_session)

        assert len(plan) == 1
        assert plan[0]["from_rel_type"] == "informs"
        assert plan[0]["to_rel_type"] == "INFORMS"
        assert plan[0]["create_canonical"] is True

    def test_existing_canonical_twin_downgrades_to_a_drop(
        self, migration, test_db_session
    ):
        """Renaming onto an edge that already exists would create a duplicate."""
        _seed(test_db_session)
        create_link(test_db_session, "a", "b", "INFORMS", {})
        create_link(test_db_session, "a", "b", "informs", {})

        plan = migration.build_plan(test_db_session)

        assert len(plan) == 1
        assert plan[0]["create_canonical"] is False

    def test_relationship_properties_are_carried_into_the_plan(
        self, migration, test_db_session
    ):
        _seed(test_db_session)
        create_link(test_db_session, "a", "b", "informs", {"topic": "case"})

        plan = migration.build_plan(test_db_session)

        assert plan[0]["properties"]["topic"] == "case"


class TestApplyPlan:
    def _apply(self, migration, driver, project_dir):
        with driver.session(database=NEO4J_DB) as session:
            plan = migration.build_plan(session)
        return migration.apply_plan(
            project_dir, driver, NEO4J_DB, plan, {"INFORMS": "informs"}, None
        )

    def test_rename_preserves_the_edge_count(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed(session)
            create_link(session, "a", "b", "informs", {})

        self._apply(migration, neo4j_driver, tmp_path)

        with neo4j_driver.session(database=NEO4J_DB) as session:
            assert len(get_relationships_of_type(session, "INFORMS")) == 1
            assert get_relationships_of_type(session, "informs") == []

    def test_properties_survive_the_rename(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed(session)
            create_link(session, "a", "b", "informs", {"topic": "case"})

        self._apply(migration, neo4j_driver, tmp_path)

        with neo4j_driver.session(database=NEO4J_DB) as session:
            rels = get_relationships_of_type(session, "INFORMS")
        assert rels[0]["properties"]["topic"] == "case"

    def test_graph_is_canonical_afterwards(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed(session)
            create_link(session, "a", "b", "informs", {})

        self._apply(migration, neo4j_driver, tmp_path)

        with neo4j_driver.session(database=NEO4J_DB) as session:
            assert find_noncanonical_rel_types(session) == []

    def test_both_halves_are_recorded_as_events(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed(session)
            create_link(session, "a", "b", "informs", {})

        self._apply(migration, neo4j_driver, tmp_path)

        types = [e["event_type"] for e in read_events(tmp_path)]
        assert types == ["link_created", "link_case_migrated"]

    def test_link_created_event_records_the_domain_declared_name(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        """Replay uppercases, so recording the declared lowercase name matches
        the convention of every pre-existing link_created event."""
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed(session)
            create_link(session, "a", "b", "informs", {})

        self._apply(migration, neo4j_driver, tmp_path)

        created = [e for e in read_events(tmp_path) if e["event_type"] == "link_created"]
        assert created[0]["payload"]["rel_type"] == "informs"

    def test_case_migrated_event_records_both_spellings(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed(session)
            create_link(session, "a", "b", "informs", {})

        self._apply(migration, neo4j_driver, tmp_path)

        migrated = [
            e for e in read_events(tmp_path) if e["event_type"] == "link_case_migrated"
        ]
        assert migrated[0]["payload"]["from_rel_type"] == "informs"
        assert migrated[0]["payload"]["to_rel_type"] == "INFORMS"

    def test_duplicate_spelling_is_dropped_without_a_second_create(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed(session)
            create_link(session, "a", "b", "INFORMS", {})
            create_link(session, "a", "b", "informs", {})

        created, removed = self._apply(migration, neo4j_driver, tmp_path)

        assert (created, removed) == (0, 1)
        with neo4j_driver.session(database=NEO4J_DB) as session:
            assert len(get_relationships_of_type(session, "INFORMS")) == 1

    def test_rerunning_is_a_no_op(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed(session)
            create_link(session, "a", "b", "informs", {})

        self._apply(migration, neo4j_driver, tmp_path)
        second = self._apply(migration, neo4j_driver, tmp_path)

        assert second == (0, 0)
        assert len(read_events(tmp_path)) == 2

    def test_null_endpoint_is_refused_rather_than_silently_dropped(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        """A relationship on a non-Artifact node has no artifact_id, so its
        migration cannot be recorded as an event. Fail loud."""
        with neo4j_driver.session(database=NEO4J_DB) as session:
            session.run("CREATE (:Thing {n: 1})-[:informs]->(:Thing {n: 2})")
            plan = migration.build_plan(session)

        with pytest.raises(ValueError, match="null endpoint"):
            migration.apply_plan(
                tmp_path, neo4j_driver, NEO4J_DB, plan, {"INFORMS": "informs"}, None
            )


class TestMainSafety:
    def test_refuses_the_shared_ontology_master(self, migration, tmp_path):
        from seldon.config import ONTOLOGY_MASTER_DB

        (tmp_path / "seldon.yaml").write_text(
            f"project:\n  name: t\n  domain: research\n"
            f"neo4j:\n  database: {ONTOLOGY_MASTER_DB}\n  uri: bolt://localhost:7687\n"
            f"event_store:\n  path: seldon_events.jsonl\n"
        )

        code = migration.main(["--apply", "--project-dir", str(tmp_path)])

        assert code == 2

    def test_apply_and_dry_run_are_mutually_exclusive(self, migration, tmp_path):
        assert migration.main(["--apply", "--dry-run", "--project-dir", str(tmp_path)]) == 2

    def test_dry_run_writes_nothing(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        (tmp_path / "seldon.yaml").write_text(
            f"project:\n  name: t\n  domain: research\n"
            f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
            f"event_store:\n  path: seldon_events.jsonl\n"
        )
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed(session)
            create_link(session, "a", "b", "informs", {})

        code = migration.main(["--project-dir", str(tmp_path)])

        assert code == 0
        assert read_events(tmp_path) == []
        with neo4j_driver.session(database=NEO4J_DB) as session:
            assert len(find_noncanonical_rel_types(session)) == 1
