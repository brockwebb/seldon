"""STD-001R (AD-039): cc_tasks/ and handoffs/ are tracked; `seldon verify` refuses a `.gitignore`
that says otherwise; `seldon init` writes the blob stanza.

No Neo4j: the check is a pure function of the repository, and `seldon init` is run against an
unroutable bolt endpoint (see tests/test_init.py, UNREACHABLE_NEO4J_URI) so it writes its files
and warns instead of creating a database.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.init import init_command
from seldon.commands.verify import TIER_A_CHECKS, check_tracked_dirs
from seldon.core import tracked_dirs as TD

UNREACHABLE_NEO4J_URI = "bolt://127.0.0.1:1"


def _repo(tmp_path: Path, gitignore: str | None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if gitignore is not None:
        (repo / ".gitignore").write_text(gitignore)
    return repo


@pytest.fixture(autouse=True)
def _no_global_excludes(monkeypatch, tmp_path):
    """The operator's global excludes file must not decide these tests."""
    empty = tmp_path / "global_ignore"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    (tmp_path / "gitconfig").write_text(f"[core]\n\texcludesFile = {empty}\n")


class TestTheCheck:
    def test_a_gitignore_holding_handoffs_is_refused(self, tmp_path):
        repo = _repo(tmp_path, "*.pyc\nhandoffs/\n")
        findings = TD.ignored(repo)
        assert [f["probe"] for f in findings] == ["handoffs/probe.md"]
        f = findings[0]
        assert f["source"] == ".gitignore" and f["line"] == 2 and f["pattern"] == "handoffs/"
        r = check_tracked_dirs(repo)
        assert r.symbol == "fail"
        assert TD.FINDING in r.summary
        assert any(".gitignore:2" in d and "handoffs/" in d for d in r.details)
        assert any("AD-039" in d for d in r.details)

    def test_a_gitignore_ignoring_both_names_both(self, tmp_path):
        repo = _repo(tmp_path, "cc_tasks/\nhandoffs/\n")
        assert {f["probe"] for f in TD.ignored(repo)} == {"cc_tasks/probe.md", "handoffs/probe.md"}

    def test_a_wildcard_under_the_dir_is_refused(self, tmp_path):
        repo = _repo(tmp_path, "handoffs/*\n!handoffs/.gitkeep\n")
        assert [f["probe"] for f in TD.ignored(repo)] == ["handoffs/probe.md"]

    def test_a_nested_gitignore_is_read(self, tmp_path):
        repo = _repo(tmp_path, "")
        (repo / "cc_tasks").mkdir()
        (repo / "cc_tasks" / ".gitignore").write_text("*.md\n")
        f = TD.ignored(repo)
        assert [x["source"] for x in f] == ["cc_tasks/.gitignore"]

    def test_the_four_blob_lines_pass(self, tmp_path):
        repo = _repo(tmp_path, TD.stanza())
        assert TD.ignored(repo) == []
        r = check_tracked_dirs(repo)
        assert r.symbol == "pass", r

    def test_the_blob_lines_still_ignore_the_blobs(self, tmp_path):
        repo = _repo(tmp_path, TD.stanza())
        for p in ("cc_tasks/x.json", "cc_tasks/x.jsonl", "handoffs/x.json", "handoffs/x.jsonl"):
            assert subprocess.run(["git", "check-ignore", "-q", "--no-index", p],
                                  cwd=repo).returncode == 0, p

    def test_no_gitignore_passes(self, tmp_path):
        assert check_tracked_dirs(_repo(tmp_path, None)).symbol == "pass"

    def test_not_a_repository_is_a_skip_not_a_pass_claim(self, tmp_path):
        r = check_tracked_dirs(tmp_path)
        assert r.symbol == "pass" and "Not a git repository" in r.summary

    def test_the_check_is_tier_a(self):
        assert TD.CHECK_NAME in TIER_A_CHECKS


class TestInitWritesTheStanza:
    def _init(self, tmp_path, monkeypatch, pre: str | None = None):
        monkeypatch.setenv("NEO4J_URI", UNREACHABLE_NEO4J_URI)
        monkeypatch.delenv("SELDON_ONTOLOGY_PATH", raising=False)
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            subprocess.run(["git", "init", "-q", td], check=True)
            if pre is not None:
                Path(td, ".gitignore").write_text(pre)
            result = runner.invoke(init_command, ["std001-probe"])
            text = Path(td, ".gitignore").read_text()
            findings = TD.ignored(Path(td))
        return result, text, findings

    def test_init_on_an_empty_dir_leaves_a_gitignore_that_passes(self, tmp_path, monkeypatch):
        result, text, findings = self._init(tmp_path, monkeypatch)
        assert result.exit_code == 0, result.output
        for line in TD.BLOB_LINES:
            assert line in text.splitlines()
        assert ".env" in text.splitlines()
        assert findings == []
        assert "add .env to your .gitignore" not in result.output

    def test_init_appends_to_an_existing_gitignore_without_duplicating(self, tmp_path, monkeypatch):
        result, text, findings = self._init(tmp_path, monkeypatch, pre="*.pyc\n.env\nhandoffs/*.json\n")
        assert result.exit_code == 0, result.output
        lines = text.splitlines()
        assert lines[0] == "*.pyc"
        assert lines.count(".env") == 1 and lines.count("handoffs/*.json") == 1
        assert "cc_tasks/*.jsonl" in lines

    def test_init_reports_a_gitignore_that_still_ignores_the_dirs(self, tmp_path, monkeypatch):
        result, _, findings = self._init(tmp_path, monkeypatch, pre="handoffs/\n")
        assert findings and TD.FINDING in result.output
