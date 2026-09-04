"""Tests for the SI-09 units-fallback measurement instrument.

TRANSITIONAL (AD-028). `seldon.paper.build.check_units_fallback` exists to
measure the removal condition of the transitional units fallback: the fallback
may be deleted once every project reports zero fallback resolutions. These tests
go when the fallback goes.

The behaviours that matter for a fleet-wide survey, and that these tests pin:

* a legacy unnamed Result reachable only by its `units` is COUNTED;
* a properly named Result is NOT counted (it never touches the fallback);
* an ambiguous fallback is counted separately and still blocks removal;
* a project that cannot be reached reports an error and is NOT reported as
  zero — conflating "unmeasurable" with "measured zero" would let the fallback
  be deleted on the strength of a project nobody could read.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.core.artifacts import create_artifact
from seldon.domain.loader import load_domain_config
from seldon.paper.build import check_units_fallback

from tests.testdb import TEST_DATABASE

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _project(tmp_path: Path, database: str | None = NEO4J_DB) -> Path:
    """Write a minimal seldon.yaml. `database=None` omits neo4j.database."""
    db_line = f"  database: {database}\n" if database else ""
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n" + db_line +
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    return tmp_path


def _wire_driver(monkeypatch, neo4j_driver):
    monkeypatch.setattr(
        "seldon.paper.build.get_neo4j_driver", lambda config: neo4j_driver
    )
    monkeypatch.setattr(neo4j_driver, "close", lambda: None)


def test_counts_a_legacy_units_only_result(
    tmp_path, neo4j_driver, domain_config, clean_test_db, monkeypatch
):
    create_artifact(
        project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 3.5, "units": "admitted_yield_ratio",
                    "description": "legacy, name lives in units"},
        actor="human", authority="accepted",
    )
    project = _project(tmp_path)
    doc = tmp_path / "findings.md"
    doc.write_text("Yield was {{result:admitted_yield_ratio:value}}.\n")
    _wire_driver(monkeypatch, neo4j_driver)

    report = check_units_fallback(project, [doc])

    assert report.measured is True
    assert report.database == NEO4J_DB
    assert report.tokens == 1
    assert report.resolutions == 1
    assert report.ambiguities == 0
    assert report.index_keys == 1
    assert report.files[0].path == str(doc)


def test_named_result_is_not_a_fallback_resolution(
    tmp_path, neo4j_driver, domain_config, clean_test_db, monkeypatch
):
    create_artifact(
        project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"name": "admitted_yield_ratio", "value": 3.5,
                    "units": "ratio", "description": "migrated"},
        actor="human", authority="accepted",
    )
    project = _project(tmp_path)
    doc = tmp_path / "findings.md"
    doc.write_text("Yield was {{result:admitted_yield_ratio:value}}.\n")
    _wire_driver(monkeypatch, neo4j_driver)

    report = check_units_fallback(project, [doc])

    assert report.measured is True
    assert report.tokens == 1
    assert report.resolutions == 0
    assert report.ambiguities == 0
    # `ratio` is a real unit, so nothing is reachable by the fallback at all.
    assert report.index_keys == 0


def test_ambiguous_fallback_is_counted_separately(
    tmp_path, neo4j_driver, domain_config, clean_test_db, monkeypatch
):
    for value in (1.0, 2.0):
        create_artifact(
            project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="Result",
            properties={"value": value, "units": "shared_token_key",
                        "description": "legacy"},
            actor="human", authority="accepted",
        )
    project = _project(tmp_path)
    doc = tmp_path / "findings.md"
    doc.write_text("{{result:shared_token_key:value}}\n")
    _wire_driver(monkeypatch, neo4j_driver)

    report = check_units_fallback(project, [doc])

    assert report.resolutions == 0
    assert report.ambiguities == 1


def test_project_without_database_is_unmeasurable_not_zero(tmp_path):
    project = _project(tmp_path, database=None)
    doc = tmp_path / "findings.md"
    doc.write_text("{{result:anything:value}}\n")

    report = check_units_fallback(project, [doc])

    assert report.measured is False
    assert report.resolutions == 0
    assert report.files == []
    assert "neo4j.database" in report.error


def test_unreachable_graph_is_reported_not_raised(tmp_path, monkeypatch):
    project = _project(tmp_path)
    doc = tmp_path / "findings.md"
    doc.write_text("{{result:anything:value}}\n")

    def _boom(config):
        raise RuntimeError("could not connect")

    monkeypatch.setattr("seldon.paper.build.get_neo4j_driver", _boom)

    report = check_units_fallback(project, [doc])

    assert report.measured is False
    assert report.error == "RuntimeError: could not connect"


def test_multiple_files_are_tallied_per_file_and_in_total(
    tmp_path, neo4j_driver, domain_config, clean_test_db, monkeypatch
):
    create_artifact(
        project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 7.0, "units": "legacy_key",
                    "description": "legacy"},
        actor="human", authority="accepted",
    )
    project = _project(tmp_path)
    a = tmp_path / "a.md"
    a.write_text("{{result:legacy_key:value}} and {{result:legacy_key:value}}\n")
    b = tmp_path / "b.md"
    b.write_text("no tokens here\n")
    _wire_driver(monkeypatch, neo4j_driver)

    report = check_units_fallback(project, [a, b])

    assert [f.resolutions for f in report.files] == [2, 0]
    assert report.resolutions == 2
    assert report.tokens == 2


def test_zero_from_an_empty_graph_is_distinguishable_from_a_real_zero(
    tmp_path, neo4j_driver, clean_test_db, monkeypatch
):
    """A vacuous zero must be visible as one.

    An empty graph resolves nothing by the fallback — but it resolves nothing by
    name either. `named_artifacts` and `unresolved` are what let a reader of the
    fleet table tell that apart from a project whose tokens all resolve.
    """
    project = _project(tmp_path)
    doc = tmp_path / "findings.md"
    doc.write_text("{{result:some_metric:value}}\n")
    _wire_driver(monkeypatch, neo4j_driver)

    report = check_units_fallback(project, [doc])

    assert report.measured is True
    assert report.resolutions == 0        # the number the condition is stated in
    assert report.named_artifacts == 0    # ...but nothing was there to resolve
    assert report.unresolved == 1


def test_latent_legacy_results_are_reported_even_with_zero_resolutions(
    tmp_path, neo4j_driver, domain_config, clean_test_db, monkeypatch
):
    """Legacy rows nobody cites yet are a latent dependency worth surfacing."""
    create_artifact(
        project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 1.0, "units": "uncited_legacy_key",
                    "description": "legacy, cited by nothing"},
        actor="human", authority="accepted",
    )
    project = _project(tmp_path)
    doc = tmp_path / "findings.md"
    doc.write_text("no tokens at all\n")
    _wire_driver(monkeypatch, neo4j_driver)

    report = check_units_fallback(project, [doc])

    assert report.resolutions == 0
    assert report.index_keys == 1


def test_cli_reports_and_exits_nonzero_when_fallback_fires(
    tmp_path, neo4j_driver, domain_config, clean_test_db, monkeypatch
):
    from click.testing import CliRunner

    from seldon.commands.paper import paper_check_units_fallback

    create_artifact(
        project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 7.0, "units": "legacy_key",
                    "description": "legacy"},
        actor="human", authority="accepted",
    )
    project = _project(tmp_path)
    (tmp_path / "a.md").write_text("{{result:legacy_key:value}}\n")
    _wire_driver(monkeypatch, neo4j_driver)

    result = CliRunner().invoke(
        paper_check_units_fallback,
        ["a.md", "--project-dir", str(project)],
    )

    assert result.exit_code == 1
    assert "SI-09 resolutions=1" in result.output


def test_cli_exits_two_when_project_is_unmeasurable(tmp_path):
    from click.testing import CliRunner

    from seldon.commands.paper import paper_check_units_fallback

    project = _project(tmp_path, database=None)
    (tmp_path / "a.md").write_text("{{result:legacy_key:value}}\n")

    result = CliRunner().invoke(
        paper_check_units_fallback,
        ["a.md", "--project-dir", str(project)],
    )

    assert result.exit_code == 2
    assert "NOT MEASURABLE" in result.output


def test_cli_files_from_reads_a_tracked_file_list(
    tmp_path, neo4j_driver, domain_config, clean_test_db, monkeypatch
):
    """The fleet measurement feeds `git ls-files` output through --files-from."""
    from click.testing import CliRunner

    from seldon.commands.paper import paper_check_units_fallback

    create_artifact(
        project_dir=tmp_path, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 7.0, "units": "legacy_key",
                    "description": "legacy"},
        actor="human", authority="accepted",
    )
    project = _project(tmp_path)
    (tmp_path / "a.md").write_text("{{result:legacy_key:value}}\n")
    (tmp_path / "b.md").write_text("{{result:legacy_key:value}}\n")
    listing = tmp_path / "tracked.txt"
    listing.write_text("a.md\nb.md\n")
    _wire_driver(monkeypatch, neo4j_driver)

    result = CliRunner().invoke(
        paper_check_units_fallback,
        ["--project-dir", str(project), "--files-from", str(listing)],
    )

    assert result.exit_code == 1
    assert "SI-09 resolutions=2" in result.output
