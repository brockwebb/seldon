from __future__ import annotations

import time
from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.core.sync import full_replay


@click.command("rebuild")
def rebuild_command():
    """
    Rebuild Neo4j graph from JSONL event log.

    WARNING: This issues MATCH (n) DETACH DELETE n on the PROJECT database.
    All nodes and relationships in the project database are destroyed and
    recreated from the event log. The JSONL log is not modified.
    """
    config = load_project_config()
    project_dir = Path.cwd()
    database = config["neo4j"]["database"]
    driver = get_neo4j_driver(config)

    click.echo(f"Rebuilding '{database}' from event log...")
    click.echo(f"WARNING: All data in '{database}' will be deleted and recreated.")

    start = time.time()
    count = full_replay(project_dir, driver, database)
    elapsed = time.time() - start

    driver.close()
    click.echo(f"Rebuild complete: {count} events replayed in {elapsed:.2f}s")
