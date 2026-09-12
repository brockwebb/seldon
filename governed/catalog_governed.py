"""Catalog every governed markdown file as a manifest candidate (AD-030-R1, R5).

The manifest is the inventory control system: one entry per document ever considered, and nothing
enters the graph except through it. This script is the enumerator that fills it — it walks the four
governed directories the graph's `domain.governed_directories` declares and writes a candidates
file for `squiddy catalog`, which is the only writer of new manifest entries.

Nothing here decides admission. That is the assess stage's job, and its criterion for this graph is
`local_file_present`. A file that disappears between cataloging and assessment is declined with
that reason, which is how a relocation becomes a recorded decision instead of a silent gap.

    python governed/catalog_governed.py --graph governed --out governed/work/candidates.yaml
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import yaml

#: Files under a governed directory that are not governed documents. The parsed and resolved
#: caches live under the graph's own corpus directory, never under these, so nothing here is
#: about the pipeline's own output.
_SKIP_NAMES = {"README.md"}

#: A leading `YYYY-MM-DD_` prefix, stripped when deriving a title.
_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[_-]")

#: The first ATX H1 of a document, which is where a governed document states what it is.
_H1_RE = re.compile(r"^ {0,3}#[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)


def title_of(path: Path, text: str) -> str:
    """The document's own title, or one derived from its filename.

    Args:
        path: The file.
        text: Its content.

    Returns:
        The first H1's text, or the filename with its date prefix stripped and underscores
        turned into spaces.
    """
    match = _H1_RE.search(text)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return _DATE_PREFIX_RE.sub("", path.stem).replace("_", " ")


def governed_files(repo_root: Path, directories: list[dict]) -> list[tuple[Path, str]]:
    """Every governed markdown file, with the doc_kind its directory gives it.

    Args:
        repo_root: Repository root.
        directories: The `domain.governed_directories` list.

    Returns:
        `(path, doc_kind)` pairs, sorted by repo-relative path.
    """
    found: list[tuple[Path, str]] = []
    for entry in directories:
        base = repo_root / entry["path"]
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if path.name.startswith(".") or path.name in _SKIP_NAMES:
                continue
            found.append((path, entry["doc_kind"]))
    return sorted(found, key=lambda pair: str(pair[0]))


def candidate_for(path: Path, doc_kind: str, repo_root: Path, graph_root: Path) -> dict:
    """One candidate entry for a governed file.

    Args:
        path: The file.
        doc_kind: Its governed directory's doc_kind.
        repo_root: Repository root, which repo-relative paths are relative to.
        graph_root: The graph directory, which `local_path` is relative to.

    Returns:
        The candidate mapping `squiddy catalog` consumes.
    """
    from emit import doc_id_for  # the one place doc ids are derived

    rel = path.relative_to(repo_root).as_posix()
    text = path.read_text(encoding="utf-8")
    import os

    return {
        "id": doc_id_for(rel),
        "kind": "local_document",
        "disposition": "active",
        "title": title_of(path, text),
        # `source_url` carries the repo-relative path: it is the document's address, and the
        # manifest-to-ledger gate compares it, so a moved file shows up as a gate failure rather
        # than as a quietly re-keyed node.
        "source_url": rel,
        "local_path": os.path.relpath(path, graph_root),
        "doc_kind": doc_kind,
        "provenance_flag": "local_authored",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--graph", required=True, help="the graph directory (holds config.yaml)")
    parser.add_argument("--out", required=True, help="where to write the candidates file")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(Path(args.graph).resolve()))
    from squiddy.config import load_graph

    graph = load_graph(args.graph)
    repo_root = (graph.root / graph.domain.get("source_root", "..")).resolve()
    directories = graph.domain.get("governed_directories") or []
    if not directories:
        print("FATAL: domain.governed_directories is empty; nothing to catalog", file=sys.stderr)
        return 1

    files = governed_files(repo_root, directories)
    candidates = [candidate_for(path, kind, repo_root, graph.root) for path, kind in files]

    seen: dict[str, str] = {}
    for candidate in candidates:
        if candidate["id"] in seen:
            print(f"FATAL: two governed files derive the same document id {candidate['id']!r}: "
                  f"{seen[candidate['id']]} and {candidate['source_url']}", file=sys.stderr)
            return 1
        seen[candidate["id"]] = candidate["source_url"]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        yaml.safe_dump(
            {
                "recorded_decision": "AD-030-R1 (docs/design/AD-030_governed_documents_as_graph_content.md)",
                "banner": "AD-030-R1: every governed markdown file is a Document node.",
                "candidates": candidates,
            },
            sort_keys=False, allow_unicode=True, width=100,
        ),
        encoding="utf-8",
    )
    by_kind: dict[str, int] = {}
    for candidate in candidates:
        by_kind[candidate["doc_kind"]] = by_kind.get(candidate["doc_kind"], 0) + 1
    print(f"cataloged {len(candidates)} governed file(s) to {out}: "
          + ", ".join(f"{k} {v}" for k, v in sorted(by_kind.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
