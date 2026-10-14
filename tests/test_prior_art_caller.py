"""DISP-c7 (AD-036-R10, R11; ADDENDUM 04): the query log is the calling repository's, and a run commits what it wrote.

Every repository here is a scratch git repository with its own `seldon.yaml`, so `run_search` and `run_verify` resolve
the calling project the way the CLI does: from disk. Nothing reads the operator's repositories or the library index.
"""
from __future__ import annotations

import json
import subprocess
import urllib.parse
from pathlib import Path

import pytest
import yaml

from seldon.commands import prior_art as cmd
from seldon.core import prior_art as pa

SPACED = "docs/research/AI Readiness  A Comprehensive Review.md"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


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


def _block(tmp: Path) -> dict:
    return {
        "log": "state/prior_art_queries.jsonl",
        "internal_roots": [{"name": "sib", "path": str(tmp / "sib")}],
        "internal": {"default_include": ["docs/design/**", "docs/research/**"], "suffixes": [".md"],
                     "top_n": 20, "max_file_bytes": 100000, "bm25": {"k1": 1.2, "b": 0.75}},
        "library": {"graph": str(tmp / "nolib"), "k": 20},
        "gate": {"design_dir": "docs/design", "baseline": "docs/design/AD-036_baseline.txt",
                 "exempt_globs": ["*_ADDENDUM_*.md"], "verdict_ledger_without_governed": "state/verdicts.jsonl"},
    }


def _project(root: Path, tmp: Path) -> Path:
    _repo(root, {"seldon.yaml": yaml.safe_dump({"prior_art": _block(tmp)}),
                 "docs/design/AD-036_baseline.txt": "\n", "docs/design/sub/.keep": ""})
    return root


@pytest.fixture
def two(tmp_path):
    """Two projects, `a` and `b`, sharing one sibling corpus whose research note has two spaces in its name."""
    sha = _repo(tmp_path / "sib", {"docs/design/DN-001.md": "# DN-001\n\nThe unit of extraction is the paragraph.\n",
                                   SPACED: "Readiness review.\n\nThe unit of extraction, in a spaced file.\n"})
    return {"a": _project(tmp_path / "a", tmp_path), "b": _project(tmp_path / "b", tmp_path), "sha": sha,
            "tmp": tmp_path}


def _lines(p: Path) -> list:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.is_file() else []


def _porcelain(root: Path) -> str:
    return _git(root, "status", "--porcelain")


# ------------------------------------------------------------------------- step 4: a hit path with spaces

def test_a_hit_path_with_two_spaces_round_trips_through_search_and_verify(two):
    s = pa.settings(two["a"], yaml.safe_load((two["a"] / "seldon.yaml").read_text()))
    tool = pa.Internal(s)
    (receipt,) = tool.receipts(tool.search("unit of extraction"))
    assert "AI%20Readiness%20%20A%20Comprehensive%20Review.md" in receipt
    note = two["a"] / "docs" / "design" / "AD-099_x.md"
    note.write_text("# AD-099\n\n## Prior art\n\n### External\n\n- web receipt: url https://example.org | retrieved "
                    "2026-10-14\n\n### Internal\n\n" + receipt + "\n")
    v = pa.verify_note(note, s)
    (r,) = [x for x in v.receipts if x.kind == "internal"]
    assert r.status == pa.PASS, r.detail
    assert (SPACED, 3, None) in r.hits


def test_the_same_receipt_written_unencoded_is_malformed(two):
    """The defect MODEL-003 found, kept as the control: the old form of the receipt does not parse."""
    raw = f'query "unit of extraction" | repo sib@{two["sha"]} | hits {SPACED}:3'
    r = pa._parse_receipt("Internal", "internal", raw, 1, "n.md", raw)
    assert r.error


@pytest.mark.parametrize("path", ["docs/design/AD-036_x.md", "a b.md", "a  b\tc.md", "100%,done.md",
                                  "Réadiness  ü.md", "x:y.md"])
def test_encoding_is_reversible_and_the_identity_on_plain_paths(path):
    enc = pa.encode_hit_path(path)
    assert urllib.parse.unquote(enc) == path
    assert not any(ch.isspace() or ch == "," for ch in enc)
    if not any(ch in path for ch in "%, \t"):
        assert enc == path


# ------------------------------------------------------------------------- R10: the calling project

def test_calling_project_order_explicit_then_note_then_cwd(two):
    a, b = two["a"], two["b"]
    assert pa.calling_project(b, None, a) == b.resolve()
    assert pa.calling_project(None, b / "docs/design/X.md", a) == b.resolve()
    assert pa.calling_project(None, "docs/design/X.md", a / "docs/design/sub") == a.resolve()
    assert pa.calling_project(None, None, a / "docs/design/sub") == a.resolve()
    with pytest.raises(pa.PriorArtError, match="holds no seldon.yaml"):
        pa.calling_project(two["tmp"], None, a)
    with pytest.raises(pa.PriorArtError, match="no seldon.yaml at or above"):
        pa.calling_project(None, None, two["tmp"] / "sib")


