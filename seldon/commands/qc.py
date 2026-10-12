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
