#!/usr/bin/env python3
"""
Migrate relationship types stored in non-canonical case to UPPERCASE.

Why
---
UPPERCASE is the canonical spelling of a relationship type *by construction*:
``seldon.core.artifacts.create_link`` and ``remove_link`` both call
``rel_type.upper()`` before the type reaches Neo4j, and event replay in
``seldon.core.sync._apply_event`` does the same. The domain config declares
type names in lowercase — that is what the JSONL event records and what
validation matches — but it is never what the graph stores.

A relationship stored in any other case therefore cannot have come from a
sanctioned write; it is graph-only drift written by raw Cypher. It is also
*invisible*: every type-filtered query in this codebase names the uppercase
form, so the non-canonical twin is silently skipped and the query returns a
confidently incomplete answer.

What it does
------------
For every relationship whose type is not its own uppercase form:

1. Emit a ``link_created`` event for the canonical spelling and create the
   canonical relationship (skipped when one already exists between the same
   endpoints — the migration then only removes the duplicate spelling).
2. Emit a ``link_case_migrated`` event and delete the non-canonical
   relationship.

Both steps are event-then-write, in that order, matching
``seldon.core.artifacts``. ``link_case_migrated`` is audit-only in replay: see
the comment on ``_AUDIT_ONLY_EVENT_TYPES`` in ``seldon/core/sync.py``.

Why not ``seldon.core.artifacts.create_link``
---------------------------------------------
Because it applies domain-config relationship validation. A case migration is a
*rename*: it must preserve the edge set exactly, including edges that violate
the domain config (this project's graph contains one — an ``informs`` edge
between two ArchitecturalDecisions, where the config permits only
DesignNote → ArchitecturalDecision). Validating a rename would either drop that
edge or abort the migration, and "the edge violates the domain config" is a
different defect needing a different decision. This script composes
``make_event`` / ``append_event`` with the ``seldon.core.graph`` primitives
directly — the same two layers ``artifacts.py`` composes, minus the semantic
validation a rename must not apply.

Safety
------
* Dry run by default. ``--apply`` is required to write anything.
* Prints the full plan, relationship by relationship, before acting.
* Idempotent and re-runnable: a second run finds nothing to do, and a run
  interrupted midway resumes correctly (the canonical-edge check is per
  relationship, not per type).
* Acts on ONE database — the one named in the resolved project's
  ``seldon.yaml``. It refuses the shared ontology master outright.

Usage:
    python scripts/migrations/2026-09-04_migrate_rel_type_case.py [--dry-run]
    python scripts/migrations/2026-09-04_migrate_rel_type_case.py --apply
    python scripts/migrations/2026-09-04_migrate_rel_type_case.py --apply \\
        --project-dir /path/to/project
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Repo root on sys.path so `seldon` imports resolve when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from seldon.config import (  # noqa: E402
    ONTOLOGY_MASTER_DB,
    get_current_session,
    get_neo4j_driver,
    load_project_config,
)
from seldon.core import graph  # noqa: E402
from seldon.core.events import append_event, make_event  # noqa: E402
from seldon.domain.loader import load_domain_config  # noqa: E402

ACTOR = "rel-type-case-migration"
AUTHORITY = "accepted"


def _domain_rel_name(project_dir: Path, config: dict, canonical: str) -> str:
    """Return the domain config's declared name for a canonical relationship type.

    Existing ``link_created`` events record the domain-declared (lowercase) name
    and rely on replay to uppercase it, so a migration event should match that
    convention where a declaration exists. Where none does — the type is in the
    graph but not in the config — the canonical uppercase form is recorded
    instead; replay uppercases either way, so both project identically.

    Args:
        project_dir: Project root.
        config: Loaded project config.
        canonical: Uppercase relationship type name.

    Returns:
        The declared name if the domain config has one, else ``canonical``.
    """
    domain_name = config["project"].get("domain", "research")
    domain_yaml = (
        Path(__file__).resolve().parents[2]
        / "seldon"
        / "domain"
        / f"{domain_name}.yaml"
    )
    if not domain_yaml.is_file():
        return canonical
    domain_config = load_domain_config(domain_yaml)
    for declared in domain_config.relationship_types or {}:
        if declared.upper() == canonical:
            return declared
    return canonical


def build_plan(session) -> list[dict]:
    """Enumerate the work, without changing anything.

    Args:
        session: Open Neo4j session on the target database.

    Returns:
        One dict per non-canonical relationship, with keys ``from_id``,
        ``to_id``, ``from_rel_type``, ``to_rel_type``, ``properties`` and
        ``create_canonical`` (False when the canonical edge already exists, in
        which case the migration only drops the duplicate spelling).
    """
    plan: list[dict] = []
    for offender in graph.find_noncanonical_rel_types(session):
        stored = offender["rel_type"]
        canonical = offender["canonical"]
        for rel in graph.get_relationships_of_type(session, stored):
            from_id, to_id = rel["from_id"], rel["to_id"]
            already = False
            if from_id and to_id:
                already = graph.relationship_exists(
                    session, from_id, to_id, canonical
                )
            plan.append(
                {
                    "from_id": from_id,
                    "to_id": to_id,
                    "from_rel_type": stored,
                    "to_rel_type": canonical,
                    "properties": rel["properties"],
                    "create_canonical": not already,
                }
            )
    return plan


def print_plan(database: str, plan: list[dict]) -> None:
    """Print exactly what the migration will do, one line per relationship."""
    print(f"database: {database}")
    if not plan:
        print("nothing to migrate — all relationship types are canonical.")
        return
    print(f"{len(plan)} non-canonical relationship(s) to migrate:\n")
    for item in plan:
        action = "rename" if item["create_canonical"] else "drop duplicate"
        print(
            f"  [{action}] {item['from_id']} -[{item['from_rel_type']}]-> "
            f"{item['to_id']}"
        )
        print(
            f"      → {item['to_rel_type']}"
            + ("" if item["create_canonical"] else "  (canonical edge already present)")
        )
        if item["properties"]:
            print(f"      properties carried over: {sorted(item['properties'])}")
    print()


def apply_plan(
    project_dir: Path,
    driver,
    database: str,
    plan: list[dict],
    event_rel_names: dict[str, str],
    session_id: str | None,
) -> tuple[int, int]:
    """Execute the plan, event-then-write, one relationship at a time.

    Args:
        project_dir: Project root — where the JSONL event log lives.
        driver: Neo4j driver.
        database: Target database name.
        plan: Output of :func:`build_plan`.
        event_rel_names: Canonical type → name to record in the event payload.
        session_id: Current Seldon session id, or None.

    Returns:
        ``(created, removed)`` counts.

    Raises:
        ValueError: If a planned relationship has a null endpoint id, which
            would make it unrecordable as an event.
    """
    created = removed = 0
    for item in plan:
        from_id, to_id = item["from_id"], item["to_id"]
        if not from_id or not to_id:
            raise ValueError(
                f"Refusing to migrate a relationship with a null endpoint: "
                f"{item['from_id']} -[{item['from_rel_type']}]-> {item['to_id']}. "
                "Its migration cannot be recorded as an event. Resolve by hand."
            )
        canonical = item["to_rel_type"]
        props = item["properties"] or {}

        if item["create_canonical"]:
            append_event(
                project_dir,
                make_event(
                    event_type="link_created",
                    actor=ACTOR,
                    authority=AUTHORITY,
                    payload={
                        "from_id": from_id,
                        "to_id": to_id,
                        "rel_type": event_rel_names.get(canonical, canonical),
                        "properties": props,
                    },
                    session_id=session_id,
                ),
            )
            with driver.session(database=database) as session:
                graph.create_link(session, from_id, to_id, canonical, props)
            created += 1

        append_event(
            project_dir,
            make_event(
                event_type="link_case_migrated",
                actor=ACTOR,
                authority=AUTHORITY,
                payload={
                    "from_id": from_id,
                    "to_id": to_id,
                    "from_rel_type": item["from_rel_type"],
                    "to_rel_type": canonical,
                    "properties": props,
                },
                session_id=session_id,
            ),
        )
        with driver.session(database=database) as session:
            graph.remove_link(session, from_id, to_id, item["from_rel_type"])
        removed += 1

    return created, removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually migrate. Without it the script only prints the plan.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit no-op form of the default behaviour.",
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Project root containing seldon.yaml (default: cwd).",
    )
    args = parser.parse_args(argv)

    if args.apply and args.dry_run:
        print("ERROR: --apply and --dry-run are mutually exclusive.", file=sys.stderr)
        return 2

    project_dir = Path(args.project_dir).resolve()
    config = load_project_config(project_dir)
    database = config["neo4j"]["database"]

    # This migration writes. It may only ever write to the project resolved from
    # the working directory, never to the shared ontology master, and never to
    # another project's graph.
    if database == ONTOLOGY_MASTER_DB:
        print(
            f"ERROR: refusing to migrate the shared ontology master "
            f"({ONTOLOGY_MASTER_DB}). Writes to master go through "
            "`seldon ontology ingest`.",
            file=sys.stderr,
        )
        return 2

    driver = get_neo4j_driver(config)
    try:
        with driver.session(database=database) as session:
            plan = build_plan(session)

        print_plan(database, plan)

        if not plan:
            return 0

        if not args.apply:
            print("dry run — nothing written. Re-run with --apply to migrate.")
            return 0

        canonicals = {item["to_rel_type"] for item in plan}
        event_rel_names = {
            c: _domain_rel_name(project_dir, config, c) for c in canonicals
        }

        created, removed = apply_plan(
            project_dir,
            driver,
            database,
            plan,
            event_rel_names,
            get_current_session(project_dir),
        )
        print(
            f"applied: {created} canonical relationship(s) created, "
            f"{removed} non-canonical relationship(s) removed."
        )

        with driver.session(database=database) as session:
            leftover = graph.find_noncanonical_rel_types(session)
        if leftover:
            print(f"WARNING: still non-canonical after migration: {leftover}",
                  file=sys.stderr)
            return 1
        print("verified: no non-canonical relationship types remain.")
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
