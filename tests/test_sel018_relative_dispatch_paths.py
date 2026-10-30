"""SEL-018: a relative path in `dispatch:` resolves against the PRIMARY checkout, so a worktree session reads it.

hazbrief HB-73, headless in a worktree, could not run `seldon dispatch status`: `standing_band_ref:
../squiddy/squiddy/spend.yaml#job_token_cap_default` was joined to the worktree, where `../squiddy` does not exist.
The class (SEL-017 B, RECALL-002R): a path meant relative to the repository resolved relative to wherever the
command ran. Every relative path the `dispatch:` block names now goes through `dispatch.config_path`, which joins it
to `worktree.anchor` (the primary checkout; the directory itself outside a git work tree).

Part B's fixture: a linked worktree at the CLI's own place (`.claude/worktrees/<name>`) of a repository whose
`standing_band_ref` points at `../sibling/spend.yaml`. `dispatch status` from inside the worktree reads the cap;
with the sibling absent it still fails, naming the primary checkout.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from seldon.core import dispatch as D
from seldon.core import prior_art as PA
from seldon.core import stations as S
from seldon.core import worktree as WT

CAP = 1_234_567
REF = "../sibling/spend.yaml#caps.job"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _sibling(tmp_path: Path) -> Path:
    s = tmp_path / "sibling"
    s.mkdir()
    (s / "spend.yaml").write_text(yaml.safe_dump({"caps": {"job": CAP}}), encoding="utf-8")
    return s


@pytest.fixture
def repo(tmp_path):
    """`primary` beside `sibling/spend.yaml`, its `dispatch:` block naming the sibling by `../`, and one linked
    worktree where the CLI puts them, `primary/.claude/worktrees/x`, whose `../sibling` does not exist."""
    p = tmp_path / "primary"
    p.mkdir()
    _git(p, "init", "-q", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    (p / ".gitignore").write_text(".seldon/\n.claude/\nlogs/\n.venv/\n", encoding="utf-8")
    (p / "seldon.yaml").write_text(yaml.safe_dump({"dispatch": {
        "enabled": True, "branch": "main", "standing_band_ref": REF, "poll_interval_s": 300,
        "permission_mode": "bypassPermissions", "stop_file": ".seldon/DISPATCH_STOP",
        "log_dir": "logs/dispatch", "lease_file": ".seldon/dispatch.lock"}}), encoding="utf-8")
    _git(p, "add", "-A")
    _git(p, "commit", "-q", "-m", "init")
    wt = p / ".claude" / "worktrees" / "x"
    assert _git(p, "worktree", "add", "-q", "-b", "worktree-x", str(wt)).returncode == 0
    _sibling(tmp_path)
    return p, wt


# ================================================================================ Part A: the resolver


def test_the_plant_the_reference_does_not_exist_beside_the_worktree(repo):
    """The HB-73 condition: joined to the worktree, the reference names nothing."""
    p, wt = repo
    assert not (wt / REF.split("#")[0]).is_file()
    assert (p / REF.split("#")[0]).is_file()


def test_standing_band_resolves_from_the_worktree(repo):
    p, wt = repo
    assert D.resolve_standing_band(wt, REF) == CAP
    assert D.resolve_standing_band(p, REF) == CAP


def test_negative_control_an_absent_sibling_still_refuses_naming_the_primary(repo, tmp_path):
    p, wt = repo
    (tmp_path / "sibling" / "spend.yaml").unlink()
    with pytest.raises(D.DispatchConfigError) as exc:
        D.resolve_standing_band(wt, REF)
    msg = str(exc.value)
    assert REF in msg, "names the reference"
    assert f"primary checkout {WT.primary_checkout(wt)}" in msg, "names the checkout it was resolved from"


def test_an_absolute_path_is_left_alone(repo, tmp_path):
    _, wt = repo
    absolute = tmp_path / "sibling" / "spend.yaml"
    assert D.config_path(wt, str(absolute)) == absolute
    assert D.resolve_standing_band(wt, f"{absolute}#caps.job") == CAP


def test_from_the_primary_nothing_changes(repo):
    """The dispatcher runs in the primary: there the join is `project_dir / rel` exactly, path form included."""
    p, _ = repo
    assert D.config_path(p, ".seldon/dispatch.lock") == p / ".seldon/dispatch.lock"
    assert WT.anchor(p) is not None and WT.anchor(p) == p


def test_outside_a_git_work_tree_the_directory_is_its_own_anchor(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert WT.anchor(plain) == plain
    assert D.config_path(plain, "logs/dispatch") == plain / "logs/dispatch"


def test_every_path_key_of_the_block_resolves_at_the_primary(repo):
    """The audit (task A): stop file, lease, per-worktree leases, logs and cross-repo root are the primary's."""
    p, wt = repo
    primary = WT.primary_checkout(wt)
    cfg = D.load_dispatch_config(wt)
    assert D.config_path(wt, cfg["stop_file"]) == primary / ".seldon/DISPATCH_STOP"
    assert D.config_path(wt, cfg["lease_file"]) == primary / ".seldon/dispatch.lock"
    assert D.config_path(wt, cfg["log_dir"]) == primary / "logs/dispatch"
    assert D.worktree_lease_path(wt, cfg, "s") == primary / cfg["lease_dir"] / "s.lock"
    assert D.stuck_state_path(wt, cfg).parent == primary / ".seldon"
    assert D.config_path(wt, cfg["cross_repo_root"]).resolve() == primary.parent.resolve()
    # The kill switch is the one file: the primary's STOP is seen from the worktree.
    (p / ".seldon").mkdir()
    (p / ".seldon" / "DISPATCH_STOP").write_text("", encoding="utf-8")
    assert D.config_path(wt, cfg["stop_file"]).exists()


