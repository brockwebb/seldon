"""SEL-037 Part A: why `dispatch.worktree_links` cannot carry a squiddy graph's release out of a worktree build.

The task asked for `graphs/seldon-biblio/{work,exports,corpus/parsed}` in `dispatch.worktree_links`, so that a build
in any later worktree writes the primary's directories, with the test "a worktree build's served export is the
primary's file", and said: if `worktree_links` cannot carry this, say why and stop the Part. These tests are the why.

1. `exports/` holds TRACKED files (EXPORT_VERSIONS.md, the diff and host-posture reports), so every worktree checkout
   creates the directory, and `worktree.link` skips a destination that exists (seldon/core/worktree.py `link`). The
   directory entry is a silent no-op.
2. The established workaround (hazbrief HB-73 Part A, aacps: link the served export FILE) does carry the served copy:
   squiddy's export publishes it with `shutil.copyfile(versioned, latest)` (squiddy/export.py), which writes through
   the link into the primary. But the VERSIONED export, the file a library receipt names (`release <file>`) and
   `prior_art.Library.export_path` must find on disk in the primary (receipts are verified at the primary,
   `corpus_anchor`), has a new name every release, so no configured link can name it in advance; it stays in the
   worktree's real `exports/` and is discarded with the worktree. Linking work/ and the served file would leave the
   primary serving a release whose receipts fail `release_unavailable`, which holds every task the note governs.

So no seldon-biblio link is declared (seldon.yaml `dispatch` comment), and a worktree build's release is installed
into the primary by copying its gitignored outputs, the route SEL-036 staged and SEL-037 Part A ran.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from seldon.core import worktree as WT


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """A primary checkout with a graph whose exports/ holds a tracked report and a gitignored served export, a served
    index under the gitignored work/, and one linked worktree `wt`."""
    p = tmp_path / "primary"
    p.mkdir()
    _git(p, "init", "-q", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    g = p / "graphs" / "g"
    (g / "exports").mkdir(parents=True)
    # squiddy's generated ignore rules for a graph (graphs/seldon-biblio/.gitignore), the two that matter here
    (g / ".gitignore").write_text("exports/*.json\nwork\n", encoding="utf-8")
    (g / "exports" / "EXPORT_VERSIONS.md").write_text("| release |\n", encoding="utf-8")
    _git(p, "add", "-A")
    _git(p, "commit", "-q", "-m", "init")
    (g / "exports" / "g_graph.json").write_text('{"release": "r1"}', encoding="utf-8")
    (g / "exports" / "g_graph_r1_2026-11-09.json").write_text('{"release": "r1"}', encoding="utf-8")
    (g / "work" / "index").mkdir(parents=True)
    (g / "work" / "index" / "index_manifest.json").write_text('{"release": "r1"}', encoding="utf-8")
    wt = tmp_path / "wt"
    assert _git(p, "worktree", "add", "-q", "-b", "worktree-x", str(wt)).returncode == 0
    return p, wt


def test_the_exports_directory_is_never_linked_because_a_checkout_creates_it(repo):
    p, wt = repo
    assert (wt / "graphs/g/exports/EXPORT_VERSIONS.md").is_file()      # the tracked report put it there
    assert WT.link(p, wt, ["graphs/g/exports"]) == []
    assert not (wt / "graphs/g/exports").is_symlink()
    assert not (wt / "graphs/g/exports/g_graph.json").exists()


def test_work_and_the_served_file_link_but_the_versioned_export_stays_in_the_worktree(repo):
    p, wt = repo
    linked = WT.link(p, wt, ["graphs/g/work", "graphs/g/exports/g_graph.json"])
    assert linked == ["graphs/g/work", "graphs/g/exports/g_graph.json"]
    # A build in the worktree, as squiddy's export stage writes it: a new versioned file, then the served copy.
    versioned = wt / "graphs/g/exports/g_graph_r2_2026-11-11.json"
    versioned.write_text('{"release": "r2"}', encoding="utf-8")
    shutil.copyfile(versioned, wt / "graphs/g/exports/g_graph.json")
    (wt / "graphs/g/work/index/index_manifest.json").write_text('{"release": "r2"}', encoding="utf-8")
    # The primary now serves r2 and its index names r2 ...
    assert (p / "graphs/g/exports/g_graph.json").read_text(encoding="utf-8") == '{"release": "r2"}'
    assert (p / "graphs/g/work/index/index_manifest.json").read_text(encoding="utf-8") == '{"release": "r2"}'
    # ... but the file a receipt for r2 names is not in the primary's exports directory: it dies with the worktree.
    assert not (p / "graphs/g/exports" / versioned.name).exists()
