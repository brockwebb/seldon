"""Fleet-wide ontology replica sync — `seldon ontology sync --all`.

The 2026-09-04 defect sweep (§7.3, §7.7) found ten project replicas stranded at
epoch 3 carrying two junk terms as `active`, plus two more at older epochs. The
per-project `sync` command could fix each one, but only if somebody remembered
to run it from every project directory on the machine. `--all` closes that gap.

The properties that matter, and are tested here:

A. Classification is one function. `--all --dry-run` must promise exactly what
   `--apply` performs, so both go through `_compute_replica_delta`.
B. Discovery is by marker, not by name. `seldon-` is a convention; a master must
   never be a sync target; the pytest harness's own databases are left alone.
C. A fleet command is plan-only by default and never aborts halfway: one broken
   database must not strand the rest, and the run must exit non-zero.
D. A replica's sync event goes in that replica's own event log, or nowhere.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from seldon.commands.ontology import (
    DEFAULT_INHERITANCE,
    SYNC_ALL_EXCLUDE_ENV,
    ReplicaSyncReport,
    _compute_replica_delta,
    _discover_replica_databases,
    _excluded_databases,
    _find_projects_including_nested,
    _map_databases_to_projects,
    _plan_replica,
    _run_sync_all,
    _TEST_HARNESS_DB_RE,
)
from seldon.config import ONTOLOGY_MASTER_DB
from tests.testdb import BASE_DATABASE, TEST_DATABASE, TEST_PROJECT_DATABASE

from tests.test_ontology import _do_ingest

TEST_MASTER_DB = TEST_DATABASE
TEST_PROJECT_DB = TEST_PROJECT_DATABASE


def _node(term_id, *, state="active", content_hash="h1", artifact_id=None):
    """Minimal OntologyTerm node properties, as master or a replica holds them."""
    return {
        "term_id": term_id,
        "artifact_id": artifact_id or f"aid-{term_id}",
        "name": term_id.rsplit(":", 1)[-1],
        "definition": "d",
        "category": "c",
        "state": state,
        "content_hash": content_hash,
    }


# ===========================================================================
# A. Classification (pure — no Neo4j)
# ===========================================================================


class TestComputeReplicaDelta:
    """One classifier backs both the dry-run plan and the live apply."""

    def test_missing_active_term_is_created(self):
        delta = _compute_replica_delta({"t:a": _node("t:a")}, {}, DEFAULT_INHERITANCE)

        assert [p["term_id"] for p in delta.creates] == ["t:a"]
        assert delta.creates[0]["inheritance"] == DEFAULT_INHERITANCE
        assert delta.is_empty is False

    def test_missing_deprecated_term_is_skipped_not_created(self):
        """A term master retired and this replica never carried stays absent."""
        delta = _compute_replica_delta(
            {"t:dead": _node("t:dead", state="deprecated")}, {}, DEFAULT_INHERITANCE
        )

        assert delta.creates == []
        assert delta.skipped_deprecated == ["t:dead"]
        assert delta.is_empty is True

    def test_changed_content_hash_is_an_update(self):
        delta = _compute_replica_delta(
            {"t:a": _node("t:a", content_hash="new")},
            {"t:a": _node("t:a", content_hash="old")},
            DEFAULT_INHERITANCE,
        )

        assert len(delta.updates) == 1
        assert delta.updates[0]["content_hash"] == "new"

    def test_an_update_never_carries_a_state_change(self):
        """State moves are classified separately so one cannot smuggle in another."""
        delta = _compute_replica_delta(
            {"t:a": _node("t:a", content_hash="new", state="deprecated")},
            {"t:a": _node("t:a", content_hash="old", state="active")},
            DEFAULT_INHERITANCE,
        )

        assert "state" not in delta.updates[0]
        assert delta.state_changes == [("aid-t:a", "deprecated")]

    def test_junk_term_deprecation_propagates_at_an_unchanged_hash(self):
        """The actual §7.3 defect: master retired it, the replica still says active.

        The content hash is identical on both sides, so a content-only
        comparison finds nothing to do. The lifecycle state is what diverged.
        """
        delta = _compute_replica_delta(
            {"t:junk": _node("t:junk", state="deprecated")},
            {"t:junk": _node("t:junk", state="active")},
            DEFAULT_INHERITANCE,
        )

        assert delta.updates == []
        assert delta.state_changes == [("aid-t:junk", "deprecated")]
        assert delta.deprecated_count == 1

    def test_term_master_no_longer_holds_is_deprecated(self):
        delta = _compute_replica_delta(
            {}, {"t:gone": _node("t:gone")}, DEFAULT_INHERITANCE
        )

        assert delta.orphan_deprecations == ["aid-t:gone"]
        assert delta.deprecated_count == 1

    def test_already_deprecated_orphan_is_left_alone(self):
        delta = _compute_replica_delta(
            {}, {"t:gone": _node("t:gone", state="deprecated")}, DEFAULT_INHERITANCE
        )

        assert delta.orphan_deprecations == []
        assert delta.is_empty is True

    def test_deprecated_count_sums_both_causes(self):
        delta = _compute_replica_delta(
            {"t:junk": _node("t:junk", state="deprecated")},
            {
                "t:junk": _node("t:junk", state="active"),
                "t:gone": _node("t:gone"),
            },
            DEFAULT_INHERITANCE,
        )

        assert delta.deprecated_count == 2
        assert delta.state_synced_count == 0

    def test_revival_counts_as_a_state_sync_not_a_deprecation(self):
        delta = _compute_replica_delta(
            {"t:a": _node("t:a", state="active")},
            {"t:a": _node("t:a", state="deprecated")},
            DEFAULT_INHERITANCE,
        )

        assert delta.state_synced_count == 1
        assert delta.deprecated_count == 0

    def test_identical_replica_is_empty(self):
        terms = {"t:a": _node("t:a"), "t:b": _node("t:b")}
        delta = _compute_replica_delta(terms, dict(terms), DEFAULT_INHERITANCE)

        assert delta.is_empty is True


# ===========================================================================
# B. Discovery scope (pure parts)
# ===========================================================================


class TestTestHarnessPattern:
    """Exclusion must be exact, not a `seldon-test` prefix match."""

    @pytest.mark.parametrize(
        "suffix",
        ["", "-project", "-p1", "-p12345", "-p12345-gw0", "-p12345-gw0-project"],
    )
    def test_harness_databases_match(self, suffix):
        """Built from BASE_DATABASE so the pattern cannot drift from the harness."""
        assert _TEST_HARNESS_DB_RE.match(f"{BASE_DATABASE}{suffix}")

    @pytest.mark.parametrize(
        "name",
        [
            "seldon-seldon-self",
            "seldon-sfv-paper",
            "seldon-testbed",
            "seldon-test-harness",
            "seldon-ontology",
            "xseldon-test",
            "neo4j",
        ],
    )
    def test_real_databases_do_not_match(self, name):
        assert _TEST_HARNESS_DB_RE.match(name) is None


class TestExcludedDatabases:
    def test_cli_and_env_are_additive(self, monkeypatch):
        monkeypatch.setenv(
            SYNC_ALL_EXCLUDE_ENV, os.pathsep.join(["seldon-a", "seldon-b"])
        )

        assert _excluded_databases(["seldon-c"]) == {
            "seldon-a", "seldon-b", "seldon-c",
        }

    def test_unset_env_yields_only_cli_names(self, monkeypatch):
        monkeypatch.delenv(SYNC_ALL_EXCLUDE_ENV, raising=False)

        assert _excluded_databases(["seldon-c"]) == {"seldon-c"}

    def test_blank_entries_are_dropped(self, monkeypatch):
        monkeypatch.setenv(SYNC_ALL_EXCLUDE_ENV, os.pathsep.join(["", "  "]))

        assert _excluded_databases(["", "  "]) == set()


# ===========================================================================
# C. Project mapping (pure — no Neo4j)
# ===========================================================================


def _make_project(root: Path, name: str, database: str) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "seldon.yaml").write_text(
        yaml.dump(
            {
                "project": {"name": name, "slug": name, "domain": "research"},
                "neo4j": {"uri": "bolt://localhost:7687", "database": database},
                "event_store": {"path": "seldon_events.jsonl"},
                "shared_ontology": {
                    "inheritance": "read-only", "source": ".", "vocabularies": [],
                },
            }
        )
    )
    (d / "seldon_events.jsonl").touch()
    return d


class TestProjectMapping:
    def test_a_project_nested_inside_a_project_is_found(self, tmp_path):
        """`brock_projects/nsf_aiday2026` owns its own database and its own log."""
        outer = _make_project(tmp_path, "outer", "seldon-outer")
        _make_project(outer, "inner", "seldon-inner")

        found = {
            ref.database for ref in _find_projects_including_nested([tmp_path], 3)
        }

        assert found == {"seldon-outer", "seldon-inner"}

    def test_mapping_reports_every_directory_claiming_a_database(self, tmp_path):
        _make_project(tmp_path / "live", "proj", "seldon-dup")
        _make_project(tmp_path / "quarantine", "proj", "seldon-dup")

        mapping, _ = _map_databases_to_projects([str(tmp_path)], 3)

        assert len(mapping["seldon-dup"]) == 2

    def test_no_roots_maps_nothing_and_says_so(self, monkeypatch):
        monkeypatch.delenv("SELDON_PROJECT_ROOTS", raising=False)

        mapping, notes = _map_databases_to_projects([], 3)

        assert mapping == {}
        assert any("no project roots given" in n for n in notes)

    def test_a_broken_config_does_not_stop_the_scan(self, tmp_path):
        _make_project(tmp_path, "good", "seldon-good")
        broken = tmp_path / "broken"
        broken.mkdir()
        (broken / "seldon.yaml").write_text("project: [unclosed\n")

        mapping, notes = _map_databases_to_projects([str(tmp_path)], 3)

        assert "seldon-good" in mapping
        assert any("unreadable" in n for n in notes)


# ===========================================================================
# D. Reporting and exit code (pure)
# ===========================================================================


class TestReplicaSyncReport:
    def test_epoch_current_requires_a_real_epoch(self):
        """Two zeros are not 'current' — that is an unsynced replica and an
        unpopulated master, which is a problem, not a no-op."""
        assert ReplicaSyncReport("db", current_epoch=0, target_epoch=0).epoch_current is False
        assert ReplicaSyncReport("db", current_epoch=6, target_epoch=6).epoch_current is True
        assert ReplicaSyncReport("db", current_epoch=3, target_epoch=6).epoch_current is False


# ===========================================================================
# E. Discovery and end-to-end sync (REQUIRE Neo4j)
# ===========================================================================


@pytest.fixture
def master_and_replica(neo4j_driver, monkeypatch, tmp_path):
    """A populated test master plus an empty replica database."""
    for db in (TEST_MASTER_DB, TEST_PROJECT_DB):
        with neo4j_driver.session(database="system") as s:
            s.run(f"CREATE DATABASE `{db}` IF NOT EXISTS WAIT")
        with neo4j_driver.session(database=db) as s:
            s.run("MATCH (n) DETACH DELETE n")

    monkeypatch.setenv("SELDON_ONTOLOGY_EVENT_DIR", str(tmp_path))
    result = _do_ingest(monkeypatch)
    assert result.exit_code == 0, f"ingest failed: {result.output}"
    monkeypatch.setattr(
        "seldon.commands.ontology.ONTOLOGY_MASTER_DB", TEST_MASTER_DB
    )
    return neo4j_driver


def _mark_as_replica(driver, database, epoch=0):
    with driver.session(database=database) as s:
        s.run(
            "MERGE (m:_OntologyReplicaMeta {key: 'replica'}) SET m.last_epoch = $e",
            e=epoch,
        )


def _replica_epoch(driver, database):
    with driver.session(database=database) as s:
        row = s.run(
            "MATCH (m:_OntologyReplicaMeta {key: 'replica'}) "
            "RETURN m.last_epoch AS e"
        ).single()
    return row["e"] if row else None


class TestDiscovery:
    """Marker-based, master-safe discovery against a real cluster."""

    def test_a_replica_is_discovered_and_the_master_is_not(self, master_and_replica):
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)

        replicas, skipped = _discover_replica_databases(
            master_and_replica, skip_test_harness=False
        )

        assert TEST_PROJECT_DB in replicas
        assert TEST_MASTER_DB not in replicas
        reason = dict(skipped).get(TEST_MASTER_DB, "")
        assert "_OntologyMeta" in reason or "master" in reason

    def test_the_configured_master_is_never_a_target(self, master_and_replica):
        """Even with the marker check bypassed, the master name is refused."""
        replicas, skipped = _discover_replica_databases(
            master_and_replica, skip_test_harness=False
        )

        assert ONTOLOGY_MASTER_DB not in replicas

    def test_a_master_that_is_not_the_configured_one_is_still_refused(
        self, master_and_replica, monkeypatch
    ):
        """The name guard is not enough: a master is recognised by its marker.

        The test master here carries BOTH markers and is not the configured
        master name, so only the ``_OntologyMeta`` check can save it. Syncing a
        master as if it were a replica would overwrite the authoritative copy.
        """
        _mark_as_replica(master_and_replica, TEST_MASTER_DB)
        monkeypatch.setattr(
            "seldon.commands.ontology.ONTOLOGY_MASTER_DB", "seldon-no-such-master"
        )

        replicas, skipped = _discover_replica_databases(
            master_and_replica, skip_test_harness=False
        )

        assert TEST_MASTER_DB not in replicas
        assert "_OntologyMeta" in dict(skipped)[TEST_MASTER_DB]

    def test_a_database_without_the_marker_is_not_a_replica(self, master_and_replica):
        """Discovery is by marker node, not by the `seldon-` name prefix."""
        with master_and_replica.session(database=TEST_PROJECT_DB) as s:
            s.run("MATCH (m:_OntologyReplicaMeta) DELETE m")

        replicas, _ = _discover_replica_databases(
            master_and_replica, skip_test_harness=False
        )

        assert TEST_PROJECT_DB not in replicas

    def test_harness_databases_are_skipped_by_default(self, master_and_replica):
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)

        replicas, skipped = _discover_replica_databases(master_and_replica)

        assert TEST_PROJECT_DB not in replicas
        assert "pytest harness" in dict(skipped)[TEST_PROJECT_DB]

    def test_an_operator_exclusion_is_honoured(self, master_and_replica):
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)

        replicas, skipped = _discover_replica_databases(
            master_and_replica, exclude=[TEST_PROJECT_DB], skip_test_harness=False
        )

        assert TEST_PROJECT_DB not in replicas
        assert dict(skipped)[TEST_PROJECT_DB] == "excluded by operator"


class TestPlanReplica:
    def test_an_unreadable_database_is_reported_not_raised(self, master_and_replica):
        report = _plan_replica(
            master_and_replica, "no-such-database-here", 6, {}, DEFAULT_INHERITANCE
        )

        assert report.error is not None
        assert report.delta is None

    def test_a_fresh_replica_plans_every_active_master_term(self, master_and_replica):
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)
        with master_and_replica.session(database=TEST_MASTER_DB) as s:
            master_terms = {
                dict(r["a"])["term_id"]: dict(r["a"])
                for r in s.run("MATCH (a:Artifact:OntologyTerm) RETURN a").data()
            }

        report = _plan_replica(
            master_and_replica, TEST_PROJECT_DB, 1, master_terms, DEFAULT_INHERITANCE
        )

        assert report.error is None
        assert len(report.delta.creates) == len(master_terms)
        assert report.current_epoch == 0


class TestRunSyncAll:
    """The command loop: plan-only by default, isolated failures, re-runnable."""

    @pytest.fixture(autouse=True)
    def _only_the_test_replica(self, monkeypatch):
        """Never let a test discover — let alone write to — a real replica."""
        self._discovered = [TEST_PROJECT_DB]
        monkeypatch.setattr(
            "seldon.commands.ontology._discover_replica_databases",
            lambda driver, exclude=(), skip_test_harness=True: (
                list(self._discovered), []
            ),
        )

    def test_dry_run_writes_nothing(self, master_and_replica, capsys):
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)

        code = _run_sync_all(
            master_and_replica, apply=False, exclude=(), roots=(), depth=3
        )

        assert code == 0
        assert "DRY RUN" in capsys.readouterr().out
        assert _replica_epoch(master_and_replica, TEST_PROJECT_DB) == 0

    def test_apply_syncs_the_replica_and_a_second_run_is_a_no_op(
        self, master_and_replica, capsys
    ):
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)

        assert _run_sync_all(
            master_and_replica, apply=True, exclude=(), roots=(), depth=3
        ) == 0
        first_out = capsys.readouterr().out
        epoch_after = _replica_epoch(master_and_replica, TEST_PROJECT_DB)

        assert epoch_after and epoch_after > 0
        assert "Synced 1 replica" in first_out

        assert _run_sync_all(
            master_and_replica, apply=True, exclude=(), roots=(), depth=3
        ) == 0
        second_out = capsys.readouterr().out

        assert "Synced 0 replica(s); 1 already current." in second_out
        assert _replica_epoch(master_and_replica, TEST_PROJECT_DB) == epoch_after

    def test_a_broken_database_does_not_strand_the_others(
        self, master_and_replica, capsys
    ):
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)
        self._discovered = ["no-such-database-here", TEST_PROJECT_DB]

        code = _run_sync_all(
            master_and_replica, apply=True, exclude=(), roots=(), depth=3
        )
        out = capsys.readouterr().out

        assert code == 1, "a failed database must produce a non-zero exit"
        assert "1 database(s) failed" in out
        assert _replica_epoch(master_and_replica, TEST_PROJECT_DB) > 0

    def test_a_failure_while_writing_is_recorded_not_raised(
        self, master_and_replica, tmp_path, capsys
    ):
        """`_do_sync` refuses a project with no shared_ontology section. That
        refusal must land in the report as one failed database, not escape and
        abandon the rest of the fleet."""
        root = tmp_path / "roots"
        project = root / "misconfigured"
        project.mkdir(parents=True)
        (project / "seldon.yaml").write_text(
            yaml.dump(
                {
                    "project": {"name": "m", "slug": "m", "domain": "research"},
                    "neo4j": {
                        "uri": "bolt://localhost:7687", "database": TEST_PROJECT_DB,
                    },
                    "event_store": {"path": "seldon_events.jsonl"},
                }
            )
        )
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)

        code = _run_sync_all(
            master_and_replica, apply=True, exclude=(), roots=(str(root),), depth=3
        )
        out = capsys.readouterr().out

        assert code == 1
        assert "shared_ontology" in out
        assert _replica_epoch(master_and_replica, TEST_PROJECT_DB) == 0

    def test_an_unmapped_replica_is_synced_without_an_event(
        self, master_and_replica, tmp_path, capsys, monkeypatch
    ):
        """No project directory means no event log — and the report says so."""
        monkeypatch.delenv("SELDON_PROJECT_ROOTS", raising=False)
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)

        _run_sync_all(master_and_replica, apply=True, exclude=(), roots=(), depth=3)
        out = capsys.readouterr().out

        assert "unmapped — graph-only, no event" in out

    def test_a_mapped_replica_records_its_event_in_its_own_log(
        self, master_and_replica, tmp_path, capsys
    ):
        root = tmp_path / "roots"
        project = _make_project(root, "mapped", TEST_PROJECT_DB)
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)

        _run_sync_all(
            master_and_replica, apply=True, exclude=(), roots=(str(root),), depth=3
        )

        events = [
            json.loads(line)
            for line in (project / "seldon_events.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert [e["event_type"] for e in events] == ["ontology_synced"]

    def test_an_ambiguous_replica_is_synced_without_an_event(
        self, master_and_replica, tmp_path, capsys
    ):
        """Two directories claim the database; attributing the event would be
        inventing a fact, so neither log gets one."""
        root = tmp_path / "roots"
        a = _make_project(root / "live", "proj", TEST_PROJECT_DB)
        b = _make_project(root / "quarantine", "proj", TEST_PROJECT_DB)
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)

        _run_sync_all(
            master_and_replica, apply=True, exclude=(), roots=(str(root),), depth=3
        )
        out = capsys.readouterr().out

        assert "AMBIGUOUS (2 dirs)" in out
        assert (a / "seldon_events.jsonl").read_text().strip() == ""
        assert (b / "seldon_events.jsonl").read_text().strip() == ""
        assert _replica_epoch(master_and_replica, TEST_PROJECT_DB) > 0

    def test_content_drift_at_a_current_epoch_is_flagged(
        self, master_and_replica, capsys
    ):
        """The epoch short-circuit would hide this, so the report must not."""
        _mark_as_replica(master_and_replica, TEST_PROJECT_DB)
        _run_sync_all(master_and_replica, apply=True, exclude=(), roots=(), depth=3)
        capsys.readouterr()

        with master_and_replica.session(database=TEST_PROJECT_DB) as s:
            s.run(
                "MATCH (a:Artifact:OntologyTerm) WITH a LIMIT 1 "
                "SET a.content_hash = 'drifted'"
            )

        _run_sync_all(master_and_replica, apply=False, exclude=(), roots=(), depth=3)
        out = capsys.readouterr().out

        assert "content diverges" in out


class TestSyncAllCli:
    """Flag wiring — the guards that stop a fleet write from being an accident."""

    def _invoke(self, args):
        from click.testing import CliRunner
        from seldon.commands.ontology import ontology_group

        return CliRunner().invoke(ontology_group, ["sync", *args])

    def test_dry_run_and_apply_together_are_refused(self):
        result = self._invoke(["--all", "--dry-run", "--apply"])

        assert result.exit_code != 0
        assert "contradict" in result.output

    def test_fleet_only_flags_are_refused_without_all(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = self._invoke(["--apply"])

        assert result.exit_code != 0
        assert "only to `sync --all`" in result.output
