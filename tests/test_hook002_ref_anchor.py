"""HOOK-002 (AD-036 ADDENDUM 08): a `prior_art.ref` resolves at the primary checkout, the way the corpus does.

A dispatched session commits from `<primary>/.claude/worktrees/<name>`. squiddy's block is `ref: ../seldon/seldon.yaml
#prior_art`; resolved against the worktree it named `.claude/worktrees/seldon`, which does not exist, so the pre-commit
hook refused every commit before judging a file, and every dispatched squiddy merge went in with `--no-verify` (SQ-019,
SQ-029R, SQ-028R RESULTs). The ref is a repository-level path like the corpus paths ADDENDUM 06 anchored, and now goes
through the same `corpus_anchor`.

The scratch layout is `test_prior_art_ref`'s: `seldon/` (the definer), `sib/` (a corpus root) and `proj/` (refers),
siblings under tmp_path; `proj` gets a linked worktree at `proj/.claude/worktrees/w1`, where `../seldon` does not exist.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from seldon.core import hooks as H
from seldon.core import prior_art as pa
from tests.test_prior_art_ref import REF, StubLibrary, _git, _good, machine  # noqa: F401 (fixture)


#: The checkout whose `seldon` these tests import. The installed hook runs `python -m seldon`, which otherwise imports
#: the pip-installed seldon (the primary checkout's code), not the code under test.
_CODE = Path(pa.__file__).resolve().parents[2]


def _commit(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["PYTHONPATH"] = os.pathsep.join([str(_CODE), *filter(None, [env.get("PYTHONPATH")])])
    return subprocess.run(["git", "-C", str(root), "commit", *args], capture_output=True, text=True, env=env)


def _worktree(m) -> Path:
    proj = m["proj"]
    (proj / "README.md").write_text("x\n")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    wt = proj / ".claude" / "worktrees" / "w1"
    _git(proj, "worktree", "add", "-q", "-b", "worktree-w1", str(wt))
    assert not (wt.parent / "seldon").exists()       # the worktree-relative reading names nothing
    return wt


#: Settings fields that name the machine's definition and corpus: one value, wherever the project is checked out.
_MACHINE = ("roots", "suffixes", "top_n", "max_file_bytes", "k1", "b", "library_graph", "library_k", "design_dir",
            "exempt_globs", "defined_in")
#: Settings fields that name the project's own state: the checkout's, so a worktree's state stays in the worktree.
_STATE = ("log", "baseline", "verdict_ledger_without_governed")


def test_settings_from_a_worktree_equal_settings_from_the_primary(machine):
    wt = _worktree(machine)
    here, there = pa.settings(wt, machine["config"]), pa.settings(machine["proj"], machine["config"])
    assert here.defined_in == (machine["definer"] / "seldon.yaml").resolve()
    for f in _MACHINE:
        assert getattr(here, f) == getattr(there, f), f
    for f in _STATE:
        assert (getattr(here, f).relative_to(here.project_dir)
                == getattr(there, f).relative_to(there.project_dir)), f
    assert here.project_dir == wt.resolve() and here.log.is_relative_to(wt.resolve())


def test_a_ref_absent_at_the_primary_too_is_refused_naming_both_paths(machine):
    wt = _worktree(machine)
    with pytest.raises(pa.PriorArtError) as exc:
        pa.settings(wt, {"prior_art": {**REF, "ref": "../nowhere/seldon.yaml#prior_art"}})
    msg = str(exc.value)
    assert "which does not exist" in msg
    assert str((wt.parent / "nowhere" / "seldon.yaml").resolve()) in msg                 # read from the worktree
    assert str((machine["tmp"] / "nowhere" / "seldon.yaml").resolve()) in msg           # anchored at the primary


def test_a_ref_absent_outside_any_worktree_names_one_path(machine):
    with pytest.raises(pa.PriorArtError) as exc:
        pa.settings(machine["proj"], {"prior_art": {**REF, "ref": "../nowhere/seldon.yaml#prior_art"}})
    assert str(exc.value).count("nowhere") == 2       # the ref as written, and the one path it names


@pytest.fixture
def hooked_wt(machine):
    wt = _worktree(machine)
    assert H.install(machine["proj"], python=sys.executable).wrote_hook
    _git(machine["proj"], "add", "-A")
    _git(machine["proj"], "commit", "-qm", "install the commit gate")
    _git(wt, "merge", "-q", "--ff-only", "main")
    return machine, wt


def test_the_hook_in_a_worktree_judges_a_note_instead_of_refusing_the_ref(hooked_wt):
    _, wt = hooked_wt
    (wt / "docs" / "design" / "AD-099_x.md").write_text("# AD-099\n\nNo prior art section.\n")
    _git(wt, "add", "docs/design/AD-099_x.md")
    r = _commit(wt, "-m", "planted")
    assert r.returncode != 0
    assert "does not exist" not in r.stderr, r.stderr
    assert "docs/design/AD-099_x.md" in r.stderr and "AD-036-R4" in r.stderr


def test_the_hook_in_a_worktree_passes_a_note_with_its_staged_verdict(hooked_wt):
    m, wt = hooked_wt
    note = wt / "docs" / "design" / "AD-099_x.md"
    note.write_text(_good(m))
    pa.record_verdict(pa.verify_note(note, pa.settings(wt, m["config"]), library=StubLibrary()), wt, m["config"])
    _git(wt, "add", "docs/design/AD-099_x.md", "state/prior_art_verdicts.jsonl")
    r = _commit(wt, "-m", "note")
    assert r.returncode == 0, r.stderr


def test_a_worktree_commit_touching_no_note_passes(hooked_wt):
    """The defect refused every commit, note or not: the ref was read before any file was judged."""
    _, wt = hooked_wt
    (wt / "README.md").write_text("y\n")
    _git(wt, "add", "README.md")
    r = _commit(wt, "-m", "readme")
    assert r.returncode == 0, r.stderr
