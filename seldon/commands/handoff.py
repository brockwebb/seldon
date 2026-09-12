"""`seldon handoff` — close a session: write the handoff, print the two blocks.

The command surface is deliberately thin. Everything it does lives in
:mod:`seldon.core.handoff` so that `seldon_handoff` (MCP) is the same code path
and cannot drift from this one.
"""
from __future__ import annotations

from pathlib import Path

import click

from seldon.config import get_neo4j_driver, load_project_config
from seldon.core.handoff import (
    R9Violation,
    build_handoff,
    write_handoff,
)
from seldon.domain.loader import load_domain_config


def _domain_config(config: dict):
    """Load the domain configuration named by a project config.

    Args:
        config: Parsed seldon.yaml.

    Returns:
        The loaded DomainConfig.
    """
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


def r9_refusal_text(violation: R9Violation) -> str:
    """Render the AD-030-R9 refusal, with the evidence that produced it.

    Args:
        violation: The raised refusal.

    Returns:
        Multi-line text for stderr.
    """
    ids = ", ".join(f"`{tid[:8]}`" for tid in violation.verdict.gated_task_ids)
    return (
        f"ERROR: {violation}\n"
        f"  Desktop-created tasks in this window: {ids}\n"
        "  Files under docs/design/ in this window: none.\n"
        "  Why: rulings a task implements must be addressable, or the next "
        "task re-decides them.\n"
        "  Override for this project: set handoff.require_design_note: false "
        "in seldon.yaml."
    )


@click.command("handoff")
@click.option("--slug", required=True, help="Filename slug: handoffs/<date>_<slug>.md")
@click.option("--summary", required=True, help="One line: what this session did.")
@click.option("--next", "next_action", required=True, help="First action for the next session.")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Replace an existing handoff at the same path.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Render and print without writing the file.",
)
def handoff_command(slug, summary, next_action, force, dry_run):
    """Close a session: write the handoff, print the resume and dispatch blocks.

    The document is generated from the event log, the graph and the filesystem;
    only --summary and --next are authored prose (AD-030-R2).

    Refuses to close a Desktop session that created tasks and wrote no design
    note (AD-030-R9), unless handoff.require_design_note is false in seldon.yaml.
    """
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    try:
        document = build_handoff(
            project_dir=project_dir,
            config=config,
            driver=driver,
            database=database,
            domain_config=_domain_config(config),
            slug=slug,
            summary=summary,
            next_action=next_action,
        )
    except R9Violation as violation:
        click.echo(r9_refusal_text(violation), err=True)
        raise SystemExit(1)
    finally:
        driver.close()

    for warning in document.warnings:
        click.echo(warning, err=True)

    if dry_run:
        click.echo(f"[dry-run] would write {document.path}")
        click.echo("")
        click.echo(document.text)
    else:
        try:
            written = write_handoff(document, force=force)
        except FileExistsError as exc:
            click.echo(f"ERROR: {exc}", err=True)
            raise SystemExit(1)
        click.echo(f"Wrote {written}")

    click.echo("")
    click.echo("## Resume block")
    click.echo("")
    click.echo(document.resume)
    click.echo("")
    click.echo("## CC dispatch block")
    click.echo("")
    click.echo(document.dispatch)
