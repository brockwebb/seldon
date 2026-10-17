"""`seldon prune`: the weekly prune of open artifacts (PRUNE-001).

The rules, their reasons and their config live in `seldon.core.prune`. This module is the I/O:
which repositories, which databases, the `prune_pass` record and the notification.

    seldon prune run [--repo PATH ...] [--dry-run]   # the lane's command (scripts/jobs/seldon_prune.sh)
    seldon prune redate TASK --reason TEXT [--project PATH]   # the hand step rule 2 cannot do
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from seldon.config import get_current_session, get_neo4j_driver, load_project_config, resolve_cli_actor
from seldon.core import prune as P
from seldon.core.events import append_event, make_event
from seldon.domain.loader import load_domain_config

#: Exit codes. 0: the run finished (whatever it found). 1: some unit failed and is a row in the
#: record. 2: config refused. 4: the token ceiling stopped the run (DN-042 R-178).
EXIT_UNIT_ERRORS, EXIT_CONFIG, EXIT_CEILING = 1, 2, 4


def _domain_config(config: dict):
    name = config["project"].get("domain", "research")
    return load_domain_config(Path(__file__).parent.parent / "domain" / f"{name}.yaml")


def _repositories(owner: Path, cfg: dict, only: tuple) -> list[Path]:
    """The configured repositories, resolved against the owner's root; `--repo` narrows them."""
    repos = [(owner / r).resolve() if not Path(r).is_absolute() else Path(r) for r in cfg["repositories"]]
    if only:
        wanted = {Path(o).resolve() for o in only}
        unknown = wanted - set(repos)
        if unknown:
            raise click.UsageError(f"--repo not in prune.repositories: {sorted(map(str, unknown))}")
        repos = [r for r in repos if r in wanted]
    return repos


def _notify(owner: Path, session_id: str, message: str) -> None:
    """The dispatcher's notify channel (`dispatch.notify`), one code path for every alarm.

    The STUCK alarm's reasoning applies: a second mechanism would be a second thing to configure
    and a second thing that can silently not exist.
    """
    from seldon.commands.dispatch import _run_notifier
    from seldon.core.dispatch import load_dispatch_config

    _run_notifier(owner, session_id, load_dispatch_config(owner), {
        "SELDON_NOTIFY_TASK_ID": "prune",
        "SELDON_NOTIFY_TASK_NAME": "weekly prune",
        "SELDON_NOTIFY_OK": "true",
        "SELDON_NOTIFY_OUTCOME": "prune",
        "SELDON_NOTIFY_MESSAGE": message,
        "SELDON_NOTIFY_RESULT_PATH": "",
        "SELDON_NOTIFY_LOG_PATH": "",
        "SELDON_NOTIFY_WALL_SECONDS": "0",
    }, task_id="prune", label="prune")


def run_prune(owner: Path, only: tuple = (), dry_run: bool = False, now: datetime | None = None,
              echo=click.echo, git_for=None) -> dict:
    """One run of the sweep over the configured repositories.

    Args:
        owner: The lane's owning project (its seldon.yaml carries `prune:`; its store gets the record).
        only: Repositories to narrow to (each must be configured).
        dry_run: Decide and print; write nothing, record nothing, notify nobody.
        now: The run's clock (tests pin it).
        echo: Line sink.
        git_for: `repo -> Git`, for tests.

    Returns:
        The `prune_pass` payload.

    Raises:
        PruneConfigError: On a missing or malformed `prune:` block.
    """
    owner = Path(owner).resolve()
    owner_cfg = yaml.safe_load((owner / "seldon.yaml").read_text(encoding="utf-8"))
    cfg = P.load_prune_config(owner_cfg)
    now = now or datetime.now(timezone.utc)
    session_id = get_current_session(owner)
    guard = P.SpendGuard(cfg["token_cap"], cfg["token_stop_factor"])
    results, stopped = [], None
    for repo in _repositories(owner, cfg, only):
        echo(f"prune: {repo.name}")
        config = load_project_config(repo)
        driver = get_neo4j_driver(config)
        try:
            results.append(P.prune_repository(
                repo, driver, config["neo4j"]["database"], _domain_config(config), cfg, now,
                dry_run, guard, session_id=session_id,
                git=git_for(repo) if git_for else None, echo=echo))
        except P.PruneCeiling as exc:
            stopped = str(exc)
            echo(f"prune: STOPPED: {exc}")
            break
        finally:
            driver.close()
        r = results[-1]
        echo(f"  {r['before']} -> {r['after']}; resolved {len(r['resolved'])}, re-dated "
             f"{len(r['redated'])}, withdrawn {len(r['withdrawn'])}, errors {len(r['errors'])}")
    payload = {"dry_run": dry_run, "run_at": now.isoformat().replace("+00:00", "Z"),
               "stale_days": cfg["stale_days"], "tokens_spent": guard.spent,
               "token_cap": cfg["token_cap"], "stopped": stopped,
               "actions": P.total_actions(results), "repositories": results}
    if dry_run:
        return payload
    append_event(owner, make_event(event_type=P.EVENT_PRUNE_PASS, actor=P.PRUNE_ACTOR,
                                   authority="accepted", payload=payload, session_id=session_id))
    if payload["actions"] or stopped:
        parts = [f"{Path(r['repo']).name}: {len(r['resolved'])} resolved, {len(r['redated'])} re-dated, "
                 f"{len(r['withdrawn'])} withdrawn" + (f", {len(r['errors'])} errors" if r["errors"] else "")
                 for r in results if r["resolved"] or r["redated"] or r["withdrawn"] or r["errors"]]
        _notify(owner, session_id, ("STOPPED: " + stopped + "; " if stopped else "") + "; ".join(parts))
    return payload


