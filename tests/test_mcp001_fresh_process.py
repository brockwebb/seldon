"""MCP-001 Part A: every seldon-mcp tool, reads included, runs the checkout's current code in a fresh process.

AD-038-R3 moved the mutating tools into `python -P -m seldon mcp-call <tool>` and left six read-only tools in process
behind SEL-006's stale guard, which refused with `server_stale` after every merge under `seldon/` until Desktop was
restarted (four restarts on 2026-10-17; AD-038 ADDENDUM 01). These tests fail on the code before MCP-001: a read tool
answered from the code the server loaded (or refused), and its answer named no code.

The plant is FRICTION-001's: a temp checkout holds a copy of the package and stands in for the server's repository
(`_repo`); a commit under its `seldon/` after the server imported moves HEAD, and the merged code says something the
loaded code never says, so the answer proves which code ran.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import seldon.mcp_server as m
from tests.testdb import TEST_DATABASE

SELDON_PKG = Path(m.__file__).resolve().parent
MARKER = "MOVED-HEAD-CODE-ANSWERED"
#: The tools that stayed in process before MCP-001.
FORMERLY_IN_PROCESS = {"seldon_go", "seldon_task_list", "seldon_query", "seldon_decision_show",
                       "seldon_decision_list", "seldon_decision_check"}
CODE_LINE = re.compile(r"\n\ncode: ([0-9a-f]{7})( \+ uncommitted changes under seldon/)?$")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _init(repo: Path) -> None:
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(repo, *args)


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch) -> Path:
    """A checkout holding a copy of the seldon package, standing in for the server's repository."""
    co = tmp_path / "co"
    co.mkdir()
    _init(co)
    shutil.copytree(SELDON_PKG, co / "seldon", ignore=shutil.ignore_patterns("__pycache__"))
    (co / "seldon.yaml").write_text("project: {name: co}\n")
    _git(co, "add", "-A")
    _git(co, "commit", "-qm", "init")
    monkeypatch.setattr(m, "_repo", lambda: co)
    return co


@pytest.fixture
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    _init(proj)
    (proj / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {TEST_DATABASE}\n  uri: {os.getenv('NEO4J_URI', 'bolt://localhost:7687')}\n"
        f"event_store:\n  path: seldon_events.jsonl\n")
    (proj / "seldon_events.jsonl").write_text("")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    return proj


def _merge_marker_into_task_list(co: Path) -> str:
    """A merge under `seldon/` after the server loaded: the new `seldon_task_list` answers with MARKER."""
    path = co / "seldon" / "mcp_server.py"
    text = path.read_text()
    old = 'return f"No ResearchTasks found (filter: {state_filter})"'
    assert text.count(old) == 1
    path.write_text(text.replace(old, f'return f"{MARKER} No ResearchTasks found (filter: {{state_filter}})"'))
    _git(co, "add", "-A")
    _git(co, "commit", "-qm", "merge under seldon/")
    return _git(co, "rev-parse", "--short=7", "HEAD")


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_a_read_tool_answers_from_a_checkout_whose_head_moved_after_the_server_started(checkout, project):
    loaded = _git(checkout, "rev-parse", "--short=7", "HEAD")
    moved = _merge_marker_into_task_list(checkout)
    assert moved != loaded

    out = m.seldon_task_list(project_dir=str(project))
    assert out.startswith(f"{MARKER} No ResearchTasks found"), out
    # The note names the code that answered: the moved HEAD, not the one the server started on.
    mm = CODE_LINE.search(out)
    assert mm and mm.group(1) == moved, out
    assert MARKER not in Path(m.__file__).read_text()


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_no_tool_result_carries_server_stale_after_a_merge(checkout, project):
    """Every formerly in-process tool, called after a merge under `seldon/`: none refuses, each names its code."""
    moved = _merge_marker_into_task_list(checkout)
    calls = {
        "seldon_go": {"brief": True},
        "seldon_task_list": {},
        "seldon_query": {"cypher": "MATCH (n) RETURN count(n) AS n"},
        "seldon_decision_show": {"record_id": "seldon:AD-000"},
        "seldon_decision_list": {},
        "seldon_decision_check": {},
    }
    assert set(calls) == FORMERLY_IN_PROCESS
    for name, kwargs in calls.items():
        out = getattr(m, name)(project_dir=str(project), **kwargs)
        assert "server_stale" not in out, (name, out)
        mm = CODE_LINE.search(out)
        assert mm and mm.group(1) == moved, (name, out[-300:])


def test_every_registered_tool_runs_in_a_fresh_process():
    names = {t.name for t in asyncio.run(m.mcp.list_tools())}
    assert FORMERLY_IN_PROCESS <= names
    head = m._runs_head(lambda: None).__code__
    assert {n for n in names if getattr(m, n).__code__ is not head} == set()
    assert set(m.RAW_TOOLS) == names


def test_the_server_process_imports_nothing_from_seldon_core_to_answer_a_call(tmp_path):
    """The server keeps only transport and marshalling: importing it and answering a call loads no `seldon.core`."""
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "seldon.yaml").write_text("project: {name: p}\n")
    probe = ("import sys, seldon.mcp_server as m\n"
             f"out = m.seldon_decision_check(project_dir={str(proj)!r})\n"
             "assert '\\n\\ncode: ' in out, out\n"
             "print(sorted(k for k in sys.modules if k.startswith('seldon.core')))\n")
    env = {**os.environ,
           "PYTHONPATH": os.pathsep.join([str(SELDON_PKG.parent), *filter(None, [os.environ.get("PYTHONPATH")])])}
    env.pop("SELDON_MCP_CHILD", None)
    r = subprocess.run([sys.executable, "-P", "-c", probe], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.strip().splitlines()[-1] == "[]", r.stdout


def test_the_code_line_names_a_directory_that_is_not_a_checkout(tmp_path):
    from seldon.commands.mcp_call import code_line
    assert code_line(tmp_path) == f"code: unknown ({tmp_path} is not a git checkout)"


def test_the_code_line_names_uncommitted_edits_under_seldon(checkout):
    from seldon.commands.mcp_call import code_line
    sha = _git(checkout, "rev-parse", "--short=7", "HEAD")
    assert code_line(checkout) == f"code: {sha}"
    (checkout / "seldon" / "x.py").write_text("x = 1\n")
    assert code_line(checkout) == f"code: {sha} + uncommitted changes under seldon/"
