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
    out = S.chart(read_events(project_dir), name, seed=seed, min_points=min_points)
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
