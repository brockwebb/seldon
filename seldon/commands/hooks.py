"""`seldon hooks`: the commit gate as a git hook (AD-036-R4; HOOK-001, AD-036 ADDENDUM 02).

    seldon hooks install [--repo PATH]   # core.hooksPath -> the tracked .githooks/, per repository
    seldon hooks status  [--repo PATH]   # installed here? what was it before?
    seldon hooks pre-commit              # run by .githooks/pre-commit; judges the staged files

The mechanism and its reasons are in `seldon/core/hooks.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import click

from seldon.core import hooks as H


@click.group("hooks")
def hooks_group():
    """The commit gate as a git hook (AD-036-R4, HOOK-001)."""


@hooks_group.command("install")
@click.option("--repo", "repo", type=click.Path(file_okay=False, path_type=Path), default=".",
              help="Repository to install in (default: the current directory)")
@click.option("--json", "as_json", is_flag=True, help="machine-readable result")
def hooks_install(repo, as_json):
    """Set this repository's own core.hooksPath to the tracked .githooks/ and record the
    interpreter. Writes .githooks/pre-commit when absent; commit it. Never touches global or
    system config."""
    try:
        res = H.install(repo)
    except H.HookError as exc:
        raise click.ClickException(str(exc))
    st = H.status(Path(res.repo))
    if as_json:
        click.echo(json.dumps({**res.__dict__, "status": st}, indent=1))
    else:
        click.echo(f"{res.repo}: core.hooksPath {res.old_hooks_path or 'unset'} -> "
                   f"{res.hooks_path}; {H.PYTHON_KEY} {res.python}"
                   + ("; wrote .githooks/pre-commit (commit it)" if res.wrote_hook else ""))
        for p in st["problems"]:
            click.echo(f"  still to do: {p}")
    if not st["installed"] and not res.wrote_hook:
        raise SystemExit(1)


@hooks_group.command("status")
@click.option("--repo", "repo", type=click.Path(file_okay=False, path_type=Path), default=".")
def hooks_status(repo):
    """Exit 0 when git will run the tracked seldon hook in this checkout, 1 otherwise."""
    try:
        st = H.status(repo)
    except H.HookError as exc:
        raise click.ClickException(str(exc))
    click.echo(json.dumps(st, indent=1))
    raise SystemExit(0 if st["installed"] else 1)


@hooks_group.command("pre-commit")
def hooks_pre_commit():
    """What .githooks/pre-commit runs. Exit 1 refuses the commit."""
    try:
        findings, summary = H.pre_commit(Path.cwd())
    except Exception as exc:                                        # noqa: BLE001
        # Any failure to judge is a refusal, named: a gate that passes when it cannot read the
        # index is no gate. --no-verify remains the operator's way past.
        click.echo(f"seldon commit gate: could not judge this commit: {type(exc).__name__}: "
                   f"{exc}", err=True)
        click.echo(H.REFUSAL_FOOTER, err=True)
        raise SystemExit(1)
    if findings:
        click.echo(f"seldon commit gate: {len(findings)} finding(s) in the staged files:",
                   err=True)
        for f in findings:
            click.echo(f"  - {f}", err=True)
        click.echo(H.REFUSAL_FOOTER, err=True)
        raise SystemExit(1)
