"""SEL-039 (AD-036 ADDENDUM 14, R25-R27): the library arm searches the project's own graphs first, and a project that
takes its prior-art block by reference does not inherit the referenced project's bibliography.

Synthetic throughout. Four scratch repositories laid out as siblings, the way the operator's repositories sit under
~/GitHub:

- `seldon/`  the definer: its block lists `../squiddy/graphs/library` and its own `graphs/seldon-biblio`;
- `squiddy/` holds the shared library graph;
- `hazbrief/` a consumer by reference (`ref: ../seldon/seldon.yaml#prior_art`) with its own served graph
  `graphs/hazbrief-corpus`;
- `other/`   a third project with a graph nobody lists.

A graph is a directory with a `graph.yaml`. Whether its export and its index are served is read through
`pa.served_export_reason` and `pa.index_reason`, which the tests replace with marker files (`SERVED`, `INDEXED`), so no
squiddy graph is built. The library arm itself is replaced by `StubLibrary`, which answers with rows named after the
graph it was built for: what is pinned is WHICH graphs are searched, in WHAT order, and where each receipt is verified.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from seldon.commands import prior_art as cmd
from seldon.core import prior_art as pa

SHA = {"library": "1" * 64, "seldon-biblio": "2" * 64, "hazbrief-corpus": "3" * 64, "other/othergraph": "4" * 64,
       "second": "5" * 64}


def _git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


def _repo(root: Path, files: dict) -> str:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return _git(root, "rev-parse", "HEAD")


def _graph(repo: Path, name: str, served: bool = True, indexed: bool = True) -> Path:
    g = repo / "graphs" / name
    g.mkdir(parents=True, exist_ok=True)
    (g / "graph.yaml").write_text(f"name: {name}\n")
    if served:
        (g / "SERVED").write_text("")
    if indexed:
        (g / "INDEXED").write_text("")
    return g


DEFINITION = {
    "log": "state/q.jsonl",
    "internal_roots": [{"name": "seldon", "path": "."}],
    "internal": {"default_include": ["docs/design/**"], "suffixes": [".md"], "top_n": 20,
                 "max_file_bytes": 100000, "bm25": {"k1": 1.2, "b": 0.75}},
    "library": {"graph": ["../squiddy/graphs/library", "graphs/seldon-biblio"], "k": 20},
    "gate": {"design_dir": "docs/design", "baseline": "docs/design/AD-036_baseline.txt",
             "exempt_globs": ["*_ADDENDUM_*.md"], "verdict_ledger_without_governed": "state/verdicts.jsonl"},
}
REF = {"ref": "../seldon/seldon.yaml#prior_art", "gate": {"baseline": "docs/design/AD-036_baseline.txt"}}


class StubLibrary:
    """Stands in for `pa.Library`: built the same two ways `Libraries` builds the real one."""

    built: list = []
    #: The receipt line is the real one: what a receipt says is under test.
    receipt = staticmethod(pa.Library.receipt)

    def __init__(self, s, graph=None, name=None):
        self.s = s
        self.path = Path(graph) if graph is not None else s.library_graph
        self.name = name or self.path.name
        self.calls = []
        StubLibrary.built.append(self)

    def search(self, query, k=None):
        self.calls.append(query)
        return {"query": query, "graph": self.name, "release": f"{self.name.replace('/', '_')}.json",
                "sha256": SHA[self.name], "rows": [f"{self.name}#row1"],
                "hits": [{"doc_id": f"{self.name}-doc", "rows": [{"receipt": {"row_id": f"{self.name}#row1"},
                                                                  "text": f"text of {self.name}"}]}]}

    def search_release(self, query, release, sha256, k=None):
        raise pa.PriorArtError(f"{pa.RELEASE_UNAVAILABLE}: release {release} is not on disk")

    def resolve_superseded(self, rows, exclude_sha256=None):
        return {"missing": list(rows), "served": None, "unchecked": []}

    def close(self):
        pass


@pytest.fixture
def machine(tmp_path, monkeypatch):
    seldon = tmp_path / "seldon"
    _repo(seldon, {"seldon.yaml": yaml.safe_dump({"prior_art": DEFINITION}),
                   "docs/design/AD-036_baseline.txt": "\n"})
    _graph(seldon, "seldon-biblio")
    squiddy = tmp_path / "squiddy"
    _repo(squiddy, {"README.md": "x\n"})
    _graph(squiddy, "library")
    hazbrief = tmp_path / "hazbrief"
    _repo(hazbrief, {"seldon.yaml": yaml.safe_dump({"project": {"name": "hazbrief"}, "prior_art": dict(REF)}),
                     "docs/design/AD-036_baseline.txt": "\n"})
    _graph(hazbrief, "hazbrief-corpus")
    other = tmp_path / "other"
    _repo(other, {"README.md": "x\n"})
    _graph(other, "othergraph")
    monkeypatch.setattr(pa, "served_export_reason",
                        lambda g: None if (Path(g) / "SERVED").is_file() else "no served export")
    monkeypatch.setattr(pa, "index_reason",
                        lambda g: None if (Path(g) / "INDEXED").is_file() else "no served index")
    StubLibrary.built = []
    monkeypatch.setattr(pa, "Library", StubLibrary)
    return {"tmp": tmp_path, "seldon": seldon, "squiddy": squiddy, "hazbrief": hazbrief, "other": other}


def _config(project: Path) -> dict:
    return yaml.safe_load((project / "seldon.yaml").read_text())


def _settings(project: Path, config: dict | None = None) -> pa.Settings:
    return pa.settings(project, config or _config(project))


def _plan(project: Path, config: dict | None = None) -> dict:
    return pa.library_plan(_settings(project, config))


def _searched(plan: dict) -> list:
    return [(g["name"], g["origin"]) for g in plan["search"]]


# --------------------------------------------------------------------------- R25: which graphs, in which order

def test_a_consumer_by_reference_searches_its_own_graph_first_then_the_shared_library_and_not_seldons_bibliography(
        machine):
    plan = _plan(machine["hazbrief"])
    assert _searched(plan) == [("hazbrief-corpus", "own"), ("library", "shared")]
    skipped = {g["name"]: g["why"] for g in plan["not_searched"]}
    assert "seldon-biblio" in skipped and "referenced project" in skipped["seldon-biblio"]


def test_seldons_own_search_still_returns_seldon_biblio_and_the_squiddy_library(machine):
    """seldon-biblio is seldon's own: it lies in seldon's repository, so for seldon it is an own graph, listed first
    and once, though seldon's list also names it."""
    plan = _plan(machine["seldon"])
    assert _searched(plan) == [("seldon-biblio", "own"), ("library", "shared")]
    assert plan["not_searched"] == []


