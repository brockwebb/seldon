"""`seldon models`: show, resolve and refresh the machine-wide model lock (AD-035).

The logic is in `seldon.models`; this module is its command surface (AD-003: internal tools are
CLI commands). `resolve --json` prints the full launch block, so a launcher in a repository that
cannot import Seldon can still take its ids from the one accessor.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from seldon import models as M


@click.group(name="models")
def models_group():
    """The model registry (intent) and lock (resolution): AD-035."""


@models_group.command(name="show")
@click.option("--json", "as_json", is_flag=True, help="Print the registry and lock as JSON.")
@click.option("--project", "project", default=None, type=click.Path(file_okay=False),
              help="Print this project's pilot declaration (AD-035-R15). Default: the current directory, when it "
                   "holds a seldon.yaml.")
def models_show(as_json, project):
    """Print every role with its family, effort and locked model id, the lock, when it may next refresh and who holds
    it, and the project's pilot declaration."""
    if project is None and (Path.cwd() / "seldon.yaml").is_file():
        project = str(Path.cwd())
    try:
        data = M.show(project_dir=Path(project) if project else None)
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
        for mid, row in sorted((lock.get("models") or {}).items()):
            click.echo(f"  named   {mid} available={row['available']} served={row.get('served')}")
    click.echo("roles:")
    for r in data["roles"]:
        # AD-035-R9: a role naming a model says so, with whether the lock marks it available (R12).
        named = f"  named, available={r['available']}" if r["named"] else ""
        click.echo(f"  {r['role']:<20} {r['family']:<7} effort={str(r['effort']):<8} {r['model']}{named}")
    click.echo(f"interactive claude on PATH (not launched by any launcher): {data['path_cli']}")
    r = data["refresh"]
    # AD-035-R14: the boundary is a configured fact, and there is no clock behind it.
    click.echo(f"refresh: day boundary {r['cache_boundary_utc']}Z; next eligible {r['next_eligible'] or 'now'}; "
               f"it runs at the first {' or '.join('`' + t + '`' for t in r['triggers'])} after that instant "
               f"with no run holding the lock (no clock job runs it)")
    if "holders_error" in r:
        click.echo(f"  holders: cannot be read: {r['holders_error']}")
    elif not r["holders"]:
        click.echo("  holders: none")
    for h in r.get("holders") or []:
        click.echo(f"  holder: {h['kind']} {h['task'] or ''} ({h['holder'] or '?'}, pid {h['pid']}) "
                   f"{h['repo'] or h['path']}")
    if "pilot" in data:
        decl = data["pilot"]
        if decl is None:
            click.echo(f"pilot: none declared in {data['project']}/seldon.yaml (models.pilot, AD-035-R15)")
        else:
            click.echo(f"pilot ({data['project']}): " + " ".join(
                f"{k}={','.join(v) if isinstance(v, list) else v}" for k, v in decl.items()))


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

    One minimal call per family, plus one per model a role names (AD-035-R10). Cached for the UTC
    day unless --force or a role names a model the lock has never probed. Appends a
    `models_lock_bumped` event when an id, the CLI version or a named model's availability changes
    (AD-035 R2). While a dispatcher lease or a run hold holds the lock, it defers: the lock stands, one
    `lock_refresh_deferred` line names the holders, and it exits 0 (AD-035-R7, R13). `--force` overrides that too.
    """
    try:
        out = M.refresh(force=force, version=version, commit=not no_commit)
    except M.ModelsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    click.echo(f"refresh: {out.status}")
    if out.status == "deferred":
        # AD-035-R13: a deferral is the rule working, not a failure; exit 0.
        for m in out.messages:
            click.echo(m)
        if out.event:
            click.echo(f"event: {out.event['event_type']} {out.event['event_id']} (not committed; the dispatcher's "
                       f"reconciler commits it)")
        return
    for fam, row in sorted(out.lock["families"].items()):
        click.echo(f"  {fam:<7} {row['model']}")
    for mid, row in sorted((out.lock.get("models") or {}).items()):
        click.echo(f"  named   {mid} available={row['available']} served={row.get('served')}"
                   f"{' (' + row['error'] + ')' if row.get('error') else ''}")
    click.echo(f"  cli     {out.lock['cli']['version']} {out.lock['cli']['path']}")
    if out.evidence:
        click.echo(f"evidence: {out.evidence}")
    if out.event:
        click.echo(f"event: {out.event['event_type']} {out.event['event_id']}")
    if out.committed:
        click.echo(f"committed: {out.committed}")
    for m in out.messages:
        click.echo(m)


@models_group.command(name="hold", context_settings={"ignore_unknown_options": True,
                                                    "allow_interspersed_args": False})
@click.option("--run", "run", required=True, help="The run's name: one path segment, unique while it runs.")
@click.option("--by", "by", default=None, help="Who holds it (a task id, a session); recorded in the hold.")
@click.argument("command", nargs=-1, required=True, type=click.UNPROCESSED)
def models_hold(run, by, command):
    """Run COMMAND while holding the model lock (AD-035-R7, R13): `seldon models hold --run NAME -- CMD ...`.

    A refresh defers while the hold is live, so the lock does not move under the run. The hold is an flock taken for
    COMMAND's whole life and dropped by the kernel if this process dies (flock(1) is the prior art). Exits with
    COMMAND's exit code.
    """
    try:
        with M.hold(run, by=by) as path:
            click.echo(f"hold: {run} at {path}", err=True)
            code = subprocess.call(list(command))
    except M.ModelsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    except FileNotFoundError as exc:
        click.echo(f"ERROR: cannot run {command[0]!r}: {exc}", err=True)
        sys.exit(127)
    sys.exit(code)