def test_per_worktree_leases_are_listed_from_a_worktree_relative_to_the_primary(repo):
    p, wt = repo
    cfg = D.load_dispatch_config(wt)
    (p / ".seldon" / "leases").mkdir(parents=True)
    (p / ".seldon" / "leases" / "s.lock").write_text(json.dumps({"holder": None}), encoding="utf-8")
    (row,) = D.worktree_leases(wt, cfg)
    assert row["path"] == ".seldon/leases/s.lock" and row["stem"] == "s"


def test_a_declared_interpreter_resolves_at_the_primary(repo):
    """`dispatch.stations.interpreter` (squiddy: `.venv/bin/python`) is gitignored: only the primary has it."""
    p, wt = repo
    py = p / ".venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    py.chmod(0o755)
    assert S.resolve_interpreter(".venv/bin/python", wt) == str(WT.primary_checkout(wt).absolute() / ".venv/bin/python")


def test_environment_siblings_resolve_beside_the_primary(repo, tmp_path):
    p, wt = repo
    (p / "kit.yaml").write_text(yaml.safe_dump({"environment_packages": ["sibling"]}), encoding="utf-8")
    got = S.environment_repositories(wt, {}, {"environment_ref": "kit.yaml#environment_packages"})
    assert got == {"sibling": str((tmp_path / "sibling").resolve())}


def test_the_prior_art_gate_does_not_defer_in_a_worktree_to_the_primarys_lease(repo):
    """The lease guards the primary's tree. Resolving `lease_file` at the primary must not make a worktree session
    defer its own prior-art commits to the dispatcher that launched it (before SEL-018 it never found the file)."""
    p, wt = repo
    (p / ".seldon").mkdir()
    (p / ".seldon" / "dispatch.lock").write_text(json.dumps({"holder": "pass", "pid": os.getpid()}),
                                                 encoding="utf-8")
    config = yaml.safe_load((wt / "seldon.yaml").read_text(encoding="utf-8"))
    assert D.lease_is_held(wt, D.load_dispatch_config(wt, config)), "the plant: the primary's lease is live"
    assert PA._lease_defers(wt, config) is False
    assert PA._lease_defers(p, config) is True, "in the primary the lease still defers"


# ================================================================================ Part B: `dispatch status`


def _status_project(tmp_path, neo4j_driver):
    from tests.dispatch_scaffold import git, make_project
    p = make_project(tmp_path, dispatch_extra={"standing_band_ref": REF})
    wt = p / ".claude" / "worktrees" / "x"
    git(p, "worktree", "add", "-q", "-b", "worktree-x", str(wt))
    return p, wt


def test_dispatch_status_reads_the_cap_from_a_worktree(tmp_path, neo4j_driver):
    from seldon.commands.dispatch import dispatch_group
    from tests.dispatch_scaffold import run_cli
    _sibling(tmp_path)
    p, wt = _status_project(tmp_path, neo4j_driver)
    assert not (wt / "../sibling/spend.yaml").is_file(), "the plant"
    res = run_cli(wt, dispatch_group, ["status", "--json"])
    assert res.exit_code == 0, res.output
    st = json.loads(res.output)
    assert st["standing_band"] == CAP and st["standing_band_ref"] == REF


def test_dispatch_status_from_a_worktree_still_fails_with_the_sibling_absent(tmp_path, neo4j_driver):
    from seldon.commands.dispatch import dispatch_group
    from tests.dispatch_scaffold import run_cli
    p, wt = _status_project(tmp_path, neo4j_driver)
    with pytest.raises(D.DispatchConfigError) as exc:
        run_cli(wt, dispatch_group, ["status", "--json"])
    assert f"primary checkout {WT.primary_checkout(wt)}" in str(exc.value)
