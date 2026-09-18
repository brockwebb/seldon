"""Registration commits the untracked file it registers, path-scoped, and says so on its event.

`ai-readiness-kg/cc_tasks/2026-09-18_registration_commits.md` decision 1. A Desktop
registration used to leave its task file untracked until the standing dispatcher's next pass
committed it (DN-006 ADDENDUM_03 §2), and a pass that finds the lease held exits — so a file
registered while a dispatched session ran stayed untracked for that session's whole life, and
every protected-paths check the session ran saw a file it did not write. The window is closed at
its source: `register_task_file` (the one code path the CLI, the MCP tool and the cadence share)
commits the file by path and records the commit on `artifact_created` as `source_commit`.

Real git and real Neo4j: the behaviour under test is what git's index does with a pathspec
commit, and a fake of either would prove nothing about it.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.cc import cc_group
from seldon.core import dispatch as D
from seldon.mcp_server import seldon_cc_register
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
REL = "cc_tasks/2026-09-18_commit_probe.md"
BODY = "# CC Task: commit probe\n\n**Implements:** DN-006\n\nA task registered untracked.\n"

pytestmark = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A project with one commit already in it, as every real checkout has."""
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"]):
        _git(tmp_path, *args)
    (tmp_path / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: {os.getenv('NEO4J_URI', 'bolt://localhost:7687')}\n"
        f"event_store:\n  path: seldon_events.jsonl\n", encoding="utf-8")
    (tmp_path / "cc_tasks").mkdir()
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "seldon.yaml", "README.md")
    _git(tmp_path, "commit", "-qm", "init")
    (tmp_path / REL).write_text(BODY, encoding="utf-8")
    return tmp_path


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _registration(repo: Path) -> dict:
    lines = (repo / "seldon_events.jsonl").read_text(encoding="utf-8").splitlines()
    created = [json.loads(ln) for ln in lines if ln.strip()]
    created = [e for e in created if e["event_type"] == "artifact_created"
               and e["payload"]["properties"].get("source_file") == REL]
    assert len(created) == 1
    return created[0]


def _node_commit(driver):
    with driver.session(database=NEO4J_DB) as s:
        return s.run("MATCH (t:ResearchTask {source_file: $f}) RETURN t.source_commit AS c",
                     f=REL).single()["c"]


def _files_in(repo: Path, sha: str) -> list[str]:
    return _git(repo, "show", "--name-only", "--pretty=", sha).stdout.split()


def test_an_untracked_registration_is_committed_and_the_event_names_the_commit(
        repo, neo4j_driver):
    before = _head(repo)
    out = seldon_cc_register(REL, project_dir=str(repo), allow_untracked=True)
    assert out.startswith("Registered:"), out

    head = _head(repo)
    assert head != before
    assert D.is_tracked(repo, repo / REL)
    assert _git(repo, "status", "--porcelain", "--", REL).stdout == ""
    # The commit is of that one path, and its message names the task it registers.
    assert _files_in(repo, head) == [REL]
    event = _registration(repo)
    task_id = event["payload"]["artifact_id"]
    assert task_id[:8] in _git(repo, "log", "-1", "--pretty=%s").stdout
    # Full sha, on the registration event itself and on the node it projects to.
    assert event["payload"]["properties"]["source_commit"] == head
    assert _node_commit(neo4j_driver) == head
    # The event store is NOT in that commit: its line is written after the commit it names,
    # and a store holding a running session's lines is never swept up (decision 1).
    assert "seldon_events.jsonl" not in _files_in(repo, head)


def test_nothing_else_in_the_tree_is_swept_into_the_registration_commit(repo, neo4j_driver):
    """A running session's work — untracked, modified or already staged — stays exactly where
    it was. `git commit -- <path>` commits that path's content and nothing else in the index."""
    (repo / "session_work.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "README.md").write_text("edited by the session\n", encoding="utf-8")
    (repo / "staged.txt").write_text("staged by the session\n", encoding="utf-8")
    _git(repo, "add", "staged.txt")

    seldon_cc_register(REL, project_dir=str(repo), allow_untracked=True)

    assert _files_in(repo, _head(repo)) == [REL]
    status = _git(repo, "status", "--porcelain").stdout.splitlines()
    assert "?? session_work.py" in status
    assert " M README.md" in status
    assert "A  staged.txt" in status


def test_a_committed_file_is_left_alone(repo, neo4j_driver):
    _git(repo, "add", REL)
    _git(repo, "commit", "-qm", "author commits the task first")
    before = _head(repo)

    seldon_cc_register(REL, project_dir=str(repo))

    assert _head(repo) == before
    assert _registration(repo)["payload"]["properties"]["source_commit"] is None


def test_a_staged_file_is_left_alone(repo, neo4j_driver):
    """add → register → commit the spec with the RESULT is the sanctioned CLI workflow; a file
    the author has staged is the author's to commit."""
    _git(repo, "add", REL)
    before = _head(repo)

    seldon_cc_register(REL, project_dir=str(repo))

    assert _head(repo) == before
    assert _git(repo, "status", "--porcelain", "--", REL).stdout.startswith("A ")
    assert _registration(repo)["payload"]["properties"]["source_commit"] is None


def test_a_failing_commit_leaves_registration_intact_and_the_file_as_it_was(
        repo, neo4j_driver, tmp_path_factory):
    """A hook (or an index.lock held by a session's own commit) refuses the commit: the task is
    still registered, `source_commit` is null — today's behaviour — and the file is unstaged
    again, because a file left in the index would read as tracked to the dispatcher's sweep,
    which would then never commit it."""
    hooks = tmp_path_factory.mktemp("hooks")
    (hooks / "pre-commit").write_text("#!/bin/sh\necho refused by hook >&2\nexit 1\n",
                                      encoding="utf-8")
    (hooks / "pre-commit").chmod(0o755)
    _git(repo, "config", "core.hooksPath", str(hooks))
    before = _head(repo)

    out = seldon_cc_register(REL, project_dir=str(repo), allow_untracked=True)

    assert out.startswith("Registered:"), out
    assert _head(repo) == before
    assert not D.is_tracked(repo, repo / REL)
    assert _registration(repo)["payload"]["properties"]["source_commit"] is None
    assert _node_commit(neo4j_driver) is None


def test_the_cli_commits_through_the_same_path(repo, neo4j_driver):
    prev = Path.cwd()
    os.chdir(repo)
    try:
        res = CliRunner().invoke(cc_group, ["register", REL, "--allow-untracked"],
                                 catch_exceptions=False)
    finally:
        os.chdir(prev)
    assert res.exit_code == 0, res.output
    assert D.is_tracked(repo, repo / REL)
    assert _registration(repo)["payload"]["properties"]["source_commit"] == _head(repo)
