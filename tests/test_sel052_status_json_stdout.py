"""SEL-052 Part B: factory's 2026-11-26 filing item 2, "`seldon dispatch status --json` writes a warning line into the
stream that carries its JSON" (SEL-047 Part E item 2).

Read from the code, the warning (`_cross_waits`' unreadable-graph line) is written with `click.echo(..., err=True)`:
stderr. What SEL-047 saw was Click 8.1's `CliRunner()`, whose default `mix_stderr=True` folds stderr into
`result.output`, the stream the test parsed. A reader of the real command's stdout gets JSON alone; this pins it.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from seldon.core import cross_project as X
from tests.test_sel018_relative_dispatch_paths import CAP, _sibling, _status_project


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_status_json_keeps_its_warnings_off_stdout(tmp_path, neo4j_driver, monkeypatch):
    from seldon.commands.dispatch import dispatch_group
    _sibling(tmp_path)
    p, wt = _status_project(tmp_path, neo4j_driver)

    def unreadable(project_dir, tasks, on_error=None):
        on_error("cross-project wait: graph of `elsewhere` could not be read (plant)")
        return {}

    monkeypatch.setattr(X, "unsatisfied_waits", unreadable)
    monkeypatch.chdir(wt)
    res = CliRunner(mix_stderr=False).invoke(dispatch_group, ["status", "--json"], catch_exceptions=False)
    assert res.exit_code == 0, res.stdout + res.stderr
    assert json.loads(res.stdout)["standing_band"] == CAP
    assert "could not be read (plant)" in res.stderr
