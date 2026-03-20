from __future__ import annotations

from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.domain.loader import load_domain_config
from seldon.paper.qc import (
    load_qc_config,
    load_style_config,
    run_tier2,
    run_tier3,
    format_violations,
)
from seldon.paper.build import build_paper


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


@click.group("paper")
def paper_group():
    """Paper authoring: prose QC and graph-driven manuscript assembly."""
    pass


@paper_group.command("audit")
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--tier", type=click.Choice(["2", "3"]), default=None,
              help="Run only Tier 2 (prose) or Tier 3 (style) checks.")
@click.option("--qc-config", "qc_config_path", default=None, type=click.Path(),
              help="Override Tier 2 config path.")
@click.option("--style-config", "style_config_path", default=None, type=click.Path(),
              help="Override Tier 3 config path.")
def paper_audit(files, tier, qc_config_path, style_config_path):
    """Check markdown prose for quality (Tier 2) and style (Tier 3) violations.

    FILES defaults to paper/sections/*.md relative to the current directory.
    """
    project_dir = Path.cwd()

    # Resolve files
    if files:
        paths = [Path(f) for f in files]
    else:
        default_dir = project_dir / "paper" / "sections"
        if not default_dir.exists():
            click.echo(f"No files provided and {default_dir} does not exist.", err=True)
            raise SystemExit(1)
        paths = sorted(default_dir.glob("*.md"))
        if not paths:
            click.echo(f"No .md files found in {default_dir}.", err=True)
            raise SystemExit(1)

    # Load configs
    qc_config = load_qc_config(Path(qc_config_path) if qc_config_path else None)
    style_config = load_style_config(Path(style_config_path) if style_config_path else None)

    run_tier2_checks = tier in (None, "2")
    run_tier3_checks = tier in (None, "3")

    tier2_violations = []
    tier3_violations = []

    for path in paths:
        text = path.read_text()
        if run_tier2_checks:
            tier2_violations.extend(run_tier2(text, qc_config, filename=str(path)))
        if run_tier3_checks:
            tier3_violations.extend(run_tier3(text, style_config, filename=str(path)))

    if run_tier2_checks:
        click.echo(format_violations(tier2_violations, "TIER 2: Prose Quality"))
    if run_tier3_checks:
        click.echo(format_violations(tier3_violations, "TIER 3: Style Preferences"))

    # Exit 1 if any Tier 2 violations
    if run_tier2_checks and tier2_violations:
        raise SystemExit(1)


@paper_group.command("sync")
@click.option("--register-untracked", is_flag=True, default=False,
              help="Auto-create PaperSection artifacts for untracked section files.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Show what would change without writing anything.")
@click.option("--auto-stale", is_flag=True, default=False,
              help="Automatically transition changed sections to stale if in review or published state.")
def paper_sync(register_untracked, dry_run, auto_stale):
    """Reconcile section files on disk with graph state.

    Detects content changes, updates CITES edges for added/removed references,
    and optionally transitions changed sections to stale. Run after editing sections.
    """
    from seldon.paper.sync import sync_all

    project_dir = Path.cwd()
    paper_dir = project_dir / "paper"

    config = load_project_config()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]

    try:
        results = sync_all(
            driver=driver,
            database=database,
            project_dir=project_dir,
            domain_config=domain_config,
            paper_dir=paper_dir,
            dry_run=dry_run,
            auto_stale=auto_stale,
            register_untracked=register_untracked,
        )
    finally:
        driver.close()

    if not results:
        click.echo("No section files found in paper/sections/.")
        return

    click.echo("PAPER SYNC REPORT")
    click.echo("═" * 50)
    click.echo()

    col_width = max(len(r.filename) for r in results) + 3
    counts = {"updated": 0, "untracked": 0, "unchanged": 0, "registered": 0}

    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
        name_col = r.filename.ljust(col_width, ".")

        if r.status == "unchanged":
            click.echo(f"  {name_col} unchanged")
        elif r.status == "untracked":
            click.echo(f"  {name_col} untracked (no PaperSection artifact)")
        elif r.status == "registered":
            click.echo(f"  {name_col} REGISTERED")
        elif r.status == "updated":
            parts = []
            if r.refs_added:
                parts.append(f"{len(r.refs_added)} ref{'s' if len(r.refs_added) != 1 else ''} added")
            if r.refs_removed:
                parts.append(f"{len(r.refs_removed)} ref{'s' if len(r.refs_removed) != 1 else ''} removed")
            if r.state_changed:
                parts.append("→ stale")
            detail = f" ({', '.join(parts)})" if parts else ""
            prefix = "[dry-run] " if dry_run else ""
            click.echo(f"  {name_col} {prefix}UPDATED{detail}")

    click.echo()
    summary_parts = []
    if counts.get("updated"):
        summary_parts.append(f"{counts['updated']} updated")
    if counts.get("registered"):
        summary_parts.append(f"{counts['registered']} registered")
    if counts.get("untracked"):
        summary_parts.append(f"{counts['untracked']} untracked")
    if counts.get("unchanged"):
        summary_parts.append(f"{counts['unchanged']} unchanged")
    click.echo(f"Summary: {', '.join(summary_parts)}")


