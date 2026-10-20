"""PA-002 (AD-036 ADDENDUM 06): a library receipt verifies against the release it names.

AD-036-R2/R3 made a receipt re-runnable against a named corpus identity. Until PA-002 the verifier compared every
library receipt with the release the index serves now, so a new release failed every earlier note as
`release_unavailable` although the named release was still on disk. These tests pin the rule:

* a receipt naming the served release runs the served index exactly as before (the current path, unchanged);
* a receipt naming another release that is on disk with the digest it names is re-run against THAT release, rebuilt
  from the library's own checkpoints, and passes or fails on top-k membership as before;
* only a release absent from disk (or whose bytes no longer hash to the receipt) is `release_unavailable`, and the
  finding names the path it looked for;
* the query log records the release each verification ran against.

The unit tests stub the squiddy side (the served search and the rebuilt index) and use a scratch exports directory
and a scratch git repository. The last test runs on the operator's real library when it is on disk: it rebuilds the
SERVED release through the older-release path and checks the rebuild reproduces the served index's rows and dense
shard set exactly, which is what makes a rebuilt older release the same instrument the receipt ran on.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from seldon.core import prior_art as pa
from tests.test_prior_art import _note, _repo, proj  # noqa: F401 (fixture)

SERVED_SHA = "a" * 64
SERVED_ROWS = ["lesson:served#p1:1:0-9"]
OLD_ROWS = ["lesson:old#p2:3:10-40", "lesson:old#p5:1:0-12"]


class FakeIndex:
    """A rebuilt release's index: answers every query with the rows it was built with."""

    def __init__(self, rows):
        self.rows, self.calls = list(rows), 0

    def search(self, query, k=None):
        self.calls += 1
        return {"hits": [{"rank": 1, "doc_id": "lesson:old",
                          "rows": [{"receipt": {"row_id": r}} for r in self.rows]}]}


class ExportsLibrary(pa.Library):
    """The real `Library` resolution with the squiddy side stubbed: the served search answers `SERVED_SHA`, the
    exports directory is a scratch folder, and a rebuild returns a `FakeIndex` (counted) instead of reading squiddy's
    checkpoints."""

    def __init__(self, s, exports: Path, old_rows=OLD_ROWS):
        super().__init__(s)
        self._exports = exports
        self.old_rows = old_rows
        self.served_calls = 0
        self.rebuilds = []

    def search(self, query, k=None):
        self.served_calls += 1
        return {"query": query, "release": "served.json", "sha256": SERVED_SHA, "rows": SERVED_ROWS, "hits": []}

    def exports_dir(self) -> Path:
        return self._exports

    def _rebuild(self, sha256, work):
        self.rebuilds.append(sha256)
        assert Path(work).is_dir()
        return FakeIndex(self.old_rows), {"commit": "c" * 40, "rows": 3}


def _exports(tmp: Path) -> tuple[Path, str]:
    d = tmp / "exports"
    d.mkdir(exist_ok=True)
    data = b'{"nodes": [], "links": [], "graph": {"release": "old"}}'
    (d / "old.json").write_bytes(data)
    return d, hashlib.sha256(data).hexdigest()


def _body(release: str, sha: str, rows: str, proj) -> str:
    return (f"# AD-099 a note\n\n## Prior art\n\n### External\n\n"
            f'- library receipt: query "unit of extraction" | release {release} sha256:{sha} | rows {rows}\n\n'
            f"### Internal\n\n"
            f'- internal receipt: query "unit of extraction" | repo sib@{proj["sha"]} '
            f"| hits docs/design/DN-001_unit.md:5\n")


def _lib_status(v):
    return [(r.status, r.detail) for r in v.receipts if r.kind == "library"]


def _log(s) -> list[dict]:
    return [json.loads(x) for x in s.log.read_text().splitlines() if x.strip()]


def test_a_receipt_naming_a_present_older_release_verifies(proj):
    s = pa.settings(proj["dir"], proj["config"])
    exports, sha = _exports(proj["tmp"])
    lib = ExportsLibrary(s, exports)
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body("old.json", sha, ", ".join(OLD_ROWS), proj)), s, library=lib)
    assert _lib_status(v) == [(pa.PASS, f"{len(OLD_ROWS)} row(s) returned")]
    assert v.verdict == "pass", v.problems
    assert lib.rebuilds == [sha]
    lines = [x for x in _log(s) if x.get("arm") == "library" and x.get("purpose") == "verify"]
    ran = [(x["release"], x["sha256"]) for x in lines]
    assert ("old.json", sha) in ran, "the query log names the release the verification ran against"
    old = next(x for x in lines if x["release"] == "old.json")
    assert old["index"] == "rebuilt" and old["export_path"] == str(exports / "old.json")


