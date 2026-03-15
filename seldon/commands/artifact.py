from __future__ import annotations

from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.core.artifacts import create_artifact as do_create_artifact
from seldon.core.graph import get_artifacts_by_type, get_artifacts_by_state
from seldon.domain.loader import load_domain_config


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


@click.group("artifact")
def artifact_group():
    """Manage artifacts."""
    pass


@artifact_group.command("create")
@click.argument("artifact_type")
@click.option("--property", "-p", "properties", multiple=True,
              metavar="KEY=VALUE", help="Set a property (repeatable)")
@click.option("--actor", default="human", show_default=True)
@click.option("--authority", default="accepted", show_default=True,
              type=click.Choice(["proposed", "accepted"]))
def artifact_create(artifact_type: str, properties: tuple, actor: str, authority: str):
    """Create a new artifact of the given type."""
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)

    # Parse KEY=VALUE pairs
    props = {}
    for prop in properties:
        if "=" not in prop:
            click.echo(f"Invalid property format '{prop}' — use KEY=VALUE", err=True)
            raise SystemExit(1)
        key, _, value = prop.partition("=")
        # Attempt numeric coercion
        try:
            props[key] = float(value) if "." in value else int(value)
        except ValueError:
            props[key] = value

    try:
        artifact_id = do_create_artifact(
            project_dir=project_dir,
            driver=driver,
            database=config["neo4j"]["database"],
            domain_config=domain_config,
            artifact_type=artifact_type,
            properties=props,
            actor=actor,
            authority=authority,
        )
        click.echo(f"Created {artifact_type}: {artifact_id}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@artifact_group.command("list")
@click.option("--type", "artifact_type", default=None, help="Filter by artifact type")
@click.option("--state", default=None, help="Filter by state")
def artifact_list(artifact_type: str, state: str):
    """List artifacts, optionally filtered by type and/or state."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        if artifact_type:
            artifacts = get_artifacts_by_type(session, artifact_type)
        elif state:
            artifacts = get_artifacts_by_state(session, state)
        else:
            records = session.run("MATCH (a:Artifact) RETURN a ORDER BY a.artifact_type").data()
            artifacts = [dict(r["a"]) for r in records]

    driver.close()

    if not artifacts:
        click.echo("No artifacts found.")
        return

    click.echo(f"{'TYPE':<20} {'STATE':<15} {'ID'}")
    click.echo("-" * 70)
    for a in artifacts:
        click.echo(
            f"{a.get('artifact_type', '?'):<20} "
            f"{a.get('state', '?'):<15} "
            f"{a.get('artifact_id', '?')}"
        )
