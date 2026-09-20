"""`seldon cadence` — read the schedules, and render a template because somebody asked.

`ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence_after.md` decision 2,
from DN-007 ruling 3 ("a cycle is rendered on request").

**The condition this closes.** `seldon.core.cadence.render` has existed since DN-006 decision 8
and was reachable from exactly one place: the dispatcher's cadence pass. A project that turns
its schedule off — `dispatch.cadence: []`, which ai-readiness-kg did on 2026-09-18 when the
operator ruled that a scan cycle is requested and not scheduled — therefore has a template it
cannot render with the tool that owns the template format. Two things followed, and both are
the defect rather than a workaround: a task file documented `seldon cadence render spot_scan
--target bea` as if the command existed, and the project wrote its own renderer to call
`C.render` directly.

**A hand render is not a cadence firing, and the log says so.** `cadence_created` is a
schedule's assertion that a period was due and that nothing had served it yet (DN-006 decision
8). A person asking for a file is a different assertion and gets `cadence_rendered`, with the
actor, the template, the variables and the instance stem on it. Collapsing the two would make
`dispatch.cadence: []` indistinguishable in the log from a schedule that fired.

**Without `--write` this command touches nothing.** Rendering to stdout is the common case —
read it, then decide — and it is the one a `--dry-run` flag usually models badly by making the
destructive form the default.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click

from seldon.config import (
    get_current_session, get_neo4j_driver, load_project_config, resolve_cli_actor,
)
from seldon.core import cadence as C
from seldon.core.dispatch import DispatchConfigError, load_dispatch_config
from seldon.core.events import append_event, make_event
from seldon.domain.loader import load_domain_config

#: Where a rendered instance goes when the template is not a configured schedule's and there is
#: therefore no `instances_dir` to read. Overridable with `--out-dir`; it is the directory the
#: dispatcher's finish check already looks in for `<stem>_RESULT.md`, so a render that landed
#: anywhere else would produce a task whose RESULT nothing can find.
DEFAULT_INSTANCES_DIR = "cc_tasks"


def _utcnow() -> datetime:
    """The one clock seam, as `seldon.commands.dispatch` has: a test freezes it at a
    hand-checked instant rather than depending on what today happens to be."""
    return datetime.now(timezone.utc)


def _cfg(project_dir: Path):
    try:
        return load_dispatch_config(project_dir)
    except DispatchConfigError as exc:
        raise click.ClickException(str(exc)) from exc


def _entry(cfg: dict, name: str) -> dict:
    for entry in cfg.get("cadence") or []:
        if entry["name"] == name:
            return entry
    known = ", ".join(e["name"] for e in (cfg.get("cadence") or [])) or "(none configured)"
    raise click.ClickException(
        f"no cadence named {name!r} in seldon.yaml dispatch.cadence; configured: {known}. "
        f"To render a template that is not a schedule's, pass --template <path>.")


@click.group("cadence")
def cadence_group():
    """The schedules in `dispatch.cadence`, and rendering their templates on request."""


# ------------------------------------------------------------------------------------ list

@cadence_group.command("list")
def cadence_list():
    """Every configured schedule, evaluated against now. Writes nothing."""
    project_dir = Path.cwd()
    cfg = _cfg(project_dir)
    entries = cfg.get("cadence") or []
    if not entries:
        click.echo("dispatch.cadence is empty: no schedule is configured.")
        click.echo("A template can still be rendered on request: "
                   "seldon cadence render --template <path> --period <P> --cycle-name <N>")
        return
    now = _utcnow()
    for entry in entries:
        row = C.evaluate_entry(project_dir, entry, now)
        click.echo(f"{row['cadence']}  period {row['period']}  due_at {row['due_at']}")
        click.echo(f"  due: {row['due']}   before start_period "
                   f"({row['start_period']}): {row['before_start']}")
        click.echo(f"  template: {row['template']}")
        click.echo(f"  instance this period: {row['instance'] or '(none)'}")
        click.echo(f"  last_instance recorded: {row['last_instance'] or '(none)'}")
        click.echo(f"  next due: {', '.join(row['next_due'])}")


# ----------------------------------------------------------------------------------- check

@cadence_group.command("check")
def cadence_check():
    """Validate every schedule and its template. Exit 1 on anything that would fail at 00:00.

    `load_dispatch_config` already refuses a malformed rule, so what is left for this command
    is the half the config loader cannot see: the template file on disk, and the placeholders
    in it.
    """
    project_dir = Path.cwd()
    cfg = _cfg(project_dir)
    entries = cfg.get("cadence") or []
    if not entries:
        click.echo("dispatch.cadence is empty: nothing to check.")
        return
    bad = 0
    for entry in entries:
        path = project_dir / entry["template"]
        if not path.is_file():
            click.echo(f"FAIL {entry['name']}: template {entry['template']} does not exist",
                       err=True)
            bad += 1
            continue
        text = path.read_text(encoding="utf-8")
        try:
            declared = C.declared_vars(text)
        except C.CadenceRenderError as exc:
            click.echo(f"FAIL {entry['name']}: {exc}", err=True)
            bad += 1
            continue
        unknown = C.unknown_placeholders(text, declared)
        if unknown:
            click.echo(f"FAIL {entry['name']}: {entry['template']} names "
                       f"{', '.join(repr(u) for u in unknown)}, which nobody defines",
                       err=True)
            bad += 1
            continue
        click.echo(f"ok   {entry['name']}: {entry['template']}"
                   + (f"  declares {', '.join(declared)}" if declared else ""))
    if bad:
        raise SystemExit(1)


# ---------------------------------------------------------------------------------- render

@cadence_group.command("render")
@click.argument("cadence_name", required=False)
@click.option("--template", "template_path", default=None,
              help="Render a template that is not a configured schedule's. "
                   "Requires --period and --cycle-name, which a schedule's rule would supply.")
@click.option("--var", "variables", multiple=True, metavar="KEY=VALUE",
              help="A value for a placeholder the template DECLARES on its "
                   "`<!-- seldon:vars ... -->` line. Anything else is refused by name.")
@click.option("--period", default=None,
              help="Override the period the rule would compute (e.g. 2026-10).")
@click.option("--cycle-name", "cycle_name", default=None,
              help="Override the cycle name `cycle_name_format` would compute.")
@click.option("--out-dir", "out_dir", default=None,
              help=f"Where --write puts the instance. Default: the schedule's instances_dir, "
                   f"or {DEFAULT_INSTANCES_DIR}.")
@click.option("--write", is_flag=True, default=False,
              help="Write <out-dir>/<instance_stem>.md. Refuses to overwrite.")
@click.option("--register", "do_register", is_flag=True, default=False,
              help="Implies --write, then registers the instance through the same function "
                   "`seldon cc register` uses.")
def cadence_render(cadence_name, template_path, variables, period, cycle_name, out_dir,
                   write, do_register):
    """Render a cadence template because somebody asked, not because a period came due.

    With neither --write nor --register the rendered text goes to stdout and nothing on disk
    or in the graph changes.
    """
    project_dir = Path.cwd()
    if bool(cadence_name) == bool(template_path):
        raise click.ClickException(
            "give exactly one of <cadence-name> or --template <path>")

    supplied = dict(_parse_var(v) for v in variables)

    if cadence_name:
        cfg = _cfg(project_dir)
        entry = _entry(cfg, cadence_name)
        template = project_dir / entry["template"]
        instances_dir = out_dir or entry["instances_dir"]
    else:
        template = Path(template_path)
        if not template.is_absolute():
            template = project_dir / template
        # No schedule, so no rule and no `cycle_name_format` — the two values a rule would have
        # computed are REQUIRED rather than guessed. A default here would name a cycle after a
        # calendar nobody declared, and a dated measurement may not carry a date nobody chose.
        missing = [flag for flag, value in (("--period", period),
                                            ("--cycle-name", cycle_name)) if not value]
        if missing:
            raise click.ClickException(
                f"--template needs {' and '.join(missing)}: with no schedule there is no rule "
                f"to compute {'them' if len(missing) > 1 else 'it'} from")
        entry = {"name": template.stem, "instances_dir": out_dir or DEFAULT_INSTANCES_DIR}
        instances_dir = entry["instances_dir"]

    if not template.is_file():
        raise click.ClickException(f"template {template} does not exist")
    text = template.read_text(encoding="utf-8")

    now = _utcnow()
    period = period or C.period_of(entry["rule"], now)
    cycle_name = cycle_name or C.cycle_name_for(entry, now)
    stem = C.instance_stem(entry, period, now)
    created_at = now.isoformat().replace("+00:00", "Z")

    try:
        rendered = C.render_with_vars(
            text, variables=supplied, cycle_name=cycle_name, period=period,
            cadence_name=entry["name"], created_at=created_at, instance_stem=stem)
    except C.CadenceRenderError as exc:
        raise click.ClickException(str(exc)) from exc

    if not (write or do_register):
        click.echo(rendered, nl=False)
        return

    path = project_dir / instances_dir / f"{stem}.md"
    rel = str(path.relative_to(project_dir))
    if path.exists():
        if not do_register:
            raise click.ClickException(
                f"refusing to overwrite {rel}: a render for this stem already exists. "
                f"Delete it, or pass a different --period.")
        # `--register` on an existing instance is the idempotent case: nothing is rendered a
        # second time, and registration itself warns rather than creating a duplicate.
        click.echo(f"Warning: {rel} already exists; nothing rendered. "
                   f"Registering the file that is there.", err=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        _emit_rendered(project_dir, template, entry, period, cycle_name, stem, rel, supplied)
        click.echo(rel)

    if do_register:
        _register(project_dir, path, rel)


def _parse_var(raw: str) -> tuple:
    if "=" not in raw:
        raise click.ClickException(f"--var {raw!r} is not KEY=VALUE")
    key, value = raw.split("=", 1)
    key = key.strip()
    if not key:
        raise click.ClickException(f"--var {raw!r} names no variable")
    return key, value


def _emit_rendered(project_dir, template, entry, period, cycle_name, stem, rel, supplied):
    """One `cadence_rendered`, and only when a file was actually written.

    Never `cadence_created`: see this module's docstring. The actor is resolved the way
    `seldon issue create` resolves it — this command has no fixed caller.
    """
    try:
        rel_template = str(template.relative_to(project_dir))
    except ValueError:
        rel_template = str(template)
    append_event(project_dir, make_event(
        event_type=C.EVENT_CADENCE_RENDERED,
        actor=resolve_cli_actor(),
        authority="accepted",
        payload={"cadence": entry["name"], "template": rel_template, "period": period,
                 "cycle_name": cycle_name, "instance_stem": stem, "instance": rel,
                 "vars": supplied, "on_request": True},
        session_id=get_current_session(project_dir),
    ))


def _register(project_dir: Path, path: Path, rel: str):
    """Registration goes through `register_task_file` — the ONE code path `seldon cc register`,
    `seldon_cc_register` and the dispatcher's cadence already use. A second one would drift
    from every gate those apply."""
    from seldon.commands.cc import register_task_file

    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    domain_name = config["project"].get("domain", "research")
    domain_config = load_domain_config(
        Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml")
    try:
        outcome = register_task_file(
            project_dir=project_dir, config=config, driver=driver,
            database=config["neo4j"]["database"], domain_config=domain_config,
            session_id=get_current_session(project_dir), task_path=path,
            actor=resolve_cli_actor(), allow_untracked=True,
            emit=lambda msg: click.echo(msg, err=msg.startswith("Warning:")))
    except ValueError as exc:
        raise click.ClickException(
            f"{exc}\n  Fix: cite the AD or DN this task implements in the template.") from exc
    finally:
        driver.close()
    if outcome["warning"]:
        click.echo(outcome["warning"], err=True)
    return outcome
