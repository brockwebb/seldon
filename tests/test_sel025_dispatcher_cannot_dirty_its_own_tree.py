"""SEL-025 (AD-038-R22, R23): the dispatcher cannot dirty its own tree.

`cc_tasks/2026-11-06_SEL-025_the_dispatcher_cannot_dirty_its_own_tree_log_rotation_and_a_filing_left_untracked.md`:
seldon's queue was refused on c7 for three days (2026-11-04 02:19Z to 2026-11-06 12:55Z) by two untracked files the
machine itself wrote. One was the wrapper's rotated log, `logs/seldon_dispatch.log.<stamp>`, which `*.log` does not
match. The other was an unregistered consumer filing in `cc_tasks/`, which the reconciler's `task_files` class does not
admit because it admits registered files only.

Part A: the wrapper rotates to `logs/dispatch/seldon_dispatch.<stamp>.log` and `.gitignore` ignores `logs/**`.
Part B: the pass commits an untracked filing (`**Kind:** filing`, or a Status naming a consumer filing), one commit
per filing, `dispatcher: filing: <basename>`, and prints `filing_committed:`; any other untracked path still refuses.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import yaml

from seldon.commands.dispatch import dispatch_group
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, add_task, git, make_project, register, run_cli, write_stub,
)

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "jobs" / "seldon_dispatch.sh"
STORE = "seldon_events.jsonl"

FILING_BY_KIND = """# Consumer filing from squiddy: a thing the consumer met

**Repo:** seldon. **Date:** 2026-11-06.
**Kind:** filing
**Filed by:** squiddy

## What the consumer observed

It met a thing.
"""

FILING_BY_STATUS = """# FAC-03 filing: a convention mismatch

