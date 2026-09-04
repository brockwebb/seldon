"""The MCP CC tools enforce the same untracked-file guard as the CLI.

`seldon cc register` / `cc complete` gained a git-tracking guard (task
`868d6bb0`), but `seldon_cc_register` / `seldon_cc_complete` duplicate that
logic in `seldon/mcp_server.py` and originally bypassed it — so a Desktop
session could still register an unrecoverable task file after the CLI stopped
allowing it. A guard with an open side door is not a guard.

These tests pin both halves of that: the MCP decision matches the CLI's status
predicate, and the helper is not itself exposed as an MCP tool.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from seldon.commands.cc import (
    GIT_IGNORED,
    GIT_NO_REPO,
    GIT_TRACKED,
    GIT_UNTRACKED,
    _git_tracking_status,
)
from seldon.mcp_server import _mcp_git_tracking_error


def _init_repo(path: Path) -> None:
    """Create a git work tree at `path` with identity configured."""
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T")):
        subprocess.run(
            ["git", "-C", str(path), "config", key, value], check=True
        )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_repo(tmp_path)
    return tmp_path


def _task_file(repo: Path, name: str = "cc_tasks/t.md") -> Path:
    task = repo / name
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text("# CC Task — probe\n")
    return task


class TestMcpGuardMatchesCliDecision:
    """The MCP helper refuses exactly when the CLI's status predicate says so."""

    def test_tracked_file_is_allowed(self, repo):
        task = _task_file(repo)
        subprocess.run(["git", "-C", str(repo), "add", str(task)], check=True)
        assert _git_tracking_status(repo, task) == GIT_TRACKED
        assert _mcp_git_tracking_error(
            repo, task, "cc_tasks/t.md", "seldon_cc_register", False
        ) is None

    def test_untracked_file_is_refused(self, repo):
        task = _task_file(repo)
        assert _git_tracking_status(repo, task) == GIT_UNTRACKED
        error = _mcp_git_tracking_error(
            repo, task, "cc_tasks/t.md", "seldon_cc_register", False
        )
        assert error is not None
        assert "refusing to register an untracked task file" in error
        assert GIT_UNTRACKED in error

    def test_ignored_file_is_refused_and_says_so(self, repo):
        (repo / ".gitignore").write_text("cc_tasks/\n")
        task = _task_file(repo)
        assert _git_tracking_status(repo, task) == GIT_IGNORED
        error = _mcp_git_tracking_error(
            repo, task, "cc_tasks/t.md", "seldon_cc_register", False
        )
        assert error is not None
        # The ignored case is the one that produced the 37 orphans, and its
        # remedy differs from plain-untracked, so it must be named distinctly.
        assert GIT_IGNORED in error
        assert ".gitignore" in error

    def test_no_repo_is_refused(self, tmp_path):
        task = _task_file(tmp_path)
        assert _git_tracking_status(tmp_path, task) == GIT_NO_REPO
        error = _mcp_git_tracking_error(
            tmp_path, task, "cc_tasks/t.md", "seldon_cc_complete", False
        )
        assert error is not None
        assert GIT_NO_REPO in error


class TestOverride:
    """`allow_untracked` opens the door, and the message names the way back."""

    def test_override_allows_untracked(self, repo):
        task = _task_file(repo)
        assert _mcp_git_tracking_error(
            repo, task, "cc_tasks/t.md", "seldon_cc_register", True
        ) is None

    def test_refusal_names_the_mcp_override_not_the_cli_flag(self, repo):
        task = _task_file(repo)
        error = _mcp_git_tracking_error(
            repo, task, "cc_tasks/t.md", "seldon_cc_register", False
        )
        # An MCP caller cannot pass `--allow-untracked`; telling them to would
        # be a dead end.
        assert "allow_untracked=True" in error
        assert "--allow-untracked" not in error
        assert "seldon_cc_register" in error


class TestToolSurface:
    """The tools expose the override; the helper is not itself a tool."""

    @pytest.mark.parametrize(
        "tool_name", ["seldon_cc_register", "seldon_cc_complete"]
    )
    def test_tool_accepts_allow_untracked(self, tool_name):
        import inspect

        import seldon.mcp_server as mcp_server

        tool = getattr(mcp_server, tool_name)
        fn = getattr(tool, "fn", tool)
        assert "allow_untracked" in inspect.signature(fn).parameters

    def test_helper_is_not_registered_as_a_tool(self):
        import seldon.mcp_server as mcp_server

        # A bare `@mcp.tool()` left above the helper would silently publish an
        # internal predicate as a callable tool.
        assert not hasattr(mcp_server._mcp_git_tracking_error, "fn")


class TestToolRefusesEndToEnd:
    """The guard fires through the actual tool, not just the helper.

    Wiring is the part that regresses: the helper can be correct while a tool
    forgets to call it. These drive the tool itself.

    They need Neo4j because the tools resolve the project — and therefore open a
    driver — before reaching the guard. That ordering is worth knowing: a
    refusal still costs a connection, so the guard is not a cheap pre-filter.
    """

    @pytest.mark.parametrize(
        "tool_name", ["seldon_cc_register", "seldon_cc_complete"]
    )
    def test_tool_refuses_untracked_file_by_default(
        self, repo, tool_name, neo4j_driver, clean_test_db
    ):
        import seldon.mcp_server as mcp_server

        from tests.testdb import TEST_DATABASE

        (repo / "seldon.yaml").write_text(
            "project:\n  name: test\n  domain: research\n"
            f"neo4j:\n  database: {TEST_DATABASE}\n  uri: bolt://localhost:7687\n"
            "event_store:\n  path: seldon_events.jsonl\n"
        )
        task = _task_file(repo)
        tool = getattr(mcp_server, tool_name)
        fn = getattr(tool, "fn", tool)

        result = fn(filepath=str(task), project_dir=str(repo))

        assert "refusing to register an untracked task file" in result
        assert f"call {tool_name} again with allow_untracked=True" in result
