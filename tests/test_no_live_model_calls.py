"""AD-036-R9: a test never spends unasked. Proven, not asserted.

Since SEL-043 (AD-036-R28) the instrument is the outer session itself: `tests/r9_shim.py`, loaded by
`tests/conftest.py`, puts a recording `claude` first on PATH for every pytest session of this suite (xdist's workers,
git hooks and every subprocess a test starts inherit it) and fails a session in which anything invoked it. Before,
it was a nested pytest over six launcher-adjacent files (66.7 to 95.8 s and about 0.39 GB per run, measured
2026-11-24); the session covers every file on the same commit at no added run time.

seldon's search for tests that can reach a launcher without a fake (PA-001 Part E) found none that call a model: the
dispatcher tests use stub CLIs from the fixture lock, refresh drives a fake CLI and fake npm, and the audit tests
patch `subprocess.run`. So nothing here is gated behind `LIVE_MODEL_CALLS=1`. Every seldon launcher reads its CLI
from the lock (`seldon.models.launch_spec`), and the fixture lock conftest installs names `/nonexistent/claude`, so a
launcher that escaped its fake fails loudly rather than calls; the shim catches the other road, a bare `claude`.

The controls below run a nested pytest with only the shim plugin loaded (`-p tests.r9_shim`) on planted tests: a
planted call fails its session and is named, serially and under xdist; a clean session passes. An empty record in the
real session therefore means "no call", not "the shim was never on PATH", and the first test shows this session is
under it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests import r9_shim

REPO = Path(__file__).resolve().parent.parent
CALLS = "import subprocess\n\ndef test_calls():\n    subprocess.run(['claude', '-p', 'hi'])\n"
CLEAN = "def test_nothing():\n    assert True\n"


def _nested(tmp: Path, body: str, *extra: str) -> subprocess.CompletedProcess:
    planted = tmp / "test_planted.py"
    planted.write_text(body, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in (r9_shim.OPT_IN, r9_shim.ENV_RECORD)}
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "tests.r9_shim",
                           "--rootdir", str(tmp), *extra, str(planted)], cwd=REPO, env=env, capture_output=True,
                          text=True, timeout=300)


@pytest.mark.skipif(bool(os.environ.get(r9_shim.OPT_IN)), reason=f"{r9_shim.OPT_IN}=1 opts out of the shim (R9)")
def test_this_session_runs_under_the_recording_shim():
    record = Path(os.environ[r9_shim.ENV_RECORD])
    assert shutil.which("claude") == str(record.parent / "bin" / "claude")
    assert r9_shim.calls(record) == [], "no test before this one invoked claude"


def test_positive_control_a_planted_call_fails_its_session_and_is_named(tmp_path):
    r = _nested(tmp_path, CALLS)
    assert r.returncode == 1, r.stdout[-1500:] + r.stderr[-1500:]
    assert "AD-036-R9: 1 `claude` invocation(s)" in r.stderr and "-p hi" in r.stderr


def test_positive_control_under_xdist_the_workers_calls_are_recorded(tmp_path):
    r = _nested(tmp_path, CALLS, "-n", "2")
    assert r.returncode == 1, r.stdout[-1500:] + r.stderr[-1500:]
    assert "-p hi" in r.stderr


def test_negative_control_a_clean_session_passes(tmp_path):
    r = _nested(tmp_path, CLEAN)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    assert "AD-036-R9" not in r.stderr
