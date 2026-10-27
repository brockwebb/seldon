"""DESK-004R: every file the machine writes is committed by the tool that wrote it (AD-038-R15).

A. `seldon hooks install` wrote `.githooks/commit-msg` and left it untracked; `seldon_commit_governed` refuses
   `.githooks/` paths, so nobody committed it, and squiddy's dispatcher refused every candidate on c7 from 2026-10-21
   21:17 (SUITE-001 9324622d included). The installer now commits the hook files it writes, alone and through the
   hooks. `ensure_installed` runs before the dispatcher's lease and does not commit; the reconciler's `hooks` class
   commits seldon's exact hook text under the lease.

B. The retired `_commit_registered` swept `<stem>_ADDENDUM*.md` only beside an UNTRACKED base, so an addendum filed
   after its base was committed was committed by nobody (ai-readiness-kg 1267b87d: three tasks stuck 2026-10-02 to
   10-04). The AD-038-R1 reconciler that replaced it keys on the addendum's own untracked state; these tests pin that
   for a tracked base, at the class table and through a real dispatcher pass.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from seldon.commands.dispatch import dispatch_group
from seldon.commands.hooks import hooks_group
from seldon.core import hooks as H
from seldon.core import reconcile as R
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, add_task, git, make_project, register, run_cli, write_stub,
)

STORE = "seldon_events.jsonl"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _porcelain(repo: Path) -> str:
    return _git(repo, "status", "--porcelain", "--untracked-files=all").stdout


@pytest.fixture
def scratch(tmp_path):
    d = tmp_path / "scratch"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "README.md").write_text("x\n", encoding="utf-8")
    _git(d, "add", "README.md")
    _git(d, "commit", "-q", "-m", "init")
    return d


# ================================================================================ Part A

def test_a_fresh_install_leaves_the_tree_clean(scratch):
    """The task's test: a fresh install in a scratch repo leaves `git status --porcelain` empty."""
    res = H.install(scratch, python=sys.executable)
    assert res.wrote_hook
    assert _porcelain(scratch) == "", _porcelain(scratch)
    assert sorted(res.committed) == [".githooks/commit-msg", ".githooks/pre-commit"]
    files = _git(scratch, "show", "--name-only", "--pretty=", "HEAD").stdout.split()
    assert sorted(files) == sorted(res.committed)            # the hook files alone
    assert res.commit == _git(scratch, "rev-parse", "--short", "HEAD").stdout.strip()
    assert H.status(scratch)["installed"]


def test_the_cli_install_leaves_the_tree_clean_and_names_the_commit(scratch):
    out = run_cli(scratch, hooks_group, ["install", "--repo", str(scratch)])
    assert out.exit_code == 0, out.output
    assert "committed .githooks/pre-commit, .githooks/commit-msg as" in out.output, out.output
    assert "commit them" not in out.output
    assert _porcelain(scratch) == ""


def test_the_commit_runs_through_the_hooks_and_leaves_other_staged_work_alone(scratch):
    """Path-limited: an unrelated staged file stays staged and uncommitted. (Through the hooks: the refusal test
    below fails the commit by the interpreter the just-installed hooks run.)"""
    (scratch / "work.txt").write_text("in progress\n", encoding="utf-8")
    _git(scratch, "add", "work.txt")
    H.install(scratch, python=sys.executable)
    assert _git(scratch, "diff", "--cached", "--name-only").stdout.split() == ["work.txt"]
    assert "work.txt" not in _git(scratch, "show", "--name-only", "--pretty=", "HEAD").stdout


def test_an_untracked_hook_an_earlier_install_left_is_committed(scratch):
    """squiddy's state: commit-msg on disk with seldon's text, untracked, since 2026-10-21. Re-running install,
    which writes nothing, commits it."""
    H.install(scratch, python=sys.executable, commit=False)
    assert "?? .githooks/commit-msg" in _porcelain(scratch)
    res = H.install(scratch, python=sys.executable)
    assert not res.wrote_hook and res.changed
    assert _porcelain(scratch) == ""


def test_install_is_idempotent_and_commits_nothing_twice(scratch):
    H.install(scratch, python=sys.executable)
    head = _git(scratch, "rev-parse", "HEAD").stdout
    res = H.install(scratch, python=sys.executable)
    assert res.committed == () and res.commit is None and res.changed is False
    assert _git(scratch, "rev-parse", "HEAD").stdout == head


