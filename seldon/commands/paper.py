from __future__ import annotations

from pathlib import Path

import click

from seldon.paper.qc import (
    load_qc_config,
    load_style_config,
    run_tier2,
    run_tier3,
    format_violations,
)
from seldon.paper.build import build_paper


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
