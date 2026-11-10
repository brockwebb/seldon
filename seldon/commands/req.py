"""`seldon req`: requirements as graph content (SEL-033, SEL-035; AD-013-R1, R2, R4 to R6).

`import` onboards an UNMARKED markdown table (a marked one is output and is refused); `add` creates one requirement
and `update` changes one, authored fields only; `trace` keeps the `verified_by` edges the tests' `verifies` markers
declare; `migrate` removes SEL-033's verbatim cells once; `list` reads them back. The rules are in
`seldon/core/requirements.py`, `req_trace.py` and `req_migrate.py`; the projection is
`seldon docs generate requirements|rtm`.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from seldon.config import get_neo4j_driver, load_project_config
from seldon.core import req_load as RL
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
        click.echo(f"  {len(plan.unresolved)} did not resolve or were kept in the note (listed, not dropped; "
                   f"AD-013-R1):")
        for u in plan.unresolved:
            click.echo(f"    {u}")


def _run(fn):
    """Open the project's driver, call `fn(project_dir, config, driver, database)`, refuse on a RequirementsError."""
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    try:
        return fn(project_dir, config, driver, config["neo4j"]["database"])
    except (RQ.RequirementsError, ValueError) as exc:
        click.echo(f"REFUSED: {exc}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@click.group("req")
def req_group():
    """Requirements as graph content (AD-013): onboard a table, add or update one, trace the tests, list them."""


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
                   "`seldon docs generate` renders it from the graph from then on.")
@click.option("--dry-run", is_flag=True, default=False, help="Plan and report; write nothing.")
def req_import(source, id_column, statement_column, set_by_column, verified_by_column, status_column, document,
               mark, dry_run):
    """Onboard an unmarked requirements table: an SRS_Requirement per row, idempotent on the id (AD-013-R2: a
    marked file is output and is refused; change a requirement with `req update`)."""
    overrides = {"id": id_column, "statement": statement_column, "set_by": set_by_column,
                 "verified_by": verified_by_column, "status": status_column}
    plan, src = _run(lambda p, c, d, db: RL.import_file(p, d, db, _domain(c), c, source, document=document,
                                                        column_overrides=overrides, dry_run=dry_run))
    click.echo(f"{source}: {len(src.rows)} requirement(s) in {len(src.req_tables)} table(s)"
               + (f"; key map of {len(src.keys)}" if src.keys else ""))
    _report(plan, dry_run)
    if mark and not dry_run:
        if RL.mark_source(Path.cwd(), src):
            click.echo(f"marked {source}: each requirements table is now a seldon:projection block; run "
                       f"`seldon docs generate requirements` (or rtm) after declaring it in docs.projections")
        else:
            click.echo(f"{source}: already marked")


def _authored(statement, set_by, section, document, method, note) -> dict:
    return {"description": statement, "set_by": set_by, "section": section, "document": document,
            "verification_method": method, "note": note}


_FIELD_OPTIONS = [
    click.option("--statement", default=None, help="The requirement, one testable sentence."),
    click.option("--set-by", default=None, help="Its source, e.g. `DN-019 §3` (verbatim)."),
    click.option("--section", default=None, help="The heading it sits under in its document."),
    click.option("--document", default=None, help="The projection file it belongs to."),
    click.option("--method", default=None, type=click.Choice(RQ.METHODS),
                 help="How it is verified (default test; AD-013-R6)."),
    click.option("--note", default=None, help="Free text; the Status cell is the state's label, then this."),
    click.option("--state", default=None, help="Move it on the SRS_Requirement machine (verified needs a "
                                                "qualifying verified_by edge)."),
    click.option("--evidence", multiple=True, help="A Result or Issue id that records the evidence of a "
                                                    "non-test method (repeatable; AD-013-R6)."),
    click.option("--dry-run", is_flag=True, default=False),
]


def _with_fields(fn):
    for opt in reversed(_FIELD_OPTIONS):
        fn = opt(fn)
    return fn


