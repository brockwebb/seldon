"""`seldon decision` — the decision register's one write path (AD-033-R2), CLI form.

    seldon decision propose   --from record.yaml --decided-by <who> [--date D] [--receipt R ...]
    seldon decision accept    --from record.yaml ...       (a new record, accepted when registered)
    seldon decision accept    <id> --reason <why> ...      (a proposed record accepted)
    seldon decision reject    <id> --reason <why> ...
    seldon decision deprecate <id> --reason <why> ...
    seldon decision supersede --from record.yaml ...       (a new record naming `supersedes`)
    seldon decision supersede <id> --by <id> --reason <why> ...
    seldon decision amend     <id> --reason <why> [--clause C --text T [--by <id>]] [--changes changes.yaml]
    seldon decision show      <id>
    seldon decision list      [--status S] [--repo R]
    seldon decision check
    seldon decision project   (replay the register into `Decision` nodes; render REGISTER.md)

The MCP tools (`seldon_decision_*`) call :func:`run_write` and :func:`run_read` below, so the two
surfaces cannot drift: a refusal on one is the same refusal on the other.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import click
import yaml

from seldon.config import get_current_session, get_neo4j_driver, load_project_config
from seldon.core import decisions as dr


def _domain_config(config: dict):
    from seldon.domain.loader import load_domain_config

    name = config["project"].get("domain", "research")
    return load_domain_config(Path(__file__).parent.parent / "domain" / f"{name}.yaml")


def run_write(project_dir: Path, action: str, *, qid: Optional[str] = None,
              record: Optional[dict] = None, decided_by: str, date: Optional[str] = None,
              reason: Optional[str] = None, receipts: Optional[list[str]] = None,
              operator_stated: bool = False, superseded_by: Optional[str] = None,
              amendment: Optional[dict] = None, changes: Optional[dict] = None,
              render: bool = True) -> list[Path]:
    """Every write, CLI or MCP. Raises :class:`seldon.core.decisions.RegisterError` on refusal.

    After a write the repository's REGISTER.md is rendered again, so the rendered view never lags
    the files (the projection into the graph is `seldon decision project`, or `verify --fix`).
    """
    config = load_project_config(project_dir)
    u = dr.universe(project_dir, config)
    date = date or dr.today()
    common = dict(date=date, decided_by=decided_by, operator_stated=operator_stated,
                  receipts=receipts, reason=reason)
    if action in ("propose", "accept", "supersede") and record is not None:
        written = dr.create(u, action, record, **common)
    elif action in ("accept", "reject", "deprecate", "supersede"):
        if not qid:
            raise dr.RegisterError(f"{action} names the record it acts on")
        if not reason:
            raise dr.RegisterError(f"{action} of an existing record states its reason")
        written = dr.transition(u, action, qid, superseded_by=superseded_by, **common)
    elif action == "amend":
        if not qid or not reason:
            raise dr.RegisterError("amend names the record and states its reason")
        written = dr.amend(u, qid, amendment=amendment, changes=changes, **common)
    elif action == "propose":
        raise dr.RegisterError("propose takes the record (--from FILE)")
    else:
        raise dr.RegisterError(f"unknown action {action!r}")
    if render and u.register(u.s.repository).exists():
        dr.write_rendered(dr.universe(project_dir, config))
    return written


def run_read(project_dir: Path, action: str, *, qid: Optional[str] = None,
             status: Optional[str] = None, repo: Optional[str] = None) -> str:
    config = load_project_config(project_dir)
    if action == "check":
        findings = dr.check(project_dir, config)
        return ("register: clean" if not findings else
                f"{len(findings)} finding(s):\n  " + "\n  ".join(findings))
    u = dr.universe(project_dir, config)
    if action == "show":
        return dr.show(u, qid)
    if action == "list":
        recs = dr.list_records(u, [repo] if repo else None, status)
        lines = [f"{len(recs)} record(s)"]
        for r in recs:
            st = " ".join(str(dr._statement_of(r)).split())
            lines.append(f"  {r.id:32s} {r.status:10s} {st[:110]}")
        return "\n".join(lines)
    raise dr.RegisterError(f"unknown read {action!r}")


def _load_record(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise click.UsageError(f"{path} is not a YAML mapping of record fields")
    return data


def _common(fn):
    fn = click.option("--decided-by", required=True,
                      help="operator, desktop, cc:<task id>, or inherited:<repository> (AD-033-R3).")(fn)
    fn = click.option("--date", default=None, help="YYYY-MM-DD; default today.")(fn)
    fn = click.option("--reason", default=None, help="Why: finding ids, quotes, grounding.")(fn)
    fn = click.option("--receipt", "receipts", multiple=True,
                      help="Evidence for the decision or the event (repeatable).")(fn)
    fn = click.option("--operator-stated", is_flag=True, default=False,
                      help="The operator stated it in his own words; requires --receipt.")(fn)
    return fn


def _emit(written: list[Path], project_dir: Path) -> None:
    for p in written:
        try:
            click.echo(f"wrote {p.relative_to(project_dir)}")
        except ValueError:
            click.echo(f"wrote {p}")


def _fail(exc: Exception) -> None:
    click.echo(f"REFUSED: {exc}", err=True)
    raise SystemExit(1)


@click.group("decision")
def decision_group():
    """The decision register (AD-033): one write path, status derived, never edited."""


_HELP = {
    "propose": "Register a new record as proposed (it waits on a named measurement).",
    "accept": "Register a new record accepted (--from), or accept a proposed one (QID).",
    "supersede": "Register a record that supersedes others (--from), or declare QID superseded "
                 "--by an accepted record.",
    "reject": "Reject a proposed record.",
    "deprecate": "Withdraw an active record with nothing replacing it.",
}


def _create_or_transition(action: str):
    @decision_group.command(action, help=_HELP[action])
    @click.argument("qid", required=False)
    @click.option("--from", "from_file", default=None, help="YAML of the new record's fields.")
    @click.option("--by", "superseded_by", default=None, help="supersede: the record that supersedes QID.")
    @_common
    def cmd(qid, from_file, superseded_by, decided_by, date, reason, receipts, operator_stated):
        project_dir = Path.cwd()
        try:
            written = run_write(project_dir, action, qid=qid, record=_load_record(from_file),
                                decided_by=decided_by, date=date, reason=reason,
                                receipts=list(receipts), operator_stated=operator_stated,
                                superseded_by=superseded_by)
        except dr.RegisterError as exc:
            _fail(exc)
        _emit(written, project_dir)
    return cmd


for _a in ("propose", "accept", "supersede"):
    _create_or_transition(_a)


def _transition_only(action: str):
    @decision_group.command(action, help=_HELP[action])
    @click.argument("qid")
    @_common
    def cmd(qid, decided_by, date, reason, receipts, operator_stated):
        project_dir = Path.cwd()
        try:
            written = run_write(project_dir, action, qid=qid, decided_by=decided_by, date=date,
                                reason=reason, receipts=list(receipts),
                                operator_stated=operator_stated)
        except dr.RegisterError as exc:
            _fail(exc)
        _emit(written, project_dir)
    return cmd


for _a in ("reject", "deprecate"):
    _transition_only(_a)


@decision_group.command("amend")
@click.argument("qid")
@click.option("--clause", default=None, help="Which part of the record the amendment changes.")
@click.option("--text", default=None, help="The amendment, in words.")
@click.option("--by", "by", default=None, help="The record that makes the amendment, if one does.")
@click.option("--changes", "changes_file", default=None,
              help=f"YAML mapping of field changes; amendable: {', '.join(dr.AMENDABLE)}.")
@_common
def amend_cmd(qid, clause, text, by, changes_file, decided_by, date, reason, receipts, operator_stated):
    """Amend an active record's clause, change its amendable fields, or both."""
    project_dir = Path.cwd()
    amendment = {"clause": clause, "text": text, "by": by} if (clause or text) else None
    changes = _load_record(changes_file)
    try:
        written = run_write(project_dir, "amend", qid=qid, decided_by=decided_by, date=date,
                            reason=reason, receipts=list(receipts), operator_stated=operator_stated,
                            amendment=amendment, changes=changes)
    except dr.RegisterError as exc:
        _fail(exc)
    _emit(written, project_dir)


