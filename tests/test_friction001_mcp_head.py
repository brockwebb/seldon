"""FRICTION-001 Part C (AD-038-R3): the MCP server runs HEAD.

Before this, any merge under `seldon/` made every seldon-mcp tool answer `server_stale` and ask for a Claude Desktop
restart (three restarts in three days; AD-038 §1 mechanism 3). Reloading in place cannot fix that (`importlib.reload`
does not rebind names imported with `from ... import`), so each mutating tool now runs `python -P -m seldon mcp-call
<tool>` in a fresh process on the checkout's current code. MCP-001 extended that to the read-only tools and removed
the stale guard; its tests are `tests/test_mcp001_fresh_process.py`, and the ones here were rewritten to match.

The plant is the one SEL-006 used: a temp checkout stands in for the code the server loaded, and a commit under its
`seldon/` moves it. The second test goes further and points the child at a copy of the package whose
`seldon_task_create` says something the loaded code never says, so the answer proves which code ran.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import seldon.mcp_server as m
from tests.testdb import TEST_DATABASE

pytestmark = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

SELDON_PKG = Path(m.__file__).resolve().parent


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A checkout holding a copy of the seldon package: what the server 'loaded'."""
    co = tmp_path / "co"
    co.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(co, *args)
    shutil.copytree(SELDON_PKG, co / "seldon", ignore=shutil.ignore_patterns("__pycache__"))
    (co / "seldon.yaml").write_text("project: {name: co}\n")
    _git(co, "add", "-A")
    _git(co, "commit", "-qm", "init")
    return co


@pytest.fixture
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(proj, *args)
    (proj / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {TEST_DATABASE}\n  uri: {os.getenv('NEO4J_URI', 'bolt://localhost:7687')}\n"
        f"event_store:\n  path: seldon_events.jsonl\n")
    (proj / "seldon_events.jsonl").write_text("")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    return proj


def _merge_under_seldon(co: Path, marker: str = "") -> None:
    """A merge that moves `seldon/`. With a marker, the new code's `seldon_task_create` answers with it."""
    path = co / "seldon" / "mcp_server.py"
    text = path.read_text()
    if marker:
        # Indentation-free anchor: the tool's body moves when it is refactored (SEL-007).
        old = 'f"Created ResearchTask: '
        assert text.count(old) == 1
        text = text.replace(old, f'"{marker} " f"Created ResearchTask: ', 1)
    path.write_text(text + "\n# merged after the server loaded\n")
    _git(co, "add", "-A")
    _git(co, "commit", "-qm", "merge under seldon/")


def test_after_a_merge_a_mutating_tool_and_a_read_tool_both_answer(checkout, project, monkeypatch):
    monkeypatch.setattr(m, "_repo", lambda: checkout)
    _merge_under_seldon(checkout)

    wrote = m.seldon_task_create("a task after the merge", project_dir=str(project))
    assert "server_stale" not in wrote, wrote
    assert "Created ResearchTask" in wrote, wrote

    read = m.seldon_task_list(project_dir=str(project))
    assert "server_stale" not in read, read
    assert "a task after the merge" in read, read


def test_the_mutating_tool_runs_the_checkouts_current_code(checkout, project, monkeypatch):
    """The child imports the repository as it stands now: the merged code's answer comes back."""
    monkeypatch.setattr(m, "_repo", lambda: checkout)
    _merge_under_seldon(checkout, marker="HEAD-CODE-RAN")
    out = m.seldon_task_create("proof of which code ran", project_dir=str(project))
    assert out.startswith("HEAD-CODE-RAN Created ResearchTask"), out
    # The in-process body is the loaded code, which never says it.
    assert "HEAD-CODE-RAN" not in Path(m.__file__).read_text()


def test_a_child_that_cannot_answer_is_reported_not_swallowed(monkeypatch):
    out = m._run_in_head("seldon_no_such_tool", {})
    assert out.startswith("Error: seldon_no_such_tool exited "), out
    assert "no seldon-mcp tool named" in out, out


def test_every_tool_runs_head():
    """Rewritten by MCP-001: no tool is read-only guarded any longer; every one runs HEAD."""
    import asyncio
    names = {t.name for t in asyncio.run(m.mcp.list_tools())}
    head = m._runs_head(lambda: None).__code__
    assert {n for n in names if getattr(m, n).__code__ is head} == names
    assert "seldon_dispatch_redrive" in names