**Status:** proposed (consumer filing; no dispatch headers. Seldon's Desktop turns it into a SEL task or declines it.)
**Filed by:** factory, FAC-03 (task 7a9a839d), 2026-11-02, from a dispatched session.

## The defect

A mismatch.
"""

NOT_A_FILING = """# A scratch note

**Status:** proposed

## Body

Not a filing; it names a consumer filing only in its body.
"""


# ================================================================== Part A: the rotated log is ignored

def _wrapper_repo(tmp_path: Path, max_run_bytes: int = 10) -> Path:
    """A project the wrapper can run against: seldon.yaml with the poll interval and the log caps, a plist whose
    StartInterval agrees, this repository's .gitignore, and a git repo so `check-ignore` answers."""
    repo = tmp_path / "proj"
    (repo / "logs").mkdir(parents=True)
    (repo / "seldon.yaml").write_text(yaml.safe_dump({
        "dispatch": {"poll_interval_s": 300},
        "jobs": {"dispatch": {"log_max_line_chars": 2000, "log_max_run_bytes": max_run_bytes,
                              "log_retention_days": 30}}}), encoding="utf-8")
    (repo / "job.plist").write_text("<dict>\n<key>StartInterval</key>\n<integer>300</integer>\n</dict>\n",
                                    encoding="utf-8")
    shutil.copy(ROOT / ".gitignore", repo / ".gitignore")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", "init")
    return repo


def _run_wrapper(repo: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "NEO4J_PASSWORD": "not-used", "SELDON_DISPATCH_BIN": "/usr/bin/true"}
    env.pop("SELDON_DISPATCH_LOG", None)
    return subprocess.run(["bash", str(WRAPPER), str(repo), str(repo / "job.plist")],
                          capture_output=True, text=True, env=env, timeout=60)


def test_the_wrapper_rotates_to_a_dot_log_name_under_logs_dispatch_and_it_is_ignored(tmp_path):
    repo = _wrapper_repo(tmp_path)
    log = repo / "logs" / "seldon_dispatch.log"
    log.write_text("x" * 100 + "\n", encoding="utf-8")
    r = _run_wrapper(repo)
    assert r.returncode == 0, (r.stdout, r.stderr, log.read_text() if log.exists() else None)
    rotated = sorted((repo / "logs" / "dispatch").glob("seldon_dispatch.*.log"))
    assert len(rotated) == 1, list((repo / "logs").rglob("*"))
    assert rotated[0].read_text().startswith("x" * 100), "the rotated file is not the old log"
    assert not list((repo / "logs").glob("seldon_dispatch.log.*")), "the old rotation name came back"
    rel = rotated[0].relative_to(repo).as_posix()
    assert git(repo, "check-ignore", "-q", "--", rel).returncode == 0, f"{rel} is not ignored"
    assert git(repo, "status", "--porcelain", "--untracked-files=all").stdout == "", "the wrapper dirtied the tree"
    assert "seldon-dispatch fire" in log.read_text(), "the new log was not written after rotation"


def test_retention_deletes_an_old_rotation_and_keeps_a_young_one_and_the_session_logs(tmp_path):
    repo = _wrapper_repo(tmp_path, max_run_bytes=10_000_000)
    d = repo / "logs" / "dispatch"
    d.mkdir()
    old = d / "seldon_dispatch.20260901T000000Z.log"
    young = d / "seldon_dispatch.20261105T000000Z.log"
    legacy = repo / "logs" / "seldon_dispatch.log.20260901T000000Z"
    session = d / "2026-09-01_SOME-TASK.log"
    for f in (old, young, legacy, session):
        f.write_text("old\n", encoding="utf-8")
    forty_days_ago = time.time() - 40 * 86400
    for f in (old, legacy, session):
        os.utime(f, (forty_days_ago, forty_days_ago))
    r = _run_wrapper(repo)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert not old.exists() and not legacy.exists(), "an expired rotation was kept"
    assert young.exists(), "a rotation inside retention was deleted"
    assert session.exists(), "retention deleted a dispatched session's log, which is not the wrapper's rotation"


@pytest.mark.parametrize("rel", ["logs/dispatch/seldon_dispatch.20261106T000000Z.log",
                                 "logs/seldon_dispatch.log.20261104T021957Z",
                                 "logs/anything/at/all.txt"])
def test_this_repositorys_gitignore_ignores_every_log_path(rel):
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", "--", rel], cwd=ROOT)
    assert r.returncode == 0, f"{rel} is not ignored by {ROOT / '.gitignore'}"


# ============================================================ Part B, the class (no Neo4j)

@pytest.fixture
def repo(tmp_path):
    p = tmp_path / "r"
    (p / "cc_tasks").mkdir(parents=True)
    git(p, "init", "-q", "-b", "main")
    git(p, "config", "user.email", "t@t")
    git(p, "config", "user.name", "t")
    (p / STORE).write_text("", encoding="utf-8")
    (p / "cc_tasks" / "old.md").write_text("# old\n", encoding="utf-8")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "init")
    return p


CONFIG = {"event_store": {"path": STORE}}


def test_a_filing_by_kind_or_by_status_is_its_own_class_and_scratch_is_not(repo):
    from seldon.core import reconcile as R
    (repo / "cc_tasks" / "2026-11-06_consumer_filing_x.md").write_text(FILING_BY_KIND, encoding="utf-8")
    (repo / "cc_tasks" / "2026-11-02_FAC-03_y.md").write_text(FILING_BY_STATUS, encoding="utf-8")
    (repo / "cc_tasks" / "2026-11-02_FAC-03_y_ADDENDUM_01.md").write_text("# more\n", encoding="utf-8")
    (repo / "cc_tasks" / "scratch.md").write_text(NOT_A_FILING, encoding="utf-8")
    (repo / "cc_tasks" / "sub").mkdir()
    (repo / "cc_tasks" / "sub" / "nested.md").write_text(FILING_BY_KIND, encoding="utf-8")
    (repo / "notes.md").write_text(FILING_BY_KIND, encoding="utf-8")
    got = R.classify(repo, CONFIG, set())
    assert sorted(got["classes"]["filing"]["paths"]) == [
        "cc_tasks/2026-11-02_FAC-03_y.md", "cc_tasks/2026-11-02_FAC-03_y_ADDENDUM_01.md",
        "cc_tasks/2026-11-06_consumer_filing_x.md"], got
    why = {u["path"]: u["why"] for u in got["unreconciled"]}
    assert set(why) == {"cc_tasks/scratch.md", "cc_tasks/sub/nested.md", "notes.md"}, why


