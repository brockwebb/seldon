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
from seldon.core import project_new as PN
from tests.dispatch_scaffold import run_cli
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
