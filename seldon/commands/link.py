from __future__ import annotations

from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.core.artifacts import create_link as do_create_link
from seldon.core.graph import get_artifact, find_artifact_by_property, find_any_artifact_by_name
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
@click.argument("from_id", required=False, default=None)
@click.argument("rel_type", required=False, default=None)
@click.argument("to_id", required=False, default=None)
@click.option("--from-id", "from_id_opt", default=None, help="Source artifact UUID (alternative to positional)")
@click.option("--to-id", "to_id_opt", default=None, help="Target artifact UUID (alternative to positional)")
@click.option("--from-name", "from_name", default=None, help="Source artifact name (alternative to FROM_ID)")
@click.option("--to-name", "to_name", default=None, help="Target artifact name (alternative to TO_ID)")
@click.option("--rel", "rel_type_opt", default=None, help="Relationship type (alternative to REL_TYPE positional)")
@click.option("--actor", default="human", show_default=True)
@click.option("--authority", default="accepted", show_default=True,
              type=click.Choice(["proposed", "accepted"]))
def link_create(from_id, rel_type, to_id, from_id_opt, to_id_opt, from_name, to_name, rel_type_opt, actor, authority):
    """
    Create a directed relationship between two artifacts.

    Positional: seldon link create <from_uuid> <rel_type> <to_uuid>
    Named:      seldon link create --from-name X --rel generated_by --to-name Y
    """
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]

    # Resolution priority: positional > --from-id/--to-id > --from-name/--to-name
    resolved_from = from_id or from_id_opt
    resolved_to = to_id or to_id_opt
    resolved_rel = rel_type or rel_type_opt

    if resolved_from is None and from_name:
        with driver.session(database=database) as session:
            node = find_any_artifact_by_name(session, from_name)
        if node is None:
            click.echo(f"Error: no artifact with name='{from_name}' found", err=True)
            driver.close()
            raise SystemExit(1)
        resolved_from = node["artifact_id"]

    if resolved_to is None and to_name:
        with driver.session(database=database) as session:
            node = find_any_artifact_by_name(session, to_name)
        if node is None:
            click.echo(f"Error: no artifact with name='{to_name}' found", err=True)
            driver.close()
            raise SystemExit(1)
        resolved_to = node["artifact_id"]

    if not resolved_from or not resolved_to or not resolved_rel:
        click.echo("Error: must provide from_id, rel_type, and to_id (positional or via flags)", err=True)
        driver.close()
        raise SystemExit(1)

    # Fetch artifact types for validation
    with driver.session(database=database) as session:
        from_node = get_artifact(session, resolved_from)
        to_node = get_artifact(session, resolved_to)

    if from_node is None:
        click.echo(f"Error: artifact '{resolved_from}' not found", err=True)
        driver.close()
        raise SystemExit(1)
    if to_node is None:
        click.echo(f"Error: artifact '{resolved_to}' not found", err=True)
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
            from_id=resolved_from,
            to_id=resolved_to,
            from_type=from_type,
            to_type=to_type,
            rel_type=resolved_rel.lower(),
            actor=actor,
            authority=authority,
        )
        click.echo(f"Created link: {resolved_from} -[{resolved_rel.upper()}]-> {resolved_to}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()
