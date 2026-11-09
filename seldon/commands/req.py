"""`seldon req`: load requirements into the graph (SEL-033, AD-013-R1 and R2).

`import` reads a markdown requirements table, `add` writes one requirement, `list` reads them back. The rules and the
grammar are in `seldon/core/requirements.py`; the projection is `seldon docs generate requirements|rtm`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click

from seldon.config import get_neo4j_driver, load_project_config
from seldon.core import requirements as RQ
from seldon.domain.loader import load_domain_config


def _domain(config: dict):
    name = config["project"].get("domain", "research")
    return load_domain_config(Path(__file__).parent.parent / "domain" / f"{name}.yaml")


def _report(plan: RQ.Plan, dry_run: bool) -> None:
    verb = "would write" if dry_run else "wrote"
    click.echo(f"{verb} {len(plan.writes)} event(s): {len(plan.created)} created, {len(plan.updated)} updated, "
               f"{len(plan.unchanged)} unchanged; {plan.links_added} link(s) added, {plan.links_removed} removed; "
               f"{plan.tests_created} test node(s) created")
    if plan.states:
        click.echo("  states: " + ", ".join(f"{s} {n}" for s, n in sorted(plan.states.items())))
    if plan.unresolved:
        click.echo(f"  {len(plan.unresolved)} did not resolve (listed, not dropped; AD-013-R1):")
        for u in plan.unresolved:
            click.echo(f"    {u}")


def _fail(exc: Exception) -> None:
    click.echo(f"REFUSED: {exc}", err=True)
    raise SystemExit(1)


@click.group("req")
def req_group():
    """Requirements as graph content (AD-013-R1): import a table, add one, list them."""


@req_group.command("import")
@click.argument("source")
@click.option("--id-column", default=None, help="The id column's header (default: requirements.columns.id).")
@click.option("--statement-column", default=None, help="The statement column's header.")
@click.option("--set-by-column", default=None, help="The source column's header.")
@click.option("--verified-by-column", default=None, help="The verification column's header.")
@click.option("--status-column", default=None, help="The status column's header.")
@click.option("--document", default=None,
              help="The projection the requirements belong to (default: SOURCE itself).")
@click.option("--mark", is_flag=True, default=False,
              help="Wrap each imported table of SOURCE in seldon:projection markers, once, so "
                   "`seldon docs generate` renders it from the graph.")
@click.option("--dry-run", is_flag=True, default=False, help="Plan and report; write nothing.")
def req_import(source, id_column, statement_column, set_by_column, verified_by_column, status_column, document,
               mark, dry_run):
    """Create or update an SRS_Requirement per row of SOURCE's requirements tables, idempotent on the id."""
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    overrides = {"id": id_column, "statement": statement_column, "set_by": set_by_column,
                 "verified_by": verified_by_column, "status": status_column}
    try:
        plan, src = RQ.import_file(project_dir, driver, config["neo4j"]["database"], _domain(config), config,
                                   source, document=document, column_overrides=overrides, dry_run=dry_run)
    except RQ.RequirementsError as exc:
        _fail(exc)
    finally:
        driver.close()
    click.echo(f"{source}: {len(src.rows)} requirement(s) in {len(src.req_tables)} table(s)"
               + (f"; key map of {len(src.keys)}" if src.keys else ""))
    _report(plan, dry_run)
    if mark and not dry_run:
        if RQ.mark_source(project_dir, src):
            click.echo(f"marked {source}: each requirements table is now a seldon:projection block; run "
                       f"`seldon docs generate requirements` (or rtm) after declaring it in docs.projections")
        else:
            click.echo(f"{source}: already marked")


@req_group.command("add")
@click.argument("requirement_id")
@click.option("--statement", default=None, help="The requirement, one testable sentence (new ids need it).")
@click.option("--set-by", default=None, help="Its source, e.g. `DN-019 §3`; a key that names an artifact links it.")
@click.option("--verified-by", "verified_by", multiple=True, help="A test node `path::node` (repeatable).")
@click.option("--validated-by", default=None, help="The review or answer that confirmed it.")
@click.option("--status", default=None, help="The status text; requirements.status_map maps it to the state.")
@click.option("--section", default=None, help="The heading it sits under in its document.")
@click.option("--document", default=None, help="The projection file it belongs to.")
@click.option("--dry-run", is_flag=True, default=False)
def req_add(requirement_id, statement, set_by, verified_by, validated_by, status, section, document, dry_run):
    """Create or update one requirement; options not given keep the node's values."""
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    try:
        plan = RQ.add_one(project_dir, driver, config["neo4j"]["database"], _domain(config), config,
                          requirement_id, statement=statement, set_by=set_by, verified_by=list(verified_by),
                          validated_by=validated_by, status=status, section=section, document=document,
                          dry_run=dry_run)
    except RQ.RequirementsError as exc:
        _fail(exc)
    finally:
        driver.close()
    _report(plan, dry_run)


@req_group.command("list")
@click.option("--unverified", is_flag=True, default=False, help="Only those with no verified_by edge.")
@click.option("--json", "as_json", is_flag=True, default=False)
def req_list(unverified, as_json):
    """The project's requirements, with their state and verification."""
    config = load_project_config(Path.cwd())
    driver = get_neo4j_driver(config)
    try:
        nodes = RQ.load_requirements(driver, config["neo4j"]["database"])
    finally:
        driver.close()
    if unverified:
        nodes = [n for n in nodes if not n["_tests"] and n.get("state") != "rejected"]
    rows = [{"id": n.get("requirement_id"), "state": n.get("state"), "document": n.get("document"),
             "tests": n["_tests"], "derived_from": n["_sources"], "satisfied_by": n["_satisfiers"],
             "statement": n.get("description")} for n in nodes]
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    click.echo(f"{len(rows)} requirement(s)")
    for r in rows:
        click.echo(f"  {r['id']:12s} {str(r['state']):12s} tests {len(r['tests'])}  {str(r['statement'])[:90]}")
