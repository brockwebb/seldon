"""Tests for the shared ontology system (AD-017).

Covers:
  8a. Parser tests (no Neo4j required)
  8b. Master ingest tests (require Neo4j)
  8c. Sync tests (require Neo4j, two databases)
  8d. Write protection tests (require Neo4j for update guard)
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from seldon.ontology.parser import ParsedVocabulary, parse_vocabulary

VOCAB_PATH = Path(__file__).parent.parent / "ontology" / "validity" / "VALIDITY_VOCABULARY.md"

# Test database names — never touch production databases
TEST_MASTER_DB = "seldon-test"
TEST_PROJECT_DB = "seldon-test-project"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project_config(tmp_path, database="seldon-test", with_shared_ontology=True):
    """Write a minimal seldon.yaml and event store file for testing."""
    config = {
        "project": {"name": "test", "slug": "test", "domain": "research"},
        "neo4j": {"uri": "bolt://localhost:7687", "database": database},
        "event_store": {"path": "seldon_events.jsonl"},
    }
    if with_shared_ontology:
        config["shared_ontology"] = {
            "inheritance": "read-only",
            "source": ".",
            "vocabularies": [],
        }
    (tmp_path / "seldon.yaml").write_text(yaml.dump(config))
    (tmp_path / "seldon_events.jsonl").touch()
    return config


def _do_ingest(monkeypatch, vocab_path=None):
    """Run ingest via CliRunner with monkeypatched master DB and vocab path.

    Returns the CliRunner result object.
    """
    from click.testing import CliRunner
    from seldon.commands.ontology import ontology_group

    monkeypatch.setattr("seldon.commands.ontology.ONTOLOGY_MASTER_DB", TEST_MASTER_DB)
    if vocab_path is None:
        vocab_path = VOCAB_PATH
    monkeypatch.setenv("SELDON_ONTOLOGY_PATH", str(vocab_path))

    runner = CliRunner()
    result = runner.invoke(ontology_group, ["ingest"])
    return result


# ===========================================================================
# 8a. Parser tests (NO Neo4j required)
# ===========================================================================


class TestParser:
    """Test VALIDITY_VOCABULARY.md parser — pure Python, no database."""

    @pytest.fixture(autouse=True)
    def _parse(self):
        self.vocab: ParsedVocabulary = parse_vocabulary(VOCAB_PATH)

    def test_parse_sfv_term(self):
        """SFV framework term exists with correct term_id, name, category."""
        sfv = [t for t in self.vocab.terms if t.term_id == "ontology:validity:SFV"]
        assert len(sfv) == 1
        term = sfv[0]
        assert term.name == "State Fidelity Validity"
        assert term.category == "framework"
        assert term.namespace == "ontology:validity"

    def test_parse_sub_dimensions(self):
        """5 sub-dimensions, each with shorthand in extra dict."""
        subs = [t for t in self.vocab.terms if t.category == "sub_dimension"]
        assert len(subs) == 5
        expected_shorthands = {"TC", "SP", "CF", "SC", "SCoh"}
        actual_shorthands = {t.extra["shorthand"] for t in subs}
        assert actual_shorthands == expected_shorthands
        # Verify term_id pattern
        for t in subs:
            assert t.term_id.startswith("ontology:validity:SFV:")

    def test_parse_threats(self):
        """5 threats T1-T5 with correct term_ids and threat_number in extra."""
        threats = [t for t in self.vocab.terms if t.category == "threat"]
        assert len(threats) == 5
        numbers = {t.extra["threat_number"] for t in threats}
        assert numbers == {"T1", "T2", "T3", "T4", "T5"}
        for t in threats:
            assert t.term_id.startswith("ontology:validity:SFV:")

    def test_parse_severity_scale(self):
        """4 severity levels."""
        severity = [t for t in self.vocab.terms if t.category == "severity"]
        assert len(severity) == 4

    def test_parse_countermeasures(self):
        """7 countermeasures, each with threat_refs in extra."""
        cms = [t for t in self.vocab.terms if t.category == "countermeasure"]
        assert len(cms) == 7
        for cm in cms:
            assert "threat_refs" in cm.extra

    def test_parse_metrics(self):
        """6 metrics."""
        metrics = [t for t in self.vocab.terms if t.category == "metric"]
        assert len(metrics) == 6

    def test_parse_classical_validity(self):
        """4 classical validity types."""
        classical = [t for t in self.vocab.terms if t.category == "classical_validity"]
        assert len(classical) == 4

    def test_parse_terminology_decisions(self):
        """Confabulation and reliability_vs_validity entries."""
        terminology = [t for t in self.vocab.terms if t.category == "terminology_decision"]
        ids = {t.term_id for t in terminology}
        assert "ontology:validity:terminology:confabulation" in ids
        assert "ontology:validity:terminology:reliability_vs_validity" in ids

    def test_parse_framework_terms(self):
        """TEVV, TSE, FCSM framework terms."""
        fw = [t for t in self.vocab.terms if t.category == "framework_term"]
        ids = {t.term_id for t in fw}
        assert "ontology:validity:framework:tevv" in ids
        assert "ontology:validity:framework:tse" in ids
        assert "ontology:validity:framework:fcsm" in ids

    def test_parse_relationships(self):
        """Relationship counts match expected topology."""
        by_type: dict[str, int] = {}
        for r in self.vocab.relationships:
            by_type[r.rel_type] = by_type.get(r.rel_type, 0) + 1

        assert by_type.get("defines_sub_dimension", 0) == 5
        assert by_type.get("defines_threat", 0) == 5
        assert by_type.get("addresses_threat", 0) >= 1
        assert by_type.get("measures_threat", 0) >= 1
        assert by_type.get("precondition_for", 0) == 4

    def test_content_hash_stable(self):
        """Same file path parsed twice produces the same content_hash."""
        vocab2 = parse_vocabulary(VOCAB_PATH)
        assert self.vocab.content_hash == vocab2.content_hash

    def test_content_hash_changes(self, tmp_path):
        """Modified copy of file produces a different content_hash."""
        modified = tmp_path / "VALIDITY_VOCABULARY.md"
        shutil.copy(VOCAB_PATH, modified)
        text = modified.read_text()
        # Append content so the hash changes without breaking parsing
        text += "\n<!-- test modification for hash change -->\n"
        modified.write_text(text)
        vocab_modified = parse_vocabulary(modified)
        assert self.vocab.content_hash != vocab_modified.content_hash


# ===========================================================================
# 8b. Master ingest tests (REQUIRE Neo4j)
# ===========================================================================


@pytest.fixture
def clean_master_db(neo4j_driver):
    """Clear seldon-test (used as master substitute) before each test."""
    with neo4j_driver.session(database="system") as s:
        s.run(f"CREATE DATABASE `{TEST_MASTER_DB}` IF NOT EXISTS WAIT")
    with neo4j_driver.session(database=TEST_MASTER_DB) as s:
        s.run("MATCH (n) DETACH DELETE n")
    yield neo4j_driver


class TestIngest:
    """Test ontology ingest into master database (seldon-test as substitute)."""

    def test_ingest_creates_meta_node(self, clean_master_db, monkeypatch):
        """After ingest, _OntologyMeta {key: 'master'} exists with epoch >= 1."""
        result = _do_ingest(monkeypatch)
        assert result.exit_code == 0, f"ingest failed: {result.output}"

        with clean_master_db.session(database=TEST_MASTER_DB) as s:
            rec = s.run(
                "MATCH (m:_OntologyMeta {key: 'master'}) RETURN m.epoch AS epoch"
            ).single()
        assert rec is not None, "_OntologyMeta node not found"
        assert rec["epoch"] >= 1

    def test_ingest_creates_artifacts(self, clean_master_db, monkeypatch):
        """After ingest, OntologyTerm nodes exist in the test master DB."""
        _do_ingest(monkeypatch)

        with clean_master_db.session(database=TEST_MASTER_DB) as s:
            count = s.run(
                "MATCH (a:Artifact:OntologyTerm) RETURN count(a) AS cnt"
            ).single()["cnt"]
        assert count > 0, "No OntologyTerm nodes created"

        # Spot-check: SFV term should have the expected properties
        with clean_master_db.session(database=TEST_MASTER_DB) as s:
            sfv = s.run(
                "MATCH (a:Artifact:OntologyTerm {term_id: 'ontology:validity:SFV'}) RETURN a"
            ).single()
        assert sfv is not None, "SFV term not found after ingest"
        props = dict(sfv["a"])
        assert props["name"] == "State Fidelity Validity"
        assert props["category"] == "framework"
        assert props["state"] == "active"

    def test_ingest_creates_relationships(self, clean_master_db, monkeypatch):
        """After ingest, relationship edges between OntologyTerm nodes exist."""
        _do_ingest(monkeypatch)

        with clean_master_db.session(database=TEST_MASTER_DB) as s:
            count = s.run(
                "MATCH (:Artifact:OntologyTerm)-[r]->(:Artifact:OntologyTerm) "
                "RETURN count(r) AS cnt"
            ).single()["cnt"]
        assert count > 0, "No relationships created"

    def test_ingest_increments_epoch(self, clean_master_db, monkeypatch):
        """Ingest twice; epoch should be 2 after the second run."""
        _do_ingest(monkeypatch)
        _do_ingest(monkeypatch)

        with clean_master_db.session(database=TEST_MASTER_DB) as s:
            epoch = s.run(
                "MATCH (m:_OntologyMeta {key: 'master'}) RETURN m.epoch AS epoch"
            ).single()["epoch"]
        assert epoch == 2

    def test_ingest_idempotent_no_changes(self, clean_master_db, monkeypatch):
        """Second ingest of the same file reports 0 new, 0 updated."""
        _do_ingest(monkeypatch)
        result = _do_ingest(monkeypatch)
        assert result.exit_code == 0
        # Output should report 0 new and 0 updated (all unchanged)
        assert "0 new" in result.output
        assert "updated 0" in result.output

    def test_ingest_detects_definition_change(self, clean_master_db, monkeypatch, tmp_path):
        """Modifying a definition and re-ingesting detects the update."""
        _do_ingest(monkeypatch)

        # Create a modified copy
        modified = tmp_path / "VALIDITY_VOCABULARY.md"
        shutil.copy(VOCAB_PATH, modified)
        text = modified.read_text()
        # Change a threat definition to trigger update detection
        text = text.replace(
            "State Fidelity Validity (SFV):**",
            "State Fidelity Validity (SFV):** MODIFIED_DEFINITION_FOR_TEST",
        )
        modified.write_text(text)

        result = _do_ingest(monkeypatch, vocab_path=modified)
        assert result.exit_code == 0
        # Should report at least 1 updated
        assert "updated" in result.output
        # The SFV term definition changed, so updated should be >= 1
        # Parse the output for "updated N" where N >= 1
        import re
        match = re.search(r"updated (\d+)", result.output)
        assert match is not None, f"Could not find 'updated N' in output: {result.output}"
        assert int(match.group(1)) >= 1

    def test_ingest_sets_active_state(self, clean_master_db, monkeypatch):
        """All ingested terms have state == 'active'."""
        _do_ingest(monkeypatch)

        with clean_master_db.session(database=TEST_MASTER_DB) as s:
            records = s.run(
                "MATCH (a:Artifact:OntologyTerm) "
                "WHERE a.state <> 'active' "
                "RETURN count(a) AS cnt"
            ).single()["cnt"]
        assert records == 0, "Some terms do not have state == 'active'"


# ===========================================================================
# 8c. Sync tests (REQUIRE Neo4j — two databases)
# ===========================================================================


@pytest.fixture
def two_clean_dbs(neo4j_driver):
    """Create and clear both test databases (master + project)."""
    for db in [TEST_MASTER_DB, TEST_PROJECT_DB]:
        with neo4j_driver.session(database="system") as s:
            s.run(f"CREATE DATABASE `{db}` IF NOT EXISTS WAIT")
        with neo4j_driver.session(database=db) as s:
            s.run("MATCH (n) DETACH DELETE n")
    yield neo4j_driver


class TestSync:
    """Test ontology sync from master to project database."""

    def _ingest_then_sync(self, driver, monkeypatch, tmp_path):
        """Helper: ingest to master, then sync to project. Returns sync result dict."""
        from seldon.commands.ontology import _do_sync

        # Ingest into master (seldon-test)
        result = _do_ingest(monkeypatch)
        assert result.exit_code == 0, f"ingest failed: {result.output}"

        # Sync to project DB
        config = _make_project_config(tmp_path, database=TEST_PROJECT_DB)
        monkeypatch.setattr("seldon.commands.ontology.ONTOLOGY_MASTER_DB", TEST_MASTER_DB)
        return _do_sync(driver, TEST_PROJECT_DB, tmp_path, config)

    def test_sync_first_time(self, two_clean_dbs, monkeypatch, tmp_path):
        """After ingest + sync, OntologyTerm nodes appear in project DB."""
        sync_result = self._ingest_then_sync(two_clean_dbs, monkeypatch, tmp_path)

        assert sync_result["new"] > 0
        assert sync_result["epoch"] >= 1

        # Verify terms exist in project DB
        with two_clean_dbs.session(database=TEST_PROJECT_DB) as s:
            count = s.run(
                "MATCH (a:Artifact:OntologyTerm) RETURN count(a) AS cnt"
            ).single()["cnt"]
        assert count > 0

        # Verify replica meta
        with two_clean_dbs.session(database=TEST_PROJECT_DB) as s:
            meta = s.run(
                "MATCH (m:_OntologyReplicaMeta {key: 'replica'}) "
                "RETURN m.last_epoch AS epoch"
            ).single()
        assert meta is not None
        assert meta["epoch"] == sync_result["epoch"]

    def test_sync_already_current(self, two_clean_dbs, monkeypatch, tmp_path):
        """Second sync reports 'already up to date'."""
        from seldon.commands.ontology import _do_sync

        self._ingest_then_sync(two_clean_dbs, monkeypatch, tmp_path)

        # Sync again — should be up to date
        config = _make_project_config(tmp_path, database=TEST_PROJECT_DB)
        monkeypatch.setattr("seldon.commands.ontology.ONTOLOGY_MASTER_DB", TEST_MASTER_DB)
        result2 = _do_sync(two_clean_dbs, TEST_PROJECT_DB, tmp_path, config)
        assert result2.get("up_to_date") is True

    def test_sync_preserves_artifact_ids(self, two_clean_dbs, monkeypatch, tmp_path):
        """artifact_ids in master and project are identical for the same term_id."""
        self._ingest_then_sync(two_clean_dbs, monkeypatch, tmp_path)

        # Collect artifact_ids from master
        with two_clean_dbs.session(database=TEST_MASTER_DB) as s:
            master_map = {
                r["tid"]: r["aid"]
                for r in s.run(
                    "MATCH (a:Artifact:OntologyTerm) "
                    "RETURN a.term_id AS tid, a.artifact_id AS aid"
                ).data()
            }

        # Collect artifact_ids from project
        with two_clean_dbs.session(database=TEST_PROJECT_DB) as s:
            project_map = {
                r["tid"]: r["aid"]
                for r in s.run(
                    "MATCH (a:Artifact:OntologyTerm) "
                    "RETURN a.term_id AS tid, a.artifact_id AS aid"
                ).data()
            }

        # Every term in project should have the same artifact_id as in master
        for tid in project_map:
            assert tid in master_map, f"term_id {tid} in project but not master"
            assert project_map[tid] == master_map[tid], (
                f"artifact_id mismatch for {tid}: "
                f"master={master_map[tid]}, project={project_map[tid]}"
            )

    def test_sync_marks_terms_readonly(self, two_clean_dbs, monkeypatch, tmp_path):
        """After sync, all OntologyTerm nodes in project have inheritance == 'read-only'."""
        self._ingest_then_sync(two_clean_dbs, monkeypatch, tmp_path)

        with two_clean_dbs.session(database=TEST_PROJECT_DB) as s:
            records = s.run(
                "MATCH (a:Artifact:OntologyTerm) "
                "WHERE a.inheritance <> 'read-only' OR a.inheritance IS NULL "
                "RETURN count(a) AS cnt"
            ).single()["cnt"]
        assert records == 0, "Some synced terms missing inheritance == 'read-only'"


# ===========================================================================
# 8d. Write protection tests
# ===========================================================================


class TestWriteProtection:
    """Test that OntologyTerm creation/update is blocked in read-only projects."""

    def test_create_ontology_term_blocked_in_project(self, tmp_path, neo4j_driver):
        """Creating OntologyTerm in a project with read-only inheritance raises ValueError."""
        from seldon.domain.loader import load_domain_config
        from seldon.core.artifacts import create_artifact

        _make_project_config(tmp_path, with_shared_ontology=True)
        domain_yaml = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
        domain_config = load_domain_config(domain_yaml)

        with pytest.raises(ValueError, match="read-only|inherited from the shared ontology"):
            create_artifact(
                project_dir=tmp_path,
                driver=neo4j_driver,
                database=TEST_MASTER_DB,
                domain_config=domain_config,
                artifact_type="OntologyTerm",
                properties={
                    "term_id": "ontology:test:blocked",
                    "name": "Blocked Term",
                    "definition": "Should not be created",
                    "category": "test",
                    "source_vocabulary": "test.md",
                },
                actor="test",
                authority="test",
            )

    def test_update_ontology_term_blocked_in_project(
        self, tmp_path, neo4j_driver, clean_test_db
    ):
        """Updating an OntologyTerm in a read-only project raises ValueError."""
        from seldon.core import graph as graph_mod
        from seldon.core.artifacts import update_artifact

        _make_project_config(tmp_path, with_shared_ontology=True)

        # Bypass write protection: create the term directly via graph module
        import uuid

        artifact_id = str(uuid.uuid4())
        with neo4j_driver.session(database=TEST_MASTER_DB) as session:
            graph_mod.create_artifact(session, "OntologyTerm", {
                "artifact_id": artifact_id,
                "term_id": "ontology:test:update_blocked",
                "name": "Update Blocked",
                "definition": "Original definition",
                "category": "test",
                "source_vocabulary": "test.md",
                "state": "active",
            })

        with pytest.raises(ValueError, match="read-only"):
            update_artifact(
                project_dir=tmp_path,
                driver=neo4j_driver,
                database=TEST_MASTER_DB,
                artifact_id=artifact_id,
                properties={"definition": "Modified definition"},
                actor="test",
                authority="test",
            )

    def test_create_other_type_not_blocked(self, tmp_path, neo4j_driver, clean_test_db):
        """Creating a non-OntologyTerm artifact succeeds even with read-only ontology."""
        from seldon.domain.loader import load_domain_config
        from seldon.core.artifacts import create_artifact

        _make_project_config(tmp_path, with_shared_ontology=True)
        domain_yaml = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
        domain_config = load_domain_config(domain_yaml)

        # ResearchTask should not be blocked
        artifact_id = create_artifact(
            project_dir=tmp_path,
            driver=neo4j_driver,
            database=TEST_MASTER_DB,
            domain_config=domain_config,
            artifact_type="ResearchTask",
            properties={
                "name": "Test Task",
                "description": "Testing write protection scope",
                "goal": "Verify non-ontology types pass through",
            },
            actor="test",
            authority="test",
        )
        assert artifact_id is not None

    def test_create_ontology_term_allowed_without_config(
        self, tmp_path, neo4j_driver, clean_test_db
    ):
        """Without seldon.yaml, OntologyTerm creation is allowed (e.g., master DB context)."""
        from seldon.domain.loader import load_domain_config
        from seldon.core.artifacts import create_artifact

        # Do NOT create seldon.yaml — simulates running in master DB context
        domain_yaml = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
        domain_config = load_domain_config(domain_yaml)

        artifact_id = create_artifact(
            project_dir=tmp_path,
            driver=neo4j_driver,
            database=TEST_MASTER_DB,
            domain_config=domain_config,
            artifact_type="OntologyTerm",
            properties={
                "term_id": "ontology:test:allowed",
                "name": "Allowed Term",
                "definition": "Should be created when no config exists",
                "category": "test",
                "source_vocabulary": "test.md",
            },
            actor="test",
            authority="test",
        )
        assert artifact_id is not None
