"""A pytest session removes its own basetemp at its end, and only its own (SQ-010 ADDENDUM 02 D3.3).

`tests/pytest_basetemp.py` holds the why, including why pytest's `tmp_path_retention_policy = "none"` is NOT
used: it deletes the live basetemps of concurrent sessions. These run a toy suite in a subprocess with the repo's
real fixture loaded (`-p tests.pytest_basetemp`), in a private temp root (`PYTEST_DEBUG_TEMPROOT`), so nothing here
touches `$TMPDIR/pytest-of-<user>`.
"""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TOY = (
    "def test_passes(tmp_path, tmp_path_factory):\n"
    "    (tmp_path / 'a').write_text('1')\n"
    "    (tmp_path_factory.mktemp('m') / 'b').write_text('2')\n"
    "def test_fails(tmp_path):\n"
    "    (tmp_path / 'c').write_text('3')\n"
    "    assert False\n"
)


def _toy_session(tmp_path: Path, root: Path) -> subprocess.CompletedProcess:
    toy = tmp_path / "toy"
    toy.mkdir(exist_ok=True)
    (toy / "test_toy.py").write_text(TOY, encoding="utf-8")
    env = {**os.environ, "PYTEST_DEBUG_TEMPROOT": str(root),
           "PYTHONPATH": os.pathsep.join(filter(None, [str(REPO), os.environ.get("PYTHONPATH")]))}
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "tests.pytest_basetemp", "-p", "no:randomly",
                           "-p", "no:cacheprovider", "-q", "--rootdir", str(toy), str(toy / "test_toy.py")],
                          cwd=toy, env=env, capture_output=True, text=True)


def _basetemps(root: Path) -> list:
    # `<root>/pytest-of-<user>/` is pytest's per-user root and stays; a basetemp is `pytest-<N>` beneath it
    return sorted(p.name for p in root.glob("pytest-of-*/pytest-*") if p.is_dir() and not p.is_symlink())


def test_a_session_leaves_no_basetemp_passed_or_failed(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    r = _toy_session(tmp_path, root)
    assert "1 failed, 1 passed" in r.stdout, r.stdout + r.stderr
    assert list(root.glob("pytest-of-*")), "the toy session made no temp root: the check below would be vacuous"
    assert _basetemps(root) == [], f"basetemps left behind: {_basetemps(root)}"


def test_another_live_sessions_basetemp_survives_this_sessions_end(tmp_path):
    """The defect "none" has: a sibling basetemp holding a fresh lock (a session still running) is not touched."""
    root = tmp_path / "root"
    user_root = root / f"pytest-of-{getpass.getuser()}"
    live = user_root / "pytest-0"
    live.mkdir(parents=True)
    (live / ".lock").write_text(str(os.getpid()), encoding="utf-8")
    os.utime(live / ".lock", (time.time(), time.time()))
    (live / "in_use.txt").write_text("a running session's file", encoding="utf-8")
    r = _toy_session(tmp_path, root)
    assert "1 failed, 1 passed" in r.stdout, r.stdout + r.stderr
    assert (live / "in_use.txt").is_file(), "this session's end deleted another live session's basetemp"
    assert _basetemps(root) == ["pytest-0"]