def test_a_refused_hook_commit_raises_and_leaves_the_index_as_found(scratch):
    """The hooks it commits through are its own, so a refusal is forced with a different interpreter that fails."""
    bad = scratch / "false_python"
    bad.write_text("#!/bin/sh\necho 'refused for the test' >&2\nexit 1\n", encoding="utf-8")
    bad.chmod(0o755)
    _git(scratch, "add", "false_python")
    _git(scratch, "commit", "-q", "-m", "a failing interpreter")
    with pytest.raises(H.HookError, match="refused for the test"):
        H.install(scratch, python=str(bad))
    assert _git(scratch, "diff", "--cached", "--name-only").stdout == ""
    assert (scratch / ".githooks" / "commit-msg").is_file()       # left on disk for the operator


def test_ensure_installed_does_not_commit_outside_the_lease(scratch):
    """The dispatcher calls it before the lease; the reconciler, under the lease, commits what it wrote."""
    hf = scratch / ".githooks" / "pre-commit"
    hf.parent.mkdir()
    hf.write_text(H.HOOK_SCRIPT, encoding="utf-8")
    hf.chmod(0o755)
    _git(scratch, "add", ".githooks/pre-commit")
    _git(scratch, "commit", "-q", "--no-verify", "-m", "pre-commit only (a pre-DESK-001 checkout)")
    head = _git(scratch, "rev-parse", "HEAD").stdout
    got = H.ensure_installed(scratch)
    assert got["ok"], got
    assert _git(scratch, "rev-parse", "HEAD").stdout == head
    assert _porcelain(scratch).strip() == "?? .githooks/commit-msg"
    out = R.reconcile(scratch, {"event_store": {"path": STORE}}, set())
    assert [c["class"] for c in out["commits"]] == ["hooks"] and out["commits"][0]["committed"], out
    assert "AD-038-R15" in out["commits"][0]["message"]
    assert _porcelain(scratch) == ""


def test_the_reconciler_does_not_commit_a_hook_file_that_is_not_seldons(scratch):
    (scratch / ".githooks").mkdir()
    (scratch / ".githooks" / "commit-msg").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    got = R.classify(scratch, {"event_store": {"path": STORE}}, set())
    assert got["classes"] == {}
    assert got["unreconciled"] == [{"path": ".githooks/commit-msg", "why": "a hook file that is not seldon's text"}]


# ================================================================================ Part B

def test_an_untracked_addendum_to_a_tracked_base_is_reconciled(scratch):
    """The class table: the base is committed, its addendum is not, and the addendum is a task file to commit."""
    (scratch / "cc_tasks").mkdir()
    (scratch / "cc_tasks" / "t.md").write_text("# t\n", encoding="utf-8")
    _git(scratch, "add", "cc_tasks/t.md")
    _git(scratch, "commit", "-q", "-m", "register t")
    (scratch / "cc_tasks" / "t_ADDENDUM_01.md").write_text("# late addendum\n", encoding="utf-8")
    out = R.reconcile(scratch, {"event_store": {"path": STORE}}, {"cc_tasks/t.md"})
    assert [(c["class"], c["paths"], c["committed"]) for c in out["commits"]] == [
        ("task_files", ["cc_tasks/t_ADDENDUM_01.md"], True)], out
    files = _git(scratch, "show", "--name-only", "--pretty=", "HEAD").stdout.split()
    assert files == ["cc_tasks/t_ADDENDUM_01.md"]
    assert out["unreconciled"] == [] and _porcelain(scratch) == ""


@pytest.fixture
def project(tmp_path, neo4j_driver, clean_test_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    p = make_project(tmp_path, dispatch_extra={"stuck_after_passes_by_criterion": {}})
    rel = add_task(p, "t1")                                    # committed: the tracked base
    register(p, neo4j_driver, load_domain_config(RESEARCH_YAML), "t1", "2026-10-27T00:00:00Z")
    git(p, "commit", "-q", "-m", "register t1", "--", STORE)
    git(p, "push", "-q")
    write_stub(p, {"t1": {"complete": True}})
    return p, rel


def test_a_dispatcher_pass_commits_a_late_addendum_and_launches(project):
    """ai-readiness-kg 1267b87d's wedge end to end: the base is tracked, the addendum arrives after it, unregistered.
    The pass commits the addendum alone and c7 does not refuse."""
    project, base_rel = project
    base = project / base_rel
    assert _git(project, "ls-files", "--error-unmatch", base_rel).returncode == 0, "fixture: base not tracked"
    addendum = base.with_name(f"{base.stem}_ADDENDUM_01.md")
    addendum.write_text("# ADDENDUM 01\n\nA late amendment.\n", encoding="utf-8")
    out = run_cli(project, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    assert "dirty_tree" not in out.output, out.output
    assert "launching" in out.output, out.output
    rel = str(addendum.relative_to(project))
    assert _git(project, "ls-files", "--error-unmatch", rel).returncode == 0, out.output
    subjects = _git(project, "log", "-8", "--pretty=%s").stdout
    assert any("task_files" in s and rel in s for s in subjects.splitlines()), subjects
