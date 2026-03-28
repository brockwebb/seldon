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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from seldon.config import ONTOLOGY_MASTER_DB
from seldon.core.events import append_event, make_event
from seldon.core.graph import create_indexes


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


def _resolve_vocabulary_path() -> Path:
    """Find the vocabulary file using config or env var.

    Resolution order:
    1. Project seldon.yaml shared_ontology.source + vocabularies[0]
    2. SELDON_ONTOLOGY_PATH env var
    3. Error with instructions
    """
    from seldon.config import get_shared_ontology_source, load_project_config

    # Try project config first
    try:
        config = load_project_config()
        vocab_path = get_shared_ontology_source(config)
        if vocab_path and vocab_path.exists():
            return vocab_path
    except FileNotFoundError:
        pass

    # Try env var
    env_path = os.getenv("SELDON_ONTOLOGY_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        raise click.ClickException(
            f"SELDON_ONTOLOGY_PATH points to non-existent file: {env_path}"
        )

    raise click.ClickException(
        "Cannot locate vocabulary file. Either:\n"
        "  1. Run from a project directory with seldon.yaml containing "
        "shared_ontology.source + vocabularies\n"
        "  2. Set SELDON_ONTOLOGY_PATH=/path/to/VALIDITY_VOCABULARY.md"
    )


def _seldon_repo_dir() -> Path:
    """Return the Seldon repository root (for event store writes during ingest)."""
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
# Core sync logic (shared between `sync` command and `init` hook)
# ---------------------------------------------------------------------------

def _do_sync(
    driver,
    database: str,
    project_dir: Path,
    config: dict,
) -> Dict[str, Any]:
    """Pull OntologyTerms from master into a project database.

    Args:
        driver: Neo4j driver (already authenticated).
        database: Project database name.
        project_dir: Path to project root (for event store).
        config: Loaded seldon.yaml dict.

    Returns:
        Dict with keys: epoch, terms, new, updated, deprecated.

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
    rel_count = 0

    with driver.session(database=database) as session:
        # Sync terms from master
        for term_id, master_term in master_terms.items():
            props = dict(master_term)
            props["inheritance"] = inheritance

            if term_id not in project_terms:
                # New term -- create with same artifact_id as master
                props.setdefault("created_at", _now_iso())
                create_artifact(session, "OntologyTerm", props)
                new_count += 1
            else:
                # Existing term -- check if content changed
                if props.get("content_hash") != project_terms[term_id].get("content_hash"):
                    props["updated_at"] = _now_iso()
                    update_artifact(session, props["artifact_id"], props)
                    updated_count += 1

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

    # Write sync event to project event store
    event = make_event(
        event_type="ontology_synced",
        actor="seldon",
        authority="accepted",
        payload={
            "master_epoch": master_epoch,
            "new_terms": new_count,
            "updated_terms": updated_count,
            "deprecated_terms": deprecated_count,
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
@click.option("--dry-run", is_flag=True, help="Parse and report without writing.")
def ingest_command(dry_run: bool):
    """Parse vocabulary file and write terms to the master ontology database.

    Writes to the shared seldon-ontology database only. Never touches
    project databases. Use `seldon ontology sync` to pull into a project.
    """
    from dotenv import load_dotenv
    load_dotenv(override=False)

    from seldon.ontology.parser import parse_vocabulary

    vocab_path = _resolve_vocabulary_path()
    click.echo(f"Parsing vocabulary: {vocab_path}")

    parsed = parse_vocabulary(vocab_path)
    click.echo(
        f"  Parsed {len(parsed.terms)} terms, "
        f"{len(parsed.relationships)} relationships "
        f"(file hash: {parsed.content_hash[:12]}...)"
    )

    if dry_run:
        click.echo("\n[DRY RUN] Would write to master database:")
        by_cat: Dict[str, int] = {}
        for t in parsed.terms:
            by_cat[t.category] = by_cat.get(t.category, 0) + 1
        for cat, count in sorted(by_cat.items()):
            click.echo(f"  {cat}: {count} terms")
        click.echo(f"  Relationships: {len(parsed.relationships)}")
        click.echo("No changes written.")
        return

    from seldon.core.graph import create_artifact, update_artifact

    driver = _get_neo4j_driver()
    try:
        _ensure_master_db(driver)
        _ensure_master_indexes(driver)

        current_epoch = _get_or_create_master_meta(driver)
        new_epoch = _increment_epoch(driver)

        new_count = 0
        updated_count = 0
        unchanged_count = 0

        with driver.session(database=ONTOLOGY_MASTER_DB) as session:
            # Build lookup of existing terms
            existing_records = session.run(
                "MATCH (a:Artifact:OntologyTerm) RETURN a"
            ).data()
            existing_by_term_id = {
                dict(r["a"])["term_id"]: dict(r["a"]) for r in existing_records
            }

            for term in parsed.terms:
                content_hash = _term_content_hash(term)
                existing = existing_by_term_id.get(term.term_id)

                if existing is None:
                    # New term -- create
                    props = _term_to_props(term, new_epoch, content_hash)
                    props["artifact_id"] = str(uuid.uuid4())
                    props["source_vocabulary"] = str(vocab_path)
                    props["created_at"] = _now_iso()
                    create_artifact(session, "OntologyTerm", props)
                    new_count += 1

                elif existing.get("content_hash") != content_hash:
                    # Changed -- update
                    update_props = _term_to_props(term, new_epoch, content_hash)
                    update_props["source_vocabulary"] = str(vocab_path)
                    update_props["updated_at"] = _now_iso()
                    update_artifact(session, existing["artifact_id"], update_props)
                    updated_count += 1

                else:
                    # Unchanged
                    unchanged_count += 1

            # Create relationships using MERGE
            rel_created = 0
            for rel in parsed.relationships:
                cypher = (
                    f"MATCH (a:Artifact:OntologyTerm {{term_id: $from_id}}), "
                    f"(b:Artifact:OntologyTerm {{term_id: $to_id}}) "
                    f"MERGE (a)-[r:{rel.rel_type.upper()}]->(b) "
                    f"ON CREATE SET r.created_at = $now "
                    f"RETURN r"
                )
                result = session.run(
                    cypher,
                    from_id=rel.from_term_id,
                    to_id=rel.to_term_id,
                    now=_now_iso(),
                ).single()
                if result:
                    rel_created += 1

        # Write event to Seldon repo's event store
        repo_dir = _seldon_repo_dir()
        event = make_event(
            event_type="ontology_ingested",
            actor="seldon",
            authority="accepted",
            payload={
                "master_epoch": new_epoch,
                "source_file": str(vocab_path),
                "source_hash": parsed.content_hash,
                "new_terms": new_count,
                "updated_terms": updated_count,
                "unchanged_terms": unchanged_count,
                "relationships_created": rel_created,
                "total_terms": len(parsed.terms),
            },
        )
        append_event(repo_dir, event)

        click.echo(
            f"Master epoch {new_epoch}: Ingested {new_count} new, "
            f"updated {updated_count}, unchanged {unchanged_count} terms. "
            f"{rel_created} relationships created."
        )

    finally:
        driver.close()


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

            with driver.session(database=database) as session:
                count_result = session.run(
                    "MATCH (a:Artifact:OntologyTerm) RETURN count(a) AS cnt"
                ).single()
                project_count = count_result["cnt"]

            click.echo(
                f"  Master epoch: {master_epoch}, project epoch: {project_epoch}"
            )
            click.echo(
                f"  Master has {master_count} terms, project has {project_count}."
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
