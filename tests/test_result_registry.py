"""
AD-028 Result registry contract tests.

Covers the `name` property (slug grammar, uniqueness), fail-loud reference
resolution in `seldon result register`, `seldon result migrate-names`, and
`seldon result backfill-provenance`.

The CLI tests run the real Click commands against the real `seldon-test`
database; only the driver factory is patched so the session-scoped fixture
driver is reused instead of a fresh one built from the environment.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.result import (
    Classification,
    RESULT_NAME_MAX_LENGTH,
    classify_unnamed_results,
    collect_token_keys,
    find_result_by_name,
    load_provenance_map,
    result_backfill_provenance,
    result_migrate_names,
    result_register,
    validate_result_name,
)
from seldon.core.artifacts import create_artifact
from seldon.core.events import event_count, read_events
from seldon.core.graph import get_artifact
from seldon.domain.loader import load_domain_config
from seldon.domain.units_vocabulary import (
    load_units_vocabulary,
    is_real_unit,
    vocabulary_path,
)

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def seldon_project(project_dir):
    """A tmp project root with a seldon.yaml pointing at the test database."""
    (project_dir / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n  database: seldon-test\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    return project_dir


def _invoke(command, args, neo4j_driver, seldon_project, monkeypatch):
    """Run a `seldon result` subcommand against the test database.

    Args:
        command: The Click command object to invoke.
        args: Argument list.
        neo4j_driver: Session-scoped fixture driver.
        seldon_project: Project root containing seldon.yaml.
        monkeypatch: pytest monkeypatch, used to chdir so Path.cwd() is real.

    Returns:
        The CliRunner result.
    """
    monkeypatch.chdir(seldon_project)
    with patch("seldon.commands.result.get_neo4j_driver", return_value=neo4j_driver), \
         patch.object(neo4j_driver, "close"):
        return CliRunner().invoke(command, args)


def _make_result(project_dir, driver, domain_config, **props):
    defaults = {"value": 1.0, "units": "score", "description": "test result"}
    defaults.update(props)
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties=defaults, actor="human", authority="accepted",
    )


def _make_datafile(project_dir, driver, domain_config, name="test_data"):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="DataFile",
        properties={"name": name, "path": f"data/{name}.csv"},
        actor="human", authority="accepted",
    )


def _make_script(project_dir, driver, domain_config, name="test_script"):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties={"name": name, "path": f"scripts/{name}.py"},
        actor="human", authority="accepted",
    )


# ── units vocabulary ──────────────────────────────────────────────────────────

def test_units_vocabulary_loads_from_packaged_location():
    """The vocabulary resolves from the seldon.domain package, not from cwd."""
    path = vocabulary_path()
    seldon_package_root = Path(__import__("seldon").__file__).resolve().parent
    assert path.is_file()
    assert path.parent == seldon_package_root / "domain"


def test_units_vocabulary_is_cwd_independent(tmp_path, monkeypatch):
    """Loading the vocabulary from an unrelated working directory still works."""
    monkeypatch.chdir(tmp_path)
    vocab = load_units_vocabulary()
    assert "count" in vocab


def test_units_vocabulary_contains_seed_and_codebase_entries():
    vocab = load_units_vocabulary()
    for seed in ("%", "rate", "ratio", "count", "kappa", "USD"):
        assert seed in vocab
    for found in ("accuracy", "score", "ms", "fraction", "bits"):
        assert found in vocab


def test_is_real_unit_rejects_token_keys():
    assert is_real_unit("count") is True
    assert is_real_unit("admitted_yield_ratio") is False
    assert is_real_unit(None) is False


def test_load_units_vocabulary_missing_file_fails_loud(tmp_path):
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FileNotFoundError) as exc:
        load_units_vocabulary(missing)
    assert str(missing) in str(exc.value)


def test_load_units_vocabulary_rejects_malformed(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("seed_units: not-a-list\n")
    with pytest.raises(ValueError) as exc:
        load_units_vocabulary(bad)
    assert "must be a list" in str(exc.value)


# ── A1: slug grammar ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "info_rate", "a", "0abc", "dotted.name", "with-dash", "mix_of.all-3",
])
def test_validate_result_name_accepts_valid_slugs(name):
    validate_result_name(name)


@pytest.mark.parametrize("name", [
    "Info_Rate",        # uppercase is not in the grammar
    "_leading",         # must start with [a-z0-9]
    "-leading",
    ".leading",
    "has space",
    "has/slash",
    "unicode_é",
    "",
])
def test_validate_result_name_rejects_invalid_slugs(name):
    with pytest.raises(ValueError):
        validate_result_name(name)


def test_validate_result_name_rejects_overlong():
    with pytest.raises(ValueError) as exc:
        validate_result_name("a" * (RESULT_NAME_MAX_LENGTH + 1))
    assert str(RESULT_NAME_MAX_LENGTH) in str(exc.value)


def test_register_rejects_bad_slug_and_writes_no_event(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    before = event_count(seldon_project)
    result = _invoke(
        result_register,
        ["--name", "Bad_Name", "--value", "1.0", "--units", "count",
         "--description", "d"],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 1
    assert "slug grammar" in result.output
    assert event_count(seldon_project) == before


# ── A1: uniqueness ────────────────────────────────────────────────────────────

def test_register_name_collision_names_existing_artifact_id(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    existing_id = _make_result(
        seldon_project, neo4j_driver, domain_config, name="dup_metric"
    )
    before = event_count(seldon_project)

    result = _invoke(
        result_register,
        ["--name", "dup_metric", "--value", "2.0", "--units", "count",
         "--description", "d"],
        neo4j_driver, seldon_project, monkeypatch,
    )

    assert result.exit_code == 1
    assert existing_id in result.output
    assert event_count(seldon_project) == before


def test_register_accepts_a_free_name(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    result = _invoke(
        result_register,
        ["--name", "fresh_metric", "--value", "0.5", "--units", "ratio",
         "--description", "a fresh metric"],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 0, result.output

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = find_result_by_name(session, "fresh_metric")
    assert node is not None
    assert node["value"] == 0.5
    assert node["units"] == "ratio"


def test_find_result_by_name_is_case_sensitive(
    neo4j_driver, seldon_project, domain_config, clean_test_db
):
    _make_result(seldon_project, neo4j_driver, domain_config, name="lower_case")
    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert find_result_by_name(session, "lower_case") is not None
        assert find_result_by_name(session, "Lower_Case") is None


# ── A3: unknown references are fatal, and write nothing ───────────────────────

def test_register_unknown_data_name_errors_and_writes_no_event(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    before = event_count(seldon_project)

    result = _invoke(
        result_register,
        ["--name", "m1", "--value", "1.0", "--units", "count",
         "--description", "d", "--data-name", "no_such_datafile"],
        neo4j_driver, seldon_project, monkeypatch,
    )

    assert result.exit_code == 1
    assert "no_such_datafile" in result.output
    assert "no DataFile with that name" in result.output
    # The whole point: nothing at all was written.
    assert event_count(seldon_project) == before
    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert find_result_by_name(session, "m1") is None


def test_register_unknown_script_name_errors_and_writes_no_event(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    before = event_count(seldon_project)
    result = _invoke(
        result_register,
        ["--name", "m2", "--value", "1.0", "--units", "count",
         "--description", "d", "--script-name", "no_such_script"],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 1
    assert "no Script with that name" in result.output
    assert event_count(seldon_project) == before


def test_register_reports_every_unresolved_reference_at_once(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    result = _invoke(
        result_register,
        ["--name", "m3", "--value", "1.0", "--units", "count",
         "--description", "d",
         "--script-name", "missing_script",
         "--data-name", "missing_a,missing_b"],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 1
    for token in ("missing_script", "missing_a", "missing_b"):
        assert token in result.output


def test_register_known_data_name_creates_link(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    _make_datafile(seldon_project, neo4j_driver, domain_config, name="real_data")

    result = _invoke(
        result_register,
        ["--name", "m4", "--value", "1.0", "--units", "count",
         "--description", "d", "--data-name", "real_data"],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 0, result.output

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (r:Result {name: 'm4'})-[:COMPUTED_FROM]->(d:DataFile) RETURN d"
        ).single()
    assert rel is not None


# ── A2: classification ────────────────────────────────────────────────────────

def _node(artifact_id, units=None):
    node = {"artifact_id": artifact_id, "value": 1.0, "state": "proposed"}
    if units is not None:
        node["units"] = units
    return node


def test_classify_all_three_classes():
    vocab = frozenset({"count", "ratio"})
    nodes = [
        _node("a", "count"),                    # real unit, uncontested
        _node("b", "admitted_yield_ratio"),     # token key in the wrong slot
        _node("c", "ratio"),                    # real unit AND a live token key
    ]
    by_id = {
        c.node["artifact_id"]: c.migration_class
        for c in classify_unnamed_results(nodes, vocab, token_keys={"ratio"})
    }
    assert by_id == {
        "a": "units_is_real_unit",
        "b": "migrated",
        "c": "ambiguous",
    }


def test_classify_marks_duplicate_units_ambiguous_not_migrated():
    """Two unnamed Results sharing a token key cannot both take it as a name."""
    vocab = frozenset({"count"})
    nodes = [_node("a", "precision"), _node("b", "precision"), _node("c", "recall")]
    classes = {
        c.node["artifact_id"]: c.migration_class
        for c in classify_unnamed_results(nodes, vocab, token_keys=set())
    }
    assert classes["a"] == "ambiguous"
    assert classes["b"] == "ambiguous"
    assert classes["c"] == "migrated"


def test_classify_duplicate_real_unit_is_not_a_collision():
    """Several Results measured in `count` is normal — nothing is promoted."""
    vocab = frozenset({"count"})
    nodes = [_node("a", "count"), _node("b", "count")]
    classes = {c.migration_class for c in classify_unnamed_results(nodes, vocab, set())}
    assert classes == {"units_is_real_unit"}


def test_classify_respects_already_claimed_names():
    vocab = frozenset({"count"})
    nodes = [_node("a", "info_rate")]
    result = classify_unnamed_results(
        nodes, vocab, token_keys=set(), claimed_names={"info_rate"}
    )
    assert result[0].migration_class == "ambiguous"
    assert "already claimed" in result[0].reason


def test_classify_no_units_bucket():
    result = classify_unnamed_results([_node("a")], frozenset(), set())
    assert result[0].migration_class == "no_units"


def test_classify_returns_one_classification_per_result():
    nodes = [_node("a", "count"), _node("b", "x"), _node("c")]
    out = classify_unnamed_results(nodes, frozenset({"count"}), set())
    assert len(out) == len(nodes)
    assert all(isinstance(c, Classification) for c in out)


def test_collect_token_keys_reads_paper_sources(tmp_path):
    sections = tmp_path / "paper" / "sections"
    sections.mkdir(parents=True)
    (sections / "01.md").write_text(
        "Value is {{result:info_rate:value}} and {{figure:fig_a:path}}.\n"
    )
    (sections / "02.md").write_text("Also {{result:other_metric:units}}.\n")
    assert collect_token_keys(tmp_path) == {"info_rate", "other_metric"}


def test_collect_token_keys_no_paper_dir(tmp_path):
    assert collect_token_keys(tmp_path) == set()


# ── A2: migrate-names command ─────────────────────────────────────────────────

def test_migrate_names_dry_run_writes_no_event(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    _make_result(seldon_project, neo4j_driver, domain_config, units="token_key_a")
    _make_result(seldon_project, neo4j_driver, domain_config, units="count")
    before = event_count(seldon_project)

    result = _invoke(
        result_migrate_names,
        ["--dry-run", "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )

    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert "no events written" in result.output
    assert event_count(seldon_project) == before


def test_migrate_names_live_promotes_units_to_name(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    migrate_id = _make_result(
        seldon_project, neo4j_driver, domain_config, units="token_key_a"
    )
    keep_id = _make_result(
        seldon_project, neo4j_driver, domain_config, units="count"
    )

    result = _invoke(
        result_migrate_names,
        ["--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 0, result.output
    assert "Migrated 1 Result(s)." in result.output

    with neo4j_driver.session(database=NEO4J_DB) as session:
        migrated = get_artifact(session, migrate_id)
        kept = get_artifact(session, keep_id)

    assert migrated["name"] == "token_key_a"
    assert "units" not in migrated          # cleared, not blanked
    assert "name" not in kept               # real unit left alone
    assert kept["units"] == "count"


def test_migrate_names_writes_one_replayable_event_per_promotion(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    _make_result(seldon_project, neo4j_driver, domain_config, units="token_key_b")
    before = len(read_events(seldon_project))

    _invoke(
        result_migrate_names,
        ["--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )

    events = read_events(seldon_project)[before:]
    assert len(events) == 1
    assert events[0]["event_type"] == "artifact_updated"
    props = events[0]["payload"]["properties"]
    assert props["name"] == "token_key_b"
    assert props["units"] is None


def test_migrate_names_leaves_duplicates_alone(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    first = _make_result(seldon_project, neo4j_driver, domain_config, units="shared_key")
    second = _make_result(seldon_project, neo4j_driver, domain_config, units="shared_key")

    result = _invoke(
        result_migrate_names,
        ["--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 0, result.output
    assert "Migrated 0 Result(s)." in result.output

    with neo4j_driver.session(database=NEO4J_DB) as session:
        for artifact_id in (first, second):
            node = get_artifact(session, artifact_id)
            assert "name" not in node
            assert node["units"] == "shared_key"


# ── A3: backfill-provenance ───────────────────────────────────────────────────

def _write_map(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload))
    return path


def test_load_provenance_map_rejects_unknown_key(tmp_path):
    path = _write_map(tmp_path / "m.yaml", {"r1": {"nonsense": 1}})
    with pytest.raises(ValueError) as exc:
        load_provenance_map(path)
    assert "unknown key" in str(exc.value)


def test_load_provenance_map_accepts_json(tmp_path):
    path = tmp_path / "m.json"
    path.write_text('{"r1": {"generated_by": "s1"}}')
    assert load_provenance_map(path) == {"r1": {"generated_by": "s1"}}


def test_backfill_provenance_dry_run_writes_nothing(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    _make_result(seldon_project, neo4j_driver, domain_config, name="r_backfill")
    _make_datafile(seldon_project, neo4j_driver, domain_config, name="d1")
    map_path = _write_map(
        seldon_project / "map.yaml", {"r_backfill": {"computed_from": ["d1"]}}
    )
    before = event_count(seldon_project)

    result = _invoke(
        result_backfill_provenance,
        ["--map", str(map_path), "--dry-run", "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )

    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert event_count(seldon_project) == before
    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert session.run(
            "MATCH (:Result)-[r:COMPUTED_FROM]->(:DataFile) RETURN r"
        ).single() is None


def test_backfill_provenance_live_creates_links(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    _make_result(seldon_project, neo4j_driver, domain_config, name="r_live")
    _make_datafile(seldon_project, neo4j_driver, domain_config, name="d1")
    _make_script(seldon_project, neo4j_driver, domain_config, name="s1")
    map_path = _write_map(
        seldon_project / "map.yaml",
        {"r_live": {"computed_from": ["d1"], "generated_by": "s1"}},
    )

    result = _invoke(
        result_backfill_provenance,
        ["--map", str(map_path), "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 0, result.output

    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert session.run(
            "MATCH (:Result {name:'r_live'})-[r:COMPUTED_FROM]->(:DataFile {name:'d1'}) RETURN r"
        ).single() is not None
        assert session.run(
            "MATCH (:Result {name:'r_live'})-[r:GENERATED_BY]->(:Script {name:'s1'}) RETURN r"
        ).single() is not None


def test_backfill_provenance_is_idempotent(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    _make_result(seldon_project, neo4j_driver, domain_config, name="r_idem")
    _make_datafile(seldon_project, neo4j_driver, domain_config, name="d1")
    map_path = _write_map(
        seldon_project / "map.yaml", {"r_idem": {"computed_from": ["d1"]}}
    )
    args = ["--map", str(map_path), "--project-dir", str(seldon_project)]

    _invoke(result_backfill_provenance, args, neo4j_driver, seldon_project, monkeypatch)
    second = _invoke(
        result_backfill_provenance, args, neo4j_driver, seldon_project, monkeypatch
    )

    assert second.exit_code == 0, second.output
    assert "already present" in second.output
    with neo4j_driver.session(database=NEO4J_DB) as session:
        rels = session.run(
            "MATCH (:Result {name:'r_idem'})-[r:COMPUTED_FROM]->(:DataFile) RETURN r"
        ).data()
    assert len(rels) == 1


def test_backfill_provenance_partial_failure_continues_and_exits_nonzero(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    """A bad row is reported and skipped; the good rows still get written."""
    _make_result(seldon_project, neo4j_driver, domain_config, name="r_good")
    _make_result(seldon_project, neo4j_driver, domain_config, name="r_bad")
    _make_datafile(seldon_project, neo4j_driver, domain_config, name="d1")
    map_path = _write_map(
        seldon_project / "map.yaml",
        {
            "r_good": {"computed_from": ["d1"]},
            "r_bad": {"computed_from": ["d_missing"]},
            "r_absent": {"computed_from": ["d1"]},
        },
    )

    result = _invoke(
        result_backfill_provenance,
        ["--map", str(map_path), "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )

    assert result.exit_code == 1
    assert "d_missing" in result.output
    assert "r_absent" in result.output

    with neo4j_driver.session(database=NEO4J_DB) as session:
        # The good row landed.
        assert session.run(
            "MATCH (:Result {name:'r_good'})-[r:COMPUTED_FROM]->(:DataFile) RETURN r"
        ).single() is not None
        # The failing row wrote nothing at all.
        assert session.run(
            "MATCH (:Result {name:'r_bad'})-[r:COMPUTED_FROM]->(:DataFile) RETURN r"
        ).single() is None
