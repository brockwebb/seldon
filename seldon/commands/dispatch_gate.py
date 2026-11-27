"""SEL-055 (AD-034 ADDENDUM 13, R38, R39): the full suite runs on main on a schedule, and its red closes the merges that
can change a test.

`maybe_run` is called by the dispatcher's pass (`seldon.commands.dispatch._pass`) under the pass lease with no session in
flight. It asks `gate_plan.scheduled_due` whether the scheduled run is due (on an idle pass after `full_every_s`, on any
pass after `full_overdue_s`, or at once after a merge under a red main) and, if so, runs `run_scheduled`. `seldon gate
main` runs `run_scheduled` by hand.

`run_scheduled` checks out main's head, detached, at `dispatch.gate.scheduled_worktree` (fresh for each run, with
`dispatch.worktree_links` linked in, removed after), runs `dispatch.gate_command` there under `dispatch.gate_timeout_s`,
and writes one `gate_run` record with call site `scheduled`. A red run that opens a closure (the previous scheduled run
passed, or none is recorded) rings `dispatch.notify` once and opens one Issue (`main_red`); a pass that ends a closure
rings `notify` once (`main_green`). The merge round reads the closure from the records (`gate_plan.main_red`).

Prior art (the addendum's section 2): Google TAP's split of selection at submission and the whole suite on a batched
schedule (Memon et al. 2017, as squiddy DN-043 read it), and tree closure on a red continuous build.
"""
from __future__ import annotations

import fcntl
import shutil
from pathlib import Path

import click

from seldon.core import dispatch as D
from seldon.core import gate_plan as GP
from seldon.core import worktree as WT
from seldon.core.events import read_events

ACTOR = "dispatcher"
#: The notification outcomes R39 adds to `dispatch.notify`'s `SELDON_NOTIFY_OUTCOME`.
NOTIFY_MAIN_RED, NOTIFY_MAIN_GREEN = "main_red", "main_green"
#: The Issue type a red scheduled run opens (R39).
ISSUE_MAIN_RED = "main_red"
#: How many failed files a notification and an Issue name (the record holds them all).
NAMED_FILES_CAP = 10


class ScheduledBusy(RuntimeError):
    """Another scheduled run holds this project's scheduled-worktree lock."""


def _lock_path(wt: Path) -> Path:
    return wt.parent / f"{wt.name}.lock"


def _clear(project_dir: Path, wt: Path) -> None:
    """Remove a scheduled checkout a killed run left: as a worktree first, then the directory itself (it is this
    module's own scratch path, never a task's), then git's record of it."""
    if wt.exists() or wt.is_symlink():
        WT.remove(project_dir, wt)
    if wt.exists():
        shutil.rmtree(wt)
    WT.git(project_dir, "worktree", "prune")


