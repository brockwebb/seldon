"""`seldon qc`: in-process quality control for dispatched sessions (AD-037).

`seldon qc calibrate-judge` reads a calibration set and one judge's verdicts on it and writes one report with three
separate numbers: position bias (ABBA flip rate), test-retest reliability (replicate kappa) and self-preference (the
catch-rate difference between reference-text and generator-style plants), each with its interval and its n
(AD-037-R5; `seldon.core.qc`). A report missing any of them is refused as `calibration_incomplete` and nothing is
written. Zero model calls: the verdicts come from the judge's own run (QC-002).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import click

from seldon import models as M
from seldon.core import qc


@click.group("qc")
def qc_group():
    """In-process quality control for dispatched sessions (AD-037)."""


@qc_group.command("calibrate-judge")
@click.option("--verdicts", "verdicts_path", required=True,
              help="JSONL: one row per reading, {item, half: generator|reference, order: AB|BA, replicate, verdict}.")
@click.option("--judge", "judge_role", required=True, help="The judge's role in models/registry.yaml (or `checker`).")
@click.option("--generator", "generator_role", required=True,
              help="The role whose work the judge reads; the generator-style plants are in its style.")
@click.option("--set", "set_path", default=None, help="The calibration set (default: the registry's calibration.set).")
@click.option("--out", "out_path", default=None,
              help="Where to write the report (default: the registry's calibration.report_dir, keyed by both ids).")
def calibrate_judge_command(verdicts_path, judge_role, generator_role, set_path, out_path):
    """Write a judge's calibration report: position bias, test-retest reliability and self-preference."""
    home = M.models_home()
    cfg = M.load_registry(home)["calibration"]
    judge = M.resolve(judge_role, home, generator=generator_role if judge_role == M.CHECKER_ROLE else None)
    generator = M.resolve(generator_role, home)
    set_file = Path(set_path) if set_path else home / cfg["set"]
    try:
        items = qc.load_set(set_file)
        report = qc.calibrate(items, qc.load_verdicts(verdicts_path), cfg)
    except qc.CalibrationIncomplete as exc:
        click.echo(f"REFUSED: {exc}", err=True)
        raise SystemExit(2)
    except qc.CalibrationSetError as exc:
        click.echo(f"FATAL: {exc}", err=True)
        raise SystemExit(1)
    report.update({"judge": {"role": judge_role, "model": judge}, "generator": {"role": generator_role,
                                                                              "model": generator},
                   "set": {"path": str(set_file), "sha256": qc.sha256_file(set_file), "items": len(items)},
                   "verdicts": {"path": str(verdicts_path), "sha256": qc.sha256_file(verdicts_path)},
                   "computed_utc": datetime.now(timezone.utc).isoformat()})
    out = Path(out_path) if out_path else qc.report_path(home, judge, generator)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    sp = report["self_preference"]
    click.echo(f"position bias {report['position_bias']['estimate']:.3f} (n {report['position_bias']['n']}); "
               f"replicate kappa {report['test_retest']['kappa']:.3f} (n {report['test_retest']['n']}); "
               f"self-preference {sp['difference']['estimate']:+.3f} (generator catch {sp['generator']['estimate']:.3f}"
               f", n {sp['generator']['n']}; reference {sp['reference']['estimate']:.3f}, n {sp['reference']['n']}); "
               f"passes the bar: {report['passes']}")
    click.echo(f"report -> {out}")


