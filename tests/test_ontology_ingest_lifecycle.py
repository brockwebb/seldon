"""Ingest change-detection and term deprecation (2026-09-03 defect sweep).

Two defects in `seldon ontology ingest` are covered here:

1. The epoch was bumped unconditionally *before* master content was compared,
   so an ingest that changed nothing still marked every replica stale and wrote
   a false ``ontology_ingested`` event. The epoch is a change counter: it may
   move only when master content moves.

2. There was no deprecation pass. A term dropped from the source vocabulary
   stayed ``active`` in master forever, and `sync` kept replicating it into
   every project as a live term.

Layout:
  A. Plan tests — pure functions, no Neo4j.
  B. Ingest behaviour — requires Neo4j (per-process test database as master).
  C. Sync behaviour — requires Neo4j (master + replica pair).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seldon.commands.ontology import IngestPlan, build_ingest_plan
from tests.testdb import TEST_DATABASE, TEST_PROJECT_DATABASE

from tests.test_ontology import VOCAB_PATH, _do_ingest, _make_project_config

TEST_MASTER_DB = TEST_DATABASE
TEST_PROJECT_DB = TEST_PROJECT_DATABASE

#: An entry in "## Related Terms (Defined Elsewhere)". Deleting its term line and
#: its definition line removes exactly one parsed term and no relationships,
#: which makes it the cheapest way to produce a source one term short of master.
#:
#: This fixture previously targeted a row of the "Terms That May Be Promoted from
#: Projects" table. That row was never a term — the parser captured it only
#: because of the b6714f3 section-boundary bug, fixed 2026-09-04. See
#: cc_tasks/2026-09-04_related_terms_parser_regression_SUBRESULT.md.
_REMOVABLE_TERM_BLOCK = (
    "**Fidelity**\n"
    ": Faithfulness of the operative state to the actual history of decisions. "
    "Use precisely; do not conflate with audio/signal fidelity.\n"
)

#: term_id the parser assigns to that entry.
ORPHANED_TERM_ID = "ontology:validity:related:fidelity"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vocab_missing_one_term(tmp_path: Path) -> Path:
    """Return a copy of the validity vocabulary with one term removed."""
    trimmed = tmp_path / "VALIDITY_VOCABULARY_trimmed.md"
    text = VOCAB_PATH.read_text(encoding="utf-8")
    assert _REMOVABLE_TERM_BLOCK in text, (
        f"fixture assumption broken: the '{ORPHANED_TERM_ID}' entry is no longer "
        f"verbatim in {VOCAB_PATH}"
    )
    trimmed.write_text(text.replace(_REMOVABLE_TERM_BLOCK, "", 1), encoding="utf-8")
    return trimmed


def _epoch(driver) -> int:
    with driver.session(database=TEST_MASTER_DB) as s:
        rec = s.run(
            "MATCH (m:_OntologyMeta {key: 'master'}) RETURN m.epoch AS epoch"
        ).single()
    return rec["epoch"] if rec else 0


def _term_state(driver, database: str, term_id: str):
    with driver.session(database=database) as s:
        rec = s.run(
            "MATCH (a:Artifact:OntologyTerm {term_id: $tid}) RETURN a.state AS state",
            tid=term_id,
        ).single()
    return rec["state"] if rec else None


def _events(event_dir: Path, event_type: str | None = None) -> list[dict]:
    path = event_dir / "seldon_events.jsonl"
    if not path.exists():
        return []
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if event_type is None:
        return events
    return [e for e in events if e["event_type"] == event_type]


def _term(term_id: str, definition: str = "d", category: str = "c"):
    """Minimal stand-in for a ParsedTerm, for the pure plan tests."""
    from seldon.ontology.parser import ParsedTerm

    return ParsedTerm(
        term_id=term_id,
        name=term_id.rsplit(":", 1)[-1],
        definition=definition,
        category=category,
        citations=[],
        namespace="ontology:test",
        extra={},
    )


def _master_node(term_id: str, definition: str = "d", category: str = "c",
                 state: str = "active"):
    """Master node properties matching what ingest would have written."""
    from seldon.commands.ontology import _term_content_hash

    return {
        "term_id": term_id,
        "artifact_id": f"aid-{term_id}",
        "name": term_id.rsplit(":", 1)[-1],
        "definition": definition,
        "category": category,
        "state": state,
        "content_hash": _term_content_hash(_term(term_id, definition, category)),
    }


# ===========================================================================
# A. Plan tests (NO Neo4j)
# ===========================================================================


class TestIngestPlan:
    """build_ingest_plan is the compare-first step; it must be exact."""

    def test_identical_source_is_no_change(self):
        parsed = {"ontology:test:a": (Path("v.md"), _term("ontology:test:a"))}
        master = {"ontology:test:a": _master_node("ontology:test:a")}

        plan = build_ingest_plan(parsed, master, set(), set())

        assert plan.unchanged == 1
        assert plan.to_create == []
        assert plan.to_update == []
        assert plan.has_changes(deprecate_missing=False) is False
        assert plan.has_changes(deprecate_missing=True) is False

    def test_new_term_is_a_change(self):
        parsed = {"ontology:test:a": (Path("v.md"), _term("ontology:test:a"))}

        plan = build_ingest_plan(parsed, {}, set(), set())

        assert len(plan.to_create) == 1
        assert plan.has_changes(deprecate_missing=False) is True

    def test_changed_definition_is_an_update(self):
        parsed = {"ontology:test:a": (Path("v.md"), _term("ontology:test:a", "new"))}
        master = {"ontology:test:a": _master_node("ontology:test:a", "old")}

        plan = build_ingest_plan(parsed, master, set(), set())

        assert len(plan.to_update) == 1
        assert plan.to_update[0][3] == "aid-ontology:test:a"
        assert plan.has_changes(deprecate_missing=False) is True

    def test_orphan_is_a_change_only_when_opted_in(self):
        """An orphan alone must not make an unchanged ingest look changed."""
        master = {"ontology:test:gone": _master_node("ontology:test:gone")}

        plan = build_ingest_plan({}, master, set(), set())

        assert [t["term_id"] for t in plan.to_deprecate] == ["ontology:test:gone"]
        assert plan.has_changes(deprecate_missing=False) is False
        assert plan.has_changes(deprecate_missing=True) is True

    def test_already_deprecated_orphan_is_not_re_deprecated(self):
        master = {
            "ontology:test:gone": _master_node("ontology:test:gone", state="deprecated")
        }

        plan = build_ingest_plan({}, master, set(), set())

        assert plan.to_deprecate == []
        assert plan.has_changes(deprecate_missing=True) is False

    def test_non_active_orphan_is_reported_not_deprecated(self):
        """`stale` has no legal direct edge to `deprecated` in the state machine."""
        master = {"ontology:test:s": _master_node("ontology:test:s", state="stale")}

        plan = build_ingest_plan({}, master, set(), set())

        assert plan.to_deprecate == []
        assert [t["term_id"] for t in plan.not_deprecatable] == ["ontology:test:s"]
        assert plan.has_changes(deprecate_missing=True) is False

    def test_resurrection_of_deprecated_term_is_blocked(self):
        parsed = {"ontology:test:a": (Path("v.md"), _term("ontology:test:a"))}
        master = {"ontology:test:a": _master_node("ontology:test:a", state="deprecated")}

        plan = build_ingest_plan(parsed, master, set(), set())

        assert plan.blocked_resurrections == ["ontology:test:a"]
        assert plan.to_update == []

    def test_missing_relationship_is_a_change(self):
        parsed = {
            "ontology:test:a": (Path("v.md"), _term("ontology:test:a")),
            "ontology:test:b": (Path("v.md"), _term("ontology:test:b")),
        }
        master = {
            "ontology:test:a": _master_node("ontology:test:a"),
            "ontology:test:b": _master_node("ontology:test:b"),
        }
        rels = {("ontology:test:a", "DEFINES_THREAT", "ontology:test:b")}

        plan = build_ingest_plan(parsed, master, rels, set())

        assert plan.rels_to_create == list(rels)
        assert plan.has_changes(deprecate_missing=False) is True

    def test_existing_relationship_is_not_a_change(self):
        parsed = {"ontology:test:a": (Path("v.md"), _term("ontology:test:a"))}
        master = {"ontology:test:a": _master_node("ontology:test:a")}
        rels = {("ontology:test:a", "PRECONDITION_FOR", "ontology:test:a")}

        plan = build_ingest_plan(parsed, master, rels, rels)

        assert plan.rels_to_create == []
        assert plan.has_changes(deprecate_missing=False) is False

    def test_unwritable_relationship_is_not_a_pending_change(self):
        """A relationship naming an unknown term can never be written.

        Counting it as pending would make every future ingest look changed and
        bump the epoch forever — the same defect by another route.
        """
        parsed = {"ontology:test:a": (Path("v.md"), _term("ontology:test:a"))}
        master = {"ontology:test:a": _master_node("ontology:test:a")}
        rels = {("ontology:test:a", "DEFINES_THREAT", "ontology:test:nowhere")}

        plan = build_ingest_plan(parsed, master, rels, set())

        assert plan.rels_to_create == []
        assert plan.unresolvable_rels == list(rels)
        assert plan.has_changes(deprecate_missing=False) is False

    def test_empty_plan_has_no_changes(self):
        assert IngestPlan().has_changes(deprecate_missing=True) is False


# ===========================================================================
# B. Ingest behaviour (REQUIRES Neo4j)
# ===========================================================================


@pytest.fixture
def clean_master(neo4j_driver):
    """Clear the per-process test database, used here as the master substitute."""
    with neo4j_driver.session(database="system") as s:
        s.run(f"CREATE DATABASE `{TEST_MASTER_DB}` IF NOT EXISTS WAIT")
    with neo4j_driver.session(database=TEST_MASTER_DB) as s:
        s.run("MATCH (n) DETACH DELETE n")
    yield neo4j_driver


@pytest.fixture
def event_dir(tmp_path, monkeypatch):
    """Redirect ingest's event log away from the real Seldon repo log."""
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("SELDON_ONTOLOGY_EVENT_DIR", str(d))
    return d


