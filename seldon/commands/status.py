from __future__ import annotations

from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.core.events import event_count
from seldon.core.graph import graph_stats, get_stale_artifacts
from seldon.core.staleness import (
    partition_stale,
    resolver_for_session,
    stale_label,
)


@click.command("status")
def status_command():
    """Show project status: artifact counts, open tasks, stale results."""
    config = load_project_config()
    project_dir = Path.cwd()
    database = config["neo4j"]["database"]
    driver = get_neo4j_driver(config)

    total_events = event_count(project_dir)

    with driver.session(database=database) as session:
        stats = graph_stats(session)
        # ONE predicate with `verify`, `briefing` and `go` (seldon.core.staleness): a
        # decided supersession or withdrawal is a record, not drift, and four renderers
        # with four filters is how one count comes to mean four things.
        stale = partition_stale(get_stale_artifacts(session), resolver_for_session(session))
        open_tasks = session.run(
            "MATCH (t:ResearchTask) WHERE t.state IN ['proposed','accepted','in_progress'] "
            "RETURN t.artifact_id AS id, t.state AS state ORDER BY t.state"
        ).data()

    driver.close()

    click.echo(f"\nSeldon Project: {config['project']['name']}")
    click.echo(f"Database: {database}")
    click.echo(f"Events in log: {total_events}")
    click.echo(f"Nodes in graph: {stats['total_nodes']}")
    click.echo(f"Relationships: {stats['total_relationships']}")

    if stats["by_type"]:
        click.echo("\nArtifacts by type:")
        for atype, cnt in sorted(stats["by_type"].items()):
            click.echo(f"  {atype:<20} {cnt}")

    if stats["by_state"]:
        click.echo("\nArtifacts by state:")
        for state, cnt in sorted(stats["by_state"].items()):
            click.echo(f"  {state:<20} {cnt}")

    if open_tasks:
        click.echo(f"\nOpen tasks ({len(open_tasks)}):")
        for t in open_tasks:
            click.echo(f"  [{t['state']}] {t['id']}")
    else:
        click.echo("\nNo open tasks.")

    if stale.undecided:
        click.echo(f"\nStale artifacts ({len(stale.undecided)}):")
        for a, reason in stale.undecided:
            click.echo(f"  {a.get('artifact_type', '?'):<20} {a['artifact_id']}  {reason}")
    else:
        click.echo("No stale artifacts.")
    if stale.decided:
        click.echo(f"Decided, not drifted: {len(stale.withdrawn)} withdrawn, "
                   f"{len(stale.superseded)} superseded")
        for a in stale.withdrawn:
            click.echo(f"  withdrawn   {stale_label(a)}: {a.get('withdrawn_reason')}")
        for a in stale.superseded:
            click.echo(f"  superseded  {stale_label(a)} -> {a.get('superseded_by')}")
