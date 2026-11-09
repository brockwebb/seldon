"""SEL-036 (AD-036-R21): the prior-art library arm searches a LIST of graphs, and a receipt names its graph.

Synthetic throughout: the graphs are stubs, the project is a scratch repository (tests/test_prior_art.py's `proj`).
What is pinned: `library.graph` as a list or a string; two graphs with one directory name refused; the receipt
grammar with and without `graph <name> |`; verification routed to the named graph (the first when none is named, so
every receipt written before R21 verifies as it did); an unknown graph `release_unavailable`; one graph that cannot
answer never failing the search of the others.
"""
from __future__ import annotations

import pytest

from seldon.core import prior_art as pa
from tests.test_prior_art import LIB_SHA, _note, proj  # noqa: F401  (proj is a fixture)

OTHER_SHA = "b" * 64


class Stub:
    """One graph's Library: answers with its own release and rows."""

    def __init__(self, name, sha, rows, fail=None):
        self.name, self.sha, self.rows, self.fail, self.calls = name, sha, list(rows), fail, []

    def search(self, query, k=None):
        self.calls.append(query)
        if self.fail:
            raise pa.PriorArtError(self.fail)
        return {"query": query, "graph": self.name, "release": f"{self.name}.json", "sha256": self.sha,
                "rows": self.rows, "hits": []}

    def search_release(self, query, release, sha256, k=None):
        raise pa.PriorArtError(f"{pa.RELEASE_UNAVAILABLE}: release {release} is not on disk")

    def resolve_superseded(self, rows, exclude_sha256=None):
        return {"missing": list(rows), "served": None, "unchecked": []}

    def close(self):
        pass


def _two(proj, tmp_name="seldon-biblio"):
    lib, bib = proj["tmp"] / "library", proj["tmp"] / tmp_name
    proj["config"]["prior_art"]["library"]["graph"] = [str(lib), str(bib)]
    return pa.settings(proj["dir"], proj["config"])


def _libraries(s, a: Stub, b: Stub) -> pa.Libraries:
    libs = pa.Libraries(s)
    libs.libs = {"library": a, "seldon-biblio": b}
    return libs


def test_library_graph_takes_a_list_and_names_each_graph_by_its_directory(proj):
    s = _two(proj)
    assert [n for n, _p in s.library_graphs] == ["library", "seldon-biblio"]
    assert s.library_graph == proj["tmp"] / "library"          # the first, as every reader before R21 saw it
    assert pa.Libraries(s).default == "library"


def test_a_single_graph_string_still_works(proj):
    s = pa.settings(proj["dir"], proj["config"])
    assert len(s.library_graphs) == 1 and s.library_graphs[0][1] == s.library_graph


def test_two_graphs_with_one_directory_name_are_refused(proj):
    proj["config"]["prior_art"]["library"]["graph"] = [str(proj["tmp"] / "a" / "g"), str(proj["tmp"] / "b" / "g")]
    with pytest.raises(pa.PriorArtError, match="one directory name"):
        pa.settings(proj["dir"], proj["config"])


def test_an_empty_list_is_refused(proj):
    proj["config"]["prior_art"]["library"]["graph"] = []
    with pytest.raises(pa.PriorArtError, match="non-empty list"):
        pa.settings(proj["dir"], proj["config"])


def test_the_receipt_grammar_takes_an_optional_graph(tmp_path):
    with_graph = (f'- library receipt: query "suspect link" | graph seldon-biblio | release x.json '
                  f'sha256:{LIB_SHA} | rows sw_requiem#meta')
    without = f'- library receipt: query "suspect link" | release x.json sha256:{LIB_SHA} | rows a#meta'
    note = tmp_path / "AD-099_x.md"
    note.write_text(f"# x\n\n## Prior art\n\n### External\n\n{with_graph}\n{without}\n\n### Internal\n")
    rs = pa.parse_note(note).subsections["External"]
    assert [(r.graph, r.release, r.rows, r.error) for r in rs] == [
        ("seldon-biblio", "x.json", ["sw_requiem#meta"], None), (None, "x.json", ["a#meta"], None)]