class TestNoOpIngest:
    """Defect 1: compare first, bump the epoch only on real change."""

    def test_noop_ingest_does_not_bump_epoch(
        self, clean_master, monkeypatch, event_dir
    ):
        first = _do_ingest(monkeypatch)
        assert first.exit_code == 0, first.output
        epoch_after_first = _epoch(clean_master)

        second = _do_ingest(monkeypatch)

        assert second.exit_code == 0, second.output
        assert _epoch(clean_master) == epoch_after_first
        assert "No changes" in second.output

    def test_noop_ingest_writes_no_event(self, clean_master, monkeypatch, event_dir):
        _do_ingest(monkeypatch)
        assert len(_events(event_dir, "ontology_ingested")) == 1

        _do_ingest(monkeypatch)

        assert len(_events(event_dir, "ontology_ingested")) == 1

    def test_noop_ingest_leaves_replica_current(
        self, clean_master, monkeypatch, event_dir, tmp_path
    ):
        """The whole point: a no-op ingest must not stale any replica."""
        from seldon.commands.ontology import _do_sync

        with clean_master.session(database="system") as s:
            s.run(f"CREATE DATABASE `{TEST_PROJECT_DB}` IF NOT EXISTS WAIT")
        with clean_master.session(database=TEST_PROJECT_DB) as s:
            s.run("MATCH (n) DETACH DELETE n")

        _do_ingest(monkeypatch)
        monkeypatch.setattr(
            "seldon.commands.ontology.ONTOLOGY_MASTER_DB", TEST_MASTER_DB
        )
        config = _make_project_config(tmp_path, database=TEST_PROJECT_DB)
        _do_sync(clean_master, TEST_PROJECT_DB, tmp_path, config)

        _do_ingest(monkeypatch)
        after = _do_sync(clean_master, TEST_PROJECT_DB, tmp_path, config)

        assert after.get("up_to_date") is True

    def test_dry_run_reports_the_same_plan(self, clean_master, monkeypatch, event_dir):
        _do_ingest(monkeypatch)

        dry = _do_ingest(monkeypatch, args=["--dry-run"])

        assert dry.exit_code == 0, dry.output
        assert "No changes" in dry.output
        assert "Master epoch would stay 1" in dry.output
        assert _epoch(clean_master) == 1

    def test_dry_run_on_pending_change_predicts_the_bump(
        self, clean_master, monkeypatch, event_dir, tmp_path
    ):
        _do_ingest(monkeypatch)
        trimmed = _vocab_missing_one_term(tmp_path)

        dry = _do_ingest(
            monkeypatch, vocab_path=trimmed, args=["--dry-run", "--deprecate-missing"]
        )

        assert dry.exit_code == 0, dry.output
        assert ORPHANED_TERM_ID in dry.output
        assert "epoch would move 1 -> 2" in dry.output
        # Predicted only: nothing was written.
        assert _epoch(clean_master) == 1
        assert _term_state(clean_master, TEST_MASTER_DB, ORPHANED_TERM_ID) == "active"

    def test_unparseable_source_writes_nothing(
        self, clean_master, monkeypatch, event_dir, tmp_path
    ):
        """A source that yields no terms must never touch the master database."""
        empty = tmp_path / "EMPTY_VOCABULARY.md"
        empty.write_text("# Nothing here\n")

        result = _do_ingest(monkeypatch, vocab_path=empty)

        assert result.exit_code != 0
        assert _epoch(clean_master) == 0
        with clean_master.session(database=TEST_MASTER_DB) as s:
            count = s.run(
                "MATCH (a:Artifact:OntologyTerm) RETURN count(a) AS cnt"
            ).single()["cnt"]
        assert count == 0
        assert _events(event_dir) == []


