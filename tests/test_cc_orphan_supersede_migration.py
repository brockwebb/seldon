"""Tests for scripts/migrations/2026-09-04_supersede_orphan_source_file_tasks.py.

Two invariants matter more than the mechanics:

* No description is ever written. Two of this project's orphans cannot be
  re-derived; an invented description would launder a gap into an assertion.
* Terminal tasks are never relabelled. `superseded` is unreachable from
  `completed` / `verified` / `rejected` by design — relabelling a finished task
  would corrupt the honest completion record.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from seldon.core.graph import create_artifact
from seldon.domain.loader import load_domain_config

from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"

SCRIPT = (
    Path(__file__).parent.parent
    / "scripts"
    / "migrations"
    / "2026-09-04_supersede_orphan_source_file_tasks.py"
)

pytestmark = pytest.mark.usefixtures("neo4j_available")


def _load_script():
    spec = importlib.util.spec_from_file_location("_orphan_supersede", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    return _load_script()


@pytest.fixture(scope="module")
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _task(session, artifact_id, source_file, state="proposed"):
    create_artifact(
        session,
        "ResearchTask",
        {
            "artifact_id": artifact_id,
            "state": state,
            "source_file": source_file,
            "description": "seeded description",
        },
    )


def _write_config(tmp_path):
    (tmp_path / "seldon.yaml").write_text(
        f"project:\n  name: t\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        f"event_store:\n  path: seldon_events.jsonl\n"
    )


class TestEligibleStates:
    def test_read_from_the_domain_config_not_hardcoded(self, migration, domain_config):
        assert migration.eligible_states(domain_config) == {
            "proposed",
            "accepted",
            "in_progress",
            "blocked",
        }

    def test_terminal_states_are_excluded(self, migration, domain_config):
        states = migration.eligible_states(domain_config)
        assert "completed" not in states
        assert "verified" not in states
        assert "rejected" not in states


class TestFindOrphans:
    def test_task_whose_file_exists_is_not_an_orphan(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        (tmp_path / "cc_tasks").mkdir()
        (tmp_path / "cc_tasks" / "t.md").write_text("# T\n")
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/t.md")

        assert migration.find_orphans(neo4j_driver, NEO4J_DB, tmp_path) == []

    def test_task_whose_file_is_missing_is_an_orphan(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md")

        orphans = migration.find_orphans(neo4j_driver, NEO4J_DB, tmp_path)

        assert [o["artifact_id"] for o in orphans] == ["t1"]

    def test_task_with_no_source_file_is_never_an_orphan(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            create_artifact(
                session,
                "ResearchTask",
                {"artifact_id": "t1", "state": "proposed", "description": "x"},
            )

        assert migration.find_orphans(neo4j_driver, NEO4J_DB, tmp_path) == []


class TestMain:
    def test_dry_run_changes_nothing(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        _write_config(tmp_path)
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md")

        assert migration.main(["--project-dir", str(tmp_path)]) == 0

        with neo4j_driver.session(database=NEO4J_DB) as session:
            state = session.run(
                "MATCH (t:Artifact {artifact_id: 't1'}) RETURN t.state AS s"
            ).single()["s"]
        assert state == "proposed"

    def test_apply_supersedes_the_open_orphan(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        _write_config(tmp_path)
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md")

        assert migration.main(["--apply", "--project-dir", str(tmp_path)]) == 0

        with neo4j_driver.session(database=NEO4J_DB) as session:
            node = session.run(
                "MATCH (t:Artifact {artifact_id: 't1'}) RETURN t"
            ).single()["t"]
        assert node["state"] == "superseded"
        assert node["terminal_reason"] == migration.REASON

    def test_description_is_never_touched(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        _write_config(tmp_path)
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md")

        migration.main(["--apply", "--project-dir", str(tmp_path)])

        with neo4j_driver.session(database=NEO4J_DB) as session:
            desc = session.run(
                "MATCH (t:Artifact {artifact_id: 't1'}) RETURN t.description AS d"
            ).single()["d"]
        assert desc == "seeded description"

    def test_completed_orphan_is_left_alone(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        _write_config(tmp_path)
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md", state="completed")

        assert migration.main(["--apply", "--project-dir", str(tmp_path)]) == 0

        with neo4j_driver.session(database=NEO4J_DB) as session:
            state = session.run(
                "MATCH (t:Artifact {artifact_id: 't1'}) RETURN t.state AS s"
            ).single()["s"]
        assert state == "completed"

    def test_rejected_orphan_is_left_alone(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        _write_config(tmp_path)
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md", state="rejected")

        migration.main(["--apply", "--project-dir", str(tmp_path)])

        with neo4j_driver.session(database=NEO4J_DB) as session:
            state = session.run(
                "MATCH (t:Artifact {artifact_id: 't1'}) RETURN t.state AS s"
            ).single()["s"]
        assert state == "rejected"

    def test_rerunning_is_a_no_op(
        self, migration, neo4j_driver, clean_test_db, tmp_path
    ):
        _write_config(tmp_path)
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md")

        migration.main(["--apply", "--project-dir", str(tmp_path)])
        events_after_first = (tmp_path / "seldon_events.jsonl").read_text()
        migration.main(["--apply", "--project-dir", str(tmp_path)])

        assert (tmp_path / "seldon_events.jsonl").read_text() == events_after_first

    def test_plan_names_both_partitions(
        self, migration, neo4j_driver, clean_test_db, tmp_path, capsys
    ):
        _write_config(tmp_path)
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/open.md", state="proposed")
            _task(session, "t2", "cc_tasks/done.md", state="completed")

        migration.main(["--project-dir", str(tmp_path)])

        out = capsys.readouterr().out
        assert "WILL SUPERSEDE (1)" in out
        assert "WILL NOT TOUCH (1)" in out
        assert migration.REASON in out

    def test_apply_and_dry_run_are_mutually_exclusive(self, migration, tmp_path):
        _write_config(tmp_path)
        assert (
            migration.main(["--apply", "--dry-run", "--project-dir", str(tmp_path)])
            == 2
        )
