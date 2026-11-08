"""SEL-029 Part A (AD-036-R19, answering SEL-028): a library receipt whose release cannot be rebuilt verifies as
`pass (superseded)` when a release the library still carries holds every row it lists.

SEL-028: hazbrief-mcp's DN-019 carried a library receipt against release sha256 `7b72aaa89fe005d3`, which squiddy's
export register never carried (SQ-114/114R built and served the index over that export, then halted before the
`registers` and `seal` stages). Every touch of the note failed `release_unavailable`, although every row the receipt
lists is in the current release. These tests pin the rule:

* a receipt naming a release that is gone (no export on disk, no register row) passes superseded when the served
  release holds its rows, and its verdict line names the release it was verified against;
* with one row absent from every carried release it fails `release_unavailable`, and the detail names the missing row;
* a register release other than the served one is consulted, newest first, up to `library.superseded_releases`;
* the register is parsed in the kit's row format; the receipt in the note is never rewritten.

The squiddy side (the served index's rows, a register release's rebuilt rows) is stubbed; the register and the exports
directory are scratch files.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from seldon.core import prior_art as pa
from tests.test_prior_art import _note, _repo, proj  # noqa: F401 (fixture)

SERVED_SHA = "b" * 64
OLD_SHA = "7" * 64                                     # the release the receipt names: no export, no register row
ROW_A = "lesson:2026-03-17_arXiv_2601_04748#p18:376:2399-2513"
ROW_B = "lesson:2026-04-13_arXiv_2507_15330#p9:148:1909-2363"
ROW_GONE = "lesson:2026-01-01_retracted#p1:1:0-10"


def _register(exports: Path, rows: list[tuple[str, str, str]]) -> Path:
    """An export register in the kit's format: one `| **version** | `file` | date | `sha16` | ... |` row each."""
    lines = ["# Library graph export versions", "", "| Version | File | Date | sha256 (first 16) | Nodes / edges | "
             "Contents |", "|---|---|---|---|---|---|"]
    for version, release, sha in rows:
        lines.append(f"| **{version}** | `{release}` | 2026-11-06 | `{sha[:16]}` | 1 / 1 | test row |")
    p = exports / pa.EXPORT_REGISTER
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class CarriedLibrary(pa.Library):
    """The real resolution with the squiddy side stubbed: the served search answers `SERVED_SHA` (for other queries
    than the receipt's), the served index holds `served_rows`, and the exports directory is a scratch folder."""

    def __init__(self, s, exports: Path, served_rows):
        super().__init__(s)
        self._exports = exports
        self._served = frozenset(served_rows)

    def search(self, query, k=None):
        return {"query": query, "release": "served.json", "sha256": SERVED_SHA, "rows": [], "hits": []}

    def exports_dir(self) -> Path:
        return self._exports

    def graph(self):
        return object()          # only `release_row_ids` (stubbed per test) receives it

    def served_rows(self) -> dict:
        return {"release": "served.json", "sha256": SERVED_SHA, "rows": self._served}


def _exports(proj) -> Path:
    d = proj["tmp"] / "exports"
    d.mkdir(exist_ok=True)
    return d


def _body(rows: str, proj, sha=OLD_SHA, release="library_graph_20261105_sq114_a_2026-11-05.json") -> str:
    return (f"# AD-099 a note\n\n## Prior art\n\n### External\n\n"
            f'- library receipt: query "situation awareness display design" | release {release} sha256:{sha} '
            f"| rows {rows}\n\n### Internal\n\n"
            f'- internal receipt: query "unit of extraction" | repo sib@{proj["sha"]} '
            f"| hits docs/design/DN-001_unit.md:5\n")


def _lib(v):
    (r,) = [r for r in v.receipts if r.kind == "library"]
    return r


def test_a_receipt_against_a_removed_release_passes_superseded_when_the_served_release_holds_its_rows(proj):
    s = pa.settings(proj["dir"], proj["config"])
    exports = _exports(proj)
    _register(exports, [("20261106_sq125_c", "served.json", SERVED_SHA)])
    note = _note(proj, "AD-099_x.md", _body(f"{ROW_A}, {ROW_B}", proj))
    before = note.read_bytes()
    v = pa.verify_note(note, s, library=CarriedLibrary(s, exports, [ROW_A, ROW_B, "lesson:other#p1:1:0-1"]))
    r = _lib(v)
    assert r.status == pa.SUPERSEDED == "pass (superseded)"
    assert r.verified_against == {"release": "served.json", "sha256": SERVED_SHA}
    assert "served.json" in r.detail and "is not on disk" in r.detail, "names the release and why the named one failed"
    assert v.verdict == "pass", v.problems
    payload = v.as_payload()
    (lr,) = [x for x in payload["receipts"] if x["kind"] == "library"]
    assert lr["verified_against"]["release"] == "served.json", "the ledger carries the resolution"
    assert note.read_bytes() == before, "a superseded receipt is not rewritten in the note"


def test_a_row_absent_from_every_carried_release_fails_and_the_missing_row_is_named(proj):
    s = pa.settings(proj["dir"], proj["config"])
    exports = _exports(proj)
    _register(exports, [("20261106_sq125_c", "served.json", SERVED_SHA)])
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body(f"{ROW_A}, {ROW_GONE}", proj)), s,
                       library=CarriedLibrary(s, exports, [ROW_A, ROW_B]))
    r = _lib(v)
    assert r.status == pa.RELEASE_UNAVAILABLE
    assert f"rows missing from the current release served.json: {ROW_GONE}" in r.detail
    assert ROW_A not in r.detail.split("missing from the current release")[1]
    assert r.verified_against is None
    assert v.verdict == "fail"


