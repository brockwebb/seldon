"""`seldon models`: show, resolve and refresh the machine-wide model lock (AD-035).

The logic is in `seldon.models`; this module is its command surface (AD-003: internal tools are
CLI commands). `resolve --json` prints the full launch block, so a launcher in a repository that
cannot import Seldon can still take its ids from the one accessor.
"""
from __future__ import annotations

import sys

import click

from seldon import models as M


@click.group(name="models")
def models_group():
    """The model registry (intent) and lock (resolution): AD-035."""


@models_group.command(name="show")
@click.option("--json", "as_json", is_flag=True, help="Print the registry and lock as JSON.")
def models_show(as_json):
    """Print every role with its family, effort and locked model id, and the lock itself."""
    try:
        data = M.show()
    except M.ModelsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    if as_json:
        click.echo(M.as_json(data))
        return
    lock = data["lock"]
    click.echo(f"models home: {data['home']}")
    if "error" in lock:
        click.echo(f"lock: {lock['error']}")
    else:
        click.echo(f"lock: resolved {lock.get('resolved_on')} by CLI {lock['cli']['version']} "
                   f"({lock['cli']['path']}); evidence {lock.get('evidence')}")
        for fam, row in sorted(lock["families"].items()):
            click.echo(f"  {fam:<7} {row['model']}")
    click.echo("roles:")
    for r in data["roles"]:
        click.echo(f"  {r['role']:<20} {r['family']:<7} effort={r['effort']:<8} {r['model']}")
    click.echo(f"interactive claude on PATH (not launched by any launcher): {data['path_cli']}")


@models_group.command(name="resolve")
@click.argument("role")
@click.option("--json", "as_json", is_flag=True,
              help="Print the full launch block: model, CLI path and version, env, args.")
def models_resolve(role, as_json):
    """Print the model id ROLE resolves to (or, with --json, the launch block)."""
    try:
        spec = M.launch_spec(role)
    except M.ModelsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    click.echo(M.as_json(spec) if as_json else spec["model"])


@models_group.command(name="refresh")
@click.option("--force", is_flag=True, help="Re-probe although the lock was resolved today.")
@click.option("--version", "version", default=None,
              help="Install and probe this CLI version instead of npm's newest.")
@click.option("--no-commit", is_flag=True, help="Write the lock and evidence; do not commit.")
def models_refresh(force, version, no_commit):
    """Install the newest CLI into a versioned prefix, probe each family alias, write the lock.

    Four minimal calls (one per family). Cached for the UTC day unless --force. Appends a
    `models_lock_bumped` event when an id or the CLI version changes (AD-035 R2).
    """
    try:
        out = M.refresh(force=force, version=version, commit=not no_commit)
    except M.ModelsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    click.echo(f"refresh: {out.status}")
    for fam, row in sorted(out.lock["families"].items()):
        click.echo(f"  {fam:<7} {row['model']}")
    click.echo(f"  cli     {out.lock['cli']['version']} {out.lock['cli']['path']}")
    if out.evidence:
        click.echo(f"evidence: {out.evidence}")
    if out.event:
        click.echo(f"event: {out.event['event_type']} {out.event['event_id']}")
    if out.committed:
        click.echo(f"committed: {out.committed}")
    for m in out.messages:
        click.echo(m)