def test_a_tracked_filing_edited_is_not_a_filing_commit(repo):
    """Only an UNTRACKED filing is the machine's dirt; an edit to a committed one is a person's, and c7 names it."""
    from seldon.core import reconcile as R
    f = repo / "cc_tasks" / "2026-11-06_consumer_filing_x.md"
    f.write_text(FILING_BY_KIND, encoding="utf-8")
    git(repo, "add", "--", "cc_tasks/2026-11-06_consumer_filing_x.md")
    git(repo, "commit", "-q", "-m", "filed")
    f.write_text(FILING_BY_KIND + "\nedited\n", encoding="utf-8")
    got = R.classify(repo, CONFIG, set())
    assert "filing" not in got["classes"]
    assert [u["path"] for u in got["unreconciled"]] == ["cc_tasks/2026-11-06_consumer_filing_x.md"]


def test_each_filing_is_its_own_path_limited_commit_with_the_dispatcher_subject(repo):
    from seldon.core import reconcile as R
    (repo / "cc_tasks" / "2026-11-06_consumer_filing_x.md").write_text(FILING_BY_KIND, encoding="utf-8")
    (repo / "cc_tasks" / "2026-11-02_FAC-03_y.md").write_text(FILING_BY_STATUS, encoding="utf-8")
    (repo / "src.py").write_text("x = 1\n", encoding="utf-8")
    out = R.reconcile(repo, CONFIG, set())
    filings = [c for c in out["commits"] if c["class"] == "filing"]
    assert len(filings) == 2 and all(c["committed"] for c in filings), out
    by_path = {c["paths"][0]: c for c in filings}
    for path, c in by_path.items():
        assert c["paths"] == [path]
        files = git(repo, "show", "--name-only", "--pretty=", c["commit"]).stdout.split()
        assert files == [path], files
        subject = git(repo, "log", "-1", "--pretty=%s", c["commit"]).stdout.strip()
        assert subject == f"dispatcher: filing: {Path(path).name}", subject
    assert out["unreconciled"] == [{"path": "src.py", "why": "not machine-written governed state (untracked)"}]


# ============================================================ Part B, the pass (Neo4j)

@pytest.fixture
def project(tmp_path, neo4j_driver, clean_test_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    p = make_project(tmp_path, dispatch_extra={"stuck_after_passes_by_criterion": {}})
    add_task(p, "t1")
    register(p, neo4j_driver, load_domain_config(RESEARCH_YAML), "t1", "2026-11-06T00:00:00Z")
    git(p, "commit", "-q", "-m", "register t1", "--", STORE)
    git(p, "push", "-q")
    write_stub(p, {"t1": {"complete": True}})
    return p


def test_an_untracked_filing_is_committed_by_the_pass_and_the_next_candidate_launches(project):
    name = "2026-11-02_FAC-03_filing_result_filename_convention_mismatch.md"
    (project / "cc_tasks" / name).write_text(FILING_BY_STATUS, encoding="utf-8")
    out = run_cli(project, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    assert f"filing_committed: cc_tasks/{name}" in out.output, out.output
    assert "launching" in out.output, out.output
    assert "dirty_tree" not in out.output, out.output
    subjects = git(project, "log", "-12", "--pretty=%s").stdout.splitlines()
    assert f"dispatcher: filing: {name}" in subjects, subjects
    assert git(project, "ls-files", "--error-unmatch", "--", f"cc_tasks/{name}").returncode == 0


def test_an_untracked_scratch_file_still_refuses_and_is_named(project):
    (project / "cc_tasks" / "scratch.md").write_text(NOT_A_FILING, encoding="utf-8")
    head = git(project, "rev-parse", "HEAD").stdout.strip()
    out = run_cli(project, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    assert "launching" not in out.output, out.output
    assert "dirty_tree" in out.output, out.output
    assert "unreconciled: cc_tasks/scratch.md: not machine-written governed state (untracked)" in out.output, \
        out.output
    assert "filing_committed" not in out.output, out.output
    assert git(project, "rev-parse", "HEAD").stdout.strip() == head