def test_an_older_release_still_fails_on_top_k_membership(proj):
    s = pa.settings(proj["dir"], proj["config"])
    exports, sha = _exports(proj["tmp"])
    lib = ExportsLibrary(s, exports, old_rows=["lesson:other#p1:1:0-1"])
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body("old.json", sha, OLD_ROWS[0], proj)), s, library=lib)
    assert [st for st, _d in _lib_status(v)] == [pa.ID_NOT_RETURNED]


def test_a_receipt_naming_an_absent_release_is_release_unavailable_and_names_the_path(proj):
    s = pa.settings(proj["dir"], proj["config"])
    exports, _sha = _exports(proj["tmp"])
    lib = ExportsLibrary(s, exports)
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body("gone.json", "b" * 64, OLD_ROWS[0], proj)), s, library=lib)
    (status, detail), = _lib_status(v)
    assert status == pa.RELEASE_UNAVAILABLE
    assert str(exports / "gone.json") in detail
    assert lib.rebuilds == []


def test_a_release_whose_bytes_moved_is_release_unavailable(proj):
    s = pa.settings(proj["dir"], proj["config"])
    exports, _sha = _exports(proj["tmp"])
    lib = ExportsLibrary(s, exports)
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body("old.json", "d" * 64, OLD_ROWS[0], proj)), s, library=lib)
    (status, detail), = _lib_status(v)
    assert status == pa.RELEASE_UNAVAILABLE
    assert str(exports / "old.json") in detail and "d" * 12 in detail
    assert lib.rebuilds == []


def test_a_release_name_with_a_path_in_it_is_refused(proj):
    s = pa.settings(proj["dir"], proj["config"])
    exports, sha = _exports(proj["tmp"])
    lib = ExportsLibrary(s, exports)
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body("../exports/old.json", sha, OLD_ROWS[0], proj)), s,
                       library=lib)
    (status, detail), = _lib_status(v)
    assert status == pa.RELEASE_UNAVAILABLE and "file name" in detail
    assert lib.rebuilds == []


def test_the_current_release_path_is_unchanged(proj):
    s = pa.settings(proj["dir"], proj["config"])
    exports, _sha = _exports(proj["tmp"])
    lib = ExportsLibrary(s, exports)
    v = pa.verify_note(_note(proj, "AD-099_x.md", _body("served.json", SERVED_SHA, SERVED_ROWS[0], proj)), s,
                       library=lib)
    assert _lib_status(v) == [(pa.PASS, "1 row(s) returned")]
    assert lib.served_calls == 1 and lib.rebuilds == []
    lib2 = ExportsLibrary(s, exports)
    v = pa.verify_note(_note(proj, "AD-098_y.md", _body("served.json", SERVED_SHA, "lesson:no#p1:1:0-1", proj)), s,
                       library=lib2)
    assert [st for st, _d in _lib_status(v)] == [pa.ID_NOT_RETURNED]
    assert lib2.rebuilds == []


def test_one_older_release_is_rebuilt_once_for_every_query_that_names_it(proj):
    s = pa.settings(proj["dir"], proj["config"])
    exports, sha = _exports(proj["tmp"])
    lib = ExportsLibrary(s, exports)
    body = _body("old.json", sha, OLD_ROWS[0], proj).replace("### Internal", (
        f'- library receipt: query "model pin" | release old.json sha256:{sha} | rows {OLD_ROWS[1]}\n\n'
        f'- library receipt: query "model pin" | release served.json sha256:{SERVED_SHA} | rows {SERVED_ROWS[0]}\n\n'
        f"### Internal"))
    v = pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=lib)
    assert [st for st, _d in _lib_status(v)] == [pa.PASS, pa.PASS, pa.PASS]
    assert lib.rebuilds == [sha]


# ------------------------------------------------------------------------- the commit a release was recorded in