@decision_group.command("show")
@click.argument("qid")
def show_cmd(qid):
    """Print one record as its events say it stands now."""
    try:
        click.echo(run_read(Path.cwd(), "show", qid=qid))
    except dr.RegisterError as exc:
        _fail(exc)


@decision_group.command("list")
@click.option("--status", default=None, type=click.Choice(sorted(dr.SCHEMA.enums["DecisionStatus"])))
@click.option("--repo", default=None, help="One repository; default this one and its imports.")
def list_cmd(status, repo):
    """List records (this repository and its imports)."""
    try:
        click.echo(run_read(Path.cwd(), "list", status=status, repo=repo))
    except dr.RegisterError as exc:
        _fail(exc)


@decision_group.command("check")
@click.option("--probe", "with_probe", is_flag=True, default=False,
              help="Also re-run the conflicts probe on the register (AD-033-R9): open contradictions, "
                   "silent supersessions among active records.")
def check_cmd(with_probe):
    """The register checks `seldon verify` fails on (and, with --probe, the conflicts probe)."""
    out = run_read(Path.cwd(), "check")
    click.echo(out)
    failed = out != "register: clean"
    if with_probe:
        text, clean = run_probe(Path.cwd())
        click.echo(text)
        failed = failed or not clean
    if failed:
        raise SystemExit(1)


