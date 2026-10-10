"""HOOK-001: the commit gate of AD-036-R4 runs as a git hook (AD-036 ADDENDUM 02).

Every repository here is a scratch git repository. The refusals are produced by `git commit`
itself, with no seldon command typed: the hook is what runs. The last tests are the removal check
of kg_construction_methodology section 7.9: take the hook away and the same planted note gets
through, so the refusal tests are known to depend on the hook and not on something incidental.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from seldon.core import hooks as H
from seldon.core import prior_art as pa

LIB_SHA = "a" * 64


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    # GIT_* variables from an enclosing hook would point these commands at another repository.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(root), *args], check=check, capture_output=True,
                          text=True, env=env)


class StubLibrary:
    def __init__(self, rows=("lesson:x#p1:1:0-9",), sha=LIB_SHA):
        self.rows, self.sha = list(rows), sha

    def search(self, query, k=None):
        return {"query": query, "release": "lib.json", "sha256": self.sha, "rows": self.rows,
                "hits": []}


@pytest.fixture
def repo(tmp_path):
    """A project with a prior_art gate, a decision register block, a tracked governed ledger, a
    baseline note, and the hook installed by `seldon hooks install`."""
    sib = tmp_path / "sib"
    sib.mkdir()
    _git(sib, "init", "-q")
    _git(sib, "config", "user.email", "t@t")
    _git(sib, "config", "user.name", "t")
    (sib / "docs" / "design").mkdir(parents=True)
    (sib / "docs" / "design" / "DN-001_unit.md").write_text(
        "# DN-001\n\nIntro line.\n\nThe unit of extraction is the\nparagraph, measured.\n")
    _git(sib, "add", "-A")
    _git(sib, "commit", "-qm", "init")
    sib_sha = _git(sib, "rev-parse", "HEAD").stdout.strip()

    proj = tmp_path / "proj"
    proj.mkdir()
    _git(proj, "init", "-q", "-b", "main")
    _git(proj, "config", "user.email", "t@t")
    _git(proj, "config", "user.name", "t")
    (proj / "governed" / "ledger").mkdir(parents=True)
    (proj / "governed" / "ledger" / "events.jsonl").write_text("")
    (proj / "docs" / "design").mkdir(parents=True)
    (proj / "docs" / "decisions" / "register").mkdir(parents=True)
    (proj / "docs" / "design" / "AD-036_baseline.txt").write_text("docs/design/OLD.md\n")
    (proj / "docs" / "design" / "OLD.md").write_text("# an old note, no prior art\n")
    (proj / "README.md").write_text("x\n")
    config = {
        "project": {"name": "t"},
        "governed": {"graph_dir": "governed"},
        "prior_art": {
            "log": "state/q.jsonl",
            "internal_roots": [{"name": "sib", "path": str(sib)}],
            "internal": {"default_include": ["docs/design/**"], "suffixes": [".md"],
                         "top_n": 20, "max_file_bytes": 100000, "bm25": {"k1": 1.2, "b": 0.75}},
            "library": {"graph": str(tmp_path / "nolib"), "k": 20},
            "gate": {"design_dir": "docs/design", "baseline": "docs/design/AD-036_baseline.txt",
                     "exempt_globs": ["*_ADDENDUM_*.md", "*_erratum_*.md"]},
        },
    }
    (proj / "seldon.yaml").write_text(yaml.safe_dump(config))
    (proj / ".gitignore").write_text("state/\n")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    base = _git(proj, "rev-parse", "HEAD").stdout.strip()
    config["decisions"] = {
        "repository": "t", "baseline": {"name": "B", "commit": base},
        "design_notes": [{"glob": "docs/design/AD-*.md",
                          "pattern": r"^(?:\s*[-*]\s*)?\*\*(AD-\d{3}-R\d+)[.:)\s]",
                          "id": "{repo}:{label}"}]}
    (proj / "seldon.yaml").write_text(yaml.safe_dump(config))
    res = H.install(proj, python=sys.executable)
    assert res.wrote_hook
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "install the commit gate")
    return {"dir": proj, "config": config, "sib_sha": sib_sha}


def _good(repo) -> str:
    return (f"# AD-099 a note\n\n## 2. Prior art\n\n### External\n\n"
            f'- library receipt: query "unit of extraction" | release lib.json sha256:{LIB_SHA} '
            f"| rows lesson:x#p1:1:0-9\n\n### Internal\n\n"
            f'- internal receipt: query "unit of extraction" | repo sib@{repo["sib_sha"]} '
            f"| hits docs/design/DN-001_unit.md:5\n\n## 3. Decisions\n")


def _plant(repo, name="AD-099_x.md", body="# AD-099\n\nNo prior art section.\n") -> Path:
    p = repo["dir"] / "docs" / "design" / name
    p.write_text(body)
    return p


def _verify_and_record(repo, note: Path):
    s = pa.settings(repo["dir"], repo["config"])
    v = pa.verify_note(note, s, library=StubLibrary())
    pa.record_verdict(v, repo["dir"], repo["config"])
    return v


def _commit(repo, *extra) -> subprocess.CompletedProcess:
    return _git(repo["dir"], "commit", "-m", "planted", *extra, check=False)


def _head(repo) -> str:
    return _git(repo["dir"], "rev-parse", "HEAD").stdout.strip()


# ------------------------------------------------------------------------------- refusal

def test_git_commit_itself_refuses_a_planted_note_without_prior_art(repo):
    before = _head(repo)
    _plant(repo)
    _git(repo["dir"], "add", "docs/design/AD-099_x.md")
    r = _commit(repo)
    assert r.returncode != 0
    assert "docs/design/AD-099_x.md" in r.stderr and "AD-036-R4" in r.stderr
    assert "--no-verify" in r.stderr
    assert _head(repo) == before


def test_a_verified_note_commits_when_its_verdict_is_staged_with_it(repo):
    note = _plant(repo, body=_good(repo))
    assert _verify_and_record(repo, note).verdict == "pass"
    _git(repo["dir"], "add", "docs/design/AD-099_x.md")
    r = _commit(repo)                       # the verdict is in the working tree only
    assert r.returncode != 0 and "stage the governed ledger" in r.stderr
    _git(repo["dir"], "add", "governed/ledger/events.jsonl")
    r = _commit(repo)
    assert r.returncode == 0, r.stderr


def test_unstaged_state_never_decides_a_commit(repo):
    # A failing note staged, then repaired in the working tree only: still refused.
    note = _plant(repo)
    _git(repo["dir"], "add", "docs/design/AD-099_x.md")
    note.write_text(_good(repo))
    _verify_and_record(repo, note)
    _git(repo["dir"], "add", "governed/ledger/events.jsonl")
    assert _commit(repo).returncode != 0
    # A passing note staged, then broken in the working tree only: it commits.
    _git(repo["dir"], "add", "docs/design/AD-099_x.md")
    note.write_text("# broken after staging\n")
    r = _commit(repo)
    assert r.returncode == 0, r.stderr


def test_an_unparsed_ruling_label_is_refused_at_commit(repo):
    # An addendum is outside the prior-art gate, so only the label check can refuse it.
    _plant(repo, "AD-099_ADDENDUM_01_x.md", "# addendum\n\n## AD-099-R1. A heading label\n")
    _git(repo["dir"], "add", "-A", "docs/design")
    r = _commit(repo)
    assert r.returncode != 0 and "ruling_label_unparsed" in r.stderr
    assert "AD-099_ADDENDUM_01_x.md:3" in r.stderr


def test_a_labeled_decision_without_a_staged_record_is_refused(repo):
    _plant(repo, "AD-099_ADDENDUM_01_x.md", "# addendum\n\n- **AD-099-R1.** A decision.\n")
    _git(repo["dir"], "add", "-A", "docs/design")
    r = _commit(repo)
    assert r.returncode != 0 and "t:AD-099-R1" in r.stderr and "AD-033-R2" in r.stderr


def test_a_hand_written_register_file_is_refused_at_commit(repo):
    reg = repo["dir"] / "docs" / "decisions" / "register" / "00001_t-x_accept.yaml"
    reg.write_text("id: t:X\nevent: accept\n")
    _git(repo["dir"], "add", "-A", "docs/decisions")
    r = _commit(repo)
    assert r.returncode != 0 and "Decision register:" in r.stderr


def test_a_commit_touching_no_governed_file_passes(repo):
    (repo["dir"] / "README.md").write_text("y\n")
    _git(repo["dir"], "add", "README.md")
    assert _commit(repo).returncode == 0


# ------------------------------------------------------------------------------- the bypass

def test_no_verify_is_the_only_way_past_and_verify_reports_it(repo):
    from seldon.commands.verify import check_commit_hook
    assert check_commit_hook(repo["dir"], repo["config"]).symbol == "pass"
    _plant(repo)
    _git(repo["dir"], "add", "docs/design/AD-099_x.md")
    assert _commit(repo).returncode != 0
    r = _commit(repo, "--no-verify")
    assert r.returncode == 0, r.stderr
    rows = H.bypassed(repo["dir"], repo["config"])
    assert [(x["commit"], x["note"], x["healed"]) for x in rows] == \
        [(_head(repo), "docs/design/AD-099_x.md", False)]
    res = check_commit_hook(repo["dir"], repo["config"])
    assert res.symbol == "fail" and H.BYPASSED in res.summary
    assert any(d.startswith(f"{H.BYPASSED}: {_head(repo)[:12]}") for d in res.details)


def test_a_healed_bypass_is_still_reported_as_a_warning(repo):
    from seldon.commands.verify import check_commit_hook
    note = _plant(repo)
    _git(repo["dir"], "add", "docs/design/AD-099_x.md")
    assert _commit(repo, "--no-verify").returncode == 0
    note.write_text(_good(repo))
    _verify_and_record(repo, note)
    _git(repo["dir"], "add", "-A")
    assert _commit(repo).returncode == 0
    rows = H.bypassed(repo["dir"], repo["config"])
    assert len(rows) == 1 and rows[0]["healed"]
    assert check_commit_hook(repo["dir"], repo["config"]).symbol == "warn"


def test_commits_before_the_hook_existed_are_not_audited(repo):
    assert H.anchor(repo["dir"]) == _head(repo)
    # OLD.md was committed before the hook and is baseline; nothing is reported.
    assert H.bypassed(repo["dir"], repo["config"]) == []


# ----------------------------------------------------------------------------- installation

def test_the_hook_is_installed_by_path_not_copied(repo):
    d = repo["dir"]
    assert _git(d, "config", "--local", "--get", "core.hooksPath").stdout.strip() == ".githooks"
    assert _git(d, "rev-parse", "--git-path", "hooks").stdout.strip() == ".githooks"
    assert _git(d, "ls-files", ".githooks/pre-commit").stdout.strip() == ".githooks/pre-commit"
    assert not (d / ".git" / "hooks" / "pre-commit").exists()
    assert (d / ".githooks" / "pre-commit").read_text() == H.HOOK_SCRIPT
    # Git runs the tracked file itself: change it and the next commit runs the change.
    (d / ".githooks" / "pre-commit").write_text("#!/bin/sh\necho tracked-file-ran >&2\nexit 1\n")
    (d / "README.md").write_text("z\n")
    _git(d, "add", "README.md")
    r = _commit(repo)
    assert r.returncode != 0 and "tracked-file-ran" in r.stderr


def test_install_never_writes_global_config_and_reports_the_old_value(repo, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    _git(other, "config", "core.hooksPath", "/nonexistent/old/.git/hooks")
    res = H.install(other, python=sys.executable)
    assert res.old_hooks_path == "/nonexistent/old/.git/hooks"
    scope = _git(other, "config", "--show-scope", "--get", "core.hooksPath").stdout
    assert scope.startswith("local\t.githooks")
    assert H.install(other, python=sys.executable).changed is False      # idempotent


def test_install_refuses_to_overwrite_a_different_hook(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-q")
    (d / ".githooks").mkdir()
    (d / ".githooks" / "pre-commit").write_text("#!/bin/sh\nexit 0\n")
    with pytest.raises(H.HookError, match="not seldon's hook"):
        H.install(d, python=sys.executable)


def test_the_dispatcher_points_git_at_the_tracked_hook_and_refuses_without_it(repo, tmp_path):
    d = repo["dir"]
    _git(d, "config", "--local", "--unset", "core.hooksPath")
    assert not H.status(d)["installed"]
    got = H.ensure_installed(d)
    assert got["ok"] and got["changed"] and H.status(d)["installed"]
    bare = tmp_path / "bare"
    bare.mkdir()
    _git(bare, "init", "-q")
    got = H.ensure_installed(bare)
    assert not got["ok"] and ".githooks/pre-commit" in got["error"]
    assert not (bare / ".githooks").exists()          # never writes a tracked file


def test_a_worktree_runs_the_hook_its_own_checkout_carries(repo, tmp_path):
    wt = tmp_path / "wt"
    _git(repo["dir"], "worktree", "add", "-q", str(wt), "-b", "feat/x")
    (wt / "docs" / "design" / "AD-099_x.md").write_text("# no section\n")
    _git(wt, "add", "docs/design/AD-099_x.md")
    r = _git(wt, "commit", "-m", "planted", check=False)
    assert r.returncode != 0 and "AD-036-R4" in r.stderr


# --------------------------------------------------------------------- section 7.9 removal

@pytest.mark.parametrize("removal", ["unset_hooks_path", "delete_hook_file"])
def test_removing_the_hook_lets_the_planted_note_through(repo, removal):
    """Without the hook the same planted note commits: the refusal above is the hook's doing."""
    d = repo["dir"]
    if removal == "unset_hooks_path":
        _git(d, "config", "--local", "--unset", "core.hooksPath")
    else:
        (d / ".githooks" / "pre-commit").unlink()
    _plant(repo)
    _git(d, "add", "docs/design/AD-099_x.md")
    r = _commit(repo)
    assert r.returncode == 0, r.stderr


def test_the_refusal_test_fails_when_the_hook_is_removed(repo):
    """The planted-refusal test's own assertion, run with the hook removed, does not hold."""
    _git(repo["dir"], "config", "--local", "--unset", "core.hooksPath")
    with pytest.raises(AssertionError):
        test_git_commit_itself_refuses_a_planted_note_without_prior_art(repo)