def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def test_release_commit_is_the_first_commit_whose_register_row_carries_the_digest(tmp_path):
    repo = tmp_path / "g"
    first = _repo(repo, {"exports/EXPORT_VERSIONS.md": "| v | file | date | sha16 |\n",
                         "corpus/manifest.yaml": "documents: []\n"})
    sha_a, sha_b = "1" * 64, "2" * 64
    (repo / "exports" / "EXPORT_VERSIONS.md").write_text(
        "| v | file | date | sha16 |\n| **a** | `a.json` | 2026-10-01 | `" + sha_a[:16] + "` |\n")
    _git(repo, "commit", "-qam", "release a")
    c_a = _git(repo, "rev-parse", "HEAD")
    (repo / "exports" / "EXPORT_VERSIONS.md").write_text(
        (repo / "exports" / "EXPORT_VERSIONS.md").read_text() + "| **b** | `b.json` | 2026-10-02 | `" + sha_b[:16] + "` |\n")
    _git(repo, "commit", "-qam", "release b")
    c_b = _git(repo, "rev-parse", "HEAD")
    reg = repo / "exports" / "EXPORT_VERSIONS.md"
    assert pa.release_commit(reg, sha_a) == c_a
    assert pa.release_commit(reg, sha_b) == c_b
    assert pa.release_commit(reg, "3" * 64) is None
    assert first not in (c_a, c_b)


# ------------------------------------------------------------------------- a worktree's corpus is the primary's

def test_a_worktree_resolves_its_corpus_beside_the_primary_checkout(proj):
    """A dispatched session runs in `<primary>/.claude/worktrees/<name>`; `../sib` must name the primary's sibling,
    not `.claude/worktrees/sib` (MCP-001 RESULT: every sibling receipt failed from a worktree). The project's own state
    (the query log) stays in the worktree."""
    primary = proj["dir"]
    _git(primary, "add", "-A")
    _git(primary, "commit", "-qm", "fixture")
    wt = primary / ".claude" / "worktrees" / "w1"
    _git(primary, "worktree", "add", "-q", "-b", "worktree-w1", str(wt))
    config = json.loads(json.dumps(proj["config"]))
    config["prior_art"]["internal_roots"][0]["path"] = "../sib"
    config["prior_art"]["library"]["graph"] = "../nolib"
    s = pa.settings(wt, config)
    assert s.roots[0].path == (proj["tmp"] / "sib").resolve()
    assert s.library_graph == (proj["tmp"] / "nolib").resolve()
    assert s.log == (wt / "state" / "q.jsonl").resolve()
    # the note being verified, in the worktree, is still left out of the primary-anchored root (QC-001 premise 3)
    config["prior_art"]["internal_roots"].append({"name": "self", "path": "."})
    s2 = pa.settings(wt, config)
    assert ("self", "docs/design/AD-099_x.md") in pa.note_keys(s2, [wt / "docs" / "design" / "AD-099_x.md"])
    assert pa.corpus_anchor(primary) == primary.resolve()
    assert pa.corpus_anchor(proj["tmp"] / "loose") == (proj["tmp"] / "loose").resolve()   # not a git work tree


# ------------------------------------------------------------------------- the real library, when it is on disk

def _real_library():
    """`(Settings, Library)` on this checkout's configured library, or a skip reason."""
    try:
        import squiddy  # noqa: F401
    except ImportError:
        return None, "squiddy is not installed in this interpreter"
    from seldon.config import load_project_config
    root = Path(__file__).resolve().parent.parent
    try:
        s = pa.settings(root, load_project_config(root))
    except Exception as exc:  # noqa: BLE001 (the reason is the skip message)
        return None, f"no prior_art settings here: {exc}"
    idx = s.library_graph / "work" / "index" / "index_manifest.json"
    if not idx.is_file():
        return None, f"the library index is not on disk ({idx})"
    return (s, pa.Library(s)), None


def test_rebuilding_the_served_release_reproduces_the_served_index(tmp_path):
    """The rebuild path, run on the release the index serves, yields the served index's rows and dense shard set
    byte for byte: the rebuild rule (manifest as committed with the release; the library's append-only corpus rows
    and keyed shards) reproduces the instrument, so a rebuilt OLDER release is the index its receipts ran on."""
    got, why = _real_library()
    if got is None:
        pytest.skip(why)
    s, lib = got
    served = json.loads((s.library_graph / "work" / "index" / "index_manifest.json").read_text())
    export = s.library_graph / served["release"]["export"]
    if not export.is_file():
        pytest.skip(f"the served export is not on disk ({export})")
    info = pa.rebuild_release(lib.graph(), served["release"]["sha256"], tmp_path)
    assert info["row_fingerprint"] == served["row_fingerprint"]
    assert info["shard_set_sha256"] == served["dense"]["shard_set_sha256"]
    assert info["rows"] == served["rows"]
