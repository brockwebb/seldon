"""SEL-038: a system-written journal never blocks a merge, a merge block names the files git named, the verdict ledger
merges by union, and a held library release is read through squiddy's accessor.

`cc_tasks/2026-11-11_SEL-038_a_system_written_journal_never_blocks_a_merge_and_a_held_library_release_is_read_through_squiddys_accessor.md`,
answering three consumer filings:

- hazbrief HB-155 (filing `a7795a22`): six hours of green work left `ff_refused` because Desktop's `prior-art/1` had
  appended six lines to `state/prior_art_queries.jsonl` in main during the run and the branch had receipts of its own
  in that file. The lease-held step before the fast-forward committed the event store only. AD-034-R19.
- the same Issue said "Files: none named" while git's stderr named the file. AD-034-R20.
- hazbrief HB-166 (filing `6d607cb9`): `state/prior_art_verdicts.jsonl` conflicted twice on a rebase where main and
  the branch had each appended one verdict; `seldon hooks install` declared the query log `merge=union` and not the
  verdict ledger. AD-036-R23.
- squiddy SQ-134 (filing of 2026-11-10): sealed releases older than the diff base are held as `<name>.gz`; a receipt
  naming one read `release_unavailable` because `Library` opened the plain name. AD-036-R24.

Real git and real detached supervisors for the merge round (the scaffold of `tests/test_dispatch_parallel.py`), the
per-process scratch Neo4j database, zero model calls, no network.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.hooks import hooks_group
from seldon.core import hooks as H
from seldon.core import prior_art as pa
from seldon.core import worktree as WT
from tests.dispatch_scaffold import NEO4J_DB, add_task, git, register, write_stub
from tests.test_dispatch_parallel import (  # noqa: F401  (fixtures and helpers of the same scaffold)
    _finished, _issues, _no_api_key, _once, _parallel_opted_in, _project, _show, _wait_settled, dc,
)

QUERY_LOG = "state/prior_art_queries.jsonl"
VERDICTS = "state/prior_art_verdicts.jsonl"

#: git's stderr exactly as hazbrief HB-155's `dispatch_finished` event (`8d7403aa`) carried it.
HB155_STDERR = ("error: Your local changes to the following files would be overwritten by merge:\n"
                "\tstate/prior_art_queries.jsonl\n"
                "Please commit your changes or stash them before you merge.\n"
                "Aborting")


# ================================================================================ C: the files git named

def test_the_files_git_named_are_read_from_the_filings_stderr():
    assert WT.files_named(HB155_STDERR) == ["state/prior_art_queries.jsonl"]


def test_untracked_and_conflict_forms_are_read_and_a_message_naming_none_gives_none():
    untracked = ("error: The following untracked working tree files would be overwritten by merge:\n"
                 "\tout/a/x.txt\n\tout/b/y.txt\n"
                 "Please move or remove them before you merge.\nAborting")
    assert WT.files_named(untracked) == ["out/a/x.txt", "out/b/y.txt"]
    conflict = ("Auto-merging shared.txt\nCONFLICT (content): Merge conflict in shared.txt\n"
                "error: could not apply 1234567... b: result")
    assert WT.files_named(conflict) == ["shared.txt"]
    assert WT.files_named("fatal: Not possible to fast-forward, aborting.") == []
    assert WT.files_named("") == [] and WT.files_named(None) == []


# ================================================================================ D: the verdict ledger is union

def _hooked_project(tmp_path: Path, governed: bool = False) -> Path:
    """A git project with seldon's hooks and a complete prior-art block whose verdict ledger is tracked."""
    p = tmp_path / "proj"
    p.mkdir()
    _sh(p, "git", "init", "-q", "-b", "main")
    _sh(p, "git", "config", "user.email", "t@t")
    _sh(p, "git", "config", "user.name", "t")
    config = {"project": {"name": "t"}, "event_store": {"path": "seldon_events.jsonl"},
              "prior_art": _prior_art_block(tmp_path)}
    (p / "seldon_events.jsonl").write_text('{"event_id": "e0"}\n')
    if governed:
        (p / "governed" / "ledger").mkdir(parents=True)
        (p / "governed" / "ledger" / "events.jsonl").write_text("")
        config["governed"] = {"graph_dir": "governed"}
    (p / "docs" / "design").mkdir(parents=True)
    (p / "docs" / "design" / "AD-036_baseline.txt").write_text("")
    (p / "state").mkdir()
    (p / QUERY_LOG).write_text('{"tool": "prior-art/1", "query": "base"}\n')
    (p / VERDICTS).write_text(json.dumps({"event_id": "v0", "type": "prior_art_verdict"}) + "\n")
    (p / "seldon.yaml").write_text(yaml.safe_dump(config))
    # What hazbrief-mcp's `.gitattributes` held on 2026-11-11, as an earlier `seldon hooks install` wrote it.
    (p / ".gitattributes").write_text(f"seldon_events.jsonl merge=union\n{QUERY_LOG} merge=union\n")
    H.install(p, python=sys.executable)
    _sh(p, "git", "add", "-A")
    _sh(p, "git", "commit", "-qm", "init")
    return p


