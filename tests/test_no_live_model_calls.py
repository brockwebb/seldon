"""AD-036-R9: a test never spends unasked. Proven, not asserted: the launcher-adjacent test files
run in a nested pytest with a recording `claude` first on PATH, and the record must be empty.

seldon's search for tests that can reach a launcher without a fake (PA-001 Part E) found none that
call a model: the dispatcher tests use stub CLIs from the fixture lock, refresh drives a fake CLI
and fake npm, and the audit tests patch `subprocess.run`. So nothing here is gated behind
`LIVE_MODEL_CALLS=1`; this test is what keeps it that way. The positive control plants a test
that does invoke `claude` and shows the same harness records it, so an empty record means
"no call", not "the shim was never on PATH".

Every seldon launcher reads its CLI from the lock (`seldon.models.launch_spec`), and the fixture
lock conftest installs names `/nonexistent/claude`, so a launcher that escaped its fake would fail
loudly rather than call; the PATH shim catches the other road, a bare `claude` from PATH.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
#: The files that touch a launcher, the lock or the CLI. Nested because the full suite inside one
#: test would double the suite's wall clock.
LAUNCHER_ADJACENT = ["test_models.py", "test_audit_dispatch.py", "test_mcp_audit.py",
                     "test_dispatch.py", "test_prior_art.py", "test_cc_register_commits.py"]


def _shim(tmp: Path) -> tuple[Path, Path]:
    bindir, record = tmp / "shimbin", tmp / "claude_calls.txt"
    bindir.mkdir()
    shim = bindir / "claude"
    shim.write_text(f"#!/bin/sh\necho \"$@\" >> {record}\nexit 97\n")
    shim.chmod(0o755)
    return bindir, record


def _run(files: list, bindir: Path, cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "LIVE_MODEL_CALLS"}
    env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "-p", "no:xdist", *map(str, files)], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=600)


def test_the_launcher_adjacent_suite_makes_zero_claude_calls(tmp_path):
    bindir, record = _shim(tmp_path)
    r = _run([TESTS / f for f in LAUNCHER_ADJACENT], bindir, TESTS.parent)
    assert r.returncode in (0, 1), r.stdout[-2000:] + r.stderr[-2000:]
    calls = record.read_text().splitlines() if record.exists() else []
    assert calls == [], f"{len(calls)} claude invocation(s) by default: {calls[:3]}"


def test_positive_control_a_planted_call_is_recorded(tmp_path):
    bindir, record = _shim(tmp_path)
    planted = tmp_path / "test_planted.py"
    planted.write_text("import subprocess\n\ndef test_calls():\n"
                       "    subprocess.run(['claude', '-p', 'hi'])\n")
    _run([planted], bindir, tmp_path)
    assert record.read_text().splitlines() == ["-p hi"]
