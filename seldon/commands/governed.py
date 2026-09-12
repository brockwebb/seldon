"""`seldon governed` — import the governed-documents ledger, and search what it holds.

Three commands over :mod:`seldon.core.governed`:

    seldon governed sync [--all | <path>] [--dry-run]
    seldon governed search <terms> [--type Ruling] [--limit N]
    seldon governed status

`sync` is also what `seldon verify --fix` runs, so the hook and the hand-run command cannot drift.
"""
from __future__ import annotations

from pathlib import Path

import click

from seldon.config import get_current_session, get_neo4j_driver, load_project_config
from seldon.core import governed
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


def render_report(report: governed.SyncReport) -> str:
    """Render a sync report for the terminal.

    Args:
        report: What the run did.

    Returns:
        Multi-line text.
    """
    prefix = "[dry-run] " if report.dry_run else ""
    lines = [
        f"{prefix}governed sync — {report.documents_seen} document(s) in the ledger",
        f"  Documents: {report.documents_created} created, {report.documents_updated} updated, "
        f"{report.documents_unchanged} unchanged (hash matched)",
    ]
    if report.nodes_created:
        lines.append("  Nodes created: " + ", ".join(
            f"{t} {n}" for t, n in sorted(report.nodes_created.items())))
    if report.nodes_updated:
        lines.append("  Nodes updated: " + ", ".join(
            f"{t} {n}" for t, n in sorted(report.nodes_updated.items())))
    if report.edges_created:
        lines.append("  Edges created: " + ", ".join(
            f"{t} {n}" for t, n in sorted(report.edges_created.items())))
    if report.linked_legacy:
        lines.append(f"  Matched to an existing ArchitecturalDecision or DesignNote: "
                     f"{report.linked_legacy}")
    if report.edges_suspect:
        lines.append(f"  Edges marked suspect by a content-hash change: {report.edges_suspect}")
    if report.edges_cleared:
        lines.append(f"  Suspect edges cleared after re-derivation: {report.edges_cleared}")
    if report.abstained:
        total = sum(report.abstained.values())
        shown = ", ".join(f"{k}" for k in sorted(report.abstained)[:8])
        lines.append(
            f"  Abstained on {len(report.abstained)} identifier(s), {total} reference(s): "
            f"{shown}{' ...' if len(report.abstained) > 8 else ''} — nothing in this graph "
            f"answers to them, which is recorded, not guessed at."
        )
    return "\n".join(lines)


@click.group("governed")
def governed_group():
    """Governed documents as graph content (AD-030)."""


@governed_group.command("sync")
@click.argument("path", required=False)
@click.option("--all", "sync_all", is_flag=True, default=False,
              help="Sync every governed document (the default when no path is given).")
@click.option("--dry-run", is_flag=True, default=False, help="Report; write nothing.")
def governed_sync(path, sync_all, dry_run):
    """Import the governed-documents ledger into this project's graph.

    Idempotent by content hash: a document whose sha256 has not moved produces no events at all.
    A document whose hash HAS moved is updated and every edge touching it is marked suspect.

    PATH optionally names one governed document (repo-relative) instead of all of them.
    """
    if path and sync_all:
        click.echo("ERROR: give a path or --all, not both.", err=True)
        raise SystemExit(1)

    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    ledger = governed.ledger_path(project_dir, config)
    if not ledger.is_file():
        driver.close()
        click.echo(
            f"ERROR: no governed ledger at {ledger}.\n"
            f"  The governed graph has not been built. Run, from the project root:\n"
            f"    make -C governed catalog && make -C governed sweep",
            err=True,
        )
        raise SystemExit(1)

    try:
        report = governed.sync(
            project_dir=project_dir, config=config, driver=driver, database=database,
            domain_config=_domain_config(config), only=path, dry_run=dry_run,
            session_id=get_current_session(project_dir),
        )
    except ValueError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()

    click.echo(render_report(report))


@governed_group.command("search")
@click.argument("terms", nargs=-1, required=True)
@click.option("--type", "artifact_type", default=None,
              help="Restrict to one type: Section, Ruling, Passage, Citation, Document.")
@click.option("--limit", default=20, show_default=True, help="Maximum hits.")
def governed_search(terms, artifact_type, limit):
    """Full-text search over governed document text.

    Returns the document, the section id and the span, so a hit can be read back from the file
    it came from rather than only from the graph.
    """
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    query = " ".join(terms)
    try:
        hits = governed.search(driver, database, query, artifact_type=artifact_type, limit=limit)
    except RuntimeError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        driver.close()
        raise SystemExit(1)
    finally:
        driver.close()

    if not hits:
        click.echo(f"No governed text matches {query!r}.")
        return

    click.echo(f"{len(hits)} hit(s) for {query!r}:")
    for hit in hits:
        span = ""
        if hit.get("span_start") is not None:
            span = f" [{hit['span_start']}:{hit['span_end']}]"
        click.echo(f"\n  {hit['artifact_type']}  {hit.get('source_document') or '?'}{span}")
        click.echo(f"    id: {hit.get('name')}")
        text = " ".join((hit.get("text") or "").split())
        click.echo(f"    {text[:300]}{'...' if len(text) > 300 else ''}")


@governed_group.command("status")
def governed_status():
    """What the graph holds, and what the ledger says it should."""
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    try:
        view = governed.read_ledger(governed.ledger_path(project_dir, config))
        have = governed.existing_documents(driver, database)
        stale = governed.out_of_date(project_dir, config, driver, database)
        counts = governed.graph_counts(driver, database)
    finally:
        driver.close()

    click.echo(f"Ledger:  {len(view.documents())} document(s), {len(view.nodes)} node(s), "
               f"{len(view.edges)} edge(s)")
    click.echo(f"Graph:   {len(have)} Document artifact(s)")
    for artifact_type, n in sorted(counts["nodes"].items()):
        click.echo(f"           {artifact_type}: {n}")
    if counts["edges"]:
        click.echo("  Edges:   " + ", ".join(f"{t} {n}" for t, n in sorted(counts["edges"].items())))
    if counts["suspect_edges"]:
        click.echo(f"  Suspect: {counts['suspect_edges']} edge(s) awaiting review")
    if stale:
        click.echo(f"\n{len(stale)} document(s) not in sync — run `seldon governed sync`:")
        for path in stale[:20]:
            click.echo(f"  - {path}")
        if len(stale) > 20:
            click.echo(f"  ... and {len(stale) - 20} more")
    else:
        click.echo("\nEvery governed document in the ledger is in sync with the graph.")
