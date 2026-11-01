"""SEL-020: `project new` ignores its own state (Part A), and the governed commit takes a per-project allowlist,
`desktop_commit.paths` (Part B).

Part A's end-to-end test reuses SEL-019's kit fixture and fake `launchctl`: the real `seldon init` (this process's
test database), the real hooks, the real adopt, then one real `seldon dispatch once --dry-run` in the new project.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from seldon.commands.dispatch import dispatch_group
from seldon.core import desktop_commit as DC
from seldon.core import project_new as PN
from tests.dispatch_scaffold import run_cli
from tests.test_hooks import repo  # noqa: F401  (fixture)
from tests.test_sel019_project_new import _new, kit, launchctl  # noqa: F401  (fixtures)


def _git(d, *args):
    return subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, check=True).stdout


# ══════════════════════════════════════════════════════════════════════════════
# Part A: `project new` writes the `.seldon/` ignore line
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_a_new_project_stays_clean_after_one_dry_run_pass(tmp_path, kit, launchctl, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)          # DD-007 refuses a pass before it writes anything
    target = tmp_path / "newproj"
    res = _new(target, "--dispatch", "--enable")
    assert res.exit_code == 0, res.output
    assert ".seldon/" in (target / ".gitignore").read_text().splitlines()
    assert _git(target, "status", "--porcelain") == ""

    # State the dispatcher and the hooks keep under `.seldon/` beyond adopt's two named files.
    (target / ".seldon" / "leases").mkdir(parents=True, exist_ok=True)
    (target / ".seldon" / "leases" / "x.lock").write_text("{}\n")
    (target / ".seldon" / "dispatch_stuck.json").write_text("{}\n")
    out = run_cli(target, dispatch_group, ["once", "--dry-run"])
    assert out.exit_code == 0, out.output
    assert "refused" not in out.output, out.output
    assert _git(target, "status", "--porcelain", "-uall") == ""


def test_the_ignore_step_converges_and_keeps_existing_lines(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    (d / ".gitignore").write_text(".env\n# mine\n")
    first = PN.ignore_step(d)
    assert first.status == "changed" and first.wrote == [".gitignore"]
    text = (d / ".gitignore").read_text()
    assert text.startswith(".env\n# mine\n") and ".seldon/" in text.splitlines()
    assert PN.ignore_step(d).status == "ok"
    assert (d / ".gitignore").read_text() == text


def test_the_ignore_step_accepts_a_tracked_rule_written_another_way(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    (d / ".gitignore").write_text(".seldon\n")
    assert PN.ignore_step(d).status == "ok"
    assert (d / ".gitignore").read_text() == ".seldon\n"


def test_a_rule_only_in_info_exclude_is_not_enough(tmp_path):
    """aacps carried `.seldon/` in `.git/info/exclude`, which no clone or worktree checkout inherits from the
    record; the line belongs in the tracked `.gitignore`."""
    d = tmp_path / "p"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    (d / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (d / ".git" / "info" / "exclude").write_text(".seldon/\n")
    step = PN.ignore_step(d)
    assert step.status == "changed"
    assert ".seldon/" in (d / ".gitignore").read_text().splitlines()


# ══════════════════════════════════════════════════════════════════════════════
# Part B: `desktop_commit.paths`, a per-project allowlist for the governed commit
# ══════════════════════════════════════════════════════════════════════════════
# The fixture is DESK-001's: real git and the real hooks in a scratch repository.

#: A scanner with squiddy.secret_scan's output contract (DESK-003): a hit line per flagged file, then the trailer.
SCANNER = """#!/bin/sh
hit=0
for f in "$@"; do
  if grep -q AKIA "$f"; then echo "$f:1 aws_key"; hit=1; fi