def _prior_art_block(tmp_path: Path) -> dict:
    # As tests/test_attr001_union_attribute.py writes one, with the verdict ledger at hazbrief's path.
    return {"log": QUERY_LOG,
            "internal_roots": [{"name": "self", "path": "."}],
            "internal": {"default_include": ["docs/design/**"], "suffixes": [".md"], "top_n": 20,
                         "max_file_bytes": 100000, "bm25": {"k1": 1.2, "b": 0.75}},
            "library": {"graph": str(tmp_path / "nolib"), "k": 20},
            "gate": {"design_dir": "docs/design", "baseline": "docs/design/AD-036_baseline.txt",
                     "exempt_globs": ["*_ADDENDUM_*.md"], "verdict_ledger_without_governed": VERDICTS}}


def _sh(cwd: Path, *argv: str) -> subprocess.CompletedProcess:
    # The hooks run `python -m seldon hooks ...`: the code under test must be first on PYTHONPATH.
    src = Path(H.__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["PYTHONPATH"] = os.pathsep.join(x for x in (str(src), env.get("PYTHONPATH")) if x)
    r = subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, (argv, r.stdout, r.stderr)
    return r


def _config(p: Path) -> dict:
    return yaml.safe_load((p / "seldon.yaml").read_text())


def test_the_verdict_ledger_is_one_of_the_append_only_paths(tmp_path):
    p = _hooked_project(tmp_path)
    assert H.append_only_paths(p, _config(p)) == ["seldon_events.jsonl", QUERY_LOG, VERDICTS]


def test_with_a_governed_graph_the_verdict_ledger_is_the_governed_ledger_listed_once(tmp_path):
    """The governed-ledger case: verdicts go to the governed ledger (`prior_art.verdict_ledger`), which ATTR-001
    already declared; the fallback path is not a verdict ledger there, so it is not declared."""
    p = _hooked_project(tmp_path, governed=True)
    assert pa.verdict_ledger(p, _config(p)) == p.resolve() / "governed/ledger/events.jsonl"
    assert H.append_only_paths(p, _config(p)) == [
        "seldon_events.jsonl", "governed/ledger/events.jsonl", QUERY_LOG]


def test_a_block_without_the_fallback_key_declares_no_verdict_ledger(tmp_path):
    p = _hooked_project(tmp_path)
    config = _config(p)
    del config["prior_art"]["gate"]["verdict_ledger_without_governed"]
    assert H.append_only_paths(p, config) == ["seldon_events.jsonl", QUERY_LOG]


def test_a_rebase_where_both_sides_appended_a_verdict_keeps_every_line_once(tmp_path):
    """HB-166's conflict, replayed: main and a branch each append one verdict. Declared by `hooks install`, the
    rebase completes and the ledger holds every line once."""
    p = _hooked_project(tmp_path)
    assert H.union_missing(p, _config(p)) == [VERDICTS], "hazbrief's state: the log declared, the ledger not"
    res = CliRunner().invoke(hooks_group, ["install", "--repo", str(p)])
    assert res.exit_code == 0, res.output
    assert f"declares {VERDICTS} merge=union" in res.output
    assert H.union_missing(p, _config(p)) == []
    assert f"{VERDICTS} merge=union\n" in (p / ".gitattributes").read_text()
    assert _sh(p, "git", "status", "--porcelain").stdout == "", "install committed what it wrote"
    wt = tmp_path / "wt"
    _sh(p, "git", "worktree", "add", "-q", "-b", "task", str(wt))
    branch_line = json.dumps({"event_id": "v-branch", "type": "prior_art_verdict"}) + "\n"
    main_line = json.dumps({"event_id": "v-main", "type": "prior_art_verdict"}) + "\n"
    with open(wt / VERDICTS, "a") as fh:
        fh.write(branch_line)
    _sh(wt, "git", "commit", "-qm", "record: prior-art verify (branch)", "--", VERDICTS)
    with open(p / VERDICTS, "a") as fh:
        fh.write(main_line)
    _sh(p, "git", "commit", "-qm", "record: prior-art verify (main)", "--", VERDICTS)

    rb = WT.rebase(wt, "main")

    assert rb["ok"], rb
    lines = (wt / VERDICTS).read_text().splitlines()
    ids = [json.loads(x)["event_id"] for x in lines]
    assert sorted(ids) == ["v-branch", "v-main", "v0"] and len(ids) == len(set(ids))
    check = WT.check_union_text((wt / VERDICTS).read_bytes(), "event_id", base=WT.show(p, "main", VERDICTS))
    assert check["ok"], check


# ================================================================================ B: the merge round

def _prior_art_dispatch_project(tmp_path: Path, **extra) -> Path:
    """The dispatch scaffold with a prior-art block, its query log and verdict ledger tracked, and the
    `.gitattributes` hazbrief had before this task (event store and query log; the verdict ledger missing)."""
    p = _project(tmp_path, **extra)
    config = yaml.safe_load((p / "seldon.yaml").read_text())
    config["prior_art"] = _prior_art_block(tmp_path)
    (p / "seldon.yaml").write_text(yaml.safe_dump(config))
    (p / "docs" / "design").mkdir(parents=True)
    (p / "docs" / "design" / "AD-036_baseline.txt").write_text("")
    (p / "state").mkdir()
    (p / QUERY_LOG).write_text('{"tool": "prior-art/1", "query": "base"}\n')
    (p / VERDICTS).write_text(json.dumps({"event_id": "v0", "type": "prior_art_verdict"}) + "\n")
    (p / ".gitattributes").write_text(f"seldon_events.jsonl merge=union\n{QUERY_LOG} merge=union\n")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "prior-art block")
    git(p, "push", "-q")
    return p


