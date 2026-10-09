"""`seldon prior-art`: search the prior art and verify a note's receipts (AD-036).

    seldon prior-art search --internal "<query>" [--root NAME ...] [--top N] [--json]
    seldon prior-art search --library "<query>" [--json]
    seldon prior-art verify docs/design/<note>.md [--no-record] [--json]

`search` prints receipts in AD-036-R1's form, ready to paste under `### Internal` or
`### External`; `verify` re-runs every receipt a note and its addenda carry and writes the verdict
to the governed ledger (R2, R4). The grammar and the matching rules are in
`seldon/core/prior_art.py`.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import click

from seldon.config import load_project_config
from seldon.core import prior_art as pa


def _settings() -> tuple[Path, dict, pa.Settings]:
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    try:
        return project_dir, config, pa.settings(project_dir, config)
    except pa.PriorArtError as exc:
        raise click.ClickException(str(exc))


def run_search(arm: str, query: str, roots: tuple = (), top: int | None = None,
               project_dir: Path | None = None, config: dict | None = None) -> dict:
    """One search, logged. Returns {receipts, hits, meta}; shared by the CLI and the MCP tool."""
    project_dir = Path(project_dir or Path.cwd())
    config = config if config is not None else load_project_config(project_dir)
    s = pa.settings(project_dir, config)
    started = time.monotonic()
    if arm == "internal":
        tool = pa.Internal(s)
        res = tool.search(query, roots or None)
        n = top or s.top_n
        out = {"arm": arm, "query": query, "receipts": tool.receipts(res, n),
               "corpora": res["corpora"], "total_hits": len(res["hits"]),
               "top": [{"root": h.root, "cite": h.cite(), "lines": f"{h.start}-{h.end}",
                        "score": h.score} for h in res["hits"][:n]]}
        pa.log_query(s, {"arm": "internal", "purpose": "search", "query": query,
                         "corpora": {k: v["identity"] for k, v in res["corpora"].items()},
                         "hits": len(res["hits"]),
                         "top": [f"{h.root}:{h.cite()}" for h in res["hits"][:n]]})
    elif arm == "library":
        tool = pa.Library(s)
        res = tool.search(query)
        out = {"arm": arm, "query": query, "receipts": [tool.receipt(res)],
               "release": res["release"], "sha256": res["sha256"], "total_hits": len(res["rows"]),
               "top": [{"doc_id": h["doc_id"], "rows": [r["receipt"]["row_id"] for r in h["rows"]],
                        "text": h["rows"][0]["text"][:200] if h["rows"] else ""}
                       for h in res["hits"]]}
        pa.log_query(s, {"arm": "library", "purpose": "search", "query": query,
                         "release": res["release"], "sha256": res["sha256"],
                         "rows": len(res["rows"])})
    else:
        raise pa.PriorArtError(f"unknown arm {arm!r}")
    out["seconds"] = round(time.monotonic() - started, 3)
    return out


def run_verify(note: str, record: bool = True, project_dir: Path | None = None,
               config: dict | None = None) -> dict:
    """Verify one note; record the verdict unless told not to. Shared by the CLI and MCP."""
    project_dir = Path(project_dir or Path.cwd())
    config = config if config is not None else load_project_config(project_dir)
    s = pa.settings(project_dir, config)
    path = Path(note)
    if not path.is_absolute():
        path = project_dir / path
    v = pa.verify_note(path, s)
    out = v.as_payload()
    if record:
        event = pa.record_verdict(v, project_dir, config)
        out["recorded"] = event["event_id"]
    return out


@click.group("prior-art")
def prior_art_group():
    """Search the prior art with receipts, and verify a design note's receipts (AD-036)."""


@prior_art_group.command("search")
@click.argument("query")
@click.option("--internal", "arm", flag_value="internal", help="The operator's own repositories.")
@click.option("--library", "arm", flag_value="library", help="The squiddy library graph.")
@click.option("--root", "roots", multiple=True, help="Internal arm: only these roots.")
@click.option("--top", type=int, default=None, help="Hits to print (default: config top_n).")
@click.option("--json", "as_json", is_flag=True, help="Print the full result as JSON.")
def search_command(query, arm, roots, top, as_json):
    """Run QUERY on one arm; print receipts to paste into a note's `## Prior art` section."""
    if arm is None:
        raise click.UsageError("choose --internal or --library")
    project_dir, config, _s = _settings()
    try:
        out = run_search(arm, query, roots, top, project_dir, config)
    except pa.PriorArtError as exc:
        raise click.ClickException(str(exc))
    if as_json:
        click.echo(json.dumps(out, indent=1, default=str))
        return
    click.echo(f"{arm} search: {query!r}  ({out['total_hits']} hit(s), {out['seconds']} s)")
    if arm == "internal":
        for name, meta in out["corpora"].items():
            note = f", {meta['untracked']} untracked read from disk" if meta["untracked"] else ""
            if meta["dirty_tracked"]:
                note += f", {meta['dirty_tracked']} modified file(s) read at the commit"
            if meta["skipped_large"]:
                note += f", {meta['skipped_large']} over the size bound skipped"
            click.echo(f"  {name}@{meta['identity'][:12]}: {meta['files']} file(s){note}")
        for h in out["top"]:
            click.echo(f"  {h['score']:>8.3f}  {h['root']}:{h['cite']}  (lines {h['lines']})")
    else:
        click.echo(f"  release {out['release']} sha256:{str(out['sha256'])[:12]}...")
        for h in out["top"]:
            click.echo(f"  {h['doc_id']}  {h['text'][:120]!r}")
    click.echo("\nReceipts:")
    for r in out["receipts"]:
        click.echo(r)


@prior_art_group.command("verify")
@click.argument("note")
@click.option("--no-record", is_flag=True, help="Do not write the verdict to the governed ledger.")
@click.option("--json", "as_json", is_flag=True, help="Print the verdict payload as JSON.")
def verify_command(note, no_record, as_json):
    """Re-run every receipt in NOTE and its addenda; exit 0 on pass, 2 on fail (AD-036-R2)."""
    project_dir, config, _s = _settings()
    try:
        out = run_verify(note, not no_record, project_dir, config)
    except pa.PriorArtError as exc:
        raise click.ClickException(str(exc))
    if as_json:
        click.echo(json.dumps(out, indent=1, default=str))
    else:
        click.echo(f"prior-art verify {out['note']} (sha256 {out['sha256'][:12]}): "
                   f"{out['verdict'].upper()}")
        for a in out["addenda"]:
            click.echo(f"  with addendum {a['path']}")
        for r in out["receipts"]:
            label = r.get("query") or r.get("url") or r.get("raw", "")[:60]
            click.echo(f"  {r['status']:<20} {r['section']:<8} {r['kind']:<8} "
                       f"{r['source']}:{r['line']}  {label!r}")
        for p in out["problems"]:
            click.echo(f"  PROBLEM: {p}")
        if out.get("recorded"):
            click.echo(f"  verdict recorded in the governed ledger: event {out['recorded']}")
    raise SystemExit(0 if out["verdict"] == "pass" else 2)
