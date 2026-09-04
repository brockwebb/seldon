"""CLI commands for shared ontology management (AD-017).

Provides three subcommands:
  seldon ontology ingest   -- parse vocabulary and write to master DB
  seldon ontology sync     -- pull master terms into project DB
  seldon ontology list     -- display ontology terms

Master database: seldon-ontology (shared across all projects).
Project databases: each project gets read-only replicas via sync.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import click

from seldon.config import ONTOLOGY_MASTER_DB
from seldon.core.events import append_event, make_event
from seldon.core.graph import create_indexes

#: Environment variable overriding the directory whose event log `ingest`
#: appends to. Ingest is a repo-level command: its events describe the shared
#: master database, so by default they land in the Seldon repo's event store.
#: The override mirrors SELDON_ONTOLOGY_PATH and exists for the same reason —
#: tests and CI must be able to run a real ingest without appending to the real
#: log.
ONTOLOGY_EVENT_DIR_ENV = "SELDON_ONTOLOGY_EVENT_DIR"

#: Domain whose state machine governs OntologyTerm nodes in the master database.
#: The master is not a project — it has no seldon.yaml to read a domain from —
#: and OntologyTerm is defined by the research domain (AD-017).
ONTOLOGY_DOMAIN = "research"

#: Neo4j reports a missing database with this error code. Matched (alongside the
#: message text, which differs between server versions) so dry-run can report
#: "master does not exist yet" instead of crashing.
_DB_NOT_FOUND_CODE = "Neo.ClientError.Database.DatabaseNotFound"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _term_content_hash(term) -> str:
    """Compute a SHA-256 hash of a term's definition for change detection.

    Uses term_id + definition + category so renames and recategorizations
    are also detected.
    """
    payload = f"{term.term_id}|{term.definition}|{term.category}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_neo4j_driver():
    """Create a Neo4j driver using env var credentials.

    Does not require a project config -- credentials always come from
    environment variables (NEO4J_USERNAME/NEO4J_PASSWORD).
    """
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER") or "neo4j"
    password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS") or "password"

    extra_kwargs = {}
    try:
        from neo4j import NotificationMinimumSeverity
        extra_kwargs["notifications_min_severity"] = NotificationMinimumSeverity.OFF
        extra_kwargs["warn_notification_severity"] = NotificationMinimumSeverity.OFF
    except ImportError:
        pass

    return GraphDatabase.driver(uri, auth=(username, password), **extra_kwargs)


def _ensure_master_db(driver) -> None:
    """Create the master ontology database if it does not exist."""
    with driver.session(database="system") as session:
        session.run(
            f"CREATE DATABASE `{ONTOLOGY_MASTER_DB}` IF NOT EXISTS WAIT"
        )


def _ensure_master_indexes(driver) -> None:
    """Create standard Artifact indexes plus term_id index on master DB."""
    with driver.session(database=ONTOLOGY_MASTER_DB) as session:
        create_indexes(session)
        session.run(
            "CREATE INDEX ontology_term_id IF NOT EXISTS "
            "FOR (a:Artifact) ON (a.term_id)"
        )


def _get_or_create_master_meta(driver) -> int:
    """Ensure _OntologyMeta node exists and return current epoch."""
    with driver.session(database=ONTOLOGY_MASTER_DB) as session:
        result = session.run(
            "MERGE (m:_OntologyMeta {key: 'master'}) "
            "ON CREATE SET m.epoch = 0, m.created_at = $now "
            "RETURN m.epoch AS epoch",
            now=_now_iso(),
        ).single()
        return result["epoch"]


def _increment_epoch(driver) -> int:
    """Increment and return the new master epoch."""
    with driver.session(database=ONTOLOGY_MASTER_DB) as session:
        result = session.run(
            "MATCH (m:_OntologyMeta {key: 'master'}) "
            "SET m.epoch = m.epoch + 1, m.updated_at = $now "
            "RETURN m.epoch AS epoch",
            now=_now_iso(),
        ).single()
        return result["epoch"]


def _resolve_vocabulary_paths() -> list[Path]:
    """Find all vocabulary files using env var override or project config.

    Resolution order:
    1. SELDON_ONTOLOGY_PATH env var — explicit override, single file, takes
       precedence over config (used in tests and CI scripts).
    2. Project seldon.yaml shared_ontology.source + vocabularies (all entries)
    3. Error with instructions

    Returns list of existing vocabulary paths in config order.
    """
    from seldon.config import get_shared_ontology_sources, load_project_config

    # Env var override takes precedence — enables test isolation and CI use
    env_path = os.getenv("SELDON_ONTOLOGY_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return [p]
        raise click.ClickException(
            f"SELDON_ONTOLOGY_PATH points to non-existent file: {env_path}"
        )

    # Fall back to project config (all vocabulary entries)
    try:
        config = load_project_config()
        all_paths = get_shared_ontology_sources(config)
        existing = [p for p in all_paths if p.exists()]
        if existing:
            return existing
    except FileNotFoundError:
        pass

    raise click.ClickException(
        "Cannot locate vocabulary file. Either:\n"
        "  1. Run from a project directory with seldon.yaml containing "
        "shared_ontology.source + vocabularies\n"
        "  2. Set SELDON_ONTOLOGY_PATH=/path/to/VALIDITY_VOCABULARY.md"
    )


def _resolve_vocabulary_path() -> Path:
    """Find the first vocabulary file using config or env var (backwards compat)."""
    paths = _resolve_vocabulary_paths()
    return paths[0]


def _parse_vocabulary_file(vocab_path: Path):
    """Dispatch to the correct parser based on filename.

    Returns ParsedVocabulary from whichever parser matches the file.
    """
    from seldon.ontology.parser import parse_vocabulary

    filename = vocab_path.name.upper()
    if "PRACTITIONER" in filename:
        from seldon.ontology.practitioner_parser import parse_practitioner_vocabulary
        return parse_practitioner_vocabulary(vocab_path)
    else:
        return parse_vocabulary(vocab_path)


def _seldon_repo_dir() -> Path:
    """Return the directory whose event log ingest writes to.

    Defaults to the Seldon repository root. ``SELDON_ONTOLOGY_EVENT_DIR``
    overrides it (see the constant's docstring).

    Raises:
        click.ClickException: If the override names a directory that does not
            exist. Falling back to the real repo log would silently write master
            ontology events into a project that did not ask for them.
    """
    override = os.getenv(ONTOLOGY_EVENT_DIR_ENV)
    if override:
        path = Path(override)
        if not path.is_dir():
            raise click.ClickException(
                f"{ONTOLOGY_EVENT_DIR_ENV} points to a non-existent directory: "
                f"{override}"
            )
        return path
    return Path(__file__).parents[2]


def _term_to_props(term, epoch: int, content_hash: str) -> Dict[str, Any]:
    """Convert a ParsedTerm to a Neo4j properties dict.

    Does not set source_vocabulary — callers must set it directly, since it
    depends on the actual file path used at call time (not stored on the term).
    """
    props = {
        "term_id": term.term_id,
        "name": term.name,
        "definition": term.definition,
        "category": term.category,
        "namespace": term.namespace,
        "content_hash": content_hash,
        "epoch": epoch,
        "state": "active",
        "artifact_type": "OntologyTerm",
    }
    # Store citations as JSON string (Neo4j doesn't support nested lists well)
    if term.citations:
        props["citations"] = json.dumps(term.citations)
    # Store extra fields as JSON
    if term.extra:
        props["extra"] = json.dumps(term.extra)
    return props


# ---------------------------------------------------------------------------
# Ingest planning
#
# The plan is computed BEFORE anything is written, and the master epoch may only
# move when the plan is non-empty. The epoch is a change counter that every
# replica compares against, so bumping it unconditionally (the pre-2026-09-04
# behaviour) marked every replica stale on a run that changed nothing.
# ---------------------------------------------------------------------------

#: A relationship as compared between source and master: (from_id, TYPE, to_id).
RelTriple = Tuple[str, str, str]


@dataclass
class IngestPlan:
    """Every write an ingest would perform, computed before the first write.

    Attributes:
        to_create: ``(vocabulary_path, ParsedTerm, content_hash)`` for terms
            absent from master.
        to_update: ``(vocabulary_path, ParsedTerm, content_hash, artifact_id)``
            for terms whose content hash differs from master's.
        to_deprecate: Master term property dicts that are ``active`` but absent
            from the parsed source.
        rels_to_create: Relationship triples present in the source and absent
            from master, whose endpoints both exist (or are about to).
        unresolvable_rels: Source relationships naming a term that exists
            neither in the source nor in master. They can never be written, so
            they are reported rather than counted as a pending change — counting
            them would make every subsequent ingest look "changed" forever.
        blocked_resurrections: term_ids present in the source that master holds
            in the terminal ``deprecated`` state.
        not_deprecatable: Master terms absent from the source that are neither
            ``active`` nor ``deprecated``, so the state machine has no legal
            direct edge to ``deprecated``.
        unchanged: Count of source terms already current in master.
    """

    to_create: List[Tuple[Path, Any, str]] = field(default_factory=list)
    to_update: List[Tuple[Path, Any, str, str]] = field(default_factory=list)
    to_deprecate: List[Dict[str, Any]] = field(default_factory=list)
    rels_to_create: List[RelTriple] = field(default_factory=list)
    unresolvable_rels: List[RelTriple] = field(default_factory=list)
    blocked_resurrections: List[str] = field(default_factory=list)
    not_deprecatable: List[Dict[str, Any]] = field(default_factory=list)
    unchanged: int = 0

    def has_changes(self, deprecate_missing: bool) -> bool:
        """Return True if executing this plan would change master content.

        Args:
            deprecate_missing: Whether the deprecation pass is opted in. Orphan
                terms are only a pending change when it is — without the flag
                they are reported and left alone, so they must not by themselves
                make an otherwise-unchanged ingest look changed.
        """
        if self.to_create or self.to_update or self.rels_to_create:
            return True
        return bool(deprecate_missing and self.to_deprecate)


def build_ingest_plan(
    parsed_index: Dict[str, Tuple[Path, Any]],
    master_terms: Dict[str, Dict[str, Any]],
    parsed_rels: Set[RelTriple],
    master_rels: Set[RelTriple],
) -> IngestPlan:
    """Diff a parsed vocabulary against master content.

    Pure function: no database access, no writes, no I/O. This is what makes
    "compare first, bump only on change" checkable in a unit test.

    Args:
        parsed_index: term_id -> (source vocabulary path, ParsedTerm).
        master_terms: term_id -> master node properties.
        parsed_rels: Relationship triples declared by the source.
        master_rels: Relationship triples already in master.

    Returns:
        The :class:`IngestPlan`.
    """
    plan = IngestPlan()

    for term_id, (vocab_path, term) in parsed_index.items():
        existing = master_terms.get(term_id)
        content_hash = _term_content_hash(term)
        if existing is None:
            plan.to_create.append((vocab_path, term, content_hash))
        elif existing.get("state") == "deprecated":
            # `deprecated` is terminal in the OntologyTerm state machine, so a
            # term that came back in the source cannot legally be reactivated.
            plan.blocked_resurrections.append(term_id)
        elif existing.get("content_hash") != content_hash:
            plan.to_update.append(
                (vocab_path, term, content_hash, existing["artifact_id"])
            )
        else:
            plan.unchanged += 1

    for term_id, existing in master_terms.items():
        if term_id in parsed_index:
            continue
        state = existing.get("state")
        if state == "active":
            plan.to_deprecate.append(existing)
        elif state != "deprecated":
            plan.not_deprecatable.append(existing)

    known_terms = set(parsed_index) | set(master_terms)
    for rel in sorted(parsed_rels):
        if rel in master_rels:
            continue
        if rel[0] in known_terms and rel[2] in known_terms:
            plan.rels_to_create.append(rel)
        else:
            plan.unresolvable_rels.append(rel)

    plan.blocked_resurrections.sort()
    return plan


def _read_master_state(
    driver, allow_missing: bool = False
) -> Tuple[int, Dict[str, Dict[str, Any]], Set[RelTriple]]:
    """Read the master epoch, terms and relationships.

    Args:
        driver: Connected Neo4j driver.
        allow_missing: When True, a master database that does not exist yet is
            reported as ``(0, {}, set())`` instead of raising. Used by
            ``--dry-run``, which must not create the database it inspects.

    Returns:
        ``(epoch, terms_by_term_id, relationship_triples)``. Epoch is 0 when no
        ``_OntologyMeta`` node exists.

    Raises:
        neo4j.exceptions.Neo4jError: On any failure other than a missing
            database with ``allow_missing`` set.
    """
    try:
        with driver.session(database=ONTOLOGY_MASTER_DB) as session:
            meta = session.run(
                "MATCH (m:_OntologyMeta {key: 'master'}) RETURN m.epoch AS epoch"
            ).single()
            epoch = meta["epoch"] if meta else 0
            terms = {
                dict(r["a"])["term_id"]: dict(r["a"])
                for r in session.run(
                    "MATCH (a:Artifact:OntologyTerm) RETURN a"
                ).data()
            }
            rels = {
                (r["from_id"], r["rel_type"], r["to_id"])
                for r in session.run(
                    "MATCH (a:Artifact:OntologyTerm)-[r]->(b:Artifact:OntologyTerm) "
                    "RETURN a.term_id AS from_id, type(r) AS rel_type, "
                    "b.term_id AS to_id"
                ).data()
            }
        return epoch, terms, rels
    except Exception as e:
        if allow_missing and _is_missing_database_error(e):
            return 0, {}, set()
        raise


def _is_missing_database_error(exc: Exception) -> bool:
    """Return True if ``exc`` reports that the target database does not exist."""
    if getattr(exc, "code", None) == _DB_NOT_FOUND_CODE:
        return True
    text = str(exc).lower()
    return "database does not exist" in text or "database not found" in text


# ---------------------------------------------------------------------------
# Core sync logic (shared between `sync` command and `init` hook)
# ---------------------------------------------------------------------------

def _do_sync(
    driver,
    database: str,
    project_dir: Path,
    config: dict,
    emit_event: bool = True,
) -> Dict[str, Any]:
    """Pull OntologyTerms from master into a project database.

    Args:
        driver: Neo4j driver (already authenticated).
        database: Project database name.
        project_dir: Path to project root (for event store).
        config: Loaded seldon.yaml dict.
        emit_event: Append an ``ontology_synced`` event on success. Set False
            when called from event replay, which restores existing state rather
            than recording a new fact — see seldon.core.sync._restore_ontology.

    Returns:
        Dict with keys: epoch, terms, new, updated, deprecated, state_synced,
        skipped_deprecated, relationships, up_to_date. ``deprecated`` counts
        both terms master has retired and terms master no longer holds at all;
        ``skipped_deprecated`` counts master terms this replica never carried
        and that master has already retired, which are deliberately not created.

    Raises:
        RuntimeError: If shared_ontology config is missing, inheritance mode is
            unsupported, master DB is not populated, or a relationship type from
            master contains unsafe characters.
    """
    from seldon.core.graph import change_state, create_artifact, update_artifact

    shared = config.get("shared_ontology")
    if not shared:
        raise RuntimeError(
            "No shared_ontology section in seldon.yaml. "
            "Cannot sync without ontology configuration."
        )

    inheritance = shared.get("inheritance", "read-only")
    if inheritance != "read-only":
        raise RuntimeError(
            f"Unsupported inheritance mode: {inheritance!r}. "
            "Only 'read-only' is currently supported."
        )

    # Read master epoch
    try:
        with driver.session(database=ONTOLOGY_MASTER_DB) as session:
            result = session.run(
                "MATCH (m:_OntologyMeta {key: 'master'}) RETURN m.epoch AS epoch"
            ).single()
            if result is None:
                raise RuntimeError(
                    f"No _OntologyMeta node in {ONTOLOGY_MASTER_DB}. "
                    "Run `seldon ontology ingest` first."
                )
            master_epoch = result["epoch"]
    except RuntimeError:
        raise
    except Exception as e:
        if "database does not exist" in str(e).lower():
            raise RuntimeError(
                f"Database {ONTOLOGY_MASTER_DB} does not exist. "
                "Run `seldon ontology ingest` first."
            )
        raise

    # Read project's last synced epoch
    with driver.session(database=database) as session:
        result = session.run(
            "MATCH (m:_OntologyReplicaMeta {key: 'replica'}) "
            "RETURN m.last_epoch AS last_epoch"
        ).single()
        project_epoch = result["last_epoch"] if result else 0

    if project_epoch == master_epoch and master_epoch > 0:
        return {
            "epoch": master_epoch,
            "terms": 0,
            "new": 0,
            "updated": 0,
            "deprecated": 0,
            "state_synced": 0,
            "skipped_deprecated": 0,
            "relationships": 0,
            "up_to_date": True,
        }

    # Fetch all master terms
    with driver.session(database=ONTOLOGY_MASTER_DB) as session:
        master_records = session.run(
            "MATCH (a:Artifact:OntologyTerm) RETURN a"
        ).data()
        master_terms = {dict(r["a"])["term_id"]: dict(r["a"]) for r in master_records}

        # Fetch all master relationships
        master_rels = session.run(
            "MATCH (a:Artifact:OntologyTerm)-[r]->(b:Artifact:OntologyTerm) "
            "RETURN a.term_id AS from_id, type(r) AS rel_type, b.term_id AS to_id"
        ).data()

    # Fetch existing project terms
    with driver.session(database=database) as session:
        project_records = session.run(
            "MATCH (a:Artifact:OntologyTerm) RETURN a"
        ).data()
        project_terms = {dict(r["a"])["term_id"]: dict(r["a"]) for r in project_records}

    new_count = 0
    updated_count = 0
    deprecated_count = 0
    state_synced_count = 0
    skipped_deprecated_count = 0
    rel_count = 0

    with driver.session(database=database) as session:
        # Sync terms from master
        for term_id, master_term in master_terms.items():
            props = dict(master_term)
            props["inheritance"] = inheritance
            master_state = props.get("state")

            if term_id not in project_terms:
                if master_state == "deprecated":
                    # Master retired this term and the replica never carried it.
                    # Introducing a dead term into a project that never
                    # referenced it adds no provenance and pollutes
                    # `seldon ontology list`, so it is skipped. Replicas that DO
                    # carry it have the deprecation propagated below.
                    skipped_deprecated_count += 1
                    continue
                # New term -- create with same artifact_id as master
                props.setdefault("created_at", _now_iso())
                create_artifact(session, "OntologyTerm", props)
                new_count += 1
            else:
                proj_term = project_terms[term_id]
                # Existing term -- check if content changed. State is handled
                # separately below, so a content update cannot smuggle in an
                # unexamined lifecycle change.
                if props.get("content_hash") != proj_term.get("content_hash"):
                    content_props = dict(props)
                    content_props.pop("state", None)
                    content_props["updated_at"] = _now_iso()
                    update_artifact(session, props["artifact_id"], content_props)
                    updated_count += 1
                # A term master has retired keeps its content hash, so a
                # content-only comparison would leave the replica calling a dead
                # term 'active'. Master is authoritative for the lifecycle of an
                # inherited term: replicate its state whenever it diverges.
                if master_state and master_state != proj_term.get("state"):
                    change_state(session, proj_term["artifact_id"], master_state)
                    if master_state == "deprecated":
                        deprecated_count += 1
                    else:
                        state_synced_count += 1

        # Deprecate project terms not in master
        for term_id, proj_term in project_terms.items():
            if term_id not in master_terms and proj_term.get("state") != "deprecated":
                change_state(session, proj_term["artifact_id"], "deprecated")
                deprecated_count += 1

        # Sync relationships using MERGE
        for rel in master_rels:
            from_id = rel["from_id"]
            to_id = rel["to_id"]
            rel_type = rel["rel_type"]
            # Guard against Cypher injection: rel_type comes from Neo4j type()
            # and is interpolated into the query string, so validate it first.
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', rel_type):
                raise RuntimeError(f"Invalid relationship type from master: {rel_type!r}")
            # Use MERGE to avoid duplicates
            cypher = (
                f"MATCH (a:Artifact:OntologyTerm {{term_id: $from_id}}), "
                f"(b:Artifact:OntologyTerm {{term_id: $to_id}}) "
                f"MERGE (a)-[r:{rel_type}]->(b) "
                f"ON CREATE SET r.created_at = $now "
                f"RETURN r"
            )
            result = session.run(
                cypher, from_id=from_id, to_id=to_id, now=_now_iso()
            ).single()
            if result:
                rel_count += 1

        # Update replica meta
        session.run(
            "MERGE (m:_OntologyReplicaMeta {key: 'replica'}) "
            "SET m.last_epoch = $epoch, m.synced_at = $now",
            epoch=master_epoch, now=_now_iso(),
        )

    # Write sync event to project event store.
    #
    # Suppressed when called from event replay (seldon rebuild). Replay restores
    # ontology state by re-running this sync, and if it appended an event each
    # time, every rebuild would grow the log by one ontology_synced event, which
    # would in turn trigger another restore on the next rebuild. Restoring state
    # is not a new fact about the project and must not be recorded as one.
    if emit_event:
        event = make_event(
            event_type="ontology_synced",
            actor="seldon",
            authority="accepted",
            payload={
                "master_epoch": master_epoch,
                "new_terms": new_count,
                "updated_terms": updated_count,
                "deprecated_terms": deprecated_count,
                "state_synced_terms": state_synced_count,
                "skipped_deprecated_terms": skipped_deprecated_count,
                "relationships_synced": rel_count,
            },
        )
        append_event(project_dir, event)

    return {
        "epoch": master_epoch,
        "terms": len(master_terms),
        "new": new_count,
        "updated": updated_count,
        "deprecated": deprecated_count,
        "state_synced": state_synced_count,
        "skipped_deprecated": skipped_deprecated_count,
        "relationships": rel_count,
        "up_to_date": False,
    }


# ---------------------------------------------------------------------------
# Click command group
# ---------------------------------------------------------------------------

@click.group("ontology")
def ontology_group():
    """Manage the shared validity ontology (AD-017)."""
    pass


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

@ontology_group.command("ingest")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report the exact change plan without writing anything.",
)
@click.option(
    "--deprecate-missing",
    is_flag=True,
    help=(
        "Also mark master terms that are absent from the source as deprecated. "
        "IRREVERSIBLE: 'deprecated' is a terminal state. Without this flag such "
        "terms are only reported."
    ),
)
def ingest_command(dry_run: bool, deprecate_missing: bool):
    """Parse vocabulary files and write terms to the master ontology database.

    Reads all vocabulary files configured in seldon.yaml shared_ontology.vocabularies.
    Writes to the shared seldon-ontology database only. Never touches
    project databases. Use `seldon ontology sync` to pull into a project.

    The master epoch is a change counter every replica compares itself against,
    so it moves only when this run actually changes master content. An ingest
    that finds nothing to do writes nothing: no epoch bump, no event, no stale
    replicas.

    Terms that master holds but the source no longer defines are reported by
    default and deprecated only under ``--deprecate-missing``, because
    ``deprecated`` is terminal for an OntologyTerm and a truncated or
    mid-edit source file must not be able to retire vocabulary by accident.
    """
    from dotenv import load_dotenv
    load_dotenv(override=False)

    vocab_paths = _resolve_vocabulary_paths()

    # Parse every vocabulary file up front so a parse failure happens before
    # Neo4j is touched at all.
    all_parsed = []
    for vocab_path in vocab_paths:
        click.echo(f"Parsing vocabulary: {vocab_path}")
        parsed = _parse_vocabulary_file(vocab_path)
        click.echo(
            f"  Parsed {len(parsed.terms)} terms, "
            f"{len(parsed.relationships)} relationships "
            f"(file hash: {parsed.content_hash[:12]}...)"
        )
        all_parsed.append((vocab_path, parsed))

    # Index by term_id. A term_id defined in two files is a source conflict:
    # the later file silently won before this was surfaced, and a silent winner
    # in a shared vocabulary is exactly the kind of drift the ontology exists
    # to prevent.
    parsed_index: Dict[str, Tuple[Path, Any]] = {}
    duplicates: List[str] = []
    for vocab_path, parsed in all_parsed:
        for term in parsed.terms:
            if term.term_id in parsed_index:
                duplicates.append(term.term_id)
            parsed_index[term.term_id] = (vocab_path, term)

    parsed_rels: Set[RelTriple] = set()
    for _, parsed in all_parsed:
        for rel in parsed.relationships:
            rel_type = rel.rel_type.upper()
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", rel_type):
                raise click.ClickException(
                    f"Invalid relationship type in source vocabulary: {rel_type!r}"
                )
            parsed_rels.add((rel.from_term_id, rel_type, rel.to_term_id))

    total_terms = len(parsed_index)
    if len(all_parsed) > 1:
        click.echo(
            f"Total: {total_terms} terms, {len(parsed_rels)} relationships "
            f"across {len(all_parsed)} files."
        )
    if duplicates:
        raise click.ClickException(
            "Duplicate term_id across vocabulary files: "
            + ", ".join(sorted(set(duplicates)))
            + "\nEach term must be defined in exactly one vocabulary."
        )

    # A parse that yields nothing is a broken source or a broken parser, never
    # an instruction to empty the shared ontology. Refuse before any write.
    # Both current parsers raise on an empty parse themselves; this is the
    # backstop for the next one, which writes to a database every project reads.
    if total_terms == 0:
        raise click.ClickException(
            "Parsed 0 terms — refusing to ingest. Check the vocabulary file "
            "and the parser before re-running."
        )

    driver = _get_neo4j_driver()
    try:
        if not dry_run:
            _ensure_master_db(driver)
            _ensure_master_indexes(driver)
            # Ensure the epoch counter exists before it is read or incremented.
            # Idempotent: on an established master this is a plain read.
            _get_or_create_master_meta(driver)

        # Dry run must not create the database it inspects, so a missing master
        # is reported as an empty one rather than provisioned.
        master_epoch, master_terms, master_rels = _read_master_state(
            driver, allow_missing=dry_run
        )

        plan = build_ingest_plan(parsed_index, master_terms, parsed_rels, master_rels)

        if plan.blocked_resurrections:
            raise click.ClickException(
                "Source defines terms that master holds as deprecated, which is "
                "a terminal state — refusing to ingest so nothing is partially "
                "written:\n  "
                + "\n  ".join(plan.blocked_resurrections)
                + "\nRemove them from the source, or issue new term_ids."
            )

        for term in plan.not_deprecatable:
            click.echo(
                f"  WARNING: {term.get('term_id')} is absent from the source but "
                f"is in state {term.get('state')!r}, which has no legal "
                f"transition to 'deprecated'. Left untouched."
            )
        for rel in plan.unresolvable_rels:
            click.echo(
                f"  WARNING: relationship {rel[0]} -{rel[1]}-> {rel[2]} names a "
                f"term that exists in neither the source nor master. Skipped."
            )

        will_change = plan.has_changes(deprecate_missing)

        if dry_run:
            _report_plan(plan, master_epoch, deprecate_missing, will_change)
            return

        if not will_change:
            click.echo(
                f"No changes: {plan.unchanged} terms already current. "
                f"Master epoch stays {master_epoch}; no event written."
            )
            _report_orphans(plan, deprecate_missing)
            return

        new_epoch = _increment_epoch(driver)
        counts = _apply_ingest_plan(
            driver, plan, new_epoch, deprecate_missing
        )

        event = make_event(
            event_type="ontology_ingested",
            actor="seldon",
            authority="accepted",
            payload={
                "master_epoch": new_epoch,
                "source_files": [str(p) for p, _ in all_parsed],
                "new_terms": counts["new"],
                "updated_terms": counts["updated"],
                "unchanged_terms": plan.unchanged,
                "deprecated_terms": counts["deprecated"],
                "deprecated_term_ids": counts["deprecated_term_ids"],
                "relationships_created": counts["relationships"],
                "total_terms": total_terms,
            },
        )
        append_event(_seldon_repo_dir(), event)

        click.echo(
            f"Master epoch {new_epoch}: Ingested {counts['new']} new, "
            f"updated {counts['updated']}, unchanged {plan.unchanged} terms. "
            f"{counts['relationships']} relationships created. "
            f"{counts['deprecated']} deprecated."
        )
        _report_orphans(plan, deprecate_missing)

    finally:
        driver.close()


def _report_orphans(plan: IngestPlan, deprecate_missing: bool) -> None:
    """Report master terms the source no longer defines, when not deprecating."""
    if deprecate_missing or not plan.to_deprecate:
        return
    click.echo(
        f"\n{len(plan.to_deprecate)} active term(s) in master are absent from "
        f"the source:"
    )
    for term in sorted(plan.to_deprecate, key=lambda t: t.get("term_id", "")):
        click.echo(f"  {term.get('term_id')}  {term.get('name')}")
    click.echo(
        "Re-run with --deprecate-missing to retire them (irreversible), or "
        "restore them in the source vocabulary."
    )


def _report_plan(
    plan: IngestPlan,
    master_epoch: int,
    deprecate_missing: bool,
    will_change: bool,
) -> None:
    """Print exactly what a live run of this plan would do."""
    click.echo("\n[DRY RUN] Change plan against the master database:")
    click.echo(f"  Create:    {len(plan.to_create)} terms")
    for _, term, _ in sorted(plan.to_create, key=lambda x: x[1].term_id):
        click.echo(f"    + {term.term_id}  {term.name}")
    click.echo(f"  Update:    {len(plan.to_update)} terms")
    for _, term, _, _ in sorted(plan.to_update, key=lambda x: x[1].term_id):
        click.echo(f"    ~ {term.term_id}  {term.name}")
    click.echo(f"  Unchanged: {plan.unchanged} terms")
    click.echo(f"  New relationships: {len(plan.rels_to_create)}")

    verb = "Deprecate" if deprecate_missing else "Would deprecate (needs --deprecate-missing)"
    click.echo(f"  {verb}: {len(plan.to_deprecate)} terms")
    for term in sorted(plan.to_deprecate, key=lambda t: t.get("term_id", "")):
        click.echo(f"    - {term.get('term_id')}  {term.get('name')}")

    if will_change:
        click.echo(
            f"\nMaster epoch would move {master_epoch} -> {master_epoch + 1} "
            f"and one ontology_ingested event would be written."
        )
    else:
        click.echo(
            f"\nNo changes. Master epoch would stay {master_epoch} and no event "
            f"would be written."
        )
    click.echo("No changes written.")


def _apply_ingest_plan(
    driver,
    plan: IngestPlan,
    new_epoch: int,
    deprecate_missing: bool,
) -> Dict[str, Any]:
    """Execute a non-empty ingest plan against the master database.

    Args:
        driver: Connected Neo4j driver.
        plan: The plan built by :func:`build_ingest_plan`.
        new_epoch: Epoch stamped on created and updated terms.
        deprecate_missing: Whether to run the deprecation pass.

    Returns:
        Dict with keys ``new``, ``updated``, ``relationships``, ``deprecated``
        and ``deprecated_term_ids``.
    """
    from seldon.core.graph import create_artifact, update_artifact

    new_count = 0
    updated_count = 0
    rel_created = 0

    with driver.session(database=ONTOLOGY_MASTER_DB) as session:
        for vocab_path, term, content_hash in plan.to_create:
            props = _term_to_props(term, new_epoch, content_hash)
            props["artifact_id"] = str(uuid.uuid4())
            props["source_vocabulary"] = str(vocab_path)
            props["created_at"] = _now_iso()
            create_artifact(session, "OntologyTerm", props)
            new_count += 1

        for vocab_path, term, content_hash, artifact_id in plan.to_update:
            props = _term_to_props(term, new_epoch, content_hash)
            # `state` is lifecycle, not source content. Writing it here would be
            # an unvalidated state transition; the source file has no authority
            # over an existing term's state.
            props.pop("state", None)
            props["source_vocabulary"] = str(vocab_path)
            props["updated_at"] = _now_iso()
            update_artifact(session, artifact_id, props)
            updated_count += 1

        for from_id, rel_type, to_id in plan.rels_to_create:
            cypher = (
                f"MATCH (a:Artifact:OntologyTerm {{term_id: $from_id}}), "
                f"(b:Artifact:OntologyTerm {{term_id: $to_id}}) "
                f"MERGE (a)-[r:{rel_type}]->(b) "
                f"ON CREATE SET r.created_at = $now "
                f"RETURN r"
            )
            result = session.run(
                cypher, from_id=from_id, to_id=to_id, now=_now_iso()
            ).single()
            if result:
                rel_created += 1

    deprecated_ids: List[str] = []
    if deprecate_missing and plan.to_deprecate:
        deprecated_ids = _deprecate_terms(driver, plan.to_deprecate)

    return {
        "new": new_count,
        "updated": updated_count,
        "relationships": rel_created,
        "deprecated": len(deprecated_ids),
        "deprecated_term_ids": deprecated_ids,
    }


def _deprecate_terms(driver, terms: List[Dict[str, Any]]) -> List[str]:
    """Transition master terms to ``deprecated`` through the event path.

    Each term gets a validated ``artifact_state_changed`` event before the node
    is touched, so the retirement is auditable and replayable rather than a
    silent property mutation.

    Args:
        driver: Connected Neo4j driver.
        terms: Master term property dicts, all in state ``active``.

    Returns:
        The term_ids deprecated, sorted.

    Raises:
        seldon.core.state.InvalidStateTransition: If the domain state machine
            does not permit active -> deprecated. Raised before any write.
    """
    from seldon.core.artifacts import transition_state
    from seldon.domain.loader import load_domain_config

    domain_yaml = Path(__file__).parent.parent / "domain" / f"{ONTOLOGY_DOMAIN}.yaml"
    domain_config = load_domain_config(domain_yaml)
    event_dir = _seldon_repo_dir()
    session_id = str(uuid.uuid4())

    deprecated: List[str] = []
    for term in sorted(terms, key=lambda t: t.get("term_id", "")):
        transition_state(
            project_dir=event_dir,
            driver=driver,
            database=ONTOLOGY_MASTER_DB,
            domain_config=domain_config,
            artifact_id=term["artifact_id"],
            artifact_type="OntologyTerm",
            current_state=term["state"],
            new_state="deprecated",
            actor="seldon",
            authority="accepted",
            session_id=session_id,
        )
        deprecated.append(term["term_id"])
    return deprecated


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

@ontology_group.command("sync")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing.")
def sync_command(dry_run: bool):
    """Pull ontology terms from the master database into the current project.

    Must be run from a project directory with seldon.yaml containing a
    shared_ontology section with inheritance: read-only.
    """
    from dotenv import load_dotenv
    from seldon.config import load_project_config

    project_dir = Path.cwd()
    load_dotenv(project_dir / ".env", override=False)

    config = load_project_config(project_dir)
    database = config["neo4j"]["database"]
    driver = _get_neo4j_driver()

    try:
        if dry_run:
            # Dry run: show what would change without writing
            click.echo("[DRY RUN] Checking master vs. project state...")

            # Read master epoch
            with driver.session(database=ONTOLOGY_MASTER_DB) as session:
                result = session.run(
                    "MATCH (m:_OntologyMeta {key: 'master'}) "
                    "RETURN m.epoch AS epoch"
                ).single()
                if result is None:
                    raise click.ClickException(
                        "No master ontology found. Run `seldon ontology ingest` first."
                    )
                master_epoch = result["epoch"]

            with driver.session(database=database) as session:
                result = session.run(
                    "MATCH (m:_OntologyReplicaMeta {key: 'replica'}) "
                    "RETURN m.last_epoch AS last_epoch"
                ).single()
                project_epoch = result["last_epoch"] if result else 0

            if project_epoch == master_epoch and master_epoch > 0:
                click.echo(f"Already up to date at epoch {master_epoch}.")
                return

            # Count master terms
            with driver.session(database=ONTOLOGY_MASTER_DB) as session:
                count_result = session.run(
                    "MATCH (a:Artifact:OntologyTerm) RETURN count(a) AS cnt"
                ).single()
                master_count = count_result["cnt"]
                master_deprecated = session.run(
                    "MATCH (a:Artifact:OntologyTerm) WHERE a.state = 'deprecated' "
                    "RETURN count(a) AS cnt"
                ).single()["cnt"]

            with driver.session(database=database) as session:
                count_result = session.run(
                    "MATCH (a:Artifact:OntologyTerm) RETURN count(a) AS cnt"
                ).single()
                project_count = count_result["cnt"]

            click.echo(
                f"  Master epoch: {master_epoch}, project epoch: {project_epoch}"
            )
            click.echo(
                f"  Master has {master_count} terms "
                f"({master_deprecated} deprecated), project has {project_count}."
            )
            click.echo("No changes written.")
            return

        try:
            result = _do_sync(driver, database, project_dir, config)
        except RuntimeError as e:
            raise click.ClickException(str(e))

        if result.get("up_to_date"):
            click.echo(f"Already up to date at epoch {result['epoch']}.")
        else:
            click.echo(
                f"Synced to epoch {result['epoch']}: "
                f"{result['new']} new, {result['updated']} updated, "
                f"{result['deprecated']} deprecated. Project is current."
            )
            if result.get("skipped_deprecated"):
                click.echo(
                    f"  {result['skipped_deprecated']} term(s) already "
                    f"deprecated on master were not added to this project."
                )

    finally:
        driver.close()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@ontology_group.command("list")
@click.option("--category", default=None, help="Filter by category.")
@click.option("--verbose", is_flag=True, help="Include definition text (first 100 chars).")
@click.option("--master", is_flag=True, help="Query master DB instead of project DB.")
def list_command(category: Optional[str], verbose: bool, master: bool):
    """Display ontology terms from the project or master database."""
    from dotenv import load_dotenv

    project_dir = Path.cwd()
    load_dotenv(project_dir / ".env", override=False)

    if master:
        database = ONTOLOGY_MASTER_DB
    else:
        from seldon.config import load_project_config
        config = load_project_config(project_dir)
        database = config["neo4j"]["database"]

    driver = _get_neo4j_driver()

    try:
        with driver.session(database=database) as session:
            if category:
                records = session.run(
                    "MATCH (a:Artifact:OntologyTerm) "
                    "WHERE a.category = $category "
                    "RETURN a ORDER BY a.term_id",
                    category=category,
                ).data()
            else:
                records = session.run(
                    "MATCH (a:Artifact:OntologyTerm) RETURN a ORDER BY a.category, a.term_id"
                ).data()

        if not records:
            source = "master" if master else "project"
            if category:
                click.echo(f"No ontology terms found in {source} DB with category '{category}'.")
            else:
                click.echo(f"No ontology terms found in {source} DB.")
            return

        terms = [dict(r["a"]) for r in records]

        # Group by category for display
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for t in terms:
            cat = t.get("category", "unknown")
            by_category.setdefault(cat, []).append(t)

        source_label = f"Master ({ONTOLOGY_MASTER_DB})" if master else "Project"
        click.echo(f"\n{source_label} ontology terms ({len(terms)} total):\n")

        for cat in sorted(by_category.keys()):
            click.echo(f"  [{cat}] ({len(by_category[cat])} terms)")
            for t in by_category[cat]:
                state = t.get("state", "?")
                epoch = t.get("epoch", "?")
                line = f"    {t['term_id']}  {t['name']}  [{state}]  epoch={epoch}"
                click.echo(line)
                if verbose:
                    defn = t.get("definition", "")
                    if len(defn) > 100:
                        defn = defn[:100] + "..."
                    click.echo(f"      {defn}")
            click.echo()

    finally:
        driver.close()