done
echo "scanned $# file(s); exit $hit"
exit $hit
"""


def _scanner(tmp_path) -> str:
    s = tmp_path / "scan.sh"
    s.write_text(SCANNER)
    s.chmod(0o755)
    return str(s)


def _declared(repo, tmp_path, paths=("friction-log.md", "docs/")) -> dict:
    return dict(repo["config"], desktop_commit={"paths": list(paths),
                                                "scan": {"roots": ["handoffs/"], "command": [_scanner(tmp_path)]}})


def _files_in_head(repo) -> list:
    return sorted(_git(repo["dir"], "show", "--name-only", "--pretty=", "HEAD").split())


def test_a_project_without_the_key_refuses_readme_exactly_as_before(repo):
    (repo["dir"] / "README.md").write_text("changed\n")
    head = _git(repo["dir"], "rev-parse", "HEAD")
    out = DC.commit_governed(repo["dir"], ["README.md"], repo["config"])
    assert not out.committed and out.refusal == DC.OUTSIDE_ROOTS
    assert out.detail == ("outside_roots: README.md is under none of docs/design/, cc_tasks/, handoffs/, issues/, "
                          "ontology/; this tool commits only what a Desktop session writes")
    assert _git(repo["dir"], "rev-parse", "HEAD") == head
    assert _git(repo["dir"], "diff", "--cached", "--name-only") == ""
    assert DC.settings(repo["dir"], repo["config"]).roots == DC.DEFAULT_ROOTS


def test_declared_paths_commit_a_file_and_a_directory_and_refuse_the_rest(repo, tmp_path):
    cfg = _declared(repo, tmp_path)
    (repo["dir"] / "friction-log.md").write_text("# friction\n")
    (repo["dir"] / "docs" / "x.md").write_text("# x\n")
    (repo["dir"] / "scripts").mkdir()
    (repo["dir"] / "scripts" / "x.sh").write_text("echo x\n")

    out = DC.commit_governed(repo["dir"], ["friction-log.md", "docs/x.md"], cfg)
    assert out.committed, out.detail
    assert _files_in_head(repo) == ["docs/x.md", "friction-log.md"]
    assert out.message == "desktop: file: friction-log.md; docs: x.md"

    refused = DC.commit_governed(repo["dir"], ["scripts/x.sh"], cfg)
    assert refused.refusal == DC.OUTSIDE_ROOTS and "scripts/x.sh" in refused.detail
    assert _git(repo["dir"], "status", "--porcelain", "--", "scripts/x.sh").startswith("??")
    # The declared list REPLACES the fixed set: cc_tasks/ is not in it.
    (repo["dir"] / "cc_tasks").mkdir()
    (repo["dir"] / "cc_tasks" / "t.md").write_text("# t\n")
    assert DC.commit_governed(repo["dir"], ["cc_tasks/t.md"], cfg).refusal == DC.OUTSIDE_ROOTS


def test_a_declared_path_holding_a_planted_secret_is_refused_by_the_scan(repo, tmp_path):
    """The scan's own roots name handoffs/ only; with a declared list every path committed is scanned."""
    cfg = _declared(repo, tmp_path)
    (repo["dir"] / "docs" / "leak.md").write_text("key AKIAABCDEFGHIJKLMNOP\n")
    head = _git(repo["dir"], "rev-parse", "HEAD")
    out = DC.commit_governed(repo["dir"], ["docs/leak.md"], cfg)
    assert out.refusal == DC.SECRET_FOUND and "aws_key" in out.detail
    assert _git(repo["dir"], "rev-parse", "HEAD") == head
    assert _git(repo["dir"], "status", "--porcelain", "--", "docs/leak.md").startswith("??")


@pytest.mark.parametrize("bad", [[], ["/etc/x"], ["../x"], [""], "docs/", ["docs"], [3]])
def test_a_malformed_declared_list_is_refused(repo, bad):
    """`docs` names a directory: it is written `docs/`, gitignore's trailing-slash convention."""
    with pytest.raises(DC.CommitConfigError):
        DC.settings(repo["dir"], {"desktop_commit": {"paths": bad, "scan": {"command": ["x"]}}})


def test_a_declared_list_needs_a_scan_and_excludes_roots(repo):
    with pytest.raises(DC.CommitConfigError, match="scan"):
        DC.settings(repo["dir"], {"desktop_commit": {"paths": ["docs/"]}})
    with pytest.raises(DC.CommitConfigError, match="not both"):
        DC.settings(repo["dir"], {"desktop_commit": {"paths": ["docs/"], "roots": {"docs/": "d"},
                                                     "scan": {"command": ["x"]}}})
    out = DC.commit_governed(repo["dir"], ["README.md"], {**repo["config"], "desktop_commit": {"paths": ["docs/"]}})
    assert out.refusal == "config_invalid"
