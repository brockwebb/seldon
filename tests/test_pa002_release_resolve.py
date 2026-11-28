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
and a scratch git repository. The rebuild test (SEL-050) builds a small served release in `tmp_path` with the kit's
own calls, rebuilds that SERVED release through the older-release path and checks the rebuild reproduces the served
index's rows and dense shard set exactly, which is what makes a rebuilt older release the same instrument the receipt
ran on. The same comparison against the operator's real library is kept, off by default (`LIVE_SWITCH`): it reads
another repository's state, so it cannot gate this one (Issue d6040ce8).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

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


# ------------------------------------------------------------------------- the rebuild reproduces the served index

#: SEL-050: set this environment variable to `1` to also run the rebuild comparison on the operator's real library
#: (`prior_art.library.graph` in this checkout's config). Off by default: it reads squiddy's live library, so its
#: outcome is another repository's state, and it was red for a real reason when SEL-047 ran it (the same 416,365 rows
#: with another row fingerprint and shard set; docs/evidence/sel047/README.md Part C). Issue d6040ce8.
LIVE_SWITCH = "SELDON_PA002_LIVE"

#: The fixture library's texts: two acquired entries (one of two pages) and one entry with no text, so the release
#: holds paragraph rows and metadata rows. Pages are separated by form feeds, as the kit's page reader returns them.
_TEXTS = {
    "work_a": ["Record linkage matches records\nacross two files.\n\nThe Fellegi Sunter model weighs agreement.",
               "Blocking reduces the candidate pairs.\n"],
    "work_b": ["Knowledge graphs store entities\nand relations between them.\n"],
}

#: A stub encoder's identity in the `index:` block: four dimensions, so a shard is a few hundred bytes. Values follow
#: squiddy's own index fixture (tests/test_s016_index.py `ENC`); no model is loaded or called.
_ENCODER = {"model_id": "stub", "revision": "stub", "trust_remote_repo": "stub", "trust_remote_revision": "stub",
            "dimension": 4, "query_prefix": "q: ", "document_prefix": "d: ", "device": "cpu", "normalize": True,
            "max_seq_length": 64, "batch_size": 2}


def _stub_encoder(texts):
    import numpy as np
    return np.array([[len(t), sum(map(ord, t)) % 97, 1.0, 0.0] for t in texts], dtype="float32")


def _read_pages(path) -> list[str]:
    return Path(path).read_text(encoding="utf-8").split("\f")


