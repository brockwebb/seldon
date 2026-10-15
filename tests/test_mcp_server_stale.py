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
def test_the_tool_answers_server_stale_and_never_reaches_the_registry_error(checkout, project, monkeypatch):
    monkeypatch.setattr(m, "_LOADED", _capture(checkout))
    monkeypatch.setenv(models.MODELS_HOME_ENV, str(checkout / "models"))
    # The plant: a merge moves the code and the registry under the running server (fed23c36's shape).
    (checkout / "seldon" / "models.py").write_text("# the new loader\n")
    # The registry shape the stale loader refused: a role whose family it reads as None.
    reg = yaml.safe_load((checkout / "models" / "registry.yaml").read_text())
    reg["roles"]["primary"] = {"family": None}
    (checkout / "models" / "registry.yaml").write_text(yaml.safe_dump(reg))
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-qm", "merge MODEL-003")

    out = m.seldon_cc_register("cc_tasks/t.md", project_dir=str(project))

    assert out.startswith("Error: server_stale: seldon-mcp loaded "), out
    assert "Restart the MCP server (restart Claude Desktop)." in out
    assert "model_not_in_lock" not in out
    # Removal check: without the guard the same call reaches the error the stale process gave.
    under = m.seldon_cc_register.__wrapped__("cc_tasks/t.md", project_dir=str(project))
    assert "model_not_in_lock" in under and "family None is not one of" in under, under


def test_every_tool_the_server_registers_is_guarded():
    import asyncio
    names = {t.name for t in asyncio.run(m.mcp.list_tools())}
    assert names
    for name in names:
        fn = getattr(m, name)
        assert fn.__code__ is m._refuses_when_stale(lambda: None).__code__, name