def test_a_search_returns_own_rows_first_and_no_row_from_the_referenced_projects_bibliography(machine):
    out = cmd.run_search("library", "dense gas dispersion", project_dir=machine["hazbrief"])
    assert [g["graph"] for g in out["graphs"]] == ["hazbrief-corpus", "library"]
    assert [g["origin"] for g in out["graphs"]] == ["own", "shared"]
    assert out["top"][0]["doc_id"] == "hazbrief-corpus-doc"
    assert len(out["receipts"]) == 2
    assert "| graph hazbrief-corpus |" in out["receipts"][0] and "| graph library |" in out["receipts"][1]
    assert not any("seldon-biblio" in r for r in out["receipts"])
    assert [g["graph"] for g in out["not_searched"]] == ["seldon-biblio"]
    # The log line went to hazbrief's own log, and names each graph searched.
    lines = [json.loads(x) for x in (machine["hazbrief"] / "state" / "q.jsonl").read_text().splitlines()]
    assert [x["graph"] for x in lines] == ["hazbrief-corpus", "library"]


def test_seldons_search_receipts_name_seldon_biblio_and_the_library(machine):
    out = cmd.run_search("library", "suspect link", project_dir=machine["seldon"])
    assert [g["graph"] for g in out["graphs"]] == ["seldon-biblio", "library"]
    assert "| graph seldon-biblio |" in out["receipts"][0]


def test_a_graph_directory_without_a_served_export_is_not_searched_and_says_why(machine):
    _graph(machine["hazbrief"], "drafts", served=False)
    plan = _plan(machine["hazbrief"])
    assert ("drafts", "own") not in _searched(plan)
    assert {"name": "drafts", "why": "no served export"}.items() <= next(
        g for g in plan["not_searched"] if g["name"] == "drafts").items()


def test_own_graphs_declared_pins_the_choice_in_a_referencing_block(machine):
    _graph(machine["hazbrief"], "second")
    assert _searched(_plan(machine["hazbrief"]))[:2] == [("hazbrief-corpus", "own"), ("second", "own")]
    cfg = _config(machine["hazbrief"])
    cfg["prior_art"]["own_graphs"] = ["graphs/second"]
    assert _searched(_plan(machine["hazbrief"], cfg)) == [("second", "own"), ("library", "shared")]


