"""A Desktop-registered task records its spec hash, and `cc complete` checks it.

`ai-readiness-kg/cc_tasks/2026-09-17_dispatcher_notifies.md` decision 3. `seldon_cc_register`
(the MCP tool every Desktop registration goes through) wrote no `file_hash`, so every
`seldon cc complete` on a Desktop-authored task printed "Task has no registered file_hash.
Skipping immutability check." — the "immutable once written" line was unenforced for exactly
the files the Desktop writes. `allow_untracked` is a statement about git recoverability; it was
never a reason to skip hashing the bytes on disk.

The sequence under test: register untracked, which now commits the file by path at registration
(`ai-readiness-kg/cc_tasks/2026-09-18_registration_commits.md` decision 1 — before that, the
dispatcher's `D.commit_paths` did it on its next pass), then complete. Neither commit changes the
file's bytes, and the hash must survive either.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.cc import HASH_SCOPE_SPEC, _spec_hash, cc_group
from seldon.core import dispatch as D
from seldon.mcp_server import seldon_cc_register
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
REL = "cc_tasks/2026-09-17_hash_probe.md"
BODY = "# CC Task: hash probe\n\n**Implements:** DN-006\n\nA task whose spec is hashed.\n"

pytestmark = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    (tmp_path / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: {os.getenv('NEO4J_URI', 'bolt://localhost:7687')}\n"
        f"event_store:\n  path: seldon_events.jsonl\n", encoding="utf-8")
    (tmp_path / "cc_tasks").mkdir()
    (tmp_path / REL).write_text(BODY, encoding="utf-8")
    return tmp_path


def _node(driver, rel):
    with driver.session(database=NEO4J_DB) as s:
        return s.run("MATCH (t:ResearchTask {source_file: $f}) "
                     "RETURN t.file_hash AS fh, t.hash_scope AS scope, t.created_by AS by",
                     f=rel).single()


def _complete(repo: Path):
    prev = Path.cwd()
    os.chdir(repo)
    try:
        return CliRunner().invoke(cc_group, ["complete", REL], catch_exceptions=False)
    finally:
        os.chdir(prev)


def _register_and_commit(repo: Path, neo4j_driver):
    out = seldon_cc_register(filepath=REL, project_dir=str(repo), allow_untracked=True)
    assert "Registered" in out, out
    node = _node(neo4j_driver, REL)
    assert D.is_tracked(repo, repo / REL), "registration did not commit the untracked file"
    committed = subprocess.run(["git", "show", f"HEAD:{REL}"], cwd=repo, check=True,
                               capture_output=True).stdout
    assert (repo / REL).read_bytes() == committed == BODY.encode("utf-8"), (
        "the registration's commit changed the bytes")
    return node


def test_an_untracked_desktop_registration_records_the_spec_hash(repo, neo4j_driver):
    node = _register_and_commit(repo, neo4j_driver)
    assert node["fh"] == _spec_hash(repo / REL)
    assert node["scope"] == HASH_SCOPE_SPEC
    assert node["by"] == "desktop"


def test_complete_runs_the_hash_check_on_a_desktop_registered_task(repo, neo4j_driver):
    _register_and_commit(repo, neo4j_driver)
    # A RESULT-style append below a Findings heading is allowed by the spec-scoped hash.
    with (repo / REL).open("a", encoding="utf-8") as fh:
        fh.write("\n## Findings\n\nappended after execution\n")
    res = _complete(repo)
    assert res.exit_code == 0, res.output
    assert "no registered file_hash" not in res.output
    assert "Completed:" in res.output


def test_complete_refuses_a_desktop_registered_task_whose_spec_changed(repo, neo4j_driver):
    _register_and_commit(repo, neo4j_driver)
    (repo / REL).write_text(BODY.replace("A task", "An EDITED task"), encoding="utf-8")
    res = _complete(repo)
    assert res.exit_code == 1
    assert "SPEC has been modified since registration" in res.output
