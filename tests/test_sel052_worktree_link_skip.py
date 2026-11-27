"""SEL-052 Part B: factory's 2026-11-25 filing, "a declared worktree link to a tracked directory is skipped without a
word". factory declares `dispatch.worktree_links: [.env, corpus/inbox]` and tracks `corpus/inbox/.gitkeep`, so every
checkout creates the directory and `worktree.link` skipped it; FAC-06 and FAC-06R each found an empty real directory.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from seldon.commands import dispatch_worktree as DW
from seldon.core import dispatch as D
from seldon.core import worktree as WT


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _primary(tmp_path) -> Path:
    p = tmp_path / "p"
    (p / "corpus" / "inbox").mkdir(parents=True)
    (p / "corpus" / "inbox" / ".gitkeep").write_text("", encoding="utf-8")
    (p / "data").mkdir()
    (p / ".gitignore").write_text("data/\n.env\n", encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "main", str(p))
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    _git(p, "add", "-A")
    _git(p, "commit", "-q", "-m", "init")
    (p / "corpus" / "inbox" / "held.pdf").write_text("pdf", encoding="utf-8")   # the primary's local copy
    (p / "data" / "x.bin").write_text("x", encoding="utf-8")
    return p


def test_a_skipped_link_says_why(tmp_path):
    p = _primary(tmp_path)
    wt = p / D.CLI_WORKTREE_DIR / "w"
    _git(p, "worktree", "add", "-q", "-b", "worktree-w", str(wt))
    linked, skipped = WT.link_report(p, wt, [".env", "corpus/inbox", "data"])
    assert linked == ["data"] and (wt / "data").is_symlink()
    assert skipped == [{"path": ".env", "reason": WT.LINK_ABSENT},
                       {"path": "corpus/inbox", "reason": WT.LINK_TRACKED}]
    assert not (wt / "corpus" / "inbox").is_symlink() and not (wt / "corpus" / "inbox" / "held.pdf").exists()


def test_the_launch_records_and_prints_a_link_the_checkout_made(tmp_path, capsys):
    p = _primary(tmp_path)
    wt = p / D.CLI_WORKTREE_DIR / "named"
    _git(p, "worktree", "add", "-q", "-b", "worktree-named", str(wt))
    extra = {"worktree_task": "t1", "stem": "s", "source_file": "cc_tasks/s.md", "child_session_id": "c1"}
    rec = DW.name_worktree(p, None, extra, {"cwd": str(wt)}, [".env", "corpus/inbox", "data"], emit=False)
    assert rec["linked"] == ["data"]
    assert rec["links_skipped"] == [{"path": "corpus/inbox", "reason": WT.LINK_TRACKED}]
    err = capsys.readouterr().err
    assert "LINK SKIPPED corpus/inbox" in err and "git rm --cached" in err


def test_the_remedy_works_once_the_directory_is_untracked(tmp_path):
    """factory's question 2: the form for a local inbox shared with every worktree is an UNTRACKED, gitignored
    directory; then no checkout creates it and the declared link is made. The pattern has no trailing slash: the
    link is a symlink, which a `dir/` pattern never matches (gitignore(5)), and git would list its parent untracked."""
    p = _primary(tmp_path)
    _git(p, "rm", "-q", "--cached", "corpus/inbox/.gitkeep")
    (p / ".gitignore").write_text("data/\n.env\n/corpus/inbox\n", encoding="utf-8")
    _git(p, "add", ".gitignore")
    _git(p, "commit", "-q", "-m", "the inbox is local")
    wt = p / D.CLI_WORKTREE_DIR / "w2"
    _git(p, "worktree", "add", "-q", "-b", "worktree-w2", str(wt))
    linked, skipped = WT.link_report(p, wt, ["corpus/inbox"])
    assert linked == ["corpus/inbox"] and skipped == []
    assert (wt / "corpus" / "inbox" / "held.pdf").read_text(encoding="utf-8") == "pdf"
    assert WT.dirty_paths(wt, exclude=linked) == []
