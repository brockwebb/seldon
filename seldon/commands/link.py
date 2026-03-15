from __future__ import annotations

from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.core.artifacts import create_link as do_create_link
from seldon.core.graph import get_artifact
from seldon.domain.loader import load_domain_config


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


@click.group("link")
def link_group():
    """Manage artifact relationships."""
    pass


@link_group.command("create")
@click.argument("from_id")
@click.argument("rel_type")
@click.argument("to_id")
@click.option("--actor", default="human", show_default=True)
@click.option("--authority", default="accepted", show_default=True,
              type=click.Choice(["proposed", "accepted"]))
def link_create(from_id: str, rel_type: str, to_id: str, actor: str, authority: str):
    """
    Create a directed relationship between two artifacts.

    Example: seldon link create <uuid1> generated_by <uuid2>
    """
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]

    # Fetch artifact types for validation
    with driver.session(database=database) as session:
        from_node = get_artifact(session, from_id)
        to_node = get_artifact(session, to_id)

    if from_node is None:
        click.echo(f"Error: artifact '{from_id}' not found", err=True)
        driver.close()
        raise SystemExit(1)
    if to_node is None:
        click.echo(f"Error: artifact '{to_id}' not found", err=True)
        driver.close()
        raise SystemExit(1)

    from_type = from_node["artifact_type"]
    to_type = to_node["artifact_type"]

    try:
        do_create_link(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            from_id=from_id,
            to_id=to_id,
            from_type=from_type,
            to_type=to_type,
            rel_type=rel_type.lower(),
            actor=actor,
            authority=authority,
        )
        click.echo(f"Created link: {from_id} -[{rel_type.upper()}]-> {to_id}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()
