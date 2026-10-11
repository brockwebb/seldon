"""This session's pytest basetemp is removed when the session ends (SQ-010 ADDENDUM 02 D3.3).

squiddy/docs/evidence/sq010/disk_incident.md: on 2026-10-11 the suites' basetemps under `$TMPDIR/pytest-of-<user>`
held about 1.1 GB when the data volume filled. pytest's default retention keeps the last three sessions'
directories, and the many suites on this machine (squiddy's, seldon's, the dispatcher's gates) each kept theirs.

**Why not pytest's own `tmp_path_retention_policy = "none"`.** Under "none" a session takes no lock on its own
basetemp (`_pytest/pathlib.py make_numbered_dir_with_cleanup`: "Only lock the current dir when keep is not 0"), and
at exit it deletes every unlocked numbered basetemp in the shared root, which includes the directories of other
pytest sessions still running. Found 2026-10-11 by SQ-010 ADDENDUM 02 D3: a seldon session under "none" lost its
live test project mid-test, and a running squiddy test (test_r160) lost its files. So pytest's default retention
and its lock stay, and this fixture removes ONLY this session's own basetemp, after its last test.

Registered by `tests/conftest.py` (imported there), and loadable on its own with `-p tests.pytest_basetemp`, which
is how `tests/test_pytest_tmp_retention.py` runs it against a toy suite.
"""
from __future__ import annotations

import shutil

import pytest


@pytest.fixture(scope="session", autouse=True)
def _basetemp_removed_at_session_end(request, tmp_path_factory):
    yield
    if request.config.option.basetemp is not None:
        return  # a --basetemp the user gave is theirs to keep
    # No ignore_errors: a basetemp that cannot be removed is a leak, and a leak is reported, not swallowed.
    shutil.rmtree(tmp_path_factory.getbasetemp())