@pytest.mark.usefixtures("neo4j_available")
@pytest.mark.parametrize("journal,branch_line,main_line", [
    (QUERY_LOG, {"tool": "prior-art/1", "query": "the branch's receipt"},
     {"tool": "prior-art/1", "query": "Desktop's search during the run"}),
    (VERDICTS, {"event_id": "v-branch", "type": "prior_art_verdict"},
     {"event_id": "v-main", "type": "prior_art_verdict"}),
], ids=["query_log", "verdict_ledger"])
def test_a_journal_dirty_in_main_during_the_run_does_not_block_the_merge(
        tmp_path, neo4j_driver, clean_test_db, dc, journal, branch_line, main_line):
    """HB-155, reproduced: the branch appends to a prior-art journal and commits it; during the run a Desktop tool
    appends to the same journal in main and leaves it uncommitted. With one merge attempt the round must merge: it
    commits every journal class under the lease, rebases over that housekeeping commit by union, and fast-forwards."""
    p = _prior_art_dispatch_project(tmp_path, merge_attempts=1)
    add_task(p, "a", "**Exclusive:** no\n**Touches:** out/a/\n")
    write_stub(p, {"a": {"write": {journal: json.dumps(branch_line) + "\n", "out/a/1.txt": "a\n"},
                         "primary_append": {journal: json.dumps(main_line) + "\n"}}})
    register(p, neo4j_driver, dc, "a", "2026-11-11T00:00:01Z")

    assert _once(p).count("launching") == 1
    _wait_settled(p, neo4j_driver, ["a"])

    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merged" and fin["merge"]["attempts"] == 1, fin["merge"]
    rows = [json.loads(x) for x in _show(p, "main", journal).splitlines() if x.strip()]
    assert branch_line in rows and main_line in rows
    assert len(rows) == 3, "the base line and both appends, each once"
    assert git(p, "status", "--porcelain").stdout == ""
    subjects = git(p, "log", "--format=%s", "main").stdout
    assert "(prior_art, AD-038-R1)" in subjects, "the Desktop line was committed by the reconcile, as a pass would"
    # D in effect: the pass declared the verdict ledger before the launch, as it declares every append-only log.
    assert f"{VERDICTS} merge=union" in _show(p, "main", ".gitattributes")