def test_a_definers_own_graphs_are_never_inherited_by_reference(machine):
    seldon_cfg = _config(machine["seldon"])
    seldon_cfg["prior_art"]["own_graphs"] = ["graphs/seldon-biblio"]
    (machine["seldon"] / "seldon.yaml").write_text(yaml.safe_dump(seldon_cfg))
    assert _searched(_plan(machine["seldon"])) == [("seldon-biblio", "own"), ("library", "shared")]
    assert _searched(_plan(machine["hazbrief"])) == [("hazbrief-corpus", "own"), ("library", "shared")]


def test_a_referencing_block_may_set_own_graphs_and_still_nothing_else(machine):
    cfg = _config(machine["hazbrief"])
    cfg["prior_art"]["own_graphs"] = ["graphs/hazbrief-corpus"]
    assert _settings(machine["hazbrief"], cfg).own_graphs[0][0] == "hazbrief-corpus"
    cfg["prior_art"]["library"] = {"k": 5}
    with pytest.raises(pa.PriorArtError, match="may set only"):
        _settings(machine["hazbrief"], cfg)


def test_an_own_graph_and_a_shared_graph_with_one_name_and_two_paths_are_refused(machine):
    _graph(machine["hazbrief"], "library")
    with pytest.raises(pa.PriorArtError, match="one directory name"):
        _plan(machine["hazbrief"])


def test_a_project_whose_own_repository_holds_a_listed_graph_searches_it_once_as_its_own(machine):
    """squiddy takes the block by reference and owns the library seldon's list names: it is squiddy's own graph."""
    (machine["squiddy"] / "seldon.yaml").write_text(yaml.safe_dump({"prior_art": dict(REF)}))
    (machine["squiddy"] / "docs" / "design").mkdir(parents=True)
    (machine["squiddy"] / "docs" / "design" / "AD-036_baseline.txt").write_text("\n")
    assert _searched(_plan(machine["squiddy"])) == [("library", "own")]


# --------------------------------------------------------------------------- R26: receipts and named graphs

def _note(project: Path, body: str) -> Path:
    p = project / "docs" / "design" / "DN-900_x.md"
    p.write_text(body)
    return p


def _lib(graph: str | None, rows: str) -> str:
    g = f"graph {graph} | " if graph else ""
    name = graph or "library"
    return (f'- library receipt: query "q {name}" | {g}release {name.replace("/", "_")}.json sha256:{SHA[name]} '
            f"| rows {rows}\n")


def test_every_receipt_written_before_r25_still_verifies_in_the_graph_it_names(machine):
    """hazbrief's notes carry receipts naming `seldon-biblio` and `library`, and receipts naming none (AD-036-R21's
    default, the first graph listed). After R25 seldon-biblio is not searched for hazbrief, but a receipt naming it is
    still verified in it, and an unnamed receipt still in `library` (AD-036-R19: no receipt is re-recorded)."""
    body = ("# DN-900\n\n## Prior art\n\n### External\n\n"
            + _lib("seldon-biblio", "seldon-biblio#row1") + _lib("library", "library#row1")
            + _lib(None, "library#row1") + _lib("hazbrief-corpus", "hazbrief-corpus#row1")
            + "\n### Internal\n\n- internal receipt: query \"x\" | repo seldon@" + "0" * 40 + " | hits none\n")
    s = _settings(machine["hazbrief"])
    v = pa.verify_note(_note(machine["hazbrief"], body), s)
    lib = [r for r in v.receipts if r.kind == "library"]
    assert [r.status for r in lib] == [pa.PASS] * 4, [(r.graph, r.status, r.detail) for r in lib]
    by = {b.name: b.calls for b in StubLibrary.built}
    assert by["seldon-biblio"] == ["q seldon-biblio"]
    assert by["library"] == ["q library"]  # both the named and the unnamed receipt, one query each
    assert by["hazbrief-corpus"] == ["q hazbrief-corpus"]


def test_naming_the_referenced_projects_graph_on_the_call_searches_it_and_the_receipt_says_which(machine):
    out = cmd.run_search("library", "q", project_dir=machine["hazbrief"], graphs=("seldon-biblio",))
    assert [(g["graph"], g["origin"]) for g in out["graphs"]] == [("seldon-biblio", "named")]
    assert "| graph seldon-biblio |" in out["receipts"][0]