@click.group("prune")
def prune_group():
    """The weekly prune (PRUNE-001): close fixed issues, re-date or withdraw stale FUTURE proposals."""


@prune_group.command("run")
@click.option("--repo", "repos", multiple=True, help="Narrow to these configured repositories")
@click.option("--dry-run", is_flag=True, help="Decide and print; write nothing")
@click.option("--json-out", type=click.Path(dir_okay=False), default=None,
              help="Also write the run's record (the prune_pass payload) to this file")
def prune_run(repos, dry_run, json_out):
    """Run both rules over `prune.repositories` and write one `prune_pass` record.

    The record is written whatever the run found; the notification only when it changed
    something, failed a unit or hit the ceiling. Never deletes.
    """
    try:
        payload = run_prune(Path.cwd(), repos, dry_run)
    except P.PruneConfigError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(EXIT_CONFIG)
    if json_out:
        Path(json_out).write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    click.echo(f"prune: {payload['actions']} action(s){' (dry run)' if dry_run else ''}; "
               f"tokens {payload['tokens_spent']} of cap {payload['token_cap']}")
    if payload["stopped"]:
        raise SystemExit(EXIT_CEILING)
    if any(r["errors"] for r in payload["repositories"]):
        raise SystemExit(EXIT_UNIT_ERRORS)


@prune_group.command("redate")
@click.argument("task_id")
@click.option("--reason", required=True, help="One line: why the trigger is still plausible")
@click.option("--project", type=click.Path(file_okay=False, exists=True), default=None,
              help="The repository holding the task (default: the current directory)")
def prune_redate(task_id, reason, project):
    """Keep a FUTURE proposal alive for another `prune.stale_days`, with its reason (rule 2's hand step)."""
    from seldon.core.graph import get_artifact
    from seldon.core.moving import is_future

    repo = Path(project or Path.cwd()).resolve()
    config = load_project_config(repo)
    database = config["neo4j"]["database"]
    driver = get_neo4j_driver(config)
    try:
        from seldon.core.artifacts import resolve_artifact_id
        try:
            full_id = resolve_artifact_id(driver, database, task_id)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        with driver.session(database=database) as s:
            node = get_artifact(s, full_id)
        if node is None or node.get("artifact_type") != "ResearchTask":
            raise click.ClickException(f"no ResearchTask {task_id!r} in {database}")
        if node.get("state") != "proposed" or not is_future(node.get("description")):
            raise click.ClickException(f"{task_id[:8]} is not a proposed FUTURE task "
                                       f"(state {node.get('state')!r}); only those are re-dated")
        P.redate(repo, driver, database, node["artifact_id"], reason, datetime.now(timezone.utc),
                 get_current_session(repo), actor=resolve_cli_actor())
        click.echo(f"Re-dated {node['artifact_id'][:8]}: {reason}")
    finally:
        driver.close()
