"""DESK-001: everything a Desktop session writes into a governed repository is committed by the
tool that wrote it, and a blocked queue is visible.

Real git and the real hooks (`seldon hooks install`) in a scratch repository: what is under test
is what git and the hooks do with the commit the tool makes. The fixture is `tests/test_hooks.py`'s
(a prior-art gate, a decision register, a tracked governed ledger); the library arm is a stub, as
there.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from seldon.core import desktop_commit as DC
from seldon.core import dispatch as D
from seldon.core import hooks as H
from tests.test_hooks import _git, _good, _plant, _verify_and_record, repo  # noqa: F401 (fixture)

NOTE = "docs/design/AD-099_x.md"


def _head(repo) -> str:
    return _git(repo["dir"], "rev-parse", "HEAD").stdout.strip()


def _subject(repo) -> str:
    return _git(repo["dir"], "log", "-1", "--format=%s").stdout.strip()


def _files_in(repo, rev: str = "HEAD") -> list[str]:
    return sorted(_git(repo["dir"], "show", "--name-only", "--pretty=", rev).stdout.split())


def _porcelain(repo, *paths) -> str:
    return _git(repo["dir"], "status", "--porcelain", "--untracked-files=all", "--", *paths).stdout


def _commit(repo, paths):
    return DC.commit_governed(repo["dir"], paths, repo["config"])


# ------------------------------------------------------------------------------ the commit tool

def test_an_untracked_design_note_is_committed_and_the_tree_is_clean(repo):
    note = _plant(repo, body=_good(repo))
    _verify_and_record(repo, note)
    # The verdict line is committed first, as `seldon prior-art verify` commits its own lines
    # (AD-036-R11); the hook then finds the note's receipt in the index.
    _git(repo["dir"], "add", "governed/ledger/events.jsonl")
    _git(repo["dir"], "commit", "-qm", "verdict")
    before = _head(repo)

    out = _commit(repo, [NOTE])

    assert out.committed, out.detail
    assert out.sha == _head(repo) and _git(repo["dir"], "rev-parse", "HEAD~1").stdout.strip() == before
    assert out.message == "desktop: design: AD-099_x.md" and _subject(repo) == out.message
    assert out.drafts == []
    assert _files_in(repo) == [NOTE]
    assert _porcelain(repo) == ""


def test_an_unverified_note_commits_as_a_draft_and_is_not_a_bypass(repo):
    _plant(repo)
    out = _commit(repo, [NOTE])

    assert out.committed, out.detail
    assert _subject(repo) == "desktop: draft: design: AD-099_x.md"
    assert [d["note"] for d in out.drafts] == [NOTE]
    assert _porcelain(repo) == ""
    # The audit does not report a declared draft as a bypass ...
    assert H.bypassed(repo["dir"], repo["config"]) == []
    # ... and `seldon verify` warns on it rather than failing every later task's --strict.
    from seldon.commands.verify import check_prior_art
    r = check_prior_art(repo["dir"], repo["config"])
    assert r.symbol == "warn" and any(d.startswith(f"draft: {NOTE}") for d in r.details)


def test_a_path_outside_the_roots_refuses_and_stages_nothing(repo):
    (repo["dir"] / "seldon").mkdir()
    (repo["dir"] / "seldon" / "x.py").write_text("print(1)\n")
    before = _head(repo)

    out = _commit(repo, ["seldon/x.py"])

    assert not out.committed and out.refusal == DC.OUTSIDE_ROOTS
    assert _head(repo) == before
    assert _git(repo["dir"], "diff", "--cached", "--name-only").stdout == ""
    assert _porcelain(repo, "seldon/x.py").startswith("??")


def test_paths_escaping_the_project_ignored_or_unchanged_are_refused(repo):
    assert _commit(repo, ["../elsewhere.md"]).refusal == DC.OUTSIDE_PROJECT
    assert _commit(repo, ["docs/design/nope.md"]).refusal == DC.NOT_FOUND
    assert _commit(repo, ["docs/design/OLD.md"]).refusal == DC.UNCHANGED
    (repo["dir"] / "state").mkdir(exist_ok=True)
    cfg = dict(repo["config"], desktop_commit={"roots": {"state/": "state"}})
    (repo["dir"] / "state" / "x.md").write_text("x\n")
    assert DC.commit_governed(repo["dir"], ["state/x.md"], cfg).refusal == DC.IGNORED


def test_a_hook_refusal_returns_the_hook_text_and_leaves_nothing_staged(repo):
    # Without the commit-msg half the pre-commit hook refuses an unverified note outright (fail
    # closed), which is a hook refusal the tool must report verbatim.
    (repo["dir"] / ".githooks" / "commit-msg").unlink()
    _plant(repo)
    before = _head(repo)

    out = _commit(repo, [NOTE])

    assert not out.committed and out.refusal == DC.HOOK_REFUSED
    assert f"Prior art: {NOTE}: no prior-art verdict" in out.detail
    assert "seldon commit gate" in out.detail
    assert _head(repo) == before
    assert _porcelain(repo, NOTE).startswith("??")


def test_only_the_named_paths_are_committed(repo):
    """AD-032 FC-27: the guard is `git add -- <paths>` and `git commit -- <paths>`. Replace either
    with the whole tree and this fails: another session's staged and dirty files would go in."""
    (repo["dir"] / "README.md").write_text("someone else's staged edit\n")
    _git(repo["dir"], "add", "README.md")
    other = repo["dir"] / "docs" / "design" / "AD-098_other.md"
    other.write_text("# another session's note\n")
    _plant(repo)

    out = _commit(repo, [NOTE])

    assert out.committed, out.detail
    assert _files_in(repo) == [NOTE]
    assert _porcelain(repo, "README.md").startswith("M ")             # still staged, not committed
    assert _porcelain(repo, "docs/design/AD-098_other.md").startswith("??")