@pytest.mark.usefixtures("neo4j_available")
def test_an_ff_refused_block_and_its_issue_name_the_file_git_named(tmp_path, neo4j_driver, clean_test_db, dc):
    """AD-034-R20: a fast-forward git refuses over a file that is not a journal (an untracked file in main at a path
    the branch adds) is still `ff_refused`, and the record and the Issue carry the path from git's stderr."""
    p = _project(tmp_path, merge_attempts=1)
    add_task(p, "a", "**Exclusive:** no\n**Touches:** out/a/\n")
    write_stub(p, {"a": {"write": {"out/a/x.txt": "the branch's\n"},
                         "primary_append": {"out/a/x.txt": "an operator's file in main\n"}}})
    register(p, neo4j_driver, dc, "a", "2026-11-11T00:00:01Z")

    assert _once(p).count("launching") == 1
    _wait_settled(p, neo4j_driver, ["a"])

    fin = _finished(p, "a")[-1]
    assert fin["outcome"] == "merge_blocked" and fin["merge"]["reason"] == "ff_refused", fin
    assert fin["merge"]["files"] == ["out/a/x.txt"]
    assert "out/a/x.txt" in fin["merge"]["stderr"]
    [issue] = _issues(neo4j_driver)
    assert issue["reason"] == "ff_refused" and issue["files"] == ["out/a/x.txt"]
    with neo4j_driver.session(database=NEO4J_DB) as s:
        desc = s.run("MATCH (i:Issue) RETURN i.description AS d").single()["d"]
    assert "Files: out/a/x.txt." in desc and "none named" not in desc


# ================================================================================ E: held releases

class _Settings(types.SimpleNamespace):
    pass


def _held_library(tmp_path: Path):
    """A `Library` whose exports directory holds one release as squiddy's R-253 holds it: `<name>.gz` beside where
    the plain file was, one `held` line in `compressed.jsonl` with the original's sha256 and size, the plain gone."""
    exports = tmp_path / "exports"
    exports.mkdir()
    name = "library_graph_20260916_hv006_2026-09-16.json"
    data = json.dumps({"nodes": [{"id": "n1"}], "links": []}).encode()
    sha = hashlib.sha256(data).hexdigest()
    with gzip.open(exports / f"{name}.gz", "wb") as fh:
        fh.write(data)
    (exports / "compressed.jsonl").write_text(json.dumps(
        {"event": "held", "file": name, "gz": f"{name}.gz", "release": "20260916_hv006", "sha256": sha,
         "bytes": len(data)}) + "\n")
    lib = pa.Library(_Settings(library_graph=tmp_path / "graph", library_k=5))
    lib.exports_dir = lambda: exports
    return lib, exports, name, sha


def _contract_accessor() -> types.ModuleType:
    """squiddy.exports's contract (DN-059 R-253 item 3) for the four calls seldon makes, written from the filing:
    a dated export read by its PLAIN path, plain or held; a held read decompresses and verifies the recorded sha256
    and size, and a mismatch raises a SystemExit (`HeldExportError`)."""
    m = types.ModuleType("squiddy.exports")

    def _rec(p):
        recs = {}
        for ln in (p.parent / "compressed.jsonl").read_text().splitlines():
            r = json.loads(ln)
            recs[r["file"]] = r
        r = recs.get(p.name)
        if not (r and r["event"] == "held" and (p.parent / f"{p.name}.gz").is_file()):
            raise FileNotFoundError(f"{p} is not on disk, plain or held")
        return r

    def exists(p):
        p = Path(p)
        try:
            return p.is_file() or bool(_rec(p))
        except FileNotFoundError:
            return False

    def sha256(p):
        p = Path(p)
        if p.is_file():
            return hashlib.sha256(p.read_bytes()).hexdigest()
        r = _rec(p)
        with gzip.open(p.parent / f"{p.name}.gz", "rb") as fh:
            data = fh.read()
        got = hashlib.sha256(data).hexdigest()
        if got != r["sha256"] or len(data) != r["bytes"]:
            raise SystemExit(f"FATAL: {p.name}.gz decompresses to sha256 {got[:16]}, not {r['sha256'][:16]}")
        return got

    def size(p):
        p = Path(p)
        return p.stat().st_size if p.is_file() else int(_rec(p)["bytes"])

    def mtime(p):
        p = Path(p)
        return (p if p.is_file() else p.parent / f"{p.name}.gz").stat().st_mtime

    m.exists, m.sha256, m.size, m.mtime = exists, sha256, size, mtime
    return m


