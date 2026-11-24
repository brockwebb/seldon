"""AD-036-R9's instrument on the outer session (SEL-043, AD-036-R28): every pytest session of this suite runs with a
recording `claude` first on PATH, and a session in which anything invoked it fails, naming the calls.

Before SEL-043 the instrument was a nested pytest over six launcher-adjacent files under the shim (66.7 to 95.8 s and
about 0.39 GB per run of seldon's suite, measured 2026-11-24; in squiddy 1,278 s of a 3,095 s run, three times per
kit pass). Its assertion is a property of the commit, not of the run's order, and the outer session is a larger
subject on the same commit: every test file, not six, at no added run time. The positive controls in
`test_no_live_model_calls.py` show a planted call fails a session, serial and under xdist, and a clean one passes.

How it is wired: the controller installs the shim in `pytest_configure` (os.environ, so xdist's workers, git hooks and
every subprocess a test starts inherit it) and reads the record in `pytest_sessionfinish`. `LIVE_MODEL_CALLS=1`, the
opt-in R9 names, turns it off. A test that replaces PATH wholesale escapes it, as it escaped the nested run.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

#: Where the shim writes one line per invocation; set for the whole session and inherited by every child.
ENV_RECORD = "SELDON_R9_RECORD"
#: R9's opt-in: a session that may call a model on purpose runs without the shim.
OPT_IN = "LIVE_MODEL_CALLS"
#: The shim's exit status: not 0, so a caller that escaped its fake fails loudly as well as being recorded.
SHIM_EXIT = 97


def install() -> Path | None:
    """Put a recording `claude` first on PATH for this process and its children; returns the record's path, or None
    under the opt-in."""
    if os.environ.get(OPT_IN):
        return None
    d = Path(tempfile.mkdtemp(prefix="seldon-r9-"))
    record = d / "claude_calls.txt"
    shim = d / "bin" / "claude"
    shim.parent.mkdir()
    shim.write_text(f"#!/bin/sh\necho \"$@\" >> '{record}'\nexit {SHIM_EXIT}\n", encoding="utf-8")
    shim.chmod(0o755)
    os.environ["PATH"] = f"{shim.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    os.environ[ENV_RECORD] = str(record)
    return record


def calls(record: Path | None) -> list:
    if record is None or not Path(record).is_file():
        return []
    return Path(record).read_text(encoding="utf-8").splitlines()


def pytest_configure(config):
    # The controller only: xdist's workers inherit the controller's environment, so they write the same record.
    if hasattr(config, "workerinput"):
        return
    config._seldon_r9_record = install()


def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):
        return
    made = calls(getattr(session.config, "_seldon_r9_record", None))
    if made:
        sys.stderr.write(f"\nAD-036-R9: {len(made)} `claude` invocation(s) by default in this session, so it fails: "
                         f"{made[:3]}\n")
        session.exitstatus = 1
