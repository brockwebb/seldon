#!/usr/bin/env python3
"""
Supersede ResearchTasks whose ``source_file`` no longer exists on disk.

Why
---
A ResearchTask's ``source_file`` is its specification — the only place its
scope, success criteria and boundaries were ever written down. In this project
37 of the 50 tasks carrying a ``source_file`` point at a file that is on
neither disk nor any branch, because ``cc_tasks/`` was gitignored until commit
c53b3c9. Those nodes record that a task existed without recording what it was.

Two of them (``7120e000``, ``676c0e39``) cannot be re-derived at all. This
script therefore NEVER writes a description. An invented description is worse
than an absent one: it launders a gap into an assertion.

What "superseded" can and cannot cover
--------------------------------------
``superseded`` is reachable only from ``proposed``, ``accepted``,
``in_progress`` and ``blocked`` — see the ResearchTask state machine in
``seldon/domain/research.yaml``, which says so explicitly: relabelling a
finished task would corrupt the honest completion record. A ``completed``,
``verified`` or ``rejected`` orphan therefore stays as it is. That is the right
outcome, not a limitation to work around: the work was done and the graph
records the outcome; only the spec file is lost, and losing the spec of a
finished task does not un-finish it.

So this script partitions the orphans and acts on the open ones only. The
terminal ones are printed as an untouched inventory.

Safety
------
* Dry run by default. ``--apply`` is required to write anything.
* Prints the full plan — eligible and ineligible, by state — before acting.
* Idempotent and re-runnable: superseded tasks no longer appear in the
  eligible set, and a task whose file has been restored drops out entirely.
* Every transition goes through ``seldon.core.artifacts.transition_task``, so
  each one is an event first and a graph write second, validated against the
  state machine.
* Acts on ONE database — the one named in the resolved project's
  ``seldon.yaml``.

Usage:
    python scripts/migrations/2026-09-04_supersede_orphan_source_file_tasks.py
    python scripts/migrations/2026-09-04_supersede_orphan_source_file_tasks.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from seldon.config import (  # noqa: E402
    get_current_session,
    get_neo4j_driver,
    load_project_config,
)
from seldon.core.artifacts import transition_task  # noqa: E402
from seldon.domain.loader import load_domain_config  # noqa: E402

ACTOR = "orphan-source-file-migration"

#: Recorded verbatim as ``terminal_reason``. Names the commit that closed the
#: hole so a reader can date the loss without guessing.
REASON = "source_file lost pre-c53b3c9"

TARGET_STATE = "superseded"


def _domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = (
        Path(__file__).resolve().parents[2]
        / "seldon"
        / "domain"
        / f"{domain_name}.yaml"
    )
    return load_domain_config(domain_yaml)


def eligible_states(domain_config) -> set[str]:
    """Return the ResearchTask states from which ``superseded`` is reachable.

    Read from the domain config rather than hardcoded, so that a change to the
    state machine moves this script with it instead of silently diverging.

    Args:
        domain_config: Loaded domain configuration.

    Returns:
        Set of state names whose successor list contains ``superseded``.
    """
    machine = domain_config.state_machines.get("ResearchTask", {})
    return {state for state, nexts in machine.items() if TARGET_STATE in nexts}


def find_orphans(driver, database: str, project_dir: Path) -> list[dict]:
    """Return every ResearchTask whose ``source_file`` is missing from disk.

    Args:
        driver: Neo4j driver.
        database: Project database name.
        project_dir: Project root; relative source_file values resolve against it.

    Returns:
        One dict per orphan with keys ``artifact_id``, ``source_file``,
        ``state`` and ``description``, ordered by source_file.
    """
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (t:Artifact:ResearchTask) WHERE t.source_file IS NOT NULL "
            "RETURN t.artifact_id AS artifact_id, t.source_file AS source_file, "
            "t.state AS state, t.description AS description "
            "ORDER BY t.source_file"
        ).data()

    orphans = []
    for rec in records:
        path = Path(rec["source_file"])
        if not path.is_absolute():
            path = project_dir / path
        if not path.is_file():
            orphans.append(rec)
    return orphans


def print_plan(
    database: str, eligible: list[dict], ineligible: list[dict]
) -> None:
    """Print exactly what will and will not be touched."""
    print(f"database: {database}")
    print(f"reason to be recorded: {REASON!r}")
    print()

    print(f"WILL SUPERSEDE ({len(eligible)}):")
    if not eligible:
        print("  (none)")
    for rec in eligible:
        print(f"  {rec['artifact_id']}  [{rec['state']}]  {rec['source_file']}")
    print()

    by_state: dict[str, list[dict]] = {}
    for rec in ineligible:
        by_state.setdefault(rec["state"] or "?", []).append(rec)
    print(
        f"WILL NOT TOUCH ({len(ineligible)}) — terminal states; `superseded` is "
        "unreachable from them by design:"
    )
    if not ineligible:
        print("  (none)")
    for state in sorted(by_state):
        print(f"  {state}: {len(by_state[state])}")
        for rec in by_state[state]:
            print(f"    {rec['artifact_id']}  {rec['source_file']}")
    print()
    print("No description is written or changed by this script, for any task.")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually transition. Without it the script only prints the plan.",
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
    domain_config = _domain_config(config)
    open_states = eligible_states(domain_config)

    driver = get_neo4j_driver(config)
    try:
        orphans = find_orphans(driver, database, project_dir)
        eligible = [r for r in orphans if r["state"] in open_states]
        ineligible = [r for r in orphans if r["state"] not in open_states]

        print(f"orphaned source_file tasks: {len(orphans)}")
        print_plan(database, eligible, ineligible)

        if not eligible:
            print("nothing to do.")
            return 0

        if not args.apply:
            print("dry run — nothing written. Re-run with --apply to transition.")
            return 0

        session_id = get_current_session(project_dir)
        done = 0
        for rec in eligible:
            transition_task(
                project_dir=project_dir,
                driver=driver,
                database=database,
                domain_config=domain_config,
                artifact_id=rec["artifact_id"],
                current_state=rec["state"],
                new_state=TARGET_STATE,
                actor=ACTOR,
                authority="accepted",
                session_id=session_id,
                terminal_reason=REASON,
            )
            print(
                f"  {rec['artifact_id']}: {rec['state']} → {TARGET_STATE}"
            )
            done += 1
        print(f"\napplied: {done} task(s) superseded.")
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