def _served_fixture_release(tmp: Path):
    """A small library, served, built in `tmp` by the kit's own calls: `(graph, served index manifest)`.

    The steps are the ones the library's release takes, at fixture size:

    1. the graph's config and empty manifest rendered by `squiddy init`'s renderers (`render_config`,
       `render_manifest`; `write_graph` itself also generates LinkML artifacts, which the index never reads);
    2. three manifest entries in the graph's in-graph stage, two with texts, and an `index:` block;
    3. a git repository, and the release: an export file and its register row, committed (what the release's
       export stages leave for `release_commit` to find);
    4. `squiddy.index.build` with a stub encoder for that release, which writes the corpus checkpoint, the database,
       the keyed dense shards and the served `index_manifest.json`;
    5. the same units' checkpoint lines under arm A's rule (`build_corpus_rows`' default rule, as arm A writes
       them). The library's checkpoint holds them (squiddy SQ-139: 2,357 lines on 2026-11-13), and they are what
       `checkpoint_rows` reads while the kit has no `release_rows` call (AD-036-R30). When it has one, these lines
       are not read.
    """
    from squiddy import index as ix
    from squiddy import init as ini
    from squiddy.config import load_graph
    spec = {"name": "pa002fixture", "title": "the PA-002 rebuild fixture", "description": "SEL-050",
            "scope": {"topic": "the rows of a release seldon rebuilds"},
            "classes": [{"Work": "Node"}, {"AuthoredBy": "Edge"}],
            "emit": [{"metadata_document": {"fields": {"common": ["id", "kind", "title"]},
                                            "citation_lines": False}}]}
    root = tmp / "library"
    root.mkdir()
    rendered = ini.render_config_data(spec)
    (root / "config.yaml").write_text(ini.render_config(spec, ini.sha256_text(yaml.safe_dump(spec)), "graph.yaml"),
                                      encoding="utf-8")
    man_path = root / rendered["engine"]["paths"]["manifest"]
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(ini.render_manifest(spec, rendered), encoding="utf-8")
    graph = load_graph(root)
    stage = ix.in_graph_stage(graph)

    man = yaml.safe_load(man_path.read_text(encoding="utf-8"))
    man["documents"] = []
    for doc_id, pages in _TEXTS.items():
        p = root / "texts" / f"{doc_id}.txt"
        p.parent.mkdir(exist_ok=True)
        p.write_text("\f".join(pages), encoding="utf-8")
        man["documents"].append({"id": doc_id, "kind": "work", "stage": stage, "title": f"The text of {doc_id}",
                                 "text_path": str(p), "text_sha256": ix.sha256_file(p)})
    man["documents"].append({"id": "work_c", "kind": "work", "stage": stage, "title": "A work with no text"})
    man_path.write_text(yaml.safe_dump(man, sort_keys=False), encoding="utf-8")
    block = {"work_dir": "work/index", "encoder": dict(_ENCODER),
             "encoder_pin": {"file": "pin.json", "sha256": "0" * 64},
             "dense": {"pad_to": "longest", "progress_rows": 2, "progress_seconds": 60, "pilot_rows": 2,
                       "pilot_seed": 1, "wall_seconds_max": 3600, "retries_per_unit": 1},
             "fusion": {"rrf_k": 60, "candidates_per_subarm": 200, "tuned": False},
             "top_k_documents": 3, "rows_per_document": 2, "text_max_chars": 30, "corpus_progress_every": 50}
    control = Path(ix.control_path(graph))
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text(yaml.safe_dump({"index": block}), encoding="utf-8")

    _git(root, "init", "-q")
    exports = Path(graph.path("exports_dir"))
    exports.mkdir(parents=True, exist_ok=True)
    export = exports / "pa002fixture_v1.json"
    export.write_text('{"release": "v1"}', encoding="utf-8")
    sha = hashlib.sha256(export.read_bytes()).hexdigest()
    (exports / pa.EXPORT_REGISTER).write_text(
        "| version | file | date | sha256 | note |\n|---|---|---|---|---|\n"
        f"| **v1** | `{export.name}` | 2026-11-26 | `{sha[:16]}` | SEL-050 fixture |\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "release v1")

    served = ix.build(graph, encoder=_stub_encoder, read_pages=_read_pages, release=export, repo=root,
                      reader={"reader": "stub page reader"})
    cfg = ix.load_config(graph)
    wd = Path(ix.work_dir(graph, cfg))
    arm_a = ix.build_corpus_rows(ix._manifest_entries(graph), root, wd / pa.CORPUS_ROWS, wd / "build.log",
                                 ix.meta_renderer(cfg), _read_pages, int(cfg["corpus_progress_every"]), stage)
    assert arm_a["rule"] == ix.CORPUS_RULE and not arm_a["failures"], arm_a
    return graph, served


def _assert_rebuild_reproduces(graph, served: dict, work: Path) -> dict:
    info = pa.rebuild_release(graph, served["release"]["sha256"], work)
    assert info["row_fingerprint"] == served["row_fingerprint"]
    assert info["shard_set_sha256"] == served["dense"]["shard_set_sha256"]
    assert info["rows"] == served["rows"]
    return info


def test_rebuilding_the_served_release_reproduces_the_served_index(tmp_path):
    """The rebuild path, run on the release the index serves, yields the served index's rows and dense shard set
    byte for byte: the rebuild rule (manifest as committed with the release; the library's append-only corpus rows
    and keyed shards) reproduces the instrument, so a rebuilt OLDER release is the index its receipts ran on. The
    library is a fixture the kit builds in `tmp_path` (SEL-050), so the outcome is this tree's code and the
    installed kit's, not the state of squiddy's live library."""
    # SEL-063 (REVIEW-001 F-33): squiddy is the gate's premise; without it this fails rather than skips.
    from tests.squiddy_premise import require
    require("squiddy.index")
    graph, served = _served_fixture_release(tmp_path)
    assert served["release"]["export"] == "exports/pa002fixture_v1.json"
    assert served["rows"] == 7 and served["dense"]["shards"] == 3     # 4 paragraph rows + 3 metadata rows
    info = _assert_rebuild_reproduces(graph, served, tmp_path / "rebuild")
    assert info["commit"] == _git(graph.root, "rev-parse", "HEAD")
    assert len(info["shards"]) == served["dense"]["shards"]


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


@pytest.mark.skipif(os.environ.get(LIVE_SWITCH) != "1",
                    reason=f"the live-library comparison runs by hand: {LIVE_SWITCH}=1 (SEL-050, Issue d6040ce8)")
def test_rebuilding_the_live_served_release_reproduces_the_live_served_index(tmp_path):
    """The same comparison on the operator's real library, when it is on disk and the switch is on."""
    got, why = _real_library()
    if got is None:
        pytest.skip(why)
    s, lib = got
    served = json.loads((s.library_graph / "work" / "index" / "index_manifest.json").read_text())
    export = s.library_graph / served["release"]["export"]
    if not export.is_file():
        pytest.skip(f"the served export is not on disk ({export})")
    _assert_rebuild_reproduces(lib.graph(), served, tmp_path)
