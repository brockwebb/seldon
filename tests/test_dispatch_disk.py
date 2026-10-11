"""The dispatcher checks free space against its launch's own measured need (SQ-010 ADDENDUM 02 D3.4).

squiddy/docs/evidence/sq010/disk_incident.md: on 2026-10-11 a session's worktrees and clean-run clone (about
4.4 GB) took the data volume to 100 percent, on a disk that was already within a few GiB of full. Nothing
checked free space before the work started. The rule this holds: before a launch, criterion c12 compares the
free space on the volume the launch writes to with `dispatch.disk_need_factor` (default 2) times the launch's
footprint, measured at launch time from git (`git ls-tree -r -l` blob sizes of the configured branch), never a
guessed constant and never the machine-wide 25 GB floor. A shortfall is a standing condition, refused like
`dirty_tree`: no claim, no event, a line naming the need, the free space and the path, and the stuck streak
counts it.

No test here reads the machine's free space (DN-043 R-184): conftest's `_disk_free_is_a_fake` sets
`SELDON_DISK_FREE_BYTES` for every test, and the probe reads it before any statvfs.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from seldon.core import dispatch as D
from tests.test_dispatch_launch import (  # noqa: F401  (fixtures)
    _events, _git, _register, _run, _state, _stub, domain_config, project,
)

NEEDS_NEO4J = pytest.mark.usefixtures("neo4j_available")


def _blob_bytes(repo: Path, ref: str = "main") -> int:
    """The tracked tree's size the slow, obvious way: every file at `ref`, by `git cat-file -s`."""
    names = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref], cwd=repo, check=True,
                           capture_output=True, text=True).stdout.split("\n")
    total = 0
    for n in filter(None, names):
        total += int(subprocess.run(["git", "cat-file", "-s", f"{ref}:{n}"], cwd=repo, check=True,
                                    capture_output=True, text=True).stdout)
    return total


# ------------------------------------------------------------------------------------- the probe and the need

def test_the_footprint_is_the_checked_out_tree_measured_from_git(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_bytes(b"x" * 1000)
    (repo / "d").mkdir()
    (repo / "d" / "b.bin").write_bytes(b"y" * 4321)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "one")
    assert D.tree_bytes(repo, "main") == _blob_bytes(repo) == 5321


def test_the_probe_reads_the_fake_and_never_statvfs_when_it_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv(D.DISK_FREE_ENV, "12345")
    monkeypatch.setattr(D.shutil, "disk_usage", lambda p: pytest.fail("the real disk was read"))
    free, probe = D.free_bytes(tmp_path)
    assert free == 12345 and D.DISK_FREE_ENV in probe


def test_the_probe_reads_the_volume_when_no_fake_is_set(tmp_path, monkeypatch):
    monkeypatch.delenv(D.DISK_FREE_ENV, raising=False)
    seen = []

    def usage(p):
        seen.append(Path(p))
        return D.shutil._ntuple_diskusage(100, 10, 77)

    monkeypatch.setattr(D.shutil, "disk_usage", usage)
    # a directory not made yet is measured on the volume of its nearest existing parent
    assert D.free_bytes(tmp_path / "not" / "made")[0] == 77
    assert seen == [tmp_path]


def test_a_fake_that_is_not_a_byte_count_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(D.DISK_FREE_ENV, "lots")
    with pytest.raises(D.DispatchConfigError, match=D.DISK_FREE_ENV):
        D.free_bytes(tmp_path)


def test_the_need_is_the_factor_times_the_footprint(project, monkeypatch):
    cfg = D.load_dispatch_config(project)
    assert cfg["disk_need_factor"] == D.DISK_NEED_FACTOR_DEFAULT == 2
    tree = D.tree_bytes(project, "main")
    monkeypatch.setenv(D.DISK_FREE_ENV, str(2 * tree))
    st = D.disk_state(project, cfg, worktree=False)
    assert (st["footprint_bytes"], st["need_bytes"], st["free_bytes"]) == (tree, 2 * tree, 2 * tree)
    assert st["ok"] is True and st["path"] == str(project)
    monkeypatch.setenv(D.DISK_FREE_ENV, str(2 * tree - 1))
    assert D.disk_state(project, cfg, worktree=False)["ok"] is False


def test_a_worktree_launch_is_measured_where_the_worktree_goes(project, monkeypatch):
    cfg = {**D.load_dispatch_config(project), "worktree_dir": ".worktrees"}
    st = D.disk_state(project, cfg, worktree=True)
    assert st["path"] == str(project / ".worktrees") and st["launch"] == "worktree"


@pytest.mark.parametrize("bad", [0, 0.5, -1, "2", True])
def test_a_bad_need_factor_refuses_at_load(project, bad):
    import yaml
    data = yaml.safe_load((project / "seldon.yaml").read_text(encoding="utf-8"))
    data["dispatch"]["disk_need_factor"] = bad
    with pytest.raises(D.DispatchConfigError, match="disk_need_factor"):
        D.load_dispatch_config(project, data)


def test_an_unmeasurable_tree_refuses_rather_than_guessing(tmp_path, monkeypatch):
    """A repository with no commit on the branch has no tree to measure: refused, never a need of 0."""
    repo = tmp_path / "empty"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    st = D.disk_state(repo, {"branch": "main", "disk_need_factor": 2}, worktree=False)
    assert st["ok"] is False and st["read_error"]
    assert D.first_refusal_reason({"criteria": {"c12": st}}) == "disk_unmeasured"


