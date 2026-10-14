"""DISP-c7 step 1: split seldon's prior-art query log by the repository whose document each line supports.

    python scripts/disp_c7/migrate_query_log.py --seldon <seldon checkout> --report <file.json> [--apply] <repo> ...

**Attribution rule.** A query-log line names what it ran (query, plus the corpus identity: an internal line's
`corpora` {root: commit}, a library line's release sha256), never who ran it. The receipt that a search produced, or
that a verify re-ran, carries the same query and identity and is pasted into a document. So a line is attributed to
the repository holding a receipt with its key: `("internal", query, root, commit)` or `("library", query, sha256)`.
- Held only in seldon, or in seldon and elsewhere: seldon's, it stays.
- Held by exactly one other repository: that repository's, it moves.
- Held by several other repositories: ambiguous, it stays.
- Held by none: unattributable, it stays.

Every receipt-bearing markdown file a repository tracks, or has untracked and not ignored, is scanned. A moved line
is appended to `<repo>/state/prior_art_queries.jsonl` with a `migrated` field naming its source, commit and basis;
seldon's log is rewritten without it. Without `--apply` nothing is written. Local files only; no model calls.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from seldon.core import prior_art as pa

LOG_REL = "state/prior_art_queries.jsonl"
TASK = "DISP-c7 (defca7cc)"


def md_files(repo: Path) -> list[Path]:
    out = []
    for args in (["ls-files", "-z", "--", "*.md"], ["ls-files", "-z", "-o", "--exclude-standard", "--", "*.md"]):
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
        out += [repo / p for p in r.stdout.decode().split("\0") if p]
    return [p for p in out if p.is_file()]


def receipt_keys(repo: Path) -> tuple[dict, int]:
    """`({key: [file:line, ...]}, receipts containing '%')` over every receipt line in the repository."""
    keys: dict = {}
    percent = 0
    for f in md_files(repo):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(lines, 1):
            m = pa._RECEIPT_START_RE.match(line)
            if not m or m.group(1).lower() == "web":
                continue
            r = pa._parse_receipt("Internal", m.group(1), m.group(2), n, str(f), line)
            if r.query is None:
                continue
            if "%" in line.split("| hits", 1)[-1] and r.kind == "internal":
                percent += 1
            key = (("internal", r.query, r.repo, r.commit) if r.kind == "internal"
                   else ("library", r.query, r.sha256))
            keys.setdefault(key, []).append(f"{f.relative_to(repo)}:{n}")
    return keys, percent


def line_keys(row: dict) -> set:
    if row.get("arm") == "library":
        return {("library", row.get("query"), row.get("sha256"))}
    return {("internal", row.get("query"), name, ident) for name, ident in (row.get("corpora") or {}).items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seldon", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("repos", nargs="+")
    a = ap.parse_args(argv)
    seldon = Path(a.seldon).resolve()
    repos = {Path(r).resolve().name: Path(r).resolve() for r in a.repos}
    repos["seldon"] = seldon
    index, percent = {}, {}
    for name, path in repos.items():
        index[name], percent[name] = receipt_keys(path)
    source = seldon / LOG_REL
    raw = source.read_text(encoding="utf-8").splitlines()
    head = subprocess.run(["git", "-C", str(seldon), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    keep, moves, tally, rows = [], {}, Counter(), []
    for n, text in enumerate(raw, 1):
        row = json.loads(text)
        keys = line_keys(row)
        holders = {name for name, idx in index.items() if keys & set(idx)}
        others = holders - {"seldon"}
        if "seldon" in holders:
            cls, target = "seldon", None
        elif len(others) == 1:
            (target,) = others
            cls = "moved"
        elif others:
            cls, target = "ambiguous", None
        else:
            cls, target = "unattributable", None
        tally[cls if cls != "moved" else f"moved:{target}"] += 1
        basis = sorted({w for name in holders for k in keys & set(index[name]) for w in index[name][k]})[:3]
        rows.append({"line": n, "class": cls, "target": target, "holders": sorted(holders), "basis": basis,
                     "ts": row.get("ts"), "arm": row.get("arm"), "purpose": row.get("purpose"),
                     "query": row.get("query")})
        if target:
            row["migrated"] = {"from": f"seldon:{LOG_REL}", "line": n, "at": head, "by": TASK,
                               "basis": f"{target}:{basis[0]}" if basis else None}
            moves.setdefault(target, []).append(json.dumps(row, sort_keys=True, default=str))
        else:
            keep.append(text)
    report = {"source": f"seldon:{LOG_REL}@{head}", "lines": len(raw), "tally": dict(sorted(tally.items())),
              "stays_in_seldon": len(keep), "moved": {k: len(v) for k, v in sorted(moves.items())},
              "percent_in_receipts": percent, "applied": a.apply, "rows": rows}
    Path(a.report).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
    if a.apply:
        for target, lines in moves.items():
            dest = repos[target] / LOG_REL
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        source.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