def test_a_search_for_another_repos_note_is_logged_and_committed_there(two):
    a, b = two["a"], two["b"]
    head_a = _git(a, "rev-parse", "HEAD")
    out = cmd.run_search("internal", "unit of extraction", note=str(b / "docs/design/AD-099_y.md"), cwd=a)
    assert out["project"] == str(b.resolve())
    assert out["commit"]["committed"], out["commit"]
    assert not (a / "state" / "prior_art_queries.jsonl").exists()
    (line,) = _lines(b / "state" / "prior_art_queries.jsonl")
    assert line["project"] == "b" and line["purpose"] == "search"
    assert _porcelain(a) == "" and _porcelain(b) == ""
    assert _git(a, "rev-parse", "HEAD") == head_a
    assert _git(b, "log", "-1", "--format=%s").startswith("record: prior-art internal search")
    assert _git(b, "show", "--name-only", "--format=", "HEAD") == "state/prior_art_queries.jsonl"


def test_a_verify_commits_its_log_lines_and_its_verdict_in_the_notes_repo(two):
    b = two["b"]
    tool = pa.Internal(pa.settings(b, yaml.safe_load((b / "seldon.yaml").read_text())))
    (receipt,) = tool.receipts(tool.search("unit of extraction"))
    note = b / "docs" / "design" / "AD-099_z.md"
    note.write_text("# AD-099\n\n## Prior art\n\n### External\n\n- web receipt: url https://example.org | retrieved "
                    "2026-10-14\n\n### Internal\n\n" + receipt + "\n")
    _git(b, "add", "-A")
    _git(b, "commit", "-q", "-m", "note")
    out = cmd.run_verify(str(note), cwd=two["a"])
    assert out["project"] == str(b.resolve())
    assert out["commit"]["committed"], out["commit"]
    assert set(out["commit"]["committed_paths"]) == {"state/prior_art_queries.jsonl", "state/verdicts.jsonl"}
    assert _porcelain(b) == "" and _porcelain(two["a"]) == ""


def test_lines_already_waiting_are_not_committed_by_a_run_and_the_pass_sweep_commits_them(two):
    a = two["a"]
    log = a / "state" / "prior_art_queries.jsonl"
    log.parent.mkdir()
    log.write_text(json.dumps({"tool": "prior-art/1", "query": "earlier", "ts": "t"}) + "\n")
    out = cmd.run_search("internal", "unit of extraction", cwd=a)
    assert out["commit"] == {"committed": False, "reason": "dirty_before_this_run",
                             "skipped": ["state/prior_art_queries.jsonl"]}
    assert len(_lines(log)) == 2
    swept = pa.commit_leftovers(a, yaml.safe_load((a / "seldon.yaml").read_text()))
    assert swept["committed"] and _porcelain(a) == ""


def test_the_sweep_leaves_a_log_carrying_foreign_lines(two):
    a = two["a"]
    log = a / "state" / "prior_art_queries.jsonl"
    log.parent.mkdir()
    log.write_text(json.dumps({"tool": "something-else"}) + "\n")
    swept = pa.commit_leftovers(a, yaml.safe_load((a / "seldon.yaml").read_text()))
    assert swept == {"committed": False, "reason": "nothing_to_commit"}
    assert "state/" in _porcelain(a)


def test_a_held_lease_defers_the_commit_to_the_next_pass(two, monkeypatch):
    a = two["a"]
    monkeypatch.setattr(pa, "_lease_defers", lambda project_dir, config: True)
    out = cmd.run_search("internal", "unit of extraction", cwd=a)
    assert out["commit"]["reason"] == "lease_held"
    assert "state/" in _porcelain(a)
    monkeypatch.undo()
    assert pa.commit_leftovers(a, yaml.safe_load((a / "seldon.yaml").read_text()))["committed"]
    assert _porcelain(a) == ""


def test_lease_defers_unless_the_caller_is_the_session_the_lease_launched(tmp_path, monkeypatch):
    from seldon.core import dispatch as D
    store = tmp_path / "seldon_events.jsonl"
    store.write_text(json.dumps({"event_type": "dispatch_launched",
                                 "payload": {"task_id": "T1", "child_session_id": "S1"}}) + "\n")
    monkeypatch.setattr(D, "load_dispatch_config", lambda p, c: {"lease_file": ".seldon/dispatch.lock"})
    monkeypatch.setattr(D, "lease_is_held", lambda p, cfg: True)
    monkeypatch.setattr(D, "read_lease", lambda p: {"holder": "h", "pid": 1, "task": "T1"})
    monkeypatch.setenv("SELDON_SESSION_ID", "S1")
    assert pa._lease_defers(tmp_path, {}) is False
    monkeypatch.setenv("SELDON_SESSION_ID", "S2")
    assert pa._lease_defers(tmp_path, {}) is True
    monkeypatch.delenv("SELDON_SESSION_ID")
    assert pa._lease_defers(tmp_path, {}) is True
    monkeypatch.setattr(D, "lease_is_held", lambda p, cfg: False)
    assert pa._lease_defers(tmp_path, {}) is False


def test_outside_a_work_tree_nothing_is_committed_and_nothing_fails(tmp_path):
    (tmp_path / "sib").mkdir()
    (tmp_path / "sib" / "n.md").write_text("unit of extraction\n")
    proj = tmp_path / "p"
    proj.mkdir()
    block = _block(tmp_path)
    block["internal_roots"][0]["include"] = ["**"]
    (proj / "seldon.yaml").write_text(yaml.safe_dump({"prior_art": block}))
    out = cmd.run_search("internal", "unit of extraction", cwd=proj)
    assert out["commit"] == {"committed": False, "reason": "not_a_work_tree"}
    assert len(_lines(proj / "state" / "prior_art_queries.jsonl")) == 1
