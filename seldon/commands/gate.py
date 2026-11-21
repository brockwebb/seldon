"""`seldon gate plan|run`: the project's gate, scoped to what the branch changed (SEL-041, AD-034-R29 to R37).

    seldon gate plan [--base main] [--full] [--json]   print the tier, the reason, the slices matched, the selected
                                                       tests and commands (reads only)
    seldon gate run  [--base main] [--full]            run them and write the `gate_run` record (R33); exit 0 on a
                                                       pass, 1 on a red or timed-out gate

Run from the checkout to gate (a task's worktree, or the primary). The record goes to the primary checkout's event
store, where the merge round reads it as evidence (R34). The full tier is `dispatch.gate_command`; `--full` asks for it
(R29). A project with no `dispatch.gate.slices` plans full (`no_slices`), as every gate ran before this addendum.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from seldon.config import load_project_config, resolve_cli_actor
from seldon.core import dispatch as D
from seldon.core import gate_plan as GP
from seldon.core import worktree as WT
from seldon.core.events import read_events


@click.group("gate")
def gate_group():
    """The project's gate: scoped to what a change touched, full at declared points (AD-034 ADDENDUM 12)."""


def _context(base: str | None, task: str | None, full: bool) -> dict:
    tree = Path.cwd().resolve()
    primary = WT.anchor(tree)
    config = load_project_config()
    if not config.get("dispatch"):
        raise click.ClickException("seldon.yaml has no `dispatch:` block: there is no gate_command to plan against")
    try:
        cfg = D.load_dispatch_config(tree, config)
    except D.DispatchConfigError as exc:
        raise click.ClickException(f"the dispatch block does not load: {exc}") from exc
    events = read_events(primary)
    task_id, source = None, None
    if task:
        hit = [e for e in events if e.get("event_type") == D.EVENT_LAUNCHED
               and task in ((e.get("payload") or {}).get("task_id") or "",
                            Path((e.get("payload") or {}).get("source_file") or "").stem)]
        if not hit:
            raise click.ClickException(f"no dispatch launch names task {task!r} in {primary}'s event store")
        lp = hit[-1]["payload"]
        task_id, source = lp["task_id"], lp.get("source_file")
    else:
        from seldon.core import stations as S
        launch = S.launch_for_session(events, os.environ.get("SELDON_SESSION_ID"))
        if launch is not None:
            task_id, source = launch["payload"]["task_id"], launch["payload"].get("source_file")
    text = None
    if source and (tree / source).is_file():
        text = (tree / source).read_text(encoding="utf-8", errors="surrogateescape")
    branch = WT.git(tree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or None
    gcfg = cfg[GP.CONFIG_KEY]
    try:
        plan = GP.plan(tree, gcfg, base=base or cfg["branch"], gate_command=cfg["gate_command"], events=events,
                       full=full, task_text=text, branch=branch, exclude=cfg.get("worktree_links") or ())
    except GP.GateConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    stem = Path(source).stem if source else (branch or "gate").replace("/", "_")
    return {"tree": tree, "primary": primary, "cfg": cfg, "gcfg": gcfg, "events": events, "plan": plan,
            "task_id": task_id, "branch": branch, "stem": stem}


def _print_plan(plan: dict) -> None:
    click.echo(f"gate plan against {plan['base']} (fork {str(plan['fork'])[:8]}, tree {str(plan['tree'])[:8]}"
               f"{', DIRTY' if plan['dirty'] else ''}): {GP.summary(plan)}")
    for r in plan["reasons"][1:]:
        click.echo(f"  also full: {r}")
    for name, paths in sorted(plan["slices"].items()):
        click.echo(f"  slice {name}: {len(paths)} path(s): {', '.join(paths[:5])}{' ...' if len(paths) > 5 else ''}")
    if plan["unmatched"]:
        click.echo(f"  unmatched: {', '.join(plan['unmatched'][:10])}")
    if plan["tier"] == GP.TIER_SCOPED:
        for t in plan["tests"]:
            click.echo(f"  test {t}")
        for m in plan["markers"]:
            click.echo(f"  marker {m}")
        for c in plan["commands"]:
            click.echo(f"  command {c}")
        always = plan["always"]
        if always["changed_tests"] or always["last_failed"]:
            click.echo(f"  always run (R31): changed {always['changed_tests']}, last failed {always['last_failed']}")


@gate_group.command("plan")
@click.option("--base", default=None, help="the branch the change is measured against (default: dispatch.branch)")
@click.option("--full", is_flag=True, help="ask for the full tier (AD-034-R29)")
@click.option("--task", default=None, help="task id or stem whose header may ask for the full tier")
@click.option("--json", "as_json", is_flag=True, help="the whole plan as JSON")
def plan_command(base, full, task, as_json):
    """Print what the gate would run for this checkout, and why. Reads only."""
    ctx = _context(base, task, full)
    if as_json:
        click.echo(GP.as_json(ctx["plan"]))
        return
    _print_plan(ctx["plan"])


@gate_group.command("run")
@click.option("--base", default=None, help="the branch the change is measured against (default: dispatch.branch)")
@click.option("--full", is_flag=True, help="run the full tier, `dispatch.gate_command` (AD-034-R29)")
@click.option("--task", default=None, help="task id or stem the record names (default: this session's launch)")
def run_command(base, full, task):
    """Run the plan and write its `gate_run` record to the primary's event store. Exit 0 pass, 1 red or timed out."""
    ctx = _context(base, task, full)
    plan, cfg = ctx["plan"], ctx["cfg"]
    _print_plan(plan)
    log = D.config_path(ctx["primary"], cfg["log_dir"]) / f"{ctx['stem']}.gate.log"
    try:
        result = GP.run(ctx["tree"], plan, ctx["gcfg"], gate_command=cfg["gate_command"],
                        timeout_s=cfg["gate_timeout_s"], log_path=log, primary=ctx["primary"])
    except GP.GateConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    payload = GP.record_payload(plan, result, call_site="cli", events=ctx["events"], task_id=ctx["task_id"],
                                branch=ctx["branch"], log_rel=D.config_rel(ctx["primary"], log))
    ev = GP.emit(ctx["primary"], payload, actor=resolve_cli_actor())
    click.echo(f"gate {plan['tier']} {result['outcome']} in {result['seconds']:.1f} s "
               f"(tests run {result['tests_run']}; record {ev['event_id'][:8]}; log {payload['log_path']})")
    if payload["escapes"]:
        click.echo(f"  ESCAPES (failed here, not selected by the last scoped gate on this change set): "
                   f"{', '.join(payload['escapes'])}")
    if not result["ok"]:
        if result["failed_files"]:
            click.echo(f"  failed: {', '.join(result['failed_files'])}")
        sys.exit(1)
