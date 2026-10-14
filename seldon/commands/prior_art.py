"""`seldon prior-art`: search the prior art and verify a note's receipts (AD-036).

    seldon prior-art search --internal "<query>" [--root NAME ...] [--top N] [--note N] [--project DIR] [--json]
    seldon prior-art search --library "<query>" [--project DIR] [--json]
    seldon prior-art verify docs/design/<note>.md [--no-record] [--project DIR] [--json]

`search` prints receipts in AD-036-R1's form, ready to paste under `### Internal` or
`### External`; `verify` re-runs every receipt a note and its addenda carry and writes the verdict
to the governed ledger (R2, R4). The grammar and the matching rules are in
`seldon/core/prior_art.py`.

**Whose evidence a run is** (AD-036-R10, R11, ADDENDUM 04). A run's log lines and verdict go to the calling project:
`--project`, else the repository holding the note, else the project at or above the working directory. The run then
commits what it appended there, path-scoped and through the hooks, so a search never leaves a tracked file dirty.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import click

from seldon.config import load_project_config
from seldon.core import prior_art as pa


def _resolve(project: str | None, note: str | None, cwd: Path) -> tuple[Path, str | None]:
    """`(calling project, the note as an absolute path)`; see `pa.calling_project`."""
    project_dir = pa.calling_project(project, note, cwd)
    if note:
        n = Path(note).expanduser()
        if not n.is_absolute():
            n = (Path(project).expanduser().resolve() if project else Path(cwd).resolve()) / n
        note = str(n.resolve())
    return project_dir, note


def _commit(project_dir: Path, config: dict, before: dict, what: str) -> dict:
    outcome = pa.commit_appends(project_dir, config, before, f"record: prior-art {what} (AD-036-R11)")
    return {k: v for k, v in outcome.items() if k in ("committed", "reason", "commit", "committed_paths",
                                                       "skipped", "path", "stderr")}


def run_search(arm: str, query: str, roots: tuple = (), top: int | None = None,
               project_dir: Path | None = None, config: dict | None = None, note: str | None = None,
               cwd: Path | None = None) -> dict:
    """One search, logged in the calling project and committed there. Returns {receipts, hits, meta, commit}; shared
    by the CLI and the MCP tool. `note` is the note the receipts are for: the internal arm leaves it out (QC-001
    premise 3), and the log goes to its repository (AD-036-R10). `project_dir` is an explicit project; without one
    the note's repository, else the project at or above `cwd` (default: the working directory)."""
    project_dir, note = _resolve(project_dir, note, Path(cwd or Path.cwd()))
    config = config if config is not None else load_project_config(project_dir)
    s = pa.settings(project_dir, config)
    before = pa.append_state(project_dir, [s.log])
    started = time.monotonic()
    if arm == "internal":
        tool = pa.Internal(s)
        exclude = frozenset()
        if note:
            exclude = pa.note_keys(s, [Path(note)])
        res = tool.search(query, roots or None, exclude=exclude)
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
    out["project"] = str(project_dir)
    out["commit"] = _commit(project_dir, config, before, f"{arm} search {query!r}")
    return out


def run_verify(note: str, record: bool = True, project_dir: Path | None = None,
               config: dict | None = None, cwd: Path | None = None) -> dict:
    """Verify one note in its own repository (or `project_dir`), record the verdict unless told not to, and commit
    the log lines and the verdict there (AD-036-R10, R11). Shared by the CLI and MCP. A relative `note` is read
    against `project_dir` when one is given, else against `cwd`."""
    project_dir, path = _resolve(project_dir, note, Path(cwd or Path.cwd()))
    config = config if config is not None else load_project_config(project_dir)
    s = pa.settings(project_dir, config)
    before = pa.append_state(project_dir, pa.prior_art_paths(project_dir, config))
    v = pa.verify_note(Path(path), s)
    out = v.as_payload()
    if record:
        event = pa.record_verdict(v, project_dir, config)
        out["recorded"] = event["event_id"]
    out["project"] = str(project_dir)
    out["commit"] = _commit(project_dir, config, before, f"verify {v.note} ({v.verdict})")
    return out


def _report_commit(out: dict) -> None:
    """Say, on stderr, when the run's lines were left uncommitted, and why (AD-036-R11: never silently)."""
    c = out.get("commit") or {}
    if c.get("committed") or c.get("reason") in ("nothing_to_commit", "not_a_work_tree"):
        return
    detail = f" ({c['stderr']})" if c.get("stderr") else ""
    click.echo(f"prior-art: lines in {out.get('project')} NOT committed: {c.get('reason')}{detail}"
               + ("; the dispatcher's next pass commits them" if c.get("reason") == "lease_held" else ""), err=True)


@click.group("prior-art")
def prior_art_group():
    """Search the prior art with receipts, and verify a design note's receipts (AD-036)."""


@prior_art_group.command("search")
@click.argument("query")
@click.option("--internal", "arm", flag_value="internal", help="The operator's own repositories.")
@click.option("--library", "arm", flag_value="library", help="The squiddy library graph.")
@click.option("--root", "roots", multiple=True, help="Internal arm: only these roots.")
@click.option("--top", type=int, default=None, help="Hits to print (default: config top_n).")
@click.option("--note", default=None, help="Internal arm: the note these receipts are for; it is left out of the "
                                           "search (a note is not prior art for itself).")
@click.option("--project", "project", default=None,
              help="The project whose evidence this search is (default: the note's repository, else the project at "
                   "or above the working directory). Its log gets the line, and the commit (AD-036-R10).")
@click.option("--json", "as_json", is_flag=True, help="Print the full result as JSON.")
def search_command(query, arm, roots, top, note, project, as_json):
    """Run QUERY on one arm; print receipts to paste into a note's `## Prior art` section."""
    if arm is None:
        raise click.UsageError("choose --internal or --library")
    try:
        out = run_search(arm, query, roots, top, project, note=note)
    except (pa.PriorArtError, FileNotFoundError) as exc:
        raise click.ClickException(str(exc))
    _report_commit(out)
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
@click.option("--project", "project", default=None,
              help="The project the verdict and log lines go to (default: the repository holding NOTE).")
@click.option("--json", "as_json", is_flag=True, help="Print the verdict payload as JSON.")
def verify_command(note, no_record, project, as_json):
    """Re-run every receipt in NOTE and its addenda; exit 0 on pass, 2 on fail (AD-036-R2)."""
    try:
        out = run_verify(note, not no_record, project)
    except (pa.PriorArtError, FileNotFoundError) as exc:
        raise click.ClickException(str(exc))
    _report_commit(out)
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
