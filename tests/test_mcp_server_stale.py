"""SEL-006 Part B: the MCP server records what it loaded and refuses when the checkout moved.

Issue fed23c36: on 2026-10-14 a seldon-mcp started before MODEL-003's merge answered
`seldon_cc_register` with `model_not_in_lock` (it parsed the new registry with the old loader).
squiddy DN-046 R-202: a process records what it loaded and re-checks it. These tests plant the
change after the server's state was captured, and show the tool answers `server_stale` and never
reaches the underlying error; the last one takes the guard away and shows that error is what was
underneath.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import seldon.mcp_server as m
from seldon import models
from seldon.core import loaded_state as L
from tests.testdb import TEST_DATABASE

REAL_MODELS = Path(models.__file__).resolve().parent.parent / "models"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A stand-in for the seldon checkout the server imported: code, registry and seldon.yaml."""
    co = tmp_path / "co"
    (co / "seldon").mkdir(parents=True)
    (co / "models").mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(co, *args)
    (co / "seldon" / "__init__.py").write_text("")
    for f in ("registry.yaml", "models.lock.yaml"):
        shutil.copy(REAL_MODELS / f, co / "models" / f)
    (co / "seldon.yaml").write_text("project: {name: co}\n")
    (co / "seldon_events.jsonl").write_text("")
    _git(co, "add", "-A")
    _git(co, "commit", "-qm", "init")
    return co


def _capture(co: Path):
    return L.capture("seldon-mcp", co, ["seldon"], [co / "models" / "registry.yaml", co / "seldon.yaml"])


MESSAGE = re.compile(r"^server_stale: seldon-mcp loaded ([0-9a-f]{7}) on .+; the checkout is at ([0-9a-f]{7}) "
                     r"\(.+ changed since\)\. Restart the MCP server \(restart Claude Desktop\)\.$")


def test_a_code_change_after_load_is_stale_and_names_both_heads(checkout):
    loaded = _capture(checkout)
    assert L.stale(loaded) is None
    (checkout / "seldon" / "x.py").write_text("x = 1\n")
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-qm", "merge new code")
    msg = L.stale(loaded)
    mm = MESSAGE.match(msg or "")
    assert mm, msg
    assert mm.group(1) == loaded.head[:7] and mm.group(2) == _git(checkout, "rev-parse", "--short=7", "HEAD")
    assert "seldon/" in msg


def test_a_commit_of_the_event_store_alone_is_not_stale(checkout):
    """The tools commit their own journal lines, so HEAD moves on nearly every Desktop write; the code
    the process runs has not changed, and refusing then would refuse every session's second call."""
    loaded = _capture(checkout)
    (checkout / "seldon_events.jsonl").write_text('{"event_type": "x"}\n')
    _git(checkout, "commit", "-qam", "record: a tool's own line")
    assert L.stale(loaded) is None


def test_an_edited_registry_or_seldon_yaml_is_stale_without_a_commit(checkout):
    loaded = _capture(checkout)
    (checkout / "models" / "registry.yaml").write_text("roles: [unclosed\n")
    assert "registry.yaml" in (L.stale(loaded) or "")
    shutil.copy(REAL_MODELS / "registry.yaml", checkout / "models" / "registry.yaml")
    assert L.stale(loaded) is None
    (checkout / "seldon.yaml").write_text("project: {name: moved}\n")
    assert "seldon.yaml" in (L.stale(loaded) or "")


def test_not_a_checkout_is_never_stale(tmp_path):
    assert L.capture("seldon-mcp", tmp_path, ["seldon"], []) is None
    assert L.stale(None) is None


@pytest.fixture
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "cc_tasks").mkdir(parents=True)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(proj, *args)
    (proj / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {TEST_DATABASE}\n  uri: {os.getenv('NEO4J_URI', 'bolt://localhost:7687')}\n"
        f"event_store:\n  path: seldon_events.jsonl\n")
    (proj / "cc_tasks" / "t.md").write_text("# CC Task: t\n\n**Implements:** DN-006\n**Model:** primary\n\nx\n")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    return proj


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_a_mutating_tool_reaches_the_current_code_and_a_read_only_tool_refuses(checkout, project, monkeypatch):
    """Rewritten by FRICTION-001 Part C (AD-038-R3). SEL-006 refused EVERY tool after a merge and asked for a Desktop
    restart. A mutating tool now runs the checkout's current code in a fresh process, so `seldon_cc_register` answers
    what that code answers on this registry (fed23c36's shape, `model_not_in_lock`), never `server_stale`; a
    read-only tool still refuses, and its message asks for no restart."""
    monkeypatch.setattr(m, "_LOADED", _capture(checkout))
    monkeypatch.setenv(models.MODELS_HOME_ENV, str(checkout / "models"))
    (checkout / "seldon" / "models.py").write_text("# the new loader\n")
    reg = yaml.safe_load((checkout / "models" / "registry.yaml").read_text())
    reg["roles"]["primary"] = {"family": None}
    (checkout / "models" / "registry.yaml").write_text(yaml.safe_dump(reg))
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-qm", "merge MODEL-003")

    out = m.seldon_cc_register("cc_tasks/t.md", project_dir=str(project))
    assert "server_stale" not in out, out
    assert "model_not_in_lock" in out and "family None is not one of" in out, out

    read = m.seldon_task_list(project_dir=str(project))
    assert read.startswith("Error: server_stale: seldon-mcp loaded "), read
    assert "restart" not in read.lower(), read


def test_every_tool_the_server_registers_is_guarded_or_runs_head():
    """Rewritten by FRICTION-001 Part C: a read-only tool is stale-guarded, every other tool runs HEAD."""
    import asyncio
    names = {t.name for t in asyncio.run(m.mcp.list_tools())}
    assert names
    codes = {m._refuses_when_stale(lambda: None).__code__, m._runs_head(lambda: None).__code__}
    for name in names:
        assert getattr(m, name).__code__ in codes, name