def test_rows_match_on_the_full_row_id_not_the_document(proj):
    """The index rule puts nothing release-specific in a row id, so another passage of the same document is not the
    receipt's row."""
    s = pa.settings(proj["dir"], proj["config"])
    exports = _exports(proj)
    _register(exports, [("20261106_sq125_c", "served.json", SERVED_SHA)])
    moved = ROW_A.replace("2399-2513", "2400-2513")
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body(ROW_A, proj)), s,
                       library=CarriedLibrary(s, exports, [moved]))
    assert _lib(v).status == pa.RELEASE_UNAVAILABLE


def _carried_export(exports: Path, name: str) -> str:
    data = f'{{"release": "{name}"}}'.encode()
    (exports / name).write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def test_a_register_release_besides_the_served_one_is_consulted_newest_first(proj, monkeypatch):
    s = pa.settings(proj["dir"], proj["config"])
    exports = _exports(proj)
    mid = _carried_export(exports, "mid.json")
    older = _carried_export(exports, "older.json")
    _register(exports, [("older", "older.json", older), ("mid", "mid.json", mid),
                        ("20261106_sq125_c", "served.json", SERVED_SHA)])
    rebuilt = []

    def rows_of(graph, sha256):
        rebuilt.append(sha256)
        return frozenset({mid: [ROW_A, ROW_GONE], older: [ROW_A, ROW_GONE]}[sha256])

    monkeypatch.setattr(pa, "release_row_ids", rows_of)
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body(f"{ROW_A}, {ROW_GONE}", proj)), s,
                       library=CarriedLibrary(s, exports, [ROW_A]))
    r = _lib(v)
    assert r.status == pa.SUPERSEDED
    assert r.verified_against == {"release": "mid.json", "sha256": mid}
    assert rebuilt == [mid], "newest first, and it stops at the first release that holds every row"


def test_superseded_releases_zero_consults_the_served_release_only(proj, monkeypatch):
    proj["config"]["prior_art"]["library"]["superseded_releases"] = 0
    s = pa.settings(proj["dir"], proj["config"])
    assert s.library_superseded_releases == 0
    exports = _exports(proj)
    mid = _carried_export(exports, "mid.json")
    _register(exports, [("mid", "mid.json", mid), ("20261106_sq125_c", "served.json", SERVED_SHA)])
    monkeypatch.setattr(pa, "release_row_ids", lambda g, sha: (_ for _ in ()).throw(AssertionError("rebuilt")))
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body(f"{ROW_A}, {ROW_GONE}", proj)), s,
                       library=CarriedLibrary(s, exports, [ROW_A]))
    assert _lib(v).status == pa.RELEASE_UNAVAILABLE


def test_a_carried_release_whose_export_moved_is_not_checked_and_says_why(proj, monkeypatch):
    s = pa.settings(proj["dir"], proj["config"])
    exports = _exports(proj)
    _carried_export(exports, "mid.json")
    _register(exports, [("mid", "mid.json", "c" * 64), ("20261106_sq125_c", "served.json", SERVED_SHA)])
    monkeypatch.setattr(pa, "release_row_ids", lambda g, sha: (_ for _ in ()).throw(AssertionError("rebuilt")))
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body(f"{ROW_A}, {ROW_GONE}", proj)), s,
                       library=CarriedLibrary(s, exports, [ROW_A]))
    r = _lib(v)
    assert r.status == pa.RELEASE_UNAVAILABLE
    assert "not checked: mid.json" in r.detail and "not the register's cccccccccccccccc" in r.detail


def test_a_receipt_that_found_nothing_is_not_resolved_as_superseded(proj):
    s = pa.settings(proj["dir"], proj["config"])
    exports = _exports(proj)
    _register(exports, [("20261106_sq125_c", "served.json", SERVED_SHA)])
    body = _body("none", proj) + "\nNo prior art was found for this.\n"
    v = pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=CarriedLibrary(s, exports, [ROW_A]))
    assert _lib(v).status == pa.RELEASE_UNAVAILABLE


def test_the_register_is_read_in_the_kits_row_format(tmp_path):
    p = tmp_path / pa.EXPORT_REGISTER
    p.write_text(
        "| Version | File | Date | sha256 (first 16) | Nodes / edges | Contents |\n|---|---|---|---|---|---|\n"
        "| **20261105_sq114_a.r1** | `library_graph_20261105_sq114_a.r1_2026-11-06.json` | 2026-11-06 | "
        "`79e52df405ff4536` | 168,422 / 216,669 | Claim 131,205 -> 131,204 (-1). |\n"
        "| **20261106_sq125_c** | `library_graph_20261106_sq125_c_2026-11-06.json` | 2026-11-06 | `bbd841d3b5ab8822` "
        "| 168,422 / 216,669 | squiddy build. |\n", encoding="utf-8")
    assert pa.register_rows(p) == [
        {"version": "20261105_sq114_a.r1", "release": "library_graph_20261105_sq114_a.r1_2026-11-06.json",
         "sha16": "79e52df405ff4536"},
        {"version": "20261106_sq125_c", "release": "library_graph_20261106_sq125_c_2026-11-06.json",
         "sha16": "bbd841d3b5ab8822"}]


def test_the_served_index_rows_are_read_from_its_database(tmp_path):
    db = tmp_path / "corpus.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE rows (rid INTEGER PRIMARY KEY, row_id TEXT UNIQUE NOT NULL, doc_id TEXT NOT NULL)")
    con.executemany("INSERT INTO rows (row_id, doc_id) VALUES (?, ?)", [(ROW_A, "a"), (ROW_B, "b")])
    con.commit()
    con.close()
    assert pa._db_row_ids(db) == frozenset({ROW_A, ROW_B})
