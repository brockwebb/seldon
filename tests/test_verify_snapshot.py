"""
Tests for snapshot artifacts and the directory guard in `seldon verify` (AD-027).

Task: cc_tasks/2026-09-02_snapshot_artifacts_verify.md. Each verify-side behaviour has a
positive control: the same artifact with `snapshot` cleared must FAIL, so a test that
passes because the check silently stopped comparing would be caught.

Requires Neo4j for the graph-backed cases (seldon-test database, cleaned per test).
The CLI parsing and core validator cases need no database.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from seldon.commands.artifact import _parse_properties
from seldon.commands.verify import check_file_hashes
from seldon.core.artifacts import (
    create_artifact,
    update_artifact,
    validate_snapshot_property,
)
from seldon.domain.loader import load_domain_config
from seldon.paper.sync import compute_file_hash, sync_section

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _register_datafile(neo4j_driver, project_dir, domain_config, name, rel_path, *, snapshot=None):
    """Write a file under project_dir and register it as a DataFile with its current hash."""
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"{name}: original\n", encoding="utf-8")
    props = {"name": name, "path": rel_path, "content_hash": _sha(path)}
    if snapshot is not None:
        props["snapshot"] = snapshot
    artifact_id = create_artifact(
        project_dir=project_dir,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="DataFile",
        properties=props,
        actor="test",
        authority="accepted",
    )
    return artifact_id, path


# ---------------------------------------------------------------------------
# No-database cases: parsing and validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("literal,expected", [
    ("true", True), ("True", True), ("1", True), ("yes", True),
    ("false", False), ("FALSE", False), ("0", False), ("no", False),
])
def test_cli_parses_snapshot_literals_to_bool(literal, expected):
    props = _parse_properties((f"snapshot={literal}",))
    assert props["snapshot"] is expected


def test_cli_leaves_unknown_snapshot_literal_for_validator():
    """An unrecognised literal is not coerced; the core validator must refuse it."""
    props = _parse_properties(("snapshot=maybe",))
    assert props["snapshot"] == "maybe"
    with pytest.raises(ValueError, match="snapshot"):
        validate_snapshot_property(props)


def test_cli_numeric_coercion_unchanged_for_other_keys():
    props = _parse_properties(("row_count=12", "name=x"))
    assert props["row_count"] == 12 and props["name"] == "x"


@pytest.mark.parametrize("bad", ["yes", 1, 0, "true", None])
def test_validator_rejects_non_bool(bad):
    with pytest.raises(ValueError, match="snapshot"):
        validate_snapshot_property({"snapshot": bad})


def test_validator_accepts_bool_and_absence():
    validate_snapshot_property({"snapshot": True})
    validate_snapshot_property({"snapshot": False})
    validate_snapshot_property({})


# ---------------------------------------------------------------------------
# Graph-backed cases
# ---------------------------------------------------------------------------

pytestmark_db = pytest.mark.usefixtures("neo4j_available")


@pytestmark_db
def test_create_rejects_non_bool_snapshot(neo4j_driver, project_dir, domain_config, clean_test_db):
    with pytest.raises(ValueError, match="snapshot"):
        create_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="DataFile",
            properties={"name": "x", "path": "x.txt", "snapshot": "true"},
            actor="test", authority="accepted",
        )


@pytestmark_db
def test_update_rejects_non_bool_snapshot(neo4j_driver, project_dir, domain_config, clean_test_db):
    artifact_id, _ = _register_datafile(neo4j_driver, project_dir, domain_config, "df", "data/df.txt")
    with pytest.raises(ValueError, match="snapshot"):
        update_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            artifact_id=artifact_id, properties={"snapshot": "yes"},
            actor="test", authority="accepted",
        )


@pytestmark_db
def test_snapshot_artifact_with_drift_passes(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Snapshot artifact whose file changed -> pass, reported informationally."""
    _, path = _register_datafile(
        neo4j_driver, project_dir, domain_config, "schema-v0.1", "kg/schema.yaml", snapshot=True
    )
    path.write_text("schema: v0.3\n", encoding="utf-8")

    result = check_file_hashes(neo4j_driver, NEO4J_DB, project_dir)
    assert result.symbol == "pass"
    assert "1 snapshot artifact, drift not checked" in result.summary
    assert "schema.yaml" not in result.details