@qc_group.command("chart")
@click.option("--json", "as_json", is_flag=True, help="machine-readable")
def chart_command(as_json):
    """AD-037-R8: station outcomes per project, from this project's event store plus the seed (`qc.chart_seed`).

    Premise-false rate, first-article reject rate, milestone defect rate, CPI per task and huddles per task. A
    first reading is reported, not gated; FC-15's individuals chart is drawn from `qc.chart_min_points` tasks on."""
    from seldon.config import load_project_config
    from seldon.core import stations as S
    from seldon.core.events import read_events

    project_dir = Path.cwd()
    config = load_project_config()
    qcfg = config.get("qc") or {}
    seed_rel = qcfg.get("chart_seed")
    seed = S.load_seed(project_dir / seed_rel) if seed_rel else []
    min_points = qcfg.get("chart_min_points")
    if not isinstance(min_points, int) or min_points < 2:
        raise click.ClickException(f"seldon.yaml qc.chart_min_points must be a whole number of at least 2, "
                                   f"got {min_points!r}")
    name = (config.get("project") or {}).get("name") or project_dir.resolve().name
    events = read_events(project_dir)
    out = S.chart(events, name, seed=seed, min_points=min_points)
    out["toil"] = _toil(project_dir, config, events)
    # DISP-001R Part B step 1: the spend ceiling's measured floor, as it stood each week.
    # A project with no `dispatch:` block launches nothing, so it has no floor to report.
    from seldon.core import dispatch as D
    dcfg = D.load_dispatch_config(project_dir, config) if config.get("dispatch") else None
    floor_window = S.load_stations_config(dcfg)["floor_launches"] if dcfg else None
    out["spend_floor"] = (S.floor_by_week(project_dir, events, dcfg["poll_interval_s"], floor_window)
                          if dcfg else [])
    if as_json:
        click.echo(json.dumps(out, indent=1, default=str))
        return

    def r(x):
        return f"{x['k']}/{x['n']}" + (f" = {x['rate']:.3f}" if x["rate"] is not None else " (no station run yet)")
    click.echo(f"qc chart ({out['project']} event store + seed {seed_rel}; first reading, not gated)")
    click.echo(f"  premise-false rate        : {r(out['premise_false_rate'])}")
    click.echo(f"  first-article reject rate : {r(out['first_article_reject_rate'])}")
    click.echo(f"  milestone defect rate     : {r(out['milestone_defect_rate'])}")
    click.echo(f"  huddles                   : {out['huddles']}")
    click.echo("  CPI per task (CPI = earned / actual; seed rows: estimate / actual):")
    click.echo(f"    {'task':10s} {'project':9s} {'source':9s} {'estimate':>10s} {'actual':>10s} {'act/est':>8s} "
               f"{'CPI':>7s} huddles")
    for t in out["tasks"]:
        est, act = t.get("estimate"), t.get("actual_tokens")
        ratio = t.get("ratio") if t.get("ratio") is not None else (round(act / est, 4) if est and act else None)
        fmt = (lambda v, w: f"{v:>{w},.0f}" if isinstance(v, (int, float)) else f"{'-':>{w}}")
        cpi = t.get("cpi")
        click.echo(f"    {t['task']:10s} {t['project']:9s} {t['source']:9s} {fmt(est, 10)} {fmt(act, 10)} "
                   f"{(f'{ratio:.2f}' if ratio is not None else '-'):>8s} "
                   f"{(f'{cpi:.3f}' if cpi is not None else '-'):>7s} {t.get('huddles', 0)}"
                   + ("  (actual is a lower bound)" if t.get("lower_bound") else ""))
    ind = out["individuals_chart"]
    if ind["drawn"]:
        click.echo(f"  individuals chart (CPI, n {ind['n']}): mean {ind['mean']}, limits [{ind['lnpl']}, {ind['unpl']}]")
    else:
        click.echo(f"  individuals chart: not drawn, {ind['n']} task(s) of the {ind['needs']} FC-15 requires")
    auto = [c for c in out["classifier"] if c["permission_mode"] == "auto"]
    click.echo(f"  classifier blocks per launch (FRICTION-002 Part D; {len(auto)} auto-mode launch(es) of "
               f"{len(out['classifier'])}):")
    for c in auto[-10:]:
        click.echo(f"    {c['task']:10s} {str(c['launched_at'])[:19]:19s} blocks {c['blocks']:>3d}"
                   + ("  BREAKER" if c["breaker"] else ""))
    t = out["toil"]
    click.echo("  toil per week (AD-038-R6; the target for every column is zero):")
    click.echo(f"    {'week':9s} {'machine-dirt':>12s} {'other-dirt':>10s} {'redrives':>8s} {'restarts':>8s} "
               f"{'re-issues':>9s} {'interventions':>13s}")
    for w in t["weeks"]:
        click.echo(f"    {w['week']:9s} {w['refused_machine_dirt']:>12d} {w['refused_other_dirt']:>10d} "
                   f"{w['redrives_by_operator']:>8d} {w['desktop_restarts']:>8d} {w['reissued_tasks']:>9d} "
                   f"{w['interventions']:>13d}")
    if not t["weeks"]:
        click.echo("    (no dispatcher log, stale log or intervention recorded yet)")
    click.echo("  spend-ceiling floor per week (DISP-001R; median tokens at the first inspection, last "
               f"{floor_window or '-'} finished launches):")
    for w in out["spend_floor"]:
        click.echo(f"    {w['week']:9s} {(f'{w["value"]:,}' if w['value'] is not None else '-'):>12s}  n {w['n']}")
    if not out["spend_floor"]:
        click.echo("    (no finished launch yet)" if dcfg else "    (no dispatch: block in seldon.yaml)")
    click.echo(f"    sources: {len(t['sources']['dispatch_logs'])} dispatcher log(s), stale log "
               f"{t['sources']['stale_log'] or '(none)'}, the event store")


def _toil(project_dir: Path, config: dict, events: list) -> dict:
    """AD-038-R6's toil reading (`seldon.core.toil`) from this project's configured sources."""
    from seldon.core import reconcile as R
    from seldon.core import toil as T

    rel = (((config.get("qc") or {}).get("toil") or {}).get("dispatch_log"))
    stale = (config.get("mcp") or {}).get("stale_log")
    return T.toil(events, T.dispatch_logs(project_dir, rel), R.governed_paths(project_dir, config),
                  project_dir / stale if stale else None)
