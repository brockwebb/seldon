"""`seldon commit-governed`: commit what a Desktop session wrote (DESK-001).

    seldon commit-governed docs/design/AD-040_x.md [more paths] [--project DIR] [--json]

The mechanism and every refusal are in `seldon/core/desktop_commit.py`. The MCP tool
`seldon_commit_governed` is the same call for a Desktop session, which has no shell.
"""
from __future__ import annotations

import json
from pathlib import Path

import click

from seldon.core import desktop_commit as DC


@click.command("commit-governed")
@click.argument("paths", nargs=-1, required=True)
@click.option("--project", "project", default=None,
              help="The project the paths belong to (default: the working directory).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable outcome.")
def commit_governed_command(paths, project, as_json):
    """Commit exactly PATHS (under docs/design/, cc_tasks/, handoffs/, issues/, ontology/) through
    the hooks, as `desktop: <kind>: <basename>`. A design note without a passing prior-art verdict
    is committed as `draft:`. Exit 1 on any refusal; nothing stays staged."""
    project_dir = Path(project).expanduser().resolve() if project else Path.cwd()
    outcome = DC.commit_governed(project_dir, list(paths))
    if as_json:
        click.echo(json.dumps(outcome.as_dict(), indent=1))
    else:
        click.echo(DC.render(outcome), err=not outcome.committed)
    if not outcome.committed:
        raise SystemExit(1)
