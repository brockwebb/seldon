"""Tests for the git-tracking guard on `seldon cc register` / `seldon cc complete`.

The defect: 37 of the 50 ResearchTasks in this project's graph that name a
`source_file` point at a file on neither disk nor any branch, because
`cc_tasks/` was gitignored until commit c53b3c9. Registration is the only moment
at which that outcome is still preventable.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.cc import (
    GIT_IGNORED,
    GIT_NO_REPO,
    GIT_TRACKED,
    GIT_UNTRACKED,
    _enforce_git_tracking,
    _git_tracking_status,
    cc_complete,
    cc_register,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path):
    """A real git repo — the guard shells out, so a fake would prove nothing."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "cc_tasks").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------

class TestGitTrackingStatus:
    def test_untracked_file_in_repo(self, repo):
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        assert _git_tracking_status(repo, f) == GIT_UNTRACKED

    def test_staged_but_uncommitted_file_counts_as_tracked(self, repo):
        """The sanctioned workflow is add → register → commit spec with RESULT.

        Demanding a prior commit would make registration impossible.
        """
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        _git(repo, "add", str(f))
        assert _git_tracking_status(repo, f) == GIT_TRACKED

    def test_committed_file_is_tracked(self, repo):
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        _git(repo, "add", str(f))
        _git(repo, "commit", "-qm", "add")
        assert _git_tracking_status(repo, f) == GIT_TRACKED

    def test_committed_then_modified_file_is_still_tracked(self, repo):
        """Dirty is not lost. The content is recoverable; the guard is about
        recoverability, not cleanliness."""
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        _git(repo, "add", str(f))
        _git(repo, "commit", "-qm", "add")
        f.write_text("# T\n\nedited\n")
        assert _git_tracking_status(repo, f) == GIT_TRACKED

    def test_gitignored_file_is_reported_as_ignored(self, repo):
        """The exact condition that produced the 37 orphans gets its own status."""
        (repo / ".gitignore").write_text("cc_tasks/\n")
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        assert _git_tracking_status(repo, f) == GIT_IGNORED

    def test_directory_without_a_repo(self, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("# T\n")
        assert _git_tracking_status(tmp_path, f) == GIT_NO_REPO


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------

class TestEnforceGitTracking:
    def test_tracked_file_proceeds(self, repo):
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        _git(repo, "add", str(f))
        # No exception is the assertion.
        _enforce_git_tracking(repo, f, "cc_tasks/t.md", "cc register", False)

    def test_untracked_file_is_refused(self, repo):
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        with pytest.raises(SystemExit) as exc:
            _enforce_git_tracking(repo, f, "cc_tasks/t.md", "cc register", False)
        assert exc.value.code == 1

    def test_untracked_file_proceeds_with_override(self, repo):
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        _enforce_git_tracking(repo, f, "cc_tasks/t.md", "cc register", True)

    def test_missing_repo_is_refused(self, tmp_path):
        """No work tree means nothing can recover the file — the strictest case."""
        f = tmp_path / "t.md"
        f.write_text("# T\n")
        with pytest.raises(SystemExit) as exc:
            _enforce_git_tracking(tmp_path, f, "t.md", "cc register", False)
        assert exc.value.code == 1

    def test_missing_repo_proceeds_with_override(self, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("# T\n")
        _enforce_git_tracking(tmp_path, f, "t.md", "cc register", True)

    def test_refusal_names_the_status_and_the_override(self, repo, capsys):
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        with pytest.raises(SystemExit):
            _enforce_git_tracking(repo, f, "cc_tasks/t.md", "cc register", False)
        err = capsys.readouterr().err
        assert GIT_UNTRACKED in err
        assert "--allow-untracked" in err
        assert "cc_tasks/t.md" in err

    def test_ignored_refusal_says_to_edit_gitignore(self, repo, capsys):
        (repo / ".gitignore").write_text("cc_tasks/\n")
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        with pytest.raises(SystemExit):
            _enforce_git_tracking(repo, f, "cc_tasks/t.md", "cc register", False)
        err = capsys.readouterr().err
        assert ".gitignore" in err

    def test_tracked_file_still_warns_to_commit_with_the_result(self, repo, capsys):
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        _git(repo, "add", str(f))
        _enforce_git_tracking(repo, f, "cc_tasks/t.md", "cc register", False)
        assert "RESULT" in capsys.readouterr().err

    def test_override_warns_loudly(self, repo, capsys):
        f = repo / "cc_tasks" / "t.md"
        f.write_text("# T\n")
        _enforce_git_tracking(repo, f, "cc_tasks/t.md", "cc register", True)
        err = capsys.readouterr().err
        assert "WARNING" in err
        assert "stub" in err


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

class TestCLIWiring:
    def test_register_exposes_allow_untracked(self):
        assert "allow_untracked" in {p.name for p in cc_register.params}

    def test_complete_exposes_allow_untracked(self):
        assert "allow_untracked" in {p.name for p in cc_complete.params}

    def test_register_refuses_untracked_before_touching_the_graph(self, tmp_path):
        """The guard must run before any Neo4j connection is opened, so a
        refusal is possible even with no database reachable."""
        (tmp_path / "seldon.yaml").write_text(
            "project:\n  name: t\n  domain: research\n"
            "neo4j:\n  database: does-not-exist\n  uri: bolt://127.0.0.1:1\n"
            "event_store:\n  path: seldon_events.jsonl\n"
        )
        task = tmp_path / "t.md"
        task.write_text("# T\n")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            import os

            os.chdir(tmp_path)
            result = runner.invoke(cc_register, ["t.md"])

        assert result.exit_code == 1
        assert "refusing to register an untracked task file" in result.output

    def test_complete_refuses_untracked_before_touching_the_graph(self, tmp_path):
        (tmp_path / "seldon.yaml").write_text(
            "project:\n  name: t\n  domain: research\n"
            "neo4j:\n  database: does-not-exist\n  uri: bolt://127.0.0.1:1\n"
            "event_store:\n  path: seldon_events.jsonl\n"
        )
        task = tmp_path / "t.md"
        task.write_text("# T\n")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            import os

            os.chdir(tmp_path)
            result = runner.invoke(cc_complete, ["t.md"])

        assert result.exit_code == 1
        assert "refusing to register an untracked task file" in result.output

    def test_missing_file_still_reports_missing_not_untracked(self, tmp_path):
        """File-existence is checked first; an absent file gets its own message."""
        (tmp_path / "seldon.yaml").write_text(
            "project:\n  name: t\n  domain: research\n"
            "neo4j:\n  database: does-not-exist\n  uri: bolt://127.0.0.1:1\n"
            "event_store:\n  path: seldon_events.jsonl\n"
        )
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            import os

            os.chdir(tmp_path)
            result = runner.invoke(cc_register, ["nope.md"])

        assert result.exit_code == 1
        assert "file not found" in result.output
