"""SEL-052 Part A: what writes an absolute `core.hooksPath` into a primary checkout, and why it stops.

The writer is the Claude Code CLI. After `claude --worktree` creates a worktree, its setup step (function `xTt` in the
2.1.325 bundle, `/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`, read 2026-11-26) reads
`core.hooksPath` from the repository's common config; when the value is RELATIVE it resolves it against the main
checkout and runs `git config core.hooksPath <absolute>` with its cwd in the new worktree. A plain `git config` write
goes to the repository's shared config (git-config(1): writes default to `--local`), so the PRIMARY's value becomes
absolute, and `seldon hooks status` / `seldon verify` there report the commit hook not installed. It logs "Configured
worktree to use hooks from main repository". Every dispatched task is a `claude --worktree` launch, so every launch
re-broke what the dispatcher's `ensure_installed` repaired on its pass (SEL-012's "written by something outside
seldon"; factory FAC-18 and FAC-21, critical-thinking-ai, 2026-11-26).

`cli_worktree_hook_step` below is that step, transcribed. The fix (`hooks.install`, SEL-052) gives the step nothing to
change: the shared value is the absolute path the CLI would write (its fixed point, so it writes nothing), and each
checkout's own `config.worktree` holds the relative `.githooks`, which git reads after the shared config and which
wins (git-worktree(1), CONFIGURATION FILE).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from seldon.core import hooks as H

SRC = Path(H.__file__).resolve().parents[2]


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["PYTHONPATH"] = os.pathsep.join(x for x in (str(SRC), env.get("PYTHONPATH")) if x)
    return subprocess.run(["git", "-C", str(root), *args], check=check, capture_output=True, text=True, env=env)


def cli_worktree_hook_step(main: Path, worktree: Path) -> str | None:
    """Claude Code 2.1.325's post-create hook step, as its bundle does it. Returns the value it wrote, or None.

    `y = <common dir config> core.hooksPath; E = isAbsolute(y) ? y : resolve(main, y);
    if (y !== E) git config core.hooksPath E   (cwd: the new worktree)`."""
    common = Path(_git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    have = _git(main, "config", "--file", str(common / "config"), "--get", "core.hooksPath", check=False)
    y = have.stdout.strip()
    if not y:
        return None
    e = y if os.path.isabs(y) else str((main / y).resolve())
    if y == e:
        return None
    _git(worktree, "config", "core.hooksPath", e)
    return e


@pytest.fixture
def primary(tmp_path):
    p = tmp_path / "primary"
    p.mkdir()
    _git(p, "init", "-q", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    (p / "README.md").write_text("x\n", encoding="utf-8")
    _git(p, "add", "README.md")
    _git(p, "commit", "-q", "-m", "init")
    H.install(p, python=sys.executable)
    return p


def _launch(p: Path, name: str) -> Path:
    """What `claude --worktree` does to the repository: add the worktree, then its hook step."""
    wt = p / ".claude" / "worktrees" / name
    _git(p, "worktree", "add", "-q", "-b", f"worktree-{name}", str(wt))
    cli_worktree_hook_step(p, wt)
    return wt


def test_a_claude_worktree_launch_leaves_the_primary_hook_installed(primary):
    """The red test: on the old install (relative value in the shared config) the CLI's step made the primary's
    value absolute and the primary reported its hook not installed."""
    from seldon.commands.verify import check_commit_hook
    assert H.status(primary)["installed"]
    _launch(primary, "one")
    st = H.status(primary)
    assert st["installed"], st["problems"]
    assert st["hooks_path"] == H.HOOKS_DIR
    assert check_commit_hook(primary, {}).symbol == "pass"


def test_the_cli_step_has_nothing_to_write_after_install(primary):
    """One writer: the shared value is the CLI's own fixed point, so its step writes nothing at all."""
    config = Path(_git(primary, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()) / "config"
    before = config.read_bytes()
    wt = primary / ".claude" / "worktrees" / "two"
    _git(primary, "worktree", "add", "-q", "-b", "worktree-two", str(wt))
    assert cli_worktree_hook_step(primary, wt) is None
    assert config.read_bytes() == before


def test_a_new_worktree_runs_its_own_checkouts_hook_before_anyone_points_it(primary):
    """`git worktree add` copies the main worktree's `config.worktree` into the new one (measured on git
    2.50.1, 2026-11-26; `copy_filtered_worktree_config` in builtin/worktree.c, from memory and not dated here), so a worktree nobody pointed (a launch
    before the dispatcher names it, or a bare `git worktree add`) resolves `.githooks` against its own top: HOOK-001's
    property, restored. On a git that does not copy it, the absolute shared value still runs the primary's tracked
    hook, never none."""
    wt = _launch(primary, "three")
    effective = _git(wt, "rev-parse", "--path-format=absolute", "--git-path", "hooks").stdout.strip()
    assert Path(effective).resolve() in {(wt / H.HOOKS_DIR).resolve(), (primary / H.HOOKS_DIR).resolve()}
    assert H.point_worktree(wt)["ok"]
    st = H.status(wt)
    assert st["installed"] and st["scope"] == "worktree", st
    assert Path(_git(wt, "rev-parse", "--path-format=absolute", "--git-path", "hooks").stdout.strip()).resolve() \
        == (wt / H.HOOKS_DIR).resolve()
    assert H.status(primary)["installed"]


def test_an_old_relative_install_is_reported_and_ensure_installed_moves_it(tmp_path):
    """A primary installed before SEL-052 holds `.githooks` in the shared config, where the next launch rewrites it.
    It is reported, and the dispatcher's launch-path `ensure_installed` moves it, after which a launch breaks
    nothing."""
    p = tmp_path / "old"
    p.mkdir()
    _git(p, "init", "-q", "-b", "main")
    (p / H.HOOKS_DIR).mkdir()
    H.hook_file(p).write_text(H.HOOK_SCRIPT, encoding="utf-8")
    H.hook_file(p).chmod(0o755)
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    _git(p, "add", "-A")
    _git(p, "commit", "-q", "--no-verify", "-m", "init")
    _git(p, "config", "--local", "core.hooksPath", H.HOOKS_DIR)
    _git(p, "config", "--local", H.PYTHON_KEY, sys.executable)
    st = H.status(p)
    assert not st["installed"] and any("Claude Code" in x for x in st["problems"]), st["problems"]
    got = H.ensure_installed(p)
    assert got["ok"] and got["changed"], got
    _launch(p, "four")
    assert H.status(p)["installed"], H.status(p)["problems"]


def test_install_refuses_a_shared_core_worktree(tmp_path):
    """git-worktree(1): `core.worktree` in the shared config must move to the main worktree's `config.worktree`
    before `extensions.worktreeConfig` is turned on; that move is not the installer's to make."""
    p = tmp_path / "cw"
    p.mkdir()
    _git(p, "init", "-q")
    _git(p, "config", "core.worktree", str(p))
    with pytest.raises(H.HookError, match="core.worktree"):
        H.install(p, python=sys.executable)
