from __future__ import annotations

from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.core.artifacts import create_artifact as do_create_artifact
from seldon.core.artifacts import update_artifact as do_update_artifact
from seldon.core.graph import get_artifacts_by_type, get_artifacts_by_state
from seldon.domain.loader import load_domain_config


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


def _parse_properties(properties: tuple) -> dict:
    """Parse KEY=VALUE tuples into a dict, with numeric coercion."""
    props = {}
    for prop in properties:
        if "=" not in prop:
            click.echo(f"Invalid property format '{prop}' — use KEY=VALUE", err=True)
            raise SystemExit(1)
        key, _, value = prop.partition("=")
        try:
            props[key] = float(value) if "." in value else int(value)
        except ValueError:
            props[key] = value
    return props


def _resolve_artifact_id(session, artifact_id: str) -> str:
    """Resolve a full or prefix artifact_id to a single match. Exits on 0 or 2+ matches."""
    records = session.run(
        "MATCH (a:Artifact) WHERE a.artifact_id STARTS WITH $prefix RETURN a.artifact_id AS id",
        prefix=artifact_id,
    ).data()
    if not records:
        click.echo(f"Error: no artifact found matching '{artifact_id}'", err=True)
        raise SystemExit(1)
    if len(records) > 1:
        click.echo(
            f"Error: '{artifact_id}' matches {len(records)} artifacts — use a longer prefix:",
            err=True,
        )
        for r in records:
            click.echo(f"  {r['id']}", err=True)
        raise SystemExit(1)
    return records[0]["id"]


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

    props = _parse_properties(properties)

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


@artifact_group.command("update")
@click.argument("artifact_id")
@click.option("--property", "-p", "properties", multiple=True,
              metavar="KEY=VALUE", help="Set a property (repeatable)")
@click.option("--actor", default="human", show_default=True)
@click.option("--authority", default="accepted", show_default=True,
              type=click.Choice(["proposed", "accepted"]))
def artifact_update(artifact_id: str, properties: tuple, actor: str, authority: str):
    """Update properties on an existing artifact (full UUID or 8+ char prefix)."""
    if not properties:
        click.echo("Error: no properties specified — use -p KEY=VALUE", err=True)
        raise SystemExit(1)

    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    try:
        with driver.session(database=database) as session:
            resolved_id = _resolve_artifact_id(session, artifact_id)

        props = _parse_properties(properties)
        do_update_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            artifact_id=resolved_id,
            properties=props,
            actor=actor,
            authority=authority,
        )
        keys = ", ".join(props.keys())
        click.echo(f"Updated {resolved_id}: set {keys}")
    finally:
        driver.close()


@artifact_group.command("show")
@click.argument("artifact_id")
def artifact_show(artifact_id: str):
    """Show all properties and relationships for an artifact."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    try:
        with driver.session(database=database) as session:
            resolved_id = _resolve_artifact_id(session, artifact_id)

            records = session.run(
                "MATCH (a:Artifact {artifact_id: $id}) RETURN a", id=resolved_id
            ).data()
            if not records:
                click.echo(f"Error: artifact '{resolved_id}' not found", err=True)
                raise SystemExit(1)
            props = dict(records[0]["a"])

            out_rels = session.run(
                "MATCH (a {artifact_id: $id})-[r]->(b) "
                "RETURN type(r) AS rel, b.artifact_id AS target_id, "
                "b.artifact_type AS target_type, b.name AS target_name "
                "ORDER BY type(r), b.artifact_id",
                id=resolved_id,
            ).data()

            in_rels = session.run(
                "MATCH (b)-[r]->(a {artifact_id: $id}) "
                "RETURN type(r) AS rel, b.artifact_id AS source_id, "
                "b.artifact_type AS source_type, b.name AS source_name "
                "ORDER BY type(r), b.artifact_id",
                id=resolved_id,
            ).data()
    finally:
        driver.close()

    # Print properties sorted alphabetically
    click.echo(f"artifact_id: {resolved_id}")
    for key in sorted(props.keys()):
        if key == "artifact_id":
            continue
        click.echo(f"{key}: {props[key]}")

    # Print relationships
    if out_rels or in_rels:
        click.echo("")
        click.echo("Relationships:")
        for r in out_rels:
            target = r.get("target_name") or r.get("target_id", "?")
            click.echo(f"  -[{r['rel']}]-> {target} ({r.get('target_type', '?')})")
        for r in in_rels:
            source = r.get("source_name") or r.get("source_id", "?")
            click.echo(f"  <-[{r['rel']}]- {source} ({r.get('source_type', '?')})")