class TestDeprecationPass:
    """Defect 2: retire terms the source no longer defines — on opt-in only."""

    def test_orphan_reported_but_not_deprecated_by_default(
        self, clean_master, monkeypatch, event_dir, tmp_path
    ):
        _do_ingest(monkeypatch)
        trimmed = _vocab_missing_one_term(tmp_path)

        result = _do_ingest(monkeypatch, vocab_path=trimmed)

        assert result.exit_code == 0, result.output
        assert ORPHANED_TERM_ID in result.output
        assert "--deprecate-missing" in result.output
        assert _term_state(clean_master, TEST_MASTER_DB, ORPHANED_TERM_ID) == "active"
        assert _epoch(clean_master) == 1
        assert len(_events(event_dir, "ontology_ingested")) == 1

    def test_opt_in_deprecates_the_orphan(
        self, clean_master, monkeypatch, event_dir, tmp_path
    ):
        _do_ingest(monkeypatch)
        trimmed = _vocab_missing_one_term(tmp_path)

        result = _do_ingest(
            monkeypatch, vocab_path=trimmed, args=["--deprecate-missing"]
        )

        assert result.exit_code == 0, result.output
        assert _term_state(clean_master, TEST_MASTER_DB, ORPHANED_TERM_ID) == "deprecated"
        assert _epoch(clean_master) == 2

    def test_deprecation_is_recorded_as_a_state_change_event(
        self, clean_master, monkeypatch, event_dir, tmp_path
    ):
        """By event, never by silent mutation."""
        _do_ingest(monkeypatch)
        trimmed = _vocab_missing_one_term(tmp_path)

        _do_ingest(monkeypatch, vocab_path=trimmed, args=["--deprecate-missing"])

        transitions = _events(event_dir, "artifact_state_changed")
        assert len(transitions) == 1
        payload = transitions[0]["payload"]
        assert payload["artifact_type"] == "OntologyTerm"
        assert payload["from_state"] == "active"
        assert payload["to_state"] == "deprecated"

        ingested = _events(event_dir, "ontology_ingested")[-1]
        assert ingested["payload"]["deprecated_term_ids"] == [ORPHANED_TERM_ID]
        assert ingested["payload"]["deprecated_terms"] == 1

    def test_deprecation_pass_is_idempotent(
        self, clean_master, monkeypatch, event_dir, tmp_path
    ):
        """A second run over the same trimmed source is a no-op, not a re-bump."""
        _do_ingest(monkeypatch)
        trimmed = _vocab_missing_one_term(tmp_path)
        _do_ingest(monkeypatch, vocab_path=trimmed, args=["--deprecate-missing"])

        again = _do_ingest(monkeypatch, vocab_path=trimmed, args=["--deprecate-missing"])

        assert again.exit_code == 0, again.output
        assert "No changes" in again.output
        assert _epoch(clean_master) == 2

    def test_resurrecting_a_deprecated_term_is_refused(
        self, clean_master, monkeypatch, event_dir, tmp_path
    ):
        """`deprecated` is terminal, so ingest must abort rather than reactivate."""
        _do_ingest(monkeypatch)
        trimmed = _vocab_missing_one_term(tmp_path)
        _do_ingest(monkeypatch, vocab_path=trimmed, args=["--deprecate-missing"])

        result = _do_ingest(monkeypatch)

        assert result.exit_code != 0
        assert ORPHANED_TERM_ID in result.output
        assert _epoch(clean_master) == 2
        assert _term_state(clean_master, TEST_MASTER_DB, ORPHANED_TERM_ID) == "deprecated"


