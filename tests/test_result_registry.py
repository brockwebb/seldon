"""
AD-028 Result registry contract tests.

Covers the `name` property (slug grammar, uniqueness), fail-loud reference
resolution in `seldon result register`, `seldon result migrate-names`, and
`seldon result backfill-provenance`.

The CLI tests run the real Click commands against the real per-process
database; only the driver factory is patched so the session-scoped fixture
driver is reused instead of a fresh one built from the environment.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.result import (
    Classification,
    MIGRATION_CLASSES,
    MIGRATION_REPORT_FIELDS,
    MIGRATION_WRITING_CLASSES,
    RESULT_NAME_MAX_LENGTH,
    build_migration_plan,
    classify_unnamed_results,
    collect_token_keys,
    find_result_by_name,
    load_provenance_map,
    result_backfill_provenance,
    result_migrate_names,
    result_register,
    validate_result_name,
    write_migration_report,
)
from seldon.core.artifacts import create_artifact, update_artifact
from seldon.core.events import event_count, read_events
from seldon.core.graph import get_artifact
from seldon.domain.loader import load_domain_config
from seldon.domain.units_vocabulary import (
    load_units_vocabulary,
    is_real_unit,
    vocabulary_path,
)

from tests.testdb import TEST_DATABASE

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def seldon_project(project_dir):
    """A tmp project root with a seldon.yaml pointing at the test database."""
    (project_dir / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n  database: " + TEST_DATABASE + "\n"
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
    # AD-028 Amendment 01 (2026-09-04): uppercase is admitted. These are the
    # ai-readiness-kg DD-035/DD-037 shapes the original grammar refused.
    "Info_Rate", "MOE", "admitted_yield_L0", "share_MOE_L4", "DP_NOISE",
    "RELIABILITY_FLAG", "Z", "9",
])
def test_validate_result_name_accepts_valid_slugs(name):
    validate_result_name(name)


@pytest.mark.parametrize("name", [
    "_leading",         # must start with an ASCII letter or digit
    "-leading",
    ".leading",
    "has space",
    "has/slash",
    "unicode_é",
    "Éaccent",     # non-ASCII uppercase is still out
    "trailing!",
    "",
])
def test_validate_result_name_rejects_invalid_slugs(name):
    with pytest.raises(ValueError):
        validate_result_name(name)


def test_validate_result_name_is_case_sensitive_not_case_folding():
    """Amendment 01 widened the grammar; it did NOT add case-insensitivity.

    `MOE` and `moe` are both legal and are two different names. Uniqueness
    stays exact-match, which the collision tests below exercise against the
    graph.
    """
    validate_result_name("MOE")
    validate_result_name("moe")


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
        ["--name", "Bad Name", "--value", "1.0", "--units", "count",
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


# ── A2b: the migration plan (AD-028 Amendment 01) ─────────────────────────────
#
# The defect the amendment records: `migrate-names --dry-run` did not run the
# validation the live path ran, so the dry run promised 3529 migrations and the
# live run wrote 2576 then refused 953 and exited partway through. The sweep
# that shipped it had checked that the dry run's class counts summed to the row
# total — which they did, while no row had been validated at all.
#
# So these tests never accept a reconciled total as evidence. They compare the
# dry run against the live run row by row, and they assert on the event store,
# which is the only thing that can tell writing apart from claiming to write.

SUMMARY_ROW_RE = re.compile(r"^ {4}(\w+)\s+(\d+)$")


def _summary_counts(output: str) -> dict:
    """Parse the per-class summary table out of a migrate-names run.

    Args:
        output: Captured stdout of the command.

    Returns:
        {class name: count} for every class in the summary table.
    """
    counts = {}
    for line in output.splitlines():
        match = SUMMARY_ROW_RE.match(line)
        if match and match.group(1) in MIGRATION_CLASSES:
            counts[match.group(1)] = int(match.group(2))
    return counts


def _mixed_fixture(project_dir, driver, domain_config) -> dict:
    """Ten Results covering all seven migration classes.

    `units` is a required property on Result, so the `no_units` row cannot be
    created with an empty one. It is produced the way the graph really produces
    it — created, then cleared by the same `artifact_updated` event the
    migration itself emits.

    Returns:
        {role: artifact_id}. Roles name the expected class so a failure message
        points at the row that misbehaved.
    """
    make = lambda **kw: _make_result(project_dir, driver, domain_config, **kw)
    ids = {
        "migrate_a": make(units="alpha_metric"),
        "migrate_b": make(units="beta_metric"),
        "refused_space": make(units="Bad Name"),
        "refused_leading": make(units="_leading"),
        "real_unit": make(units="count"),
        "pending": make(name="gamma_metric", units="gamma_metric"),
        "already": make(name="delta_metric", units="count"),
        "no_units": make(units="to_be_cleared"),
        "ambiguous_a": make(units="contested_key"),
        "ambiguous_b": make(units="contested_key"),
    }
    update_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        artifact_id=ids["no_units"], properties={"units": None},
        actor="human", authority="accepted",
    )
    return ids


EXPECTED_FIXTURE_COUNTS = {
    "migrated": 2,
    "name_set_units_pending": 1,
    "already_named": 1,
    "units_is_real_unit": 1,
    "ambiguous": 2,
    "no_units": 1,
    "refused": 2,
}


# ── plan construction ─────────────────────────────────────────────────────────

def test_classify_refuses_an_unpromotable_units_string():
    """A units value that cannot legally be a name is `refused`, not `migrated`.

    This is the check the original dry run skipped.
    """
    out = classify_unnamed_results(
        [_node("a", "Bad Name"), _node("b", "_leading"), _node("c", "ok_name")],
        frozenset({"count"}), token_keys=set(),
    )
    by_id = {c.node["artifact_id"]: c.migration_class for c in out}
    assert by_id == {"a": "refused", "b": "refused", "c": "migrated"}
    assert "slug grammar" in dict(
        (c.node["artifact_id"], c.reason) for c in out
    )["a"]


def test_classify_admits_uppercase_after_amendment_01():
    """The ai-readiness-kg DD-035/DD-037 shapes migrate now instead of refusing."""
    out = classify_unnamed_results(
        [_node("a", "admitted_yield_L0"), _node("b", "share_MOE"),
         _node("c", "DP_NOISE")],
        frozenset({"count"}), token_keys=set(),
    )
    assert {c.migration_class for c in out} == {"migrated"}
    assert [c.new_name for c in out] == ["admitted_yield_L0", "share_MOE", "DP_NOISE"]


def test_classify_sets_the_planned_action_the_live_run_executes():
    out = classify_unnamed_results(
        [_node("a", "ok_name"), _node("b", "count"), _node("c")],
        frozenset({"count"}), token_keys=set(),
    )
    assert [c.planned_action for c in out] == [
        "set_name_and_clear_units", "none", "none",
    ]


def test_build_migration_plan_classifies_every_result_exactly_once():
    results = [
        {"artifact_id": "n1", "name": "kept", "units": "count"},
        {"artifact_id": "n2", "name": "pending_key", "units": "pending_key"},
        {"artifact_id": "u1", "units": "promote_me"},
        {"artifact_id": "u2", "units": "Bad Name"},
        {"artifact_id": "u3"},
    ]
    plan = build_migration_plan(results, frozenset({"count"}), set())
    assert len(plan) == len(results)
    assert [c.node["artifact_id"] for c in plan] == [r["artifact_id"] for r in results]
    assert [c.migration_class for c in plan] == [
        "already_named", "name_set_units_pending", "migrated", "refused", "no_units",
    ]
    assert all(c.migration_class in MIGRATION_CLASSES for c in plan)


def test_build_migration_plan_pending_row_clears_units_and_keeps_its_name():
    plan = build_migration_plan(
        [{"artifact_id": "n", "name": "same_key", "units": "same_key"}],
        frozenset(), set(),
    )
    assert plan[0].migration_class == "name_set_units_pending"
    assert plan[0].planned_action == "clear_units"
    assert plan[0].new_name is None          # the name is never re-assigned


def test_build_migration_plan_already_named_row_is_inert():
    plan = build_migration_plan(
        [{"artifact_id": "n", "name": "a_key", "units": "count"}],
        frozenset({"count"}), set(),
    )
    assert plan[0].migration_class == "already_named"
    assert plan[0].planned_action == "none"


def test_build_migration_plan_named_rows_claim_their_names_against_promotions():
    """An unnamed row may not be promoted onto a name a named row already holds."""
    plan = build_migration_plan(
        [{"artifact_id": "n", "name": "taken_key", "units": "count"},
         {"artifact_id": "u", "units": "taken_key"}],
        frozenset({"count"}), set(),
    )
    assert plan[1].migration_class == "ambiguous"
    assert "already claimed" in plan[1].reason


def test_build_migration_plan_pending_row_also_blocks_a_promotion():
    """A `name_set_units_pending` row still owns its name during the same run."""
    plan = build_migration_plan(
        [{"artifact_id": "n", "name": "dup_key", "units": "dup_key"},
         {"artifact_id": "u", "units": "dup_key"}],
        frozenset(), set(),
    )
    assert [c.migration_class for c in plan] == ["name_set_units_pending", "ambiguous"]


# ── dry run predicts the live run ─────────────────────────────────────────────

def test_migrate_names_dry_run_reports_all_seven_classes(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    _mixed_fixture(seldon_project, neo4j_driver, domain_config)
    result = _invoke(
        result_migrate_names,
        ["--dry-run", "--partial", "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    counts = _summary_counts(result.output)
    assert counts == EXPECTED_FIXTURE_COUNTS
    assert set(counts) == set(MIGRATION_CLASSES)


def test_migrate_names_dry_run_and_live_run_agree_row_for_row(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    """The contract Amendment 01 exists to enforce.

    The dry run reports `refused: 2`; the live run then writes exactly the
    `migrated` + `name_set_units_pending` count and touches none of the refused
    rows. Agreement is checked against the event store and the graph, not
    against the dry run's own arithmetic.
    """
    ids = _mixed_fixture(seldon_project, neo4j_driver, domain_config)
    before = event_count(seldon_project)

    dry = _invoke(
        result_migrate_names,
        ["--dry-run", "--partial", "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    dry_counts = _summary_counts(dry.output)
    assert dry_counts["refused"] == 2
    assert event_count(seldon_project) == before, "a dry run wrote to the event store"

    live = _invoke(
        result_migrate_names,
        ["--partial", "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert _summary_counts(live.output) == dry_counts
    assert live.exit_code == dry.exit_code == 1, "refusals must exit non-zero both ways"

    events = read_events(seldon_project)[before:]
    expected_writes = (
        dry_counts["migrated"] + dry_counts["name_set_units_pending"]
    )
    assert len(events) == expected_writes
    assert {e["payload"]["artifact_id"] for e in events} == {
        ids["migrate_a"], ids["migrate_b"], ids["pending"],
    }

    with neo4j_driver.session(database=NEO4J_DB) as session:
        for role in ("refused_space", "refused_leading"):
            node = get_artifact(session, ids[role])
            assert "name" not in node, f"{role} was written despite being refused"
        assert get_artifact(session, ids["migrate_a"])["name"] == "alpha_metric"
        assert get_artifact(session, ids["migrate_b"])["name"] == "beta_metric"


def test_migrate_names_dry_run_predicts_the_live_exit_code_when_blocked(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    """Without --partial, both runs refuse and both exit 1."""
    _mixed_fixture(seldon_project, neo4j_driver, domain_config)
    dry = _invoke(
        result_migrate_names,
        ["--dry-run", "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    live = _invoke(
        result_migrate_names,
        ["--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert dry.exit_code == 1
    assert live.exit_code == 1
    assert "REFUSE" in dry.output
    assert "NOTHING was written" in live.output


def test_migrate_names_dry_run_is_clean_and_zero_exit_when_nothing_is_refused(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    _make_result(seldon_project, neo4j_driver, domain_config, units="clean_key")
    result = _invoke(
        result_migrate_names,
        ["--dry-run", "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 0, result.output
    assert "The live run would write 1 event(s)" in result.output


# ── validate-all-then-write ───────────────────────────────────────────────────

def test_migrate_names_without_partial_writes_absolutely_nothing_on_refusal(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    """One bad row aborts the whole run. The valid row stays unmigrated."""
    ids = _mixed_fixture(seldon_project, neo4j_driver, domain_config)
    before = event_count(seldon_project)

    result = _invoke(
        result_migrate_names,
        ["--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )

    assert result.exit_code == 1
    assert event_count(seldon_project) == before, "event store grew on an aborted run"
    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert "name" not in get_artifact(session, ids["migrate_a"])
        assert get_artifact(session, ids["pending"])["units"] == "gamma_metric"


def test_migrate_names_partial_writes_the_valid_rows_and_still_exits_nonzero(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    ids = _mixed_fixture(seldon_project, neo4j_driver, domain_config)
    before = event_count(seldon_project)

    result = _invoke(
        result_migrate_names,
        ["--partial", "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )

    assert result.exit_code == 1, "a partial run that refused rows is not a success"
    assert "Migrated 2 Result(s)." in result.output
    assert "Cleared pending units on 1 Result(s)." in result.output
    assert event_count(seldon_project) == before + 3
    with neo4j_driver.session(database=NEO4J_DB) as session:
        assert get_artifact(session, ids["migrate_a"])["name"] == "alpha_metric"
        assert "units" not in get_artifact(session, ids["migrate_a"])


def test_migrate_names_clean_graph_needs_no_partial_flag(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    """--partial changes nothing when there is nothing to refuse."""
    _make_result(seldon_project, neo4j_driver, domain_config, units="only_key")
    result = _invoke(
        result_migrate_names,
        ["--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 0, result.output
    assert "Migrated 1 Result(s)." in result.output


# ── resumability ──────────────────────────────────────────────────────────────

def test_migrate_names_skips_rows_that_already_carry_a_name(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    """Pin the pre-existing behaviour: a named Result is never renamed."""
    named = _make_result(
        seldon_project, neo4j_driver, domain_config,
        name="settled_key", units="count",
    )
    before = event_count(seldon_project)

    result = _invoke(
        result_migrate_names,
        ["--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )

    assert result.exit_code == 0, result.output
    assert event_count(seldon_project) == before
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, named)
    assert node["name"] == "settled_key"
    assert node["units"] == "count"


def test_migrate_names_clears_pending_units_without_reassigning_the_name(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    """The ai-readiness-kg half-applied state: name set, units still equal to it.

    2576 rows are in this state because the earlier run's combined event set the
    name and its compensating units clear never landed. The fix must emit the
    clear ALONE — re-asserting the name would be a second write of a value that
    is already correct, and would hide whether the clear was the missing half.
    """
    pending = _make_result(
        seldon_project, neo4j_driver, domain_config,
        name="pending_key", units="pending_key",
    )
    before = len(read_events(seldon_project))

    result = _invoke(
        result_migrate_names,
        ["--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 0, result.output
    assert "Cleared pending units on 1 Result(s)." in result.output

    events = read_events(seldon_project)[before:]
    assert len(events) == 1
    assert events[0]["event_type"] == "artifact_updated"
    properties = events[0]["payload"]["properties"]
    assert properties["units"] is None
    assert "name" not in properties, "the clear must not re-assert the name"

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, pending)
    assert node["name"] == "pending_key"
    assert "units" not in node


def test_migrate_names_is_idempotent(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    """A second run over an already-migrated graph writes nothing."""
    _make_result(seldon_project, neo4j_driver, domain_config, units="once_key")
    _make_result(
        seldon_project, neo4j_driver, domain_config,
        name="pending_key", units="pending_key",
    )

    first = _invoke(
        result_migrate_names, ["--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert first.exit_code == 0, first.output
    after_first = event_count(seldon_project)

    second = _invoke(
        result_migrate_names, ["--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert second.exit_code == 0, second.output
    assert event_count(seldon_project) == after_first
    counts = _summary_counts(second.output)
    assert counts["migrated"] == 0
    assert counts["name_set_units_pending"] == 0
    assert counts["already_named"] == 2


# ── --report JSONL ────────────────────────────────────────────────────────────

def test_migrate_names_report_writes_one_row_per_result_with_the_agreed_fields(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    """The JSONL shape is a contract consumed by ai-readiness-kg's follow-up."""
    ids = _mixed_fixture(seldon_project, neo4j_driver, domain_config)
    report = seldon_project / "reports" / "plan.jsonl"

    _invoke(
        result_migrate_names,
        ["--dry-run", "--partial", "--report", str(report),
         "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )

    rows = [json.loads(line) for line in report.read_text().splitlines()]
    assert len(rows) == len(ids)
    for row in rows:
        assert set(row) == set(MIGRATION_REPORT_FIELDS)
        assert row["class"] in MIGRATION_CLASSES
        assert row["planned_action"] in (
            "set_name_and_clear_units", "clear_units", "none"
        )
        assert row["reason"]

    by_id = {row["artifact_id"]: row for row in rows}
    assert by_id[ids["migrate_a"]]["class"] == "migrated"
    assert by_id[ids["migrate_a"]]["planned_action"] == "set_name_and_clear_units"
    assert by_id[ids["migrate_a"]]["current_units"] == "alpha_metric"
    assert by_id[ids["migrate_a"]]["current_name"] is None
    assert by_id[ids["refused_space"]]["class"] == "refused"
    assert by_id[ids["refused_space"]]["planned_action"] == "none"
    assert by_id[ids["pending"]]["class"] == "name_set_units_pending"
    assert by_id[ids["pending"]]["planned_action"] == "clear_units"
    assert by_id[ids["pending"]]["current_name"] == "gamma_metric"


def test_migrate_names_report_row_classes_match_the_summary_table(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    """The file and the table are two views of one plan, so they cannot differ."""
    _mixed_fixture(seldon_project, neo4j_driver, domain_config)
    report = seldon_project / "plan.jsonl"
    result = _invoke(
        result_migrate_names,
        ["--dry-run", "--partial", "--report", str(report),
         "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    rows = [json.loads(line) for line in report.read_text().splitlines()]
    from collections import Counter
    file_counts = Counter(row["class"] for row in rows)
    table = _summary_counts(result.output)
    for cls in MIGRATION_CLASSES:
        assert file_counts.get(cls, 0) == table[cls], cls


def test_migrate_names_report_is_written_on_the_live_run_too(
    neo4j_driver, seldon_project, domain_config, clean_test_db, monkeypatch
):
    _make_result(seldon_project, neo4j_driver, domain_config, units="live_key")
    report = seldon_project / "live_plan.jsonl"
    result = _invoke(
        result_migrate_names,
        ["--report", str(report), "--project-dir", str(seldon_project)],
        neo4j_driver, seldon_project, monkeypatch,
    )
    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in report.read_text().splitlines()]
    assert [row["class"] for row in rows] == ["migrated"]


def test_write_migration_report_creates_missing_parent_directories(tmp_path):
    plan = build_migration_plan(
        [{"artifact_id": "u", "units": "some_key"}], frozenset(), set()
    )
    destination = tmp_path / "deep" / "nested" / "plan.jsonl"
    write_migration_report(destination, plan)
    row = json.loads(destination.read_text().strip())
    assert row["artifact_id"] == "u"
    assert row["class"] == "migrated"


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