@req_group.command("add")
@click.argument("requirement_id")
@_with_fields
def req_add(requirement_id, statement, set_by, section, document, method, note, state, evidence, dry_run):
    """Create one requirement (its statement is required). A test declares that it verifies it with
    `@pytest.mark.verifies("<id>")` and `seldon req trace`."""
    plan = _run(lambda p, c, d, db: RQ.write_one(
        p, d, db, _domain(c), c, requirement_id, create=True, state=state, evidence=evidence, dry_run=dry_run,
        fields=_authored(statement, set_by, section, document, method, note)))
    _report(plan, dry_run)


@req_group.command("update")
@click.argument("requirement_id")
@_with_fields
def req_update(requirement_id, statement, set_by, section, document, method, note, state, evidence, dry_run):
    """Change one requirement's authored fields, its state or its evidence; options not given keep its values."""
    plan = _run(lambda p, c, d, db: RQ.write_one(
        p, d, db, _domain(c), c, requirement_id, create=False, state=state, evidence=evidence, dry_run=dry_run,
        fields=_authored(statement, set_by, section, document, method, note)))
    _report(plan, dry_run)


@req_group.command("trace")
@click.option("--dry-run", is_flag=True, default=False, help="Report the plan; write nothing.")
def req_trace_cmd(dry_run):
    """Bring the verified_by edges to the tests' `@pytest.mark.verifies` markers, read with ast (AD-013-R5)."""
    from seldon.core import req_trace as RT

    tr = _run(lambda p, c, d, db: RT.trace(p, d, db, _domain(c), c, dry_run=dry_run))
    verb = "would write" if dry_run else "wrote"
    click.echo(f"{tr.scan.files} test file(s), {len(tr.scan.markers)} marked node(s); {verb} {len(tr.writes)} "
               f"event(s): {len(tr.added)} edge(s) added, {len(tr.removed)} removed, {tr.tests_created} test node(s) "
               f"created")
    for f in tr.findings:
        click.echo(f"  ⚠ {f}")


@req_group.command("migrate")
@click.option("--dry-run", is_flag=True, default=False, help="Report the plan; write nothing.")
def req_migrate_cmd(dry_run):
    """Once: move SEL-033's verbatim cells to the note, the method or nowhere (an edge carries them), and remove
    them (AD-013 ADDENDUM 02 s.4.1). Idempotent."""
    from seldon.core import req_migrate as RM

    m = _run(lambda p, c, d, db: RM.migrate(p, d, db, c, dry_run=dry_run))
    verb = "would migrate" if dry_run else "migrated"
    click.echo(f"{verb} {len(m.migrated)} requirement(s) ({m.skipped} already migrated); "
               f"{len(m.methods)} given a verification method")
    if m.listed:
        click.echo(f"  {len(m.listed)} cell(s) no edge carries, kept in the note (listed, never dropped):")
        for x in m.listed:
            click.echo(f"    {x}")


@req_group.command("list")
@click.option("--unverified", is_flag=True, default=False, help="Only those with no qualifying verified_by edge.")
@click.option("--json", "as_json", is_flag=True, default=False)
def req_list(unverified, as_json):
    """The project's requirements, with their state, method and verification."""
    def read(p, c, d, db):
        nodes = RQ.load_requirements(d, db)
        keep = {r["id"] for r in RQ.unverified(d, db)} if unverified else None
        return [n for n in nodes if keep is None or n.get("requirement_id") in keep]

    nodes = _run(read)
    rows = [{"id": n.get("requirement_id"), "state": n.get("state"), "document": n.get("document"),
             "method": n.get("verification_method") or RQ.DEFAULT_METHOD, "verified_by": n["_tests"],
             "derived_from": n["_sources"], "satisfied_by": n["_satisfiers"], "statement": n.get("description"),
             "note": n.get("note")} for n in nodes]
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    click.echo(f"{len(rows)} requirement(s)")
    for r in rows:
        click.echo(f"  {r['id']:12s} {str(r['state']):12s} {r['method']:13s} verified by {len(r['verified_by'])}  "
                   f"{str(r['statement'])[:80]}")
