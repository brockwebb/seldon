"""FRICTION-001 Part A (AD-038-R1): the dispatcher reconciles machine-written state before c7.

`docs/design/AD-038_the_machine_reconciles_its_own_state.md` §1: 797 passes in a week refused on c7, every one on a
file the system itself had written. The dispatcher committed only `dispatcher` and `desktop` lines
(`COMMITTABLE_ACTORS`), so a `governed_sync` line (registration's `link_created`) or a `cc` line kept the whole queue
refused until a person committed it. R1 moves that duty to the pass that holds the lease: every dirty path in a
governed class is committed, one commit per class, whoever wrote it; c7 then refuses only on what the reconciler
could not or may not commit, and names it.

The first four tests are the task's; each fails on main 92f491b (the RESULT records the failures). The rest hold
the classification table in `seldon/core/reconcile.py` without Neo4j.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core.events import append_event, make_event
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, add_task, git, make_project, register, run_cli, write_stub,
)

STORE = "seldon_events.jsonl"


@pytest.fixture
def project(tmp_path, neo4j_driver, clean_test_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    p = make_project(tmp_path, dispatch_extra={"stuck_after_passes_by_criterion": {}})
    add_task(p, "t1")
    register(p, neo4j_driver, load_domain_config(RESEARCH_YAML), "t1", "2026-10-17T00:00:00Z")
    git(p, "commit", "-q", "-m", "register t1", "--", STORE)
    git(p, "push", "-q")
    write_stub(p, {"t1": {"complete": True}})
    return p


def _porcelain(p: Path) -> str:
    return git(p, "status", "--porcelain").stdout


def _subjects(p: Path, n: int = 12) -> list:
    return git(p, "log", f"-{n}", "--pretty=%s").stdout.splitlines()


def _append(p: Path, actor: str, event_type: str = "link_created") -> None:
    append_event(p, make_event(event_type=event_type, actor=actor, authority="accepted",
                               payload={"artifact_id": "feedface-0000", "note": "left uncommitted"}))


# ================================================================== the task's four tests

def test_a_governed_sync_line_is_committed_and_the_task_launches(project):
    """Registration's `link_created` lines (actor `governed_sync`) were the SQ-016R dirt: the old allowlist refused
    them with "NOT committed" and c7 refused every task."""
    _append(project, "governed_sync")
    assert _porcelain(project).strip(), "the fixture did not leave the store dirty"
    out = run_cli(project, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    assert "launching" in out.output, out.output
    assert "NOT committed" not in out.output, out.output
    reconciled = [s for s in _subjects(project) if "governed_sync" in s]
    assert reconciled and "event_store" in reconciled[0], _subjects(project)
    assert _porcelain(project).strip() == "", _porcelain(project)


def test_a_cc_line_is_committed_and_the_task_launches(project):
    """A `cc` line was refused as DD-019's class. The guard is the lease: the pass holds it with no claim in flight,
    so no session is working in the checkout and the line is a finished writer's, committed like any other."""
    _append(project, "cc", event_type="artifact_updated")
    out = run_cli(project, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    assert "launching" in out.output, out.output
    assert any("written by cc" in s for s in _subjects(project)), _subjects(project)
    assert _porcelain(project).strip() == "", _porcelain(project)


def test_a_dirty_source_file_still_refuses_and_is_named(project):
    (project / "controls.yaml").write_text(
        yaml.safe_dump({"spend": {"daily_tokens": 55_000_000}}) + "# edited by hand\n", encoding="utf-8")
    _append(project, "governed_sync")          # reconcilable dirt beside it is still committed
    out = run_cli(project, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    assert "launching" not in out.output, out.output
    assert "dirty_tree" in out.output, out.output
    assert "unreconciled: controls.yaml: not machine-written governed state" in out.output, out.output
    assert git(project, "status", "--porcelain", "--", STORE).stdout == ""
    last = D.read_last_pass(project, D.load_dispatch_config(project, yaml.safe_load(
        (project / "seldon.yaml").read_text())))
    assert any("unreconciled: controls.yaml" in ln for ln in last["lines"]), last


def test_a_non_append_only_store_change_refuses_and_is_named(project):
    head = git(project, "rev-parse", "HEAD").stdout.strip()
    (project / STORE).write_text("", encoding="utf-8")       # HEAD's lines removed: an in-place edit
    _append(project, "dispatcher", event_type=D.EVENT_FINISHED)
    out = run_cli(project, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    assert "launching" not in out.output, out.output
    assert f"unreconciled: {STORE}: not append-only against HEAD" in out.output, out.output
    assert git(project, "rev-parse", "HEAD").stdout.strip() == head


# ============================================================ the classes, without Neo4j

@pytest.fixture
def repo(tmp_path):
    p = tmp_path / "r"
    (p / "cc_tasks").mkdir(parents=True)
    (p / "docs" / "decisions" / "register").mkdir(parents=True)
    (p / "state").mkdir()
    git(p, "init", "-q", "-b", "main")
    git(p, "config", "user.email", "t@t")
    git(p, "config", "user.name", "t")
    (p / STORE).write_text(json.dumps({"event_type": "x", "actor": "cc"}) + "\n", encoding="utf-8")
    (p / "docs" / "decisions" / "register" / "00001_a.yaml").write_text("a: 1\n", encoding="utf-8")
    (p / "docs" / "decisions" / "REGISTER.md").write_text("# Register\n", encoding="utf-8")
    (p / "seldon.yaml").write_text("dispatch:\n  cadence:\n  - name: c\n    last_instance: ''\n  enabled: true\n",
                                   encoding="utf-8")
    (p / "cc_tasks" / "old.md").write_text("# old\n", encoding="utf-8")
    (p / "src.py").write_text("x = 1\n", encoding="utf-8")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "init")
    return p


CONFIG = {"event_store": {"path": STORE}}


def test_every_class_is_recognised_and_the_rest_is_named(repo):
    from seldon.core import reconcile as R
    with open(repo / STORE, "a") as fh:
        fh.write(json.dumps({"event_type": "link_created", "actor": "governed_sync"}) + "\n")
    (repo / "docs" / "decisions" / "register" / "00002_b.yaml").write_text("b: 2\n", encoding="utf-8")
    (repo / "docs" / "decisions" / "REGISTER.md").write_text("# Register\n\n- b\n", encoding="utf-8")
    (repo / "seldon.yaml").write_text((repo / "seldon.yaml").read_text().replace(
        "last_instance: ''", "last_instance: cc_tasks/new.md"), encoding="utf-8")
    (repo / "cc_tasks" / "new.md").write_text("# new\n", encoding="utf-8")
    (repo / "cc_tasks" / "new_ADDENDUM_01.md").write_text("# add\n", encoding="utf-8")
    (repo / "cc_tasks" / "stray.md").write_text("# not registered\n", encoding="utf-8")
    (repo / "src.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "docs" / "decisions" / "register" / "00001_a.yaml").write_text("a: 9\n", encoding="utf-8")

    got = R.classify(repo, CONFIG, {"cc_tasks/new.md", "cc_tasks/old.md"})
    cls = {c: sorted(v["paths"]) for c, v in got["classes"].items()}
    assert cls == {"event_store": [STORE],
                   "decision_register": ["docs/decisions/REGISTER.md", "docs/decisions/register/00002_b.yaml"],
                   "cadence": ["seldon.yaml"],
                   "task_files": ["cc_tasks/new.md", "cc_tasks/new_ADDENDUM_01.md"]}, cls
    assert got["classes"]["event_store"]["writers"] == ["governed_sync"]
    why = {u["path"]: u["why"] for u in got["unreconciled"]}
    assert set(why) == {"cc_tasks/stray.md", "src.py", "docs/decisions/register/00001_a.yaml"}, why
    assert "edited in place" in why["docs/decisions/register/00001_a.yaml"]


def test_one_commit_per_class_naming_the_class_and_the_writers(repo):
    from seldon.core import reconcile as R
    with open(repo / STORE, "a") as fh:
        fh.write(json.dumps({"event_type": "link_created", "actor": "governed_sync"}) + "\n")
    (repo / "cc_tasks" / "new.md").write_text("# new\n", encoding="utf-8")
    (repo / "src.py").write_text("x = 2\n", encoding="utf-8")
    out = R.reconcile(repo, CONFIG, {"cc_tasks/new.md"})
    assert [c["class"] for c in out["commits"]] == ["event_store", "task_files"]
    assert all(c["committed"] for c in out["commits"]), out
    subjects = _subjects(repo, 2)
    assert "task_files" in subjects[0] and "cc register" in subjects[0]
    assert "event_store" in subjects[1] and "governed_sync" in subjects[1]
    for c in out["commits"]:
        files = git(repo, "show", "--name-only", "--pretty=", c["commit"]).stdout.split()
        assert files == c["paths"], (files, c)
    assert out["unreconciled"] == [{"path": "src.py", "why": "not machine-written governed state"}]


def test_a_cadence_edit_beyond_last_instance_is_not_committed(repo):
    from seldon.core import reconcile as R
    (repo / "seldon.yaml").write_text((repo / "seldon.yaml").read_text().replace(
        "enabled: true", "enabled: false"), encoding="utf-8")
    got = R.classify(repo, CONFIG, set())
    assert got["classes"] == {}
    assert got["unreconciled"][0]["path"] == "seldon.yaml"


def test_a_refused_commit_is_named_and_leaves_the_index_clean(repo):
    """A hook refusal is c7's to name (R1: "a hook refusal"), with git's reason, and nothing stays staged."""
    from seldon.core import reconcile as R
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'gate: refused for the test' >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    with open(repo / STORE, "a") as fh:
        fh.write(json.dumps({"event_type": "e", "actor": "cc"}) + "\n")
    out = R.reconcile(repo, CONFIG, set())
    assert out["commits"][0]["committed"] is False
    assert out["unreconciled"] == [{"path": STORE,
                                    "why": "commit refused (git_commit_failed): gate: refused for the test"}]
    assert git(repo, "diff", "--cached", "--name-only").stdout == ""