def test_the_secret_scan_refuses_a_flagged_handoff(repo, tmp_path):
    (repo["dir"] / "handoffs").mkdir()
    (repo["dir"] / "handoffs" / "h.md").write_text("session\n")
    scanner = tmp_path / "scan.sh"
    scanner.write_text("#!/bin/sh\necho \"$1:1 aws_key\"\nexit 1\n")
    scanner.chmod(0o755)
    cfg = dict(repo["config"], desktop_commit={"roots": DC.DEFAULT_ROOTS,
                                               "scan": {"roots": ["handoffs/"],
                                                        "command": [str(scanner)]}})
    out = DC.commit_governed(repo["dir"], ["handoffs/h.md"], cfg)
    assert out.refusal == DC.SECRET_FOUND and "aws_key" in out.detail
    assert _porcelain(repo, "handoffs/h.md").startswith("??")


# --------------------------------------------------------------------------------- the hooks

def test_git_commit_refuses_an_unverified_note_unless_the_subject_says_draft(repo):
    _plant(repo)
    _git(repo["dir"], "add", NOTE)
    r = _git(repo["dir"], "commit", "-m", "add a note", check=False)
    assert r.returncode == 1 and "draft:" in r.stderr and "Prior art" in r.stderr
    r = _git(repo["dir"], "commit", "-m", "draft: add a note", check=False)
    assert r.returncode == 0, r.stderr
    assert "draft admitted" in r.stderr


def test_install_writes_the_commit_msg_hook_and_status_reports_drafts(repo):
    st = H.status(repo["dir"])
    assert st["installed"] and st["drafts"]
    (repo["dir"] / ".githooks" / "commit-msg").unlink()
    st = H.status(repo["dir"])
    assert st["installed"] and not st["drafts"]          # never a problem: pre-commit fails closed


def test_is_draft_reads_the_subject_only():
    assert H.is_draft("desktop: draft: design: a.md")
    assert H.is_draft("register: draft: cc_tasks/t.md with ...")
    assert not H.is_draft("fix: drafts are handled")
    assert not H.is_draft("subject\n\ndraft: in the body")


# ----------------------------------------------------------------------- dispatch: c14, alarms

def test_the_dispatcher_holds_a_task_governed_by_a_draft(repo):
    _plant(repo)
    _commit(repo, [NOTE])
    task = repo["dir"] / "cc_tasks" / "t.md"
    task.parent.mkdir(exist_ok=True)
    task.write_text(f"# T\n\n**Governing:** {NOTE}\n")
    rows = D.governing_unverified(repo["dir"], task)
    assert [r["note"] for r in rows] == [NOTE]
    row = {"criteria": {"c14": {"unverified": rows, "ok": False}}}
    assert D.first_refusal_reason(row) == "governing_unverified"


def test_a_passing_note_does_not_hold(repo):
    note = _plant(repo, body=_good(repo))
    _verify_and_record(repo, note)
    task = repo["dir"] / "cc_tasks" / "t.md"
    task.parent.mkdir(exist_ok=True)
    task.write_text(f"# T\n\n**Governing:** {NOTE}\n")
    assert D.governing_unverified(repo["dir"], task) == []


def test_dirty_tree_alarms_on_the_first_pass_by_default():
    cfg = {"stuck_after_passes": 3,
           "stuck_after_passes_by_criterion": D.STUCK_AFTER_PASSES_BY_CRITERION_DEFAULT}
    state, alarms = D.advance_stuck({}, {"t": {"criterion": "dirty_tree"}},
                                    lambda c: D.stuck_threshold(cfg, c), "now")
    assert alarms == ["t"]
    state, alarms = D.advance_stuck({}, {"t": {"criterion": "above_band"}},
                                    lambda c: D.stuck_threshold(cfg, c), "now")
    assert alarms == []


def test_a_bad_per_criterion_threshold_is_refused(tmp_path):
    import pytest
    base = {"enabled": True, "branch": "main", "standing_band_ref": "x.yaml#a",
            "poll_interval_s": 300, "permission_mode": "bypassPermissions",
            "stop_file": ".seldon/STOP", "log_dir": "logs", "lease_file": ".seldon/l.lock"}
    for bad in ({"dirty_tree": 0}, {"no_such_reason": 1}, ["dirty_tree"]):
        with pytest.raises(D.DispatchConfigError, match="stuck_after_passes_by_criterion"):
            D.load_dispatch_config(tmp_path, {"dispatch": dict(base,
                                                               stuck_after_passes_by_criterion=bad)})