def test_naming_another_projects_graph_searches_it_and_its_receipt_names_the_repository(machine, tmp_path):
    out = cmd.run_search("library", "q", project_dir=machine["seldon"], graphs=("other/othergraph",))
    assert [(g["graph"], g["origin"]) for g in out["graphs"]] == [("other/othergraph", "named")]
    line = out["receipts"][0]
    assert "| graph other/othergraph |" in line
    built = [b for b in StubLibrary.built if b.name == "other/othergraph"][0]
    assert built.path == (machine["other"] / "graphs" / "othergraph").resolve()
    # The receipt parses back with its qualified graph and verifies there.
    body = ("# DN-900\n\n## Prior art\n\n### External\n\n" + line + "\n\n### Internal\n\n"
            "- internal receipt: query \"x\" | repo seldon@" + "0" * 40 + " | hits none\n")
    note = _note(machine["seldon"], body)
    r = pa.parse_note(note).subsections["External"][0]
    assert r.graph == "other/othergraph" and r.error is None
    v = pa.verify_note(note, _settings(machine["seldon"]))
    assert [x.status for x in v.receipts if x.kind == "library"] == [pa.PASS]


def test_a_qualified_name_naming_ones_own_graph_is_receipted_by_its_own_name(machine):
    out = cmd.run_search("library", "q", project_dir=machine["hazbrief"], graphs=("hazbrief/hazbrief-corpus",))
    assert "| graph hazbrief-corpus |" in out["receipts"][0]


@pytest.mark.parametrize("name", ["../othergraph", "other/..", "./x", "other/graphs/othergraph", "nowhere"])
def test_a_named_graph_that_does_not_resolve_is_refused_naming_it(machine, name):
    libs = pa.Libraries(_settings(machine["seldon"]))
    with pytest.raises(pa.PriorArtError, match="release_unavailable|not a graph name"):
        libs.for_graph(name)


# --------------------------------------------------------------------------- R27: the warning

def test_a_project_with_graphs_and_no_readable_own_graph_is_warned_naming_what_each_lacks(machine):
    for f in ("SERVED", "INDEXED"):
        (machine["hazbrief"] / "graphs" / "hazbrief-corpus" / f).unlink()
    notice = pa.own_graph_notice(machine["hazbrief"], _config(machine["hazbrief"]))
    assert notice and "hazbrief-corpus" in notice and "no served export" in notice
    (machine["hazbrief"] / "graphs" / "hazbrief-corpus" / "SERVED").write_text("")
    notice = pa.own_graph_notice(machine["hazbrief"], _config(machine["hazbrief"]))
    assert notice and "no served index" in notice


def test_no_notice_when_an_own_graph_is_readable_or_there_is_no_graph_directory(machine):
    assert pa.own_graph_notice(machine["hazbrief"], _config(machine["hazbrief"])) is None
    bare = machine["tmp"] / "bare"
    _repo(bare, {"seldon.yaml": yaml.safe_dump({"prior_art": dict(REF)}), "docs/design/AD-036_baseline.txt": "\n"})
    assert pa.own_graph_notice(bare, _config(bare)) is None
    assert pa.own_graph_notice(bare, {}) is None            # no prior_art block: not this gate's project


def test_verify_warns_and_never_fails(machine):
    from seldon.commands.verify import check_own_graphs
    assert check_own_graphs(machine["hazbrief"], _config(machine["hazbrief"])).symbol == "pass"
    (machine["hazbrief"] / "graphs" / "hazbrief-corpus" / "INDEXED").unlink()
    r = check_own_graphs(machine["hazbrief"], _config(machine["hazbrief"]))
    assert r.symbol == "warn" and r.name == "Prior-art own graphs"
    assert check_own_graphs(machine["hazbrief"], {}).symbol == "pass"


def test_go_shows_the_notice(machine, monkeypatch):
    from seldon.commands import go
    (machine["hazbrief"] / "graphs" / "hazbrief-corpus" / "INDEXED").unlink()
    section = go._get_own_graph_notice(str(machine["hazbrief"]))
    assert section and section.startswith("## Prior-art own graphs") and "hazbrief-corpus" in section
    (machine["hazbrief"] / "graphs" / "hazbrief-corpus" / "INDEXED").write_text("")
    assert go._get_own_graph_notice(str(machine["hazbrief"])) is None