@paper_group.command("register")
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--all", "register_all", is_flag=True, default=False,
              help="Register all section files in paper/sections/.")
def paper_register(files, register_all):
    """Register section files as PaperSection artifacts.

    Creates PaperSection artifacts with name, title, file_path, and content_hash.
    Skips files that already have a PaperSection artifact.

    Provide FILE paths explicitly, or use --all to discover paper/sections/*.md.
    """
    from seldon.paper.sync import get_paper_section_artifacts, _register_section

    project_dir = Path.cwd()
    config = load_project_config()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]

    try:
        if register_all:
            sections_dir = project_dir / "paper" / "sections"
            if not sections_dir.exists():
                click.echo(f"Error: {sections_dir} does not exist.", err=True)
                raise SystemExit(1)
            paths = sorted(sections_dir.glob("*.md"))
        elif files:
            paths = [Path(f) for f in files]
        else:
            click.echo("Error: specify files or use --all.", err=True)
            raise SystemExit(1)

        if not paths:
            click.echo("No section files found.")
            return

        existing = get_paper_section_artifacts(driver, database)
        registered = 0
        skipped = 0

        for path in paths:
            if path.stem in existing or str(path) in existing:
                click.echo(f"  {path.name} ... skipped (already registered)")
                skipped += 1
                continue
            artifact_id = _register_section(
                driver, database, project_dir, domain_config, path, actor="human"
            )
            click.echo(f"  {path.name} ... registered ({artifact_id[:8]})")
            registered += 1

    finally:
        driver.close()

    click.echo(f"\nRegistered {registered}, skipped {skipped}.")


@paper_group.command("build")
@click.option("--skip-qc", is_flag=True, default=False,
              help="Skip Tier 2 and Tier 3 QC. Tier 1 structural checks always run.")
@click.option("--strict", is_flag=True, default=False,
              help="Treat Tier 2 warnings as errors.")
@click.option("--output", "output_path", default=None, type=click.Path(),
              help="Override output .qmd path.")
@click.option("--no-render", is_flag=True, default=False,
              help="Resolve references and run QC but do not call Quarto.")
@click.option("--qc-config", "qc_config_path", default=None, type=click.Path(),
              help="Override Tier 2 config path.")
@click.option("--style-config", "style_config_path", default=None, type=click.Path(),
              help="Override Tier 3 config path.")
def paper_build(skip_qc, strict, output_path, no_render, qc_config_path, style_config_path):
    """Resolve graph references, run QC, assemble .qmd, and render via Quarto."""
    project_dir = Path.cwd()
    paper_dir = project_dir / "paper"

    exit_code = build_paper(
        project_dir=project_dir,
        paper_dir=paper_dir,
        output_path=Path(output_path) if output_path else None,
        skip_qc=skip_qc,
        strict=strict,
        no_render=no_render,
        qc_config_path=Path(qc_config_path) if qc_config_path else None,
        style_config_path=Path(style_config_path) if style_config_path else None,
    )
    raise SystemExit(exit_code)