# ------------------------------------------------------------------------------------------ through a pass

@NEEDS_NEO4J
def test_a_shortfall_refuses_cleanly_and_names_need_free_and_path(project, neo4j_driver, domain_config,
                                                                   clean_test_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)
    monkeypatch.setenv(D.DISK_FREE_ENV, "1")
    log = project / "seldon_events.jsonl"
    before = log.read_bytes() if log.exists() else b""

    res = _run(project, ["once"])
    assert res.exit_code == 0, res.output
    assert _state(neo4j_driver, tid)[0] == "proposed"               # no claim
    assert "nothing eligible" in res.output and "disk_short" in res.output
    need = 2 * D.tree_bytes(project, "main")
    assert f"need {need:,} bytes" in res.output and "free 1 bytes" in res.output
    assert str(project) in res.output
    after = log.read_bytes() if log.exists() else b""
    assert after == before, "a standing-condition refusal was written to the log"
    assert not (project / "logs" / "dispatch" / "t1.log").exists()  # nothing launched


@NEEDS_NEO4J
def test_a_shortfall_is_counted_by_the_stuck_streak(project, neo4j_driver, domain_config, clean_test_db,
                                                    monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _register(project, neo4j_driver, domain_config)
    _stub(project)
    monkeypatch.setenv(D.DISK_FREE_ENV, "1")
    for _ in range(D.STUCK_AFTER_PASSES_DEFAULT):
        _run(project, ["once"])
    stuck = _events(project, D.EVENT_STUCK)
    assert len(stuck) == 1 and stuck[0]["payload"]["criterion"] == "disk_short"


@NEEDS_NEO4J
def test_enough_space_launches_and_records_the_measurement(project, neo4j_driver, domain_config,
                                                           clean_test_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)
    need = 2 * D.tree_bytes(project, "main")
    monkeypatch.setenv(D.DISK_FREE_ENV, str(need))
    res = _run(project, ["once"])
    assert res.exit_code == 0, res.output
    assert _state(neo4j_driver, tid)[0] == "completed"
    c12 = _events(project, D.EVENT_LAUNCHED)[0]["payload"]["criteria"]["c12"]
    assert c12["ok"] is True and c12["need_bytes"] == need and c12["free_bytes"] == need


@NEEDS_NEO4J
def test_a_full_real_disk_cannot_fail_a_dispatcher_test(project, neo4j_driver, domain_config, clean_test_db,
                                                        monkeypatch):
    """R-184: the machine's free space is not an input to any test. With the real volume reporting 0 bytes
    free, a clean launch still completes, because every test reads the fake conftest sets."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert os.environ.get(D.DISK_FREE_ENV), "conftest's _disk_free_is_a_fake is not in force"
    monkeypatch.setattr(D.shutil, "disk_usage", lambda p: D.shutil._ntuple_diskusage(10 ** 12, 10 ** 12, 0))
    tid = _register(project, neo4j_driver, domain_config)
    _stub(project, task_id=tid)
    res = _run(project, ["once"])
    assert res.exit_code == 0, res.output
    assert _state(neo4j_driver, tid)[0] == "completed"


@NEEDS_NEO4J
def test_a_pass_launching_several_worktrees_measures_again_before_each(tmp_path, neo4j_driver, clean_test_db,
                                                                       monkeypatch):
    """c12 is measured before the pass launches anything. Two worktree launches in one pass must not both
    spend the room for one: the second is measured again after the first wrote its tree, and waits."""
    from seldon.commands.dispatch import dispatch_group
    from seldon.domain.loader import load_domain_config
    from tests.dispatch_scaffold import RESEARCH_YAML, add_task, make_project, register, run_cli, write_stub
    from tests.test_dispatch_parallel import NONEXCL, PARALLEL, _wait_settled

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    dc = load_domain_config(RESEARCH_YAML)
    p = make_project(tmp_path, dispatch_extra=PARALLEL)
    add_task(p, "a", NONEXCL.format(touches="out/a/"))
    add_task(p, "b", NONEXCL.format(touches="out/b/"))
    write_stub(p, {"a": {"write": {"out/a/x.txt": "a\n"}}, "b": {"write": {"out/b/x.txt": "b\n"}}})
    register(p, neo4j_driver, dc, "a", "2026-10-07T00:00:01Z")
    register(p, neo4j_driver, dc, "b", "2026-10-07T00:00:02Z")
    def written(d: Path) -> int:
        return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.is_dir() else 0

    def free(path):
        # A volume with room for one launch and a half (the pass commits records first, so the tree is measured
        # when asked): free shrinks by what the worktrees write.
        tree = D.tree_bytes(p, "main")
        return 2 * tree + tree // 2 - written(p / ".worktrees"), "fake: room minus worktrees"

    monkeypatch.setattr(D, "free_bytes", free)
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    launched = [ln for ln in res.output.splitlines() if ln.startswith("launching ")]
    assert len(launched) == 1 and "cc_tasks/a.md" in launched[0], res.output
    assert "disk_short" in res.output and "cc_tasks/b.md" in res.output
    _wait_settled(p, neo4j_driver, ["a"])
