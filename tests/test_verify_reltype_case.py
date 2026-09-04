"""Tests for relationship-type case canonicalisation and the two verify checks
added with it: `Relationship types` and `Task source files`.

The defect these guard against: `seldon-seldon-self` held both `INFORMS` (8) and
a lowercase `informs` (4). Every type-filtered query in the codebase names the
uppercase form, so the lowercase set was not merely untidy — it was invisible,
and any query touching it returned a confidently incomplete answer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.commands.verify import (
    TIER_A_CHECKS,
    check_relationship_types,
    check_task_source_files,
)
from seldon.core.graph import (
    canonical_rel_type,
    create_artifact,
    create_link,
    find_noncanonical_rel_types,
    get_relationships_of_type,
    relationship_exists,
)

from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE

#: Minimal project config; only the domain name is read by these checks.
RESEARCH_CONFIG = {"project": {"name": "test", "domain": "research"}}

pytestmark = pytest.mark.usefixtures("neo4j_available")


# ---------------------------------------------------------------------------
# Pure helpers — no Neo4j
# ---------------------------------------------------------------------------

class TestCanonicalRelType:
    def test_lowercase_becomes_uppercase(self):
        assert canonical_rel_type("informs") == "INFORMS"

    def test_uppercase_is_already_canonical(self):
        assert canonical_rel_type("INFORMS") == "INFORMS"

    def test_mixed_case_becomes_uppercase(self):
        assert canonical_rel_type("Informs") == "INFORMS"

    def test_underscores_survive(self):
        assert canonical_rel_type("generated_by") == "GENERATED_BY"


class TestTierAMembership:
    def test_relationship_types_is_not_tier_a(self):
        """Historical graph data must not block the machine gate CC tasks run."""
        assert "Relationship types" not in TIER_A_CHECKS

    def test_task_source_files_is_not_tier_a(self):
        assert "Task source files" not in TIER_A_CHECKS


# ---------------------------------------------------------------------------
# Graph primitives
# ---------------------------------------------------------------------------

def _seed_pair(session, from_id: str, to_id: str) -> None:
    create_artifact(session, "DesignNote", {"artifact_id": from_id, "state": "proposed"})
    create_artifact(
        session, "ArchitecturalDecision", {"artifact_id": to_id, "state": "proposed"}
    )


class TestFindNoncanonicalRelTypes:
    def test_clean_graph_reports_nothing(self, test_db_session):
        _seed_pair(test_db_session, "a", "b")
        create_link(test_db_session, "a", "b", "INFORMS", {})
        assert find_noncanonical_rel_types(test_db_session) == []

    def test_empty_graph_reports_nothing(self, test_db_session):
        assert find_noncanonical_rel_types(test_db_session) == []

    def test_lowercase_type_is_reported_with_count(self, test_db_session):
        _seed_pair(test_db_session, "a", "b")
        create_link(test_db_session, "a", "b", "informs", {})
        create_link(test_db_session, "a", "b", "informs", {})

        found = find_noncanonical_rel_types(test_db_session)

        assert found == [{"rel_type": "informs", "canonical": "INFORMS", "count": 2}]

    def test_mixed_case_pair_reports_only_the_offender(self, test_db_session):
        """The uppercase twin is correct and must not be flagged alongside it."""
        _seed_pair(test_db_session, "a", "b")
        create_link(test_db_session, "a", "b", "INFORMS", {})
        create_link(test_db_session, "a", "b", "informs", {})

        found = find_noncanonical_rel_types(test_db_session)

        assert [f["rel_type"] for f in found] == ["informs"]

    def test_type_with_no_remaining_relationships_is_not_reported(
        self, test_db_session
    ):
        """Neo4j keeps the type token after the last edge is deleted.

        A metadata-only implementation would keep reporting a type this project
        has already migrated away from, so post-migration verification would
        never go green.
        """
        from seldon.core.graph import remove_link

        _seed_pair(test_db_session, "a", "b")
        create_link(test_db_session, "a", "b", "informs", {})
        remove_link(test_db_session, "a", "b", "informs")

        assert find_noncanonical_rel_types(test_db_session) == []


class TestGetRelationshipsOfType:
    def test_matching_is_case_sensitive(self, test_db_session):
        _seed_pair(test_db_session, "a", "b")
        create_link(test_db_session, "a", "b", "INFORMS", {})
        create_link(test_db_session, "a", "b", "informs", {})

        lower = get_relationships_of_type(test_db_session, "informs")
        upper = get_relationships_of_type(test_db_session, "INFORMS")

        assert len(lower) == 1
        assert len(upper) == 1

    def test_returns_endpoints_and_properties(self, test_db_session):
        _seed_pair(test_db_session, "a", "b")
        create_link(test_db_session, "a", "b", "informs", {"topic": "case"})

        rels = get_relationships_of_type(test_db_session, "informs")

        assert rels[0]["from_id"] == "a"
        assert rels[0]["to_id"] == "b"
        assert rels[0]["properties"]["topic"] == "case"

    def test_unsafe_type_name_is_refused(self, test_db_session):
        with pytest.raises(ValueError):
            get_relationships_of_type(test_db_session, "INFORMS]->() DELETE r //")

    def test_empty_type_name_is_refused(self, test_db_session):
        with pytest.raises(ValueError):
            get_relationships_of_type(test_db_session, "")


class TestRelationshipExists:
    def test_true_for_exact_type(self, test_db_session):
        _seed_pair(test_db_session, "a", "b")
        create_link(test_db_session, "a", "b", "INFORMS", {})
        assert relationship_exists(test_db_session, "a", "b", "INFORMS")

    def test_false_for_other_case(self, test_db_session):
        _seed_pair(test_db_session, "a", "b")
        create_link(test_db_session, "a", "b", "informs", {})
        assert not relationship_exists(test_db_session, "a", "b", "INFORMS")

    def test_false_when_absent(self, test_db_session):
        _seed_pair(test_db_session, "a", "b")
        assert not relationship_exists(test_db_session, "a", "b", "INFORMS")


# ---------------------------------------------------------------------------
# Check 8: Relationship types
# ---------------------------------------------------------------------------

class TestCheckRelationshipTypes:
    def test_passes_on_canonical_graph(self, neo4j_driver, clean_test_db):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed_pair(session, "a", "b")
            create_link(session, "a", "b", "INFORMS", {})

        result = check_relationship_types(neo4j_driver, NEO4J_DB)

        assert result.symbol == "pass"
        assert result.name == "Relationship types"

    def test_fails_on_noncanonical_type(self, neo4j_driver, clean_test_db):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed_pair(session, "a", "b")
            create_link(session, "a", "b", "informs", {})

        result = check_relationship_types(neo4j_driver, NEO4J_DB)

        assert result.symbol == "fail"
        assert "informs" in " ".join(result.details)
        assert "INFORMS" in " ".join(result.details)

    def test_failure_names_the_migration_command(self, neo4j_driver, clean_test_db):
        from seldon.commands.verify import REL_TYPE_MIGRATION_CMD

        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed_pair(session, "a", "b")
            create_link(session, "a", "b", "informs", {})

        result = check_relationship_types(neo4j_driver, NEO4J_DB)

        assert any(REL_TYPE_MIGRATION_CMD in d for d in result.details)

    def test_is_not_offered_to_fix(self, neo4j_driver, clean_test_db):
        """A rename deletes and recreates edges; it must not ride on --fix."""
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _seed_pair(session, "a", "b")
            create_link(session, "a", "b", "informs", {})

        result = check_relationship_types(neo4j_driver, NEO4J_DB)

        assert result.fixable is False


# ---------------------------------------------------------------------------
# Check 9: Task source files
# ---------------------------------------------------------------------------

def _task(session, artifact_id: str, source_file: str, state: str = "completed"):
    create_artifact(
        session,
        "ResearchTask",
        {
            "artifact_id": artifact_id,
            "state": state,
            "source_file": source_file,
            "description": "seeded",
        },
    )


class TestCheckTaskSourceFiles:
    def test_passes_when_no_task_has_a_source_file(
        self, neo4j_driver, clean_test_db, tmp_path
    ):
        result = check_task_source_files(neo4j_driver, NEO4J_DB, tmp_path)
        assert result.symbol == "pass"

    def test_passes_when_every_source_file_resolves(
        self, neo4j_driver, clean_test_db, tmp_path
    ):
        (tmp_path / "cc_tasks").mkdir()
        (tmp_path / "cc_tasks" / "t.md").write_text("# T\n")
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/t.md")

        result = check_task_source_files(neo4j_driver, NEO4J_DB, tmp_path)

        assert result.symbol == "pass"
        assert "1" in result.summary

    def test_warns_on_open_task_with_missing_source_file(
        self, neo4j_driver, clean_test_db, tmp_path
    ):
        """An open task with no spec on disk is unexecutable — a live problem."""
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md", state="proposed")

        result = check_task_source_files(
            neo4j_driver, NEO4J_DB, tmp_path, RESEARCH_CONFIG
        )

        assert result.symbol == "warn"
        assert "cc_tasks/gone.md" in " ".join(result.details)

    def test_never_fails_so_lost_history_never_blocks(
        self, neo4j_driver, clean_test_db, tmp_path
    ):
        """A lost file is history; the session that trips this cannot fix it."""
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md", state="proposed")

        result = check_task_source_files(
            neo4j_driver, NEO4J_DB, tmp_path, RESEARCH_CONFIG
        )

        assert result.symbol != "fail"

    def test_terminal_task_with_lost_spec_is_settled_not_a_warning(
        self, neo4j_driver, clean_test_db, tmp_path
    ):
        """Losing the spec of a finished task does not un-finish it.

        A check that can never go green is a check people learn to ignore.
        """
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md", state="completed")

        result = check_task_source_files(
            neo4j_driver, NEO4J_DB, tmp_path, RESEARCH_CONFIG
        )

        assert result.symbol == "pass"
        assert "1 settled" in result.summary

    def test_superseded_task_counts_as_settled(
        self, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md", state="superseded")

        result = check_task_source_files(
            neo4j_driver, NEO4J_DB, tmp_path, RESEARCH_CONFIG
        )

        assert result.symbol == "pass"

    def test_open_and_settled_are_reported_separately(
        self, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/a.md", state="completed")
            _task(session, "t2", "cc_tasks/b.md", state="proposed")

        result = check_task_source_files(
            neo4j_driver, NEO4J_DB, tmp_path, RESEARCH_CONFIG
        )

        assert result.symbol == "warn"
        assert "cc_tasks/b.md" in " ".join(result.details)
        assert "1 settled" in " ".join(result.details)

    def test_detail_list_is_capped(self, neo4j_driver, clean_test_db, tmp_path):
        """37 permanent detail lines on every pre-commit run is noise, not signal."""
        from seldon.commands.verify import MAX_MISSING_DETAILS

        with neo4j_driver.session(database=NEO4J_DB) as session:
            for i in range(MAX_MISSING_DETAILS + 5):
                _task(session, f"t{i}", f"cc_tasks/gone{i:02d}.md", state="proposed")

        result = check_task_source_files(
            neo4j_driver, NEO4J_DB, tmp_path, RESEARCH_CONFIG
        )

        assert len(result.details) == MAX_MISSING_DETAILS + 1
        assert "and 5 more" in result.details[-1]

    def test_without_config_every_state_is_treated_as_open(
        self, neo4j_driver, clean_test_db, tmp_path
    ):
        """Over-reporting is the safe failure; silently passing is not."""
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", "cc_tasks/gone.md", state="completed")

        result = check_task_source_files(neo4j_driver, NEO4J_DB, tmp_path)

        assert result.symbol == "warn"


class TestOpenTaskStates:
    def test_read_from_the_domain_config(self):
        from seldon.commands.verify import _get_domain_config, open_task_states

        states = open_task_states(_get_domain_config(RESEARCH_CONFIG))

        assert states == {"proposed", "accepted", "in_progress", "blocked"}

    def test_completed_is_not_open_despite_having_a_successor(self):
        """`completed: [verified]` is finished, not awaiting execution. A
        leaf-node test would misclassify it."""
        from seldon.commands.verify import _get_domain_config, open_task_states

        assert "completed" not in open_task_states(_get_domain_config(RESEARCH_CONFIG))

    def test_absolute_source_file_is_honoured(
        self, neo4j_driver, clean_test_db, tmp_path
    ):
        real = tmp_path / "elsewhere.md"
        real.write_text("# T\n")
        with neo4j_driver.session(database=NEO4J_DB) as session:
            _task(session, "t1", str(real))

        result = check_task_source_files(neo4j_driver, NEO4J_DB, Path("/nonexistent"))

        assert result.symbol == "pass"

    def test_tasks_without_source_file_are_ignored(
        self, neo4j_driver, clean_test_db, tmp_path
    ):
        with neo4j_driver.session(database=NEO4J_DB) as session:
            create_artifact(
                session,
                "ResearchTask",
                {"artifact_id": "t1", "state": "proposed", "description": "no file"},
            )

        result = check_task_source_files(neo4j_driver, NEO4J_DB, tmp_path)

        assert result.symbol == "pass"
