"""DISP-c7 step 2: the prior-art verdict of every design note that carries receipts, per repository, as a TSV.

    python scripts/disp_c7/verdict_table.py --out <file.tsv> <repo dir> [<repo dir> ...]

Run once with the code before the change and once after it; equal files (equal sha256) mean the move of the query log
and the hit-path encoding changed no verdict. The run writes nothing to any repository: its query-log lines go to a
temporary file (the settings' `log` is replaced), and no verdict is recorded. Local files only; no model calls.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import sys
import tempfile
from pathlib import Path

from seldon.config import load_project_config
from seldon.core import prior_art as pa


def rows_for(repo: Path, log: Path) -> list[str]:
    config = load_project_config(repo)
    s = dataclasses.replace(pa.settings(repo, config), log=log)
    internal, library = pa.Internal(s), pa.Library(s)
    out = []
    for rel in pa.design_notes(s):
        note = repo / rel
        files = [note] + pa.addenda_of(note)
        if not any(pa.parse_note(f).has_section for f in files):
            continue
        v = pa.verify_note(note, s, internal=internal, library=library)
        statuses = ";".join(f"{r.kind}:{r.status}" for r in v.receipts)
        out.append("\t".join([repo.name, v.note, v.sha256, v.verdict, statuses]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("repos", nargs="+")
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        rows = []
        for r in a.repos:
            rows += rows_for(Path(r).resolve(), Path(tmp) / "q.jsonl")
    text = "repo\tnote\tsha256\tverdict\treceipts\n" + "\n".join(sorted(rows)) + "\n"
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"{len(rows)} note(s); sha256 {hashlib.sha256(text.encode()).hexdigest()}; {pa.__file__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