def run_probe(project_dir: Path) -> tuple[str, bool]:
    """The conflicts probe on the register, rendered; `(text, clean)`."""
    config = load_project_config(project_dir)
    u = dr.universe(project_dir, config)
    if not u.s.probe_findings:
        raise dr.RegisterError("seldon.yaml decisions.probe.findings names no conflicts file")
    rep = dr.conflicts_probe(u, u.s.probe_findings, u.s.probe_exclusions)
    lines = [f"conflicts probe: {rep.findings_total} findings, {len(rep.resolved)} resolved; "
             f"{rep.active_records} active records; open contradictions {len(rep.open_contradictions)}; "
             f"open silent supersessions {len(rep.open_silent_supersessions) + len(rep.unrecorded_pairs)}; "
             f"reviewed exclusions {len(rep.excluded_pairs)}"]
    lines += [f"  OPEN {x}" for x in rep.open_contradictions + rep.open_silent_supersessions]
    lines += [f"  UNRECORDED {x['record']} {x['verb']} {x['cites']}: {x['sentence']}" for x in rep.unrecorded_pairs]
    return "\n".join(lines), rep.clean


@decision_group.command("project")
def project_cmd():
    """Replay the register (own and imported) into `Decision` nodes; render REGISTER.md."""
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    try:
        rep = dr.project(project_dir=project_dir, config=config, driver=driver,
                         database=config["neo4j"]["database"], domain_config=_domain_config(config),
                         session_id=get_current_session(project_dir))
    except dr.RegisterError as exc:
        _fail(exc)
    finally:
        driver.close()
    click.echo(f"projection: {rep.created} created, {rep.updated} updated, {rep.unchanged} unchanged, "
               f"{rep.transitions} status transition(s); edges {rep.edges_created or 0}; "
               f"skipped (endpoint outside this graph) {rep.edges_skipped or 0}; "
               f"positional rulings demoted {rep.rulings_demoted}")
    click.echo(f"by status: {rep.by_status}")
    if rep.rendered:
        click.echo(f"rendered {rep.rendered}")
