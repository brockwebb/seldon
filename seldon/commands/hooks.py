"""`seldon hooks`: the commit gate as a git hook (AD-036-R4; HOOK-001, AD-036 ADDENDUM 02).

    seldon hooks install [--repo PATH]   # core.hooksPath -> the tracked .githooks/, per repository;
                                         # .gitattributes declares the append-only logs merge=union
    seldon hooks status  [--repo PATH]   # installed here? what was it before?
    seldon hooks pre-commit              # run by .githooks/pre-commit; judges the staged files
    seldon hooks commit-msg MSGFILE      # run by .githooks/commit-msg; the prior-art half (DESK-001)
    seldon hooks prepare-commit-msg ...  # run by .githooks/prepare-commit-msg; where a rebase commits (SQ-096)

The mechanism and its reasons are in `seldon/core/hooks.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import click
import yaml

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
    interpreter. Writes .githooks/pre-commit and commit-msg when absent and commits seldon's
    hook files alone, through the hooks (DESK-004R, AD-038-R15). Never touches global or
    system config.

    In a seldon project (a seldon.yaml at the top), also declares the project's append-only logs
    `merge=union` in .gitattributes and commits that file alone through the hooks (AD-034
    ADDENDUM 05): without it every worktree task whose main moved ends in rebase_conflict."""
    try:
        res = H.install(repo)
        top = Path(res.repo)
        union = None
        if (top / "seldon.yaml").is_file():
            config = yaml.safe_load((top / "seldon.yaml").read_text(encoding="utf-8")) or {}
            union = H.declare_union(top, config)
    except H.HookError as exc:
        raise click.ClickException(str(exc))
    st = H.status(top)
    if as_json:
        click.echo(json.dumps({**res.__dict__, "status": st, "union": union}, indent=1))
    else:
        if union is None:
            click.echo(f"{top}: no seldon.yaml; no append-only logs declared")
        elif union["added"]:
            click.echo(f"{top}: {H.GITATTRIBUTES} declares {', '.join(union['added'])} merge=union; "
                       f"committed {union['commit']}")
        else:
            click.echo(f"{top}: {H.GITATTRIBUTES} already declares every append-only log merge=union")
        click.echo(f"{res.repo}: core.hooksPath {res.old_hooks_path or 'unset'} -> "
                   f"{res.hooks_path}; {H.PYTHON_KEY} {res.python}"
                   + (f"; committed {', '.join(res.committed)} as {res.commit}" if res.committed else ""))
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


@hooks_group.command("prepare-commit-msg")
@click.argument("args", nargs=-1)
def hooks_prepare_commit_msg(args):
    """What .githooks/prepare-commit-msg runs (squiddy SQ-096). Exit 1 refuses the commit, including
    one `git rebase --continue` or `git cherry-pick --continue` makes."""
    try:
        findings = H.prepare_commit_msg(Path.cwd())
    except Exception as exc:                                        # noqa: BLE001
        # As pre-commit: a gate that passes when it cannot read the index is no gate.
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


@hooks_group.command("commit-msg")
@click.argument("msgfile", type=click.Path(dir_okay=False, path_type=Path))
def hooks_commit_msg(msgfile):
    """What .githooks/commit-msg runs. Exit 1 refuses the commit.

    The prior-art check (AD-036-R4) as amended by AD-036 ADDENDUM 05: a design note without a
    passing verdict commits only when the subject carries `draft:` (DESK-001)."""
    try:
        message = msgfile.read_text(encoding="utf-8", errors="replace")
        findings, drafts, _summary = H.commit_msg(Path.cwd(), message)
    except Exception as exc:                                        # noqa: BLE001
        click.echo(f"seldon commit gate: could not judge this commit: {type(exc).__name__}: "
                   f"{exc}", err=True)
        click.echo(H.REFUSAL_FOOTER, err=True)
        raise SystemExit(1)
    if findings:
        click.echo(f"seldon commit gate: {len(findings)} finding(s) in the staged files:",
                   err=True)
        for f in findings:
            click.echo(f"  - {f}", err=True)
        click.echo(H.DRAFT_FOOTER, err=True)
        click.echo(H.REFUSAL_FOOTER, err=True)
        raise SystemExit(1)
    for d in drafts:
        click.echo(f"seldon commit gate: draft admitted: {d}", err=True)