@pytest.fixture(params=["contract", "squiddy"])
def accessor(request, monkeypatch):
    """The contract stand-in always; squiddy's own `squiddy.exports` too where the installed squiddy carries it (on
    2026-11-12 it is on squiddy's SQ-134 branch only, commit 9a54c9e5, not on squiddy main)."""
    if request.param == "squiddy":
        return pytest.importorskip("squiddy.exports", reason="the installed squiddy predates DN-059 R-253")
    m = _contract_accessor()
    monkeypatch.setattr(pa, "_exports_accessor", lambda: m)
    return m


def test_a_receipt_naming_a_held_release_verifies(tmp_path, accessor, monkeypatch):
    lib, exports, name, sha = _held_library(tmp_path)
    assert not (exports / name).exists() and (exports / f"{name}.gz").is_file()

    class _Index:
        def search(self, query, k):
            return {"hits": [{"rows": [{"receipt": {"row_id": "lesson:x#p1:1:0-10"}}]}]}

    monkeypatch.setattr(lib, "_release_index", lambda release, sha256, path: (_Index(), {"commit": "c0", "rows": 1}))
    res = lib.search_release("held release query", name, sha)
    assert res["release"] == name and res["sha256"] == sha and res["rows"] == ["lesson:x#p1:1:0-10"]
    assert res["export_path"] == str(exports / name), "the plain path, as every reader names it"


def test_a_superseded_register_release_held_compressed_reads_its_rows(tmp_path, accessor, monkeypatch):
    lib, _exports, name, sha = _held_library(tmp_path)
    monkeypatch.setattr(pa, "release_row_ids", lambda graph, sha256: frozenset({"r1"}) if sha256 == sha else None)
    monkeypatch.setattr(lib, "graph", lambda: None)
    assert lib.release_rows(name, sha[:16]) == {"release": name, "sha256": sha, "rows": frozenset({"r1"})}


def test_a_held_release_that_does_not_decompress_to_its_record_is_unavailable_not_an_exit(tmp_path, accessor):
    lib, exports, name, sha = _held_library(tmp_path)
    with gzip.open(exports / f"{name}.gz", "wb") as fh:
        fh.write(b"other bytes")
    with pytest.raises(pa.PriorArtError, match=pa.RELEASE_UNAVAILABLE):
        lib.search_release("q", name, sha)


def test_an_absent_release_is_still_unavailable_naming_both_names(tmp_path, accessor):
    lib, exports, _name, sha = _held_library(tmp_path)
    with pytest.raises(pa.PriorArtError, match=r"not on disk: .*library_graph_x.json.*library_graph_x.json.gz"):
        lib.search_release("q", "library_graph_x.json", sha)


def test_without_the_accessor_a_held_release_is_named_as_held_and_a_plain_one_still_reads(tmp_path, monkeypatch):
    """A squiddy that predates R-253 cannot read a held file: the refusal says so rather than "not on disk"."""
    monkeypatch.setattr(pa, "_exports_accessor", lambda: None)
    lib, exports, name, sha = _held_library(tmp_path)
    with pytest.raises(pa.PriorArtError, match=r"held compressed .*squiddy\.exports"):
        lib.search_release("q", name, sha)
    plain = exports / "library_graph_plain.json"
    plain.write_bytes(b"plain bytes")
    assert lib._export_exists(plain) and lib._digest(plain) == hashlib.sha256(b"plain bytes").hexdigest()
