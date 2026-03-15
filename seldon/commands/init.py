from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from seldon.config import slugify
from seldon.core.graph import create_indexes


@click.command("init")
@click.argument("project_name")
def init_command(project_name: str):
    """Initialize a new Seldon project in the current directory."""
    from neo4j import GraphDatabase

    project_dir = Path.cwd()
    slug = slugify(project_name)
    database = f"seldon-{slug}"
    events_path = "seldon_events.jsonl"

    # 1. Create seldon.yaml
    config = {
        "project": {
            "name": project_name,
            "slug": slug,
            "domain": "research",
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "neo4j": {
            "uri": "bolt://localhost:7687",
            "database": database,
        },
        "event_store": {
            "path": events_path,
        },
    }
    config_path = project_dir / "seldon.yaml"
    if config_path.exists():
        click.echo(f"seldon.yaml already exists. Aborting.")
        raise SystemExit(1)

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    # 2. Create empty event log
    events_file = project_dir / events_path
    if not events_file.exists():
        events_file.touch()

    # 3. Create .seldon/ directory for session state
    seldon_dir = project_dir / ".seldon"
    seldon_dir.mkdir(exist_ok=True)

    # 4. Connect to Neo4j and set up project database
    uri = "bolt://localhost:7687"
    username = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER") or "neo4j"
    password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS") or "password"

    try:
        extra_kwargs = {}
        try:
            from neo4j import NotificationMinimumSeverity
            extra_kwargs["notifications_min_severity"] = NotificationMinimumSeverity.OFF
            extra_kwargs["warn_notification_severity"] = NotificationMinimumSeverity.OFF
        except ImportError:
            pass
        driver = GraphDatabase.driver(uri, auth=(username, password), **extra_kwargs)

        # Create database
        with driver.session(database="system") as session:
            session.run(f"CREATE DATABASE `{database}` IF NOT EXISTS WAIT")

        # Create indexes and meta node on project database
        with driver.session(database=database) as session:
            create_indexes(session)
            session.run(
                "MERGE (m:_SeldonMeta {key: 'sync_point'}) "
                "ON CREATE SET m.last_event_id = null, m.created_at = $now",
                now=datetime.now(timezone.utc).isoformat(),
            )

        driver.close()
        neo4j_status = f"Neo4j database '{database}' created with indexes."
    except Exception as e:
        neo4j_status = f"Warning: Neo4j setup failed: {e}"

    click.echo(f"Initialized Seldon project: {project_name}")
    click.echo(f"  Slug:       {slug}")
    click.echo(f"  Database:   {database}")
    click.echo(f"  Events:     {events_path}")
    click.echo(f"  Config:     seldon.yaml")
    click.echo(f"  {neo4j_status}")