def run_scheduled(project_dir: Path, cfg: dict, why: str, *, session_id: str | None = None, driver=None,
                  database=None, domain_config=None, actor: str = ACTOR) -> dict:
    """Run the full gate on main's head (R38) and record it. Returns `{ok, outcome, seconds, gate_run, commit,
    failed_files, opened, closed, issue}`. Raises `ScheduledBusy` when another run holds the lock and
    `GP.GateConfigError` when the project has no gate command or main cannot be checked out."""
    from seldon.commands import dispatch as S
    from seldon.commands import dispatch_worktree as W

    project_dir = Path(project_dir)
    gcfg = cfg.get(GP.CONFIG_KEY) or GP.load_gate_config(None, cfg.get("gate_command"))
    if not cfg.get("gate_command"):
        raise GP.GateConfigError("the scheduled run needs dispatch.gate_command, the full tier")
    wt = D.config_path(project_dir, gcfg["scheduled_worktree"])
    wt.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(wt).open("a")
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ScheduledBusy(f"a scheduled run holds {_lock_path(wt)}") from exc
        main_sha = WT.rev(project_dir, cfg["branch"])
        if not main_sha:
            raise GP.GateConfigError(f"no commit for branch {cfg['branch']!r} in {project_dir}")
        _clear(project_dir, wt)
        r = WT.git(project_dir, "worktree", "add", "-q", "--detach", str(wt), main_sha)
        if r.returncode != 0:
            raise GP.GateConfigError(f"git worktree add --detach {wt} {main_sha[:12]} failed: "
                                     f"{(r.stderr or r.stdout).strip()}")
        try:
            WT.link(project_dir, wt, list(cfg.get("worktree_links") or []))
            plan = GP.scheduled_plan(wt, gcfg, why, cfg["branch"])
            log = D.config_path(project_dir, cfg["log_dir"]) / "scheduled.gate.log"
            click.echo(f"scheduled gate: running the full gate on {cfg['branch']} {main_sha[:12]} ({why}); output "
                       f"{D.config_rel(project_dir, log)} (AD-034-R38)")
            with W._gate_phase(project_dir, cfg, GP.CALL_SITE_SCHEDULED, log, None):
                result = GP.run(wt, plan, gcfg, gate_command=cfg["gate_command"], timeout_s=cfg["gate_timeout_s"],
                                log_path=log, primary=project_dir)
        finally:
            _clear(project_dir, wt)
        events = read_events(project_dir)
        was_red = GP.main_red(events)
        payload = GP.record_payload(plan, result, call_site=GP.CALL_SITE_SCHEDULED, events=events,
                                    branch=cfg["branch"], log_rel=D.config_rel(project_dir, log))
        ev = GP.emit(project_dir, payload, actor=actor, session_id=session_id)
    finally:
        lock.close()
    out = {"ok": result["ok"], "outcome": result["outcome"], "seconds": result["seconds"],
           "gate_run": ev["event_id"], "commit": main_sha, "failed_files": result["failed_files"],
           "opened": False, "closed": False, "issue": None}
    files = result["failed_files"]
    named = ", ".join(files[:NAMED_FILES_CAP]) + (f" (+{len(files) - NAMED_FILES_CAP} more)"
                                                   if len(files) > NAMED_FILES_CAP else "")
    click.echo(f"scheduled gate: {result['outcome']} in {result['seconds']:.0f} s on {main_sha[:12]} (record "
               f"{ev['event_id'][:8]}){': failed ' + named if files else ''}")
    if not result["ok"] and was_red is None:
        # R39: the closure opens. Once per red episode: a second red run while it holds rings nothing new.
        out["opened"] = True
        message = (f"main_red: the scheduled full gate on {cfg['branch']} {main_sha[:12]} is {result['outcome']}"
                   + (f" ({named})" if files else " and named no failed file")
                   + "; merges that can change a test are closed until a fix passes (AD-034-R39)")
        S._run_notifier(project_dir, session_id, cfg, {
            "SELDON_NOTIFY_TASK_ID": "", "SELDON_NOTIFY_TASK_NAME": "scheduled gate", "SELDON_NOTIFY_OK": "false",
            "SELDON_NOTIFY_OUTCOME": NOTIFY_MAIN_RED, "SELDON_NOTIFY_MESSAGE": message,
            "SELDON_NOTIFY_RESULT_PATH": "", "SELDON_NOTIFY_LOG_PATH": payload["log_path"] or "",
            "SELDON_NOTIFY_WALL_SECONDS": str(int(result.get("wall_seconds") or result["seconds"])),
        }, task_id="-", label=NOTIFY_MAIN_RED)
        if driver is not None:
            out["issue"] = _open_issue(project_dir, driver, database, domain_config, session_id, cfg, ev, payload,
                                       message)
    elif result["ok"] and was_red is not None:
        out["closed"] = True
        S._run_notifier(project_dir, session_id, cfg, {
            "SELDON_NOTIFY_TASK_ID": "", "SELDON_NOTIFY_TASK_NAME": "scheduled gate", "SELDON_NOTIFY_OK": "true",
            "SELDON_NOTIFY_OUTCOME": NOTIFY_MAIN_GREEN,
            "SELDON_NOTIFY_MESSAGE": f"main_green: the scheduled full gate on {cfg['branch']} {main_sha[:12]} passed; "
                                     f"the closure of {str(was_red.get('event_id'))[:8]} is lifted (AD-034-R39)",
            "SELDON_NOTIFY_RESULT_PATH": "", "SELDON_NOTIFY_LOG_PATH": payload["log_path"] or "",
            "SELDON_NOTIFY_WALL_SECONDS": str(int(result.get("wall_seconds") or result["seconds"])),
        }, task_id="-", label=NOTIFY_MAIN_GREEN)
    return out


def _open_issue(project_dir, driver, database, domain_config, session_id, cfg, ev, payload, message) -> str | None:
    """One `main_red` Issue per closure (R39). A graph that cannot be written is said on stderr; the record and the
    notification already carry the closure, and the merge round reads the record, not the Issue."""
    from seldon.core.artifacts import create_artifact
    try:
        return create_artifact(
            project_dir=project_dir, driver=driver, database=database, domain_config=domain_config,
            artifact_type="Issue",
            properties={"name": f"main_red: the scheduled full gate on {cfg['branch']} {payload['commit'][:12]}",
                        "description": message + f". Record {ev['event_id']}; log {payload['log_path']}. Every "
                                       "merge-round plan that selects a test also runs these files until a scheduled "
                                       "run passes or a branch merges on a passing full gate.",
                        "issue_type": ISSUE_MAIN_RED, "importance": "high", "urgency": "high",
                        "detection_method": "build_failure", "target": "content",
                        "files": payload["failed_files"], "gate_run": ev["event_id"]},
            actor=ACTOR, authority="accepted", session_id=session_id)
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed: the closure stands on the record
        click.echo(f"scheduled gate: could not open the main_red Issue: {type(exc).__name__}: {exc}", err=True)
        return None


def maybe_run(project_dir: Path, cfg: dict, *, idle: bool, session_id: str | None = None, driver=None,
              database=None, domain_config=None) -> dict | None:
    """The pass's call (R38): run the scheduled gate when `scheduled_due` says so, else None. Never raises: a run that
    cannot start is said on stderr and the pass goes on (the next pass asks again)."""
    gcfg = cfg.get(GP.CONFIG_KEY)
    if not GP.declared(gcfg) or not cfg.get("gate_command"):
        return None
    why = GP.scheduled_due(read_events(project_dir), gcfg, idle=idle)
    if why is None:
        return None
    try:
        return run_scheduled(project_dir, cfg, why, session_id=session_id, driver=driver, database=database,
                             domain_config=domain_config)
    except (ScheduledBusy, GP.GateConfigError) as exc:
        click.echo(f"scheduled gate: not run ({why}): {exc}", err=True)
        return None