# ===========================================================================
# C. Sync behaviour (REQUIRES Neo4j — master + replica)
# ===========================================================================


@pytest.fixture
def master_and_replica(neo4j_driver):
    """Clear both the master substitute and the replica database."""
    for db in (TEST_MASTER_DB, TEST_PROJECT_DB):
        with neo4j_driver.session(database="system") as s:
            s.run(f"CREATE DATABASE `{db}` IF NOT EXISTS WAIT")
        with neo4j_driver.session(database=db) as s:
            s.run("MATCH (n) DETACH DELETE n")
    yield neo4j_driver


class TestSyncPropagatesDeprecation:
    """A replica must never keep calling a term active after master retires it."""

    def _sync(self, driver, monkeypatch, tmp_path):
        from seldon.commands.ontology import _do_sync

        monkeypatch.setattr(
            "seldon.commands.ontology.ONTOLOGY_MASTER_DB", TEST_MASTER_DB
        )
        config = _make_project_config(tmp_path, database=TEST_PROJECT_DB)
        return _do_sync(driver, TEST_PROJECT_DB, tmp_path, config)

    def test_deprecation_propagates_to_an_existing_replica_term(
        self, master_and_replica, monkeypatch, event_dir, tmp_path
    ):
        _do_ingest(monkeypatch)
        self._sync(master_and_replica, monkeypatch, tmp_path)
        assert (
            _term_state(master_and_replica, TEST_PROJECT_DB, ORPHANED_TERM_ID)
            == "active"
        )

        trimmed = _vocab_missing_one_term(tmp_path)
        _do_ingest(monkeypatch, vocab_path=trimmed, args=["--deprecate-missing"])
        result = self._sync(master_and_replica, monkeypatch, tmp_path)

        assert result["deprecated"] >= 1
        assert (
            _term_state(master_and_replica, TEST_PROJECT_DB, ORPHANED_TERM_ID)
            == "deprecated"
        )

    def test_deprecated_term_is_not_introduced_into_a_fresh_replica(
        self, master_and_replica, monkeypatch, event_dir, tmp_path
    ):
        """A project that never carried the term gains nothing from a corpse."""
        _do_ingest(monkeypatch)
        trimmed = _vocab_missing_one_term(tmp_path)
        _do_ingest(monkeypatch, vocab_path=trimmed, args=["--deprecate-missing"])

        result = self._sync(master_and_replica, monkeypatch, tmp_path)

        assert result["skipped_deprecated"] == 1
        assert _term_state(master_and_replica, TEST_PROJECT_DB, ORPHANED_TERM_ID) is None

    def test_sync_still_replicates_live_terms(
        self, master_and_replica, monkeypatch, event_dir, tmp_path
    ):
        """Skipping dead terms must not skip live ones."""
        _do_ingest(monkeypatch)
        trimmed = _vocab_missing_one_term(tmp_path)
        _do_ingest(monkeypatch, vocab_path=trimmed, args=["--deprecate-missing"])

        result = self._sync(master_and_replica, monkeypatch, tmp_path)

        assert result["new"] > 0
        assert (
            _term_state(master_and_replica, TEST_PROJECT_DB, "ontology:validity:SFV")
            == "active"
        )