@pytestmark_db
def test_positive_control_clearing_snapshot_fails(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Same artifact, `snapshot` cleared -> the drift is detected again."""
    artifact_id, path = _register_datafile(
        neo4j_driver, project_dir, domain_config, "schema-v0.1", "kg/schema.yaml", snapshot=True
    )
    path.write_text("schema: v0.3\n", encoding="utf-8")
    assert check_file_hashes(neo4j_driver, NEO4J_DB, project_dir).symbol == "pass"

    update_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        artifact_id=artifact_id, properties={"snapshot": False},
        actor="test", authority="accepted",
    )
    result = check_file_hashes(neo4j_driver, NEO4J_DB, project_dir)
    assert result.symbol == "fail"
    assert "schema.yaml" in result.details
    assert result.fixable is True
    assert "snapshot" not in result.summary


@pytestmark_db
def test_non_snapshot_artifact_still_fails_on_drift(neo4j_driver, project_dir, domain_config, clean_test_db):
    """A snapshot sibling in the same graph does not mask drift on an ordinary artifact."""
    _register_datafile(neo4j_driver, project_dir, domain_config, "frozen", "a/frozen.txt", snapshot=True)
    _, live = _register_datafile(neo4j_driver, project_dir, domain_config, "live", "a/live.txt")
    live.write_text("changed\n", encoding="utf-8")

    result = check_file_hashes(neo4j_driver, NEO4J_DB, project_dir)
    assert result.symbol == "fail"
    assert result.details == ["live.txt"]
    assert "1 snapshot artifact, drift not checked" in result.summary


@pytestmark_db
def test_snapshot_false_is_not_a_snapshot(neo4j_driver, project_dir, domain_config, clean_test_db):
    _, path = _register_datafile(neo4j_driver, project_dir, domain_config, "df", "b/df.txt", snapshot=False)
    path.write_text("changed\n", encoding="utf-8")
    result = check_file_hashes(neo4j_driver, NEO4J_DB, project_dir)
    assert result.symbol == "fail"
    assert "snapshot" not in result.summary


@pytestmark_db
def test_directory_path_is_a_violation_not_a_crash(neo4j_driver, project_dir, domain_config, clean_test_db):
    """A DataFile whose path resolves to a directory: violation line, verify completes."""
    (project_dir / "corpus" / "bulk").mkdir(parents=True)
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="DataFile",
        properties={"name": "bulk-dir", "path": "corpus/bulk", "content_hash": "0" * 64},
        actor="test", authority="accepted",
    )
    # A healthy sibling proves the loop continued past the directory.
    _register_datafile(neo4j_driver, project_dir, domain_config, "ok", "corpus/ok.txt")

    result = check_file_hashes(neo4j_driver, NEO4J_DB, project_dir)  # must not raise
    assert result.symbol == "fail"
    assert "schema violation" in result.summary
    assert any("corpus/bulk" in d for d in result.details)
    assert result.fixable is False  # paper sync cannot repair a registration error
    assert "ok.txt" not in result.details


@pytestmark_db
def test_directory_violation_plus_drift_stays_fixable(neo4j_driver, project_dir, domain_config, clean_test_db):
    (project_dir / "d").mkdir()
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="DataFile",
        properties={"name": "dir", "path": "d", "content_hash": "0" * 64},
        actor="test", authority="accepted",
    )
    _, live = _register_datafile(neo4j_driver, project_dir, domain_config, "live", "live.txt")
    live.write_text("changed\n", encoding="utf-8")
    result = check_file_hashes(neo4j_driver, NEO4J_DB, project_dir)
    assert result.symbol == "fail"
    assert result.fixable is True
    assert "run `seldon paper sync`" in result.summary


@pytestmark_db
def test_paper_sync_never_rewrites_snapshot_hash(neo4j_driver, project_dir, domain_config, clean_test_db):
    """`verify --fix` delegates to paper sync; sync must leave a snapshot section's hash alone."""
    sections = project_dir / "paper" / "sections"
    sections.mkdir(parents=True)
    path = sections / "01_intro.md"
    path.write_text("# Intro\n\nAs registered.\n")
    old_hash = compute_file_hash(path)
    artifact_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "01_intro", "title": "Intro", "file_path": str(path),
                    "content_hash": old_hash, "snapshot": True},
        actor="test", authority="accepted",
    )
    path.write_text("# Intro\n\nDrifted.\n")
    assert compute_file_hash(path) != old_hash

    artifact = {"artifact_id": artifact_id, "name": "01_intro", "content_hash": old_hash,
                "state": "draft", "snapshot": True}
    result = sync_section(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
        domain_config=domain_config, section_path=path, artifact=artifact,
    )
    assert result.status == "snapshot"

    from seldon.core.graph import get_artifact
    with neo4j_driver.session(database=NEO4J_DB) as session:
        stored = get_artifact(session, artifact_id)
    assert stored["content_hash"] == old_hash

    # Positive control: the same section without the flag is updated by sync.
    artifact["snapshot"] = False
    result = sync_section(
        driver=neo4j_driver, database=NEO4J_DB, project_dir=project_dir,
        domain_config=domain_config, section_path=path, artifact=artifact,
    )
    assert result.status == "updated"
    with neo4j_driver.session(database=NEO4J_DB) as session:
        stored = get_artifact(session, artifact_id)
    assert stored["content_hash"] == compute_file_hash(path)