def test_a_printed_receipt_names_its_graph_and_parses_back(tmp_path):
    line = pa.Library.receipt({"query": "q", "graph": "seldon-biblio", "release": "r.json", "sha256": LIB_SHA,
                               "rows": ["e#meta"]})
    assert "| graph seldon-biblio | release r.json" in line
    note = tmp_path / "AD-099_x.md"
    note.write_text(f"# x\n\n## Prior art\n\n### External\n\n{line}\n\n### Internal\n")
    assert pa.parse_note(note).subsections["External"][0].graph == "seldon-biblio"


def test_verification_routes_each_receipt_to_the_graph_it_names(proj):
    s = _two(proj)
    a = Stub("library", LIB_SHA, ["lesson:x#p1:1:0-9"])
    b = Stub("seldon-biblio", OTHER_SHA, ["gotel1994traceability#meta"])
    body = ("# AD-099 a note\n\n## Prior art\n\n### External\n\n"
            f'- library receipt: query "q one" | release library.json sha256:{LIB_SHA} | rows lesson:x#p1:1:0-9\n'
            f'- library receipt: query "q two" | graph seldon-biblio | release seldon-biblio.json '
            f"sha256:{OTHER_SHA} | rows gotel1994traceability#meta\n\n### Internal\n\n"
            f'- internal receipt: query "unit of extraction" | repo sib@{proj["sha"]} '
            f"| hits docs/design/DN-001_unit.md:5\n")
    v = pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=_libraries(s, a, b))
    assert v.verdict == "pass", v.problems
    assert a.calls == ["q one"] and b.calls == ["q two"]


def test_a_receipt_naming_an_unlisted_graph_is_release_unavailable(proj):
    s = _two(proj)
    a, b = Stub("library", LIB_SHA, ["r#meta"]), Stub("seldon-biblio", OTHER_SHA, ["r#meta"])
    body = ("# AD-099 a note\n\n## Prior art\n\n### External\n\n"
            f'- library receipt: query "q" | graph nowhere | release n.json sha256:{LIB_SHA} | rows r#meta\n\n'
            f"### Internal\n\n"
            f'- internal receipt: query "unit of extraction" | repo sib@{proj["sha"]} '
            f"| hits docs/design/DN-001_unit.md:5\n")
    v = pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=_libraries(s, a, b))
    r = v.receipts[0]
    assert (v.verdict, r.status) == ("fail", pa.RELEASE_UNAVAILABLE) and "nowhere" in r.detail
    assert a.calls == [] and b.calls == []


def test_one_graph_that_cannot_answer_does_not_fail_the_search_of_the_others(proj):
    s = _two(proj)
    a = Stub("library", LIB_SHA, ["r#meta"])
    b = Stub("seldon-biblio", OTHER_SHA, [], fail=f"{pa.RELEASE_UNAVAILABLE}: no served index")
    out = _libraries(s, a, b).search("q")
    assert [r["graph"] for r in out] == ["library", "seldon-biblio"]
    assert out[0]["rows"] == ["r#meta"] and "no served index" in out[1]["error"]


def test_a_graph_with_no_served_export_is_a_prior_art_error_not_an_exit(proj, monkeypatch):
    """squiddy's verbs stop with SystemExit("FATAL: no served export") on a graph not yet released (a fresh graph, a
    checkout the release was not cut in); the arm reports that graph unavailable instead of ending the process."""
    s = _two(proj)
    lib = pa.Library(s, proj["tmp"] / "seldon-biblio", "seldon-biblio")

    class Verbs:
        def search(self, q, k=None):
            raise SystemExit("FATAL: no served export")

    monkeypatch.setattr(lib, "verbs", lambda: Verbs())
    with pytest.raises(pa.PriorArtError, match="no served index"):
        lib.search("q")
